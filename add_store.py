"""config.json ga yangi do'kon qo'shadi.

  python add_store.py asaxiy "Asaxiy" https://asaxiy.uz --feed https://asaxiy.uz/feed.xml
  python add_store.py olcha "Olcha" https://olcha.uz --feed https://olcha.uz/yml --default-category kichik-maishiy-texnika
"""
import argparse
import json
import re
import sys


def add_store(path, slug, name, url, feed, default_category=None):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,30}", slug):
        raise ValueError("slug faqat kichik lotin harf, raqam va tire bo'lishi kerak (masalan: asaxiy)")
    if not feed.startswith(("http://", "https://")):
        raise ValueError("feed havolasi http(s) bilan boshlanishi kerak")
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        cfg = {"stores": []}
    if any(s["slug"] == slug for s in cfg["stores"]):
        raise ValueError(f"'{slug}' allaqachon qo'shilgan")
    store = {"slug": slug, "name": name, "url": url, "type": "feed", "feed_url": feed}
    if default_category:
        store["default_category"] = default_category
    cfg["stores"].append(store)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return store


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("name")
    ap.add_argument("url")
    ap.add_argument("--feed", required=True)
    ap.add_argument("--default-category")
    ap.add_argument("--config", default="config.json")
    a = ap.parse_args(argv)
    try:
        add_store(a.config, a.slug, a.name, a.url, a.feed, a.default_category)
    except ValueError as exc:
        print("Xato:", exc)
        return 1
    print(f"'{a.name}' qo'shildi. Avval tekshiring:  python validate_feed.py {a.feed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
