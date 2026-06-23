import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_NAME = "accounting.db"
# نسخه دیتابیس به ۵ ارتقا یافت - سیستم انبار
CURRENT_DB_VERSION = 5 

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    cursor.execute("PRAGMA user_version;")
    db_version = cursor.fetchone()[0]

    if db_version == 0:
        cursor.execute('''CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS entities (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, type TEXT, amount REAL, description TEXT,
            account_name TEXT, category_name TEXT, entity_name TEXT,
            source TEXT DEFAULT 'دستی',
            attachment TEXT DEFAULT ''
        )''')
        # ایجاد جدول‌های تگ‌ها (نسخه ۴)
        cursor.execute('''CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS transaction_tags (
            transaction_id INTEGER,
            tag_id INTEGER,
            PRIMARY KEY (transaction_id, tag_id),
            FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )''')
        
        # ایجاد جدول‌های انبار (نسخه ۵) هنگام ساخت دیتابیس جدید
        cursor.execute('''CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            unit TEXT DEFAULT 'عدد',
            buy_price REAL DEFAULT 0,
            current_stock REAL DEFAULT 0,
            min_stock REAL DEFAULT 0
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS inventory_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER,
            item_id INTEGER,
            quantity REAL NOT NULL,
            unit_price REAL DEFAULT 0,
            type TEXT NOT NULL,
            FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
        )''')
        
        cursor.execute(f"PRAGMA user_version = {CURRENT_DB_VERSION};")
        
    elif db_version == 1:
        cursor.execute("PRAGMA table_info(transactions)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'source' not in columns:
            cursor.execute("ALTER TABLE transactions ADD COLUMN source TEXT DEFAULT 'دستی'")
        if 'attachment' not in columns:
            cursor.execute("ALTER TABLE transactions ADD COLUMN attachment TEXT DEFAULT ''")
        cursor.execute(f"PRAGMA user_version = {CURRENT_DB_VERSION};")
        
    elif db_version == 2:
        cursor.execute("PRAGMA table_info(transactions)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'attachment' not in columns:
            cursor.execute("ALTER TABLE transactions ADD COLUMN attachment TEXT DEFAULT ''")
        # ارتقاء به نسخه ۳
        cursor.execute(f"PRAGMA user_version = 3;")
    
    # ارتقاء از نسخه ۳ به ۴: دسته‌بندی سلسله مراتبی و تگ‌گذاری
    db_ver = cursor.execute("PRAGMA user_version;").fetchone()[0]
    if db_ver == 3 or db_ver == 5:
        # بررسی و اضافه کردن parent_id اگر وجود نداشت
        cursor.execute("PRAGMA table_info(categories)")
        cols = [col[1] for col in cursor.fetchall()]
        if 'parent_id' not in cols:
            cursor.execute("ALTER TABLE categories ADD COLUMN parent_id INTEGER DEFAULT NULL")
        # اضافه کردن ستون parent_id به جدول categories برای سلسله مراتبی شدن
        cursor.execute("PRAGMA table_info(categories)")
        cols = [col[1] for col in cursor.fetchall()]
        if 'parent_id' not in cols:
            cursor.execute("ALTER TABLE categories ADD COLUMN parent_id INTEGER DEFAULT NULL")
        
        # ایجاد جدول تگ‌ها
        cursor.execute('''CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )''')
        
        # ایجاد جدول ارتباط تراکنش و تگ (Many-to-Many)
        cursor.execute('''CREATE TABLE IF NOT EXISTS transaction_tags (
            transaction_id INTEGER,
            tag_id INTEGER,
            PRIMARY KEY (transaction_id, tag_id),
            FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )''')
        
        cursor.execute(f"PRAGMA user_version = {CURRENT_DB_VERSION};")

    # ارتقاء از نسخه ۴ به ۵: سیستم مدیریت انبار
    if cursor.execute("PRAGMA user_version;").fetchone()[0] == 4:
        # جدول کالاها
        cursor.execute('''CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            unit TEXT DEFAULT 'عدد',
            buy_price REAL DEFAULT 0,
            initial_stock REAL DEFAULT 0,
            current_stock REAL DEFAULT 0,
            min_stock REAL DEFAULT 0
        )''')
        
        # جدول تراکنش‌های انبار
        cursor.execute('''CREATE TABLE IF NOT EXISTS inventory_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER,
            item_id INTEGER,
            quantity REAL NOT NULL,
            unit_price REAL DEFAULT 0,
            type TEXT NOT NULL,
            FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
        )''')
        
        cursor.execute(f"PRAGMA user_version = {CURRENT_DB_VERSION};")

    # بررسی وجود ستون initial_stock در جدول items
    # این بررسی باید همیشه انجام شود چون ممکن است دیتابیس از بکاپ بازیابی شده باشد
    try:
        cursor.execute("SELECT * FROM items LIMIT 1")
        cols = [desc[0] for desc in cursor.description]
        if 'initial_stock' not in cols:
            cursor.execute("ALTER TABLE items ADD COLUMN initial_stock REAL DEFAULT 0")
            cursor.execute("UPDATE items SET initial_stock = current_stock WHERE initial_stock = 0 AND current_stock != 0")
            conn.commit()
            logger.info("ستون initial_stock به جدول items اضافه شد")
    except Exception as e:
        logger.warning(f"بررسی ستون initial_stock: {e}")
    
    conn.commit()
    conn.close()


# =========================================================================
# توابع بدهکار/بستانکار اشخاص
# =========================================================================
def get_entity_balance(entity_name):
    """محاسبه تراز مالی یک شخص
    
    منطق:
    - واریز = شخص پولی به ما داده = پول او دست ماست = شخص طلبکار (منفی)
    - برداشت = ما پولی به شخص داده‌ایم = پول ما دست اوست = شخص بدهکار (مثبت)
    - کالاهای انبار خروج = کالا به شخص تحویل شده = از طلب شخص کم می‌شود (مثبت)
    - کالاهای انبار ورود = کالا از شخص دریافت شده = طلب شخص زیاد می‌شود (منفی)
    
    مثبت = بدهکار (طلب ما از شخص) / منفی = بستانکار (طلب شخص از ما)
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, type, amount FROM transactions WHERE entity_name=?", (entity_name,))
    total_deposit = 0    # واریز = شخص طلبکار
    total_withdrawal = 0 # برداشت = شخص بدهکار
    tx_ids = []
    
    for row in cursor.fetchall():
        tx_id, tx_type, amount = row[0], row[1], float(row[2])
        tx_ids.append(tx_id)
        if tx_type == "واریز":
            total_deposit += amount
        elif tx_type == "برداشت":
            total_withdrawal += amount
    
    # محاسبه ارزش کالاهای انبار
    inv_entry_value = 0   # ورود کالا از شخص (شخص کالا داده → طلبش زیاد شده)
    inv_exit_value = 0    # خروج کالا به شخص (ما کالا دادیم → از طلبش کم شده)
    if tx_ids:
        placeholders = ','.join(['?' for _ in tx_ids])
        cursor.execute(f"""
            SELECT COALESCE(SUM(CASE WHEN it.type='entry' THEN it.quantity * it.unit_price ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN it.type='exit' THEN it.quantity * it.unit_price ELSE 0 END), 0)
            FROM inventory_transactions it 
            WHERE it.transaction_id IN ({placeholders})
        """, tx_ids)
        row = cursor.fetchone()
        if row:
            inv_entry_value = float(row[0])
            inv_exit_value = float(row[1])
    
    conn.close()
    
    # تراز = (پرداخت ما - دریافت ما) + (خروج کالا - ورود کالا)
    return (total_withdrawal - total_deposit) + (inv_exit_value - inv_entry_value)


def get_all_entities_balance():
    """دریافت لیست تمام اشخاص با ترازشان و ارزش انبار"""
    entities = get_all_entities()
    result = []
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    for name in entities:
        balance = get_entity_balance(name)
        # دریافت آخرین تراکنش
        cursor.execute("SELECT date, description FROM transactions WHERE entity_name=? ORDER BY id DESC LIMIT 1", (name,))
        last_tx = cursor.fetchone()
        last_date = last_tx[0] if last_tx else ""
        last_desc = last_tx[1] if last_tx else ""
        
        # محاسبه ارزش کل انبار شخص
        cursor.execute("""
            SELECT COALESCE(SUM(it.quantity * it.unit_price), 0)
            FROM inventory_transactions it
            JOIN transactions t ON it.transaction_id = t.id
            WHERE t.entity_name = ?
        """, (name,))
        inv_result = cursor.fetchone()
        inv_value = float(inv_result[0]) if inv_result and inv_result[0] else 0
        
        result.append((name, balance, last_date, last_desc, inv_value))
    conn.close()
    return result


def get_entity_transactions_detail(entity_name):
    """دریافت جزئیات تراکنش‌های یک شخص برای نمایش در تب تراز
    شامل اطلاعات کالاهای انبار"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, date, type, amount, description, account_name, category_name 
        FROM transactions WHERE entity_name=? ORDER BY date DESC, id DESC
    """, (entity_name,))
    txs = cursor.fetchall()
    
    # اضافه کردن اطلاعات انبار به هر تراکنش
    result = []
    for tx in txs:
        tx_id = tx[0]
        cursor.execute("""
            SELECT i.name, i.unit, it.quantity, it.unit_price, it.type
            FROM inventory_transactions it
            JOIN items i ON it.item_id = i.id
            WHERE it.transaction_id = ?
        """, (tx_id,))
        inventory_items = cursor.fetchall()
        inventory_text = ""
        inventory_value = 0
        if inventory_items:
            entry_items = []
            exit_items = []
            for item_name, unit, qty, price, inv_type in inventory_items:
                item_str = f"{item_name}({qty} {unit}×{price:,.0f})"
                if inv_type == "entry":
                    entry_items.append(item_str)
                else:
                    exit_items.append(item_str)
                inventory_value += qty * price
            parts = []
            if entry_items:
                parts.append("📥 ورود: " + ", ".join(entry_items))
            if exit_items:
                parts.append("📤 خروج: " + ", ".join(exit_items))
            inventory_text = "📦 " + " | ".join(parts)
        result.append(tx + (inventory_text, inventory_value))
    
    conn.close()
    return result


def get_entity_inventory_detail(entity_name):
    """دریافت تمام تراکنش‌های انبار مرتبط با یک شخص
    شامل ورود و خروج کالاها"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.date, i.name, i.unit, it.quantity, it.unit_price, it.type, t.description
        FROM inventory_transactions it
        JOIN items i ON it.item_id = i.id
        JOIN transactions t ON it.transaction_id = t.id
        WHERE t.entity_name = ?
        ORDER BY t.date DESC
    """, (entity_name,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def add_entity_settlement(entity_name, amount, description="تسویه حساب"):
    """ثبت تسویه حساب با یک شخص"""
    # اگر مبلغ مثبت باشد = شخص به ما پول داده (واریز)
    # اگر مبلغ منفی باشد = ما به شخص پول داده‌ایم (برداشت)
    if amount > 0:
        tx_type = "واریز"
    else:
        tx_type = "برداشت"
        amount = abs(amount)
    
    import jdatetime
    today = jdatetime.date.today().strftime("%Y/%m/%d")
    
    return add_transaction(
        date=today,
        t_type=tx_type,
        amount=amount,
        description=f"💳 {description}",
        account_name="",
        category_name="تسویه حساب",
        entity_name=entity_name,
        source="تسویه حساب",
        attachment=""
    )


def add_account(name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO accounts (name) VALUES (?)", (name,))
        conn.commit()
        success = True
    except sqlite3.IntegrityError: success = False
    conn.close()
    return success

def get_all_accounts():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM accounts")
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()
    return rows

def delete_account(name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM accounts WHERE name=?", (name,))
    conn.commit()
    conn.close()

def add_category(name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM categories WHERE name=?", (name,))
    if cursor.fetchone(): return False
    cursor.execute("INSERT INTO categories (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()
    return True

def get_all_categories():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM categories")
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()
    return rows

def delete_category(name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM categories WHERE name=?", (name,))
    conn.commit()
    conn.close()

def add_entity(name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM entities WHERE name=?", (name,))
    if cursor.fetchone(): return False
    cursor.execute("INSERT INTO entities (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()
    return True

def get_all_entities():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM entities")
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()
    return rows

def delete_entity(name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM entities WHERE name=?", (name,))
    conn.commit()
    conn.close()

def add_transaction(date, t_type, amount, desc, account, category, entity, source='دستی', attachment=''):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO transactions (date, type, amount, description, account_name, category_name, entity_name, source, attachment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (date, t_type, amount, desc, account, category, entity, source, attachment))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id

def update_transaction(tx_id, date, t_type, amount, desc, account, category, entity, attachment=''):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE transactions 
        SET date=?, type=?, amount=?, description=?, account_name=?, category_name=?, entity_name=?, attachment=?
        WHERE id=?
    ''', (date, t_type, amount, desc, account, category, entity, attachment, tx_id))
    conn.commit()
    conn.close()

def delete_transaction(tx_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
    conn.commit()
    conn.close()

def clear_all_transactions():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions")
    conn.commit()
    conn.close()

def get_all_transactions():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, date, type, account_name, category_name, entity_name, amount, description, source, attachment FROM transactions")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_filtered_transactions(t_type="همه", account="همه", category="همه", entity=""):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    query = "SELECT id, date, type, account_name, category_name, entity_name, amount, description, source, attachment FROM transactions WHERE 1=1"
    params = []
    
    if t_type != "همه":
        query += " AND type = ?"
        params.append(t_type)
    if account != "همه":
        query += " AND account_name = ?"
        params.append(account)
    if category != "همه":
        query += " AND category_name = ?"
        params.append(category)
    if entity.strip() != "":
        query += " AND entity_name LIKE ?"
        params.append(f"%{entity.strip()}%")
        
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_person_transactions(person_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, date, type, account_name, category_name, entity_name, amount, description, source, attachment FROM transactions WHERE entity_name LIKE ?", (f"%{person_name}%",))
    rows = cursor.fetchall()
    conn.close()
    return rows

def cleanup_unused_definitions():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM accounts WHERE name NOT IN (SELECT DISTINCT account_name FROM transactions WHERE account_name IS NOT NULL)")
    cursor.execute("DELETE FROM categories WHERE name NOT IN (SELECT DISTINCT category_name FROM transactions WHERE category_name IS NOT NULL)")
    cursor.execute("DELETE FROM entities WHERE name NOT IN (SELECT DISTINCT entity_name FROM transactions WHERE entity_name IS NOT NULL)")
    conn.commit()
    conn.close()

def get_transaction_by_id(tx_id):
    """دریافت یک تراکنش خاص بر اساس شناسه - کارآمدتر از جستجو در کل جدول"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, date, type, account_name, category_name, entity_name, amount, description, source, attachment FROM transactions WHERE id=?", (tx_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def is_duplicate_transaction(date, t_type, amount, desc, account, category, entity):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id FROM transactions 
        WHERE date=? AND type=? AND amount=? AND description=? 
        AND account_name=? AND category_name=? AND entity_name=?
    ''', (date, t_type, amount, desc, account, category, entity))
    result = cursor.fetchone()
    conn.close()
    return result is not None


# =========================================================================
# توابع مربوط به دسته‌بندی سلسله مراتبی
# =========================================================================

def add_subcategory(parent_name, sub_name):
    """افزودن زیردسته برای یک دسته‌بندی اصلی"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        # پیدا کردن ID دسته والد
        cursor.execute("SELECT id FROM categories WHERE name=? AND parent_id IS NULL", (parent_name,))
        parent = cursor.fetchone()
        if not parent:
            logger.warning(f"دسته والد '{parent_name}' یافت نشد")
            conn.close()
            return False
        parent_id = parent[0]
        
        # بررسی تکراری نبودن زیردسته در همان والد
        cursor.execute("SELECT id FROM categories WHERE name=? AND parent_id=?", (sub_name, parent_id))
        if cursor.fetchone():
            conn.close()
            return False
        
        cursor.execute("INSERT INTO categories (name, parent_id) VALUES (?, ?)", (sub_name, parent_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"خطا در افزودن زیردسته: {e}")
        conn.close()
        return False

def get_parent_categories():
    """دریافت لیست دسته‌بندی‌های اصلی (بدون زیردسته)"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM categories WHERE parent_id IS NULL")
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()
    return rows

def get_subcategories(parent_name):
    """دریافت زیردسته‌های یک دسته اصلی"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c2.name FROM categories c1 
        JOIN categories c2 ON c2.parent_id = c1.id 
        WHERE c1.name = ?
    """, (parent_name,))
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()
    return rows

def get_all_categories_hierarchical():
    """دریافت تمام دسته‌بندی‌ها به صورت سلسله مراتبی: {والد: [زیردسته‌ها]}"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, parent_id FROM categories ORDER BY parent_id, name")
    all_cats = cursor.fetchall()
    conn.close()
    
    result = {}
    for cat_id, name, parent_id in all_cats:
        if parent_id is None:
            if name not in result:
                result[name] = []
        else:
            # پیدا کردن نام والد
            parent_name = next((c[1] for c in all_cats if c[0] == parent_id), "نامشخص")
            if parent_name not in result:
                result[parent_name] = []
            result[parent_name].append(name)
    return result

def get_all_categories_flat():
    """دریافت تمام دسته‌بندی‌ها (والد + زیردسته) به صورت تخت"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c1.name, c2.name FROM categories c1 
        LEFT JOIN categories c2 ON c2.parent_id = c1.id 
        WHERE c1.parent_id IS NULL
        ORDER BY c1.name
    """)
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for parent, sub in rows:
        result.append(parent)
        if sub:
            result.append(f"  └ {sub}")  # نمایش زیردسته با تورفتگی
    return result

def delete_category_full(name):
    """حذف دسته‌بندی و تمام زیردسته‌های آن"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM categories WHERE name=?", (name,))
    conn.commit()
    conn.close()


# =========================================================================
# توابع مربوط به تگ‌ها
# =========================================================================

def add_tag(name):
    """افزودن تگ جدید"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO tags (name) VALUES (?)", (name.strip(),))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def get_all_tags():
    """دریافت تمام تگ‌ها"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM tags ORDER BY name")
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()
    return rows

def delete_tag(name):
    """حذف تگ و تمام ارتباطات آن"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM tags WHERE name=?", (name,))
    tag = cursor.fetchone()
    if tag:
        cursor.execute("DELETE FROM transaction_tags WHERE tag_id=?", (tag[0],))
        cursor.execute("DELETE FROM tags WHERE id=?", (tag[0],))
        conn.commit()
    conn.close()

def set_transaction_tags(tx_id, tag_names):
    """تنظیم تگ‌های یک تراکنش (جایگزینی کامل)"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # حذف تگ‌های قبلی
    cursor.execute("DELETE FROM transaction_tags WHERE transaction_id=?", (tx_id,))
    # اضافه کردن تگ‌های جدید
    for tag_name in tag_names:
        tag_name = tag_name.strip()
        if not tag_name:
            continue
        cursor.execute("SELECT id FROM tags WHERE name=?", (tag_name,))
        tag = cursor.fetchone()
        if tag:
            cursor.execute("INSERT OR IGNORE INTO transaction_tags (transaction_id, tag_id) VALUES (?, ?)", (tx_id, tag[0]))
        else:
            # ایجاد خودکار تگ جدید
            cursor.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
            new_tag_id = cursor.lastrowid
            cursor.execute("INSERT INTO transaction_tags (transaction_id, tag_id) VALUES (?, ?)", (tx_id, new_tag_id))
    conn.commit()
    conn.close()

def get_transaction_tags(tx_id):
    """دریافت تگ‌های یک تراکنش"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.name FROM tags t 
        JOIN transaction_tags tt ON t.id = tt.tag_id 
        WHERE tt.transaction_id = ?
    """, (tx_id,))
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()
    return rows

def get_transactions_by_tag(tag_name):
    """دریافت تمام تراکنش‌های دارای یک تگ خاص"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tx.id, tx.date, tx.type, tx.account_name, tx.category_name, 
               tx.entity_name, tx.amount, tx.description, tx.source, tx.attachment 
        FROM transactions tx
        JOIN transaction_tags tt ON tx.id = tt.transaction_id
        JOIN tags t ON tt.tag_id = t.id
        WHERE t.name = ?
    """, (tag_name,))
    rows = cursor.fetchall()
    conn.close()
    return rows


# =========================================================================
# توابع مدیریت انبار (Inventory)
# =========================================================================

def add_item(name, unit="عدد", buy_price=0, initial_stock=0, current_stock=None, min_stock=0):
    """افزودن کالای جدید"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        if current_stock is None:
            current_stock = initial_stock
        cursor.execute("INSERT INTO items (name, unit, buy_price, initial_stock, current_stock, min_stock) VALUES (?, ?, ?, ?, ?, ?)",
                       (name, unit, buy_price, initial_stock, current_stock, min_stock))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def update_item(item_id, name, unit, buy_price, initial_stock, current_stock, min_stock):
    """بروزرسانی اطلاعات کالا
    اگر موجودی اولیه تغییر کند، موجودی فعلی نیز به همان میزان تغییر می‌کند"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # خواندن موجودی اولیه فعلی
    cursor.execute("SELECT initial_stock, current_stock FROM items WHERE id=?", (item_id,))
    old = cursor.fetchone()
    if old:
        old_initial = old[0] if old[0] else 0
        old_current = old[1] if old[1] else 0
        # محاسبه تغییر موجودی اولیه
        diff = initial_stock - old_initial
        # اعمال تغییر روی موجودی فعلی
        new_current = old_current + diff
        cursor.execute("UPDATE items SET name=?, unit=?, buy_price=?, initial_stock=?, current_stock=?, min_stock=? WHERE id=?",
                       (name, unit, buy_price, initial_stock, new_current, min_stock, item_id))
    else:
        cursor.execute("UPDATE items SET name=?, unit=?, buy_price=?, initial_stock=?, current_stock=?, min_stock=? WHERE id=?",
                       (name, unit, buy_price, initial_stock, current_stock, min_stock, item_id))
    conn.commit()
    conn.close()

def delete_item(item_id):
    """حذف کالا"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()

def get_all_items():
    """دریافت تمام کالاها"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, unit, buy_price, initial_stock, current_stock, min_stock FROM items ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_item_names():
    """دریافت نام تمام کالاها"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM items ORDER BY name")
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()
    return rows

def get_item_by_name(name):
    """دریافت کالا بر اساس نام"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, unit, buy_price, initial_stock, current_stock, min_stock FROM items WHERE name=?", (name,))
    row = cursor.fetchone()
    conn.close()
    return row

def add_inventory_transaction(transaction_id, item_id, quantity, unit_price, tx_type):
    """ثبت تراکنش انبار (entry یا exit)"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO inventory_transactions (transaction_id, item_id, quantity, unit_price, type) VALUES (?, ?, ?, ?, ?)",
                   (transaction_id, item_id, quantity, unit_price, tx_type))
    # بروزرسانی موجودی کالا
    item = cursor.execute("SELECT current_stock, buy_price FROM items WHERE id=?", (item_id,)).fetchone()
    if item:
        if tx_type == "entry":
            new_stock = item[0] + quantity
            # محاسبه میانگین قیمت خرید
            total_old = item[0] * item[1]
            total_new = quantity * unit_price
            if new_stock > 0:
                avg_price = (total_old + total_new) / new_stock
            else:
                avg_price = unit_price
            cursor.execute("UPDATE items SET current_stock=?, buy_price=? WHERE id=?", (new_stock, avg_price, item_id))
        elif tx_type == "exit":
            new_stock = item[0] - quantity  # اجازه منفی شدن موجودی
            cursor.execute("UPDATE items SET current_stock=? WHERE id=?", (new_stock, item_id))
    conn.commit()
    conn.close()

def get_inventory_transactions(transaction_id=None):
    """دریافت تراکنش‌های انبار"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if transaction_id:
        cursor.execute("""
            SELECT it.id, it.transaction_id, i.name, i.unit, it.quantity, it.unit_price, it.type
            FROM inventory_transactions it
            JOIN items i ON it.item_id = i.id
            WHERE it.transaction_id = ?
        """, (transaction_id,))
    else:
        cursor.execute("""
            SELECT it.id, it.transaction_id, i.name, i.unit, it.quantity, it.unit_price, it.type
            FROM inventory_transactions it
            JOIN items i ON it.item_id = i.id
            ORDER BY it.id DESC
        """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_inventory_for_transaction(transaction_id):
    """حذف تراکنش‌های انبار مرتبط با یک تراکنش مالی"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # برگرداندن موجودی قبل از حذف
    inv_txs = cursor.execute(
        "SELECT item_id, quantity, type FROM inventory_transactions WHERE transaction_id=?",
        (transaction_id,)
    ).fetchall()
    for item_id, quantity, tx_type in inv_txs:
        item = cursor.execute("SELECT current_stock FROM items WHERE id=?", (item_id,)).fetchone()
        if item:
            if tx_type == "entry":
                new_stock = max(0, item[0] - quantity)
            else:
                new_stock = item[0] + quantity
            cursor.execute("UPDATE items SET current_stock=? WHERE id=?", (new_stock, item_id))
    cursor.execute("DELETE FROM inventory_transactions WHERE transaction_id=?", (transaction_id,))
    conn.commit()
    conn.close()

def get_low_stock_items():
    """دریافت کالاهای زیر حداقل موجودی"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, unit, buy_price, current_stock, min_stock FROM items WHERE current_stock <= min_stock AND min_stock > 0")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_inventory_report(item_name=None, tx_type=None):
    """دریافت گزارش تاریخچه انبار با فیلتر"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    query = """
        SELECT it.id, t.date, i.name, i.unit, it.quantity, it.unit_price, 
               it.type, t.entity_name, t.description
        FROM inventory_transactions it
        JOIN items i ON it.item_id = i.id
        JOIN transactions t ON it.transaction_id = t.id
        WHERE 1=1
    """
    params = []
    if item_name and item_name != "همه":
        query += " AND i.name = ?"
        params.append(item_name)
    if tx_type and tx_type != "همه":
        query += " AND it.type = ?"
        params.append(tx_type)
    query += " ORDER BY t.date DESC, it.id DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return rows
