import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
from motor.motor_asyncio import AsyncIOMotorClient

# Налаштування (беруться з Railway Variables)
TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL") 
MONGO_URL = os.getenv("MONGO_URL")
PORT = int(os.getenv("PORT", 8080))

# Канал для підписки
CHANNELS = [{"url": "https://t.me/vexoo_hub", "id": "@vexoo_hub"}]
PROMO_CODES = {"hello": 100, "News": 67}

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Підключення до бази (використовуємо стару назву для збереження балансу)
client = AsyncIOMotorClient(MONGO_URL, tlsAllowInvalidCertificates=True)
db = client["fish_cash_test_db"]
users_col = db["users"]

async def check_subscription(user_id):
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel["id"], user_id=user_id)
            if member.status in ["member", "administrator", "creator"]:
                return True
        except Exception:
            return False
    return False

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    if not await check_subscription(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Підписатися", url=CHANNELS[0]["url"])],
            [InlineKeyboardButton(text="✅ Перевірити підписку", callback_data="check_sub")]
        ])
        await message.answer("🌊 Для входу підпишіться на канал:", reply_markup=kb)
        return
    await show_main_menu(message)

@dp.callback_query(lambda c: c.data == "check_sub")
async def process_check_sub(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        await show_main_menu(callback.message)
    else:
        await callback.answer("❌ Ви не підписані!", show_alert=True)

async def show_main_menu(message: types.Message):
    u_id = str(message.chat.id)
    user = await users_col.find_one({"user_id": u_id})
    if not user:
        await users_col.insert_one({
            "user_id": u_id, 
            "coins": 100, 
            "name": message.chat.full_name or "Рибалка",
            "used_promos": []
        })
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎣 Відкрити Озеро", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await bot.send_message(message.chat.id, "Вудка готова! Натискай кнопку нижче:", reply_markup=kb)

# API
async def get_balance(request):
    user_id = request.query.get("user_id")
    user = await users_col.find_one({"user_id": str(user_id)})
    if user: user.pop("_id", None)
    return web.json_response(user if user else {"error": "not_found"})

async def save_balance(request):
    data = await request.json()
    await users_col.update_one({"user_id": str(data.get("user_id"))}, {"$set": {"coins": int(data.get("coins"))}}, upsert=True)
    return web.json_response({"ok": True})

async def use_promo(request):
    data = await request.json()
    u_id, code = str(data.get("user_id")), data.get("code")
    if code in PROMO_CODES:
        user = await users_col.find_one({"user_id": u_id})
        if code in user.get("used_promos", []):
            return web.json_response({"ok": False, "message": "Вже використано!"})
        await users_col.update_one({"user_id": u_id}, {"$inc": {"coins": PROMO_CODES[code]}, "$push": {"used_promos": code}})
        return web.json_response({"ok": True, "bonus": PROMO_CODES[code]})
    return web.json_response({"ok": False, "message": "Невірний код!"})

async def handle_index(request): return web.FileResponse('index.html')
async def handle_poplavok(request): return web.FileResponse('poplavok.png')

app = web.Application()
app.router.add_get('/', handle_index)
app.router.add_get('/poplavok.png', handle_poplavok)
app.router.add_get('/api/get_balance', get_balance)
app.router.add_post('/api/save_balance', save_balance)
app.router.add_post('/api/use_promo', use_promo)

async def main():
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
