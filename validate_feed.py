"""Do'kon feedini bazaga yozmasdan tekshiradi va hisobot beradi.

  python validate_feed.py https://dokon.uz/feed.xml
  python validate_feed.py feed.xml              (kompyuterdagi fayl)
  python validate_feed.py feed.xml --default-category smartfonlar
"""
import argparse
import sys

import feeds


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="feed havolasi yoki fayl yo'li")
    ap.add_argument("--default-category", help="tasniflanmaganlar uchun kategoriya (slug)")
    args = ap.parse_args(argv)

    try:
        if args.source.startswith(("http://", "https://")):
            import scrapers
            data = scrapers.fetch_feed_bytes(args.source)
        else:
            with open(args.source, "rb") as f:
                data = f.read()
        items = feeds.parse_yml(data)
    except Exception as exc:
        print(f"Feedni o'qib bo'lmadi: {exc}")
        return 2

    cfg = {"default_category": args.default_category} if args.default_category else {}
    r = feeds.audit(items, cfg)
    print(f"Jami tovar: {r['total']}")
    if r["total"]:
        print(f"Moslashtirildi: {r['matched']} | sotuvda: {r['in_stock']} | rasmli: {r['with_image']} | "
              f"brendli: {r['with_vendor']} | shtrix-kodli: {r['with_gtin']}")
        print("Kategoriyalar:", ", ".join(f"{k} ({v})" for k, v in r["categories"].items()) or "-")
        print("Aniqlik darajasi:", r["levels"])
        if r["unclassified_examples"]:
            print("Kategoriyasi aniqlanmagan misollar:", *r["unclassified_examples"], sep="\n  - ")
    for p in r["problems"]:
        print("XATO:", p)
    for w in r["warnings"]:
        print("Ogohlantirish:", w)
    print("\nNatija:", "MUAMMO BOR" if r["problems"] else "feed yaroqli")
    return 1 if r["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
