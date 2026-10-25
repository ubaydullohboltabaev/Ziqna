"""Narx tarixi hisob-kitoblari."""
from datetime import date, datetime, timedelta


def _to_date(ts):
    if isinstance(ts, date) and not isinstance(ts, datetime):
        return ts
    if isinstance(ts, datetime):
        return ts.date()
    return datetime.strptime(ts[:10], "%Y-%m-%d").date()


def daily_min_series(history, days=60, today=None):
    """history: [(offer_id, price, ts), ...]. Har kun uchun barcha do'konlarning
    o'sha kundagi oxirgi ma'lum narxlari ichidan eng arzonini qaytaradi:
    [(date, min_price), ...]. Narx o'zgarmagan do'konlar oldingi qiymat bilan qatnashadi."""
    if not history:
        return []
    today = today or date.today()
    events = {}
    for offer_id, price, ts in sorted(history, key=lambda r: str(r[2])):
        events.setdefault(offer_id, []).append((_to_date(ts), price))

    first_day = min(d for ev in events.values() for d, _ in ev)
    start = max(first_day, today - timedelta(days=days - 1))
    series = []
    day = start
    while day <= today:
        prices = []
        for ev in events.values():
            last = None
            for d, p in ev:
                if d <= day:
                    last = p
                else:
                    break
            if last is not None:
                prices.append(last)
        if prices:
            series.append((day, min(prices)))
        day += timedelta(days=1)
    return series


def sparkline_svg(series, width=560, height=140, pad=14):
    """[(date, price)] dan oddiy SVG chiziqli grafik (HTML qaytaradi, ichida foydalanuvchi matni yo'q)."""
    if len(series) < 2:
        return ""
    prices = [p for _, p in series]
    lo, hi = min(prices), max(prices)
    span = (hi - lo) or 1
    n = len(series)
    pts = []
    for i, (_, p) in enumerate(series):
        x = pad + (width - 2 * pad) * i / (n - 1)
        y = pad + (height - 2 * pad) * (1 - (p - lo) / span)
        pts.append(f"{x:.1f},{y:.1f}")
    poly = " ".join(pts)
    last_x, last_y = pts[-1].split(",")
    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
        f'aria-label="Narx tarixi grafigi" preserveAspectRatio="none">'
        f'<polyline points="{poly}" fill="none" stroke="currentColor" stroke-width="2.5" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{last_x}" cy="{last_y}" r="4" fill="currentColor"/></svg>'
    )


def fmt_som(value):
    return f"{int(value):,}".replace(",", " ") + " so'm"
