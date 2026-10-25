import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import app as app_module
import db
import seed_demo


@pytest.fixture()
def client(tmp_path):
    path = str(tmp_path / "t.db")
    conn = db.connect(path)
    seed_demo.seed(conn, reset=True)
    conn.close()
    a = app_module.create_app(path)
    a.config["TESTING"] = True
    return a.test_client(), path


def test_index_and_health(client):
    c, _ = client
    r = c.get("/")
    assert r.status_code == 200
    assert "Ziqna" in r.text and "DEMO" in r.text
    assert c.get("/healthz").json == {"ok": True}


def test_search_matches_across_name_variants(client):
    c, _ = client
    r = c.get("/search?q=a55")
    assert r.status_code == 200 and "Galaxy A55" in r.text
    assert "Galaxy A55" in c.get("/search?q=galaxy+a55").text
    assert "Galaxy A55" in c.get("/search?q=samsung+a55").text
    r = c.get("/search?q=iphone+15+256")
    assert "iPhone 15 Pro Max" in r.text
    r = c.get("/search?q=zzzz")
    assert "Hech narsa topilmadi" in r.text


def test_search_is_safe_against_like_wildcards_and_junk(client):
    c, _ = client
    assert c.get("/search?q=%25").status_code == 200
    assert "Hech narsa topilmadi" in c.get("/search?q=%25").text
    assert c.get("/search?q=a&sort=DROP TABLE&brand=x&page=abc").status_code == 200
    assert c.get("/search?q=%27%3B--").status_code == 200


def test_suggest(client):
    c, _ = client
    d = c.get("/suggest?q=galaxy+a55").json
    assert d["products"] and "Galaxy A55" in d["products"][0]["title"]
    assert d["products"][0]["price"].endswith("so'm") and d["products"][0]["url"].startswith("/p/")
    assert d["queries"][0]["text"] == "Samsung Galaxy A55 5G"   # xotira hajmisiz nom
    assert c.get("/suggest?q=a").json == {"queries": [], "products": []}   # juda qisqa
    assert c.get("/suggest?q=%25").json["products"] == []                  # LIKE belgisi himoyalangan
    assert len(c.get("/suggest?q=sam").json["products"]) <= 6


def test_sorting(client):
    c, _ = client
    cheap = c.get("/search?sort=cheap").text
    exp = c.get("/search?sort=expensive").text
    assert cheap.index("Redmi 13C") < cheap.index("iPhone 15 Pro Max")
    assert exp.index("iPhone 15 Pro Max") < exp.index("Redmi 13C")


def test_product_page(client):
    c, path = client
    conn = db.connect(path)
    pid = conn.execute("SELECT id FROM products WHERE title LIKE '%A55%'").fetchone()["id"]
    r = c.get(f"/p/{pid}")
    assert r.status_code == 200
    assert "Eng arzon narx" in r.text and "Narx tarixi" in r.text and "<polyline" in r.text
    assert c.get("/p/999999").status_code == 404


def test_go_redirects_and_logs_click(client):
    c, path = client
    conn = db.connect(path)
    o = conn.execute("SELECT id, url FROM offers LIMIT 1").fetchone()
    r = c.get(f"/go/{o['id']}")
    assert r.status_code == 302 and r.headers["Location"] == o["url"]
    assert conn.execute("SELECT COUNT(*) FROM clicks").fetchone()[0] == 1
    assert c.get("/go/999999").status_code == 404


def test_go_refuses_non_http_urls(client):
    c, path = client
    conn = db.connect(path)
    conn.execute("UPDATE offers SET url = 'javascript:alert(1)' WHERE id = (SELECT MIN(id) FROM offers)")
    conn.commit()
    oid = conn.execute("SELECT MIN(id) FROM offers").fetchone()[0]
    assert c.get(f"/go/{oid}").status_code == 404


def test_html_is_escaped(client):
    c, path = client
    conn = db.connect(path)
    conn.execute("UPDATE offers SET title = '<script>alert(1)</script>' WHERE id = (SELECT MIN(id) FROM offers)")
    conn.commit()
    pid = conn.execute("SELECT product_id FROM offers WHERE id = (SELECT MIN(id) FROM offers)").fetchone()[0]
    r = c.get(f"/p/{pid}")
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text


def test_category_pages_and_filters(tmp_path):
    import db as _db
    import ingest as _ing
    path = str(tmp_path / "cat.db")
    conn = _db.connect(path)
    _db.init_db(conn)
    a = _db.get_or_create_store(conn, "a", "A do'kon")
    b = _db.get_or_create_store(conn, "b", "B do'kon")
    _ing.upsert_offer(conn, a, "Холодильник Samsung RB37J5000SA", "https://a.uz/1", 7_900_000)
    _ing.upsert_offer(conn, b, "Samsung холодильник RB37J5000SA/WT", "https://b.uz/1", 7_500_000)
    _ing.upsert_offer(conn, a, "Смартфон Samsung Galaxy A55 8/256GB", "https://a.uz/2", 4_500_000)
    conn.close()

    from app import create_app
    c = create_app(path).test_client()

    home = c.get("/").get_data(as_text=True)
    assert "Muzlatgichlar" in home and "Smartfonlar" in home
    r = c.get("/k/muzlatgichlar")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "RB37J5000SA" in html and "Galaxy A55" not in html
    assert "2 ta do'konda" in html                      # ikki do'kon bitta tovarga birlashgan
    assert c.get("/k/yoq-kategoriya").status_code == 404
    assert "Galaxy A55" not in c.get("/search?category=muzlatgichlar").get_data(as_text=True)
    assert c.get("/search?category=xxx").status_code == 200       # noma'lum kategoriya e'tiborsiz
    assert c.get("/search?brand=<script>").status_code == 200
    sg = c.get("/suggest?q=холодильник").get_json()
    assert sg["products"] and "RB37J5000SA" in sg["products"][0]["title"]
    assert "Muzlatgichlar" in c.get("/p/1").get_data(as_text=True)


def test_brand_name_from_one_place(client):
    import html
    import brand
    c, _ = client
    r = c.get("/")
    assert f"{brand.LOGO_MAIN}<span>{brand.LOGO_ACCENT}</span>" in r.text
    assert "arzonini toping" in r.text
    assert "t.me/ziqnauz_bot" in r.text
