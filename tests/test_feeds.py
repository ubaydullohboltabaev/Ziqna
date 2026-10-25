import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import add_store
import db
import feeds
import ingest
import run_scrape
import validate_feed

XML = """<?xml version="1.0" encoding="UTF-8"?>
<yml_catalog><shop><categories>
  <category id="1">Maishiy texnika</category><category id="2" parentId="1">Muzlatgichlar</category>
  <category id="3">Aksessuarlar</category></categories><offers>
 <offer id="1" available="true"><url>https://s.uz/1</url><price>7900000</price><currencyId>UZS</currencyId>
   <categoryId>2</categoryId><vendor>Samsung</vendor><vendorCode>RB37J5000SA</vendorCode>
   <barcode>4006381333931</barcode><name>Samsung Twin Cooling 367L</name><picture>https://s.uz/1.jpg</picture></offer>
 <offer id="2" available="false"><url>https://s.uz/2</url><price>150000</price><categoryId>3</categoryId>
   <name>Чехол для телефона</name></offer>
 <offer id="3"><url>https://s.uz/3</url><price>4500000</price><currencyId>USD</currencyId>
   <name>Смартфон Samsung Galaxy A55 8/256GB</name></offer>
</offers></shop></yml_catalog>""".encode()


def test_parse_yml_fields_and_category_path():
    items = feeds.parse_yml(XML)
    assert len(items) == 3
    a = items[0]
    assert a["vendor"] == "Samsung" and a["mpn"] == "RB37J5000SA" and a["gtin"] == ["4006381333931"]
    assert a["category_name"] == "Maishiy texnika > Muzlatgichlar"
    assert items[1]["in_stock"] is False


def test_audit_reports_problems():
    r = feeds.audit(feeds.parse_yml(XML), {"category_map": {"muzlatgichlar": "muzlatgichlar"}})
    assert r["total"] == 3 and r["wrong_currency"] == 1 and r["with_gtin"] == 1
    assert any("so'mda emas" in p for p in r["problems"])
    assert "muzlatgichlar" in r["categories"]
    empty = feeds.audit([])
    assert empty["problems"]


def test_validate_feed_cli(tmp_path, capsys):
    f = tmp_path / "feed.xml"
    f.write_bytes(XML)
    code = validate_feed.main([str(f)])
    out = capsys.readouterr().out
    assert code == 1 and "Jami tovar: 3" in out
    assert validate_feed.main([str(tmp_path / "yoq.xml")]) == 2


def test_add_store(tmp_path):
    p = str(tmp_path / "c.json")
    add_store.add_store(p, "asaxiy", "Asaxiy", "https://asaxiy.uz", "https://asaxiy.uz/f.xml")
    assert json.load(open(p, encoding="utf-8"))["stores"][0]["type"] == "feed"
    for bad in [("asaxiy", "https://x/f"), ("Bad Slug", "https://x/f"), ("ok-1", "ftp://x")]:
        with pytest.raises(ValueError):
            add_store.add_store(p, bad[0], "N", "https://x", bad[1])


def test_sync_store_stale_and_guard(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_db(conn)
    store = {"slug": "s", "name": "S", "default_category": "kichik-maishiy-texnika"}

    def item(i, price=100_000):
        return {"title": f"Blender Redmond RBM-M{1000 + i}", "url": f"https://s.uz/{i}", "price": price}

    r = run_scrape.sync_store(conn, store, [item(i) for i in range(10)])
    assert r["stats"]["new"] == 10 and r["stale"] == 0

    # keyingi sinxronlashda 2 ta tovar yo'q: ular sotuvdan chiqadi
    conn.execute("UPDATE offers SET updated_at = datetime('now', '-1 hour')")
    conn.commit()
    r = run_scrape.sync_store(conn, store, [item(i) for i in range(8)])
    assert r["stale"] == 2
    assert conn.execute("SELECT COUNT(*) FROM offers WHERE in_stock = 1").fetchone()[0] == 8

    # feed keskin kichraysa (8 -> 2), hech narsa o'chirilmaydi
    conn.execute("UPDATE offers SET updated_at = datetime('now', '-1 hour')")
    conn.commit()
    r = run_scrape.sync_store(conn, store, [item(0), item(1)])
    assert r["guarded"] and r["stale"] == 0
    assert conn.execute("SELECT COUNT(*) FROM offers WHERE in_stock = 1").fetchone()[0] == 8
    assert conn.execute("SELECT status FROM stores").fetchone()[0] == "warning"


def test_fetch_items_sections_tag_category_and_survive_errors(monkeypatch):
    import scrapers

    def fake(cfg):
        if "bad" in cfg["list_url"]:
            raise PermissionError("robots")
        return [{"title": "Muzlatgich X", "url": "https://s.uz/1", "price": 1}]

    monkeypatch.setattr(scrapers, "scrape_jsonld", fake)
    store = {"slug": "s", "type": "jsonld", "sections": [
        {"list_url": "https://s.uz/katalog/ok/?page={page}", "category": "muzlatgichlar"},
        {"list_url": "https://s.uz/katalog/bad/?page={page}", "category": "televizorlar"},
        {"list_url": "https://s.uz/katalog/free/?page={page}"}]}
    items = run_scrape.fetch_items(store)
    assert [i.get("category") for i in items] == ["muzlatgichlar", None]
    store["sections"] = store["sections"][1:2]
    with pytest.raises(RuntimeError):
        run_scrape.fetch_items(store)


def test_fallback_category_prefers_title_classification(tmp_path):
    conn = db.connect(str(tmp_path / "f.db"))
    db.init_db(conn)
    sid = db.get_or_create_store(conn, "s", "S")
    items = [
        {"title": "Mikroto`lqinli pech Samsung ME83ARW", "url": "https://s.uz/1", "price": 1_600_000,
         "fallback_category": "kichik-maishiy-texnika"},
        {"title": "Vitek VT-1234 Premium", "url": "https://s.uz/2", "price": 500_000,
         "fallback_category": "kichik-maishiy-texnika"},
        {"title": "Lavazza maydalangan qahvasi 250 g", "url": "https://s.uz/3", "price": 119_000,
         "fallback_category": "kichik-maishiy-texnika"},
    ]
    stats = ingest.process_items(conn, sid, items)
    cats = {r["title"]: r["slug"] for r in conn.execute(
        "SELECT p.title, c.slug FROM products p JOIN categories c ON c.id = p.category_id")}
    assert any(v == "mikrotolqinli-pechlar" for v in cats.values())
    assert any(v == "kichik-maishiy-texnika" for v in cats.values())
    assert stats["skipped:accessory"] == 1
