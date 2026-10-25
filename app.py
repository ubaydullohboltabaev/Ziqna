"""Ziqna — O'zbekiston do'konlari narxlarini taqqoslash sayti (Flask)."""
import math
import os
from urllib.parse import urlparse

from flask import Flask, abort, g, redirect, render_template, request, url_for
from markupsafe import Markup

import brand
import catalog
import db
import identify
import pricing

PER_PAGE = 24
SORTS = {
    "cheap": ("min_price ASC", "Avval arzonlari"),
    "expensive": ("min_price DESC", "Avval qimmatlari"),
    "stores": ("n_offers DESC, min_price ASC", "Do'kon soni bo'yicha"),
    "new": ("p.id DESC", "Yangilari"),
}

LIST_SQL = """
SELECT p.id, p.title, p.brand, p.image, p.ram_gb, p.storage_gb, c.slug AS cat_slug, c.name AS cat_name,
       MIN(o.price) AS min_price, MAX(o.price) AS max_price, COUNT(o.id) AS n_offers
FROM products p
JOIN offers o ON o.product_id = p.id AND o.in_stock = 1
LEFT JOIN categories c ON c.id = p.category_id
{where}
GROUP BY p.id
ORDER BY {order}
"""


def _escape_like(s):
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def create_app(db_path=None):
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path or db.DEFAULT_DB

    boot = db.connect(app.config["DB_PATH"])
    db.init_db(boot)
    boot.close()

    def get_db():
        if "db" not in g:
            g.db = db.connect(app.config["DB_PATH"])
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    app.jinja_env.filters["som"] = pricing.fmt_som

    @app.context_processor
    def inject_globals():
        row = get_db().execute("SELECT 1 FROM stores WHERE slug LIKE 'demo-%' LIMIT 1").fetchone()
        cats = get_db().execute(
            "SELECT c.slug, c.name, COUNT(DISTINCT p.id) AS n FROM categories c "
            "JOIN products p ON p.category_id = c.id "
            "JOIN offers o ON o.product_id = p.id AND o.in_stock = 1 "
            "GROUP BY c.id ORDER BY n DESC, c.name").fetchall()
        return {"brand": brand, "is_demo": row is not None, "brand_name": identify.brand_display, "nav_categories": cats}

    def query_products(q="", brand="", sort="cheap", page=1, category=""):
        where, params = [], []
        if category:
            where.append("c.slug = ?")
            params.append(category)
        for tok in catalog.norm(q).split()[:6]:
            where.append("p.search_text LIKE ? ESCAPE '\\'")
            params.append(f"%{_escape_like(tok)}%")
        if brand:
            where.append("p.brand = ?")
            params.append(brand)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        order = SORTS.get(sort, SORTS["cheap"])[0]
        sql = LIST_SQL.format(where=where_sql, order=order)
        rows = get_db().execute(sql, params).fetchall()
        total = len(rows)
        start = (page - 1) * PER_PAGE
        return rows[start:start + PER_PAGE], total

    @app.route("/")
    def index():
        rows, _ = query_products(sort="stores")
        return render_template("index.html", products=rows[:12])

    def listing(category_slug=""):
        q = request.args.get("q", "").strip()[:80]
        brand = request.args.get("brand", "").strip().lower()
        sort = request.args.get("sort", "cheap")
        if sort not in SORTS:
            sort = "cheap"
        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1
        category = category_slug or request.args.get("category", "").strip()
        cat = None
        if category:
            cat = get_db().execute("SELECT slug, name FROM categories WHERE slug = ?", (category,)).fetchone()
            if cat is None:
                if category_slug:
                    abort(404)
                category = ""
        brands = get_db().execute(
            "SELECT p.brand, COUNT(DISTINCT p.id) AS n FROM products p "
            "JOIN offers o ON o.product_id = p.id AND o.in_stock = 1 "
            "LEFT JOIN categories c ON c.id = p.category_id "
            + ("WHERE c.slug = ? " if category else "") +
            "GROUP BY p.brand ORDER BY n DESC LIMIT 30", ([category] if category else [])).fetchall()
        if brand not in {b["brand"] for b in brands}:
            brand = ""
        rows, total = query_products(q, brand, sort, page, category)
        pages = max(1, math.ceil(total / PER_PAGE))
        return render_template("search.html", products=rows, total=total, q=q, brand=brand, sort=sort,
                               sorts=SORTS, page=page, pages=pages, cat=cat, brands=brands)

    @app.route("/search")
    def search():
        return listing()

    @app.route("/k/<slug>")
    def category(slug):
        return listing(slug)

    @app.route("/suggest")
    def suggest():
        q = request.args.get("q", "").strip()[:80]
        if len(q) < 2:
            return {"queries": [], "products": []}
        rows, _ = query_products(q, sort="stores")
        queries, seen = [], set()
        for r in rows:
            # telefonlarda oxirgi bo'lak xotira hajmi ("8/256GB"), qolganlarda nomning o'zi
            name = r["title"].rsplit(" ", 1)[0] if r["cat_slug"] == "smartfonlar" else r["title"][:60]
            if name not in seen:
                seen.add(name)
                queries.append({"text": name, "url": url_for("search", q=name)})
            if len(queries) == 4:
                break
        products = [
            {"title": r["title"], "price": pricing.fmt_som(r["min_price"]), "stores": r["n_offers"],
             "url": url_for("product", product_id=r["id"])}
            for r in rows[:6]
        ]
        return {"queries": queries, "products": products}

    @app.route("/p/<int:product_id>")
    def product(product_id):
        conn = get_db()
        p = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if p is None:
            abort(404)
        offers = conn.execute(
            "SELECT o.id, o.title, o.price, o.in_stock, o.updated_at, s.name AS store_name "
            "FROM offers o JOIN stores s ON s.id = o.store_id "
            "WHERE o.product_id = ? ORDER BY o.in_stock DESC, o.price ASC", (product_id,)
        ).fetchall()
        in_stock = [o for o in offers if o["in_stock"]]
        best = in_stock[0] if in_stock else None
        savings = (in_stock[-1]["price"] - best["price"]) if len(in_stock) > 1 else 0

        hist = conn.execute(
            "SELECT h.offer_id, h.price, h.ts FROM price_history h "
            "JOIN offers o ON o.id = h.offer_id WHERE o.product_id = ?", (product_id,)
        ).fetchall()
        series = pricing.daily_min_series([(r["offer_id"], r["price"], r["ts"]) for r in hist])
        chart = Markup(pricing.sparkline_svg(series))
        price_lo = min((v for _, v in series), default=None)
        price_hi = max((v for _, v in series), default=None)

        related = conn.execute(
            LIST_SQL.format(where="WHERE p.brand = ? AND p.id != ? AND p.category_id IS ?",
                            order="n_offers DESC, min_price ASC"),
            (p["brand"], product_id, p["category_id"]),
        ).fetchall()[:4]
        cat = conn.execute("SELECT slug, name FROM categories WHERE id = ?", (p["category_id"],)).fetchone()
        return render_template("product.html", p=p, cat=cat, offers=offers, best=best, savings=savings,
                               chart=chart, price_lo=price_lo, price_hi=price_hi, related=related)

    @app.route("/go/<int:offer_id>")
    def go(offer_id):
        conn = get_db()
        o = conn.execute("SELECT id, url FROM offers WHERE id = ?", (offer_id,)).fetchone()
        if o is None:
            abort(404)
        u = urlparse(o["url"])
        if u.scheme not in ("http", "https") or not u.netloc:
            abort(404)
        conn.execute("INSERT INTO clicks (offer_id) VALUES (?)", (offer_id,))
        conn.commit()
        return redirect(o["url"], code=302)

    @app.route("/healthz")
    def healthz():
        return {"ok": True}

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("404.html"), 404

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
