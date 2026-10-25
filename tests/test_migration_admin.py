import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import admin_tools
import db
import ingest

OLD_SCHEMA = """
CREATE TABLE stores (id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL, url TEXT);
CREATE TABLE products (id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL, brand TEXT NOT NULL, model TEXT NOT NULL,
    ram_gb INTEGER NOT NULL DEFAULT 0, storage_gb INTEGER NOT NULL DEFAULT 0, title TEXT NOT NULL,
    search_text TEXT NOT NULL, image TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE offers (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE, title TEXT NOT NULL, url TEXT NOT NULL,
    price INTEGER NOT NULL, in_stock INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (product_id, store_id));
CREATE TABLE price_history (id INTEGER PRIMARY KEY, offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
    price INTEGER NOT NULL, ts TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE clicks (id INTEGER PRIMARY KEY, offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
    ts TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE subscriptions (chat_id INTEGER NOT NULL, product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    baseline INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')), PRIMARY KEY (chat_id, product_id));
CREATE INDEX idx_offers_product ON offers(product_id);
"""


def test_old_database_is_migrated_without_losing_data(tmp_path):
    path = str(tmp_path / "old.db")
    raw = sqlite3.connect(path)
    raw.executescript(OLD_SCHEMA)
    raw.execute("INSERT INTO stores (slug, name, url) VALUES ('texnomart', 'Texnomart', 'https://texnomart.uz')")
    raw.execute("INSERT INTO products (key, brand, model, ram_gb, storage_gb, title, search_text) "
                "VALUES ('honor|90 lite|8|256', 'honor', '90 lite', 8, 256, 'Honor 90 Lite 8/256GB', 'honor 90 lite')")
    raw.execute("INSERT INTO offers (product_id, store_id, title, url, price) VALUES (1, 1, 'x', 'https://t.uz/1', 2700000)")
    raw.execute("INSERT INTO price_history (offer_id, price) VALUES (1, 2700000)")
    raw.execute("INSERT INTO subscriptions (chat_id, product_id, baseline) VALUES (5, 1, 2700000)")
    raw.commit()
    raw.close()

    conn = db.connect(path)
    db.init_db(conn)
    db.init_db(conn)                                    # ikkinchi marta ham xavfsiz (idempotent)

    p = conn.execute("SELECT p.*, c.slug AS cat FROM products p JOIN categories c ON c.id = p.category_id").fetchone()
    assert p["cat"] == "smartfonlar" and p["level"] == "title" and p["key"] == "honor|90 lite|8|256"
    assert conn.execute("SELECT price FROM offers").fetchone()[0] == 2700000
    assert conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0] == 1
    assert {"status", "last_sync", "last_count"} <= {r[1] for r in conn.execute("PRAGMA table_info(stores)")}

    # eski tovar yangi taklif kelganda yana shu tovarga tushadi (kalit o'zgarmagan)
    s2 = db.get_or_create_store(conn, "asaxiy", "Asaxiy")
    ingest.upsert_offer(conn, s2, "Смартфон Honor 90 Lite 8GB 256GB", "https://a.uz/1", 2_650_000)
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0] == 2


def _setup(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_db(conn)
    a, b = db.get_or_create_store(conn, "a", "A"), db.get_or_create_store(conn, "b", "B")
    return conn, a, b


def test_merge_moves_offers_keeps_cheaper_and_aliases(tmp_path):
    conn, a, b = _setup(tmp_path)
    ingest.upsert_offer(conn, a, "Холодильник Samsung RB37J5000SA", "https://a.uz/1", 7_900_000)
    ingest.upsert_offer(conn, b, "Samsung Refrigerator Twin Cooling Plus 367L Silver", "https://b.uz/1", 7_500_000,
                        category="muzlatgichlar")
    ingest.upsert_offer(conn, a, "Samsung Refrigerator Twin Cooling Plus 367L Silver", "https://a.uz/2", 7_700_000,
                        category="muzlatgichlar")
    ids = [r[0] for r in conn.execute("SELECT id FROM products ORDER BY id")]
    assert len(ids) == 2
    keep, drop = ids[0], ids[1]
    conn.execute("INSERT INTO subscriptions (chat_id, product_id, baseline) VALUES (9, ?, 7700000)", (drop,))
    conn.commit()

    admin_tools.merge_products(conn, drop, keep)

    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1
    rows = {r["store_id"]: r["price"] for r in conn.execute("SELECT * FROM offers WHERE product_id = ?", (keep,))}
    assert rows == {a: 7_700_000, b: 7_500_000}            # A do'konda arzoni (7.7 mln) qoldi
    assert conn.execute("SELECT COUNT(*) FROM subscriptions WHERE product_id = ?", (keep,)).fetchone()[0] == 1
    # kelajakdagi yangilanish ham asosiy tovarga tushadi
    ingest.upsert_offer(conn, b, "Samsung Refrigerator Twin Cooling Plus 367L Silver", "https://b.uz/1", 7_400_000,
                        category="muzlatgichlar")
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1
    assert conn.execute("SELECT price FROM offers WHERE store_id = ?", (b,)).fetchone()[0] == 7_400_000


def test_merge_validation(tmp_path):
    conn, a, _ = _setup(tmp_path)
    ingest.upsert_offer(conn, a, "Холодильник Samsung RB37J5000SA", "https://a.uz/1", 7_900_000)
    for args in [(1, 1), (1, 99), (99, 1)]:
        try:
            admin_tools.merge_products(conn, *args)
            assert False, "xato kutilgan edi"
        except ValueError:
            pass


def test_find_duplicates_and_stats(tmp_path):
    conn, a, b = _setup(tmp_path)
    ingest.upsert_offer(conn, a, "Пылесос Dreame L10 Pro Plus", "https://a.uz/1", 3_000_000)
    ingest.upsert_offer(conn, b, "Dreame L10 Pro Plus Robot", "https://b.uz/1", 2_900_000, category="changyutgichlar")
    ingest.upsert_offer(conn, a, "Пылесос Dreame H12", "https://a.uz/2", 2_000_000)
    pairs = admin_tools.find_duplicates(conn, "changyutgichlar", threshold=0.5)
    assert len(pairs) >= 1 and "L10" in pairs[0][1] + pairs[0][3]
    s = {r["category"]: r for r in admin_tools.stats(conn)}
    assert s["Changyutgichlar"]["products"] >= 2 and s["Changyutgichlar"]["offers"] >= 3
