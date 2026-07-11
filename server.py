from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from case_engine import open_case
from models import CASES, SKINS, UPGRADE_COST, UPGRADE_REQUIRED
import hashlib
import uuid
import json
import os
import random
from datetime import datetime
from urllib.parse import urlencode
import urllib.request

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

USERS_FILE = "users.json"
DROPS_FILE = "drops.json"
SITE_URL = os.getenv("SITE_URL", "https://cs-case.onrender.com")

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

# ========== STEAM LOGIN ==========

@app.get("/api/steam/login")
def steam_login():
    """Перенаправляет на Steam для входа"""
    callback_url = f"{SITE_URL}/api/steam/callback"
    
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": callback_url,
        "openid.realm": SITE_URL,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }
    
    login_url = f"https://steamcommunity.com/openid/login?{urlencode(params)}"
    return RedirectResponse(url=login_url)

@app.get("/api/steam/callback")
async def steam_callback(request: Request):
    """Callback после входа через Steam"""
    
    # Получаем ВСЕ параметры из URL
    params = dict(request.query_params)
    print(f"Callback params: {params}")
    
    # Проверяем что Steam вернул claimed_id
    claimed_id = params.get("openid.claimed_id", "")
    
    if not claimed_id:
        return HTMLResponse(f"""
        <html><body style="background:#1a1a2e;color:#fff;font-family:Arial;padding:40px">
        <h2>Ошибка входа</h2>
        <p>Steam не вернул ID. Параметры:</p>
        <pre>{json.dumps(params, indent=2)}</pre>
        <a href="/" style="color:#ffd940">На главную</a>
        </body></html>
        """)
    
    # Извлекаем Steam ID
    steam_id = claimed_id.split("/")[-1]
    print(f"Steam ID: {steam_id}")
    
    # Ищем пользователя
    uid = None
    for u_id, data in users.items():
        if data.get("steam_id") == steam_id:
            uid = u_id
            break
    
    username = f"Player_{steam_id[-4:]}"
    avatar = ""
    
    # Пробуем получить данные из Steam API
    try:
        api_key = os.getenv("STEAM_API_KEY", "")
        if api_key:
            api_url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={api_key}&steamids={steam_id}"
            req = urllib.request.Request(api_url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                players = data.get("response", {}).get("players", [])
                if players:
                    username = players[0].get("personaname", username)
                    avatar = players[0].get("avatarfull", "")
    except Exception as e:
        print(f"Steam API error: {e}")
    
    if not uid:
        uid = str(uuid.uuid4())[:8]
        users[uid] = {
            "steam_id": steam_id,
            "username": username,
            "avatar": avatar,
            "balance": 1000,
            "inventory": [],
            "stats": init_stats(),
            "trade_url": ""
        }
    else:
        users[uid]["username"] = username
        if avatar:
            users[uid]["avatar"] = avatar
    
    save_users(users)
    
    # Перенаправляем на главную с параметрами
    return RedirectResponse(url=f"/?user_id={uid}&username={username}&avatar={avatar}")

# ========== API ==========

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
    save_users(users)
    drops.append({"username": u["username"], "user_id": user_id, "skin_name": result["name"], "skin_image": result["image"], "rarity": result["rarity"], "color": result["color"], "price": result["price"], "case_name": case["name"], "time": datetime.now().isoformat()})
    save_drops(drops)
    return {"result": result, "balance": u["balance"]}

@app.get("/api/drops")
def get_drops():
    return {"drops": list(reversed(drops[-50:]))}

@app.post("/api/sell")
def sell(user_id: str, index: int):
    if user_id not in users: raise HTTPException(404)
    u = users[user_id]
    if index < 0 or index >= len(u["inventory"]): raise HTTPException(400, "Скин не найден")
    sold = u["inventory"].pop(index)
    u["balance"] += sold.get("price", 0)
    if "stats" not in u: u["stats"] = init_stats()
    u["stats"]["total_earned"] += sold.get("price", 0)
    save_users(users)
    return {"sold": sold, "balance": u["balance"], "inventory": u["inventory"]}

@app.post("/api/upgrade")
def upgrade(user_id: str):
    if user_id not in users: raise HTTPException(404)
    u = users[user_id]
    if u["balance"] < UPGRADE_COST: raise HTTPException(400, f"Недостаточно монет! Нужно {UPGRADE_COST}💰")
    by_r = {"blue":[],"pink":[],"red":[],"gold":[]}
    for i, item in enumerate(u["inventory"]):
        r = item["rarity"]
        if r in by_r: by_r[r].append(i)
    target = None
    for r in ["blue","pink","red"]:
        if len(by_r[r]) >= UPGRADE_REQUIRED: target = r; break
    if not target: raise HTTPException(400, f"Нужно {UPGRADE_REQUIRED} скинов")
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
    if user_id not in users: raise HTTPException(404)
    users[user_id]["balance"] += amount
    save_users(users)
    return {"balance": users[user_id]["balance"]}

@app.post("/api/withdraw")
def withdraw(user_id: str, skin_index: int):
    if user_id not in users: raise HTTPException(404)
    u = users[user_id]
    if skin_index < 0 or skin_index >= len(u["inventory"]): raise HTTPException(400, "Скин не найден")
    skin = u["inventory"].pop(skin_index)
    save_users(users)
    return {"success": True, "message": f"Заявка на вывод {skin['name']} создана"}

@app.get("/")
def main():
    return FileResponse("index.html")
