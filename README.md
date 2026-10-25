# Ziqna — narxlarni taqqoslash sayti (prototip)

Cimri/Akakce g'oyasi asosida O'zbekiston uchun yozilgan MVP. Faqat smartfonlar.
Kod noldan yozilgan (Flask + SQLite), hech qaysi sayt kodi yoki dizayni ko'chirilmagan.

## Tez boshlash

```bash
pip install -r requirements.txt
python seed_demo.py --reset     # DEMO ma'lumot (do'konlar va narxlar to'qima!)
python app.py                   # http://127.0.0.1:5000
pytest                          # testlar
```

## Haqiqiy ma'lumot

1. `config.example.json` ni `config.json` ga nusxalang, do'konlarni yozing.
2. `python run_scrape.py` — narxlarni yig'adi (cron bilan har 6 soatda).

Ikki usul bor:
- **feed** (YML/XML) — tavsiya etiladi. Do'kondan feed so'rang (hamkorlik).
- **html** — CSS selektorlar bilan. Selektorlarni har bir sayt uchun o'zingiz topasiz
  (`config.example.json` dagilar namuna, haqiqiy emas). Skript `robots.txt` ni tekshiradi
  va so'rovlar orasida 2 soniya kutadi. Saytning foydalanish shartlariga rioya qiling.
  `scrapers.py` dagi `USER_AGENT` ga o'z kontaktingizni yozing.

## Tuzilma

| Fayl | Vazifasi |
|---|---|
| `matching.py` | Nomni brend/model/RAM/xotira bo'yicha standartlash, bir xil tovarni aniqlash |
| `ingest.py` | Taklifni bazaga yozish, narx tarixi, noto'g'ri ma'lumotni rad etish |
| `scrapers.py` | YML feed va HTML scraper |
| `pricing.py` | Kunlik eng arzon narx seriyasi, grafik |
| `app.py`, `templates/`, `static/` | Sayt |
| `db.py` | SQLite sxema |

## Ma'lum cheklovlar

- **Matching qat'iy**: "A35" va "A35 5G" turli tovar hisoblanadi (noto'g'ri birlashtirishdan ko'ra
  ajratib qo'yish xavfsizroq). Haqiqiy ma'lumot kelgach, `matching.py` ga alias jadvali qo'shish kerak.
- Xotira hajmi ko'rsatilmagan nomlar o'tkazib yuboriladi.
- Rasm va sharhlar, narx ogohlantirishi, Telegram bot, rus tili, reklama/CPC hisobi hali yo'q.
- `/go/<id>` bosishlarni `clicks` jadvaliga yozadi (keyin do'konlarga hisobot uchun).
- Ishlab chiqarishga chiqarishda `gunicorn` va HTTPS ishlating (`python app.py` faqat sinov uchun).

## Telegram bot

1. Telegram'da **@BotFather** ga yozing → `/newbot` → nom va `...bot` bilan tugaydigan manzil bering.
2. U bergan **tokenni** `bot_token.txt` fayliga yozing (faqat token). Tokenni hech kimga bermang.
3. `bot.bat` ni ishga tushiring (yoki `python bot.py`). Bot ishlashi uchun oyna ochiq turishi kerak.

Bot: smartfon nomini yozasiz → natijalar tugmalar bilan → tovarda do'konlar narxi va «🔔 Narx tushsa xabar ber».
Narx kamida 1% tushsa, har 10 daqiqada tekshirib xabar yuboradi. `/obunalar` — kuzatilayotganlar.
Bot har 6 soatda (`NARXTOP_SCRAPE_HOURS`) narxlarni o'zi yangilaydi (`config.json` bo'lsa).
Ommaviy sayt manzili bo'lsa `NARXTOP_URL` o'zgaruvchisiga yozing: do'konga o'tishlar saytingiz orqali hisoblanadi.


## Yangi komandalar (2-bosqich)
| Buyruq | Vazifa |
|---|---|
| `python validate_feed.py <havola yoki fayl>` | Do'kon feedini bazaga yozmasdan tekshiradi |
| `python add_store.py slug "Nom" https://sayt --feed <havola>` | config.json ga do'kon qo'shadi |
| `python run_scrape.py` | Barcha do'konlarni yangilaydi (ko'rinmay qolgan takliflar "sotuvda yo'q" bo'ladi) |
| `python admin.py stats / stores / duplicates / merge` | Katalogni boshqarish |

Kategoriya qo'shish: `categories.json` ga yozing (slug, name, keywords, exclude, min_price). Hujjatlar: `docs/`.

## Nom va kontakt

Loyiha nomi, shiori va kontakt `brand.py` faylida turadi. Nomni yoki kontaktni o'zgartirish uchun faqat shu faylni tahrirlang
(yoki `BRAND_NAME`, `BRAND_CONTACT` muhit o'zgaruvchilarini bering). Baza fayllari (`narxtop*.db`) va `NARXTOP_*`
o'zgaruvchilari eski nomda qoldi, shunda yig'ilgan ma'lumotlar yo'qolmaydi.
