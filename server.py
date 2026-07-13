from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from models import CASES, SKINS, UPGRADE_COST, UPGRADE_REQUIRED
from database import *
import uuid, json, os, random
from datetime import datetime
from urllib.parse import urlencode
from case_engine import open_case

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

SITE_URL = os.getenv("SITE_URL", "https://cs-case.onrender.com")
SITE_COMMISSION = 0.25

# Инициализируем БД и загружаем обычные кейсы
init_db()

# Загружаем обычные кейсы в БД при старте
for case_id, case_data in CASES.items():
    add_case(case_id, case_data["name"], case_data["image"], case_data["price"], case_data.get("type", "weapon"))
    add_case_items(case_id, case_data["items"])

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
        return HTMLResponse("<html><body style='background:#0a0a0f;color:#fff;padding:40px'><h2>Ошибка входа</h2><a href='/' style='color:#ffd940'>На главную</a></body></html>")
    
    steam_id = claimed_id.split("/")[-1]
    user = get_user_by_steam_id(steam_id)
    
    if not user:
        uid = str(uuid.uuid4())[:8]
        username = f"Player_{steam_id[-4:]}"
        create_user(uid, steam_id, username)
        user = get_user(uid)
    
    return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body style="background:#0a0a0f;color:#fff;text-align:center;padding-top:100px"><h2>Вход выполнен!</h2><script>localStorage.setItem('cs_user_id','{user["id"]}');localStorage.setItem('cs_username','{user["username"]}');window.location.href='/';</script></body></html>""")

# ========== API ==========

@app.get("/api/cases")
def get_cases():
    cases = get_all_cases()
    return {"cases": cases}

@app.get("/api/skins_database")
def skins_database():
    return {"skins": [{"name": n, "rarity": d["rarity"], "color": d["color"], "image": d["image"], "price": d["price"]} for n, d in SKINS.items()]}

@app.post("/api/create_case")
def create_custom_case(user_id: str, name: str, items_json: str):
    user = get_user(user_id)
    if not user: raise HTTPException(404)
    try:
        items = json.loads(items_json)
    except:
        raise HTTPException(400, "Неверный формат")
    if len(items) < 5: raise HTTPException(400, "Минимум 5 скинов")
    if len(items) > 30: raise HTTPException(400, "Максимум 30 скинов")
    
    total_chance = sum(i["chance"] for i in items)
    avg_price = sum(SKINS[i["skin"]]["price"] * (i["chance"] / total_chance) for i in items)
    case_price = max(10, int(avg_price * (1 + SITE_COMMISSION)))
    case_id = str(uuid.uuid4())[:8]
    
    add_case(case_id, name, "/static/cases/custom.png", case_price, "custom", user_id, user["username"], 1)
    add_case_items(case_id, items)
    
    return {"case": {"id": case_id, "name": name, "price": case_price}}

@app.get("/api/case_items")
def case_items(case_id: str):
    items = get_case_items(case_id)
    result = []
    for item in items:
        skin = SKINS.get(item["skin_name"], {})
        result.append({"name": item["skin_name"], "chance": item["chance"], "price": skin.get("price", 0), "color": skin.get("color", "#888"), "rarity": skin.get("rarity", "common"), "image": skin.get("image", "/static/skins/default.png")})
    return result

@app.get("/api/info")
def info(user_id: str):
    user = get_user(user_id)
    if not user: raise HTTPException(404)
    inventory = get_inventory(user_id)
    return {"username": user["username"], "balance": user["balance"], "inventory": inventory, "stats": {"total_opened": user["total_opened"], "total_spent": user["total_spent"], "total_earned": user["total_earned"]}}

@app.post("/api/open")
def open_case_endpoint(user_id: str, case_id: str):
    user = get_user(user_id)
    if not user: raise HTTPException(404)
    
    cases = get_all_cases()
    case = next((c for c in cases if c["id"] == case_id), None)
    if not case: raise HTTPException(400, "Кейс не найден")
    if user["balance"] < case["price"]: raise HTTPException(400, f"Нужно {case['price']}💰")
    
    # Списываем баланс
    update_balance(user_id, -case["price"])
    update_user_stats(user_id, spent=case["price"])
    
    # Выбираем скин
    items = get_case_items(case_id)
    wheel = []
    for item in items:
        wheel.extend([item["skin_name"]] * int(item["chance"] * 100))
    winner_name = random.choice(wheel) if wheel else items[0]["skin_name"]
    skin_data = SKINS.get(winner_name, {"rarity":"common","color":"#888","image":"/static/skins/default.png","price":0})
    
    # Добавляем в инвентарь
    add_to_inventory(user_id, winner_name, skin_data["rarity"], skin_data["color"], skin_data["image"], skin_data["price"])
    
    # Обновляем счётчик кейса
    increment_case_opens(case_id)
    
    # Комиссия создателю
    if case["creator_id"]:
        update_balance(case["creator_id"], int(case["price"] * 0.05))
    
    # Транзакция
    updated_user = get_user(user_id)
    add_transaction(user_id, "open", -case["price"], winner_name, case["name"], f"Открытие кейса", updated_user["balance"])
    
    # Дроп в ленту
    add_drop(user_id, user["username"], winner_name, skin_data["image"], skin_data["rarity"], skin_data["color"], skin_data["price"], case["name"])
    
    return {"result": {"name": winner_name, "rarity": skin_data["rarity"], "color": skin_data["color"], "image": skin_data["image"], "price": skin_data["price"]}, "balance": updated_user["balance"]}

@app.get("/api/drops")
def get_drops_list():
    return {"drops": get_drops(50)}

@app.post("/api/sell")
def sell(user_id: str, index: int):
    user = get_user(user_id)
    if not user: raise HTTPException(404)
    inventory = get_inventory(user_id)
    if index < 0 or index >= len(inventory): raise HTTPException(400)
    
    item = inventory[index]
    remove_from_inventory(item["id"])
    update_balance(user_id, item["price"])
    update_user_stats(user_id, earned=item["price"])
    
    updated_user = get_user(user_id)
    add_transaction(user_id, "sell", item["price"], item["skin_name"], None, "Продажа скина", updated_user["balance"])
    
    return {"sold": item, "balance": updated_user["balance"], "inventory": get_inventory(user_id)}

@app.post("/api/add_balance")
def add_balance(user_id: str, amount: int = 1000):
    if not get_user(user_id): raise HTTPException(404)
    update_balance(user_id, amount)
    updated_user = get_user(user_id)
    add_transaction(user_id, "add_balance", amount, None, None, "Пополнение баланса", updated_user["balance"])
    return {"balance": updated_user["balance"]}

@app.get("/")
def main():
    return FileResponse("index.html")
