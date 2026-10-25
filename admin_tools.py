"""Katalogni boshqarish: takroriy tovarlarni topish va birlashtirish, statistika."""
import re
from collections import defaultdict

import catalog


def merge_products(conn, from_id, to_id):
    """from_id tovarni to_id ga qo'shadi: takliflar, narx tarixi, shtrix-kodlar, kuzatuvlar ko'chadi.
    Bir do'konda ikkalasida ham taklif bo'lsa, sotuvda bor va arzonrog'i qoladi.
    Eski kalit `product_aliases` ga yoziladi: kelajakdagi yangilanishlar ham to_id ga tushadi."""
    if from_id == to_id:
        raise ValueError("Bir xil tovarni birlashtirib bo'lmaydi")
    src = conn.execute("SELECT * FROM products WHERE id = ?", (from_id,)).fetchone()
    dst = conn.execute("SELECT * FROM products WHERE id = ?", (to_id,)).fetchone()
    if src is None or dst is None:
        raise ValueError("Tovar topilmadi")

    for o in conn.execute("SELECT * FROM offers WHERE product_id = ?", (from_id,)).fetchall():
        same = conn.execute("SELECT * FROM offers WHERE product_id = ? AND store_id = ?",
                            (to_id, o["store_id"])).fetchone()
        if same is None:
            conn.execute("UPDATE offers SET product_id = ? WHERE id = ?", (to_id, o["id"]))
        elif (not o["in_stock"], o["price"]) < (not same["in_stock"], same["price"]):
            conn.execute("DELETE FROM offers WHERE id = ?", (same["id"],))
            conn.execute("UPDATE offers SET product_id = ? WHERE id = ?", (to_id, o["id"]))
        else:
            conn.execute("DELETE FROM offers WHERE id = ?", (o["id"],))

    conn.execute("UPDATE OR IGNORE product_gtins SET product_id = ? WHERE product_id = ?", (to_id, from_id))
    conn.execute("DELETE FROM product_gtins WHERE product_id = ?", (from_id,))
    conn.execute("UPDATE product_aliases SET product_id = ? WHERE product_id = ?", (to_id, from_id))
    conn.execute("INSERT OR REPLACE INTO product_aliases (key, product_id) VALUES (?, ?)", (src["key"], to_id))
    conn.execute("INSERT OR IGNORE INTO subscriptions (chat_id, product_id, baseline) "
                 "SELECT chat_id, ?, baseline FROM subscriptions WHERE product_id = ?", (to_id, from_id))
    conn.execute("DELETE FROM subscriptions WHERE product_id = ?", (from_id,))
    if not dst["image"] and src["image"]:
        conn.execute("UPDATE products SET image = ? WHERE id = ?", (src["image"], to_id))
    conn.execute("DELETE FROM products WHERE id = ?", (from_id,))
    conn.commit()


def _tokens(title):
    return set(re.findall(r"[a-zа-я0-9']+", catalog.norm(title)))


def find_duplicates(conn, category_slug=None, threshold=0.6, max_group=600):
    """O'xshash nomli tovar juftliklari (bir kategoriya va brend ichida). [(id1, title1, id2, title2, o'xshashlik)]"""
    sql = ("SELECT p.id, p.title, p.brand, p.category_id FROM products p "
           "LEFT JOIN categories c ON c.id = p.category_id")
    params = []
    if category_slug:
        sql += " WHERE c.slug = ?"
        params.append(category_slug)
    groups = defaultdict(list)
    for r in conn.execute(sql, params):
        groups[(r["category_id"], r["brand"])].append((r["id"], r["title"], _tokens(r["title"])))
    pairs = []
    for rows in groups.values():
        rows = rows[:max_group]
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                union = a[2] | b[2]
                sim = len(a[2] & b[2]) / len(union) if union else 0
                if sim >= threshold:
                    pairs.append((a[0], a[1], b[0], b[1], round(sim, 2)))
    return sorted(pairs, key=lambda p: -p[4])


def stats(conn):
    """Kategoriyalar bo'yicha: tovarlar, taklifli (2+ do'kon) tovarlar, takliflar."""
    return conn.execute(
        """SELECT COALESCE(c.name, '(kategoriyasiz)') AS category, COUNT(DISTINCT p.id) AS products,
                  COUNT(DISTINCT CASE WHEN n.cnt >= 2 THEN p.id END) AS compared,
                  COUNT(DISTINCT CASE WHEN p.level = 'title' AND c.slug != 'smartfonlar' THEN p.id END) AS weak,
                  COALESCE(SUM(n.cnt), 0) AS offers
           FROM products p
           LEFT JOIN categories c ON c.id = p.category_id
           LEFT JOIN (SELECT product_id, COUNT(*) AS cnt FROM offers WHERE in_stock = 1 GROUP BY product_id) n
                  ON n.product_id = p.id
           GROUP BY c.id ORDER BY products DESC""").fetchall()
