"""config.json dagi do'konlardan narxlarni yig'ib bazaga yozadi.

Ishlatish:  python run_scrape.py [config.json]
Cron misol: 0 */6 * * *  cd /path/to/narxtop && python run_scrape.py

Do'kon turlari: feed (YML/XML), jsonld, html. Sozlamalar: category_map, default_category.
Xavfsizlik: feed oldingisidan keskin kichik kelsa (50% dan kam), eski takliflar o'chirilmaydi.
"""
import json
import sys

import db
import ingest

cheapest_per_phone = ingest.cheapest_per_product      # eski nom (testlar va skriptlar uchun)
MIN_RATIO = 0.5


def fetch_items(store):
    import scrapers
    kind = store["type"]
    if kind == "feed":
        return scrapers.fetch_feed(store["feed_url"])
    if kind in ("jsonld", "html"):
        scrape = scrapers.scrape_jsonld if kind == "jsonld" else scrapers.scrape_html
        sections = store.get("sections")
        if not sections:
            return scrape(store)
        # Bir necha bo'lim: har biri o'z kategoriyasi bilan. Bitta bo'lim xatosi boshqalarni to'xtatmaydi.
        items, errors = [], []
        for sec in sections:
            cfg = {**store, **sec}
            try:
                got = scrape(cfg)
            except Exception as exc:
                errors.append(f"{sec['list_url']}: {exc}")
                continue
            for it in got:
                if sec.get("category"):
                    it["category"] = sec["category"]
                elif sec.get("fallback_category"):
                    it["fallback_category"] = sec["fallback_category"]
            print(f"  [{store['slug']}] {sec['list_url'].split('/katalog/')[-1].split('/')[0] or sec['list_url']}: {len(got)} ta")
            items.extend(got)
        for e in errors:
            print(f"  [{store['slug']}] bo'lim XATO: {e}")
        store["_partial"] = bool(errors)      # ba'zi bo'limlar yuklanmadi: eski takliflarni o'chirmaymiz
        if not items and errors:
            raise RuntimeError("barcha bo'limlar xato berdi")
        return items
    raise ValueError(f"noma'lum type: {kind}")


def sync_store(conn, store, items):
    """Bitta do'kon elementlarini yozadi va ko'rinmay qolganlarini 'sotuvda yo'q' qiladi. Natija: dict."""
    store_id = db.get_or_create_store(conn, store["slug"], store["name"], store.get("url"))
    started = conn.execute("SELECT datetime('now')").fetchone()[0]
    prev = conn.execute("SELECT last_count FROM stores WHERE id = ?", (store_id,)).fetchone()["last_count"]
    stats = ingest.process_items(conn, store_id, items, store)
    stale, guarded = 0, False
    if store.get("_partial") or (prev and len(items) < prev * MIN_RATIO):
        guarded = True          # feed buzilgan bo'lishi mumkin: hech narsani o'chirmaymiz
    else:
        stale = ingest.mark_stale(conn, store_id, started)
    conn.execute("UPDATE stores SET last_sync = datetime('now'), last_count = ?, status = ? WHERE id = ?",
                 (len(items), "warning" if guarded else "active", store_id))
    conn.commit()
    return {"items": len(items), "stats": dict(stats), "stale": stale, "guarded": guarded}


def run(config_path="config.json", conn=None):
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)
    conn = conn or db.connect()
    db.init_db(conn)

    for store in cfg["stores"]:
        try:
            items = fetch_items(store)
        except Exception as exc:  # bitta do'kon xatosi boshqalarni to'xtatmasin
            print(f"[{store['slug']}] XATO: {exc}")
            sid = db.get_or_create_store(conn, store["slug"], store["name"], store.get("url"))
            conn.execute("UPDATE stores SET status = 'error' WHERE id = ?", (sid,))
            conn.commit()
            continue
        r = sync_store(conn, store, items)
        note = "  OGOHLANTIRISH: feed keskin kichraydi, eski takliflar saqlandi" if r["guarded"] else ""
        print(f"[{store['slug']}] {r['items']} ta tovar -> {r['stats']}, sotuvdan chiqqan: {r['stale']}{note}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "config.json")
