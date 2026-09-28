import streamlit as st
import psycopg2
import pandas as pd
import re
import uuid
from difflib import SequenceMatcher



def get_db_connection():
    conn = psycopg2.connect(
        st.secrets["database"]["url"],
        options='-c client_encoding=UTF8'
    )
    conn.set_client_encoding('UTF8')
    return conn

def ensure_tables_exist():
    """التأكد من وجود الجداول الجديدة وإنشائها لو مش موجودة"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # جدول خصومات البنود
        cur.execute('''
            CREATE TABLE IF NOT EXISTS company_item_discounts (
                company_id INTEGER REFERENCES companies(id),
                item_key TEXT NOT NULL,
                discount_percent REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (company_id, item_key)
            )
        ''')
        
        # جدول أسعار السي آرم لكل شركة
        cur.execute('''
            CREATE TABLE IF NOT EXISTS company_c_arm_prices (
                company_id INTEGER REFERENCES companies(id),
                item_name TEXT NOT NULL,
                price REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (company_id, item_name)
            )
        ''')
        
        # جدول أسعار الإقامة لكل شركة
        cur.execute('''
            CREATE TABLE IF NOT EXISTS company_inpatient_prices (
                company_id INTEGER REFERENCES companies(id),
                inpatient_id INTEGER REFERENCES inpatient_services(id),
                room_price REAL NOT NULL DEFAULT 0,
                medical_supervision REAL NOT NULL DEFAULT 0,
                nursing_care REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (company_id, inpatient_id)
            )
        ''')
        
        # جدول أسعار تصنيفات العمليات لكل شركة
        cur.execute('''
            CREATE TABLE IF NOT EXISTS company_surgery_category_prices (
                company_id INTEGER REFERENCES companies(id),
                category_id INTEGER REFERENCES surgery_categories(id),
                surgeon_fee REAL NOT NULL DEFAULT 0,
                room_fee REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (company_id, category_id)
            )
        ''')
        
        # جدول الإعدادات الثابتة
        cur.execute('''
            CREATE TABLE IF NOT EXISTS inpatient_settings (
                id SERIAL PRIMARY KEY,
                setting_key TEXT UNIQUE NOT NULL,
                setting_value REAL NOT NULL,
                description TEXT
            )
        ''')
        
        # جدول أسعار السي آرم الافتراضية
        cur.execute('''
            CREATE TABLE IF NOT EXISTS c_arm_prices (
                id SERIAL PRIMARY KEY,
                item_name TEXT UNIQUE NOT NULL,
                price REAL NOT NULL DEFAULT 0
            )
        ''')
        
        # جدول أسعار التشاور لكل شركة
        cur.execute('''
            CREATE TABLE IF NOT EXISTS consultation_prices (
                company_id INTEGER PRIMARY KEY REFERENCES companies(id),
                price REAL NOT NULL DEFAULT 0
            )
        ''')
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"⚠️ خطأ في إنشاء الجداول: {e}")
    finally:
        cur.close()
        conn.close()

def update_inpatient_room(room_id, room_price, medical_supervision, nursing_care):
    """تحديث أسعار نوع إقامة"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            UPDATE inpatient_services 
            SET room_price = %s, medical_supervision = %s, nursing_care = %s
            WHERE id = %s
        ''', (room_price, medical_supervision, nursing_care, room_id))
        conn.commit()
        return True, "✅ تم تحديث أسعار الإقامة"
    except Exception as e:
        conn.rollback()
        return False, f"❌ {e}"
    finally:
        cur.close()
        conn.close()

def get_all_surgery_categories():
    """جلب كل تصنيفات العمليات مع أسعارها"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, name, surgeon_fee, room_fee FROM surgery_categories ORDER BY id')
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

def update_surgery_category(category_id, surgeon_fee, room_fee):
    """تحديث أسعار تصنيف عملية"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            UPDATE surgery_categories 
            SET surgeon_fee = %s, room_fee = %s
            WHERE id = %s
        ''', (surgeon_fee, room_fee, category_id))
        conn.commit()
        return True, "✅ تم تحديث أسعار التصنيف"
    except Exception as e:
        conn.rollback()
        return False, f"❌ {e}"
    finally:
        cur.close()
        conn.close()

# ==================== دوال أسعار الإقامة لكل شركة ====================
def get_company_inpatient_price(company_id, inpatient_id):
    """جلب أسعار إقامة لشركة معينة - لو مش موجودة يرجع الأسعار الافتراضية"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT room_price, medical_supervision, nursing_care
        FROM company_inpatient_prices
        WHERE company_id = %s AND inpatient_id = %s
    ''', (company_id, inpatient_id))
    result = cur.fetchone()
    
    if not result:
        # نرجع الأسعار الافتراضية من جدول inpatient_services
        cur.execute('''
            SELECT room_price, medical_supervision, nursing_care
            FROM inpatient_services WHERE id = %s
        ''', (inpatient_id,))
        result = cur.fetchone()
    
    cur.close()
    conn.close()
    return result if result else (0, 0, 0)

def update_company_inpatient_price(company_id, inpatient_id, room_price, medical_supervision, nursing_care):
    """تحديث أسعار إقامة لشركة معينة"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO company_inpatient_prices 
                (company_id, inpatient_id, room_price, medical_supervision, nursing_care)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (company_id, inpatient_id) 
            DO UPDATE SET 
                room_price = EXCLUDED.room_price,
                medical_supervision = EXCLUDED.medical_supervision,
                nursing_care = EXCLUDED.nursing_care
        ''', (company_id, inpatient_id, room_price, medical_supervision, nursing_care))
        conn.commit()
        return True, "✅ تم تحديث أسعار الإقامة"
    except Exception as e:
        conn.rollback()
        return False, f"❌ {e}"
    finally:
        cur.close()
        conn.close()

# ==================== دوال أسعار تصنيفات العمليات لكل شركة ====================
def get_company_surgery_category_price(company_id, category_id):
    """جلب أسعار تصنيف عملية لشركة معينة - لو مش موجودة يرجع الأسعار الافتراضية"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT surgeon_fee, room_fee
        FROM company_surgery_category_prices
        WHERE company_id = %s AND category_id = %s
    ''', (company_id, category_id))
    result = cur.fetchone()
    
    if not result:
        cur.execute('''
            SELECT surgeon_fee, room_fee
            FROM surgery_categories WHERE id = %s
        ''', (category_id,))
        result = cur.fetchone()
    
    cur.close()
    conn.close()
    return result if result else (0, 0)

def update_company_surgery_category_price(company_id, category_id, surgeon_fee, room_fee):
    """تحديث أسعار تصنيف عملية لشركة معينة"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO company_surgery_category_prices 
                (company_id, category_id, surgeon_fee, room_fee)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (company_id, category_id) 
            DO UPDATE SET 
                surgeon_fee = EXCLUDED.surgeon_fee,
                room_fee = EXCLUDED.room_fee
        ''', (company_id, category_id, surgeon_fee, room_fee))
        conn.commit()
        return True, "✅ تم تحديث أسعار التصنيف"
    except Exception as e:
        conn.rollback()
        return False, f"❌ {e}"
    finally:
        cur.close()
        conn.close()

# ==================== دوال إعدادات القسم الداخلي ====================
def get_inpatient_setting(key):
    """جلب إعداد واحد من inpatient_settings"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT setting_value FROM inpatient_settings WHERE setting_key = %s', (key,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result[0] if result else 0

def get_all_inpatient_settings():
    """جلب كل الإعدادات"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT setting_key, setting_value, description FROM inpatient_settings ORDER BY id')
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

def update_inpatient_setting(key, value):
    """تحديث إعداد"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO inpatient_settings (setting_key, setting_value)
            VALUES (%s, %s)
            ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value
        ''', (key, value))
        conn.commit()
        return True, "✅ تم تحديث الإعداد"
    except Exception as e:
        conn.rollback()
        return False, f"❌ {e}"
    finally:
        cur.close()
        conn.close()

def get_c_arm_prices():
    """جلب أسعار السي آرم"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, item_name, price FROM c_arm_prices ORDER BY id')
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

def update_c_arm_price(item_name, price):
    """تحديث سعر بند من السي آرم"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO c_arm_prices (item_name, price)
            VALUES (%s, %s)
            ON CONFLICT (item_name) DO UPDATE SET price = EXCLUDED.price
        ''', (item_name, price))
        conn.commit()
        return True, "✅ تم تحديث السعر"
    except Exception as e:
        conn.rollback()
        return False, f"❌ {e}"
    finally:
        cur.close()
        conn.close()

def get_consultation_price(company_id):
    """جلب سعر التشاور لشركة"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT price FROM consultation_prices WHERE company_id = %s', (company_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result[0] if result else 0

def update_consultation_price(company_id, price):
    """تحديث سعر التشاور لشركة"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO consultation_prices (company_id, price)
            VALUES (%s, %s)
            ON CONFLICT (company_id) DO UPDATE SET price = EXCLUDED.price
        ''', (company_id, price))
        conn.commit()
        return True, "✅ تم تحديث سعر التشاور"
    except Exception as e:
        conn.rollback()
        return False, f"❌ {e}"
    finally:
        cur.close()
        conn.close()

def get_inpatient_service_by_name(room_name):
    """جلب تفاصيل نوع إقامة من اسمه"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT id, room_type, room_price, medical_supervision, nursing_care, companion_price
        FROM inpatient_services WHERE room_type = %s
    ''', (room_name,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result

def get_all_surgery_services():
    """جلب كل العمليات الجراحية مع تصنيفها وسعر الجراح والغرفة"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT s.id, s.name, sc.name AS category_name, sc.surgeon_fee, sc.room_fee
        FROM services s
        JOIN surgery_categories sc ON sc.id = s.surgery_category_id
        ORDER BY sc.name, s.name
    ''')
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results
# ==================== قائمة بنود القسم الداخلي القابلة للخصم ====================
INPATIENT_DISCOUNT_ITEMS = {
    'room_stay': '🛏️ الإقامة (الغرفة)',
    'supervision': '👨‍⚕️ الإشراف الطبي',
    'nursing': '💉 التمريض المركّز',
    'surgeon': '👨‍⚕️ اتعاب الجراح',
    'anesthesia': '💉 التخدير',
    'assistant': '🩺 مساعد الجراح',
    'room_operation': '🏥 فتح غرفة العمليات',
    'consultation': '💬 التشاور',
    'labs': '🧪 التحاليل',
    'plates': '🔩 شرائح ومسامير',
    'scope': '🔬 المنظار',
    'c_arm': '🩻 السي آرم',
    'supplies': '📦 المستلزمات',
    'meds': '💊 الأدوية',
}

def get_company_item_discount(company_id, item_key):
    """جلب نسبة خصم بند معين لشركة"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT discount_percent FROM company_item_discounts
        WHERE company_id = %s AND item_key = %s
    ''', (company_id, item_key))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result[0] if result else 0

def update_company_item_discount(company_id, item_key, discount_percent):
    """تحديث خصم بند معين لشركة"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO company_item_discounts (company_id, item_key, discount_percent)
            VALUES (%s, %s, %s)
            ON CONFLICT (company_id, item_key) 
            DO UPDATE SET discount_percent = EXCLUDED.discount_percent
        ''', (company_id, item_key, discount_percent))
        conn.commit()
        return True, "✅ تم تحديث الخصم"
    except Exception as e:
        conn.rollback()
        return False, f"❌ {e}"
    finally:
        cur.close()
        conn.close()

def get_company_c_arm_prices(company_id):
    """جلب أسعار السي آرم لشركة - لو مش موجودة ترجع الافتراضية"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # جلب كل بنود السي آرم الأساسية
    cur.execute('SELECT item_name, price FROM c_arm_prices ORDER BY id')
    default_items = cur.fetchall()
    
    # جلب الأسعار المخصصة للشركة
    cur.execute('''
        SELECT item_name, price FROM company_c_arm_prices
        WHERE company_id = %s
    ''', (company_id,))
    company_items = dict(cur.fetchall())
    
    cur.close()
    conn.close()
    
    # دمج: لو الشركة ليها سعر مخصص، استخدمه؛ غير كده استخدم الافتراضي
    result = []
    for item_name, default_price in default_items:
        price = company_items.get(item_name, default_price)
        result.append((item_name, price))
    
    return result

def update_company_c_arm_price(company_id, item_name, price):
    """تحديث سعر بند سي آرم لشركة"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO company_c_arm_prices (company_id, item_name, price)
            VALUES (%s, %s, %s)
            ON CONFLICT (company_id, item_name) 
            DO UPDATE SET price = EXCLUDED.price
        ''', (company_id, item_name, price))
        conn.commit()
        return True, "✅ تم تحديث السعر"
    except Exception as e:
        conn.rollback()
        return False, f"❌ {e}"
    finally:
        cur.close()
        conn.close()

# ==================== دوال المصادقة ====================
ADMIN_PASSWORD = "admin123"

def check_password(password):
    return password == ADMIN_PASSWORD

# ==================== دوال قاعدة البيانات ====================
def get_all_companies():
    conn = get_db_connection()
    df = pd.read_sql_query('SELECT id, name, contract_notes FROM companies ORDER BY name', conn)
    conn.close()
    return df

def get_all_categories():
    conn = get_db_connection()
    df = pd.read_sql_query('SELECT id, name FROM categories ORDER BY name', conn)
    conn.close()
    return df

def get_services_by_category(category_id):
    conn = get_db_connection()
    df = pd.read_sql_query('SELECT id, name FROM services WHERE category_id = %s ORDER BY name', conn, params=(int(category_id),))
    conn.close()
    return df

def get_all_services():
    conn = get_db_connection()
    df = pd.read_sql_query('SELECT id, name FROM services WHERE surgery_category_id IS NULL ORDER BY name', conn)
    conn.close()
    return df

def get_inpatient_services():
    """جلب جميع أنواع الإقامة"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, room_type, room_price, medical_supervision, nursing_care, companion_price FROM inpatient_services ORDER BY id')
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

def search_price(company_name, service_name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT bp.price, c.id as company_id, s.category_id
        FROM base_prices bp
        JOIN companies c ON c.id = bp.company_id
        JOIN services s ON s.id = bp.service_id
        WHERE c.name = %s AND s.name = %s
    ''', (company_name, service_name))
    result = cur.fetchone()
    if not result:
        cur.close()
        conn.close()
        return None, "❌ الخدمة غير موجودة لهذه الشركة"
    base_price = result[0]
    company_id = result[1]
    category_id = result[2]
    cur.execute('SELECT discount_percent FROM discounts WHERE company_id = %s AND category_id = %s', (company_id, category_id))
    discount_result = cur.fetchone()
    discount_percent = discount_result[0] if discount_result else 0
    final_price = base_price * (1 - discount_percent / 100)
    cur.close()
    conn.close()
    return {'base_price': base_price, 'discount_percent': discount_percent, 'final_price': round(final_price, 2)}, None

def add_company(name, contract_notes):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO companies (name, contract_notes) VALUES (%s, %s)', (name, contract_notes))
        conn.commit()
        return True, "✅ تم إضافة الشركة بنجاح!"
    except psycopg2.IntegrityError:
        conn.rollback()
        cur.execute('UPDATE companies SET contract_notes = %s WHERE name = %s', (contract_notes, name))
        conn.commit()
        return True, "🔄 تم تحديث بيانات الشركة الموجودة!"
    finally:
        cur.close()
        conn.close()

def add_service(category_id, service_name):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO services (category_id, name) VALUES (%s, %s)', (category_id, service_name))
        conn.commit()
        return True, "✅ تم إضافة الخدمة بنجاح!"
    except psycopg2.IntegrityError:
        conn.rollback()
        return False, "⚠️ هذه الخدمة موجودة بالفعل في هذا التصنيف!"
    finally:
        cur.close()
        conn.close()

def delete_service(service_id):
    """حذف خدمة من قاعدة البيانات"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # جلب أسماء الشركات اللي مسعّرة الخدمة
        cur.execute('''
            SELECT c.name, bp.price
            FROM base_prices bp
            JOIN companies c ON c.id = bp.company_id
            WHERE bp.service_id = %s
            ORDER BY c.name
        ''', (service_id,))
        companies_with_price = cur.fetchall()
        
        if companies_with_price:
            cur.close()
            conn.close()
            return False, companies_with_price
        
        # لو مفيش أسعار، نحذف الخدمة
        cur.execute('DELETE FROM services WHERE id = %s', (service_id,))
        conn.commit()
        return True, "✅ تم حذف الخدمة بنجاح!"
    except Exception as e:
        conn.rollback()
        return False, f"❌ خطأ: {e}"
    finally:
        cur.close()
        conn.close()

def add_price(company_id, service_id, price):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT price FROM base_prices WHERE company_id = %s AND service_id = %s', (company_id, service_id))
    existing = cur.fetchone()
    if existing:
        cur.execute('UPDATE base_prices SET price = %s WHERE company_id = %s AND service_id = %s', (price, company_id, service_id))
        conn.commit()
        cur.close()
        conn.close()
        return True, "🔄 تم تحديث السعر بنجاح!"
    else:
        cur.execute('INSERT INTO base_prices (company_id, service_id, price) VALUES (%s, %s, %s)', (company_id, service_id, price))
        conn.commit()
        cur.close()
        conn.close()
        return True, "✅ تم إضافة السعر بنجاح!"

def add_discount(company_id, category_id, discount_percent):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO discounts (company_id, category_id, discount_percent) VALUES (%s, %s, %s) ON CONFLICT (company_id, category_id) DO UPDATE SET discount_percent = EXCLUDED.discount_percent', (company_id, category_id, discount_percent))
    conn.commit()
    cur.close()
    conn.close()
    return True, "✅ تم حفظ الخصم بنجاح!"

def update_service_price(company_id, service_id, new_price):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO base_prices (company_id, service_id, price)
            VALUES (%s, %s, %s)
            ON CONFLICT (company_id, service_id)
            DO UPDATE SET price = EXCLUDED.price
        ''', (company_id, service_id, new_price))
        conn.commit()
        return True, "✅ تم تحديث السعر بنجاح!"
    except Exception as e:
        conn.rollback()
        return False, f"❌ خطأ: {e}"
    finally:
        cur.close()
        conn.close()

def calculate_patient_share(base_price, patient_percent, discount_percent):
    patient_share = base_price * (patient_percent / 100)
    company_share_before_discount = base_price - patient_share
    company_discount = company_share_before_discount * (discount_percent / 100)
    company_final = company_share_before_discount - company_discount
    total_final = patient_share + company_final
    return {
        'patient_share': patient_share,
        'company_share_before_discount': company_share_before_discount,
        'company_discount': company_discount,
        'company_final': company_final,
        'total_final': total_final,
        'base_price': base_price,
        'patient_percent': patient_percent,
        'discount_percent': discount_percent
    }

# ==================== دوال رفع اللوائح ====================
def normalize_service_name(name):
    if pd.isna(name):
        return ""
    name = str(name).lower()
    name = re.sub(r'\([^)]*\)', '', name)
    name = re.sub(r'[^\w\s]', '', name)
    name = ' '.join(name.split())
    return name.strip()

def find_similar_service(service_name, existing_services, threshold=0.85):
    if not existing_services:
        return None
    normalized = normalize_service_name(service_name)
    best_match = None
    best_score = 0
    for existing in existing_services:
        existing_normalized = normalize_service_name(existing)
        score = SequenceMatcher(None, normalized, existing_normalized).ratio()
        if score > best_score:
            best_score = score
            best_match = existing
    return best_match if best_score >= threshold else None

def get_existing_services():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT name FROM services')
    results = cur.fetchall()
    cur.close()
    conn.close()
    return [r[0] for r in results]

def upload_price_list_from_excel(df, company_id):
    conn = get_db_connection()
    cur = conn.cursor()
    existing_services = get_existing_services()
    if not existing_services:
        return [], [], ["❌ لا توجد خدمات مسجلة في النظام."]
    service_col = None
    price_col = None
    for col in df.columns:
        col_lower = str(col).lower()
        if any(keyword in col_lower for keyword in ['خدمة', 'اسم', 'service', 'البند', 'البيان']):
            service_col = col
        if any(keyword in col_lower for keyword in ['سعر', 'price', 'قيمة', 'تكلفة']):
            price_col = col
    if service_col is None or price_col is None:
        return [], [], ["❌ لم يتم العثور على أعمدة الخدمة والسعر."]
    uploaded = []
    not_found = []
    errors = []
    for _, row in df.iterrows():
        service_name = str(row[service_col]).strip()
        price_value = row[price_col]
        if pd.isna(service_name) or service_name == '' or service_name == 'nan':
            continue
        try:
            price = float(price_value)
            if price <= 0:
                continue
        except:
            continue
        matched_service = find_similar_service(service_name, existing_services)
        if matched_service:
            cur.execute('SELECT id FROM services WHERE name = %s', (matched_service,))
            service_result = cur.fetchone()
            if service_result:
                service_id = service_result[0]
                try:
                    cur.execute('''
                        INSERT INTO base_prices (company_id, service_id, price) 
                        VALUES (%s, %s, %s) 
                        ON CONFLICT (company_id, service_id) 
                        DO UPDATE SET price = EXCLUDED.price
                    ''', (company_id, service_id, price))
                    uploaded.append({'service': service_name, 'matched_to': matched_service, 'price': price})
                except Exception as e:
                    errors.append(f"خطأ في رفع '{service_name}': {e}")
        else:
            not_found.append(service_name)
    conn.commit()
    cur.close()
    conn.close()
    return uploaded, not_found, errors

# ==================== واجهة التطبيق ====================
st.set_page_config(page_title="نظام إدارة أسعار العقود الطبية", page_icon="🏥", layout="wide")

# التأكد من وجود الجداول
ensure_tables_exist()

if 'is_admin' not in st.session_state:
    st.session_state.is_admin = False
if 'show_login' not in st.session_state:
    st.session_state.show_login = False

st.title("🏥 نظام إدارة أسعار العقود الطبية")
st.markdown("---")

# ==================== القائمة الجانبية ====================
st.sidebar.title("🏥 القائمة")

# الأزرار العامة
public_menu = st.sidebar.radio("📋 اختر العملية", [
    "🔍 البحث عن سعر",
    "🏥 القسم الداخلي"
])

# زر إدارة المحتوى
st.sidebar.markdown("---")
# زر إدارة المحتوى
if st.sidebar.button("⚙️ إدارة المحتوى"):
    st.session_state.show_login = True

if st.session_state.get('show_login', False):
    with st.sidebar:
        with st.form(key="admin_form"):
            password = st.text_input("🔑 أدخل كلمة المرور", type="password")
            col1, col2 = st.columns(2)
            with col1:
                submit = st.form_submit_button("تسجيل الدخول")
            with col2:
                cancel = st.form_submit_button("إلغاء")
            
            if submit:
                if check_password(password):
                    st.session_state.is_admin = True
                    st.session_state.show_login = False
                    st.success("✅ تم تسجيل الدخول كمدير")
                    st.rerun()
                else:
                    st.error("❌ كلمة المرور غير صحيحة")
            if cancel:
                st.session_state.show_login = False
                st.rerun()

# الأزرار الإدارية (تظهر بس لو admin)
if st.session_state.is_admin:
    st.sidebar.markdown("---")
    st.sidebar.success("✅ وضع المدير")
    admin_menu = st.sidebar.radio(
    "⚙️ إدارة النظام",
    [
        "🏢 إدارة الشركات",
        "🧪 إدارة الخدمات",
        "🏷️ إدارة الخصومات",
        "⚙️ إعدادات القسم الداخلي",
        "📊 عرض البيانات",
        "📤 رفع لائحة أسعار",
        "✏️ تعديل الأسعار الفردية"
    ]
)
    current_page = admin_menu
    
    # ====== زر تسجيل الخروج ======
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 تسجيل الخروج", use_container_width=True):
        st.session_state.is_admin = False
        st.session_state.show_login = False
        st.rerun()
else:
    current_page = public_menu
# ==================== الصفحات ====================
if current_page == "🔍 البحث عن سعر":
    st.header("🔍 البحث عن سعر خدمة")
    st.markdown("**📌 ملاحظة:** هذه الصفحة خاصة بخدمات العيادات الخارجية (كشوفات، تحاليل، أشعة، إلخ).")
    
    companies_df = get_all_companies()
    if companies_df.empty:
        st.warning("⚠️ لا توجد شركات مسجلة. قم بإضافة شركات أولاً.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            company_name = st.selectbox("اختر الشركة", companies_df['name'].tolist())
        with col2:
            services_df = get_all_services()
            if services_df.empty:
                st.warning("⚠️ لا توجد خدمات مسجلة. قم بإضافة خدمات أولاً.")
                service_name = None
            else:
                service_name = st.selectbox("اختر الخدمة", services_df['name'].tolist())
        
        col1, col2 = st.columns(2)
        with col1:
            patient_percent = st.number_input("🧑‍⚕️ نسبة تحمل المريض (%)", min_value=0.0, max_value=100.0, value=0.0, step=0.5, format="%.1f")
        with col2:
            quantity = st.number_input("🔢 الكمية", min_value=1, value=1, step=1)
        
        if st.button("🔍 ابحث", type="primary"):
            if service_name:
                result, error = search_price(company_name, service_name)
                if error:
                    st.error(error)
                else:
                    total_base = result['base_price'] * quantity
                    calculation = calculate_patient_share(total_base, patient_percent, result['discount_percent'])
                    st.success("✅ تم العثور على السعر!")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("💰 السعر الأساسي", f"{result['base_price']:,.2f} ج.م")
                    with col2:
                        st.metric("🧑‍⚕️ تحمل المريض", f"{calculation['patient_share']:,.2f} ج.م")
                    with col3:
                        st.metric("🏢 تحمل الشركة", f"{calculation['company_final']:,.2f} ج.م")
                    st.markdown("---")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.info(f"🏷️ **نسبة الخصم المسجلة:** {result['discount_percent']}%")
                    with col2:
                        st.info(f"🔢 **الكمية:** {quantity}")
                    with col3:
                        st.info(f"💰 **الإجمالي (قبل الخصم):** {total_base:,.2f} ج.م")
                    st.markdown("---")
                    st.subheader("📋 تفاصيل الحساب")
                    detail_data = {
                        "البند": ["السعر الأساسي (للوحدة)", "الكمية", "الإجمالي (السعر × الكمية)", "نسبة تحمل المريض", "تحمل المريض", "نسبة الخصم المسجلة", "تحمل الشركة"],
                        "القيمة": [f"{result['base_price']:,.2f} ج.م", f"{quantity}", f"{total_base:,.2f} ج.م", f"{patient_percent}%", f"{calculation['patient_share']:,.2f} ج.م", f"{result['discount_percent']}%", f"{calculation['company_final']:,.2f} ج.م"]
                    }
                    st.dataframe(pd.DataFrame(detail_data), hide_index=True, use_container_width=True)

elif current_page == "🏥 القسم الداخلي":
    st.header("🏥 القسم الداخلي - فاتورة متكاملة")
    
    # ============ إدخالات المستخدم ============
    st.subheader("📝 بيانات الفاتورة")
    
    # ===== الصف الأول: الشركة + العملية + نوع الإقامة =====
    col1, col2, col3 = st.columns(3)
    
    with col1:
        companies_df = get_all_companies()
        company_list = ["اختر الشركة"] + companies_df['name'].tolist()
        selected_company = st.selectbox("🏢 الشركة", company_list)
        company_id = None
        if selected_company != "اختر الشركة":
            company_id = int(companies_df[companies_df['name'] == selected_company]['id'].values[0])
    
    with col2:
        surgery_services = get_all_surgery_services()
        surgery_list = ["لا توجد عملية"]
        surgery_dict = {}
        for row in surgery_services:
            display_name = f"{row[1]} ({row[2]})"
            surgery_list.append(display_name)
            surgery_dict[display_name] = row
        selected_surgery = st.selectbox("🔪 العملية الجراحية", surgery_list)
        surgery_data = surgery_dict.get(selected_surgery) if selected_surgery != "لا توجد عملية" else None
    
    with col3:
        inpatient_services = get_inpatient_services()
        inpatient_list = ["لا توجد إقامة"]
        inpatient_dict = {}
        for row in inpatient_services:
            room_type = str(row[1])
            inpatient_list.append(room_type)
            inpatient_dict[room_type] = row
        selected_inpatient = st.selectbox("🛏️ نوع الإقامة", inpatient_list)
        inpatient_data = inpatient_dict.get(selected_inpatient) if selected_inpatient != "لا توجد إقامة" else None

    # ===== عدد أيام الإقامة =====
    inpatient_days = 1.0
    if inpatient_data:
        col1, col2 = st.columns([1, 3])
        with col1:
            inpatient_days = st.number_input(
                "📅 عدد الأيام",
                min_value=0.5,
                value=1.0,
                step=0.5,
                format="%.1f",
                help="أدخل 0.5 لنصف يوم، 1 ليوم كامل، 2 ليومين... إلخ"
            )
        with col2:
            st.info(f"💡 الإقامة: **{inpatient_days}** يوم × 3 بنود (غرفة + إشراف + تمريض)")
    
    # ===== الصف الثاني: المستلزمات + الأدوية + التحاليل =====
    col1, col2, col3 = st.columns(3)
    with col1:
        supplies_value = st.number_input("📦 قيمة المستلزمات", min_value=0.0, value=0.0, step=1.0, format="%.2f")
    with col2:
        meds_value = st.number_input("💊 قيمة الأدوية", min_value=0.0, value=0.0, step=1.0, format="%.2f")
    with col3:
        labs_value = st.number_input("🧪 قيمة التحاليل", min_value=0.0, value=0.0, step=1.0, format="%.2f")
    
    # ===== Checkboxes =====
    st.markdown("**🔧 خدمات إضافية:**")
    col1, col2, col3 = st.columns(3)
    with col1:
        has_plates = st.checkbox("🔩 شرائح ومسامير")
    with col2:
        has_scope = st.checkbox("🔬 منظار")
    with col3:
        has_c_arm = st.checkbox("🩻 جهاز السي آرم")
    
    # ===== خانات شرطية =====
    plates_value = 0.0
    scope_value = 0.0
    c_arm_device_count = 0
    c_arm_images_count = 0
    c_arm_tech_count = 0
    
    if has_plates:
        plates_value = st.number_input("💰 قيمة الشرائح والمسامير", min_value=0.0, value=0.0, step=1.0, format="%.2f")
    
    if has_scope:
        scope_value = st.number_input("💰 قيمة المنظار", min_value=0.0, value=0.0, step=1.0, format="%.2f")
    
    if has_c_arm:
        st.markdown("**🩻 جهاز السي آرم (أدخل العدد):**")
        col1, col2, col3 = st.columns(3)
        with col1:
            c_arm_device_count = st.number_input("عدد الجهاز", min_value=0, value=0, step=1)
        with col2:
            c_arm_images_count = st.number_input("عدد الصور", min_value=0, value=0, step=1)
        with col3:
            c_arm_tech_count = st.number_input("عدد الفني", min_value=0, value=0, step=1)
    
    # ===== Checkbox التخدير (لو العملية بسيطة) =====
    has_anesthesia = True
    if surgery_data:
        category_name = surgery_data[2]
        if "بسيطة" in category_name:
            has_anesthesia = st.checkbox("💉 العملية لها تخدير؟", value=True)
    
    # ===== بنود إضافية =====
    st.markdown("---")
    st.markdown("**➕ بنود إضافية:**")
    
    # تهيئة القائمة في session_state
    if 'additional_items' not in st.session_state:
        st.session_state.additional_items = []
    
    # زر إضافة بند جديد
    if st.button("➕ إضافة بند إضافي", key="add_additional_item"):
        st.session_state.additional_items.append({
            'id': str(uuid.uuid4()),
            'name': '',
            'price': 0.0
        })
        st.rerun()
    
    # عرض البنود الإضافية
    if st.session_state.additional_items:
        for idx, item in enumerate(st.session_state.additional_items):
            item_id = item['id']
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                item['name'] = st.text_input(
                    "اسم البند",
                    value=item['name'],
                    key=f"add_name_{item_id}",
                    placeholder="اكتب اسم البند الإضافي",
                    label_visibility="collapsed"
                )
            with col2:
                item['price'] = st.number_input(
                    "السعر",
                    min_value=0.0,
                    value=float(item['price']),
                    step=1.0,
                    format="%.2f",
                    key=f"add_price_{item_id}",
                    label_visibility="collapsed"
                )
            with col3:
                if st.button("🗑️", key=f"remove_{item_id}"):
                    st.session_state.additional_items.pop(idx)
                    st.rerun()
    
    # ============ حساب الفاتورة ============
    st.markdown("---")
    st.subheader("📋 الفاتورة")
    
    # جلب الإعدادات
    service_percent = get_inpatient_setting('service_percent')
    stamp_fee = get_inpatient_setting('stamp_fee')
    profit_margin_percent = get_inpatient_setting('profit_margin_percent')
    anesthesia_percent = get_inpatient_setting('anesthesia_percent')
    assistant_percent = get_inpatient_setting('assistant_percent')
    
    invoice = []
    total = 0
    
    # 1. الإقامة
    if inpatient_data:
        inpatient_id = inpatient_data[0]
        
        # جلب الأسعار الخاصة بالشركة
        if company_id:
            prices = get_company_inpatient_price(company_id, inpatient_id)
            room_price = prices[0]
            medical_supervision = prices[1]
            nursing_care = prices[2]
        else:
            room_price = inpatient_data[2]
            medical_supervision = inpatient_data[3]
            nursing_care = inpatient_data[4]
        
        # ضرب الأسعار في عدد الأيام
        total_room = room_price * inpatient_days
        total_supervision = medical_supervision * inpatient_days
        total_nursing = nursing_care * inpatient_days
        
        # تطبيق الخصومات
        if company_id:
            disc_room = get_company_item_discount(company_id, 'room_stay')
            disc_sup = get_company_item_discount(company_id, 'supervision')
            disc_nur = get_company_item_discount(company_id, 'nursing')
            total_room = total_room * (1 - disc_room / 100)
            total_supervision = total_supervision * (1 - disc_sup / 100)
            total_nursing = total_nursing * (1 - disc_nur / 100)
        
        # إضافة بنود الإقامة للفاتورة
        if inpatient_days == 1:
            invoice.append((f"الإقامة ({inpatient_data[1]})", total_room))
            invoice.append(("اشراف طبي", total_supervision))
            invoice.append(("تمريض مركز", total_nursing))
        else:
            invoice.append((f"الإقامة ({inpatient_data[1]}) × {inpatient_days} يوم", total_room))
            invoice.append((f"اشراف طبي × {inpatient_days} يوم", total_supervision))
            invoice.append((f"تمريض مركز × {inpatient_days} يوم", total_nursing))
    
    # 2. العملية
    surgeon_fee = 0
    anesthesia_fee = 0
    assistant_fee = 0
    room_fee = 0
    
    
    if surgery_data:
        service_id = surgery_data[0]
        
        # جلب category_id للعملية
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT surgery_category_id FROM services WHERE id = %s', (service_id,))
        cat_result = cur.fetchone()
        cur.close()
        conn.close()
        
        # جلب أسعار الجراح والغرفة
        if cat_result and company_id:
            category_id = cat_result[0]
            prices = get_company_surgery_category_price(company_id, category_id)
            surgeon_fee = prices[0]
            room_fee = prices[1]
        else:
            surgeon_fee = surgery_data[3]
            room_fee = surgery_data[4]
        
        # حساب التخدير والمساعد
        anesthesia_fee = surgeon_fee * (anesthesia_percent / 100) if has_anesthesia else 0
        assistant_fee = surgeon_fee * (assistant_percent / 100)
        
        # تطبيق الخصومات
        if company_id:
            surgeon_fee = surgeon_fee * (1 - get_company_item_discount(company_id, 'surgeon') / 100)
            room_fee = room_fee * (1 - get_company_item_discount(company_id, 'room_operation') / 100)
            anesthesia_fee = anesthesia_fee * (1 - get_company_item_discount(company_id, 'anesthesia') / 100)
            assistant_fee = assistant_fee * (1 - get_company_item_discount(company_id, 'assistant') / 100)
        
        # إضافة البنود للفاتورة
        invoice.append(("اتعاب جراح", surgeon_fee))
        if has_anesthesia:
            invoice.append(("أجور تخدير", anesthesia_fee))
        invoice.append(("أجر مساعد جراح", assistant_fee))
        invoice.append(("فتح غرفة عمليات", room_fee))
    
    # 3. التشاور
    if company_id and has_anesthesia and surgery_data:
        consultation = get_consultation_price(company_id)
        if consultation > 0:
            consultation = consultation * (1 - get_company_item_discount(company_id, 'consultation') / 100)
            invoice.append(("التشاور", consultation))
    
    # 4. التحاليل (مع الخصم)
    if labs_value > 0:
        if company_id:
            labs_value = labs_value * (1 - get_company_item_discount(company_id, 'labs') / 100)
        invoice.append(("التحاليل", labs_value))
    
    # 5. شرائح ومسامير (مع الخصم)
    if has_plates and plates_value > 0:
        if company_id:
            plates_value = plates_value * (1 - get_company_item_discount(company_id, 'plates') / 100)
        invoice.append(("شرائح ومسامير", plates_value))
        profit = plates_value * (profit_margin_percent / 100)
        invoice.append((f"هامش ربح {int(profit_margin_percent)}%", profit))
    
    # 6. المنظار (مع الخصم)
    if has_scope and scope_value > 0:
        if company_id:
            scope_value = scope_value * (1 - get_company_item_discount(company_id, 'scope') / 100)
        invoice.append(("المنظار", scope_value))
    
    # 7. السي آرم (أسعار خاصة بالشركة + خصم)
    if has_c_arm and company_id:
        c_arm_prices = get_company_c_arm_prices(company_id)
        c_arm_dict = {name: price for name, price in c_arm_prices}
        
        c_arm_discount = 1 - (get_company_item_discount(company_id, 'c_arm') / 100)
        
        if c_arm_device_count > 0:
            val = c_arm_device_count * c_arm_dict.get('جهاز السي آرم', 0) * c_arm_discount
            invoice.append(("جهاز السي آرم", val))
        if c_arm_images_count > 0:
            val = c_arm_images_count * c_arm_dict.get('صور السي آرم', 0) * c_arm_discount
            invoice.append(("صور السي آرم", val))
        if c_arm_tech_count > 0:
            val = c_arm_tech_count * c_arm_dict.get('فني السي آرم', 0) * c_arm_discount
            invoice.append(("فني السي آرم", val))
    
    # 8. المستلزمات (مع الخصم)
    if supplies_value > 0:
        if company_id:
            supplies_value = supplies_value * (1 - get_company_item_discount(company_id, 'supplies') / 100)
        invoice.append(("المستلزمات", supplies_value))
    
    # 8.5 البنود الإضافية (قبل الخدمة عشان تتحسب عليها نسبة الخدمة)
    for item in st.session_state.get('additional_items', []):
        if item['name'] and item['price'] > 0:
            invoice.append((item['name'], item['price']))
    
    # 9. الخدمة (20%)
    subtotal_before_service = sum(v for _, v in invoice)
    service_fee = subtotal_before_service * (service_percent / 100)
    invoice.append(("الخدمة", service_fee))
    
    # 10. الأدوية (مع الخصم)
    if meds_value > 0:
        if company_id:
            meds_value = meds_value * (1 - get_company_item_discount(company_id, 'meds') / 100)
        invoice.append(("الادوية", meds_value))
    
    # 11. الدمغة
    invoice.append(("الدمغة", stamp_fee))
    
    # ===== عرض الجدول =====
    invoice_data = []
    total = 0
    for item, value in invoice:
        invoice_data.append({"البيان": item, "اجمالي المبلغ": f"{value:,.2f}"})
        total += value
    
    invoice_data.append({"البيان": "الاجمالي", "اجمالي المبلغ": f"{total:,.2f}"})
    
        # عرض الجدول كامل بدون Scroll
    st.dataframe(
        pd.DataFrame(invoice_data),
        hide_index=True,
        use_container_width=True,
        height=(len(invoice_data) * 35) + 38  # ارتفاع محسوب حسب عدد الصفوف
    )
    
    st.success(f"💎 **الإجمالي: {total:,.2f} ج.م**")

# ==================== الصفحات الإدارية ====================
elif st.session_state.is_admin and current_page == "🏢 إدارة الشركات":
    st.header("🏢 إدارة الشركات")
    with st.expander("➕ إضافة شركة جديدة", expanded=True):
        col1, col2 = st.columns([2, 1])
        with col1:
            company_name = st.text_input("اسم الشركة")
        with col2:
            contract_notes = st.text_area("تعليمات العقد (اختياري)")
        if st.button("💾 حفظ الشركة", type="primary"):
            if company_name:
                success, message = add_company(company_name, contract_notes)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
            else:
                st.warning("⚠️ الرجاء إدخال اسم الشركة")
    st.subheader("📋 قائمة الشركات المسجلة")
    companies_df = get_all_companies()
    if not companies_df.empty:
        st.dataframe(companies_df, column_config={"id": "الرقم", "name": "اسم الشركة", "contract_notes": "تعليمات العقد"}, hide_index=True, use_container_width=True)
        st.caption(f"إجمالي الشركات: {len(companies_df)}")
    else:
        st.info("📭 لا توجد شركات مسجلة بعد")

elif st.session_state.is_admin and current_page == "🧪 إدارة الخدمات":
    st.header("🧪 إدارة الخدمات")
    
    # ====== إضافة خدمة جديدة ======
    with st.expander("➕ إضافة خدمة جديدة", expanded=True):
        categories_df = get_all_categories()
        if categories_df.empty:
            st.error("❌ لا توجد تصنيفات. يجب أن تكون التصنيفات موجودة مسبقاً.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                category_name = st.selectbox("اختر التصنيف (الملحق)", categories_df['name'].tolist())
                category_id = int(categories_df[categories_df['name'] == category_name]['id'].values[0])
            with col2:
                service_name = st.text_input("اسم الخدمة الجديدة")
            if st.button("💾 حفظ الخدمة", type="primary"):
                if service_name:
                    success, message = add_service(category_id, service_name)
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.warning(message)
                else:
                    st.warning("⚠️ الرجاء إدخال اسم الخدمة")
    
    # ====== عرض الخدمات ======
    st.subheader("📋 قائمة الخدمات المسجلة")
    
    conn = get_db_connection()
    services_df = pd.read_sql_query('''
        SELECT s.id, c.name as category_name, s.name as service_name,
               CASE WHEN bp.service_id IS NOT NULL THEN '✅' ELSE '❌' END as has_price
        FROM services s
        JOIN categories c ON c.id = s.category_id
        LEFT JOIN base_prices bp ON bp.service_id = s.id
        GROUP BY s.id, c.name, s.name, bp.service_id
        ORDER BY c.name, s.name
    ''', conn)
    conn.close()
    
    if not services_df.empty:
        st.dataframe(
            services_df[['category_name', 'service_name', 'has_price']],
            column_config={
                "category_name": "التصنيف",
                "service_name": "اسم الخدمة",
                "has_price": "مسعرة"
            },
            hide_index=True,
            use_container_width=True
        )
        
        st.markdown("---")
        st.subheader("🗑️ حذف خدمة")
        
        # اختيار الخدمة
        service_options = {f"{row['service_name']} ({row['category_name']})": row['id'] for _, row in services_df.iterrows()}
        selected_service_display = st.selectbox("اختر الخدمة لحذفها", list(service_options.keys()), key="delete_service_select")
        selected_service_id = service_options[selected_service_display]
        
        selected_row = services_df[services_df['id'] == selected_service_id].iloc[0]
        st.info(f"📌 **الخدمة:** {selected_row['service_name']} | **التصنيف:** {selected_row['category_name']} | **مسعرة:** {selected_row['has_price']}")
        
        # ====== زر حذف الخدمة ======
        if st.button("🗑️ حذف الخدمة", type="secondary"):
            if selected_row['has_price'] == '✅':
                # نحفظ إننا عاوزين نعرض الشركات
                st.session_state.show_companies_to_delete = True
                st.session_state.service_to_delete = selected_service_id
                st.rerun()
            else:
                success, message = delete_service(selected_service_id)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
        
        # ====== عرض الشركات المسعّرة (لو محتاجين نحذف أسعار) ======
        if st.session_state.get('show_companies_to_delete', False) and st.session_state.get('service_to_delete') == selected_service_id:
            
            # جلب الشركات اللي ليها سعر
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('''
                SELECT c.id, c.name, bp.price
                FROM base_prices bp
                JOIN companies c ON c.id = bp.company_id
                WHERE bp.service_id = %s AND bp.price IS NOT NULL
                ORDER BY c.name
            ''', (selected_service_id,))
            companies_list = cur.fetchall()
            cur.close()
            conn.close()
            
            if companies_list:
                st.warning(f"⚠️ هذه الخدمة مسعّرة في {len(companies_list)} شركة. احذف الأسعار أولاً:")
                
                # عرض الشركات مع زر حذف
                for company_id, company_name, price in companies_list:
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.write(f"🏢 **{company_name}**")
                    with col2:
                        st.write(f"{price:,.2f} ج.م")
                    with col3:
                        # زر حذف مع key فريد
                        if st.button("🗑️ حذف", key=f"del_btn_{company_id}_{selected_service_id}"):
                            # حذف السعر
                            conn = get_db_connection()
                            cur = conn.cursor()
                            cur.execute(
                                'DELETE FROM base_prices WHERE company_id = %s AND service_id = %s',
                                (company_id, selected_service_id)
                            )
                            conn.commit()
                            cur.close()
                            conn.close()
                            
                            # رسالة نجاح
                            st.success(f"✅ تم حذف سعر '{selected_row['service_name']}' من شركة '{company_name}' بنجاح!")
                            st.rerun()
                
                st.info("💡 بعد حذف كل الأسعار، اضغط على '🗑️ حذف الخدمة' لحذفها نهائياً")
            else:
                # لو مفيش شركات، نحذف الخدمة
                st.session_state.show_companies_to_delete = False
                success, message = delete_service(selected_service_id)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
            
            # زر إلغاء
            if st.button("❌ إغلاق", key="close_companies"):
                st.session_state.show_companies_to_delete = False
                st.rerun()
    else:
        st.info("📭 لا توجد خدمات مسجلة بعد")

elif st.session_state.is_admin and current_page == "🏷️ إدارة الخصومات":
    st.header("🏷️ إدارة الخصومات على الفئات")
    companies_df = get_all_companies()
    categories_df = get_all_categories()
    if companies_df.empty or categories_df.empty:
        st.warning("⚠️ يجب أن يكون لديك شركات وتصنيفات مسجلة أولاً.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            company_name = st.selectbox("🏢 اختر الشركة", companies_df['name'].tolist())
            company_id = int(companies_df[companies_df['name'] == company_name]['id'].values[0])
        with col2:
            category_name = st.selectbox("📂 اختر التصنيف (الملحق)", categories_df['name'].tolist())
            category_id = int(categories_df[categories_df['name'] == category_name]['id'].values[0])
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('SELECT COUNT(*) FROM services WHERE category_id = %s', (category_id,))
            service_count = cur.fetchone()[0]
            cur.close()
            conn.close()
            st.caption(f"📊 عدد الخدمات في هذا التصنيف: {service_count}")
        with col3:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('SELECT discount_percent FROM discounts WHERE company_id = %s AND category_id = %s', (company_id, category_id))
            current_discount = cur.fetchone()
            cur.close()
            conn.close()
            default_discount = current_discount[0] if current_discount else 0.0
            discount_percent = st.number_input("🏷️ نسبة الخصم (%)", min_value=0.0, max_value=100.0, value=float(default_discount), step=0.5, format="%.1f")
            if current_discount:
                st.info(f"ℹ️ الخصم الحالي: {current_discount[0]}%")
            else:
                st.info("ℹ️ لا يوجد خصم حالياً")
        if st.button("💾 حفظ الخصم", type="primary"):
            if discount_percent >= 0:
                success, message = add_discount(company_id, category_id, discount_percent)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
            else:
                st.warning("⚠️ الرجاء إدخال نسبة خصم صحيحة")
        st.markdown("---")
        st.subheader("📋 خصومات الشركة الحالية")
        conn = get_db_connection()
        discounts_df = pd.read_sql_query('''
            SELECT cat.name as category, d.discount_percent
            FROM discounts d
            JOIN categories cat ON cat.id = d.category_id
            WHERE d.company_id = %s
            ORDER BY cat.name
        ''', conn, params=(company_id,))
        conn.close()
        if not discounts_df.empty:
            st.dataframe(discounts_df, column_config={"category": "التصنيف", "discount_percent": "نسبة الخصم"}, hide_index=True, use_container_width=True)
        else:
            st.info("📭 لا توجد خصومات مسجلة لهذه الشركة")

elif st.session_state.is_admin and current_page == "⚙️ إعدادات القسم الداخلي":
    st.header("⚙️ إعدادات القسم الداخلي")
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "⚙️ الإعدادات الثابتة",
        "🛏️ أسعار الإقامة",
        "🔪 أسعار تصنيفات العمليات",
        "🩻 أسعار السي آرم",
        "💬 سعر التشاور لكل شركة",
        "🏷️ خصومات البنود"
    ])
    
    # ==================== tab1: الإعدادات الثابتة ====================
    with tab1:
        st.subheader("⚙️ الإعدادات الثابتة")
        st.markdown("هنا تحدد النسب الثابتة للفاتورة")
        
        settings = get_all_inpatient_settings()
        
        with st.form(key="settings_form"):
            new_values = {}
            for key, value, description in settings:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**{description or key}**")
                with col2:
                    new_val = st.number_input(
                        "القيمة",
                        min_value=0.0,
                        value=float(value),
                        step=0.5,
                        format="%.2f",
                        key=f"setting_{key}",
                        label_visibility="collapsed"
                    )
                    new_values[key] = new_val
            
            submit_settings = st.form_submit_button("💾 حفظ الإعدادات", type="primary", use_container_width=True)
        
        if submit_settings:
            for key, val in new_values.items():
                update_inpatient_setting(key, val)
            st.success("✅ تم حفظ الإعدادات بنجاح!")
            st.rerun()
    
    # ==================== tab2: أسعار الإقامة ====================
        # ==================== tab2: أسعار الإقامة (لكل شركة) ====================
    with tab2:
        st.subheader("🛏️ أسعار الإقامة والرعاية")
        st.markdown("حدد أسعار كل نوع إقامة لكل شركة على حدة")
        
        companies_df = get_all_companies()
        
        if companies_df.empty:
            st.warning("⚠️ لا توجد شركات مسجلة.")
        else:
            # قائمة منسدلة بالشركات
            company_name = st.selectbox("🏢 اختر الشركة", companies_df['name'].tolist(), key="inpatient_company")
            company_id = int(companies_df[companies_df['name'] == company_name]['id'].values[0])
            
            st.markdown("---")
            
            inpatient_services = get_inpatient_services()
            
            if not inpatient_services:
                st.warning("⚠️ لا توجد أنواع إقامة مسجلة.")
            else:
                with st.form(key=f"inpatient_prices_form_{company_id}"):
                    inpatient_values = {}
                    
                    for row in inpatient_services:
                        room_id = row[0]
                        room_type = row[1]
                        
                        # جلب الأسعار للشركة دي
                        prices = get_company_inpatient_price(company_id, room_id)
                        room_price = prices[0]
                        medical_sup = prices[1]
                        nursing = prices[2]
                        
                        st.markdown(f"### 🛏️ {room_type}")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            new_room = st.number_input(
                                "سعر الغرفة",
                                min_value=0.0,
                                value=float(room_price),
                                step=50.0,
                                format="%.2f",
                                key=f"room_{company_id}_{room_id}"
                            )
                        with col2:
                            new_sup = st.number_input(
                                "الإشراف الطبي",
                                min_value=0.0,
                                value=float(medical_sup),
                                step=10.0,
                                format="%.2f",
                                key=f"sup_{company_id}_{room_id}"
                            )
                        with col3:
                            new_nursing = st.number_input(
                                "التمريض المركّز",
                                min_value=0.0,
                                value=float(nursing),
                                step=10.0,
                                format="%.2f",
                                key=f"nursing_{company_id}_{room_id}"
                            )
                        
                        inpatient_values[room_id] = (new_room, new_sup, new_nursing)
                        st.markdown("---")
                    
                    submit_inpatient = st.form_submit_button(
                        f"💾 حفظ أسعار الإقامة لشركة {company_name}",
                        type="primary",
                        use_container_width=True
                    )
                
                if submit_inpatient:
                    saved = 0
                    for room_id, (room_price, sup, nursing) in inpatient_values.items():
                        success, _ = update_company_inpatient_price(company_id, room_id, room_price, sup, nursing)
                        if success:
                            saved += 1
                    st.success(f"✅ تم حفظ أسعار {saved} نوع إقامة لشركة {company_name} بنجاح!")
                    st.rerun()
    
    # ==================== tab3: أسعار تصنيفات العمليات (لكل شركة) ====================
    with tab3:
        st.subheader("🔪 أسعار تصنيفات العمليات")
        st.markdown("حدد اتعاب الجراح وفتح غرفة العمليات لكل تصنيف لكل شركة")
        
        companies_df = get_all_companies()
        
        if companies_df.empty:
            st.warning("⚠️ لا توجد شركات مسجلة.")
        else:
            # قائمة منسدلة بالشركات
            company_name = st.selectbox("🏢 اختر الشركة", companies_df['name'].tolist(), key="surgery_company")
            company_id = int(companies_df[companies_df['name'] == company_name]['id'].values[0])
            
            st.markdown("---")
            
            surgery_categories = get_all_surgery_categories()
            
            if not surgery_categories:
                st.warning("⚠️ لا توجد تصنيفات مسجلة.")
            else:
                with st.form(key=f"surgery_cat_form_{company_id}"):
                    cat_values = {}
                    
                    for row in surgery_categories:
                        cat_id = row[0]
                        cat_name = row[1]
                        
                        # جلب الأسعار للشركة دي
                        prices = get_company_surgery_category_price(company_id, cat_id)
                        surgeon_fee = prices[0]
                        room_fee = prices[1]
                        
                        st.markdown(f"### 🔪 {cat_name}")
                        col1, col2 = st.columns(2)
                        with col1:
                            new_surgeon = st.number_input(
                                "اتعاب الجراح",
                                min_value=0.0,
                                value=float(surgeon_fee),
                                step=500.0,
                                format="%.2f",
                                key=f"surgeon_{company_id}_{cat_id}"
                            )
                        with col2:
                            new_room = st.number_input(
                                "فتح غرفة العمليات",
                                min_value=0.0,
                                value=float(room_fee),
                                step=100.0,
                                format="%.2f",
                                key=f"roomfee_{company_id}_{cat_id}"
                            )
                        
                        cat_values[cat_id] = (new_surgeon, new_room)
                        st.markdown("---")
                    
                    submit_cat = st.form_submit_button(
                        f"💾 حفظ أسعار التصنيفات لشركة {company_name}",
                        type="primary",
                        use_container_width=True
                    )
                
                if submit_cat:
                    saved = 0
                    for cat_id, (surgeon, room) in cat_values.items():
                        success, _ = update_company_surgery_category_price(company_id, cat_id, surgeon, room)
                        if success:
                            saved += 1
                    st.success(f"✅ تم حفظ أسعار {saved} تصنيف لشركة {company_name} بنجاح!")
                    st.rerun()
    
    
    # ==================== tab4: أسعار السي آرم (لكل شركة) ====================
    with tab4:
        st.subheader("🩻 أسعار السي آرم")
        st.markdown("حدد سعر كل بند من بنود السي آرم لكل شركة على حدة")
        
        companies_df = get_all_companies()
        
        if companies_df.empty:
            st.warning("⚠️ لا توجد شركات مسجلة.")
        else:
            company_name = st.selectbox("🏢 اختر الشركة", companies_df['name'].tolist(), key="c_arm_company")
            company_id = int(companies_df[companies_df['name'] == company_name]['id'].values[0])
            
            st.markdown("---")
            
            c_arm_prices = get_company_c_arm_prices(company_id)
            
            with st.form(key=f"c_arm_form_{company_id}"):
                c_arm_values = {}
                for item_name, price in c_arm_prices:
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**{item_name}**")
                    with col2:
                        new_price = st.number_input(
                            "السعر",
                            min_value=0.0,
                            value=float(price),
                            step=1.0,
                            format="%.2f",
                            key=f"c_arm_{company_id}_{item_name}",
                            label_visibility="collapsed"
                        )
                        c_arm_values[item_name] = new_price
                
                submit_c_arm = st.form_submit_button(
                    f"💾 حفظ أسعار السي آرم لشركة {company_name}",
                    type="primary",
                    use_container_width=True
                )
            
            if submit_c_arm:
                saved = 0
                for item_name, price in c_arm_values.items():
                    success, _ = update_company_c_arm_price(company_id, item_name, price)
                    if success:
                        saved += 1
                st.success(f"✅ تم حفظ أسعار {saved} بند لشركة {company_name} بنجاح!")
                st.rerun()
    
    # ==================== tab5: سعر التشاور لكل شركة ====================
    with tab5:
        st.subheader("💬 سعر التشاور لكل شركة")
        st.markdown("حدد سعر التشاور لكل شركة على حدة")
        
        companies_df = get_all_companies()
        
        if companies_df.empty:
            st.warning("⚠️ لا توجد شركات مسجلة.")
        else:
            with st.form(key="consultation_form"):
                consultation_values = {}
                for _, row in companies_df.iterrows():
                    company_id = int(row['id'])
                    company_name = row['name']
                    current_price = get_consultation_price(company_id)
                    
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"🏢 **{company_name}**")
                    with col2:
                        new_price = st.number_input(
                            "السعر",
                            min_value=0.0,
                            value=float(current_price),
                            step=5.0,
                            format="%.2f",
                            key=f"consultation_{company_id}",
                            label_visibility="collapsed"
                        )
                        consultation_values[company_id] = new_price
                
                submit_consultation = st.form_submit_button("💾 حفظ أسعار التشاور", type="primary", use_container_width=True)

                            # ==================== tab6: خصومات البنود لكل شركة ====================
    with tab6:
        st.subheader("🏷️ خصومات البنود لكل شركة")
        st.markdown("حدد نسبة خصم لكل بند في القسم الداخلي (اترك 0 لو مفيش خصم)")
        
        companies_df = get_all_companies()
        
        if companies_df.empty:
            st.warning("⚠️ لا توجد شركات مسجلة.")
        else:
            company_name = st.selectbox("🏢 اختر الشركة", companies_df['name'].tolist(), key="discount_company")
            company_id = int(companies_df[companies_df['name'] == company_name]['id'].values[0])
            
            st.markdown("---")
            
            with st.form(key=f"discounts_form_{company_id}"):
                discount_values = {}
                
                for item_key, item_label in INPATIENT_DISCOUNT_ITEMS.items():
                    current_discount = get_company_item_discount(company_id, item_key)
                    
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**{item_label}**")
                    with col2:
                        new_discount = st.number_input(
                            "نسبة الخصم %",
                            min_value=0.0,
                            max_value=100.0,
                            value=float(current_discount),
                            step=0.5,
                            format="%.1f",
                            key=f"disc_{company_id}_{item_key}",
                            label_visibility="collapsed"
                        )
                        discount_values[item_key] = new_discount
                
                submit_discounts = st.form_submit_button(
                    f"💾 حفظ الخصومات لشركة {company_name}",
                    type="primary",
                    use_container_width=True
                )
            
            if submit_discounts:
                saved = 0
                for item_key, discount in discount_values.items():
                    success, _ = update_company_item_discount(company_id, item_key, discount)
                    if success:
                        saved += 1
                st.success(f"✅ تم حفظ خصومات {saved} بند لشركة {company_name} بنجاح!")
                st.rerun()
            
            # ====== معالجة الحفظ برة الـ form ======
            if submit:
                conn = get_db_connection()
                cur = conn.cursor()

                saved_companies = []
                unchanged_companies = []
                skipped_companies = []

                for company_id, price in prices_dict.items():
                    if price > 0:
                        cur.execute(
                            'SELECT price FROM base_prices WHERE company_id = %s AND service_id = %s',
                            (company_id, service_id)
                        )
                        old_result = cur.fetchone()
                        old_price = old_result[0] if old_result else None

                        cur.execute('SELECT name FROM companies WHERE id = %s', (company_id,))
                        company_name = cur.fetchone()[0]

                        if old_price is None or old_price != price:
                            try:
                                cur.execute('''
                                    INSERT INTO base_prices (company_id, service_id, price)
                                    VALUES (%s, %s, %s)
                                    ON CONFLICT (company_id, service_id)
                                    DO UPDATE SET price = EXCLUDED.price
                                ''', (company_id, service_id, price))

                                saved_companies.append({
                                    'name': company_name,
                                    'old_price': old_price,
                                    'new_price': price
                                })
                            except Exception as e:
                                st.error(f"خطأ في حفظ سعر {company_name}: {e}")
                        else:
                            unchanged_companies.append(company_name)
                    else:
                        cur.execute('SELECT name FROM companies WHERE id = %s', (company_id,))
                        company_name = cur.fetchone()[0]
                        skipped_companies.append(company_name)

                conn.commit()
                cur.close()
                conn.close()

                if saved_companies:
                    st.success(f"✅ تم حفظ أسعار {len(saved_companies)} شركة بنجاح!")

                    st.subheader("📋 الشركات اللي اتغير سعرها:")
                    detail_data = []
                    for item in saved_companies:
                        if item['old_price'] is None:
                            detail_data.append({
                                "الشركة": item['name'],
                                "السعر القديم": "غير مسعرة",
                                "السعر الجديد": f"{item['new_price']:,.2f} ج.م"
                            })
                        else:
                            detail_data.append({
                                "الشركة": item['name'],
                                "السعر القديم": f"{item['old_price']:,.2f} ج.م",
                                "السعر الجديد": f"{item['new_price']:,.2f} ج.م"
                            })

                    st.dataframe(
                        pd.DataFrame(detail_data),
                        hide_index=True,
                        use_container_width=True
                    )
                else:
                    st.info("ℹ️ لم يتم تغيير أي سعر.")

                if unchanged_companies:
                    st.info(f"ℹ️ {len(unchanged_companies)} شركة لم يتغير سعرها.")

                if skipped_companies:
                    st.warning(f"⚠️ تم تخطي {len(skipped_companies)} شركة (السعر = 0).")
            
            if submit_consultation:
                saved = 0
                for company_id, price in consultation_values.items():
                    success, _ = update_consultation_price(company_id, price)
                    if success:
                        saved += 1
                st.success(f"✅ تم حفظ أسعار {saved} شركة بنجاح!")
                st.rerun()

elif st.session_state.is_admin and current_page == "📊 عرض البيانات":
    st.header("📊 عرض جميع البيانات")
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏢 الشركات", "🧪 الخدمات", "💰 الأسعار", "🏷️ الخصومات", "🔪 العمليات الجراحية"])
    with tab1:
        companies_df = get_all_companies()
        if not companies_df.empty:
            st.dataframe(companies_df, hide_index=True, use_container_width=True)
        else:
            st.info("لا توجد بيانات")
    with tab2:
        conn = get_db_connection()
        services_df = pd.read_sql_query('''
            SELECT s.id, c.name as category, s.name as service, s.classification
            FROM services s
            JOIN categories c ON c.id = s.category_id
            ORDER BY c.name, s.name
        ''', conn)
        conn.close()
        if not services_df.empty:
            st.dataframe(services_df, hide_index=True, use_container_width=True)
        else:
            st.info("لا توجد بيانات")
    with tab3:
        conn = get_db_connection()
        prices_df = pd.read_sql_query('''
            SELECT c.name as company, s.name as service, bp.price
            FROM base_prices bp
            JOIN companies c ON c.id = bp.company_id
            JOIN services s ON s.id = bp.service_id
            ORDER BY c.name, s.name
        ''', conn)
        conn.close()
        if not prices_df.empty:
            st.dataframe(prices_df, hide_index=True, use_container_width=True)
        else:
            st.info("لا توجد بيانات")
    with tab4:
        conn = get_db_connection()
        discounts_df = pd.read_sql_query('''
            SELECT c.name as company, cat.name as category, d.discount_percent
            FROM discounts d
            JOIN companies c ON c.id = d.company_id
            JOIN categories cat ON cat.id = d.category_id
            ORDER BY c.name, cat.name
        ''', conn)
        conn.close()
        if not discounts_df.empty:
            st.dataframe(discounts_df, hide_index=True, use_container_width=True)
        else:
            st.info("لا توجد بيانات")
    with tab5:
        conn = get_db_connection()
        surgery_df = pd.read_sql_query('''
            SELECT s.name as service, sc.name as category,
                   sc.surgeon_fee, sc.room_fee,
                   (sc.surgeon_fee * 0.20) as anesthesia,
                   (sc.surgeon_fee * 0.10) as assistant,
                   (sc.surgeon_fee + sc.room_fee + (sc.surgeon_fee * 0.20) + (sc.surgeon_fee * 0.10)) as total
            FROM services s
            JOIN surgery_categories sc ON sc.id = s.surgery_category_id
            ORDER BY sc.name, s.name
        ''', conn)
        conn.close()
        if not surgery_df.empty:
            st.dataframe(surgery_df, hide_index=True, use_container_width=True)
        else:
            st.info("لا توجد عمليات جراحية مسجلة")

elif st.session_state.is_admin and current_page == "📤 رفع لائحة أسعار":
    st.header("📤 رفع لائحة أسعار من Excel")
    companies_df = get_all_companies()
    if companies_df.empty:
        st.warning("⚠️ يجب إضافة شركات أولاً قبل رفع اللائحة.")
    else:
        company_name = st.selectbox("🏢 اختر الشركة", companies_df['name'].tolist())
        company_id = int(companies_df[companies_df['name'] == company_name]['id'].values[0])
        uploaded_file = st.file_uploader("📂 اختر ملف Excel", type=['xlsx', 'xls'])
        if uploaded_file is not None:
            try:
                df = pd.read_excel(uploaded_file)
                st.success(f"✅ تم قراءة الملف: {len(df)} صف")
                st.subheader("📋 عينة من البيانات")
                st.dataframe(df.head(10), use_container_width=True)
                if st.button("🚀 رفع الأسعار", type="primary"):
                    with st.spinner("جاري رفع الأسعار..."):
                        uploaded, not_found, errors = upload_price_list_from_excel(df, company_id)
                        st.subheader("📊 نتائج الرفع")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("✅ تم رفعها", len(uploaded))
                        with col2:
                            st.metric("❌ غير موجودة", len(not_found))
                        with col3:
                            st.metric("⚠️ أخطاء", len(errors))
                        if uploaded:
                            st.subheader("✅ الخدمات التي تم رفعها")
                            st.dataframe(pd.DataFrame(uploaded), use_container_width=True)
                        if not_found:
                            st.subheader("❌ الخدمات غير الموجودة في النظام")
                            st.warning(f"الخدمات التالية غير موجودة ولم يتم رفعها: {len(not_found)} خدمة")
                            for service in not_found[:50]:
                                st.write(f"- {service}")
                            if len(not_found) > 50:
                                st.write(f"... و {len(not_found) - 50} خدمات أخرى")
                        if errors:
                            st.subheader("⚠️ الأخطاء")
                            for error in errors:
                                st.error(error)
                        if not uploaded and not not_found and not errors:
                            st.info("لم يتم رفع أي أسعار. تأكد من أن الملف يحتوي على بيانات صحيحة.")
            except Exception as e:
                st.error(f"❌ خطأ في قراءة الملف: {e}")

elif st.session_state.is_admin and current_page == "✏️ تعديل الأسعار الفردية":
    st.header("✏️ تسعير خدمة لأكتر من شركة")
    st.markdown("""
    **📌 التعليمات:**
    - اختر الخدمة
    - هتظهرلك كل الشركات مع خانة السعر
    - ادخل السعر لكل شركة عاوزها
    - اضغط "💾 حفظ جميع الأسعار" مرة واحدة
    """)

    services_df = get_all_services()

    if services_df.empty:
        st.warning("⚠️ لا توجد خدمات مسجلة.")
    else:
        service_name = st.selectbox("🔍 اختر الخدمة", services_df['name'].tolist())
        service_id = int(services_df[services_df['name'] == service_name]['id'].values[0])

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            SELECT c.id, c.name, bp.price
            FROM companies c
            LEFT JOIN base_prices bp 
                ON bp.company_id = c.id AND bp.service_id = %s
            ORDER BY c.name
        ''', (service_id,))
        companies_data = cur.fetchall()
        cur.close()
        conn.close()

        if not companies_data:
            st.warning("⚠️ لا توجد شركات مسجلة.")
        else:
            st.subheader(f"📋 تسعير الخدمة: {service_name}")
            st.caption(f"📊 عدد الشركات: {len(companies_data)}")
            st.markdown("---")

            # ====== FORM ======
            with st.form(key=f"prices_form_{service_id}"):
                prices_dict = {}

                for company_id, company_name, current_price in companies_data:
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"🏢 **{company_name}**")
                    with col2:
                        new_price = st.number_input(
                            "السعر",
                            min_value=0.0,
                            value=float(current_price) if current_price else 0.0,
                            step=1.0,
                            format="%.2f",
                            key=f"price_{company_id}_{service_id}",
                            label_visibility="collapsed"
                        )
                        prices_dict[company_id] = new_price

                st.markdown("---")



                # ==================== tab6: خصومات البنود لكل شركة ====================
    with tab6:
        st.subheader("🏷️ خصومات البنود لكل شركة")
        st.markdown("حدد نسبة خصم لكل بند في القسم الداخلي (اترك 0 لو مفيش خصم)")
        
        companies_df = get_all_companies()
        
        if companies_df.empty:
            st.warning("⚠️ لا توجد شركات مسجلة.")
        else:
            company_name = st.selectbox("🏢 اختر الشركة", companies_df['name'].tolist(), key="discount_company")
            company_id = int(companies_df[companies_df['name'] == company_name]['id'].values[0])
            
            st.markdown("---")
            
            with st.form(key=f"discounts_form_{company_id}"):
                discount_values = {}
                
                for item_key, item_label in INPATIENT_DISCOUNT_ITEMS.items():
                    current_discount = get_company_item_discount(company_id, item_key)
                    
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**{item_label}**")
                    with col2:
                        new_discount = st.number_input(
                            "نسبة الخصم %",
                            min_value=0.0,
                            max_value=100.0,
                            value=float(current_discount),
                            step=0.5,
                            format="%.1f",
                            key=f"disc_{company_id}_{item_key}",
                            label_visibility="collapsed"
                        )
                        discount_values[item_key] = new_discount
                
                submit_discounts = st.form_submit_button(
                    f"💾 حفظ الخصومات لشركة {company_name}",
                    type="primary",
                    use_container_width=True
                )
            
            if submit_discounts:
                saved = 0
                for item_key, discount in discount_values.items():
                    success, _ = update_company_item_discount(company_id, item_key, discount)
                    if success:
                        saved += 1
                st.success(f"✅ تم حفظ خصومات {saved} بند لشركة {company_name} بنجاح!")
                st.rerun()
            
            # ====== معالجة الحفظ برة الـ form ======
            if submit:
                conn = get_db_connection()
                cur = conn.cursor()

                saved_companies = []
                unchanged_companies = []
                skipped_companies = []

                for company_id, price in prices_dict.items():
                    if price > 0:
                        cur.execute(
                            'SELECT price FROM base_prices WHERE company_id = %s AND service_id = %s',
                            (company_id, service_id)
                        )
                        old_result = cur.fetchone()
                        old_price = old_result[0] if old_result else None

                        cur.execute('SELECT name FROM companies WHERE id = %s', (company_id,))
                        company_name = cur.fetchone()[0]

                        if old_price is None or old_price != price:
                            try:
                                cur.execute('''
                                    INSERT INTO base_prices (company_id, service_id, price)
                                    VALUES (%s, %s, %s)
                                    ON CONFLICT (company_id, service_id)
                                    DO UPDATE SET price = EXCLUDED.price
                                ''', (company_id, service_id, price))

                                saved_companies.append({
                                    'name': company_name,
                                    'old_price': old_price,
                                    'new_price': price
                                })
                            except Exception as e:
                                st.error(f"خطأ في حفظ سعر {company_name}: {e}")
                        else:
                            unchanged_companies.append(company_name)
                    else:
                        cur.execute('SELECT name FROM companies WHERE id = %s', (company_id,))
                        company_name = cur.fetchone()[0]
                        skipped_companies.append(company_name)

                conn.commit()
                cur.close()
                conn.close()

                if saved_companies:
                    st.success(f"✅ تم حفظ أسعار {len(saved_companies)} شركة بنجاح!")

                    st.subheader("📋 الشركات اللي اتغير سعرها:")
                    detail_data = []
                    for item in saved_companies:
                        if item['old_price'] is None:
                            detail_data.append({
                                "الشركة": item['name'],
                                "السعر القديم": "غير مسعرة",
                                "السعر الجديد": f"{item['new_price']:,.2f} ج.م"
                            })
                        else:
                            detail_data.append({
                                "الشركة": item['name'],
                                "السعر القديم": f"{item['old_price']:,.2f} ج.م",
                                "السعر الجديد": f"{item['new_price']:,.2f} ج.م"
                            })

                    st.dataframe(
                        pd.DataFrame(detail_data),
                        hide_index=True,
                        use_container_width=True
                    )
                else:
                    st.info("ℹ️ لم يتم تغيير أي سعر.")

                if unchanged_companies:
                    st.info(f"ℹ️ {len(unchanged_companies)} شركة لم يتغير سعرها.")

                if skipped_companies:
                    st.warning(f"⚠️ تم تخطي {len(skipped_companies)} شركة (السعر = 0).")
                                # زر الحفظ جوه الـ form
                submit = st.form_submit_button(
                    "💾 حفظ جميع الأسعار",
                    type="primary",
                    use_container_width=True
                )
