import sqlite3

def init_db():
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT
        )
    ''')
    # Добавили колонку payment_link
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            service_name TEXT,
            category TEXT,
            period TEXT,
            price REAL,
            next_payment_date TEXT,
            payment_link TEXT,  -- НОВАЯ КОЛОНКА
            reminder_days INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    conn.commit()
    conn.close()

def add_user(user_id, username):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)', (user_id, username))
    conn.commit()
    conn.close()

# Добавили payment_link
def add_subscription(user_id, service_name, category, period, price, next_payment_date, payment_link, reminder_days):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO subscriptions (user_id, service_name, category, period, price, next_payment_date, payment_link, reminder_days)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, service_name, category, period, price, next_payment_date, payment_link, reminder_days))
    conn.commit()
    conn.close()

# Теперь отдаем 8 значений (включая ссылку)
def get_subscriptions(user_id):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, service_name, category, period, price, next_payment_date, reminder_days, payment_link
        FROM subscriptions 
        WHERE user_id = ?
    ''', (user_id,))
    subs = cursor.fetchall()
    conn.close()
    return subs

def delete_subscription(sub_id):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM subscriptions WHERE id = ?', (sub_id,))
    conn.commit()
    conn.close()

def get_subscription_period_and_date(sub_id):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT period, next_payment_date, service_name FROM subscriptions WHERE id = ?', (sub_id,))
    res = cursor.fetchone()
    conn.close()
    return res

def get_subscription_name(sub_id):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT service_name FROM subscriptions WHERE id = ?', (sub_id,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else "Подписка"

def update_subscription(sub_id, field, value):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute(f'UPDATE subscriptions SET {field} = ? WHERE id = ?', (value, sub_id))
    conn.commit()
    conn.close()

def get_advanced_statistics(user_id):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT category, period, price FROM subscriptions WHERE user_id = ?', (user_id,))
    subs = cursor.fetchall()
    conn.close()
    return subs

# Теперь планировщик достает еще и ссылку!
def get_all_subscriptions_for_reminders():
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT user_id, service_name, price, next_payment_date, reminder_days, payment_link 
        FROM subscriptions 
        WHERE reminder_days > 0
    ''')
    subs = cursor.fetchall()
    conn.close()
    return subs

init_db()