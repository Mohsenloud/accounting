"""
نرم‌افزار حسابداری شخصی - نسخه Flask
"""
import os
import uuid
import shutil
import logging
import jdatetime
from flask import (Flask, render_template, request, redirect, url_for, 
                   flash, send_file, jsonify, session)
from werkzeug.utils import secure_filename
import database
import backup_utils
import export_utils
from functools import wraps

# تنظیم لاگینگ
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'hesabdari-secret-key-2024'

# رمز عبور برنامه
APP_PASSWORD = '1234'

def login_required(f):
    """محافظت از صفحات با رمز عبور"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'attachments')

# ایجاد پوشه attachments اگر وجود نداشت
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('backup', exist_ok=True)

# راه‌اندازی دیتابیس (بعد از رمزگشایی)
database.init_db()

HEADERS = ["تاریخ", "نوع تراکنش", "حساب/صندوق", "دسته‌بندی", "شخص / محل", "مبلغ (ریال/تومان)", "توضیحات", "منبع", "تگ‌ها"]

@app.context_processor
def inject_globals():
    """تزریق متغیرهای سراسری به تمام قالب‌ها"""
    try:
        txs = database.get_all_transactions()
        today = jdatetime.date.today()
        total_v = total_b = today_v = today_b = month_v = month_b = 0
        
        for tx in txs:
            t_type, amount = tx[2], float(tx[6])
            if t_type == "واریز":
                total_v += amount
            elif t_type == "برداشت":
                total_b += amount
            
            try:
                parts = str(tx[1]).strip().split('/')
                if len(parts) == 3:
                    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    if y == today.year and m == today.month:
                        if t_type == "واریز":
                            month_v += amount
                        elif t_type == "برداشت":
                            month_b += amount
                    if y == today.year and m == today.month and d == today.day:
                        if t_type == "واریز":
                            today_v += amount
                        elif t_type == "برداشت":
                            today_b += amount
            except (ValueError, IndexError):
                pass
        
        return {
            'today_balance': today_v - today_b,
            'month_balance': month_v - month_b,
            'total_balance': total_v - total_b,
            'today_v': today_v,
            'today_b': today_b,
            'current_time': jdatetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S'),
            'headers': HEADERS
        }
    except Exception as e:
        logger.error(f"خطا در محاسبه وضعیت مالی: {e}")
        return {'today_balance': 0, 'month_balance': 0, 'total_balance': 0, 'today_v': 0, 'today_b': 0, 'current_time': '', 'headers': HEADERS}


# =====================================================================
# صفحه اصلی - مدیریت تراکنش‌ها
# =====================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == APP_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        return render_template('login.html', error='رمز عبور اشتباه است.')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    txs = database.get_all_transactions()
    tx_list = []
    for tx in txs:
        tags = database.get_transaction_tags(tx[0])
        tx_list.append({
            'id': tx[0], 'date': tx[1], 'type': tx[2], 'account': tx[3],
            'category': tx[4], 'entity': tx[5], 'amount': float(tx[6]),
            'description': tx[7], 'source': tx[8], 'attachment': tx[9] if len(tx) > 9 else '',
            'tags': tags
        })
    
    accounts = database.get_all_accounts()
    categories = database.get_all_categories_hierarchical()
    entities = database.get_all_entities()
    tags = database.get_all_tags()
    items = database.get_item_names()
    
    return render_template('transactions.html', transactions=tx_list, 
                         accounts=accounts, categories=categories, entities=entities,
                         tags=tags, items=items)


@app.route('/transaction/add', methods=['POST'])
@login_required
def add_transaction():
    date = request.form.get('date', '').strip()
    t_type = request.form.get('type', '').strip()
    amount = request.form.get('amount', '0').replace(',', '').strip()
    description = request.form.get('description', '').strip()
    account = request.form.get('account', '').strip()
    category = request.form.get('category', '').strip()
    entity = request.form.get('entity', '').strip()
    tags_str = request.form.get('tags', '').strip()
    
    if not all([date, t_type, amount, entity]):
        flash('اطلاعات ناقص است.', 'error')
        return redirect(url_for('index'))
    
    try:
        amount = abs(float(amount))
    except ValueError:
        flash('مبلغ نامعتبر است.', 'error')
        return redirect(url_for('index'))
    
    # ذخیره فایل ضمیمه
    attachment = ''
    if 'attachment' in request.files:
        file = request.files['attachment']
        if file.filename:
            ext = os.path.splitext(secure_filename(file.filename))[1]
            new_filename = f"{uuid.uuid4().hex}{ext}"
            attachment = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
            file.save(attachment)
    
    # ایجاد خودکار تعاریف جدید
    if account and account not in database.get_all_accounts():
        database.add_account(account)
    if category and category not in database.get_all_categories():
        database.add_category(category)
    if entity and entity not in database.get_all_entities():
        database.add_entity(entity)
    
    new_id = database.add_transaction(date, t_type, amount, description, account, category, entity, 'دستی', attachment)
    
    # ذخیره تگ‌ها
    if tags_str:
        tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
        database.set_transaction_tags(new_id, tags_list)
    
    # پردازش انبار
    inv_enabled = request.form.get('inv_enabled') == 'on'
    if inv_enabled:
        inv_type = "entry" if t_type == "برداشت" else "exit"
        inv_items = request.form.getlist('inv_item_name[]')
        inv_qtys = request.form.getlist('inv_quantity[]')
        inv_prices = request.form.getlist('inv_price[]')
        
        for inv_name, inv_qty, inv_price in zip(inv_items, inv_qtys, inv_prices):
            try:
                qty = float(inv_qty)
                price = float(inv_price.replace(',', ''))
                item = database.get_item_by_name(inv_name.strip())
                if item:
                    database.add_inventory_transaction(new_id, item[0], qty, price, inv_type)
            except (ValueError, IndexError):
                pass
    
    flash('تراکنش با موفقیت ثبت شد.', 'success')
    return redirect(url_for('index'))


@app.route('/transaction/edit/<int:tx_id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(tx_id):
    # در حالت GET: نمایش فرم ویرایش
    if request.method == 'GET':
        tx_data = database.get_transaction_by_id(tx_id)
        if not tx_data:
            flash('تراکنش یافت نشد.', 'error')
            return redirect(url_for('index'))
        
        tags = database.get_transaction_tags(tx_id)
        inv_txs = database.get_inventory_transactions(tx_id)
        
        tx = {
            'id': tx_data[0], 'date': tx_data[1], 'type': tx_data[2], 'account': tx_data[3],
            'category': tx_data[4], 'entity': tx_data[5], 'amount': float(tx_data[6]),
            'description': tx_data[7], 'source': tx_data[8], 
            'attachment': tx_data[9] if len(tx_data) > 9 else '',
            'tags': tags
        }
        
        inv_items_list = []
        for it in inv_txs:
            inv_items_list.append({'name': str(it[2]), 'quantity': float(it[4]), 'unit_price': float(it[5])})
        
        accounts = database.get_all_accounts()
        categories = database.get_all_categories_hierarchical()
        entities = database.get_all_entities()
        all_tags = database.get_all_tags()
        items = database.get_item_names()
        units = ["عدد", "کیلوگرم", "گرم", "لیتر", "متر", "بسته", "جعبه", "تن", "سانتی‌متر"]
        
        return render_template('edit_transaction.html', tx=tx, inv_items=inv_items_list,
                             accounts=accounts, categories=categories, entities=entities,
                             tags=all_tags, items=items, units=units)
    
    # در ح POST: ذخیره تغییرات
    date = request.form.get('date', '').strip()
    t_type = request.form.get('type', '').strip()
    amount = request.form.get('amount', '0').replace(',', '').strip()
    description = request.form.get('description', '').strip()
    account = request.form.get('account', '').strip()
    category = request.form.get('category', '').strip()
    entity = request.form.get('entity', '').strip()
    tags_str = request.form.get('tags', '').strip()
    
    try:
        amount = abs(float(amount))
    except ValueError:
        flash('مبلغ نامعتبر است.', 'error')
        return redirect(url_for('index'))
    
    # ذخیره فایل ضمیمه جدید
    attachment = request.form.get('existing_attachment', '')
    if 'attachment' in request.files:
        file = request.files['attachment']
        if file.filename:
            ext = os.path.splitext(secure_filename(file.filename))[1]
            new_filename = f"{uuid.uuid4().hex}{ext}"
            attachment = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
            file.save(attachment)
    
    # ایجاد خودکار تعاریف جدید
    if account and account not in database.get_all_accounts():
        database.add_account(account)
    if category and category not in database.get_all_categories():
        database.add_category(category)
    if entity and entity not in database.get_all_entities():
        database.add_entity(entity)
    
    database.update_transaction(tx_id, date, t_type, amount, description, account, category, entity, attachment)
    
    # بروزرسانی تگ‌ها
    if tags_str:
        tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
        database.set_transaction_tags(tx_id, tags_list)
    else:
        database.set_transaction_tags(tx_id, [])
    
    # بروزرسانی انبار
    database.delete_inventory_for_transaction(tx_id)
    inv_enabled = request.form.get('inv_enabled') == 'on'
    if inv_enabled:
        inv_type = "entry" if t_type == "برداشت" else "exit"
        inv_items = request.form.getlist('inv_item_name[]')
        inv_qtys = request.form.getlist('inv_quantity[]')
        inv_prices = request.form.getlist('inv_price[]')
        
        for inv_name, inv_qty, inv_price in zip(inv_items, inv_qtys, inv_prices):
            try:
                qty = float(inv_qty)
                price = float(inv_price.replace(',', ''))
                item = database.get_item_by_name(inv_name.strip())
                if item:
                    database.add_inventory_transaction(tx_id, item[0], qty, price, inv_type)
            except (ValueError, IndexError):
                pass
    
    database.cleanup_unused_definitions()
    flash('تراکنش با موفقیت ویرایش شد.', 'success')
    return redirect(url_for('index'))


@app.route('/transaction/delete/<int:tx_id>', methods=['POST'])
@login_required
def delete_transaction(tx_id):
    database.delete_inventory_for_transaction(tx_id)
    database.delete_transaction(tx_id)
    database.cleanup_unused_definitions()
    flash('تراکنش حذف شد.', 'success')
    return redirect(url_for('index'))


@app.route('/attachment/<path:filename>')
@login_required
def view_attachment(filename):
    return send_file(filename, as_attachment=False)


# =====================================================================
# گزارش پیشرفته
# =====================================================================

@app.route('/report')
@login_required
def report():
    t_type = request.args.get('type', 'همه')
    account = request.args.get('account', 'همه')
    category = request.args.get('category', 'همه')
    entity = request.args.get('entity', '')
    tag = request.args.get('tag', 'همه')
    
    if tag != 'همه' and tag:
        txs_by_tag = database.get_transactions_by_tag(tag)
        tx_ids_by_tag = {tx[0] for tx in txs_by_tag}
        all_txs = database.get_filtered_transactions(t_type, account, category, entity)
        txs = [tx for tx in all_txs if tx[0] in tx_ids_by_tag]
    else:
        txs = database.get_filtered_transactions(t_type, account, category, entity)
    
    tx_list = []
    total_v = total_b = 0
    for tx in txs:
        tags = database.get_transaction_tags(tx[0])
        if tx[2] == "واریز":
            total_v += float(tx[6])
        elif tx[2] == "برداشت":
            total_b += float(tx[6])
        tx_list.append({
            'id': tx[0], 'date': tx[1], 'type': tx[2], 'account': tx[3],
            'category': tx[4], 'entity': tx[5], 'amount': float(tx[6]),
            'description': tx[7], 'source': tx[8], 'tags': tags
        })
    
    accounts = database.get_all_accounts()
    categories = database.get_all_categories_hierarchical()
    all_tags = database.get_all_tags()
    
    return render_template('report.html', transactions=tx_list,
                         accounts=accounts, categories=categories, tags=all_tags,
                         selected_type=t_type, selected_account=account, 
                         selected_category=category, selected_entity=entity, selected_tag=tag,
                         total_v=total_v, total_b=total_b)


@app.route('/report/export')
@login_required
def export_report():
    t_type = request.args.get('type', 'همه')
    account = request.args.get('account', 'همه')
    category = request.args.get('category', 'همه')
    entity = request.args.get('entity', '')
    tag = request.args.get('tag', 'همه')
    
    if tag != 'همه' and tag:
        txs_by_tag = database.get_transactions_by_tag(tag)
        tx_ids_by_tag = {tx[0] for tx in txs_by_tag}
        all_txs = database.get_filtered_transactions(t_type, account, category, entity)
        txs = [tx for tx in all_txs if tx[0] in tx_ids_by_tag]
    else:
        txs = database.get_filtered_transactions(t_type, account, category, entity)
    
    if not txs:
        flash('هیچ داده‌ای برای خروجی وجود ندارد.', 'error')
        return redirect(url_for('report'))
    
    export_data = []
    for tx in txs:
        tags = database.get_transaction_tags(tx[0])
        row = list(tx[1:9]) + [", ".join(tags)]
        export_data.append(row)
    
    filepath = os.path.join('backup', 'report_export.xlsx')
    if export_utils.export_to_excel(export_data, filepath):
        return send_file(filepath, as_attachment=True, download_name='گزارش_پیشرفته.xlsx')
    
    flash('خطا در ایجاد فایل خروجی.', 'error')
    return redirect(url_for('report'))


# =====================================================================
# گزارش اشخاص
# =====================================================================

@app.route('/person_report')
@login_required
def person_report():
    person = request.args.get('person', '')
    txs = []
    total_v = total_b = 0
    
    if person:
        txs_raw = database.get_person_transactions(person)
        for tx in txs_raw:
            tags = database.get_transaction_tags(tx[0])
            if tx[2] == "واریز":
                total_v += float(tx[6])
            elif tx[2] == "برداشت":
                total_b += float(tx[6])
            txs.append({
                'id': tx[0], 'date': tx[1], 'type': tx[2], 'account': tx[3],
                'category': tx[4], 'entity': tx[5], 'amount': float(tx[6]),
                'description': tx[7], 'source': tx[8], 'tags': tags
            })
    
    entities = database.get_all_entities()
    return render_template('person_report.html', transactions=txs, entities=entities,
                         selected_person=person, total_v=total_v, total_b=total_b)


# =====================================================================
# تراز مالی اشخاص
# =====================================================================

@app.route('/entity_balance')
@login_required
def entity_balance():
    entities_data = database.get_all_entities_balance()
    entities_list = []
    total_debt = total_credit = debtor_count = creditor_count = 0
    
    for name, balance, last_date, last_desc, inv_value in entities_data:
        if balance > 0:
            status = "بدهکار"
            debtor_count += 1
            total_debt += balance
        elif balance < 0:
            status = "بستانکار"
            creditor_count += 1
            total_credit += abs(balance)
        else:
            status = "تسویه"
        
        entities_list.append({
            'name': name, 'balance': balance, 'abs_balance': abs(balance),
            'status': status, 'last_date': last_date, 'last_desc': last_desc,
            'inv_value': inv_value
        })
    
    return render_template('entity_balance.html', entities=entities_list,
                         debtor_count=debtor_count, creditor_count=creditor_count,
                         total_debt=total_debt, total_credit=total_credit,
                         all_entities=[e[0] for e in entities_data])


@app.route('/entity_balance/detail/<name>')
@login_required
def entity_detail(name):
    txs = database.get_entity_transactions_detail(name)
    balance = database.get_entity_balance(name)
    inv_txs = database.get_entity_inventory_detail(name)
    
    tx_list = []
    for tx in txs:
        tx_list.append({
            'id': tx[0], 'date': tx[1], 'type': tx[2], 'amount': float(tx[3]),
            'description': tx[4], 'account': tx[5], 'category': tx[6],
            'inventory_text': tx[7] if len(tx) > 7 else '',
            'inventory_value': tx[8] if len(tx) > 8 else 0
        })
    
    inv_list = []
    for inv in inv_txs:
        inv_list.append({
            'date': inv[0], 'item_name': inv[1], 'unit': inv[2],
            'quantity': inv[3], 'unit_price': inv[4], 'type': inv[5],
            'description': inv[6]
        })
    
    return jsonify({
        'balance': balance,
        'transactions': tx_list,
        'inventory': inv_list
    })


@app.route('/entity_balance/settle', methods=['POST'])
@login_required
def entity_settle():
    entity_name = request.form.get('entity', '').strip()
    amount_str = request.form.get('amount', '').strip().replace(',', '')
    desc = request.form.get('description', 'تسویه حساب').strip()
    
    if not entity_name:
        flash('نام شخص را انتخاب کنید.', 'error')
        return redirect(url_for('entity_balance'))
    
    try:
        amount = float(amount_str)
    except ValueError:
        flash('مبلغ نامعتبر است.', 'error')
        return redirect(url_for('entity_balance'))
    
    if amount == 0:
        flash('مبلغ تسویه نمی‌تواند صفر باشد.', 'error')
        return redirect(url_for('entity_balance'))
    
    current_balance = database.get_entity_balance(entity_name)
    settle_amount = amount if current_balance > 0 else (-amount if current_balance < 0 else amount)
    database.add_entity_settlement(entity_name, settle_amount, desc)
    
    flash(f'تسویه حساب {entity_name} با مبلغ {amount:,.0f} ریال ثبت شد.', 'success')
    return redirect(url_for('entity_balance'))


# =====================================================================
# مدیریت انبار
# =====================================================================

@app.route('/inventory')
@login_required
def inventory():
    items = database.get_all_items()
    items_list = []
    total_value = 0
    
    for item in items:
        value = item[5] * item[3]  # current_stock * buy_price
        total_value += value
        items_list.append({
            'id': item[0], 'name': item[1], 'unit': item[2],
            'buy_price': item[3], 'initial_stock': item[4],
            'current_stock': item[5], 'min_stock': item[6],
            'value': value
        })
    
    low_items = database.get_low_stock_items()
    
    # گزارش تاریخچه
    filter_item = request.args.get('item', 'همه')
    filter_type = request.args.get('type', 'همه')
    
    report_rows = database.get_inventory_report(
        filter_item if filter_item != 'همه' else None,
        filter_type if filter_type != 'همه' else None
    )
    
    report_list = []
    total_entry = total_exit = 0
    for row in report_rows:
        if row[6] == 'entry':
            total_entry += row[4]
        else:
            total_exit += row[4]
        report_list.append({
            'id': row[0], 'date': row[1], 'item_name': row[2],
            'unit': row[3], 'quantity': row[4], 'unit_price': row[5],
            'type': row[6], 'entity': row[7], 'description': row[8]
        })
    
    item_names = database.get_item_names()
    units = ["عدد", "کیلوگرم", "گرم", "لیتر", "متر", "بسته", "جعبه", "تن", "سانتی‌متر"]
    
    return render_template('inventory.html', items=items_list, total_value=total_value,
                         low_items=low_items, report=report_list, item_names=item_names,
                         units=units, selected_item=filter_item, selected_type=filter_type,
                         total_entry=total_entry, total_exit=total_exit)


@app.route('/inventory/add', methods=['POST'])
@login_required
def add_item():
    name = request.form.get('name', '').strip()
    unit = request.form.get('unit', 'عدد').strip()
    buy_price = request.form.get('buy_price', '0').replace(',', '').strip()
    initial_stock = request.form.get('initial_stock', '0').strip()
    min_stock = request.form.get('min_stock', '0').strip()
    
    if not name:
        flash('نام کالا را وارد کنید.', 'error')
        return redirect(url_for('inventory'))
    
    try:
        buy_price = float(buy_price)
        initial_stock = float(initial_stock)
        min_stock = float(min_stock)
    except ValueError:
        flash('مقدار نامعتبر.', 'error')
        return redirect(url_for('inventory'))
    
    if database.add_item(name, unit, buy_price, initial_stock, initial_stock, min_stock):
        flash('کالا با موفقیت اضافه شد.', 'success')
    else:
        flash('کالایی با این نام قبلاً ثبت شده است.', 'error')
    
    return redirect(url_for('inventory'))


@app.route('/inventory/edit/<int:item_id>', methods=['POST'])
@login_required
def edit_item(item_id):
    name = request.form.get('name', '').strip()
    unit = request.form.get('unit', 'عدد').strip()
    buy_price = request.form.get('buy_price', '0').replace(',', '').strip()
    initial_stock = request.form.get('initial_stock', '0').strip()
    current_stock = request.form.get('current_stock', '0').strip()
    min_stock = request.form.get('min_stock', '0').strip()
    
    try:
        buy_price = float(buy_price)
        initial_stock = float(initial_stock)
        current_stock = float(current_stock)
        min_stock = float(min_stock)
    except ValueError:
        flash('مقدار نامعتبر.', 'error')
        return redirect(url_for('inventory'))
    
    database.update_item(item_id, name, unit, buy_price, initial_stock, current_stock, min_stock)
    flash('کالا با موفقیت ویرایش شد.', 'success')
    return redirect(url_for('inventory'))


@app.route('/inventory/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    database.delete_item(item_id)
    flash('کالا حذف شد.', 'success')
    return redirect(url_for('inventory'))


@app.route('/inventory/import', methods=['POST'])
@login_required
def import_inventory_excel():
    if 'file' not in request.files:
        flash('فایلی انتخاب نشده است.', 'error')
        return redirect(url_for('inventory'))
    
    file = request.files['file']
    if not file.filename:
        flash('فایلی انتخاب نشده است.', 'error')
        return redirect(url_for('inventory'))
    
    try:
        import pandas as pd
        import tempfile
        
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
                file.save(tmp.name)
                tmp_path = tmp.name
            df = pd.read_excel(tmp_path).fillna("")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except PermissionError:
                    pass
        
        cols = list(df.columns)
        if len(cols) < 2:
            flash('فایل اکسل باید حداقل ۲ ستون داشته باشد.', 'error')
            return redirect(url_for('inventory'))
        
        col_name = cols[0]
        col_unit = cols[1]
        imported = skipped = 0
        valid_units = ["عدد", "کیلوگرم", "گرم", "لیتر", "متر", "بسته", "جعبه", "تن", "سانتی‌متر"]
        existing_items = database.get_item_names()
        
        for _, row in df.iterrows():
            name = str(row[col_name]).strip()
            unit = str(row[col_unit]).strip()
            if not name:
                continue
            if name in existing_items:
                skipped += 1
                continue
            if unit not in valid_units:
                unit = "عدد"
            if database.add_item(name, unit, 0, 0, 0, 0):
                imported += 1
                existing_items.append(name)
            else:
                skipped += 1
        
        flash(f'تعداد {imported} کالای جدید اضافه شد. {skipped} کالا تکراری بود.', 'success')
    except Exception as e:
        flash(f'خطا در خواندن فایل اکسل: {e}', 'error')
    
    return redirect(url_for('inventory'))


# =====================================================================
# پشتیبان‌گیری
# =====================================================================

@app.route('/backup')
@login_required
def backup_page():
    # لیست بکاپ‌های موجود
    backup_files = []
    backup_dir = 'backup'
    if os.path.exists(backup_dir):
        for f in sorted(os.listdir(backup_dir), reverse=True):
            filepath = os.path.join(backup_dir, f)
            if os.path.isfile(filepath):
                size = os.path.getsize(filepath)
                mtime = jdatetime.datetime.fromtimestamp(os.path.getmtime(filepath))
                backup_files.append({
                    'name': f, 'size': f"{size / 1024:.1f} KB",
                    'date': mtime.strftime('%Y/%m/%d %H:%M')
                })
    
    return render_template('backup.html', backups=backup_files)


@app.route('/backup/full')
@login_required
def backup_full():
    filepath = backup_utils.backup_full_database()
    if filepath:
        flash('بکاپ کامل با موفقیت ذخیره شد.', 'success')
    else:
        flash('خطا در ساخت بکاپ کامل.', 'error')
    return redirect(url_for('backup_page'))


@app.route('/backup/restore', methods=['POST'])
@login_required
def backup_restore():
    if 'file' not in request.files:
        flash('فایلی انتخاب نشده است.', 'error')
        return redirect(url_for('backup_page'))
    
    file = request.files['file']
    if not file.filename:
        flash('فایلی انتخاب نشده است.', 'error')
        return redirect(url_for('backup_page'))
    
    filepath = os.path.join('backup', f"restore_{secure_filename(file.filename)}")
    file.save(filepath)
    
    success, msg = backup_utils.restore_full_database(filepath)
    if success:
        flash(f'بازیابی کامل انجام شد. {msg}', 'success')
    else:
        flash(f'خطا در بازیابی: {msg}', 'error')
    
    return redirect(url_for('backup_page'))


@app.route('/backup/restore_file/<filename>')
@login_required
def backup_restore_file(filename):
    filepath = os.path.join('backup', filename)
    if not os.path.exists(filepath):
        flash('فایل بکاپ یافت نشد.', 'error')
        return redirect(url_for('backup_page'))
    
    success, msg = backup_utils.restore_full_database(filepath)
    if success:
        flash(f'بازیابی کامل انجام شد. {msg}', 'success')
    else:
        flash(f'خطا در بازیابی: {msg}', 'error')
    
    return redirect(url_for('backup_page'))


@app.route('/backup/download/<filename>')
@login_required
def backup_download(filename):
    filepath = os.path.join('backup', filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    flash('فایل یافت نشد.', 'error')
    return redirect(url_for('backup_page'))


@app.route('/backup/definitions/export')
@login_required
def backup_definitions_export():
    filepath = os.path.join('backup', 'Definitions_Backup.json')
    backup_utils.backup_definitions(filepath)
    return send_file(filepath, as_attachment=True, download_name='Definitions_Backup.json')


@app.route('/backup/definitions/import', methods=['POST'])
@login_required
def backup_definitions_import():
    if 'file' not in request.files:
        flash('فایلی انتخاب نشده است.', 'error')
        return redirect(url_for('backup_page'))
    
    file = request.files['file']
    filepath = os.path.join('backup', f"temp_def_{secure_filename(file.filename)}")
    file.save(filepath)
    
    try:
        count = backup_utils.restore_definitions(filepath)
        flash(f'{count} تعریف جدید اضافه شد.', 'success')
    except Exception as e:
        flash(f'خطا: {e}', 'error')
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)
    
    return redirect(url_for('backup_page'))


@app.route('/backup/transactions/export')
@login_required
def backup_transactions_export():
    filepath = os.path.join('backup', 'Transactions_Backup.json')
    count = backup_utils.backup_transactions(filepath)
    return send_file(filepath, as_attachment=True, download_name='Transactions_Backup.json')


@app.route('/backup/transactions/import', methods=['POST'])
@login_required
def backup_transactions_import():
    if 'file' not in request.files:
        flash('فایلی انتخاب نشده است.', 'error')
        return redirect(url_for('backup_page'))
    
    file = request.files['file']
    filepath = os.path.join('backup', f"temp_tx_{secure_filename(file.filename)}")
    file.save(filepath)
    
    replace = request.form.get('replace', 'no') == 'yes'
    
    try:
        count = backup_utils.restore_transactions(filepath, replace_existing=replace)
        flash(f'{count} رکورد بازیابی شد.', 'success')
    except Exception as e:
        flash(f'خطا: {e}', 'error')
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)
    
    return redirect(url_for('backup_page'))


@app.route('/backup/change_password', methods=['POST'])
@login_required
def change_password():
    global APP_PASSWORD
    current = request.form.get('current_password', '').strip()
    new_pass = request.form.get('new_password', '').strip()
    confirm = request.form.get('confirm_password', '').strip()
    
    if current != APP_PASSWORD:
        flash('رمز عبور فعلی اشتباه است.', 'error')
    elif not new_pass:
        flash('رمز عبور جدید نمی‌تواند خالی باشد.', 'error')
    elif new_pass != confirm:
        flash('رمز عبور جدید و تکرار آن مطابقت ندارند.', 'error')
    else:
        APP_PASSWORD = new_pass
        flash('رمز عبور با موفقیت تغییر کرد.', 'success')
    
    return redirect(url_for('backup_page'))


@app.route('/backup/export/transactions')
@login_required
def export_transactions():
    txs = database.get_all_transactions()
    if not txs:
        flash('هیچ داده‌ای برای خروجی وجود ندارد.', 'error')
        return redirect(url_for('index'))
    
    export_data = []
    for tx in txs:
        tags = database.get_transaction_tags(tx[0])
        row = list(tx[1:9]) + [", ".join(tags)]
        export_data.append(row)
    
    filepath = os.path.join('backup', 'Transactions_Export.xlsx')
    if export_utils.export_to_excel(export_data, filepath):
        return send_file(filepath, as_attachment=True, download_name='Transactions_Export.xlsx')
    
    flash('خطا در ایجاد فایل خروجی.', 'error')
    return redirect(url_for('index'))


# =====================================================================
# مدیریت تعاریف (حساب‌ها، دسته‌بندی‌ها، اشخاص، تگ‌ها)
# =====================================================================

@app.route('/manage/accounts/add', methods=['POST'])
@login_required
def add_account():
    name = request.form.get('name', '').strip()
    if name:
        if database.add_account(name):
            flash('حساب اضافه شد.', 'success')
        else:
            flash('این حساب قبلاً ثبت شده.', 'error')
    return redirect(request.referrer or url_for('index'))


@app.route('/manage/accounts/delete', methods=['POST'])
@login_required
def delete_account():
    name = request.form.get('name', '').strip()
    if name:
        database.delete_account(name)
        flash('حساب حذف شد.', 'success')
    return redirect(request.referrer or url_for('index'))


@app.route('/manage/categories/add', methods=['POST'])
@login_required
def add_category():
    name = request.form.get('name', '').strip()
    if name:
        if database.add_category(name):
            flash('دسته‌بندی اضافه شد.', 'success')
        else:
            flash('این دسته‌بندی قبلاً ثبت شده.', 'error')
    return redirect(request.referrer or url_for('index'))


@app.route('/manage/categories/add_sub', methods=['POST'])
@login_required
def add_subcategory():
    parent = request.form.get('parent', '').strip()
    name = request.form.get('name', '').strip()
    if parent and name:
        if database.add_subcategory(parent, name):
            flash('زیردسته اضافه شد.', 'success')
        else:
            flash('خطا در افزودن زیردسته.', 'error')
    return redirect(request.referrer or url_for('index'))


@app.route('/manage/categories/delete', methods=['POST'])
@login_required
def delete_category():
    name = request.form.get('name', '').strip()
    if name:
        database.delete_category_full(name)
        flash('دسته‌بندی حذف شد.', 'success')
    return redirect(request.referrer or url_for('index'))


@app.route('/manage/entities/add', methods=['POST'])
@login_required
def add_entity():
    name = request.form.get('name', '').strip()
    if name:
        if database.add_entity(name):
            flash('شخص اضافه شد.', 'success')
        else:
            flash('این شخص قبلاً ثبت شده.', 'error')
    return redirect(request.referrer or url_for('index'))


@app.route('/manage/entities/delete', methods=['POST'])
@login_required
def delete_entity():
    name = request.form.get('name', '').strip()
    if name:
        database.delete_entity(name)
        flash('شخص حذف شد.', 'success')
    return redirect(request.referrer or url_for('index'))


@app.route('/manage/tags/add', methods=['POST'])
@login_required
def add_tag():
    name = request.form.get('name', '').strip()
    if name:
        if database.add_tag(name):
            flash('تگ اضافه شد.', 'success')
        else:
            flash('این تگ قبلاً ثبت شده.', 'error')
    return redirect(request.referrer or url_for('index'))


@app.route('/manage/tags/delete', methods=['POST'])
@login_required
def delete_tag():
    name = request.form.get('name', '').strip()
    if name:
        database.delete_tag(name)
        flash('تگ حذف شد.', 'success')
    return redirect(request.referrer or url_for('index'))


@app.route('/import/excel', methods=['POST'])
@login_required
def import_excel():
    if 'file' not in request.files:
        flash('فایلی انتخاب نشده است.', 'error')
        return redirect(url_for('index'))
    
    file = request.files['file']
    if not file.filename:
        flash('فایلی انتخاب نشده است.', 'error')
        return redirect(url_for('index'))
    
    try:
        import pandas as pd
        import tempfile
        
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
                file.save(tmp.name)
                tmp_path = tmp.name
            
            df = pd.read_excel(tmp_path).fillna("")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except PermissionError:
                    pass
        
        filename = secure_filename(file.filename)
        source_name = f"اکسل: {filename}"
        imported_count = 0
        skipped_count = 0
        
        for _, row in df.iterrows():
            try:
                amount = float(str(row.get("مبلغ (ریال/تومان)", 0)).replace(',', ''))
            except ValueError:
                amount = 0.0
            amount = abs(amount)
            
            date_str = str(row.get("تاریخ", "")).strip()
            t_type = str(row.get("نوع تراکنش", "")).strip()
            desc = str(row.get("توضیحات", "")).strip()
            acc = str(row.get("حساب/صندوق", "")).strip()
            cat = str(row.get("دسته‌بندی", "")).strip()
            ent = str(row.get("شخص / محل", "")).strip()
            
            if database.is_duplicate_transaction(date_str, t_type, amount, desc, acc, cat, ent):
                skipped_count += 1
                continue
            
            if acc and acc not in database.get_all_accounts():
                database.add_account(acc)
            if cat and cat not in database.get_all_categories():
                database.add_category(cat)
            if ent and ent not in database.get_all_entities():
                database.add_entity(ent)
            
            database.add_transaction(date_str, t_type, amount, desc, acc, cat, ent, source=source_name)
            imported_count += 1
        
        msg = f'تعداد {imported_count} رکورد جدید با موفقیت ایمپورت شد.'
        if skipped_count > 0:
            msg += f' تعداد {skipped_count} رکورد تکراری از ایمپورت چشم‌پوشی شد.'
        flash(msg, 'success')
    except Exception as e:
        flash(f'خطا در ایمپورت: {e}', 'error')
    
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)