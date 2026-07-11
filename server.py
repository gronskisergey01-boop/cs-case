from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from case_engine import open_case
from models import CASES, SKINS, UPGRADE_COST, UPGRADE_REQUIRED, RARITY_ORDER
from payment import create_payment_order, verify_payment
from steam_bot import steam_bot
from config import MIN_WITHDRAW
import hashlib
import uuid
import json
import os
import random
import asyncio

app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

USERS_FILE = "users.json"
WITHDRAW_FILE = "withdrawals.json"

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                content = f.read()
                if content.strip():
                    return json.loads(content)
        except: pass
    return {}

def save_users(u):
    with open(USERS_FILE, "w") as f:
        f.write(json.dumps(u, ensure_ascii=False, indent=2))

def load_withdrawals():
    if os.path.exists(WITHDRAW_FILE):
        try:
            with open(WITHDRAW_FILE, "r") as f:
                return json.load(f)
        except: pass
    return []

def save_withdrawals(w):
    with open(WITHDRAW_FILE, "w") as f:
        json.dump(w, f, ensure_ascii=False, indent=2)

users = load_users()
withdrawals = load_withdrawals()

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def get_user_by_username(u):
    for uid, data in users.items():
        if data.get("username") == u:
            return uid, data
    return None, None

def init_user_stats():
    return {
        "total_opened": 0,
        "total_spent": 0,
        "total_earned": 0,
        "most_expensive": None,
        "best_drop": None
    }

# ========== API ==========

@app.get("/api/cases")
def get_cases():
    cases_list = []
    for case_id, case_data in CASES.items():
        cases_list.append({
            "id": case_id,
            "name": case_data["name"],
            "image": case_data["image"],
            "price": case_data["price"],
            "type": case_data.get("type", "weapon"),
        })
    return {"cases": cases_list}

@app.get("/api/case_items")
def case_items(case_id: str):
    if case_id not in CASES:
        raise HTTPException(400, "Кейс не найден")
    case = CASES[case_id]
    items = []
    for item in case["items"]:
        skin = SKINS.get(item["skin"], {})
        items.append({
            "name": item["skin"],
            "chance": item["chance"],
            "price": skin.get("price", 0),
            "color": skin.get("color", "#888"),
            "rarity": skin.get("rarity", "common"),
            "image": skin.get("image", "/static/skins/default.png"),
        })
    rarity_order = {"gold": 0, "red": 1, "pink": 2, "blue": 3}
    items.sort(key=lambda x: rarity_order.get(x["rarity"], 4))
    return items

@app.post("/api/register")
def register(username: str, password: str):
    if get_user_by_username(username)[0]:
        raise HTTPException(400, "Пользователь уже существует")
    if len(username) < 3 or len(password) < 4:
        raise HTTPException(400, "Ник ≥3, пароль ≥4")
    uid = str(uuid.uuid4())[:8]
    users[uid] = {
        "username": username,
        "password": hash_password(password),
        "balance": 0,  # Начинают с 0
        "inventory": [],
        "stats": init_user_stats(),
        "trade_url": "",  # Steam trade URL
        "steam_id": ""
    }
    save_users(users)
    return {"user_id": uid, "username": username, "balance": 0, "stats": users[uid]["stats"]}

@app.post("/api/login")
def login(username: str, password: str):
    uid, data = get_user_by_username(username)
    if not data or data["password"] != hash_password(password):
        raise HTTPException(400, "Неверный логин или пароль")
    if "stats" not in data: data["stats"] = init_user_stats()
    if "trade_url" not in data: data["trade_url"] = ""
    return {
        "user_id": uid,
        "username": data["username"],
        "balance": data["balance"],
        "stats": data["stats"],
        "trade_url": data.get("trade_url", "")
    }

@app.get("/api/info")
def info(user_id: str):
    if user_id not in users:
        raise HTTPException(404, "Пользователь не найден")
    u = users[user_id]
    if "stats" not in u: u["stats"] = init_user_stats()
    return {
        "username": u["username"],
        "balance": u["balance"],
        "inventory": u["inventory"],
        "stats": u["stats"],
        "trade_url": u.get("trade_url", "")
    }

@app.post("/api/open")
def open_case_endpoint(user_id: str, case_id: str):
    if user_id not in users: raise HTTPException(404, "Пользователь не найден")
    if case_id not in CASES: raise HTTPException(400, "Кейс не найден")
    u = users[user_id]
    case = CASES[case_id]
    if u["balance"] < case["price"]: raise HTTPException(400, f"Недостаточно монет! Нужно {case['price']}💰")
    if "stats" not in u: u["stats"] = init_user_stats()
    
    u["balance"] -= case["price"]
    u["stats"]["total_opened"] += 1
    u["stats"]["total_spent"] += case["price"]
    result = open_case(case)
    u["inventory"].append(result)
    
    if u["stats"]["best_drop"] is None or result["price"] > u["stats"]["best_drop"]["price"]:
        u["stats"]["best_drop"] = {"name": result["name"], "price": result["price"], "rarity": result["rarity"], "color": result["color"], "image": result["image"]}
    
    prices = [(i, item["price"]) for i, item in enumerate(u["inventory"])]
    if prices:
        max_idx, max_price = max(prices, key=lambda x: x[1])
        u["stats"]["most_expensive"] = {"name": u["inventory"][max_idx]["name"], "price": max_price, "rarity": u["inventory"][max_idx]["rarity"], "color": u["inventory"][max_idx]["color"], "image": u["inventory"][max_idx]["image"]}
    
    save_users(users)
    return {"result": result, "balance": u["balance"], "stats": u["stats"]}

@app.post("/api/sell")
def sell(user_id: str, index: int):
    if user_id not in users: raise HTTPException(404, "Пользователь не найден")
    u = users[user_id]
    if index < 0 or index >= len(u["inventory"]): raise HTTPException(400, "Скин не найден")
    if "stats" not in u: u["stats"] = init_user_stats()
    
    sold = u["inventory"].pop(index)
    u["balance"] += sold.get("price", 0)
    u["stats"]["total_earned"] += sold.get("price", 0)
    
    prices = [(i, item["price"]) for i, item in enumerate(u["inventory"])]
    u["stats"]["most_expensive"] = None
    if prices:
        max_idx, max_price = max(prices, key=lambda x: x[1])
        u["stats"]["most_expensive"] = {"name": u["inventory"][max_idx]["name"], "price": max_price, "rarity": u["inventory"][max_idx]["rarity"], "color": u["inventory"][max_idx]["color"], "image": u["inventory"][max_idx]["image"]}
    
    save_users(users)
    return {"sold": sold, "balance": u["balance"], "inventory": u["inventory"], "stats": u["stats"]}

@app.post("/api/upgrade")
def upgrade(user_id: str):
    if user_id not in users: raise HTTPException(404, "Пользователь не найден")
    u = users[user_id]
    if u["balance"] < UPGRADE_COST: raise HTTPException(400, f"Недостаточно монет! Нужно {UPGRADE_COST}💰")
    if "stats" not in u: u["stats"] = init_user_stats()
    
    by_rarity = {"blue": [], "pink": [], "red": [], "gold": []}
    for i, item in enumerate(u["inventory"]):
        r = item["rarity"]
        if r in by_rarity: by_rarity[r].append(i)
    
    target = None
    for r in ["blue", "pink", "red"]:
        if len(by_rarity[r]) >= UPGRADE_REQUIRED: target = r; break
    if not target: raise HTTPException(400, f"Нужно {UPGRADE_REQUIRED} скинов одной редкости")
    
    indices = sorted(by_rarity[target][-UPGRADE_REQUIRED:], reverse=True)
    for idx in indices: u["inventory"].pop(idx)
    
    next_r = {"blue": "pink", "pink": "red", "red": "gold"}[target]
    possible = [(name, data) for name, data in SKINS.items() if data["rarity"] == next_r]
    chosen_name, chosen_data = random.choice(possible)
    new_skin = {"name": chosen_name, "rarity": chosen_data["rarity"], "color": chosen_data["color"], "image": chosen_data["image"], "price": chosen_data["price"], "type": chosen_data.get("type","weapon")}
    
    u["balance"] -= UPGRADE_COST
    u["inventory"].append(new_skin)
    save_users(users)
    return {"new_skin": new_skin, "balance": u["balance"], "inventory": u["inventory"]}

# ========== ПЛАТЕЖИ ==========

@app.post("/api/create_payment")
def create_payment(user_id: str, amount: float):
    """Создаёт ссылку на оплату"""
    if user_id not in users:
        raise HTTPException(404, "Пользователь не найден")
    if amount < 100:
        raise HTTPException(400, "Минимальная сумма пополнения: 100₽")
    
    payment_url = create_payment_order(user_id, amount)
    return {"payment_url": payment_url}

@app.post("/api/payment_callback")
async def payment_callback(request: Request):
    """Обработчик уведомлений от FreeKassa"""
    data = await request.form()
    data_dict = dict(data)
    
    print(f"Payment callback: {data_dict}")
    
    if verify_payment(data_dict):
        order_id = data_dict.get("MERCHANT_ORDER_ID", "")
        user_id = order_id.split("_")[0]
        amount = float(data_dict.get("AMOUNT", 0))
        
        if user_id in users:
            # Конвертация рублей в монеты (1₽ = 10💰)
            coins = int(amount * 10)
            users[user_id]["balance"] += coins
            save_users(users)
            print(f"Платёж зачислен: user={user_id}, +{coins}💰")
        
        return JSONResponse({"result": "success"})
    
    return JSONResponse({"result": "error"}, status_code=400)

# ========== ВЫВОД В STEAM ==========

@app.post("/api/withdraw")
async def withdraw(user_id: str, skin_index: int):
    """Создаёт заявку на вывод скина в Steam"""
    if user_id not in users:
        raise HTTPException(404, "Пользователь не найден")
    
    u = users[user_id]
    trade_url = u.get("trade_url", "")
    
    if not trade_url:
        raise HTTPException(400, "Укажите Trade URL в настройках профиля!")
    
    if skin_index < 0 or skin_index >= len(u["inventory"]):
        raise HTTPException(400, "Скин не найден")
    
    skin = u["inventory"][skin_index]
    
    if skin["price"] < MIN_WITHDRAW:
        raise HTTPException(400, f"Минимальная сумма вывода: {MIN_WITHDRAW}💰")
    
    # Создаём заявку
    withdrawal = {
        "id": str(uuid.uuid4())[:8],
        "user_id": user_id,
        "username": u["username"],
        "skin": skin,
        "trade_url": trade_url,
        "status": "pending",
        "created_at": __import__("datetime").datetime.now().isoformat()
    }
    
    withdrawals.append(withdrawal)
    save_withdrawals(withdrawals)
    
    # Удаляем скин из инвентаря
    u["inventory"].pop(skin_index)
    save_users(users)
    
    print(f"Заявка на вывод: {skin['name']} для {u['username']}")
    
    return {"success": True, "message": f"Заявка на вывод {skin['name']} создана. Ожидайте.", "withdrawal_id": withdrawal["id"]}

@app.get("/api/withdrawals")
def get_withdrawals(user_id: str):
    """Получить историю выводов пользователя"""
    user_withdrawals = [w for w in withdrawals if w["user_id"] == user_id]
    return {"withdrawals": user_withdrawals[-20:]}  # Последние 20

@app.post("/api/update_trade_url")
def update_trade_url(user_id: str, trade_url: str):
    """Обновить Trade URL пользователя"""
    if user_id not in users:
        raise HTTPException(404, "Пользователь не найден")
    users[user_id]["trade_url"] = trade_url
    save_users(users)
    return {"success": True}

# ========== ЗАПУСК STEAM БОТА ==========
@app.on_event("startup")
async def startup():
    # Запускаем Steam бота (если есть данные)
    if STEAM_CONFIG.get("login") and STEAM_CONFIG["login"] != "your_bot_login":
        asyncio.create_task(steam_bot.login())
    print("Сервер запущен")

@app.get("/")
def main():
    return FileResponse("index.html")