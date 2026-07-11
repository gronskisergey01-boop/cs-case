from PIL import Image, ImageDraw
import os

os.makedirs("static/skins", exist_ok=True)
os.makedirs("static/cases", exist_ok=True)

# Создаём картинку кейса
img = Image.new('RGB', (250, 200), color="#ff3b5c")
draw = ImageDraw.Draw(img)
draw.text((80, 90), "LUKA CASE", fill="white")
img.save("static/cases/luka.png")
print("luka.png создан")

# Создаём картинки скинов (просто цветные квадраты)
skins = [
    "deagle_blue_plywood", "mac10_azure", "deagle_discontent", "m4a1s_northern_forest",
    "r8_flame", "ump45_carcass", "glock_weasel", "g3sg1_black_sand", "negev_loader",
    "dual_panther", "m4a4_pixel", "ssg08_handbrake", "deagle_marksman", "p90_elite",
    "tec9_opal", "p90_roadwarrior", "glock_ghosts", "mp5_gauss", "awp_arsenic",
    "m4a1s_mixed", "p2000_amber", "m4a1s_night_terror", "sg553_colony",
    "cz75_yellow_jacket", "deagle_oxide", "usps_night_ops", "usps_tropical",
    "usps_conductor", "mag7_cobalt", "dual_protector", "fiveseven_fire_test",
    "deagle_daily", "m4a1s_electrum", "scar20_generator", "usps_desert",
    "sg553_moth", "ak47_aphrodite", "p250_cyber", "p90_nostalgia",
    "ssg08_necromancer", "negev_screamer", "p90_blueprint"
]
import random
for name in skins:
    c = f"#{random.randint(0,255):02x}{random.randint(0,255):02x}{random.randint(0,255):02x}"
    img = Image.new('RGB', (200, 150), color=c)
    img.save(f"static/skins/{name}.png")
    print(f"{name}.png создан")
print("Готово!")
