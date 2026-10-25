import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import catalog
import identify
import ingest
import db


@pytest.mark.parametrize("title,slug", [
    ("Muzlatgich Samsung RB37J5000SA/WT", "muzlatgichlar"),
    ("Холодильник LG GC-B459SLCL", "muzlatgichlar"),
    ("Телевизор Samsung UE50AU7100 4K Smart TV", "televizorlar"),
    ("Пылесос Dreame L10", "changyutgichlar"),
    ("Samsung Galaxy Tab S9 8/128GB", "planshetlar"),
    ("Ноутбук Lenovo IdeaPad Slim 3 15IRH8", "noutbuklar"),
    ("Air Fryer Xiaomi Smart 6L", "kichik-maishiy-texnika"),
    ("Apple AirPods Pro 2", "quloqchinlar"),
    ("Apple Watch Series 9 45mm", "soatlar"),
    ("Monitor Samsung 24 inch", "kompyuter-jihozlari"),
    ("Смартфон Apple iPhone 15 128GB", "smartfonlar"),
])
def test_classify(title, slug):
    assert catalog.classify(title) == slug


@pytest.mark.parametrize("title", [
    "Мешок для пылесоса Samsung", "Чехол для iPhone 15 Pro", "Фильтр для холодильника LG",
    "Кронштейн для телевизора 55", "Ремешок для Apple Watch",
])
def test_accessories_are_not_classified(title):
    slug = catalog.classify(title)
    assert slug is None or slug == "soatlar" and "ремешок" not in title.lower()
    with pytest.raises(identify.Skip):
        identify.resolve(title)


def test_short_keyword_needs_exact_word():
    assert catalog.classify("Stolovaya posuda tvorog") is None          # "tv" so'z ichida emas
    assert catalog.classify("Samsung 55 TV") == "televizorlar"


def test_hint_from_store_category_wins():
    assert catalog.classify("Bosch Serie 4 SMS4HVW33E", hint="Посудомоечные машины") == "idish-yuvish-mashinalari"


@pytest.mark.parametrize("a,b", [
    ("Muzlatgich Samsung RB37J5000SA/WT, oq", "Холодильник Samsung RB37J5000SA белый"),
    ("Samsung RB37J5000SA/WT Muzlatgich", "Холодильник Samsung RB37J5000SA/S9"),
    ("Электрочайник Redmond RK-M1201", "Чайник REDMOND RK M1201 серый"),
])
def test_same_model_code_same_key(a, b):
    assert identify.resolve(a).identity.key == identify.resolve(b).identity.key


def test_different_models_different_keys():
    a = identify.resolve("Холодильник Samsung RB37J5000SA").identity.key
    b = identify.resolve("Холодильник Samsung RB33J3000SA").identity.key
    c = identify.resolve("Холодильник LG RB37J5000SA").identity.key
    assert len({a, b, c}) == 3


def test_model_code_ignores_units_and_cpu():
    assert identify.extract_model_code("Ноутбук HP 15-fd0233 Core i5-1235U 16GB 512GB") == "15FD0233"
    assert identify.extract_model_code("Кондиционер 12000BTU 220V") is None
    assert identify.extract_model_code("Монитор 24 inch 144Hz") is None


def test_title_fallback_ignores_category_words_and_language():
    a = identify.resolve("Пылесос Dreame L10 Pro").identity
    b = identify.resolve("Changyutgich Dreame L10 Pro").identity
    assert a.level == "title" and a.key == b.key


def test_gtin_validation():
    assert identify.normalize_gtin("4006381333931") == "4006381333931"
    assert identify.normalize_gtin("4006381333932") is None         # nazorat raqami xato
    assert identify.normalize_gtin("1111111111111") is None         # bir xil raqamlar
    assert identify.normalize_gtin("123") is None


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(str(tmp_path / "t.db"))
    db.init_db(c)
    return c


def _store(c, slug):
    return db.get_or_create_store(c, slug, slug.title())


def test_generic_ingest_merges_across_stores_and_languages(conn):
    a, b = _store(conn, "a"), _store(conn, "b")
    assert ingest.upsert_offer(conn, a, "Muzlatgich Samsung RB37J5000SA/WT", "https://a.uz/1", 7_900_000) == "new"
    assert ingest.upsert_offer(conn, b, "Холодильник Samsung RB37J5000SA белый", "https://b.uz/1", 7_700_000) == "new"
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1
    p = conn.execute("SELECT p.*, c.slug AS cat FROM products p JOIN categories c ON c.id = p.category_id").fetchone()
    assert p["cat"] == "muzlatgichlar" and p["level"] == "model" and p["brand"] == "samsung"


def test_gtin_bridges_different_titles(conn):
    a, b = _store(conn, "a"), _store(conn, "b")
    ingest.upsert_offer(conn, a, "Пылесос Dreame L10 Pro", "https://a.uz/1", 3_000_000, gtin="4006381333931")
    ingest.upsert_offer(conn, b, "Dreame robot vacuum cleaner Lil Pro Plus", "https://b.uz/1", 2_900_000,
                        gtin="4006381333931")
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0] == 2


def test_gtin_of_other_brand_is_ignored(conn):
    a = _store(conn, "a")
    ingest.upsert_offer(conn, a, "Холодильник Samsung RB37J5000SA", "https://a.uz/1", 7_900_000, gtin="4006381333931")
    ingest.upsert_offer(conn, a, "Холодильник LG GC-B459SLCL", "https://a.uz/2", 6_900_000, gtin="4006381333931")
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 2


def test_junk_gtin_used_for_many_products_is_dropped(conn):
    a = _store(conn, "a")
    items = [{"title": f"Холодильник Samsung RB{i}J5000SA", "url": f"https://a.uz/{i}", "price": 7_000_000,
              "gtin": "4006381333931"} for i in range(30, 34)]
    stats = ingest.process_items(conn, a, items)
    assert stats["new"] == 4
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM product_gtins").fetchone()[0] == 0


def test_category_min_price_and_default_category(conn):
    a = _store(conn, "a")
    assert ingest.upsert_offer(conn, a, "Электрочайник Redmond RK-M1201", "https://a.uz/1", 5_000) == "skipped:price_range"
    assert ingest.upsert_offer(conn, a, "Электрочайник Redmond RK-M1201", "https://a.uz/1", 150_000) == "new"
    assert ingest.upsert_offer(conn, a, "Какая-то вещь XY-77", "https://a.uz/2", 150_000) == "skipped:no_category"
    assert ingest.upsert_offer(conn, a, "Какая-то вещь XY-77", "https://a.uz/2", 150_000,
                               category="kichik-maishiy-texnika") == "new"


def test_category_map_from_store_category_name(conn):
    a = _store(conn, "a")
    cfg = {"category_map": {"Стиральные": "kir-yuvish-mashinalari"}}
    items = [{"title": "Beko WRE 6512 BWW", "url": "https://a.uz/1", "price": 3_500_000,
              "category_name": "Бытовая техника / Стиральные машины"}]
    assert ingest.process_items(conn, a, items, cfg)["new"] == 1
    assert conn.execute("SELECT c.slug FROM products p JOIN categories c ON c.id=p.category_id").fetchone()[0] \
        == "kir-yuvish-mashinalari"


def test_mark_stale_hides_unseen_offers(conn):
    a = _store(conn, "a")
    ingest.upsert_offer(conn, a, "Электрочайник Redmond RK-M1201", "https://a.uz/1", 150_000)
    ingest.upsert_offer(conn, a, "Электрочайник Polaris PWK-1753", "https://a.uz/2", 160_000)
    conn.execute("UPDATE offers SET updated_at = '2000-01-01 00:00:00' WHERE title LIKE '%Polaris%'")
    conn.commit()
    started = conn.execute("SELECT datetime('now', '-1 minute')").fetchone()[0]
    assert ingest.mark_stale(conn, a, started) == 1
    assert conn.execute("SELECT in_stock FROM offers WHERE title LIKE '%Polaris%'").fetchone()[0] == 0
    assert conn.execute("SELECT in_stock FROM offers WHERE title LIKE '%Redmond%'").fetchone()[0] == 1


def test_alias_redirects_new_offers_to_merged_product(conn):
    a = _store(conn, "a")
    ingest.upsert_offer(conn, a, "Холодильник Samsung RB37J5000SA", "https://a.uz/1", 7_900_000)
    pid = conn.execute("SELECT id FROM products").fetchone()[0]
    conn.execute("INSERT INTO product_aliases (key, product_id) VALUES ('g|samsung|OLDCODE1', ?)", (pid,))
    conn.commit()
    b = _store(conn, "b")
    ingest.upsert_offer(conn, b, "Холодильник Samsung OLDCODE1", "https://b.uz/1", 7_800_000)
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM offers WHERE product_id = ?", (pid,)).fetchone()[0] == 2


def test_mixed_cyrillic_latin_titles_are_normalized():
    # Texnomart ba'zan birinchi harfni kirillcha yozadi: "Тelevizori", "Мuzlatgichi"
    assert catalog.norm("LG 50QNED70A6A Smart Тelevizori") == "lg 50qned70a6a smart televizori"
    assert catalog.norm("Мuzlatgichi") == "muzlatgichi"
    assert catalog.norm("Хo‘jalik") == "xo'jalik"
    # toza ruscha so'zlar o'zgarmaydi
    assert catalog.norm("Смартфон Samsung") == "смартфон samsung"


def test_mixed_script_title_is_classified():
    res = identify.resolve("Samsung QE50Q60DAUXUZ Smart Тelevizori")
    assert res.category == "televizorlar"
