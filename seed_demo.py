"""DEMO ma'lumot: sayt qanday ko'rinishini sinash uchun.

DIQQAT: bu yerdagi do'konlar va narxlar to'qima (fiktiv) va haqiqiy bozorni aks ettirmaydi.
Haqiqiy ma'lumot uchun run_scrape.py dan foydalaning.

Ishlatish:  python seed_demo.py [--reset]
"""
import random
import sys
import zlib
from datetime import datetime, timedelta

import db
import ingest

STORES = [
    ("demo-1", "Demo Do'kon 1", "https://example.com/1"),
    ("demo-2", "Demo Do'kon 2", "https://example.com/2"),
    ("demo-3", "Demo Do'kon 3", "https://example.com/3"),
    ("demo-4", "Demo Do'kon 4", "https://example.com/4"),
]

# (turli do'konlardagi nomlar, taxminiy bazaviy narx so'mda)
PHONES = [
    (["Samsung Galaxy A55 5G 8/256GB Black", "Смартфон Samsung A55 5G 8GB 256GB", "Samsung A55 5G 8/256 GB"], 4_300_000),
    (["Samsung Galaxy A35 5G 8/256GB", "Смартфон Samsung Galaxy A35 5G 8GB/256GB"], 3_400_000),
    (["Samsung Galaxy S24 Ultra 12/256GB", "Samsung S24 Ultra 12GB 256GB Titanium"], 11_900_000),
    (["Apple iPhone 15 128GB Black", "iPhone 15 128 GB", "Смартфон Apple iPhone 15 128GB"], 8_500_000),
    (["Apple iPhone 15 Pro Max 256GB Natural Titanium", "iPhone 15 Pro Max 256GB"], 14_500_000),
    (["Apple iPhone 14 128GB", "iPhone 14 128 GB Midnight", "Смартфон iPhone 14 128GB"], 7_000_000),
    (["Xiaomi Redmi Note 13 Pro 8/256GB Global", "Redmi Note 13 Pro 8GB RAM 256GB", "Смартфон Xiaomi Redmi Note 13 Pro 8/256"], 3_600_000),
    (["Xiaomi Redmi 13C 4/128GB", "Redmi 13C 4GB 128GB Blue"], 1_350_000),
    (["Xiaomi Poco X6 Pro 12/512GB", "Poco X6 Pro 12GB/512GB"], 4_700_000),
    (["Honor 90 Lite 8/256GB", "Смартфон Honor 90 Lite 8GB 256GB"], 2_700_000),
    (["Realme C67 8/256GB", "Смартфон Realme C67 8GB 256GB"], 2_300_000),
    (["Infinix Hot 40 Pro 8/256GB", "Infinix Hot 40 Pro 8GB 256GB Black"], 1_800_000),
    (["Tecno Spark 20 Pro 8/256GB", "Смартфон Tecno Spark 20 Pro 8/256GB"], 1_900_000),
    (["Oppo A58 6/128GB", "Смартфон OPPO A58 6GB 128GB"], 2_000_000),
]


def seed(conn, reset=False, seed_value=7):
    db.init_db(conn)
    if reset:
        for tbl in ("clicks", "price_history", "offers", "products", "stores"):
            conn.execute(f"DELETE FROM {tbl}")
        conn.commit()

    rnd = random.Random(seed_value)
    store_ids = [db.get_or_create_store(conn, s, n, u) for s, n, u in STORES]
    now = datetime.now()

    for names, base in PHONES:
        # har bir do'konda ham hamma tovar bo'lavermaydi, lekin kamida 2 ta taklif bo'lsin
        chosen = [i for i in range(len(store_ids)) if rnd.random() >= 0.15]
        while len(chosen) < 2:
            chosen.append(rnd.choice([i for i in range(len(store_ids)) if i not in chosen]))
        for idx in sorted(chosen):
            store_id = store_ids[idx]
            title = names[idx % len(names)]
            price = int(base * rnd.uniform(0.94, 1.12) / 1000) * 1000
            url = f"https://example.com/{store_id}/{zlib.crc32(title.encode()) % 10**6}"
            ingest.upsert_offer(conn, store_id, title, url, price)

    # 45 kunlik narx tarixi (tasodifiy yurish)
    offers = conn.execute("SELECT id, price FROM offers").fetchall()
    conn.execute("DELETE FROM price_history")
    for o in offers:
        price = o["price"]
        series = []
        for day in range(45, -1, -1):
            if rnd.random() < 0.25:
                price = int(price * rnd.uniform(0.97, 1.03) / 1000) * 1000
            series.append((now - timedelta(days=day), price))
        series[-1] = (series[-1][0], o["price"])
        last = None
        for ts, p in series:
            if p != last:
                conn.execute("INSERT INTO price_history (offer_id, price, ts) VALUES (?, ?, ?)",
                             (o["id"], p, ts.strftime("%Y-%m-%d %H:%M:%S")))
                last = p
    conn.commit()


if __name__ == "__main__":
    conn = db.connect()
    seed(conn, reset="--reset" in sys.argv)
    n = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    m = conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0]
    print(f"Demo tayyor: {n} ta smartfon, {m} ta taklif.")
