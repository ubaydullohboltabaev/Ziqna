import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import db
import ingest
import pricing
import scrapers


def test_daily_min_carries_forward_last_price():
    # 1-do'kon 10-kuni 100 -> 12-kuni 90; 2-do'kon 10-kuni 95 (keyin o'zgarmaydi)
    hist = [(1, 100, "2026-10-10 10:00:00"), (1, 90, "2026-10-12 10:00:00"), (2, 95, "2026-10-10 12:00:00")]
    s = dict(pricing.daily_min_series(hist, days=10, today=date(2026, 10, 13)))
    assert s[date(2026, 10, 10)] == 95
    assert s[date(2026, 10, 11)] == 95
    assert s[date(2026, 10, 12)] == 90   # 2-do'kon narxi saqlanib qolgan, lekin 90 pastroq
    assert s[date(2026, 10, 13)] == 90


def test_sparkline_needs_two_points():
    assert pricing.sparkline_svg([(date(2026, 1, 1), 5)]) == ""
    assert "<polyline" in pricing.sparkline_svg([(date(2026, 1, 1), 5), (date(2026, 1, 2), 7)])


def test_fmt_som():
    assert pricing.fmt_som(12345000) == "12 345 000 so'm"


def test_ingest_dedup_and_history(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_db(conn)
    s1 = db.get_or_create_store(conn, "a", "A")
    s2 = db.get_or_create_store(conn, "b", "B")

    assert ingest.upsert_offer(conn, s1, "Samsung Galaxy A55 5G 8/256GB", "https://a.uz/x", 4_300_000) == "new"
    assert ingest.upsert_offer(conn, s2, "Смартфон Samsung A55 5G 8GB 256GB", "https://b.uz/y", 4_200_000) == "new"
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0] == 2

    assert ingest.upsert_offer(conn, s1, "Samsung Galaxy A55 5G 8/256GB", "https://a.uz/x", 4_300_000) == "unchanged"
    assert ingest.upsert_offer(conn, s1, "Samsung Galaxy A55 5G 8/256GB", "https://a.uz/x", 4_100_000) == "updated"
    assert conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0] == 3


def test_ingest_rejects_bad_input(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_db(conn)
    s = db.get_or_create_store(conn, "a", "A")
    title = "Samsung Galaxy A55 5G 8/256GB"
    assert ingest.upsert_offer(conn, s, title, "javascript:alert(1)", 4_000_000).startswith("skipped")
    assert ingest.upsert_offer(conn, s, title, "https://a.uz/x", 5_000).startswith("skipped")
    assert ingest.upsert_offer(conn, s, title, "https://a.uz/x", "abc").startswith("skipped")
    assert ingest.upsert_offer(conn, s, "Чехол Samsung Galaxy A55 256GB", "https://a.uz/x", 400_000).startswith("skipped")


def test_parse_yml():
    xml = b"""<?xml version="1.0"?><yml_catalog><shop><offers>
      <offer id="1" available="true"><url>https://s.uz/1</url><price>4300000</price>
        <picture>https://s.uz/1.jpg</picture><name>Samsung Galaxy A55 5G 8/256GB</name></offer>
      <offer id="2" available="false"><url>https://s.uz/2</url><price>9000000</price>
        <vendor>Apple</vendor><model>iPhone 15 128GB</model></offer>
      <offer id="3"><url>https://s.uz/3</url><name>narxsiz</name></offer>
    </offers></shop></yml_catalog>"""
    items = scrapers.parse_yml(xml)
    assert len(items) == 2
    assert items[0]["image"] == "https://s.uz/1.jpg" and items[0]["in_stock"] is True
    assert items[1]["title"] == "Apple iPhone 15 128GB" and items[1]["in_stock"] is False


def test_parse_yml_blocks_xml_bomb():
    import pytest
    bomb = b"""<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><x>&b;</x>"""
    with pytest.raises(Exception):
        scrapers.parse_yml(bomb)


def test_parse_listing_html():
    html = """<div class="c"><a href="/p/1"><span class="t">Honor 90 Lite 8/256GB</span></a>
              <span class="p">2 700 000 so'm</span><img src="/i.jpg"></div>
              <div class="c"><span class="t">Narxsiz</span></div>"""
    sel = {"item": ".c", "title": ".t", "price": ".p", "link": "a", "image": "img"}
    items = scrapers.parse_listing_html(html, "https://shop.uz/list", sel)
    assert len(items) == 1
    assert items[0]["price"] == 2_700_000
    assert items[0]["url"] == "https://shop.uz/p/1"
    assert items[0]["image"] == "https://shop.uz/i.jpg"


JSONLD_PAGE = """<html><head>
<script type="application/ld+json">{"@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"name":"Bosh"}]}</script>
<script type="application/ld+json">[{"@type":"ItemList","itemListElement":[
 {"@type":"ListItem","item":{"@type":"Product","name":"Honor 400 Pro 12/512GB Midnight Black",
  "offers":{"@type":"Offer","availability":"https://schema.org/InStock","price":7824000,"url":"/uz/product/detail/1"},
  "image":"https://img.example/1.webp"}},
 {"@type":"ListItem","item":{"@type":"Product","name":"Honor 400 Pro 12/512GB Lunar Grey",
  "offers":{"@type":"Offer","availability":"https://schema.org/InStock","price":7700000,"url":"/uz/product/detail/2"}}},
 {"@type":"ListItem","item":{"@type":"Product","name":"Honor X7e 6/256GB Blue",
  "offers":{"@type":"Offer","availability":"https://schema.org/OutOfStock","price":2100000,"url":"/uz/product/detail/3"}}},
 {"@type":"ListItem","item":{"@type":"Product","name":"Narxsiz","offers":{"url":"/x"}}}
]}]</script></head><body></body></html>"""


def test_parse_jsonld_products():
    items = scrapers.parse_jsonld_products(JSONLD_PAGE, "https://texnomart.uz/katalog/smartfony/")
    assert len(items) == 3
    assert items[0]["url"] == "https://texnomart.uz/uz/product/detail/1"
    assert items[0]["price"] == 7824000 and items[0]["image"] == "https://img.example/1.webp"
    assert items[2]["in_stock"] is False


def test_parse_jsonld_ignores_broken_json():
    assert scrapers.parse_jsonld_products('<script type="application/ld+json">{oops</script>') == []


def test_cheapest_color_variant_wins_per_store():
    import run_scrape
    items = scrapers.parse_jsonld_products(JSONLD_PAGE, "https://texnomart.uz/")
    out = run_scrape.cheapest_per_phone(items)
    honor400 = [i for i in out if "400 Pro" in i["title"]]
    assert len(honor400) == 1 and honor400[0]["price"] == 7700000     # arzon rang tanlandi
    assert len(out) == 2
