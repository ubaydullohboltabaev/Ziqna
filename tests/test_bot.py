import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import bot as bot_module
import bot_core
import db
import seed_demo


class FakeAPI:
    def __init__(self):
        self.calls = []
        self.fail_send_with = None

    def call(self, method, **params):
        self.calls.append((method, params))
        if method == "sendMessage" and self.fail_send_with:
            raise bot_module.TelegramError(self.fail_send_with, "boom")
        return {}

    def sent(self):
        return [p for m, p in self.calls if m == "sendMessage"]


@pytest.fixture()
def env(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    seed_demo.seed(conn, reset=True)
    api = FakeAPI()
    return bot_module.Bot(api, conn), api, conn


def msg(text, chat_id=1, chat_type="private"):
    return {"message": {"chat": {"id": chat_id, "type": chat_type}, "text": text}}


def pid(conn, like):
    return conn.execute("SELECT id FROM products WHERE title LIKE ?", (like,)).fetchone()["id"]


def test_start_and_unknown_command(env):
    bot, api, _ = env
    bot.handle_update(msg("/start"))
    assert "Ziqna" in api.sent()[-1]["text"]
    bot.handle_update(msg("/nimadir"))
    assert "Noma'lum" in api.sent()[-1]["text"]


def test_search_returns_buttons_with_prices(env):
    bot, api, _ = env
    bot.handle_update(msg("galaxy a55"))
    s = api.sent()[-1]
    btn = s["reply_markup"]["inline_keyboard"][0][0]
    assert "Galaxy A55" in btn["text"] and "so'm" in btn["text"] and btn["callback_data"].startswith("p:")


def test_search_nothing_and_wildcards(env):
    bot, api, _ = env
    bot.handle_update(msg("zzzz"))
    assert "Hech narsa topilmadi" in api.sent()[-1]["text"]
    bot.handle_update(msg("%"))
    assert "Hech narsa topilmadi" in api.sent()[-1]["text"]


def test_group_chats_are_ignored(env):
    bot, api, _ = env
    bot.handle_update(msg("iphone", chat_type="group"))
    assert api.sent() == []


def test_html_in_product_title_and_store_is_escaped(env):
    bot, api, conn = env
    p = pid(conn, "%A55%")
    conn.execute("UPDATE products SET title = '<i>X</i> A55' WHERE id = ?", (p,))
    conn.execute("UPDATE stores SET name = '<b>Do''kon</b>' WHERE id = (SELECT store_id FROM offers WHERE product_id = ? LIMIT 1)", (p,))
    conn.commit()
    bot.handle_update({"callback_query": {"id": "c", "data": f"p:{p}", "message": {"chat": {"id": 1}, "message_id": 1}}})
    text = api.sent()[-1]["text"]
    assert "<i>X</i>" not in text and "&lt;i&gt;X&lt;/i&gt;" in text
    assert "<b>Do'kon</b>" not in text and "&lt;b&gt;Do'kon&lt;/b&gt;" in text


def test_product_view_and_subscribe_flow(env):
    bot, api, conn = env
    p = pid(conn, "%A55%")
    cb = {"id": "c1", "data": f"p:{p}", "message": {"chat": {"id": 1}, "message_id": 5}}
    bot.handle_update({"callback_query": cb})
    s = api.sent()[-1]
    assert "Eng arzon" in s["text"]
    kb = s["reply_markup"]["inline_keyboard"]
    assert kb[0][0]["url"].startswith("https://") and kb[-1][0]["callback_data"] == f"sub:{p}"

    cb2 = {"id": "c2", "data": f"sub:{p}", "message": {"chat": {"id": 1}, "message_id": 5,
                                                         "reply_markup": {"inline_keyboard": kb}}}
    bot.handle_update({"callback_query": cb2})
    assert bot_core.is_subscribed(conn, 1, p)
    edit = [x for m, x in api.calls if m == "editMessageReplyMarkup"][-1]
    assert edit["reply_markup"]["inline_keyboard"][-1][0]["callback_data"] == f"unsub:{p}"
    assert "yoqildi" in [x for m, x in api.calls if m == "answerCallbackQuery"][-1]["text"]

    bot.handle_update({"callback_query": {"id": "c3", "data": f"unsub:{p}", "message": cb2["message"]}})
    assert not bot_core.is_subscribed(conn, 1, p)


def test_bad_callback_data_does_not_crash(env):
    bot, api, _ = env
    bot.handle_update({"callback_query": {"id": "x", "data": "p:abc", "message": {"chat": {"id": 1}, "message_id": 1}}})
    bot.handle_update({"callback_query": {"id": "y", "data": "zzz", "message": {"chat": {"id": 1}, "message_id": 1}}})


def test_subscription_limit(env):
    _, _, conn = env
    ids = [r[0] for r in conn.execute("SELECT id FROM products")]
    for i in ids[:bot_core.MAX_SUBS]:
        assert bot_core.subscribe(conn, 7, i) in ("ok",)
    conn.execute("INSERT INTO products (key, brand, model, title, search_text) VALUES ('k','x','m','T','t')")
    assert bot_core.subscribe(conn, 7, ids[0]) == "exists"
    assert bot_core.subscribe(conn, 7, 99999) == "unavailable"


def _drop_price(conn, product_id, new_price):
    conn.execute("UPDATE offers SET price = ? WHERE product_id = ?", (new_price, product_id))
    conn.commit()


def test_alert_fires_on_drop_once(env):
    bot, api, conn = env
    p = pid(conn, "%A55%")
    bot_core.subscribe(conn, 1, p)
    base = conn.execute("SELECT baseline FROM subscriptions").fetchone()[0]

    assert bot.run_alerts() == 0                                 # o'zgarish yo'q
    _drop_price(conn, p, int(base * 0.90))
    assert bot.run_alerts() == 1
    text = api.sent()[-1]["text"]
    assert "Narx tushdi" in text and "Galaxy A55" in text
    assert bot.run_alerts() == 0                                 # ikkinchi marta xabar yo'q


def test_small_drop_ignored_and_rise_raises_baseline(env):
    bot, api, conn = env
    p = pid(conn, "%A55%")
    bot_core.subscribe(conn, 1, p)
    base = conn.execute("SELECT baseline FROM subscriptions").fetchone()[0]
    _drop_price(conn, p, int(base * 0.995))                      # 0.5% — kam
    assert bot.run_alerts() == 0
    _drop_price(conn, p, int(base * 1.2))                        # narx oshdi
    assert bot.run_alerts() == 0
    assert conn.execute("SELECT baseline FROM subscriptions").fetchone()[0] == int(base * 1.2)
    _drop_price(conn, p, base)                                   # yana tushdi -> xabar
    assert bot.run_alerts() == 1


def test_blocked_user_subscriptions_removed(env):
    bot, api, conn = env
    p = pid(conn, "%A55%")
    bot_core.subscribe(conn, 1, p)
    base = conn.execute("SELECT baseline FROM subscriptions").fetchone()[0]
    _drop_price(conn, p, int(base * 0.8))
    api.fail_send_with = 403
    assert bot.run_alerts() == 0
    assert conn.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0] == 0


def test_temporary_error_keeps_subscription_and_retries(env):
    bot, api, conn = env
    p = pid(conn, "%A55%")
    bot_core.subscribe(conn, 1, p)
    base = conn.execute("SELECT baseline FROM subscriptions").fetchone()[0]
    _drop_price(conn, p, int(base * 0.8))
    api.fail_send_with = 500
    assert bot.run_alerts() == 0
    assert conn.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0] == 1
    api.fail_send_with = None
    assert bot.run_alerts() == 1


def test_subscriptions_list(env):
    bot, api, conn = env
    bot.handle_update(msg("/obunalar"))
    assert "Hali hech narsani" in api.sent()[-1]["text"]
    bot_core.subscribe(conn, 1, pid(conn, "%A55%"))
    bot.handle_update(msg("/obunalar"))
    assert "1 ta" in api.sent()[-1]["text"]
