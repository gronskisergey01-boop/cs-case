from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from case_engine import open_case
from models import CASES, SKINS, UPGRADE_COST, UPGRADE_REQUIRED
import hashlib
import uuid
import json
import os
import random
from datetime import datetime

app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

USERS_FILE = "users.json"
DROPS_FILE = "drops.json"

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                c = f.read()
                if c.strip():
                    return json.loads(c)
        except:
            pass
    return {}

def save_users(u):
    with open(USERS_FILE, "w") as f:
        f.write(json.dumps(u, ensure_ascii=False, indent=2))

def load_drops():
    if os.path.exists(DROPS_FILE):
        try:
            with open(DROPS_FILE, "r") as f:
                c = f.read()
                if c.strip():
                    return json.loads(c)
        except:
            pass
    return []

def save_drops(d):
    # Храним только последние 100 дропов
    d = d[-100:]
    with open(DROPS_FILE, "w") as f:
        f.write(json.dumps(d, ensure_ascii=False, indent=2))

users = load_users()
drops = load_drops()

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def get_user_by_username(u):
    for uid, data in users.items():
        if data.get("username") == u:
            return uid, data
    return None, None

def init_stats():
    return {"total_opened": 0, "total_spent": 0, "total_earned": 0, "most_expensive": None, "best_drop": None}

@app.get("/api/cases")
def get_cases():
    return {"cases": [{"id": cid, "name": c["name"], "image": c["image"], "price": c["price"], "type": c.get("type","weapon")} for cid, c in CASES.items()]}

@app.get("/api/case_items")
def case_items(case_id: str):
    if case_id not in CASES:
        raise HTTPException(400, "Кейс не найден")
    case = CASES[case_id]
    items = []
    for item in case["items"]:
        skin = SKINS.get(item["skin"], {})
        items.append({"name": item["skin"], "chance": item["chance"], "price": skin.get("price", 0), "color": skin.get("color", "#888"), "rarity": skin.get("rarity", "common"), "image": skin.get("image", "/static/skins/default.png")})
    items.sort(key=lambda x: {"gold":0,"red":1,"pink":2,"blue":3}.get(x["rarity"],4))
    return items

@app.post("/api/register")
def register(username: str, password: str):
    if get_user_by_username(username)[0]:
        raise HTTPException(400, "Пользователь уже существует")
    if len(username) < 3 or len(password) < 4:
        raise HTTPException(400, "Ник >=3, пароль >=4")
    uid = str(uuid.uuid4())[:8]
    users[uid] = {"username": username, "password": hash_password(password), "balance": 1000, "inventory": [], "stats": init_stats(), "trade_url": ""}
    save_users(users)
    return {"user_id": uid, "username": username, "balance": 1000, "stats": users[uid]["stats"]}

@app.post("/api/login")
def login(username: str, password: str):
    uid, data = get_user_by_username(username)
    if not data or data["password"] != hash_password(password):
        raise HTTPException(400, "Неверный логин или пароль")
    if "stats" not in data: data["stats"] = init_stats()
    return {"user_id": uid, "username": data["username"], "balance": data["balance"], "stats": data["stats"], "trade_url": data.get("trade_url","")}

@app.get("/api/info")
def info(user_id: str):
    if user_id not in users: raise HTTPException(404, "Пользователь не найден")
    u = users[user_id]
    if "stats" not in u: u["stats"] = init_stats()
    return {"username": u["username"], "balance": u["balance"], "inventory": u["inventory"], "stats": u["stats"], "trade_url": u.get("trade_url","")}

@app.get("/api/user_profile")
def user_profile(user_id: str):
    """Публичный профиль пользователя"""
    if user_id not in users: raise HTTPException(404, "Пользователь не найден")
    u = users[user_id]
    if "stats" not in u: u["stats"] = init_stats()
    return {
        "username": u["username"],
        "stats": u["stats"],
        "inventory_count": len(u["inventory"])
    }

@app.post("/api/open")
def open_case_endpoint(user_id: str, case_id: str):
    if user_id not in users: raise HTTPException(404, "Пользователь не найден")
    if case_id not in CASES: raise HTTPException(400, "Кейс не найден")
    u = users[user_id]
    case = CASES[case_id]
    if u["balance"] < case["price"]: raise HTTPException(400, f"Недостаточно монет! Нужно {case['price']}💰")
    if "stats" not in u: u["stats"] = init_stats()
    u["balance"] -= case["price"]
    u["stats"]["total_opened"] += 1
    u["stats"]["total_spent"] += case["price"]
    result = open_case(case)
    u["inventory"].append(result)
    if u["stats"]["best_drop"] is None or result["price"] > u["stats"]["best_drop"]["price"]:
        u["stats"]["best_drop"] = {"name": result["name"], "price": result["price"], "rarity": result["rarity"], "color": result["color"], "image": result["image"]}
    prices = [(i, item["price"]) for i, item in enumerate(u["inventory"])]
    if prices:
        mi, mp = max(prices, key=lambda x: x[1])
        u["stats"]["most_expensive"] = {"name": u["inventory"][mi]["name"], "price": mp, "rarity": u["inventory"][mi]["rarity"], "color": u["inventory"][mi]["color"], "image": u["inventory"][mi]["image"]}
    save_users(users)
    
    # Добавляем в ленту дропов
    drops.append({
        "username": u["username"],
        "user_id": user_id,
        "skin_name": result["name"],
        "skin_image": result["image"],
        "rarity": result["rarity"],
        "color": result["color"],
        "price": result["price"],
        "case_name": case["name"],
        "time": datetime.now().isoformat()
    })
    save_drops(drops)
    
    return {"result": result, "balance": u["balance"], "stats": u["stats"]}

@app.get("/api/drops")
def get_drops():
    """Лента последних выпадений"""
    return {"drops": list(reversed(drops[-30:]))}

@app.post("/api/sell")
def sell(user_id: str, index: int):
    if user_id not in users: raise HTTPException(404, "Пользователь не найден")
    u = users[user_id]
    if index < 0 or index >= len(u["inventory"]): raise HTTPException(400, "Скин не найден")
    if "stats" not in u: u["stats"] = init_stats()
    sold = u["inventory"].pop(index)
    u["balance"] += sold.get("price", 0)
    u["stats"]["total_earned"] += sold.get("price", 0)
    prices = [(i, item["price"]) for i, item in enumerate(u["inventory"])]
    u["stats"]["most_expensive"] = None
    if prices:
        mi, mp = max(prices, key=lambda x: x[1])
        u["stats"]["most_expensive"] = {"name": u["inventory"][mi]["name"], "price": mp, "rarity": u["inventory"][mi]["rarity"], "color": u["inventory"][mi]["color"], "image": u["inventory"][mi]["image"]}
    save_users(users)
    return {"sold": sold, "balance": u["balance"], "inventory": u["inventory"], "stats": u["stats"]}

@app.post("/api/upgrade")
def upgrade(user_id: str):
    if user_id not in users: raise HTTPException(404, "Пользователь не найден")
    u = users[user_id]
    if u["balance"] < UPGRADE_COST: raise HTTPException(400, f"Недостаточно монет! Нужно {UPGRADE_COST}💰")
    by_r = {"blue":[],"pink":[],"red":[],"gold":[]}
    for i, item in enumerate(u["inventory"]):
        r = item["rarity"]
        if r in by_r: by_r[r].append(i)
    target = None
    for r in ["blue","pink","red"]:
        if len(by_r[r]) >= UPGRADE_REQUIRED: target = r; break
    if not target: raise HTTPException(400, f"Нужно {UPGRADE_REQUIRED} скинов одной редкости")
    indices = sorted(by_r[target][-UPGRADE_REQUIRED:], reverse=True)
    for idx in indices: u["inventory"].pop(idx)
    next_r = {"blue":"pink","pink":"red","red":"gold"}[target]
    possible = [(n,d) for n,d in SKINS.items() if d["rarity"]==next_r]
    cn, cd = random.choice(possible)
    new_skin = {"name":cn,"rarity":cd["rarity"],"color":cd["color"],"image":cd["image"],"price":cd["price"],"type":cd.get("type","weapon")}
    u["balance"] -= UPGRADE_COST
    u["inventory"].append(new_skin)
    save_users(users)
    return {"new_skin":new_skin,"balance":u["balance"],"inventory":u["inventory"]}

@app.post("/api/add_balance")
def add_balance(user_id: str, amount: int = 1000):
    if user_id not in users: raise HTTPException(404, "Пользователь не найден")
    users[user_id]["balance"] += amount
    save_users(users)
    return {"balance": users[user_id]["balance"], "added": amount}

@app.post("/api/update_trade_url")
def update_trade_url(user_id: str, trade_url: str):
    if user_id not in users: raise HTTPException(404, "Пользователь не найден")
    users[user_id]["trade_url"] = trade_url
    save_users(users)
    return {"success": True}

@app.get("/api/withdrawals")
def get_withdrawals(user_id: str):
    return {"withdrawals": []}

@app.post("/api/withdraw")
def withdraw(user_id: str, skin_index: int):
    raise HTTPException(400, "Вывод временно недоступен")

@app.get("/")
def main():
    return FileResponse("index.html")
