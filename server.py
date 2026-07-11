from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from case_engine import open_case
from models import CASES, SKINS, UPGRADE_COST, UPGRADE_REQUIRED
import hashlib
import uuid
import json
import os
import random
from datetime import datetime
import requests
from urllib.parse import urlencode

app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

# Steam OpenID конфигурация
STEAM_OPENID_URL = "https://steamcommunity.com/openid"
REALM = os.getenv("SITE_URL", "https://cs-case.onrender.com")
RETURN_URL = f"{REALM}/api/steam/callback"

# Простая файловая БД (замени на SQLite при необходимости)
USERS_FILE = "users.json"
DROPS_FILE = "drops.json"

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                c = f.read()
                if c.strip(): return json.loads(c)
        except: pass
    return {}

def save_users(u):
    with open(USERS_FILE, "w") as f:
        f.write(json.dumps(u, ensure_ascii=False, indent=2))

def load_drops():
    if os.path.exists(DROPS_FILE):
        try:
            with open(DROPS_FILE, "r") as f:
                c = f.read()
                if c.strip(): return json.loads(c)
        except: pass
    return []

def save_drops(d):
    with open(DROPS_FILE, "w") as f:
        f.write(json.dumps(d[-100:], ensure_ascii=False, indent=2))

users = load_users()
drops = load_drops()

def init_stats():
    return {"total_opened": 0, "total_spent": 0, "total_earned": 0, "most_expensive": None, "best_drop": None}

def get_user_by_steam_id(steam_id: str):
    for uid, data in users.items():
        if data.get("steam_id") == steam_id:
            return uid, data
    return None, None

# ========== STEAM LOGIN ==========

@app.get("/api/steam/login")
def steam_login():
    """Перенаправляет на страницу входа Steam"""
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": RETURN_URL,
        "openid.realm": REALM,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }
    return RedirectResponse(f"{STEAM_OPENID_URL}/login?{urlencode(params)}")

@app.get("/api/steam/callback")
def steam_callback(openid_claimed_id: str = Query(None), openid_identity: str = Query(None)):
    """Callback после входа через Steam"""
    if not openid_claimed_id:
        raise HTTPException(400, "Ошибка входа через Steam")
    
    # Извлекаем Steam ID из URL
    steam_id = openid_claimed_id.split("/")[-1]
    
    # Проверяем существует ли пользователь
    uid, user_data = get_user_by_steam_id(steam_id)
    
    if not uid:
        # Создаём нового пользователя
        uid = str(uuid.uuid4())[:8]
        
        # Получаем никнейм из Steam API
        username = f"Player_{steam_id[-4:]}"
        avatar = ""
        try:
            resp = requests.get(
                f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={os.getenv('STEAM_API_KEY', '')}&steamids={steam_id}"
            )
            if resp.ok:
                data = resp.json()
                players = data.get("response", {}).get("players", [])
                if players:
                    username = players[0].get("personaname", username)
                    avatar = players[0].get("avatarfull", "")
        except:
            pass
        
        users[uid] = {
            "steam_id": steam_id,
            "username": username,
            "avatar": avatar,
            "balance": 1000,
            "inventory": [],
            "stats": init_stats(),
            "trade_url": ""
        }
        save_users(users)
    
    # Перенаправляем на главную с токеном
    user_data = users[uid]
    token = hashlib.sha256(f"{uid}{steam_id}".encode()).hexdigest()[:16]
    user_data["token"] = token
    save_users(users)
    
    return RedirectResponse(f"/?user_id={uid}&token={token}")

@app.get("/api/auth_by_token")
def auth_by_token(user_id: str, token: str):
    """Авторизация по токену"""
    if user_id not in users:
        raise HTTPException(404, "Пользователь не найден")
    u = users[user_id]
    if u.get("token") != token:
        raise HTTPException(400, "Неверный токен")
    if "stats" not in u: u["stats"] = init_stats()
    return {
        "user_id": user_id,
        "username": u["username"],
        "avatar": u.get("avatar", ""),
        "steam_id": u.get("steam_id", ""),
        "balance": u["balance"],
        "stats": u["stats"]
    }

# ========== ОСТАЛЬНОЕ API ==========

@app.get("/api/cases")
def get_cases():
    return {"cases": [{"id": cid, "name": c["name"], "image": c["image"], "price": c["price"], "type": c.get("type","weapon")} for cid, c in CASES.items()]}

@app.get("/api/case_items")
def case_items(case_id: str):
    if case_id not in CASES: raise HTTPException(400, "Кейс не найден")
    case = CASES[case_id]
    items = []
    for item in case["items"]:
        skin = SKINS.get(item["skin"], {})
        items.append({"name": item["skin"], "chance": item["chance"], "price": skin.get("price", 0), "color": skin.get("color", "#888"), "rarity": skin.get("rarity", "common"), "image": skin.get("image", "/static/skins/default.png")})
    items.sort(key=lambda x: {"gold":0,"red":1,"pink":2,"blue":3}.get(x["rarity"],4))
    return items

@app.get("/api/info")
def info(user_id: str):
    if user_id not in users: raise HTTPException(404, "Пользователь не найден")
    u = users[user_id]
    if "stats" not in u: u["stats"] = init_stats()
    return {"username": u["username"], "avatar": u.get("avatar",""), "balance": u["balance"], "inventory": u["inventory"], "stats": u["stats"]}

@app.get("/api/user_profile")
def user_profile(user_id: str):
    if user_id not in users: raise HTTPException(404, "Пользователь не найден")
    u = users[user_id]
    if "stats" not in u: u["stats"] = init_stats()
    return {"username": u["username"], "avatar": u.get("avatar",""), "stats": u["stats"], "inventory_count": len(u["inventory"])}

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
    
    drops.append({
        "username": u["username"],
        "avatar": u.get("avatar",""),
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

@app.get("/")
def main():
    return FileResponse("index.html")
