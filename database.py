import sqlite3
import os
from datetime import datetime

DB_FILE = "cs_case.db"

def get_db():
    """Подключение к базе данных"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Создаёт все таблицы если их нет"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Пользователи
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            steam_id TEXT UNIQUE,
            username TEXT NOT NULL,
            avatar TEXT DEFAULT '',
            balance INTEGER DEFAULT 1000,
            trade_url TEXT DEFAULT '',
            total_opened INTEGER DEFAULT 0,
            total_spent INTEGER DEFAULT 0,
            total_earned INTEGER DEFAULT 0,
            best_drop_name TEXT,
            best_drop_price INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Инвентарь пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            skin_name TEXT NOT NULL,
            rarity TEXT NOT NULL,
            color TEXT NOT NULL,
            image TEXT NOT NULL,
            price INTEGER NOT NULL,
            skin_type TEXT DEFAULT 'weapon',
            obtained_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Кейсы (обычные + пользовательские)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cases (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            image TEXT NOT NULL,
            price INTEGER NOT NULL,
            case_type TEXT DEFAULT 'weapon',
            creator_id TEXT,
            creator_name TEXT,
            avg_value INTEGER,
            opens INTEGER DEFAULT 0,
            is_custom INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (creator_id) REFERENCES users(id)
        )
    ''')
    
    # Предметы в кейсах
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS case_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT NOT NULL,
            skin_name TEXT NOT NULL,
            chance REAL NOT NULL,
            FOREIGN KEY (case_id) REFERENCES cases(id)
        )
    ''')
    
    # Транзакции
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            skin_name TEXT,
            case_name TEXT,
            description TEXT,
            balance_after INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Дропы (лента)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS drops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            skin_name TEXT NOT NULL,
            skin_image TEXT NOT NULL,
            rarity TEXT NOT NULL,
            color TEXT NOT NULL,
            price INTEGER NOT NULL,
            case_name TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("База данных создана")

# ========== ПОЛЬЗОВАТЕЛИ ==========

def create_user(user_id: str, steam_id: str = "", username: str = "Player"):
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO users (id, steam_id, username) VALUES (?, ?, ?)",
        (user_id, steam_id, username)
    )
    conn.commit()
    conn.close()

def get_user(user_id: str):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_steam_id(steam_id: str):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE steam_id = ?", (steam_id,)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_username(username: str):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(user) if user else None

def update_balance(user_id: str, amount: int):
    conn = get_db()
    conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def update_user_stats(user_id: str, spent: int = 0, earned: int = 0):
    conn = get_db()
    if spent:
        conn.execute("UPDATE users SET total_opened = total_opened + 1, total_spent = total_spent + ? WHERE id = ?", (spent, user_id))
    if earned:
        conn.execute("UPDATE users SET total_earned = total_earned + ? WHERE id = ?", (earned, user_id))
    conn.commit()
    conn.close()

# ========== ИНВЕНТАРЬ ==========

def add_to_inventory(user_id: str, skin_name: str, rarity: str, color: str, image: str, price: int, skin_type: str = "weapon"):
    conn = get_db()
    conn.execute(
        "INSERT INTO user_inventory (user_id, skin_name, rarity, color, image, price, skin_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, skin_name, rarity, color, image, price, skin_type)
    )
    conn.commit()
    conn.close()

def get_inventory(user_id: str):
    conn = get_db()
    items = conn.execute("SELECT * FROM user_inventory WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    conn.close()
    return [dict(item) for item in items]

def remove_from_inventory(item_id: int):
    conn = get_db()
    item = conn.execute("SELECT * FROM user_inventory WHERE id = ?", (item_id,)).fetchone()
    if item:
        conn.execute("DELETE FROM user_inventory WHERE id = ?", (item_id,))
        conn.commit()
    conn.close()
    return dict(item) if item else None

# ========== КЕЙСЫ ==========

def add_case(case_id: str, name: str, image: str, price: int, case_type: str, creator_id: str = None, creator_name: str = None, is_custom: int = 0):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO cases (id, name, image, price, case_type, creator_id, creator_name, is_custom) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (case_id, name, image, price, case_type, creator_id, creator_name, is_custom)
    )
    conn.commit()
    conn.close()

def add_case_items(case_id: str, items: list):
    conn = get_db()
    conn.execute("DELETE FROM case_items WHERE case_id = ?", (case_id,))
    for item in items:
        conn.execute(
            "INSERT INTO case_items (case_id, skin_name, chance) VALUES (?, ?, ?)",
            (case_id, item["skin"], item["chance"])
        )
    conn.commit()
    conn.close()

def get_all_cases():
    conn = get_db()
    cases = conn.execute("SELECT * FROM cases ORDER BY is_custom, created_at DESC").fetchall()
    conn.close()
    return [dict(c) for c in cases]

def get_case_items(case_id: str):
    conn = get_db()
    items = conn.execute("SELECT * FROM case_items WHERE case_id = ?", (case_id,)).fetchall()
    conn.close()
    return [dict(i) for i in items]

def increment_case_opens(case_id: str):
    conn = get_db()
    conn.execute("UPDATE cases SET opens = opens + 1 WHERE id = ?", (case_id,))
    conn.commit()
    conn.close()

# ========== ТРАНЗАКЦИИ ==========

def add_transaction(user_id: str, trans_type: str, amount: int, skin_name: str = None, case_name: str = None, description: str = None, balance_after: int = 0):
    conn = get_db()
    conn.execute(
        "INSERT INTO transactions (user_id, type, amount, skin_name, case_name, description, balance_after) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, trans_type, amount, skin_name, case_name, description, balance_after)
    )
    conn.commit()
    conn.close()

# ========== ДРОПЫ ==========

def add_drop(user_id: str, username: str, skin_name: str, skin_image: str, rarity: str, color: str, price: int, case_name: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO drops (user_id, username, skin_name, skin_image, rarity, color, price, case_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, username, skin_name, skin_image, rarity, color, price, case_name)
    )
    conn.execute("DELETE FROM drops WHERE id NOT IN (SELECT id FROM drops ORDER BY id DESC LIMIT 200)")
    conn.commit()
    conn.close()

def get_drops(limit: int = 50):
    conn = get_db()
    drops = conn.execute("SELECT * FROM drops ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(d) for d in drops]

# Инициализация при импорте
init_db()