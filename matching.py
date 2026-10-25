"""Smartfon nomini standartlashtirish va bir xil tovarni aniqlash (matching).

Turli do'konlarda bir telefon turlicha yoziladi:
    "Samsung Galaxy A55 5G 8/256GB Black"
    "Смартфон Samsung A55 5G 8GB 256GB (чёрный)"
Ikkalasi ham bitta kalitga olib kelinadi: samsung|a55 5g|8|256
"""
import re
from collections import namedtuple

Parsed = namedtuple("Parsed", "brand model ram_gb storage_gb key")

# alias -> brand
BRAND_ALIASES = {
    "samsung": "samsung", "galaxy": "samsung",
    "apple": "apple", "iphone": "apple",
    "xiaomi": "xiaomi", "redmi": "xiaomi", "poco": "xiaomi",
    "honor": "honor", "huawei": "huawei", "oppo": "oppo", "realme": "realme",
    "vivo": "vivo", "infinix": "infinix", "tecno": "tecno", "itel": "itel",
    "nokia": "nokia", "motorola": "motorola", "moto": "motorola",
    "oneplus": "oneplus", "google": "google", "pixel": "google",
    "zte": "zte", "nothing": "nothing", "tcl": "tcl",
}

# modelda saqlanmaydigan brend so'zlari (redmi/poco/iphone/pixel/moto modelning bir qismi)
BRAND_WORDS_TO_STRIP = {
    "samsung", "galaxy", "apple", "xiaomi", "honor", "huawei", "oppo", "realme",
    "vivo", "infinix", "tecno", "itel", "nokia", "motorola", "oneplus", "google",
    "zte", "nothing", "tcl",
}

BRAND_DISPLAY = {
    "samsung": "Samsung", "apple": "Apple", "xiaomi": "Xiaomi", "honor": "Honor",
    "huawei": "Huawei", "oppo": "Oppo", "realme": "Realme", "vivo": "Vivo",
    "infinix": "Infinix", "tecno": "Tecno", "itel": "Itel", "nokia": "Nokia",
    "motorola": "Motorola", "oneplus": "OnePlus", "google": "Google",
    "zte": "ZTE", "nothing": "Nothing", "tcl": "TCL",
}

NOISE = {
    "smartfon", "smartphone", "telefon", "phone", "mobile", "cell", "cellphone",
    "смартфон", "телефон", "мобильный", "сотовый",
    "dual", "sim", "dualsim", "ds", "esim", "global", "version", "eu", "ru", "uz",
    "ver", "gb", "гб", "tb", "тб", "ram", "rom", "озу", "new", "yangi", "original",
    "rasmiy", "kafolat", "garantiya", "гарантия",
}

COLORS = {
    "black", "white", "blue", "green", "red", "gold", "silver", "gray", "grey",
    "purple", "pink", "yellow", "orange", "violet", "titanium", "graphite",
    "midnight", "starlight", "lavender", "mint", "cream", "beige", "natural",
    "qora", "oq", "kok", "ko'k", "yashil", "qizil", "kumush", "oltin", "sariq",
    "чёрный", "черный", "белый", "синий", "зелёный", "зеленый", "красный",
    "золотой", "серебристый", "серый", "фиолетовый", "розовый", "желтый",
    "титановый", "графитовый",
}

ACCESSORY_WORDS = {
    "case", "cover", "glass", "protector", "charger", "cable", "adapter", "holder",
    "чехол", "стекло", "пленка", "плёнка", "зарядка", "кабель", "держатель",
    "chexol", "qopqoq", "himoya", "zaryadka", "kabel", "naushnik", "airpods",
    "watch", "soat", "buds", "band", "pad", "tablet", "planshet", "планшет",
}

_RE_RAM_EXPLICIT = re.compile(
    r"\b(\d{1,2})\s*(?:gb|гб)\s*(?:ram|озу|оператив\w*)|\b(?:ram|озу)\s*(\d{1,2})\s*(?:gb|гб)?\b"
)
_RE_SLASH = re.compile(r"\b(\d{1,2})\s*(?:gb|гб)?\s*[/+]\s*(\d{1,4})\s*(gb|гб|tb|тб)?\b")
_RE_TB = re.compile(r"\b(\d)\s*(?:tb|тб)\b")
_RE_GB = re.compile(r"\b(\d{1,4})\s*(?:gb|гб)\b")
_STORAGE_SIZES = {16, 32, 64, 128, 256, 512, 1024, 2048}


def _norm(text):
    t = text.lower().replace("ё", "е").replace("’", "'").replace("ʻ", "'")
    t = re.sub(r"[(),;|]", " ", t)
    return t


def _extract_memory(t):
    """(ram, storage, qolgan_matn)"""
    ram = storage = None

    m = _RE_RAM_EXPLICIT.search(t)
    if m:
        ram = int(m.group(1) or m.group(2))
        t = t[: m.start()] + " " + t[m.end():]

    m = _RE_SLASH.search(t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if m.group(3) in ("tb", "тб"):
            b *= 1024
        if b in _STORAGE_SIZES and a <= 24:
            if ram is None:
                ram = a
            storage = b
            t = t[: m.start()] + " " + t[m.end():]

    if storage is None:
        m = _RE_TB.search(t)
        if m:
            storage = int(m.group(1)) * 1024
            t = t[: m.start()] + " " + t[m.end():]

    if storage is None:
        sizes = [int(x) for x in _RE_GB.findall(t)]
        big = [s for s in sizes if s in _STORAGE_SIZES and s >= 32]
        if big:
            storage = max(big)
            small = [s for s in sizes if s <= 24]
            if ram is None and small:
                ram = small[0]
        t = _RE_GB.sub(" ", t)

    return ram or 0, storage or 0, t


def parse_title(title):
    """Do'kon nomidan (brand, model, ram, storage, key) ni ajratadi.
    Brend topilmasa None qaytaradi."""
    t = _norm(title)
    # Xotira hajmidan keyingi hamma narsa rang/qo'shimcha ("Lunar Grey", "Sleek Black", "Global"):
    # ularni kesib tashlaymiz, aks holda bitta telefon turli rangda turli tovar bo'lib qoladi.
    cut = 0
    for rx in (_RE_SLASH, _RE_TB, _RE_GB, _RE_RAM_EXPLICIT):
        for m in rx.finditer(t):
            cut = max(cut, m.end())
    if cut:
        t = t[:cut]
    ram, storage, t = _extract_memory(t)
    tokens = re.findall(r"[a-zа-я0-9+']+", t)

    brand = None
    for tok in tokens:
        if tok in BRAND_ALIASES:
            brand = BRAND_ALIASES[tok]
            break
    if brand is None:
        return None

    model_tokens = []
    for tok in tokens:
        if tok in NOISE or tok in COLORS or tok in BRAND_WORDS_TO_STRIP:
            continue
        model_tokens.append(tok)
    model = " ".join(model_tokens).strip()
    if not model:
        return None

    key = f"{brand}|{model}|{ram}|{storage}"
    return Parsed(brand, model, ram, storage, key)


def looks_like_phone(title):
    """Aksessuar/planshet/soat emasligini va xotira hajmi borligini tekshiradi."""
    t = _norm(title)
    words = set(re.findall(r"[a-zа-я0-9']+", t))
    if words & ACCESSORY_WORDS:
        return False
    parsed = parse_title(title)
    return bool(parsed and parsed.storage_gb)


def _pretty_token(tok):
    if tok == "iphone":
        return "iPhone"
    if tok == "oneplus":
        return "OnePlus"
    m = re.fullmatch(r"([a-z]?\d+)([ie])", tok)
    if m:                                   # "50i" -> "50i", "x7e" -> "X7e" (nova 14i, Hot 50i, Honor X7e)
        return m.group(1).upper() + m.group(2)
    if any(c.isdigit() for c in tok):
        return tok.upper()
    return tok.capitalize()


def display_title(p):
    name = " ".join(_pretty_token(t) for t in p.model.split())
    if p.brand == "samsung":
        name = f"Samsung Galaxy {name}"
    elif p.brand != "apple":
        name = f"{BRAND_DISPLAY[p.brand]} {name}"
    if p.ram_gb and p.storage_gb:
        mem = f"{p.ram_gb}/{_fmt_storage(p.storage_gb)}"
    elif p.storage_gb:
        mem = _fmt_storage(p.storage_gb)
    else:
        mem = ""
    return f"{name} {mem}".strip()


def _fmt_storage(gb):
    return "1TB" if gb == 1024 else "2TB" if gb == 2048 else f"{gb}GB"


def search_text(p):
    extras = [p.brand, p.model]
    if p.brand == "samsung":
        extras.append("galaxy")  # odamlar "galaxy a55" deb qidiradi
    if p.ram_gb:
        extras.append(f"{p.ram_gb}gb")
    if p.storage_gb:
        extras.append(f"{p.storage_gb}gb")
    return " ".join(extras).lower()
