from PIL import Image, ImageDraw, ImageFont
import os

os.makedirs("static/skins", exist_ok=True)
os.makedirs("static/cases", exist_ok=True)

skins = {
    "ak47_vulcan": "#ff3b5c", "m4a4_neonoir": "#ff3b5c", "awp_lightning": "#e040fb",
    "deagle_printstream": "#ff3b5c", "sticker_titan": "#ffd940", "sticker_ibuypower": "#ffd940",
    "sticker_navi": "#ffd940", "sticker_faze": "#ff3b5c", "sticker_vp": "#e040fb",
    "sticker_c9": "#e040fb", "sticker_g2": "#ff3b5c", "sticker_liquid": "#e040fb",
    "sticker_astralis": "#ff3b5c", "sticker_vitality": "#e040fb",
    "agent_ksk": "#ff3b5c", "agent_seal": "#ff3b5c", "agent_swat": "#e040fb",
    "agent_fbi": "#e040fb", "agent_gendarmerie": "#e040fb", "agent_sas": "#ff3b5c",
    "agent_spetsnaz": "#ffd940", "agent_phoenix": "#ffd940",
}

cases = {
    "sticker_capsule": "#e040fb", "agent_case": "#ff3b5c",
}

def create_image(filename, color, folder, text=None, size=(200,150)):
    img = Image.new('RGB', size, color=color)
    draw = ImageDraw.Draw(img)
    try: font = ImageFont.truetype("arial.ttf", 14)
    except: font = ImageFont.load_default()
    if text is None: text = filename.replace("_"," ").title()
    bbox = draw.textbbox((0,0), text, font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    draw.text(((size[0]-tw)/2, (size[1]-th)/2), text, fill="black" if sum(int(color[i:i+2],16) for i in (1,3,5))/3>128 else "white", font=font)
    img.save(f"{folder}/{filename}.png")

for f,c in skins.items(): create_image(f, c, "static/skins")
for f,c in cases.items(): create_image(f, c, "static/cases", f.replace("_"," ").title()+" Case", (250,200))
print("Готово!")