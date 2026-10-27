"""Loyiha nomi va aloqa ma'lumotlari: shu yerda bir marta o'zgartirilsa, sayt, bot va scraper hammasi yangilanadi."""
import os

NAME = os.environ.get("BRAND_NAME", "Ziqna")
# Logotipda nomning ikkinchi qismi rangli chiqadi: Ziq + na
LOGO_MAIN, LOGO_ACCENT = NAME[:3], NAME[3:]
SLOGAN = "Ziqna bo'ling, arzonini toping"
TAGLINE = "narxlarni taqqoslang"

# Do'konlar botimizni taniy olishi uchun o'z e-mail yoki Telegram manzilingizni yozing.
CONTACT = os.environ.get("BRAND_CONTACT", "ubaydullohboltabaev@gmail.com")

# Telegram bot manzili (@BotFather'da band qilingan)
BOT_USERNAME = os.environ.get("BRAND_BOT", "ziqnauz_bot")
BOT_URL = f"https://t.me/{BOT_USERNAME}"
