from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from case_engine import open_case
from models import CASES, SKINS, UPGRADE_COST, UPGRADE_REQUIRED
import uuid, json, os, random
from datetime import datetime
from urllib.parse import urlencode

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
        json.dump(u, f, ensure_ascii=False, indent=2)

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
        json.dump(d[-100:], f, ensure_ascii=False, indent=2)

users = load_users()
drops = load_drops()

def init_stats():
    return {"total_opened": 0, "total_spent": 0, "total_earned": 0, "most_expensive": None, "best_drop": None}

# ========== STEAM LOGIN ==========

@app.get("/api/steam/login")
def steam_login():
    callback_url = f"{SITE_URL}/api/steam/callback"
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": callback_url,
        "openid.realm": SITE_URL,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }
    return RedirectResponse(url=f"https://steamcommunity.com/openid/login?{urlencode(params)}")

@app.get("/api/steam/callback")
async def steam_callback(request: Request):
    params = dict(request.query_params)
    claimed_id = params.get("openid.claimed_id", "")
    
    if not claimed_id:
        return HTMLResponse(f"""<html><body style="background:#0a0a0f;color:#fff;font-family:Arial;padding:40px"><h2>Ошибка</h2><pre>{json.dumps(params,indent=2)}</pre><a href="/" style="color:#ffd940">На главную</a></body></html>""")
    
    steam_id = claimed_id.split("/")[-1]
    
    uid = None
    for u_id, data in users.items():
        if data.get("steam_id") == steam_id:
            uid = u_id
            break
    
    username = f"Player_{steam_id[-4:]}"
    
    if not uid:
        uid = str(uuid.uuid4())[:8]
        users[uid] = {"steam_id": steam_id, "username": username, "avatar": "", "balance": 1000, "inventory": [], "stats": init_stats(), "trade_url": ""}
    else:
        username = users[uid].get("username", username)
    
    save_users(users)
    
    return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body style="background:#0a0a0f;color:#fff;font-family:Arial;text-align:center;padding-top:100px"><h2>Вход выполнен!</h2><script>localStorage.setItem('cs_user_id','{uid}');localStorage.setItem('cs_username','{username}');window.location.href='/';</script></body></html>""")

# ========== API ==========

@app.get("/api/cases")
def get_cases():
    # Обычные кейсы
    cases_list = [{"id": cid, "name": c["name"], "image": c["image"], "price": c["price"], "type": c.get("type","weapon")} for cid, c in CASES.items()]
    # Добавляем пользовательские
    for cc in custom_cases:
        cases_list.append({
            "id": cc["id"],
            "name": cc["name"],
            "image": cc["image"],
            "price": cc["price"],
            "type": "custom",
            "creator": cc["creator_name"]
        })
    return {"cases": cases_list}
    
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
    return {"username": u["username"], "balance": u["balance"], "inventory": u["inventory"], "stats": u["stats"]}

@app.get("/api/user_profile")
def user_profile(user_id: str):
    if user_id not in users: raise HTTPException(404)
    u = users[user_id]
    return {"username": u["username"], "stats": u.get("stats",init_stats()), "inventory_count": len(u.get("inventory",[]))}

@app.post("/api/open")
def open_case_endpoint(user_id: str, case_id: str):
    if user_id not in users: raise HTTPException(404)
    if case_id not in CASES: raise HTTPException(400)
    u = users[user_id]
    case = CASES[case_id]
    if u["balance"] < case["price"]: raise HTTPException(400, f"Нужно {case['price']}💰")
    if "stats" not in u: u["stats"] = init_stats()
    u["balance"] -= case["price"]
    u["stats"]["total_opened"] += 1
    u["stats"]["total_spent"] += case["price"]
    result = open_case(case)
    u["inventory"].append(result)
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
    if index < 0 or index >= len(u["inventory"]): raise HTTPException(400)
    sold = u["inventory"].pop(index)
    u["balance"] += sold.get("price", 0)
    save_users(users)
    return {"sold": sold, "balance": u["balance"], "inventory": u["inventory"]}

@app.post("/api/upgrade")
def upgrade(user_id: str):
    if user_id not in users: raise HTTPException(404)
    u = users[user_id]
    if u["balance"] < UPGRADE_COST: raise HTTPException(400)
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
    if skin_index < 0 or skin_index >= len(u["inventory"]): raise HTTPException(400)
    skin = u["inventory"].pop(skin_index)
    save_users(users)
    return {"success": True, "message": f"Заявка на вывод {skin['name']} создана"}
# ========== ПОЛЬЗОВАТЕЛЬСКИЕ КЕЙСЫ ==========

CUSTOM_CASES_FILE = "custom_cases.json"

def load_custom_cases():
    if os.path.exists(CUSTOM_CASES_FILE):
        try:
            with open(CUSTOM_CASES_FILE, "r") as f:
                return json.load(f)
        except: pass
    return []

def save_custom_cases(c):
    with open(CUSTOM_CASES_FILE, "w") as f:
        json.dump(c, f, ensure_ascii=False, indent=2)

custom_cases = load_custom_cases()

# Комиссия сайта
SITE_COMMISSION = 0.25  # 25% наценка к себестоимости

@app.get("/api/skins_database")
def skins_database():
    """Получить все доступные скины для создания кейсов"""
    skins_list = []
    for name, data in SKINS.items():
        skins_list.append({
            "name": name,
            "rarity": data["rarity"],
            "color": data["color"],
            "image": data["image"],
            "price": data["price"],
            "type": data.get("type", "weapon")
        })
    return {"skins": skins_list}

@app.post("/api/create_case")
def create_custom_case(user_id: str, name: str, items_json: str):
    """
    Создаёт пользовательский кейс
    items_json: [{"skin":"AK-47 | Redline","chance":30},...]
    """
    if user_id not in users: raise HTTPException(404, "Пользователь не найден")
    
    try:
        items = json.loads(items_json)
    except:
        raise HTTPException(400, "Неверный формат скинов")
    
    if not items or len(items) < 5:
        raise HTTPException(400, "Минимум 5 скинов в кейсе")
    if len(items) > 30:
        raise HTTPException(400, "Максимум 30 скинов в кейсе")
    
    # Считаем себестоимость (средневзвешенная цена)
    total_chance = sum(item["chance"] for item in items)
    avg_price = 0
    for item in items:
        skin_data = SKINS.get(item["skin"])
        if not skin_data:
            raise HTTPException(400, f"Скин не найден: {item['skin']}")
        avg_price += skin_data["price"] * (item["chance"] / total_chance)
    
    # Цена с наценкой сайта
    case_price = int(avg_price * (1 + SITE_COMMISSION))
    if case_price < 10:
        case_price = 10  # Минимальная цена
    
    case_id = str(uuid.uuid4())[:8]
    custom_case = {
        "id": case_id,
        "name": name,
        "creator_id": user_id,
        "creator_name": users[user_id]["username"],
        "price": case_price,
        "avg_value": int(avg_price),
        "image": "/static/cases/custom.png",
        "type": "custom",
        "items": items,
        "opens": 0
    }
    
    custom_cases.append(custom_case)
    save_custom_cases(custom_cases)
    
    return {"case": custom_case}

@app.get("/api/custom_cases")
def get_custom_cases():
    """Список пользовательских кейсов"""
    return {"cases": custom_cases}

@app.post("/api/open_custom")
def open_custom_case(user_id: str, case_id: str):
    """Открыть пользовательский кейс"""
    if user_id not in users: raise HTTPException(404, "Пользователь не найден")
    
    # Ищем кейс
    case = None
    for c in custom_cases:
        if c["id"] == case_id:
            case = c
            break
    if not case:
        raise HTTPException(400, "Кейс не найден")
    
    u = users[user_id]
    if u["balance"] < case["price"]:
        raise HTTPException(400, f"Недостаточно монет! Нужно {case['price']}💰")
    
    u["balance"] -= case["price"]
    case["opens"] += 1
    
    # Выбираем скин по шансам
    wheel = []
    for item in case["items"]:
        count = int(item["chance"] * 100)
        wheel.extend([item["skin"]] * count)
    
    winner_name = random.choice(wheel)
    skin_data = SKINS.get(winner_name, {"rarity":"common","color":"#888","image":"/static/skins/default.png","price":0})
    
    result = {
        "name": winner_name,
        "rarity": skin_data["rarity"],
        "color": skin_data["color"],
        "image": skin_data["image"],
        "price": skin_data["price"],
        "type": skin_data.get("type","weapon")
    }
    
    u["inventory"].append(result)
    
    # Начисляем процент создателю
    creator_commission = int(case["price"] * 0.05)  # 5% создателю
    if case["creator_id"] in users:
        users[case["creator_id"]]["balance"] += creator_commission
    
    save_users(users)
    save_custom_cases(custom_cases)
    
    # Добавляем в ленту дропов
    drops.append({
        "username": u["username"], "user_id": user_id,
        "skin_name": result["name"], "skin_image": result["image"],
        "rarity": result["rarity"], "color": result["color"],
        "price": result["price"], "case_name": case["name"],
        "time": datetime.now().isoformat()
    })
    save_drops(drops)
    
    return {"result": result, "balance": u["balance"], "case": case}
@app.get("/")
def main():
    return FileResponse("index.html")
