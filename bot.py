import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiohttp import web
from motor.motor_asyncio import AsyncIOMotorClient

# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL") 
MONGO_URL = os.getenv("MONGO_URL")
PORT = int(os.getenv("PORT", 8080))

# Канал для обов'язкової підписки
CHANNELS = [{"url": "https://t.me/vexoo_hub", "id": "@vexoo_hub"}]

# Промокоди для старту
PROMO_CODES = {
    "hello": 100,
    "News": 67
}

bot = Bot(token=TOKEN)
dp = Dispatcher()

# MongoDB - Основна база для fishcash_gamebot
client = AsyncIOMotorClient(MONGO_URL, tlsAllowInvalidCertificates=True)
db = client["fish_cash_production"]
users_col = db["users"]

# --- ФУНКЦІЯ ПЕРЕВІРКИ ПІДПИСКИ ---
async def check_subscription(user_id):
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel["id"], user_id=user_id)
            if member.status in ["member", "administrator", "creator"]:
                return True
        except Exception:
            return False
    return False

# --- ОБРОБНИКИ ТЕЛЕГРАМ ---
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    is_subscribed = await check_subscription(user_id)

    if not is_subscribed:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Підписатися на Vexoo Hub", url=CHANNELS[0]["url"])],
            [InlineKeyboardButton(text="✅ Я підписався", callback_data="check_sub")]
        ])
        await message.answer(
            "🌊 **Вітаємо у Fish Cash!**\n\nЩоб отримати доступ до озера та почати заробляти, підпишіться на наш канал:",
            reply_markup=kb
        )
        return

    await show_main_menu(message)

@dp.callback_query(lambda c: c.data == "check_sub")
async def process_check_sub(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.answer("Доступ відкрито! 🎉")
        await callback.message.delete()
        await show_main_menu(callback.message)
    else:
        await callback.answer("Ви ще не підписалися! ❌", show_alert=True)

async def show_main_menu(message: types.Message):
    u_id = str(message.chat.id)
    full_name = message.chat.full_name or "Рибалка"
    
    user = await users_col.find_one({"user_id": u_id})
    if not user:
        # Стартовий баланс для нових гравців - 100 монет
        await users_col.insert_one({
            "user_id": u_id, 
            "coins": 100, 
            "name": full_name,
            "used_promos": []
        })

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎣 Почати риболовлю", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    
    text = f"Привіт, {full_name}! 🌊\nВудка готова, озеро чекає на тебе!"
    
    try:
        photo = FSInputFile("welcome.jpg")
        await bot.send_photo(message.chat.id, photo=photo, caption=text, reply_markup=kb)
    except:
        await bot.send_message(message.chat.id, text, reply_markup=kb)

# --- API ДЛЯ ГРИ ---
async def get_balance(request):
    user_id = request.query.get("user_id")
    user = await users_col.find_one({"user_id": str(user_id)})
    if user: user.pop("_id", None)
    return web.json_response(user if user else {"error": "not_found"})

async def save_balance(request):
    try:
        data = await request.json()
        await users_col.update_one(
            {"user_id": str(data.get("user_id"))}, 
            {"$set": {"coins": int(data.get("coins"))}}, 
            upsert=True
        )
        return web.json_response({"ok": True})
    except:
        return web.json_response({"ok": False}, status=500)

async def use_promo(request):
    try:
        data = await request.json()
        u_id, code = str(data.get("user_id")), data.get("code")
        if code in PROMO_CODES:
            user = await users_col.find_one({"user_id": u_id})
            if code in user.get("used_promos", []):
                return web.json_response({"ok": False, "message": "Вже використано!"})
            
            await users_col.update_one(
                {"user_id": u_id}, 
                {"$inc": {"coins": PROMO_CODES[code]}, "$push": {"used_promos": code}}
            )
            return web.json_response({"ok": True, "bonus": PROMO_CODES[code]})
        return web.json_response({"ok": False, "message": "Невірний код!"})
    except:
        return web.json_response({"ok": False}, status=500)

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
