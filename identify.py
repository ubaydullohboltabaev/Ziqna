"""Tovarni aniqlash: do'kon nomidan bir xil tovar kalitini chiqarish.

Ishonch darajasi (level):
  gtin  - shtrix-kod bo'yicha (ingest.py da, mavjud tovarga bog'lash uchun)
  model - brend + ishlab chiqaruvchi model kodi (masalan RB37J5000SA)
  title - faqat nom bo'yicha (eng kuchsiz; admin.py duplicates bilan tekshiriladi)
Telefonlar uchun matching.py dagi maxsus qoidalar ishlatiladi.
"""
import re
from collections import namedtuple

import catalog
import matching

Identity = namedtuple("Identity", "key brand model title level ram_gb storage_gb mpn")
Resolved = namedtuple("Resolved", "category identity")


class Skip(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


BRANDS = {
    "samsung", "lg", "artel", "midea", "bosch", "haier", "beko", "indesit", "ariston", "gorenje", "hisense",
    "tcl", "sony", "panasonic", "philips", "tefal", "redmond", "polaris", "vitek", "scarlett", "moulinex",
    "braun", "dyson", "xiaomi", "roborock", "dreame", "apple", "lenovo", "hp", "asus", "acer", "dell", "msi",
    "huawei", "honor", "realme", "oppo", "vivo", "tecno", "infinix", "jbl", "anker", "logitech", "a4tech",
    "canon", "epson", "brother", "tplink", "zte", "ugreen", "sharp", "toshiba", "kenwood", "delonghi",
    "nikai", "shivaki", "elenberg", "avalon", "ballu", "electrolux", "zanussi", "whirlpool", "miele", "smeg",
    "candy", "hotpoint", "daewoo", "aeg", "siemens", "vestel", "bork", "garlyn", "sencor", "maxwell",
    "rowenta", "krups", "nespresso", "saeco", "gigabyte", "kingston", "adata", "seagate", "wd", "sandisk",
    "intel", "amd", "nvidia", "razer", "hyperx", "corsair", "benq", "aoc", "viewsonic", "gree", "mitsubishi",
    "daikin", "carrier", "hitachi", "casio", "garmin", "amazfit", "baseus", "remax", "oneplus", "nothing",
    "google", "motorola", "nokia", "itel", "poco", "redmi", "zepter", "supra", "mystery", "dexp", "irbis",
}

BRAND_ALIAS = {"mi": "xiaomi", "tp": "tplink", "hewlett": "hp", "galaxy": "samsung", "iphone": "apple",
               "macbook": "apple", "ipad": "apple", "airpods": "apple", "redmi": "xiaomi", "poco": "xiaomi"}

BRAND_DISPLAY_EXTRA = {
    "lg": "LG", "hp": "HP", "msi": "MSI", "tcl": "TCL", "jbl": "JBL", "zte": "ZTE", "tplink": "TP-Link",
    "ugreen": "UGREEN", "a4tech": "A4Tech", "aoc": "AOC", "aeg": "AEG", "wd": "WD", "amd": "AMD",
    "adata": "ADATA", "dexp": "DEXP", "other": "Boshqa", "oneplus": "OnePlus", "hyperx": "HyperX",
    "delonghi": "De'Longhi", "ballu": "Ballu",
}

_EXTRA_COLORS = {
    "oq", "qora", "kulrang", "yashil", "qizil", "sariq", "pushti", "jigarrang", "бежевый", "коричневый",
    "графит", "grafit", "inox", "нержавейка", "steel", "cream", "белый", "черный", "серый", "серебристый",
    "красный", "синий", "зеленый", "желтый", "розовый", "золотой", "серебряный", "темный", "светлый",
    "beige", "brown", "chrome", "bronze", "ivory", "dark", "light",
}
_NOISE = matching.NOISE | matching.COLORS | _EXTRA_COLORS | {
    "smart", "wifi", "wi", "fi", "new", "yangi", "ta", "dona", "sht", "шт", "для", "uchun", "va", "и", "with", "the",
}

_UNIT_RX = re.compile(
    r"^\d+([.,]\d+)?(gb|tb|mb|mah|w|kw|v|hz|btu|kg|g|l|ml|mm|cm|m|inch|in|k|p|nm|ghz|mhz|rpm|bar|db|kwh|"
    r"шт|л|кг|вт|гц|ta)$", re.I)
_NOT_CODE_RX = re.compile(r"^(i[3579]|r[3579]|u[579])\d{3,5}[a-z]{0,2}$|^(rtx|gtx|rx|gt|ddr|lpddr|usb|hdmi|wifi|bluetooth)\d*[a-z]?$",
                          re.I)
_SPLIT_CODE_RX = re.compile(r"\b([A-Z]{2,4})\s+([A-Z]\d{3,}[A-Za-z0-9]*)\b")
_CODE_RX = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-_/.]{2,}[A-Za-z0-9]")


def brand_display(brand):
    b = (brand or "other").lower()
    return matching.BRAND_DISPLAY.get(b) or BRAND_DISPLAY_EXTRA.get(b) or b.title()


def normalize_gtin(raw):
    """To'g'ri GTIN/EAN (8, 12, 13, 14 raqam, nazorat raqami to'g'ri) yoki None."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) not in (8, 12, 13, 14) or len(set(digits)) == 1:
        return None
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits[:-1])))
    return digits if (10 - total % 10) % 10 == int(digits[-1]) else None


def _clean_code(token):
    base = token.split("/")[0]
    alnum = re.sub(r"[^A-Za-z0-9]", "", base).upper()
    if len(alnum) < 4 or not re.search(r"[A-Z]", alnum) or not re.search(r"\d", alnum):
        return None
    if _UNIT_RX.match(base) or _NOT_CODE_RX.match(alnum):
        return None
    if alnum.lower() in BRANDS or alnum.lower() in BRAND_ALIAS:
        return None
    return alnum


def extract_model_code(title):
    """Nomdan model kodini topadi: harf+raqam aralash eng 'raqamli' bo'lak (RB37J5000SA/WT -> RB37J5000SA)."""
    best, best_score = None, (0, 0)
    # "RK M1201" (bo'shliq bilan yozilgan) -> "RKM1201": qisqa bosh harfli prefiks + harf-raqamli bo'lak
    text = _SPLIT_CODE_RX.sub(
        lambda m: m.group(1) + m.group(2) if m.group(1).lower() not in BRANDS else m.group(0), title or "")
    for tok in _CODE_RX.findall(text):
        code = _clean_code(tok)
        if not code:
            continue
        score = (sum(c.isdigit() for c in code), len(code))
        if score > best_score:
            best, best_score = code, score
    return best


def detect_brand(title, vendor=None):
    """Brend (kichik harf, kalit shaklida). Avval feeddagi vendor, keyin nomdagi so'zlar."""
    for text in (vendor, title):
        for tok in re.findall(r"[a-zа-я0-9]+", catalog.norm(text or "")):
            tok = BRAND_ALIAS.get(tok, tok)
            if tok in BRANDS:
                return tok
    v = re.sub(r"[^a-z0-9]", "", catalog.norm(vendor or ""))
    return v or "other"


def _fallback_tokens(title, brand, category_slug=None):
    out = set()
    text = catalog.norm(title)
    cat = catalog.by_slug(category_slug) if category_slug else None
    if cat:                              # kategoriya so'zlari ("пылесос", "air fryer") kalitga kirmasin
        for rx in cat["keywords"]:
            text = rx.sub(" ", text)
    for tok in re.findall(r"[a-zа-я0-9']+", text):
        if tok in _NOISE or tok == brand or tok in BRAND_ALIAS:
            continue
        out.add(tok)
    return sorted(out)


def identify_generic(category_slug, title, vendor=None, mpn=None):
    brand = detect_brand(title, vendor)
    code = extract_model_code(title) or (_clean_code(str(mpn)) if mpn else None)
    pretty = re.sub(r"\s+", " ", title).strip()[:140]
    if code:
        return Identity(f"g|{brand}|{code}", brand, code, pretty, "model", 0, 0, code)
    tokens = _fallback_tokens(title, brand, category_slug)
    return Identity(f"g|{category_slug}|{brand}|{' '.join(tokens)}", brand, " ".join(tokens), pretty,
                    "title", 0, 0, None)


def resolve(title, category=None, vendor=None, store_category=None, mpn=None):
    """(kategoriya, Identity) qaytaradi yoki Skip(reason) ko'taradi."""
    slug = category
    if slug:
        if catalog.by_slug(slug) is None:
            raise Skip("unknown_category")
        if catalog.is_excluded(title, slug):
            raise Skip("accessory")
    else:
        slug = catalog.classify(title, store_category)
        if slug is None and matching.looks_like_phone(title):
            slug = "smartfonlar"        # nomda "smartfon" so'zi yo'q, lekin telefon ko'rinishida
    if slug is None:
        raise Skip("no_category")
    cat = catalog.by_slug(slug)
    if cat is None:
        raise Skip("unknown_category")

    if cat["matcher"] == "phone":
        if not matching.looks_like_phone(title):
            raise Skip("not_phone")
        p = matching.parse_title(title)
        ident = Identity(p.key, p.brand, p.model, matching.display_title(p), "title",
                         p.ram_gb, p.storage_gb, None)
        return Resolved(slug, ident)
    return Resolved(slug, identify_generic(slug, title, vendor, mpn))


def search_text(res, title):
    ident = res.identity
    cat = catalog.by_slug(res.category)
    parts = [ident.title, brand_display(ident.brand) if ident.brand != "other" else "", ident.mpn or "",
             cat["name"] if cat else "", title]
    if res.category == "smartfonlar":
        parts.append(matching.search_text(matching.parse_title(title)))
    return catalog.norm(" ".join(p for p in parts if p))
