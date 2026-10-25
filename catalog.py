"""Kategoriyalar (categories.json) va nom bo'yicha tasniflash."""
import json
import os
import re

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "categories.json")
_cache = {}

DEFAULT_MIN_PRICE = 20_000
MAX_PRICE = 500_000_000

_APOS = str.maketrans({"’": "'", "ʻ": "'", "‘": "'", "`": "'", "ʼ": "'"})


# Ba'zi do'konlar lotin so'zining birinchi harfini kirillcha yozadi ("Тelevizori", "Мuzlatgichi").
# Bunday aralash so'zlarda kirillcha "egizak" harflarni lotinchaga almashtiramiz, toza ruscha so'zlar tegilmaydi.
_HOMOGLYPHS = str.maketrans({"а": "a", "в": "b", "е": "e", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p",
                             "с": "c", "т": "t", "у": "y", "х": "x", "і": "i"})
_HOMOGLYPHS_START = {"т": "t", "м": "m", "с": "c", "к": "k", "р": "p", "х": "x", "а": "a", "е": "e", "о": "o", "в": "v", "н": "n"}
_MIXED = re.compile(r"\w+")
_LAT = re.compile(r"[a-z]")
_CYR = re.compile(r"[а-яёўқғҳ]")


def _fix_mixed(m):
    w = m.group(0)
    if not (_LAT.search(w) and _CYR.search(w)):
        return w
    # birinchi harf ko'pincha tovush bo'yicha almashgan (Т->t, С->c...), qolganlari ko'rinish bo'yicha
    head = _HOMOGLYPHS_START.get(w[0], w[0])
    return head + w[1:].translate(_HOMOGLYPHS)


def norm(text):
    t = (text or "").lower().replace("ё", "е").translate(_APOS)
    t = _MIXED.sub(_fix_mixed, t)
    return re.sub(r"[-_/,;:()\[\]|]+", " ", t)


def _kw_regex(kw):
    words = norm(kw).split()
    parts = []
    for i, w in enumerate(words):
        p = re.escape(w)
        if i == len(words) - 1:
            p += r"\w*" if len(w) > 3 else r"(?!\w)"
        parts.append(p)
    return re.compile(r"(?<!\w)" + r"\s+".join(parts))


def load(path=None):
    path = os.path.abspath(path or os.environ.get("NARXTOP_CATEGORIES") or _PATH)
    if path in _cache:
        return _cache[path]
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)["categories"]
    cats = []
    for i, c in enumerate(raw):
        cats.append({
            "slug": c["slug"], "name": c["name"], "sort": i,
            "matcher": c.get("matcher", "model"),
            "min_price": int(c.get("min_price", DEFAULT_MIN_PRICE)),
            "parent": c.get("parent"),
            "keywords": [_kw_regex(k) for k in c.get("keywords", [])],
            "exclude": [_kw_regex(k) for k in c.get("exclude", [])],
        })
    _cache[path] = cats
    return cats


def by_slug(slug):
    for c in load():
        if c["slug"] == slug:
            return c
    return None


def classify(title, hint=None):
    """Nom (va do'konning o'z kategoriya nomi `hint`) bo'yicha kategoriya slug'i yoki None.
    Do'kon kategoriyasi (hint) ikki baravar og'irlikda. exclude so'zlari nomda bo'lsa, kategoriya o'tkazib yuboriladi."""
    t, h = norm(title), norm(hint)
    best, best_score = None, 0
    for c in load():
        if any(rx.search(t) for rx in c["exclude"]):
            continue
        score = sum(1 for rx in c["keywords"] if rx.search(t))
        if h:
            score += 2 * sum(1 for rx in c["keywords"] if rx.search(h))
        if score > best_score:
            best, best_score = c["slug"], score
    return best


def is_excluded(title, slug):
    c = by_slug(slug)
    t = norm(title)
    return bool(c) and any(rx.search(t) for rx in c["exclude"])


def sync(conn):
    """categories.json ni bazadagi `categories` jadvaliga tenglashtiradi (mavjudlarini yangilaydi)."""
    cats = load()
    for c in cats:
        conn.execute(
            "INSERT INTO categories (slug, name, sort) VALUES (?, ?, ?) "
            "ON CONFLICT(slug) DO UPDATE SET name = excluded.name, sort = excluded.sort",
            (c["slug"], c["name"], c["sort"]),
        )
    for c in cats:
        if c["parent"]:
            conn.execute("UPDATE categories SET parent_id = (SELECT id FROM categories WHERE slug = ?) WHERE slug = ?",
                         (c["parent"], c["slug"]))
    conn.commit()


def category_id(conn, slug):
    row = conn.execute("SELECT id FROM categories WHERE slug = ?", (slug,)).fetchone()
    return row["id"] if row else None
