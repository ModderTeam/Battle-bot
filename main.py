import re
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.markdown import quote_html
from aiogram.utils import executor
from datetime import datetime
import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)

# ==== Sozlamalar ====
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Get from environment variable
CHANNEL_ID = os.getenv("CHANNEL_ID")  # Get from environment variable
BOOST_LINK = os.getenv("BOOST_LINK")  # Get from environment variable
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))  # Get admin IDs from environment variable
DB = os.getenv("DB")  # Get database name from environment variable

USERNAME_REGEX = re.compile(r'^@[A-Za-z0-9_]{5,}$')

WELCOME_TEXT = """Username Battle:
👋 Salom {name}!

📝 Iltimos, faqat o‘z @usernamengizni yuboring.
📋 Masalan: @mening_username

ℹ️ Username kamida 5 ta belgidan iborat bo‘lishi kerak.
"""

INVALID_FORMAT = """Username Battle:
❗ Noto‘g‘ri username formati!

✅ To‘g‘ri format: @username
📏 Kamida 5 ta belgi
🔤 Faqat harf, raqam va _ belgisi ishlatiladi

📋 Masalan: @user123
"""

NOT_YOUR_USERNAME = """Username Battle:
❌ Bu sizning usernamengiz emas!

💡 Sizning usernamengiz: {real}
ℹ️ Iltimos, faqat o‘z username'ingizni yuboring.
"""

SUCCESS_REPLY = """Username Battle:
✅ Username muvaffaqiyatli ro'yxatga olindi!
📊 Sizning raqamingiz: {number}
📢 Xabar {channel} kanaliga yuborildi.
"""

DEFAULT_CHANNEL_TEMPLATE = """📢 #{num} — Yangi ishtirokchi!

👤 Foydalanuvchi: {username}
⭐ Yulduzlar: {stars}
💬 Reaksiya: {reaction}
🚀 Boost: {boost}
🔗 Boost linki: {boost_link}
"""

# === NEW: Statistics text ===
STATISTICS_REPLY = """Username Battle Statistika:
👥 Umumiy foydalanuvchilar: <b>{total}</b>
🆕 Bugun qo‘shilganlar: <b>{today}</b>
"""

# === DATABASE INIT ===
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            username TEXT UNIQUE,
            created_at TEXT
        );
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS force_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_name TEXT
        );
        """)
        # Default settings
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("battle_status", "on"))
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("template", DEFAULT_CHANNEL_TEMPLATE))
        await db.commit()

async def get_setting(key):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

async def set_setting(key, value):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()

async def register_user(tg_id: int, username: str):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT id FROM users WHERE username = ?", (username,)) as cur:
            row = await cur.fetchone()
            if row:
                return row[0]
        now = datetime.utcnow().isoformat()
        await db.execute("INSERT INTO users (telegram_id, username, created_at) VALUES (?, ?, ?)",
                         (tg_id, username, now))
        await db.commit()
        async with db.execute("SELECT id FROM users WHERE username = ?", (username,)) as cur2:
            row2 = await cur2.fetchone()
            return row2[0] if row2 else None

# === NEW: Statistics functions ===
async def get_statistics():
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total = (await cur.fetchone())[0]
        today_date = datetime.utcnow().date().isoformat()
        async with db.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = ?", (today_date,)) as cur2:
            today = (await cur2.fetchone())[0]
    return total, today

# === Admin modes flags ===
admin_template_mode = {}
admin_force_channel_mode = {}
admin_delete_channel_mode = {}

# === KEYBOARDS ===
def admin_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🚀 Start Battle"), KeyboardButton("⏸ Stop Battle"))
    kb.add(KeyboardButton("📝 Set Template"))
    kb.add(KeyboardButton("📢 Obunalar"))
    kb.add(KeyboardButton("📊 Statistika"))  # Add stats button
    return kb

def subscriptions_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("➕ Kanal qo‘shish"), KeyboardButton("➖ Kanal o‘chirish"))
    kb.add(KeyboardButton("⬅ Orqaga"))
    return kb

# === COMMANDS ===
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        await message.reply("Admin panel:", reply_markup=admin_keyboard())
    else:
        text = WELCOME_TEXT.format(name=quote_html(message.from_user.first_name or "👤"))
        await message.reply(text, parse_mode=ParseMode.HTML)

@dp.message_handler(commands=["stat"])  # Public command
async def user_statistics(message: types.Message):
    total, today = await get_statistics()
    await message.reply(STATISTICS_REPLY.format(total=total, today=today), parse_mode=ParseMode.HTML)

@dp.message_handler(lambda m: m.from_user.id in ADMIN_IDS and m.text == "📊 Statistika")
async def admin_statistics(message: types.Message):
    total, today = await get_statistics()
    await message.reply(STATISTICS_REPLY.format(total=total, today=today), parse_mode=ParseMode.HTML)

@dp.message_handler(lambda m: m.from_user.id in ADMIN_IDS and m.text == "📢 Obunalar")
async def show_subscriptions_menu(message: types.Message):
    await message.reply("📢 Obunalar bo‘limi:", reply_markup=subscriptions_keyboard())

@dp.message_handler(lambda m: m.from_user.id in ADMIN_IDS and m.text == "⬅ Orqaga")
async def back_to_main_menu(message: types.Message):
    admin_force_channel_mode[message.from_user.id] = False
    admin_delete_channel_mode[message.from_user.id] = False
    admin_template_mode[message.from_user.id] = False
    await message.reply("🔙 Asosiy menyu:", reply_markup=admin_keyboard())

@dp.message_handler(lambda m: m.from_user.id in ADMIN_IDS and m.text == "🚀 Start Battle")
async def start_battle(message: types.Message):
    await set_setting("battle_status", "on")
    await message.reply("✅ Battle boshlandi!")

@dp.message_handler(lambda m: m.from_user.id in ADMIN_IDS and m.text == "⏸ Stop Battle")
async def stop_battle(message: types.Message):
    await set_setting("battle_status", "off")
    await message.reply("⏸ Battle to‘xtatildi!")

@dp.message_handler(lambda m: m.from_user.id in ADMIN_IDS and m.text == "📝 Set Template")
async def ask_template(message: types.Message):
    admin_template_mode[message.from_user.id] = True
    admin_force_channel_mode[message.from_user.id] = False
    admin_delete_channel_mode[message.from_user.id] = False
    await message.reply(
        "📝 Yangi kanal xabar shablonini yuboring.\n\n"
        "Parametrlar: {num}, {username}, {stars}, {reaction}, {boost}, {boost_link}\n\n"
        "Masalan:\n📢 #{num} — Yangi isht
