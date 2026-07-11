import random
from models import SKINS

def open_case(case):
    wheel = []
    for item in case["items"]:
        count = int(item["chance"] * 100)
        wheel.extend([item["skin"]] * count)
    
    winner = random.choice(wheel)
    skin_info = SKINS.get(winner, {"rarity": "common", "color": "#888", "image": "/static/skins/default.png", "price": 0, "type": "other"})
    
    return {
        "name": winner,
        "rarity": skin_info["rarity"],
        "color": skin_info["color"],
        "image": skin_info["image"],
        "price": skin_info["price"],
        "type": skin_info.get("type", "weapon")
    }