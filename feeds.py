"""Do'kon feedlarini (YML/XML) o'qish. Yandex Market (YML) formatiga mos; Akakce/Cimri ham shunday feed oladi.

Har bir element: title, url, price, image, in_stock, vendor, gtin, mpn, category_name, currency.
"""
from defusedxml import ElementTree as ET

UZS_CODES = {"UZS", "SUM", "SO'M", "СУМ", ""}      # currencyId bo'sh bo'lsa so'm deb hisoblaymiz


def _text(node, tag):
    v = node.findtext(tag)
    return v.strip() if v and v.strip() else None


def _category_names(root):
    """categoryId -> 'Ota > Bola' yo'li."""
    nodes = {}
    for c in root.iter("category"):
        cid = c.get("id")
        if cid:
            nodes[cid] = ((c.text or "").strip(), c.get("parentId"))
    out = {}
    for cid in nodes:
        parts, cur, seen = [], cid, set()
        while cur in nodes and cur not in seen:
            seen.add(cur)
            name, parent = nodes[cur]
            parts.append(name)
            cur = parent
        out[cid] = " > ".join(reversed(parts))
    return out


def parse_yml(xml_bytes):
    """YML feedni elementlar ro'yxatiga aylantiradi. Noto'g'ri XML bo'lsa xato ko'taradi."""
    root = ET.fromstring(xml_bytes)
    cats = _category_names(root)
    items = []
    for offer in root.iter("offer"):
        vendor = _text(offer, "vendor")
        name = _text(offer, "name")
        if not name:
            name = " ".join(x for x in (vendor, _text(offer, "model")) if x) or None
        price, url = _text(offer, "price"), _text(offer, "url")
        if not (name and price and url):
            continue
        barcodes = [b.text.strip() for b in offer.findall("barcode") if b.text and b.text.strip()]
        items.append({
            "title": name,
            "url": url,
            "price": price,
            "image": _text(offer, "picture"),
            "in_stock": offer.get("available", "true").lower() != "false",
            "vendor": vendor,
            "gtin": barcodes or None,
            "mpn": _text(offer, "vendorCode"),
            "category_name": cats.get(_text(offer, "categoryId") or ""),
            "currency": (_text(offer, "currencyId") or "").upper(),
        })
    return items


def audit(items, cfg=None):
    """Feed sifatini tekshiradi (bazaga yozmasdan). Hisobot dict qaytaradi."""
    import ingest
    import identify
    from collections import Counter

    n = len(items)
    rep = {"total": n, "problems": [], "warnings": []}
    if n == 0:
        rep["problems"].append("Feedda birorta yaroqli tovar topilmadi (name/price/url bo'lishi shart).")
        return rep

    rep["wrong_currency"] = sum(1 for i in items if i.get("currency") not in UZS_CODES)
    rep["with_gtin"] = sum(1 for i in items if any(identify.normalize_gtin(g) for g in (i.get("gtin") or [])))
    rep["with_vendor"] = sum(1 for i in items if i.get("vendor"))
    rep["with_image"] = sum(1 for i in items if i.get("image"))
    rep["in_stock"] = sum(1 for i in items if i.get("in_stock", True))
    rep["bad_urls"] = sum(1 for i in items if not ingest._valid_url(i.get("url")))

    dup_urls = n - len({i["url"] for i in items})
    rep["duplicate_urls"] = dup_urls

    prepared, skipped = ingest.prepare_items(items, cfg)
    rep["skipped"] = dict(skipped)
    rep["matched"] = len(prepared)
    rep["categories"] = dict(Counter(res.category for _, res in prepared).most_common())
    rep["levels"] = dict(Counter(res.identity.level for _, res in prepared))
    rep["unclassified_examples"] = [i["title"] for i in items
                                    if _is_skip(i, cfg)][:5]

    if rep["wrong_currency"]:
        rep["problems"].append(f"{rep['wrong_currency']} ta tovar so'mda emas (currencyId). Narxlar so'mda bo'lishi kerak.")
    if rep["bad_urls"]:
        rep["problems"].append(f"{rep['bad_urls']} ta havola noto'g'ri (http/https bo'lishi kerak).")
    if rep["matched"] == 0:
        rep["problems"].append("Birorta tovar kategoriyaga tushmadi. config'da category_map yoki default_category kerak.")
    if rep["with_gtin"] / n < 0.3:
        rep["warnings"].append("Shtrix-kod (barcode) kam. Boshqa do'konlar bilan to'g'ri moslash uchun qo'shish tavsiya etiladi.")
    if rep["with_vendor"] / n < 0.5:
        rep["warnings"].append("Brend (vendor) kam: moslash aniqligi pasayadi.")
    if rep["with_image"] / n < 0.7:
        rep["warnings"].append("Rasmlar kam.")
    if dup_urls:
        rep["warnings"].append(f"{dup_urls} ta takroriy havola bor.")
    if skipped:
        top = ", ".join(f"{k.split(':', 1)[-1]}={v}" for k, v in skipped.most_common(3))
        rep["warnings"].append(f"O'tkazib yuborilgan tovarlar: {top}.")
    return rep


def _is_skip(item, cfg):
    import identify
    import ingest
    try:
        ingest.resolve_item(item, cfg)
        return False
    except identify.Skip:
        return True
