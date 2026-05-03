import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
from motor.motor_asyncio import AsyncIOMotorClient

# Налаштування з середовища
TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL") 
MONGO_URL = os.getenv("MONGO_URL")
PORT = int(os.getenv("PORT", 8080))

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Підключення до основної бази даних
client = AsyncIOMotorClient(MONGO_URL, tlsAllowInvalidCertificates=True)
db = client["fish_cash_final"] 
users_col = db["users"]
market_col = db["market"]

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    u_id = str(message.from_user.id)
    u_name = message.from_user.full_name or "Рибалка"
    
    # Обробка рефералів
    args = message.text.split()
    referrer = args[1] if len(args) > 1 else None

    user = await users_col.find_one({"user_id": u_id})
    if not user:
        await users_col.insert_one({
            "user_id": u_id, "coins": 100, "lang": "uk",
            "name": u_name, "inventory": [], "referrals": 0
        })
        if referrer and referrer != u_id:
            await users_col.update_one({"user_id": referrer}, {"$inc": {"coins": 50, "referrals": 1}})

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎣 Ловити рибу", web_app=WebAppInfo(url=WEBAPP_URL))
    ]])
    
    # Використання HTML для уникнення помилок парсингу через символ '_'
    text = (
        f"Привіт! Негайно лови рибу, поки не почався сезон риболовлі! 🌊🎣\n\n"
        f"Твій ID: <code>{u_id}</code>\n"
        f"Бот: @fishcash_gamebot"
    )
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# --- API МЕТОДИ ---

async def get_user_data(request):
    user_id = request.query.get("user_id")
    user = await users_col.find_one({"user_id": str(user_id)})
    if user: user.pop("_id", None)
    return web.json_response(user if user else {"error": "not_found"})

async def save_user_data(request):
    data = await request.json()
    u_id = str(data.get("user_id"))
    await users_col.update_one({"user_id": u_id}, {"$set": data}, upsert=True)
    return web.json_response({"ok": True})

async def sell_to_system(request):
    data = await request.json()
    u_id, item_id = str(data.get("user_id")), data.get("item_id")
    prices = {"fish_small": 5, "fish_karas": 15, "fish_pike": 120}
    price = prices.get(item_id, 5)
    user = await users_col.find_one({"user_id": u_id})
    inv = user.get("inventory", [])
    for idx, item in enumerate(inv):
        if item["id"] == item_id:
            inv.pop(idx)
            await users_col.update_one({"user_id": u_id}, {"$set": {"inventory": inv}, "$inc": {"coins": price}})
            return web.json_response({"ok": True, "new_balance": user['coins'] + price})
    return web.json_response({"ok": False})

async def list_on_market(request):
    data = await request.json()
    u_id, item_id, price = str(data.get("user_id")), data.get("item_id"), int(data.get("price"))
    user = await users_col.find_one({"user_id": u_id})
    inv = user.get("inventory", [])
    for idx, item in enumerate(inv):
        if item["id"] == item_id:
            inv.pop(idx)
            await users_col.update_one({"user_id": u_id}, {"$set": {"inventory": inv}})
            await market_col.insert_one({"seller_id": u_id, "seller_name": user.get("name"), "item_id": item_id, "price": price})
            return web.json_response({"ok": True})
    return web.json_response({"ok": False})

async def get_market(request):
    cursor = market_col.find({})
    lots = await cursor.to_list(length=100)
    for l in lots: l.pop("_id", None)
    return web.json_response(lots)

async def buy_from_market(request):
    data = await request.json()
    buyer_id, lot = str(data.get("user_id")), data.get("lot")
    buyer = await users_col.find_one({"user_id": buyer_id})
    if buyer["coins"] < lot["price"]: return web.json_response({"ok": False})
    res = await market_col.delete_one({"seller_id": lot["seller_id"], "item_id": lot["item_id"], "price": lot["price"]})
    if res.deleted_count > 0:
        await users_col.update_one({"user_id": buyer_id}, {"$inc": {"coins": -lot["price"]}, "$push": {"inventory": {"id": lot["item_id"]}}})
        await users_col.update_one({"user_id": lot["seller_id"]}, {"$inc": {"coins": lot["price"]}})
        return web.json_response({"ok": True})
    return web.json_response({"ok": False})

app = web.Application()
app.router.add_get('/', lambda r: web.FileResponse('index.html'))
app.router.add_get('/poplavok.png', lambda r: web.FileResponse('poplavok.png'))
app.router.add_get('/api/get_user', get_user_data)
app.router.add_post('/api/save_user', save_user_data)
app.router.add_post('/api/sell_system', sell_to_system)
app.router.add_post('/api/list_item', list_on_market)
app.router.add_get('/api/get_market', get_market)
app.router.add_post('/api/buy_item', buy_from_market)

async def main():
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
