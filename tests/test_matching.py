import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import matching


@pytest.mark.parametrize("a,b", [
    ("Samsung Galaxy A55 5G 8/256GB Black", "Смартфон Samsung A55 5G 8GB 256GB (чёрный)"),
    ("Apple iPhone 15 Pro Max 256GB Natural Titanium", "iPhone 15 Pro Max 256 GB"),
    ("Xiaomi Redmi Note 13 Pro 8/256GB Global", "Redmi Note 13 Pro 8GB RAM 256GB"),
    ("Poco X6 Pro 12/512GB", "Xiaomi Poco X6 Pro 12GB/512GB"),
    ("Honor 90 Lite 8+256GB", "Смартфон Honor 90 Lite 8GB 256GB"),
])
def test_same_phone_same_key(a, b):
    assert matching.parse_title(a).key == matching.parse_title(b).key


@pytest.mark.parametrize("a,b", [
    ("Samsung Galaxy A55 5G 8/256GB", "Samsung Galaxy A55 5G 8/128GB"),       # xotira farqi
    ("Apple iPhone 15 128GB", "Apple iPhone 15 Pro 128GB"),                    # model farqi
    ("Xiaomi Redmi Note 13 8/256GB", "Xiaomi Redmi Note 13 Pro 8/256GB"),
    ("Samsung Galaxy A55 5G 8/256GB", "Samsung Galaxy A35 5G 8/256GB"),
])
def test_different_phone_different_key(a, b):
    assert matching.parse_title(a).key != matching.parse_title(b).key


def test_memory_parsing():
    p = matching.parse_title("Samsung Galaxy S24 Ultra 12/1TB")
    assert (p.ram_gb, p.storage_gb) == (12, 1024)
    p = matching.parse_title("iPhone 15 Pro Max 256GB")
    assert (p.ram_gb, p.storage_gb) == (0, 256)


def test_accessories_rejected():
    assert not matching.looks_like_phone("Чехол для iPhone 15 Pro")
    assert not matching.looks_like_phone("Samsung Galaxy Watch 6 44mm")
    assert not matching.looks_like_phone("Apple AirPods Pro 2")
    assert not matching.looks_like_phone("Samsung Galaxy A55 5G")  # xotira hajmi yo'q
    assert matching.looks_like_phone("Samsung Galaxy A55 5G 8/256GB")


def test_unknown_brand_returns_none():
    assert matching.parse_title("Noma'lum brend 8/256GB") is None


def test_display_title():
    p = matching.parse_title("Смартфон Samsung A55 5G 8GB 256GB (чёрный)")
    assert matching.display_title(p) == "Samsung Galaxy A55 5G 8/256GB"
    p = matching.parse_title("iphone 15 pro max 256gb")
    assert matching.display_title(p) == "iPhone 15 Pro Max 256GB"


@pytest.mark.parametrize("a,b", [
    ("Honor 400 Pro 12/512GB Midnight Black", "Honor 400 Pro 12/512GB Lunar Grey"),
    ("Infinix HOT 50i 4/256GB Sleek Black", "Infinix Hot 50i 4/256GB Blue"),
    ("Xiaomi 15 12/512GB Liquid Silver", "Xiaomi 15 12/512GB Black"),
    ("Смартфон Huawei nova 15 Max 8/256GB Lake Cyan", "Huawei nova 15 Max 8/256GB Black"),
    ("Xiaomi Redmi Note 15 Pro 5G 8/256GB Titanium Color", "Xiaomi Redmi Note 15 Pro 5G 8/256GB Black"),
])
def test_unknown_colors_after_memory_are_ignored(a, b):
    assert matching.parse_title(a).key == matching.parse_title(b).key


def test_5g_variant_is_a_different_phone():
    a = matching.parse_title("Xiaomi Redmi Note 15 Pro 8/256GB Black")
    b = matching.parse_title("Xiaomi Redmi Note 15 Pro 5G 8/256GB Black")
    assert a.key != b.key


def test_display_keeps_lowercase_i_e_suffix():
    assert matching.display_title(matching.parse_title("Infinix HOT 50i 4/256GB Sleek Black")) == "Infinix Hot 50i 4/256GB"
    assert matching.display_title(matching.parse_title("Honor X7e 6/256GB Blue")) == "Honor X7e 6/256GB"
    assert matching.display_title(matching.parse_title("Huawei nova 14i 8/128GB Blue")) == "Huawei Nova 14i 8/128GB"
    assert matching.display_title(matching.parse_title("Xiaomi Redmi 13C 4/128GB")) == "Xiaomi Redmi 13C 4/128GB"
