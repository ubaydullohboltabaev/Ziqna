"""SQLite ma'lumotlar bazasi: sxema, ulanish va eski bazalarni yangilash (migratsiya)."""
import os
import sqlite3

DEFAULT_DB = os.environ.get("NARXTOP_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "narxtop.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS stores (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    url TEXT,
    status TEXT NOT NULL DEFAULT 'active',     -- active | paused
    last_sync TEXT,
    last_count INTEGER
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES categories(id),
    sort INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    key TEXT UNIQUE NOT NULL,          -- moslashtirish kaliti (telefon: brand|model|ram|storage)
    brand TEXT NOT NULL,
    model TEXT NOT NULL,
    ram_gb INTEGER NOT NULL DEFAULT 0,
    storage_gb INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,               -- ko'rsatiladigan nom
    search_text TEXT NOT NULL,
    image TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    category_id INTEGER REFERENCES categories(id),
    level TEXT NOT NULL DEFAULT 'title',   -- ishonch: title (nom) | model (model kodi) | gtin
    mpn TEXT
);

CREATE TABLE IF NOT EXISTS product_gtins (
    gtin TEXT PRIMARY KEY,             -- bitta tovarning bir nechta shtrix-kodi (ranglar) bo'lishi mumkin
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS product_aliases (
    key TEXT PRIMARY KEY,              -- qo'shib yuborilgan tovarning eski kaliti -> asosiy tovar
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    title TEXT NOT NULL,               -- do'kondagi asl nom
    url TEXT NOT NULL,
    price INTEGER NOT NULL,            -- so'mda
    in_stock INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (product_id, store_id)
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY,
    offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
    price INTEGER NOT NULL,
    ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clicks (
    id INTEGER PRIMARY KEY,
    offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
    ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS subscriptions (
    chat_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    baseline INTEGER NOT NULL,         -- oxirgi ma'lum eng arzon narx; undan tushsa xabar beramiz
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (chat_id, product_id)
);
"""

# Eski bazalarda yo'q ustunlar: (jadval, ustun, ta'rif)
_NEW_COLUMNS = [
    ("stores", "status", "TEXT NOT NULL DEFAULT 'active'"),
    ("stores", "last_sync", "TEXT"),
    ("stores", "last_count", "INTEGER"),
    ("products", "category_id", "INTEGER REFERENCES categories(id)"),
    ("products", "level", "TEXT NOT NULL DEFAULT 'title'"),
    ("products", "mpn", "TEXT"),
]

# Ustunlar mavjud bo'lgandan keyin yaratiladigan indekslar
_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_offers_product ON offers(product_id);
CREATE INDEX IF NOT EXISTS idx_offers_store ON offers(store_id);
CREATE INDEX IF NOT EXISTS idx_history_offer ON price_history(offer_id, ts);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand);
"""


def connect(path=None):
    conn = sqlite3.connect(path or DEFAULT_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _columns(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn):
    """Eski (1-versiya) bazaga yangi ustunlarni qo'shadi. Mavjud ma'lumot saqlanadi."""
    for table, col, ddl in _NEW_COLUMNS:
        if col not in _columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    conn.commit()


def init_db(conn):
    import catalog                      # kech import: catalog.py db.py ga bog'liq emas
    conn.executescript(SCHEMA)
    migrate(conn)
    conn.executescript(_INDEXES)
    catalog.sync(conn)
    # Kategoriyasiz eski tovarlar (1-versiyada faqat smartfonlar bo'lgan)
    phones = catalog.category_id(conn, "smartfonlar")
    if phones is not None:
        conn.execute("UPDATE products SET category_id = ? WHERE category_id IS NULL", (phones,))
    conn.commit()


def get_or_create_store(conn, slug, name, url=None):
    row = conn.execute("SELECT id FROM stores WHERE slug = ?", (slug,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO stores (slug, name, url) VALUES (?, ?, ?)", (slug, name, url)
    )
    conn.commit()
    return cur.lastrowid
