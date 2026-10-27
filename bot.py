"""Ziqna Telegram boti: qidiruv, eng arzon narx, "narx tushsa xabar ber".

Token'ni @BotFather dan oling va `bot_token.txt` fayliga (yoki TELEGRAM_BOT_TOKEN o'zgaruvchisiga) yozing.
Boshqa kutubxona kerak emas: faqat `requests`.
"""
import html
import os
import sys
import threading
import time

import requests

import bot_core
import brand
import db
import pricing

POLL_TIMEOUT = 30
ALERT_EVERY = 600            # soniya: narx tushishini tekshirish
SCRAPE_EVERY_HOURS = float(os.environ.get("NARXTOP_SCRAPE_HOURS", "6"))
SITE_URL = os.environ.get("NARXTOP_URL", "").rstrip("/")   # ommaviy sayt manzili (bo'lsa, /go orqali o'tadi)

WELCOME = (
    f"Salom! Men {brand.NAME} botiman. {brand.SLOGAN}!\n\n"
    "Tovar nomini yozing, masalan: <b>iPhone</b>, <b>Redmi Note</b>, <b>Samsung muzlatgich</b> yoki <b>changyutgich</b>. "
    "Men do'konlardagi eng arzon narxni topaman, xohlasangiz narx tushganda xabar beraman.\n\n"
    "/obunalar: kuzatayotgan tovarlaringiz"
)


def e(text):
    return html.escape(str(text), quote=False)


class TelegramError(Exception):
    def __init__(self, code, description):
        super().__init__(f"{code}: {description}")
        self.code = code


class TelegramAPI:
    def __init__(self, token):
        self.base = f"https://api.telegram.org/bot{token}/"

    def call(self, method, **params):
        r = requests.post(self.base + method, json=params, timeout=POLL_TIMEOUT + 10)
        try:
            data = r.json()
        except ValueError:
            raise TelegramError(r.status_code, "javob JSON emas")
        if not data.get("ok"):
            raise TelegramError(data.get("error_code", r.status_code), data.get("description", ""))
        return data["result"]


class Bot:
    def __init__(self, api, conn):
        self.api, self.conn = api, conn

    # ---------- yuborish ----------
    def send(self, chat_id, text, keyboard=None):
        params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        if keyboard:
            params["reply_markup"] = {"inline_keyboard": keyboard}
        return self.api.call("sendMessage", **params)

    def _link(self, offer):
        return f"{SITE_URL}/go/{offer['id']}" if SITE_URL else offer["url"]

    # ---------- ko'rinishlar ----------
    def show_results(self, chat_id, query):
        rows = bot_core.search_products(self.conn, query)
        header = f"«{e(query)}» bo'yicha natijalar. Tovarni tanlang:"
        if not rows:
            rows, used = bot_core.search_similar(self.conn, query)
            if not rows:
                self.send(chat_id, "Hech narsa topilmadi. Boshqa nom bilan urinib ko'ring, masalan: "
                                   "<b>iPhone</b>, <b>Redmi Note</b> yoki <b>televizor</b>.")
                return
            header = (f"«{e(query)}» hozir do'konlarda yo'q. "
                      f"«{e(used)}» bo'yicha o'xshash tovarlar:")
        kb = [[{"text": f"{r['title']} · dan {pricing.fmt_som(r['min_price'])}", "callback_data": f"p:{r['id']}"}]
              for r in rows]
        self.send(chat_id, header, kb)

    def show_product(self, chat_id, product_id):
        p, offers = bot_core.get_product(self.conn, product_id)
        if p is None or not offers:
            self.send(chat_id, "Bu tovar hozir sotuvda yo'q.")
            return
        lines = [f"<b>{e(p['title'])}</b>", ""]
        lines.append(f"Eng arzon: <b>{e(pricing.fmt_som(offers[0]['price']))}</b> ({e(offers[0]['store'])})")
        if len(offers) > 1:
            lines.append("")
            lines += [f"• {e(o['store'])}: {e(pricing.fmt_som(o['price']))}" for o in offers[:6]]
        kb = [[{"text": f"{o['store']} · {pricing.fmt_som(o['price'])}", "url": self._link(o)}] for o in offers[:5]]
        kb.append(self._sub_button(chat_id, product_id))
        self.send(chat_id, "\n".join(lines), kb)

    def _sub_button(self, chat_id, product_id):
        if bot_core.is_subscribed(self.conn, chat_id, product_id):
            return [{"text": "🔕 Kuzatishni bekor qilish", "callback_data": f"unsub:{product_id}"}]
        return [{"text": "🔔 Narx tushsa xabar ber", "callback_data": f"sub:{product_id}"}]

    def show_subscriptions(self, chat_id):
        rows = bot_core.list_subscriptions(self.conn, chat_id)
        if not rows:
            self.send(chat_id, "Hali hech narsani kuzatmayapsiz. Tovarni toping va «🔔 Narx tushsa xabar ber» ni bosing.")
            return
        kb = []
        for r in rows:
            now = pricing.fmt_som(r["now_price"]) if r["now_price"] else "sotuvda yo'q"
            kb.append([{"text": f"{r['title']} · {now}", "callback_data": f"p:{r['id']}"}])
        self.send(chat_id, f"Kuzatilayotgan tovarlar ({len(rows)} ta):", kb)

    # ---------- yangilanishlarni qayta ishlash ----------
    def handle_update(self, upd):
        if "message" in upd:
            self.handle_message(upd["message"])
        elif "callback_query" in upd:
            self.handle_callback(upd["callback_query"])

    def handle_message(self, msg):
        chat = msg.get("chat", {})
        text = (msg.get("text") or "").strip()
        if chat.get("type") != "private" or not text:
            return
        chat_id = chat["id"]
        cmd = text.split()[0].split("@")[0].lower()
        if cmd in ("/start", "/help"):
            self.send(chat_id, WELCOME)
        elif cmd in ("/obunalar", "/subs"):
            self.show_subscriptions(chat_id)
        elif text.startswith("/"):
            self.send(chat_id, "Noma'lum buyruq. Smartfon nomini yozing yoki /help ni bosing.")
        else:
            self.show_results(chat_id, text[:80])

    def handle_callback(self, cb):
        chat_id = cb["message"]["chat"]["id"]
        data = cb.get("data", "")
        answer = ""
        try:
            kind, _, raw = data.partition(":")
            pid = int(raw)
        except ValueError:
            self.api.call("answerCallbackQuery", callback_query_id=cb["id"])
            return
        if kind == "p":
            self.show_product(chat_id, pid)
        elif kind == "sub":
            result = bot_core.subscribe(self.conn, chat_id, pid)
            answer = {
                "ok": "Kuzatuv yoqildi. Narx tushsa xabar beraman.",
                "exists": "Bu tovar allaqachon kuzatuvda.",
                "limit": f"Eng ko'pi bilan {bot_core.MAX_SUBS} ta tovarni kuzatish mumkin.",
                "unavailable": "Bu tovar hozir sotuvda yo'q.",
            }[result]
            self._refresh_button(cb, chat_id, pid)
        elif kind == "unsub":
            bot_core.unsubscribe(self.conn, chat_id, pid)
            answer = "Kuzatuv o'chirildi."
            self._refresh_button(cb, chat_id, pid)
        self.api.call("answerCallbackQuery", callback_query_id=cb["id"], text=answer)

    def _refresh_button(self, cb, chat_id, product_id):
        """Xabardagi oxirgi tugmani (kuzatish/bekor qilish) yangilaydi."""
        markup = (cb["message"].get("reply_markup") or {}).get("inline_keyboard")
        if not markup:
            return
        markup = markup[:-1] + [self._sub_button(chat_id, product_id)]
        try:
            self.api.call("editMessageReplyMarkup", chat_id=chat_id, message_id=cb["message"]["message_id"],
                          reply_markup={"inline_keyboard": markup})
        except TelegramError:
            pass  # xabar o'zgarmagan yoki eskirgan: muhim emas

    # ---------- narx tushishi haqida xabar ----------
    def send_alert(self, chat_id, product_id, title, old, new, store):
        text = (f"📉 <b>Narx tushdi!</b>\n{e(title)}\n\n"
                f"{e(pricing.fmt_som(old))} → <b>{e(pricing.fmt_som(new))}</b> "
                f"(−{e(pricing.fmt_som(old - new))})\nDo'kon: {e(store)}")
        try:
            self.send(chat_id, text, [[{"text": "Ko'rish", "callback_data": f"p:{product_id}"}]])
            time.sleep(0.05)   # Telegram cheklovidan oshib ketmaslik uchun
            return "ok"
        except TelegramError as exc:
            if exc.code in (403, 400):   # foydalanuvchi botni bloklagan yoki chat yo'q
                return "blocked"
            return "error"
        except requests.RequestException:
            return "error"

    def run_alerts(self):
        return bot_core.check_alerts(self.conn, self.send_alert)


def read_token():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        here = os.path.dirname(os.path.abspath(__file__))
        # Windows kengaytmani yashirgani uchun fayl ko'pincha "bot_token.txt.txt" bo'lib qoladi
        for name in ("bot_token.txt", "bot_token.txt.txt"):
            path = os.path.join(here, name)
            if os.path.exists(path):
                token = open(path, encoding="utf-8-sig").read().strip()   # -sig: Notepad BOM'ini olib tashlaydi
                break
    return token


def scrape_loop():
    """Fon oqimi: har bir necha soatda narxlarni yangilaydi (config.json bo'lsa)."""
    import run_scrape
    while True:
        time.sleep(SCRAPE_EVERY_HOURS * 3600)
        try:
            if os.path.exists("config.json"):
                run_scrape.run("config.json")
        except Exception as exc:
            print("Scrape xatosi:", exc)


def main():
    token = read_token()
    if not token:
        sys.exit("Token topilmadi. @BotFather dan token oling va bot_token.txt fayliga yozing (README ga qarang).")
    conn = db.connect()
    db.init_db(conn)
    bot = Bot(TelegramAPI(token), conn)
    me = bot.api.call("getMe")
    print(f"Bot ishga tushdi: @{me['username']}  (to'xtatish: Ctrl+C)")
    if SCRAPE_EVERY_HOURS > 0:
        threading.Thread(target=scrape_loop, daemon=True).start()

    offset, last_alert = None, time.time()
    while True:
        try:
            params = {"timeout": POLL_TIMEOUT, "allowed_updates": ["message", "callback_query"]}
            if offset is not None:
                params["offset"] = offset
            for upd in bot.api.call("getUpdates", **params):
                offset = upd["update_id"] + 1
                try:
                    bot.handle_update(upd)
                except TelegramError as exc:
                    print("Telegram xatosi:", exc)
                except Exception as exc:   # bitta xabar botni to'xtatmasin
                    print("Xato:", repr(exc))
            if time.time() - last_alert >= ALERT_EVERY:
                last_alert = time.time()
                n = bot.run_alerts()
                if n:
                    print(f"{n} ta narx tushishi haqida xabar yuborildi")
        except requests.RequestException as exc:
            print("Tarmoq xatosi, 5 soniyadan so'ng qayta uriniladi:", exc)
            time.sleep(5)
        except TelegramError as exc:
            if exc.code == 401:
                sys.exit("Token noto'g'ri (401). bot_token.txt ni tekshiring.")
            print("Telegram xatosi:", exc)
            time.sleep(5)


if __name__ == "__main__":
    main()
