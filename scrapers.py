"""Do'konlardan narx yig'ish: (1) YML/XML feed, (2) sozlanadigan HTML scraper.

Tavsiya: avval do'konlar bilan hamkorlik qilib feed (YML) oling. HTML scraping faqat
saytning robots.txt va foydalanish shartlari ruxsat bersa ishlating.
"""
import json
import time
import urllib.robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from defusedxml import ElementTree as ET

import brand

USER_AGENT = f"{brand.NAME}Bot/0.1 (+mailto:{brand.CONTACT})"  # kontakt brand.py da
TIMEOUT = 20
REQUEST_DELAY = 2.0  # soniya; serverni ortiqcha yuklamaslik uchun


# ---------- YML feed ----------

def parse_yml(xml_bytes):
    """YML feed (batafsil: feeds.py). Eski nom saqlangan."""
    import feeds
    return feeds.parse_yml(xml_bytes)


MAX_FEED_BYTES = 150 * 1024 * 1024


def fetch_feed_bytes(feed_url):
    """Feed baytlarini yuklaydi (hajm chegarasi bilan)."""
    with requests.get(feed_url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, stream=True) as resp:
        resp.raise_for_status()
        buf, size = [], 0
        for chunk in resp.iter_content(1024 * 256):
            size += len(chunk)
            if size > MAX_FEED_BYTES:
                raise ValueError("Feed juda katta (150 MB dan oshdi)")
            buf.append(chunk)
    return b"".join(buf)


def fetch_feed(feed_url):
    return parse_yml(fetch_feed_bytes(feed_url))


# ---------- HTML scraper ----------

def _robots_ok(url):
    p = urlparse(url)
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"{p.scheme}://{p.netloc}/robots.txt")
    try:
        rp.read()
    except Exception:
        return False  # robots.txt o'qilmasa, ehtiyot uchun ruxsat berilmagan deb hisoblaymiz
    return rp.can_fetch(USER_AGENT, url)


def parse_price(text):
    """'12 345 000 so'm' -> 12345000"""
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else None


def parse_listing_html(html, base_url, sel):
    """sel: {"item","title","price","link","image"(ixtiyoriy)} — CSS selektorlar."""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for node in soup.select(sel["item"]):
        t = node.select_one(sel["title"])
        p = node.select_one(sel["price"])
        a = node.select_one(sel["link"])
        if not (t and p and a and a.get("href")):
            continue
        price = parse_price(p.get_text(" ", strip=True))
        if price is None:
            continue
        img = None
        if sel.get("image"):
            im = node.select_one(sel["image"])
            if im is not None:
                img = urljoin(base_url, im.get("src") or im.get("data-src") or "") or None
        items.append({
            "title": t.get_text(" ", strip=True),
            "url": urljoin(base_url, a["href"]),
            "price": price,
            "image": img,
            "in_stock": True,
        })
    return items


def parse_jsonld_products(html, base_url=""):
    """Sahifadagi schema.org JSON-LD (ItemList -> Product -> Offer) dan tovarlarni oladi.
    CSS selektorlardan ishonchliroq: sayt dizayni o'zgarsa ham tuzilma saqlanadi."""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text())
        except ValueError:
            continue
        for block in (data if isinstance(data, list) else [data]):
            if not isinstance(block, dict):
                continue
            for el in block.get("itemListElement") or []:
                prod = el.get("item") if isinstance(el, dict) else None
                if not isinstance(prod, dict) or not prod.get("name"):
                    continue
                offer = prod.get("offers") or {}
                if isinstance(offer, list):
                    offer = offer[0] if offer else {}
                price = offer.get("price")
                url = offer.get("url") or prod.get("url")
                if price is None or not url:
                    continue
                image = prod.get("image")
                if isinstance(image, list):
                    image = image[0] if image else None
                items.append({
                    "title": str(prod["name"]).strip(),
                    "url": urljoin(base_url, url),
                    "price": price,
                    "image": image or None,
                    "in_stock": "OutOfStock" not in str(offer.get("availability", "")),
                })
    return items


def scrape_jsonld(cfg, max_pages=None):
    """cfg: {"list_url": "https://.../smartfony/?page={page}", "max_pages": 15}.
    Yangi tovar chiqmay qolsa (yoki sahifa takrorlansa) to'xtaydi."""
    max_pages = max_pages or cfg.get("max_pages", 15)
    results, seen = [], set()
    for page in range(1, max_pages + 1):
        url = cfg["list_url"].format(page=page)
        if not _robots_ok(url):
            raise PermissionError(f"robots.txt bu manzilni taqiqlaydi yoki o'qib bo'lmadi: {url}")
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        resp.raise_for_status()
        fresh = [i for i in parse_jsonld_products(resp.text, url) if i["url"] not in seen]
        if not fresh:
            break
        seen.update(i["url"] for i in fresh)
        results.extend(fresh)
        time.sleep(REQUEST_DELAY)
    return results


def scrape_html(cfg, max_pages=5):
    """cfg: {"list_url": "https://.../smartfonlar?page={page}", "selectors": {...}}"""
    results = []
    for page in range(1, max_pages + 1):
        url = cfg["list_url"].format(page=page)
        if not _robots_ok(url):
            raise PermissionError(f"robots.txt bu manzilni taqiqlaydi yoki o'qib bo'lmadi: {url}")
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        resp.raise_for_status()
        page_items = parse_listing_html(resp.text, url, cfg["selectors"])
        if not page_items:
            break
        results.extend(page_items)
        time.sleep(REQUEST_DELAY)
    return results
