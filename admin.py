"""Katalogni boshqarish.

  python admin.py stats                       kategoriyalar bo'yicha statistika
  python admin.py stores                      do'konlar va oxirgi yangilanish
  python admin.py duplicates [kategoriya]     takroriy bo'lishi mumkin tovarlar
  python admin.py merge <ID_qo'shiladigan> <ID_asosiy>   ikki tovarni birlashtirish
"""
import sys

import admin_tools
import db


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    conn = db.connect()
    db.init_db(conn)
    cmd = argv[0]

    if cmd == "stats":
        print(f"{'Kategoriya':32} {'Tovar':>7} {'2+ do`kon':>10} {'Zaif*':>7} {'Taklif':>8}")
        for r in admin_tools.stats(conn):
            print(f"{r['category']:32} {r['products']:>7} {r['compared']:>10} {r['weak']:>7} {r['offers']:>8}")
        print("* Zaif: faqat nom bo'yicha aniqlangan (model kodi topilmagan), duplicates bilan tekshiring")
    elif cmd == "stores":
        for r in conn.execute("SELECT s.slug, s.name, s.status, s.last_sync, s.last_count, "
                              "(SELECT COUNT(*) FROM offers o WHERE o.store_id = s.id AND o.in_stock = 1) AS live "
                              "FROM stores s ORDER BY s.name"):
            print(f"{r['slug']:18} {r['status']:8} oxirgi: {r['last_sync'] or '-':20} "
                  f"feed: {r['last_count'] if r['last_count'] is not None else '-':>6}  sotuvda: {r['live']}")
    elif cmd == "duplicates":
        pairs = admin_tools.find_duplicates(conn, argv[1] if len(argv) > 1 else None)
        if not pairs:
            print("Takroriy tovar topilmadi.")
        for a, ta, b, tb, sim in pairs[:50]:
            print(f"[{sim}]  #{a} {ta}\n        #{b} {tb}\n        birlashtirish: python admin.py merge {b} {a}\n")
    elif cmd == "merge" and len(argv) == 3:
        try:
            admin_tools.merge_products(conn, int(argv[1]), int(argv[2]))
        except (ValueError, TypeError) as exc:
            print("Xato:", exc)
            return 1
        print(f"#{argv[1]} tovar #{argv[2]} ga qo'shildi.")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
