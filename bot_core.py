"""Bot mantig'i (Telegram'ga bog'liq emas, shuning uchun sinash oson): qidiruv, obuna, narx tushish tekshiruvi."""
import catalog

MAX_SUBS = 20          # bitta foydalanuvchi uchun
DROP_RATIO = 0.01      # kamida 1% tushsa xabar beramiz (mayda tebranishlar uchun emas)

_BEST_SQL = """
SELECT MIN(o.price) AS price FROM offers o WHERE o.product_id = ? AND o.in_stock = 1
"""


def _like(s):
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_products(conn, text, limit=6):
    tokens = catalog.norm(text).split()[:6]
    if not tokens:
        return []
    where = " AND ".join(["p.search_text LIKE ? ESCAPE '\\'"] * len(tokens))
    params = [f"%{_like(t)}%" for t in tokens]
    return conn.execute(
        f"""SELECT p.id, p.title, MIN(o.price) AS min_price, COUNT(o.id) AS n_offers
            FROM products p JOIN offers o ON o.product_id = p.id AND o.in_stock = 1
            WHERE {where} GROUP BY p.id ORDER BY n_offers DESC, min_price ASC LIMIT ?""",
        params + [limit],
    ).fetchall()


def search_similar(conn, text, limit=6):
    """Aniq natija bo'lmasa: oxirgi so'zlarni birma-bir tashlab qidiramiz ("iphone 15" -> "iphone").
    (natijalar, ishlatilgan so'rov) qaytaradi."""
    tokens = catalog.norm(text).split()[:6]
    while len(tokens) > 1:
        tokens = tokens[:-1]
        rows = search_products(conn, " ".join(tokens), limit)
        if rows:
            return rows, " ".join(tokens)
    return [], ""


def get_product(conn, product_id):
    p = conn.execute("SELECT id, title FROM products WHERE id = ?", (product_id,)).fetchone()
    if p is None:
        return None, []
    offers = conn.execute(
        "SELECT o.id, o.price, o.url, s.name AS store FROM offers o JOIN stores s ON s.id = o.store_id "
        "WHERE o.product_id = ? AND o.in_stock = 1 ORDER BY o.price ASC", (product_id,)
    ).fetchall()
    return p, offers


def is_subscribed(conn, chat_id, product_id):
    return conn.execute("SELECT 1 FROM subscriptions WHERE chat_id = ? AND product_id = ?",
                        (chat_id, product_id)).fetchone() is not None


def subscribe(conn, chat_id, product_id):
    """'ok' | 'exists' | 'limit' | 'unavailable'"""
    row = conn.execute(_BEST_SQL, (product_id,)).fetchone()
    if row is None or row["price"] is None:
        return "unavailable"
    if is_subscribed(conn, chat_id, product_id):
        return "exists"
    n = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE chat_id = ?", (chat_id,)).fetchone()[0]
    if n >= MAX_SUBS:
        return "limit"
    conn.execute("INSERT INTO subscriptions (chat_id, product_id, baseline) VALUES (?, ?, ?)",
                 (chat_id, product_id, row["price"]))
    conn.commit()
    return "ok"


def unsubscribe(conn, chat_id, product_id):
    conn.execute("DELETE FROM subscriptions WHERE chat_id = ? AND product_id = ?", (chat_id, product_id))
    conn.commit()


def drop_chat(conn, chat_id):
    conn.execute("DELETE FROM subscriptions WHERE chat_id = ?", (chat_id,))
    conn.commit()


def list_subscriptions(conn, chat_id):
    return conn.execute(
        "SELECT p.id, p.title, s.baseline, (SELECT MIN(o.price) FROM offers o "
        "WHERE o.product_id = p.id AND o.in_stock = 1) AS now_price "
        "FROM subscriptions s JOIN products p ON p.id = s.product_id WHERE s.chat_id = ? ORDER BY s.created_at",
        (chat_id,),
    ).fetchall()


def check_alerts(conn, send):
    """Har bir obunani tekshiradi. send(chat_id, product_id, title, old, new, store) -> 'ok'|'blocked'|'error'.
    Narx >=1% tushsa xabar yuboriladi va baza narx yangilanadi. Narx oshsa, baza ham ko'tariladi
    (keyingi tushishni ushlash uchun). Qaytaradi: yuborilgan xabarlar soni."""
    sent = 0
    subs = conn.execute("SELECT chat_id, product_id, baseline FROM subscriptions").fetchall()
    blocked = set()
    for s in subs:
        if s["chat_id"] in blocked:
            continue
        best = conn.execute(
            "SELECT o.price, st.name AS store FROM offers o JOIN stores st ON st.id = o.store_id "
            "WHERE o.product_id = ? AND o.in_stock = 1 ORDER BY o.price ASC LIMIT 1", (s["product_id"],)
        ).fetchone()
        if best is None:
            continue
        price, base = best["price"], s["baseline"]
        if price <= base * (1 - DROP_RATIO):
            title = conn.execute("SELECT title FROM products WHERE id = ?", (s["product_id"],)).fetchone()["title"]
            result = send(s["chat_id"], s["product_id"], title, base, price, best["store"])
            if result == "ok":
                sent += 1
                conn.execute("UPDATE subscriptions SET baseline = ? WHERE chat_id = ? AND product_id = ?",
                             (price, s["chat_id"], s["product_id"]))
            elif result == "blocked":
                blocked.add(s["chat_id"])
        elif price > base:
            conn.execute("UPDATE subscriptions SET baseline = ? WHERE chat_id = ? AND product_id = ?",
                         (price, s["chat_id"], s["product_id"]))
    for chat_id in blocked:
        conn.execute("DELETE FROM subscriptions WHERE chat_id = ?", (chat_id,))
    conn.commit()
    return sent
