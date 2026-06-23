import pandas as pd

def export_to_excel(data_list, file_path):
    """دریافت داده‌ها و ذخیره مستقیم آن‌ها در مسیر انتخابی کاربر"""
    try:
        # نام ستون‌ها بر اساس ساختار برنامه (شامل تگ‌ها)
        columns = ["تاریخ", "نوع تراکنش", "حساب/صندوق", "دسته‌بندی", "شخص / محل", "مبلغ (ریال/تومان)", "توضیحات", "منبع", "تگ‌ها"]
        
        # تبدیل لیست به ساختار دیتافریم پانداز
        df = pd.DataFrame(data_list, columns=columns)
        
        # ذخیره فایل در مسیر مشخص شده توسط کاربر
        df.to_excel(file_path, index=False)
        return True
    except Exception as e:
        print(f"Error exporting to excel: {e}")
        return False