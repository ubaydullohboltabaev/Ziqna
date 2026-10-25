"""Do'kondan kelgan taklifni (nom, narx, havola, ixtiyoriy: brend, shtrix-kod, kategoriya) bazaga yozish."""
from collections import Counter, defaultdict
from urllib.parse import urlparse

import catalog
import identify

MAX_PRICE = catalog.MAX_PRICE
_JUNK_GTIN_KEYS = 3        # bitta shtrix-kod 3+ turli tovarda uchrasa, do'kon uni noto'g'ri ishlatgan deb hisoblaymiz


def _valid_url(url):
    try:
        u = urlparse(url)
    except ValueError:
        return False
    return u.scheme in ("http", "https") and bool(u.netloc)


def _gtins(raw):
    if raw is None:
        return []
    items = raw if isinstance(raw, (list, tuple, set)) else [raw]
    out = []
    for r in items:
        g = identify.normalize_gtin(r)
        if g and g not in out:
            out.append(g)
    return out


def resolve_item(item, cfg=None):
    """Feed elementini (title, vendor, category_name, mpn ...) tasniflaydi. Resolved yoki Skip."""
    cfg = cfg or {}
    category = item.get("category") or _map_category(item.get("category_name"), cfg) or cfg.get("default_category")
    kwargs = dict(vendor=item.get("vendor"), store_category=item.get("category_name"), mpn=item.get("mpn"))
    fallback = item.get("fallback_category")
    if fallback and not category:
        # Bo'lim aralash tovarlardan iborat: avval nomga qarab aniqlaymiz, topilmasa bo'lim kategoriyasi
        try:
            return identify.resolve(item["title"], **kwargs)
        except identify.Skip as s:
            if s.reason != "no_category":
                raise
            category = fallback
    return identify.resolve(item["title"], category=category, **kwargs)


def _map_category(name, cfg):
    mapping = cfg.get("category_map") or {}
    n = catalog.norm(name or "")
    for needle, slug in mapping.items():
        if catalog.norm(needle) in n:
            return slug
    return None


def _find_product(conn, res, gtins):
    ident = res.identity
    for g in gtins:
        row = conn.execute(
            "SELECT p.id, p.brand FROM product_gtins g JOIN products p ON p.id = g.product_id WHERE g.gtin = ?",
            (g,)).fetchone()
        # Shtrix-kod boshqa brendga tegishli bo'lsa, ishonmaymiz (do'konlar tez-tez xato kod yozadi)
        if row and (row["brand"] == ident.brand or "other" in (row["brand"], ident.brand)):
            return row["id"]
    row = conn.execute("SELECT product_id FROM product_aliases WHERE key = ?", (ident.key,)).fetchone()
    if row:
        return row["product_id"]
    row = conn.execute("SELECT id FROM products WHERE key = ?", (ident.key,)).fetchone()
    return row["id"] if row else None


def _ensure_product(conn, res, title, gtins, image):
    ident = res.identity
    pid = _find_product(conn, res, gtins)
    if pid is None:
        cur = conn.execute(
            "INSERT INTO products (key, brand, model, ram_gb, storage_gb, title, search_text, image, "
            "category_id, level, mpn) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ident.key, ident.brand, ident.model, ident.ram_gb, ident.storage_gb, ident.title,
             identify.search_text(res, title), image, catalog.category_id(conn, res.category),
             ident.level, ident.mpn))
        pid = cur.lastrowid
    else:
        # qidiruv matnini yangilab turamiz (normalizatsiya yaxshilansa, eski tovarlar ham topiladigan bo'ladi)
        conn.execute("UPDATE products SET search_text = ? WHERE id = ?", (identify.search_text(res, title), pid))
        if image:
            conn.execute("UPDATE products SET image = ? WHERE id = ? AND image IS NULL", (image, pid))
    for g in gtins:
        conn.execute("INSERT OR IGNORE INTO product_gtins (gtin, product_id) VALUES (?, ?)", (g, pid))
    return pid


def upsert_offer(conn, store_id, title, url, price, image=None, in_stock=True, *,
                 category=None, vendor=None, store_category=None, gtin=None, mpn=None, resolved=None):
    """Taklifni yozadi. Natija: 'new' | 'updated' | 'unchanged' | 'skipped:<sabab>'."""
    if not title or not _valid_url(url):
        return "skipped:bad_input"
    try:
        price = int(round(float(price)))
    except (TypeError, ValueError):
        return "skipped:bad_price"
    try:
        res = resolved or identify.resolve(title, category=category, vendor=vendor,
                                           store_category=store_category, mpn=mpn)
    except identify.Skip as s:
        return f"skipped:{s.reason}"
    cat = catalog.by_slug(res.category)
    if not (cat["min_price"] <= price <= MAX_PRICE):
        return "skipped:price_range"

    product_id = _ensure_product(conn, res, title, _gtins(gtin), image)
    stock = 1 if in_stock else 0
    existing = conn.execute(
        "SELECT id, price FROM offers WHERE product_id = ? AND store_id = ?", (product_id, store_id)).fetchone()

    if existing is None:
        cur = conn.execute(
            "INSERT INTO offers (product_id, store_id, title, url, price, in_stock) VALUES (?, ?, ?, ?, ?, ?)",
            (product_id, store_id, title.strip(), url, price, stock))
        conn.execute("INSERT INTO price_history (offer_id, price) VALUES (?, ?)", (cur.lastrowid, price))
        conn.commit()
        return "new"

    changed = existing["price"] != price
    conn.execute(
        "UPDATE offers SET title = ?, url = ?, price = ?, in_stock = ?, updated_at = datetime('now') WHERE id = ?",
        (title.strip(), url, price, stock, existing["id"]))
    if changed:
        conn.execute("INSERT INTO price_history (offer_id, price) VALUES (?, ?)", (existing["id"], price))
    conn.commit()
    return "updated" if changed else "unchanged"


def _rank(item):
    try:
        price = float(item["price"])
    except (TypeError, ValueError):
        price = float("inf")
    return (not item.get("in_stock", True), price)


def prepare_items(items, cfg=None):
    """Elementlarni tasniflaydi va bitta do'konda bir tovarning bir necha varianti (ranglar)dan
    sotuvda bor eng arzonini qoldiradi. Qaytaradi: (tayyor [(item, Resolved)], o'tkazib yuborilgan Counter)."""
    skipped = Counter()
    resolved = []
    for it in items:
        try:
            resolved.append((it, resolve_item(it, cfg)))
        except identify.Skip as s:
            skipped[f"skipped:{s.reason}"] += 1

    # Noto'g'ri (hamma tovarga bir xil) shtrix-kodlarni aniqlash
    gtin_keys = defaultdict(set)
    for it, res in resolved:
        for g in _gtins(it.get("gtin")):
            gtin_keys[g].add(res.identity.key)
    junk = {g for g, keys in gtin_keys.items() if len(keys) >= _JUNK_GTIN_KEYS}

    best = {}
    for it, res in resolved:
        cur = best.get(res.identity.key)
        if cur is None or _rank(it) < _rank(cur[0]):
            best[res.identity.key] = (it, res)
    out = []
    for it, res in best.values():
        it = dict(it)
        it["gtin"] = [g for g in _gtins(it.get("gtin")) if g not in junk] or None
        out.append((it, res))
    return out, skipped


def process_items(conn, store_id, items, cfg=None):
    """Do'kon elementlarini bazaga yozadi. Qaytaradi: natijalar Counter'i."""
    prepared, stats = prepare_items(items, cfg)
    for it, res in prepared:
        stats[upsert_offer(
            conn, store_id, it["title"], it["url"], it["price"], it.get("image"), it.get("in_stock", True),
            gtin=it.get("gtin"), resolved=res)] += 1
    return stats


def cheapest_per_product(items, cfg=None):
    """Eski interfeys: bitta do'kondagi variantlardan eng arzonini qoldiradi (tasniflab bo'lmaganlari saqlanadi)."""
    prepared, _ = prepare_items(items, cfg)
    out = [it for it, _ in prepared]
    for it in items:
        try:
            resolve_item(it, cfg)
        except identify.Skip:
            out.append(it)
    return out


def mark_stale(conn, store_id, started_at):
    """Shu sinxronlashda ko'rinmagan (updated_at < started_at) sotuvdagi takliflarni 'sotuvda yo'q' qiladi."""
    cur = conn.execute(
        "UPDATE offers SET in_stock = 0 WHERE store_id = ? AND in_stock = 1 AND updated_at < ?",
        (store_id, started_at))
    conn.commit()
    return cur.rowcount
