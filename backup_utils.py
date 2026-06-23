import json
import shutil
import os
import logging
from datetime import datetime
import database

logger = logging.getLogger(__name__)

# =========================================================================
# بکاپ کامل دیتابیس (کپی مستقیم فایل)
# =========================================================================

def backup_full_database(filepath=None):
    """کپی کامل فایل دیتابیس"""
    if filepath is None:
        os.makedirs("backup", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = f"backup/FullBackup_{timestamp}.db"
    
    try:
        shutil.copy2(database.DB_NAME, filepath)
        logger.info(f"بکاپ کامل دیتابیس ذخیره شد: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"خطا در بکاپ کامل دیتابیس: {e}")
        return None

def restore_full_database(filepath):
    """بازیابی کامل دیتابیس از فایل بکاپ"""
    try:
        if not os.path.exists(filepath):
            return False, "فایل بکاپ یافت نشد"
        
        # ساخت بکاپ از وضعیت فعلی قبل از بازیابی
        safety_backup = backup_full_database()
        
        shutil.copy2(filepath, database.DB_NAME)
        logger.info(f"بازیابی کامل دیتابیس انجام شد: {filepath}")
        return True, f"بازیابی موفق. بکاپ امنیتی: {safety_backup}"
    except Exception as e:
        logger.error(f"خطا در بازیابی دیتابیس: {e}")
        return False, str(e)


# =========================================================================
# بکاپ JSON تعاریف (بهبود یافته با پشتیبانی از انبار)
# =========================================================================

def backup_definitions(filepath):
    data = {
        "version": 2,
        "backup_type": "definitions",
        "date": datetime.now().strftime("%Y/%m/%d %H:%M"),
        "accounts": database.get_all_accounts(),
        "categories": database.get_all_categories(),
        "categories_hierarchical": database.get_all_categories_hierarchical(),
        "entities": database.get_all_entities(),
        "tags": database.get_all_tags(),
        # اضافه شدن کالاهای انبار
        "items": []
    }
    
    # ذخیره اطلاعات کالاها
    items = database.get_all_items()
    for item in items:
        data["items"].append({
            "id": item[0], "name": item[1], "unit": item[2],
            "buy_price": item[3], "current_stock": item[4], "min_stock": item[5]
        })
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    return True

def restore_definitions(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    count = 0
    for acc in data.get("accounts", []):
        if database.add_account(acc): count += 1
    for cat in data.get("categories", []):
        if database.add_category(cat): count += 1
    for ent in data.get("entities", []):
        if database.add_entity(ent): count += 1
    for tag in data.get("tags", []):
        if database.add_tag(tag): count += 1
    
    # بازیابی دسته‌بندی‌های سلسله مراتبی
    for parent, subs in data.get("categories_hierarchical", {}).items():
        if parent not in database.get_all_categories():
            database.add_category(parent)
        for sub in subs:
            database.add_subcategory(parent, sub)
            count += 1
    
    # بازیابی کالاهای انبار
    for item in data.get("items", []):
        if database.add_item(item["name"], item.get("unit", "عدد"), 
                            item.get("buy_price", 0), item.get("current_stock", 0), 
                            item.get("min_stock", 0)):
            count += 1
    
    return count


# =========================================================================
# بکاپ JSON تراکنش‌ها (بهبود یافته با ریستور امن تگ‌ها و انبار)
# =========================================================================

def backup_transactions(filepath):
    txs = database.get_all_transactions()
    tx_list = []
    for tx in txs:
        tx_id = tx[0]
        tags = database.get_transaction_tags(tx_id)
        inv_txs = database.get_inventory_transactions(tx_id)
        inv_data = []
        for inv in inv_txs:
            inv_data.append({
                "item_name": inv[2], "unit": inv[3], "quantity": inv[4],
                "unit_price": inv[5], "type": inv[6]
            })
        tx_list.append({
            "date": tx[1], "type": tx[2], "account": tx[3], 
            "category": tx[4], "entity": tx[5], "amount": tx[6], 
            "description": tx[7], "source": tx[8],
            "attachment": tx[9] if len(tx) > 9 else "",
            "tags": tags,
            "inventory": inv_data
        })
    
    backup_data = {
        "version": 2,
        "backup_type": "transactions",
        "date": datetime.now().strftime("%Y/%m/%d %H:%M"),
        "count": len(tx_list),
        "transactions": tx_list
    }
        
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=4)
    return len(tx_list)

def restore_transactions(filepath, replace_existing=False):
    with open(filepath, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
    
    # سازگاری با فرمت قدیم و جدید
    if isinstance(raw_data, dict):
        txs = raw_data.get("transactions", [])
    else:
        txs = raw_data  # فرمت قدیم (لیست ساده)
        
    if replace_existing:
        database.clear_all_transactions()
        
    count = 0
    for tx in txs:
        acc, cat, ent = tx.get("account", ""), tx.get("category", ""), tx.get("entity", "")
        if acc and acc not in database.get_all_accounts(): database.add_account(acc)
        if cat and cat not in database.get_all_categories(): database.add_category(cat)
        if ent and ent not in database.get_all_entities(): database.add_entity(ent)
            
        new_id = database.add_transaction(
            tx.get("date", ""), tx.get("type", ""), tx.get("amount", 0.0), 
            tx.get("description", ""), acc, cat, ent, 
            tx.get("source", "بازیابی بکاپ"),
            tx.get("attachment", "")
        )
        
        # بازیابی تگ‌ها با ID واقعی تراکنش
        tags = tx.get("tags", [])
        if tags and new_id:
            database.set_transaction_tags(new_id, tags)
        
        # بازیابی تراکنش‌های انبار
        inv_list = tx.get("inventory", [])
        for inv in inv_list:
            item = database.get_item_by_name(inv.get("item_name", ""))
            if item and new_id:
                database.add_inventory_transaction(
                    new_id, item[0], inv.get("quantity", 0),
                    inv.get("unit_price", 0), inv.get("type", "entry")
                )
        
        count += 1
    return count


# =========================================================================
# بکاپ خودکار
# =========================================================================

def auto_backup_if_needed(settings):
    """بررسی و اجرای بکاپ خودکار در صورت نیاز"""
    auto_enabled = settings.value("auto_backup_enabled", False, type=bool)
    if not auto_enabled:
        return
    
    last_auto = settings.value("last_auto_backup", "")
    now = datetime.now()
    
    # بررسی اینکه آیا هفته گذشته یا نه
    try:
        if last_auto:
            last_date = datetime.strptime(last_auto, "%Y/%m/%d %H:%M")
            days_passed = (now - last_date).days
            if days_passed < 7:
                return
    except ValueError:
        pass
    
    # اجرای بکاپ خودکار
    try:
        os.makedirs("backup", exist_ok=True)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        filepath = f"backup/AutoBackup_{timestamp}.db"
        result = backup_full_database(filepath)
        if result:
            settings.setValue("last_auto_backup", now.strftime("%Y/%m/%d %H:%M"))
            logger.info(f"بکاپ خودکار انجام شد: {filepath}")
            
            # حذف بکاپ‌های قدیمی‌تر از ۳۰ روز
            cleanup_old_backups("backup", days=30)
    except Exception as e:
        logger.error(f"خطا در بکاپ خودکار: {e}")

def cleanup_old_backups(backup_dir="backup", days=30):
    """حذف فایل‌های بکاپ قدیمی‌تر از تعداد روز مشخص"""
    if not os.path.exists(backup_dir):
        return
    
    now = datetime.now()
    for filename in os.listdir(backup_dir):
        filepath = os.path.join(backup_dir, filename)
        if os.path.isfile(filepath):
            try:
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                if (now - file_time).days > days:
                    os.remove(filepath)
                    logger.info(f"بکاپ قدیمی حذف شد: {filename}")
            except Exception:
                pass

def get_backup_info(filepath):
    """دریافت اطلاعات یک فایل بکاپ"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, dict):
            return {
                "version": data.get("version", "?"),
                "type": data.get("backup_type", "نامشخص"),
                "date": data.get("date", "نامشخص"),
                "count": data.get("count", len(data.get("transactions", [])))
            }
        else:
            return {"version": 1, "type": "تراکنش‌ها (قدیم)", "date": "نامشخص", "count": len(data)}
    except Exception:
        return None