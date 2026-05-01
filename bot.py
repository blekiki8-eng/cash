import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiohttp import web
from motor.motor_asyncio import AsyncIOMotorClient

# Налаштування (беруться з Railway)
TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")
MONGO_URL = os.getenv("MONGO_URL")
PORT = int(os.getenv("PORT", 8080))

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Підключення до бази даних
client = AsyncIOMotorClient(MONGO_URL, tlsAllowInvalidCertificates=True)
db = client["fish_cash_game_prod"]
users_col = db["users"]

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    user_id = str(message.from_user.id)
    # Отримуємо ім'я або юзернейм, якщо ім'я порожнє
    full_name = message.from_user.full_name or message.from_user.username or "Рибалка"
    
    # Реферальна логіка (якщо зайшли за посиланням)
    args = message.text.split()
    referrer_id = args[1] if len(args) > 1 else None

    user = await users_col.find_one({"user_id": user_id})
    if not user:
        # Новий гравець: даємо 100 монет
        await users_col.insert_one({
            "user_id": user_id, 
            "coins": 100, 
            "name": full_name
        })
        
        # Бонус рефереру (+50 монет)
        if referrer_id and referrer_id != user_id:
            await users_col.update_one({"user_id": referrer_id}, {"$inc": {"coins": 50}})
            try:
                await bot.send_message(referrer_id, f"💎 Твій друг {full_name} приєднався! Тобі нараховано +50 монет!")
            except: 
                pass

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎣 Грати в Fish Cash", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    
    welcome_text = f"Привіт, {full_name}! 🌊\nГотовий наловити на ламборгіні?"
    
    try:
        photo = FSInputFile("welcome.jpg")
        await message.answer_photo(photo=photo, caption=welcome_text, reply_markup=kb)
    except:
        await message.answer(welcome_text, reply_markup=kb)

# --- API для зв'язку гри з базою ---

async def get_balance(request):
    user_id = request.query.get("user_id")
    user = await users_col.find_one({"user_id": str(user_id)})
    if user:
        user.pop("_id", None)
        return web.json_response(user)
    return web.json_response({"error": "not_found"}, status=404)

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

async def handle_index(request): return web.FileResponse('index.html')
async def handle_poplavok(request): return web.FileResponse('poplavok.png')

app = web.Application()
app.router.add_get('/', handle_index)
app.router.add_get('/poplavok.png', handle_poplavok)
app.router.add_get('/api/get_balance', get_balance)
app.router.add_post('/api/save_balance', save_balance)

async def main():
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
