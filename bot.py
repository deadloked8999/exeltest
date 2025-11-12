"""
Telegram бот для работы с Excel файлами и PostgreSQL через DeepSeek API
"""
import os
import logging
from typing import Optional, Dict, Any, Set, List
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    BotCommand
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

from database import Database
from excel_processor import ExcelProcessor
from employee_parser import EmployeeParser
from simple_query_parser import SimpleQueryParser
from psycopg2.extras import RealDictCursor
import re
import io
from decimal import Decimal
from datetime import datetime, date
import pandas as pd

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

ACCESS_PASSWORD = os.getenv('BOT_ACCESS_PASSWORD', '1801')
AUTHORIZED_USERS: Set[int] = set()


def user_is_authorized(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return user_id in AUTHORIZED_USERS or context.user_data.get('authorized', False)


def set_authorized(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    AUTHORIZED_USERS.add(user_id)
    context.user_data['authorized'] = True
    context.user_data.pop('awaiting_password', None)


async def request_password(message, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['awaiting_password'] = True
    await message.reply_text(
        "🔐 Введите пароль для доступа к боту.",
    )


# Инициализация компонентов
db = Database(
    host=os.getenv('DB_HOST', 'localhost'),
    port=int(os.getenv('DB_PORT', 5432)),
    database=os.getenv('DB_NAME', 'excel_bot'),
    user=os.getenv('DB_USER', 'postgres'),
    password=os.getenv('DB_PASSWORD', 'postgres')
)

excel_processor = ExcelProcessor()
query_parser = SimpleQueryParser()
employee_parser = EmployeeParser()

# Константы
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
BUTTON_FILES = "📁 Файлы"
BUTTON_QUERIES = "📊 Запросы"
BUTTON_REPORTS = "📈 Сформировать отчет"
BUTTON_EMPLOYEES = "👥 Сотрудники"
BUTTON_HELP = "ℹ️ Помощь"
DATE_FORMATS = ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"]
QUERY_BLOCKS = [
    ("income", "Доходы"),
    ("tickets", "Входные билеты"),
    ("payments", "Типы оплат"),
    ("staff", "Статистика персонала"),
    ("expenses", "Расходы"),
    ("cash", "Инкассация"),
    ("debts", "Долги по персоналу"),
    ("notes", "Примечание"),
    ("totals", "Итоговый баланс")
]


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📁 Файлы", callback_data="main_files")],
        [InlineKeyboardButton("📊 Запросы к данным", callback_data="main_queries")],
        [InlineKeyboardButton("👥 Сотрудники", callback_data="employee_menu")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="main_help")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(BUTTON_FILES), KeyboardButton(BUTTON_QUERIES)],
        [KeyboardButton(BUTTON_REPORTS)],
        [KeyboardButton(BUTTON_EMPLOYEES), KeyboardButton(BUTTON_HELP)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_files_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📄 Список файлов", callback_data="files_list")],
        [InlineKeyboardButton("📅 Даты отчётов по клубу", callback_data="files_dates_by_club")],
        [InlineKeyboardButton("🔍 Последние записи", callback_data="files_latest")],
        [InlineKeyboardButton("🔄 Переобработать все файлы", callback_data="files_reprocess")],
        [InlineKeyboardButton("🧼 Очистить все файлы", callback_data="files_clear")],
        [InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_employees_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("➕ Добавить сотрудника", callback_data="employee_add")],
        [InlineKeyboardButton("🗑 Удалить сотрудника", callback_data="employee_delete")],
        [InlineKeyboardButton("🔍 Найти сотрудника", callback_data="employee_search")],
        [InlineKeyboardButton("📋 Список сотрудников", callback_data="employee_list")],
        [InlineKeyboardButton("📥 Импорт списка (текст)", callback_data="employee_import")],
        [InlineKeyboardButton("📤 Экспорт списка (Excel)", callback_data="employee_export")],
        [InlineKeyboardButton("🧼 Очистить всех", callback_data="employee_clear")],
        [InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_club_selection_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🏢 Москвич", callback_data="select_club|Москвич")],
        [InlineKeyboardButton("🌟 Анора", callback_data="select_club|Анора")],
        [InlineKeyboardButton("📊 Оба клуба", callback_data="select_club|Оба")],
        [InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_query_dates_keyboard(dates: List[date]) -> InlineKeyboardMarkup:
    keyboard = []
    for dt in dates:
        label = format_report_date(dt)
        callback_data = f"query_date|{dt.isoformat()}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])
    keyboard.append([InlineKeyboardButton("⬅️ К выбору клуба", callback_data="main_queries")])
    keyboard.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)


def get_blocks_keyboard(report_date: date) -> InlineKeyboardMarkup:
    keyboard = []
    for block_id, block_label in QUERY_BLOCKS:
        callback_data = f"query_block|{report_date.isoformat()}|{block_id}"
        keyboard.append([InlineKeyboardButton(block_label, callback_data=callback_data)])
    keyboard.append([InlineKeyboardButton("⬅️ К выбору клуба", callback_data="main_queries")])
    keyboard.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)


def parse_period_from_text(text: str) -> Optional[tuple[date, date]]:
    """Парсинг периода из текста типа '1.11-5.12' или '1,11-5,12'"""
    try:
        from datetime import datetime
        current_year = datetime.now().year
        
        # Заменяем запятые на точки и убираем пробелы
        text = text.replace(',', '.').replace(' ', '')
        
        # Разделяем по дефису
        if '-' not in text:
            return None
        
        parts = text.split('-')
        if len(parts) != 2:
            return None
        
        start_str, end_str = parts
        
        # Парсим начальную дату
        if '.' in start_str:
            start_parts = start_str.split('.')
            if len(start_parts) == 2:
                start_day, start_month = int(start_parts[0]), int(start_parts[1])
                start_date = date(current_year, start_month, start_day)
            else:
                return None
        else:
            return None
        
        # Парсим конечную дату
        if '.' in end_str:
            end_parts = end_str.split('.')
            if len(end_parts) == 2:
                end_day, end_month = int(end_parts[0]), int(end_parts[1])
                end_date = date(current_year, end_month, end_day)
            else:
                return None
        else:
            return None
        
        # Проверяем корректность периода
        if start_date > end_date:
            return None
        
        return (start_date, end_date)
    
    except Exception as e:
        logger.error(f"Error parsing period: {e}")
        return None


def parse_report_date_from_text(text: str) -> Optional[date]:
    if not text:
        return None

    cleaned = text.strip()
    
    # Проверяем короткий формат: 1.11 или 1,11 (день.месяц без года)
    short_pattern = r'^(\d{1,2})[.,/](\d{1,2})$'
    match = re.match(short_pattern, cleaned)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        current_year = datetime.now().year
        try:
            return date(current_year, month, day)
        except ValueError:
            pass
    
    # Пробуем стандартные форматы
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue

    # Попробуем найти дату в тексте
    tokens = re.findall(r"\d{1,4}[\.\-/,]\d{1,2}(?:[\.\-/,]\d{1,4})?", cleaned)
    for token in tokens:
        # Сначала пробуем короткий формат
        short_match = re.match(short_pattern, token)
        if short_match:
            day = int(short_match.group(1))
            month = int(short_match.group(2))
            current_year = datetime.now().year
            try:
                return date(current_year, month, day)
            except ValueError:
                continue
        
        # Потом полные форматы
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(token, fmt).date()
            except ValueError:
                continue
    return None


def format_report_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def decimal_to_str(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, Decimal):
        return format(value, '0.0f')
    try:
        return format(Decimal(str(value)), '0.0f')
    except Exception:
        return str(value)


def decimal_to_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except Exception:
        return None


async def send_main_menu_message(target_message):
    await target_message.reply_text(
        "Главное меню. Используйте кнопки ниже для выбора раздела:",
        reply_markup=get_main_reply_keyboard()
    )

    await target_message.reply_text(
        "Доступные действия:",
        reply_markup=get_main_menu_keyboard()
    )


async def send_files_menu_message(target_message):
    await target_message.reply_text(
        "Управление файлами:",
        reply_markup=get_files_keyboard()
    )


async def send_employees_menu_message(target_message):
    await target_message.reply_text(
        "Выберите действие:",
        reply_markup=get_employees_keyboard()
    )


async def generate_expenses_period_report(club_name: str, start_date: date, end_date: date):
    """Генерация сводного отчета по расходам за период"""
    from collections import defaultdict
    
    # Получаем все файлы за период
    files = db.get_files_by_period(start_date, end_date, club_name)
    
    if not files:
        return None
    
    # Словарь для суммирования: {expense_item: sum}
    expense_summary = defaultdict(Decimal)
    # Список для сохранения порядка статей расходов (берем из файла с максимумом статей)
    expense_order = []
    
    # ШАГ 1: Собираем ВСЕ уникальные статьи расходов из ВСЕХ файлов периода
    all_expenses_by_file = []
    
    for file_info in files:
        file_id = file_info['id']
        records = db.list_expense_records(file_id)
        
        file_expenses = []
        for rec in records:
            expense_item = rec.get('expense_item')
            amount = rec.get('amount') or Decimal('0')
            is_total = rec.get('is_total', False)
            
            if is_total:
                # Это итоговая строка - пропускаем, посчитаем сами
                continue
            
            # Суммируем
            expense_summary[expense_item] += amount
            
            # Запоминаем порядок для этого файла
            if expense_item not in file_expenses:
                file_expenses.append(expense_item)
        
        all_expenses_by_file.append(file_expenses)
    
    # ШАГ 2: Выбираем порядок из файла с максимумом статей расходов
    if all_expenses_by_file:
        expense_order = max(all_expenses_by_file, key=len)
    
    # ШАГ 3: Добавляем статьи, которые есть в других файлах, но нет в expense_order
    for file_expenses in all_expenses_by_file:
        for expense in file_expenses:
            if expense not in expense_order:
                expense_order.append(expense)
    
    # ШАГ 4: Формируем список для вывода
    display_rows = []
    total_amount = Decimal('0')
    
    for expense_item in expense_order:
        amt = expense_summary.get(expense_item, Decimal('0'))
        total_amount += amt
        
        display_rows.append({
            'Статья расхода': expense_item,
            'Сумма': decimal_to_float(amt)
        })
    
    # Добавляем ИТОГО
    display_rows.append({
        'Статья расхода': 'ИТОГО',
        'Сумма': decimal_to_float(total_amount)
    })
    
    return display_rows, total_amount


async def generate_staff_statistics_period_report(club_name: str, start_date: date, end_date: date):
    """Генерация сводного отчета по статистике персонала за период"""
    from collections import defaultdict
    
    # Получаем все файлы за период
    files = db.get_files_by_period(start_date, end_date, club_name)
    
    if not files:
        return None
    
    # Словарь для суммирования: {role_name: sum}
    staff_summary = defaultdict(int)
    # Список для сохранения порядка должностей (берем из файла с максимумом должностей)
    role_order = []
    
    # ШАГ 1: Собираем ВСЕ уникальные должности из ВСЕХ файлов периода
    all_roles_by_file = []
    
    for file_info in files:
        file_id = file_info['id']
        records = db.list_staff_statistics(file_id)
        
        file_roles = []
        for rec in records:
            role_name = rec.get('role_name')
            staff_count = rec.get('staff_count') or 0
            
            # Суммируем
            staff_summary[role_name] += staff_count
            
            # Запоминаем порядок для этого файла
            if role_name not in file_roles:
                file_roles.append(role_name)
        
        all_roles_by_file.append(file_roles)
    
    # ШАГ 2: Выбираем порядок из файла с максимумом должностей
    if all_roles_by_file:
        role_order = max(all_roles_by_file, key=len)
    
    # ШАГ 3: Добавляем должности, которые есть в других файлах, но нет в role_order
    for file_roles in all_roles_by_file:
        for role in file_roles:
            if role not in role_order:
                role_order.append(role)
    
    # ШАГ 4: Формируем список для вывода
    display_rows = []
    total_count = 0
    
    for role_name in role_order:
        count = staff_summary.get(role_name, 0)
        total_count += count
        
        display_rows.append({
            'Должность': role_name,
            'Количество': count
        })
    
    # Добавляем ИТОГО
    display_rows.append({
        'Должность': 'ИТОГО',
        'Количество': total_count
    })
    
    return display_rows, total_count


async def generate_payment_types_period_report(club_name: str, start_date: date, end_date: date):
    """Генерация сводного отчета по типам оплат за период"""
    from collections import defaultdict
    
    # Получаем все файлы за период
    files = db.get_files_by_period(start_date, end_date, club_name)
    
    if not files:
        return None
    
    # Словарь для суммирования: {payment_type: sum}
    payment_summary = defaultdict(Decimal)
    # Список для сохранения порядка типов оплат (берем из файла с максимумом типов)
    payment_order = []
    
    # ШАГ 1: Собираем ВСЕ уникальные типы оплат из ВСЕХ файлов периода
    all_payments_by_file = []
    
    for file_info in files:
        file_id = file_info['id']
        records = db.list_payment_types(file_id)
        
        file_payments = []
        for rec in records:
            payment_type = rec.get('payment_type')
            amount = rec.get('amount') or Decimal('0')
            is_total = rec.get('is_total', False)
            
            if is_total:
                # Это итоговая строка - пропускаем, посчитаем сами
                continue
            
            # Суммируем
            payment_summary[payment_type] += amount
            
            # Запоминаем порядок для этого файла
            if payment_type not in file_payments:
                file_payments.append(payment_type)
        
        all_payments_by_file.append(file_payments)
    
    # ШАГ 2: Выбираем порядок из файла с максимумом типов оплат
    if all_payments_by_file:
        payment_order = max(all_payments_by_file, key=len)
    
    # ШАГ 3: Добавляем типы, которые есть в других файлах, но нет в payment_order
    for file_payments in all_payments_by_file:
        for payment in file_payments:
            if payment not in payment_order:
                payment_order.append(payment)
    
    # ШАГ 4: Формируем список для вывода
    display_rows = []
    total_amount = Decimal('0')
    
    for payment_type in payment_order:
        amt = payment_summary.get(payment_type, Decimal('0'))
        total_amount += amt
        
        display_rows.append({
            'Тип оплаты': payment_type,
            'Сумма': decimal_to_float(amt)
        })
    
    # Добавляем ИТОГО
    display_rows.append({
        'Тип оплаты': 'ИТОГО',
        'Сумма': decimal_to_float(total_amount)
    })
    
    return display_rows, total_amount


async def generate_tickets_period_report(club_name: str, start_date: date, end_date: date):
    """Генерация сводного отчета по входным билетам за период"""
    from collections import defaultdict
    
    # Получаем все файлы за период
    files = db.get_files_by_period(start_date, end_date, club_name)
    
    if not files:
        return None
    
    # Словарь для суммирования: {price_label: {'quantity': sum, 'amount': sum}}
    tickets_summary = defaultdict(lambda: {'quantity': 0, 'amount': Decimal('0')})
    # Список для сохранения порядка цен (берем из файла с максимумом цен)
    price_order = []
    
    # ШАГ 1: Собираем ВСЕ уникальные цены из ВСЕХ файлов периода
    all_prices_by_file = []
    total_quantity = 0
    total_amount = Decimal('0')
    
    for file_info in files:
        file_id = file_info['id']
        records = db.list_ticket_sales(file_id)
        
        file_prices = []
        for rec in records:
            price_label = rec.get('price_label')
            quantity = rec.get('quantity') or 0
            amount = rec.get('amount') or Decimal('0')
            is_total = rec.get('is_total', False)
            
            if is_total:
                # Это итоговая строка - пропускаем в суммировании, посчитаем сами
                continue
            
            # Суммируем
            tickets_summary[price_label]['quantity'] += quantity
            tickets_summary[price_label]['amount'] += amount
            
            # Запоминаем порядок для этого файла
            if price_label not in file_prices:
                file_prices.append(price_label)
        
        all_prices_by_file.append(file_prices)
    
    # ШАГ 2: Выбираем порядок из файла с максимумом цен
    if all_prices_by_file:
        price_order = max(all_prices_by_file, key=len)
    
    # ШАГ 3: Добавляем цены, которые есть в других файлах, но нет в price_order
    for file_prices in all_prices_by_file:
        for price in file_prices:
            if price not in price_order:
                price_order.append(price)
    
    # ШАГ 4: Формируем список для вывода
    display_rows = []
    for price_label in price_order:
        if price_label in tickets_summary:
            qty = tickets_summary[price_label]['quantity']
            amt = tickets_summary[price_label]['amount']
            total_quantity += qty
            total_amount += amt
            
            display_rows.append({
                'Цена': price_label,
                'Количество': qty,
                'Сумма': decimal_to_float(amt)
            })
    
    # Добавляем ИТОГО
    display_rows.append({
        'Цена': 'ИТОГО',
        'Количество': total_quantity,
        'Сумма': decimal_to_float(total_amount)
    })
    
    return display_rows, total_quantity, total_amount


async def generate_income_period_report(club_name: str, start_date: date, end_date: date):
    """Генерация сводного отчета по доходам за период"""
    from collections import defaultdict
    
    # Получаем все файлы за период
    files = db.get_files_by_period(start_date, end_date, club_name)
    
    if not files:
        return None
    
    # Словарь для суммирования: {категория: сумма}
    income_summary = defaultdict(Decimal)
    # Список для сохранения порядка категорий (берем из первого файла который имеет максимум категорий)
    category_order = []
    
    # ШАГ 1: Собираем ВСЕ уникальные категории из ВСЕХ файлов периода и запоминаем порядок
    all_categories_by_file = []
    for file_info in files:
        file_id = file_info['id']
        records = db.list_income_records(file_id)
        
        file_categories = []
        for rec in records:
            category = rec['category']
            amount = rec['amount']
            
            # Суммируем
            income_summary[category] += amount
            
            # Запоминаем порядок для этого файла
            if category not in file_categories:
                file_categories.append(category)
        
        all_categories_by_file.append(file_categories)
    
    # ШАГ 2: Выбираем порядок из файла, у которого больше всего категорий (наиболее полный)
    if all_categories_by_file:
        category_order = max(all_categories_by_file, key=len)
    
    # ШАГ 3: Добавляем категории, которые есть в других файлах, но нет в category_order
    for file_cats in all_categories_by_file:
        for cat in file_cats:
            if cat not in category_order:
                category_order.append(cat)
    
    # ШАГ 4: Формируем список для вывода В ПРАВИЛЬНОМ ПОРЯДКЕ
    # ВАЖНО: Показываем ВСЕ категории, даже если сумма = 0!
    display_rows = []
    for category in category_order:
        display_rows.append({
            'Категория': category,
            'Сумма за период': decimal_to_float(income_summary.get(category, Decimal('0')))
        })
    
    return display_rows


async def send_queries_menu_message(target_message, context=None):
    # Сначала предлагаем выбрать клуб
    await target_message.reply_text(
        "📊 Выберите клуб для просмотра отчётов:",
        reply_markup=get_club_selection_keyboard()
    )


async def send_report_dates_menu(target_message, context=None):
    club_name = context.user_data.get('current_club') if context else None
    dates = db.get_report_dates(club_name=club_name)
    if not dates:
        club_text = f" для клуба {club_name}" if club_name and club_name != 'Оба' else ""
        await target_message.reply_text(
            f"📭 Пока нет отчётов{club_text} с установленной датой. Загрузите файл и укажите дату."
        )
        return

    club_text = f" ({club_name})" if club_name else ""
    await target_message.reply_text(
        f"📅 Выберите дату отчёта{club_text}:",
        reply_markup=get_query_dates_keyboard(dates)
    )


async def send_blocks_menu_message(target_message, report_date: date):
    await target_message.reply_text(
        f"Дата отчёта: {format_report_date(report_date)}\nВыберите блок:",
        reply_markup=get_blocks_keyboard(report_date)
    )


async def send_report_block_data(target_message, report_date: date, block_id: str, context=None):
    club_name = context.user_data.get('current_club') if context else None
    file_info = db.get_file_by_report_date(report_date, club_name=club_name)
    if not file_info:
        await target_message.reply_text("⚠️ Отчёт на эту дату не найден.")
        return

    file_id = file_info['id']
    stored_club_name = file_info.get('club_name', 'Неизвестно')
    club_label = stored_club_name if stored_club_name else 'Неизвестно'
    if club_name == 'Оба':
        club_label = f"Сводный ({stored_club_name})"
    
    block_label = next((label for bid, label in QUERY_BLOCKS if bid == block_id), block_id)

    if block_id == 'income':
        records = db.list_income_records(file_id)
        if not records:
            await target_message.reply_text("📭 Нет данных по доходам для этой даты.")
            return
        
        # Отладка: проверим, что приходит из базы
        logger.info(f"Income records from DB: {records}")
        
        lines = [f"💰 Доходы ({format_report_date(report_date)}) - {club_label}:"]
        display_rows = []
        for rec in records:
            amount_val = rec.get('amount')
            logger.info(f"Processing record: category={rec.get('category')}, amount={amount_val}, type={type(amount_val)}")
            lines.append(f"• {rec['category']}: {decimal_to_str(rec['amount'])}")
            display_rows.append({
                'Категория': rec['category'],
                'Сумма': decimal_to_float(rec['amount'])
            })
        await target_message.reply_text("\n".join(lines))
        excel_bytes = excel_processor.export_to_excel_with_header(display_rows, report_date, f"Доходы - {club_label}", club_label)
        await target_message.reply_document(excel_bytes, filename=f"доходы_{club_label}_{format_report_date(report_date)}.xlsx", caption=f"📅 Дата: {format_report_date(report_date)} | Клуб: {club_label}")
        return

    if block_id == 'tickets':
        records = db.list_ticket_sales(file_id)
        if not records:
            await target_message.reply_text("📭 Нет данных по входным билетам для этой даты.")
            return
        lines = [f"🎟 Входные билеты ({format_report_date(report_date)}) - {club_label}:"]
        display_rows = []
        total_quantity = 0
        total_amount = Decimal('0')
        
        for rec in records:
            label = rec.get('price_label')
            quantity = rec.get('quantity') or 0
            amount = rec.get('amount') or Decimal('0')
            is_total = rec.get('is_total', False)
            
            if is_total:
                # Это итоговая строка
                total_quantity = quantity
                total_amount = amount
            else:
                lines.append(
                    f"• {label}: количество {quantity}, сумма {decimal_to_str(amount)}"
                )
            
            display_rows.append({
                'Цена': label,
                'Количество': quantity,
                'Сумма': decimal_to_float(amount)
            })
        
        # Добавляем итого в конце
        if total_quantity > 0 or total_amount > 0:
            lines.append(f"\n📊 ИТОГО: {total_quantity} билетов, сумма {decimal_to_str(total_amount)}")
        
        await target_message.reply_text("\n".join(lines))
        
        excel_bytes = excel_processor.export_to_excel_with_header(display_rows, report_date, f"Входные билеты - {club_label}", club_label)
        await target_message.reply_document(excel_bytes, filename=f"входные_билеты_{club_label}_{format_report_date(report_date)}.xlsx", caption=f"📅 Дата: {format_report_date(report_date)} | Клуб: {club_label}")
        return

    if block_id == 'payments':
        records = db.list_payment_types(file_id)
        if not records:
            await target_message.reply_text("📭 Нет данных по типам оплат для этой даты.")
            return
        lines = [f"💳 Типы оплат ({format_report_date(report_date)}) - {club_label}:"]
        display_rows = []
        for rec in records:
            label = rec['payment_type']
            lines.append(f"• {label}: {decimal_to_str(rec['amount'])}")
            display_rows.append({
                'Тип оплаты': label,
                'Сумма': decimal_to_float(rec['amount'])
            })
        await target_message.reply_text("\n".join(lines))
        excel_bytes = excel_processor.export_to_excel_with_header(display_rows, report_date, f"Типы оплат - {club_label}", club_label)
        await target_message.reply_document(excel_bytes, filename=f"типы_оплат_{club_label}_{format_report_date(report_date)}.xlsx", caption=f"📅 Дата: {format_report_date(report_date)} | Клуб: {club_label}")
        return

    if block_id == 'staff':
        records = db.list_staff_statistics(file_id)
        if not records:
            await target_message.reply_text("📭 Нет данных по персоналу для этой даты.")
            return
        lines = [f"👥 Статистика персонала ({format_report_date(report_date)}) - {club_label}:"]
        display_rows = []
        total_staff = 0
        for rec in records:
            lines.append(f"• {rec['role_name']}: {rec['staff_count']}")
            display_rows.append({
                'Должность': rec['role_name'],
                'Количество': rec['staff_count']
            })
            total_staff += rec['staff_count'] or 0
        
        # Добавляем ИТОГО в Excel
        display_rows.append({
            'Должность': 'ИТОГО',
            'Количество': total_staff
        })
        
        lines.append(f"Всего персонала: {total_staff}")
        await target_message.reply_text("\n".join(lines))
        excel_bytes = excel_processor.export_to_excel_with_header(display_rows, report_date, f"Статистика персонала - {club_label}", club_label)
        await target_message.reply_document(excel_bytes, filename=f"персонал_{club_label}_{format_report_date(report_date)}.xlsx", caption=f"📅 Дата: {format_report_date(report_date)} | Клуб: {club_label}")
        return

    if block_id == 'expenses':
        records = db.list_expense_records(file_id)
        if not records:
            await target_message.reply_text("📭 Нет данных по расходам для этой даты.")
            return
        lines = [f"💸 Расходы ({format_report_date(report_date)}) - {club_label}:"]
        display_rows = []
        total = Decimal('0.00')
        for rec in records:
            if rec['is_total']:
                total = rec['amount']
                # Добавляем ИТОГО в display_rows для Excel
                display_rows.append({
                    'Статья расхода': rec['expense_item'],
                    'Сумма': decimal_to_float(rec['amount'])
                })
                continue
            lines.append(f"• {rec['expense_item']}: {decimal_to_str(rec['amount'])}")
            display_rows.append({
                'Статья расхода': rec['expense_item'],
                'Сумма': decimal_to_float(rec['amount'])
            })
        lines.append(f"Итого: {decimal_to_str(total)}")
        await target_message.reply_text("\n".join(lines))
        excel_bytes = excel_processor.export_to_excel_with_header(display_rows, report_date, f"Расходы - {club_label}", club_label)
        await target_message.reply_document(excel_bytes, filename=f"расходы_{club_label}_{format_report_date(report_date)}.xlsx", caption=f"📅 Дата: {format_report_date(report_date)} | Клуб: {club_label}")
        return

    if block_id == 'cash':
        records = db.list_cash_collection(file_id)
        if not records:
            await target_message.reply_text("📭 Нет данных по инкассации для этой даты.")
            return
        lines = [f"🏦 Инкассация ({format_report_date(report_date)}) - {club_label}:"]
        display_rows = []
        total_amount = Decimal('0')
        
        for rec in records:
            is_total = rec.get('is_total', False)
            
            if is_total:
                # Это строка ИТОГО
                total_amount = rec['amount']
                display_rows.append({
                    'Валюта': rec['currency_label'],
                    'Количество': None,
                    'Курс': None,
                    'Сумма': decimal_to_float(rec['amount'])
                })
            else:
                lines.append(
                    f"• {rec['currency_label']}: количество {rec.get('quantity') or 0}, "
                    f"курс {decimal_to_str(rec.get('exchange_rate'))}, сумма {decimal_to_str(rec['amount'])}"
                )
                display_rows.append({
                    'Валюта': rec['currency_label'],
                    'Количество': rec.get('quantity'),
                    'Курс': decimal_to_float(rec.get('exchange_rate')),
                    'Сумма': decimal_to_float(rec['amount'])
                })
        
        # Добавляем итого в предпросмотр
        if total_amount > 0:
            lines.append(f"\n💰 ИТОГО: {decimal_to_str(total_amount)}")
        
        await target_message.reply_text("\n".join(lines))
        excel_bytes = excel_processor.export_to_excel_with_header(display_rows, report_date, f"Инкассация - {club_label}", club_label)
        await target_message.reply_document(excel_bytes, filename=f"инкассация_{club_label}_{format_report_date(report_date)}.xlsx", caption=f"📅 Дата: {format_report_date(report_date)} | Клуб: {club_label}")
        return

    if block_id == 'debts':
        records = db.list_staff_debts(file_id)
        if not records:
            await target_message.reply_text("📭 Нет данных по долгам персонала для этой даты.")
            return
        lines = [f"📌 Долги по персоналу ({format_report_date(report_date)}) - {club_label}:"]
        display_rows = []
        total_amount = Decimal('0')
        
        for rec in records:
            is_total = rec.get('is_total', False)
            
            if is_total:
                total_amount = rec['amount']
                # Добавляем ИТОГО в Excel
                display_rows.append({
                    'Тип долга': rec['debt_type'],
                    'Сумма': decimal_to_float(rec['amount'])
                })
            else:
                lines.append(f"• {rec['debt_type']}: {decimal_to_str(rec['amount'])}")
                display_rows.append({
                    'Тип долга': rec['debt_type'],
                    'Сумма': decimal_to_float(rec['amount'])
                })
        
        # Добавляем итого в предпросмотр
        if total_amount > 0:
            lines.append(f"\n💰 ИТОГО: {decimal_to_str(total_amount)}")
        
        await target_message.reply_text("\n".join(lines))
        excel_bytes = excel_processor.export_to_excel_with_header(display_rows, report_date, f"Долги по персоналу - {club_label}", club_label)
        await target_message.reply_document(excel_bytes, filename=f"долги_{club_label}_{format_report_date(report_date)}.xlsx", caption=f"📅 Дата: {format_report_date(report_date)} | Клуб: {club_label}")
        return

    if block_id == 'notes':
        records = db.list_notes_entries(file_id)
        if not records:
            await target_message.reply_text("📭 Нет примечаний для этой даты.")
            return
        
        # Разделяем записи на две колонки (нал и безнал)
        nal_records = [r for r in records if r['category'] == 'нал']
        beznal_records = [r for r in records if r['category'] == 'безнал']
        
        lines = [f"📝 Примечания ({format_report_date(report_date)}) - {club_label}:"]
        lines.append("\n💳 Долг безнал:")
        for rec in beznal_records:
            if rec.get('is_total'):
                lines.append(f"  {rec['entry_text']}")
            else:
                lines.append(f"  • {rec['entry_text']}")
        
        lines.append("\n💵 Долг нал:")
        for rec in nal_records:
            if rec.get('is_total'):
                lines.append(f"  {rec['entry_text']}")
            else:
                lines.append(f"  • {rec['entry_text']}")
        
        await target_message.reply_text("\n".join(lines))
        
        # Формируем Excel в две колонки КАК В ИСХОДНОМ ФАЙЛЕ
        # ЛЕВАЯ колонка = Долг безнал, ПРАВАЯ = Долг нал
        display_rows = []
        max_len = max(len(beznal_records), len(nal_records))
        
        for i in range(max_len):
            row = {}
            # ЛЕВАЯ колонка - безнал
            if i < len(beznal_records):
                row['Долг безнал:'] = beznal_records[i]['entry_text']
            else:
                row['Долг безнал:'] = ''
            
            # ПРАВАЯ колонка - нал
            if i < len(nal_records):
                row['Долг нал:'] = nal_records[i]['entry_text']
            else:
                row['Долг нал:'] = ''
            
            display_rows.append(row)
        
        excel_bytes = excel_processor.export_to_excel_with_header(display_rows, report_date, f"Примечания - {club_label}", club_label)
        await target_message.reply_document(excel_bytes, filename=f"примечания_{club_label}_{format_report_date(report_date)}.xlsx", caption=f"📅 Дата: {format_report_date(report_date)} | Клуб: {club_label}")
        return

    if block_id == 'totals':
        records = db.list_totals_summary(file_id)
        if not records:
            await target_message.reply_text("📭 Нет итогового баланса для этой даты.")
            return
        lines = [f"📊 Итоговый баланс ({format_report_date(report_date)}) - {club_label}:"]
        display_rows = []
        for rec in records:
            lines.append(
                f"• {rec['payment_type']}: доход {decimal_to_str(rec['income_amount'])}, "
                f"расход {decimal_to_str(rec['expense_amount'])}, чистая прибыль {decimal_to_str(rec['net_profit'])}"
            )
            display_rows.append({
                'Тип оплаты': rec['payment_type'],
                'Доход': decimal_to_float(rec['income_amount']),
                'Расход': decimal_to_float(rec['expense_amount']),
                'Чистая прибыль': decimal_to_float(rec['net_profit'])
            })
        await target_message.reply_text("\n".join(lines))
        excel_bytes = excel_processor.export_to_excel_with_header(display_rows, report_date, f"Итоговый баланс - {club_label}", club_label)
        await target_message.reply_document(excel_bytes, filename=f"итого_{club_label}_{format_report_date(report_date)}.xlsx", caption=f"📅 Дата: {format_report_date(report_date)} | Клуб: {club_label}")
        return

    await target_message.reply_text("⚠️ Неизвестный блок.")


async def setup_bot_commands(application: Application):
    commands = [
        BotCommand("start", "Главное меню"),
        BotCommand("moskvich", "🏢 Клуб Москвич"),
        BotCommand("anora", "🌟 Клуб Анора"),
        BotCommand("both", "📊 Оба клуба (просмотр)"),
        BotCommand("help", "Описание возможностей")
    ]
    await application.bot.set_my_commands(commands)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    if not update.message:
        return
    user_id = update.effective_user.id
    AUTHORIZED_USERS.discard(user_id)
    context.user_data.pop('authorized', None)
    await request_password(update.message, context)


async def moskvich_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор клуба Москвич"""
    if not user_is_authorized(update.effective_user.id, context):
        await request_password(update.message, context)
        return
    
    context.user_data['current_club'] = 'Москвич'
    await update.message.reply_text(
        "✅ Выбран клуб: Москвич\n\n"
        "Теперь вы можете:\n"
        "• Загружать отчеты для Москвича\n"
        "• Просматривать данные Москвича по датам и блокам\n\n"
        "Используйте кнопки меню для работы."
    )


async def anora_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор клуба Анора"""
    if not user_is_authorized(update.effective_user.id, context):
        await request_password(update.message, context)
        return
    
    context.user_data['current_club'] = 'Анора'
    await update.message.reply_text(
        "✅ Выбран клуб: Анора\n\n"
        "Теперь вы можете:\n"
        "• Загружать отчеты для Аноры\n"
        "• Просматривать данные Аноры по датам и блокам\n\n"
        "Используйте кнопки меню для работы."
    )


async def both_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Режим просмотра обоих клубов"""
    if not user_is_authorized(update.effective_user.id, context):
        await request_password(update.message, context)
        return
    
    context.user_data['current_club'] = 'Оба'
    await update.message.reply_text(
        "✅ Режим просмотра: Оба клуба\n\n"
        "Вы можете просматривать сводные данные по обоим клубам.\n\n"
        "⚠️ Загрузка файлов в этом режиме НЕДОСТУПНА!\n"
        "Для загрузки выберите конкретный клуб:\n"
        "• /moskvich - Москвич\n"
        "• /anora - Анора"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /help"""
    if not user_is_authorized(update.effective_user.id, context):
        await request_password(update.message, context)
        return

    await update.message.reply_text(build_help_text(), parse_mode='Markdown')


async def files_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not user_is_authorized(update.effective_user.id, context):
        await request_password(update.message, context)
        return

    await send_files_menu_message(update.message)


async def queries_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not user_is_authorized(update.effective_user.id, context):
        await request_password(update.message, context)
        return

    await send_queries_menu_message(update.message, context)


async def employees_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await employees_menu(update, context)


async def my_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список файлов пользователя"""
    if not user_is_authorized(update.effective_user.id, context):
        await request_password(update.message, context)
        return

    user_id = update.effective_user.id
    
    try:
        files = db.get_user_files(user_id)
        
        if not files:
            await update.message.reply_text("У вас пока нет загруженных файлов 📁")
            return
        
        message = "📂 **Ваши файлы:**\n\n"
        for i, file in enumerate(files, 1):
            upload_date = file['upload_date'].strftime("%d.%m.%Y %H:%M")
            message += f"{i}. **{file['file_name']}**\n"
            message += f"   📅 Загружен: {upload_date}\n"
            message += f"   📊 Строк: {file['row_count']}\n\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    except Exception as e:
        logger.error(f"Error getting user files: {e}")
        await update.message.reply_text("❌ Ошибка при получении списка файлов")


async def show_schema(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать схему базы данных"""
    if not user_is_authorized(update.effective_user.id, context):
        await request_password(update.message, context)
        return

    try:
        schema = db.get_database_schema()
        
        # Разбиваем на части если слишком длинное
        max_length = 4000
        if len(schema) > max_length:
            parts = [schema[i:i+max_length] for i in range(0, len(schema), max_length)]
            for part in parts:
                await update.message.reply_text(f"```\n{part}\n```", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"```\n{schema}\n```", parse_mode='Markdown')
    
    except Exception as e:
        logger.error(f"Error showing schema: {e}")
        await update.message.reply_text("❌ Ошибка при получении схемы БД")


async def debug_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отладочная команда для проверки данных в БД"""
    if not user_is_authorized(update.effective_user.id, context):
        await request_password(update.message, context)
        return

    try:
        # Проверяем последний файл
        latest_file = db.get_latest_file()
        if not latest_file:
            await update.message.reply_text("📭 Нет загруженных файлов")
            return
        
        file_id = latest_file['id']
        
        # Проверяем данные доходов
        income_recs = db.list_income_records(file_id)
        
        msg = f"🔍 Отладка данных файла: {latest_file['file_name']}\n"
        msg += f"File ID: {file_id}\n\n"
        msg += f"📊 Доходы ({len(income_recs)} записей):\n"
        
        for rec in income_recs[:5]:  # Показываем первые 5
            msg += f"• {rec['category']}: {rec['amount']} (тип: {type(rec['amount']).__name__})\n"
        
        if len(income_recs) > 5:
            msg += f"... и ещё {len(income_recs) - 5} записей\n"
        
        await update.message.reply_text(msg)
        
    except Exception as e:
        logger.error(f"Error in debug_data: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def show_excel_structure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать структуру Excel файла (первые 10 строк и 10 колонок)"""
    if not user_is_authorized(update.effective_user.id, context):
        await request_password(update.message, context)
        return
    
    if not update.message.document:
        await update.message.reply_text("📎 Отправьте Excel файл вместе с командой /structure")
        return
    
    try:
        import pandas as pd
        import io
        
        document = update.message.document
        file = await context.bot.get_file(document.file_id)
        file_content = await file.download_as_bytearray()
        
        df = pd.read_excel(io.BytesIO(file_content), sheet_name=0, header=None, engine='openpyxl')
        
        msg = f"📋 Структура файла {document.file_name}\n"
        msg += f"Размер: {df.shape[0]} строк × {df.shape[1]} колонок\n\n"
        msg += "Первые 10 строк и 10 колонок:\n\n"
        
        for row_idx in range(min(10, len(df))):
            msg += f"R{row_idx}: "
            row_data = []
            for col_idx in range(min(10, df.shape[1])):
                cell = df.iloc[row_idx, col_idx]
                if pd.isna(cell):
                    row_data.append("—")
                else:
                    cell_str = str(cell)[:15]  # Обрезаем длинные значения
                    row_data.append(cell_str)
            msg += " | ".join(row_data) + "\n"
        
        # Разбиваем на части если длинное
        if len(msg) > 4000:
            parts = [msg[i:i+4000] for i in range(0, len(msg), 4000)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(msg)
        
    except Exception as e:
        logger.error(f"Error in show_excel_structure: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def reprocess_last_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переобработать последний загруженный файл с новым парсером"""
    if not user_is_authorized(update.effective_user.id, context):
        await request_password(update.message, context)
        return
    
    try:
        user_id = update.effective_user.id
        
        # Получаем последний файл пользователя
        with db.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, file_name, row_count, report_date
                    FROM uploaded_files
                    WHERE user_id = %s
                    ORDER BY upload_date DESC
                    LIMIT 1
                    """,
                    (user_id,)
                )
                file_info = cur.fetchone()
        
        if not file_info:
            await update.message.reply_text("📭 У вас нет загруженных файлов")
            return
        
        file_id = file_info['id']
        file_name = file_info['file_name']
        
        # Читаем содержимое файла из базы
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT file_content FROM uploaded_files WHERE id = %s", (file_id,))
                result = cur.fetchone()
                if not result or not result[0]:
                    await update.message.reply_text("❌ Не удалось получить содержимое файла")
                    return
                file_content = result[0]
        
        await update.message.reply_text(f"🔄 Переобработка файла {file_name}...")
        
        # Переобрабатываем все блоки
        income_records = excel_processor.extract_income_records(file_content)
        if income_records:
            db.save_income_records(file_id, income_records)
            await update.message.reply_text(f"✅ Доходы: {len(income_records)} записей")
        
        ticket_sales_data = excel_processor.extract_ticket_sales(file_content)
        if ticket_sales_data.get('records'):
            db.save_ticket_sales(file_id, ticket_sales_data['records'])
            await update.message.reply_text(f"✅ Входные билеты: {len(ticket_sales_data['records'])} записей, итого: {ticket_sales_data.get('total_amount', 0)}")
        
        await update.message.reply_text("✅ Переобработка завершена! Теперь данные должны отображаться правильно.")
        
    except Exception as e:
        logger.error(f"Error in reprocess_last_file: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def employees_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню управления сотрудниками"""
    if not update.message:
        return

    if not user_is_authorized(update.effective_user.id, context):
        await request_password(update.message, context)
        return

    if update.message:
        await send_employees_menu_message(update.message)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка загруженного документа (Excel файл)"""
    if not user_is_authorized(update.effective_user.id, context):
        await request_password(update.message, context)
        return

    # Проверка выбора клуба
    current_club = context.user_data.get('current_club')
    
    if not current_club:
        await update.message.reply_text(
            "⚠️ Сначала выберите клуб!\n\n"
            "Используйте кнопки меню:\n"
            "• 🏢 Москвич\n"
            "• 🌟 Анора"
        )
        return
    
    if current_club == 'Оба':
        await update.message.reply_text(
            "❌ Загрузка файлов в режиме 'Оба клуба' недоступна!\n\n"
            "Для загрузки отчета выберите конкретный клуб:\n"
            "• 🏢 Москвич\n"
            "• 🌟 Анора"
        )
        return

    document = update.message.document
    user = update.effective_user
    
    # Проверка размера файла
    if document.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(
            f"❌ Файл слишком большой! Максимальный размер: {MAX_FILE_SIZE / 1024 / 1024:.0f} МБ"
        )
        return
    
    # Проверка формата файла
    if not excel_processor.validate_file(document.file_name):
        await update.message.reply_text(
            "❌ Неподдерживаемый формат файла!\n"
            "Поддерживаются: .xlsx, .xls, .xlsm, .csv"
        )
        return
    
    # Уведомление о начале обработки
    processing_msg = await update.message.reply_text("⏳ Обрабатываю файл...")
    
    try:
        # Скачивание файла
        file = await context.bot.get_file(document.file_id)
        file_content = await file.download_as_bytearray()

        caption_text = update.message.caption if update.message else None
        report_date = parse_report_date_from_text(caption_text) if caption_text else None

        # Обработка Excel файла
        data, stats = excel_processor.process_file(bytes(file_content), document.file_name)
        
        # Сохранение в БД с указанием клуба
        file_id = db.save_uploaded_file(
            user_id=user.id,
            username=user.username or user.first_name,
            file_name=document.file_name,
            file_content=bytes(file_content),
            row_count=len(data),
            report_date=report_date,
            club_name=current_club
        )
        
        db.save_excel_data(file_id, data)

        # Собираем все сообщения о блоках в один список
        summary_lines = []
        
        income_records = excel_processor.extract_income_records(bytes(file_content))
        if income_records:
            db.save_income_records(file_id, income_records)
            income_total = next(
                (record['amount'] for record in income_records if record['category'].strip().lower() == 'итого за смену'),
                None
            )
            if income_total is not None:
                total_str = format(income_total, '0.0f')
                summary_lines.append(f"💰 Блок 'Доходы' обработан. Итог за смену: {total_str}")
 
        ticket_sales_data = excel_processor.extract_ticket_sales(bytes(file_content))
        if ticket_sales_data.get('records'):
            db.save_ticket_sales(file_id, ticket_sales_data['records'])

            ticket_total_amount = ticket_sales_data.get('total_amount')

            if ticket_total_amount is not None:
                tickets_total_str = format(ticket_total_amount, '0.0f')
                summary_lines.append(f"🎟 Блок 'Входные билеты' обработан. Итого сумма: {tickets_total_str}")

        payment_types_data = excel_processor.extract_payment_types(bytes(file_content))
        if payment_types_data.get('records'):
            db.save_payment_types(file_id, payment_types_data['records'])

            payment_total = payment_types_data.get('reported_total') or Decimal('0.00')
            cash_total = payment_types_data.get('cash_total')
            
            msg_lines = ["💳 Блок 'Типы оплат' обработан."]
            if cash_total is not None:
                msg_lines.append(f"Итого касса: {format(cash_total, '0.0f')}")
            msg_lines.append(f"Итого: {format(payment_total, '0.0f')}")
            summary_lines.append("\n".join(msg_lines))

        staff_stats = excel_processor.extract_staff_statistics(bytes(file_content))
        if staff_stats:
            db.save_staff_statistics(file_id, staff_stats)
            total_staff = sum(item.get('staff_count', 0) for item in staff_stats)
            summary_lines.append(
                "👥 Блок 'Статистика персонала' обработан.\n"
                f"Всего персонала на смене: {total_staff}"
            )
 
        expense_data = excel_processor.extract_expense_records(bytes(file_content))
        if expense_data.get('records'):
            db.save_expense_records(file_id, expense_data['records'])

            expenses_total = expense_data.get('reported_total') or Decimal('0.00')
            income_total = None
            if income_records:
                income_total = next(
                    (record['amount'] for record in income_records if record['category'].strip().lower() == 'итого'),
                    None
                )

            msg_lines = ["💸 Блок 'Расходы' обработан."]
            msg_lines.append(f"Итого расходы: {format(expenses_total, '0.0f')}")

            if income_total is not None:
                balance = income_total - expenses_total
                msg_lines.append(f"Финансовый результат (Итого доходы - Расходы): {format(balance, '0.0f')}")

            summary_lines.append("\n".join(msg_lines))

        staff_debts_data = excel_processor.extract_staff_debts(bytes(file_content))
        if staff_debts_data.get('records'):
            db.save_staff_debts(file_id, staff_debts_data['records'])

            debts_total = staff_debts_data.get('reported_total') or Decimal('0.00')
            summary_lines.append(
                "📌 Блок 'Долги по персоналу' обработан.\n"
                f"Итого задолженность: {format(debts_total, '0.0f')}"
            )
        else:
            staff_debts_data = {}
 
        cash_collection_data = excel_processor.extract_cash_collection(bytes(file_content))
        if cash_collection_data.get('records'):
            db.save_cash_collection(file_id, cash_collection_data['records'])
 
            collection_total = cash_collection_data.get('reported_total') or Decimal('0.00')
            summary_lines.append(
                "🏦 Блок 'Инкассация' обработан.\n"
                f"Итого наличных после смены: {format(collection_total, '0.0f')}"
            )
 
        notes_data = excel_processor.extract_notes_entries(bytes(file_content))
        if notes_data:
            notes_records = []

            for entry in notes_data.get('безнал', []):
                notes_records.append({
                    'category': entry.get('category', 'безнал'),
                    'entry_text': entry.get('entry_text', ''),
                    'is_total': entry.get('is_total', False),
                    'amount': entry.get('amount')
                })

            for entry in notes_data.get('нал', []):
                notes_records.append({
                    'category': entry.get('category', 'нал'),
                    'entry_text': entry.get('entry_text', ''),
                    'is_total': entry.get('is_total', False),
                    'amount': entry.get('amount')
                })

            for text in notes_data.get('extra', []):
                notes_records.append({
                    'category': 'прочее',
                    'entry_text': text,
                    'is_total': False,
                    'amount': None
                })

            if notes_records:
                db.save_notes_entries(file_id, notes_records)

            summary_lines.append("📝 Блок 'Примечание' сохранён.")

        totals_summary = excel_processor.extract_totals_summary(bytes(file_content))
        if totals_summary:
            db.save_totals_summary(file_id, totals_summary)
            summary_lines.append("📊 Блок 'Итого' обработан.")

        # Отправка единого сообщения с итогами по всем блокам
        final_summary = "✅ Файл успешно обработан и сохранен!\n\n" + "\n\n".join(summary_lines)
        await processing_msg.edit_text(final_summary)
        
        if report_date is None:
            context.user_data['awaiting_report_date'] = {'file_id': file_id}
            await update.message.reply_text(
                "🗓 Укажите дату отчёта в формате ГГГГ-ММ-ДД или ДД.ММ.ГГГГ"
            )

        # Предложение действий
        keyboard = [
            [InlineKeyboardButton("📊 Мои файлы", callback_data="my_files")],
            [InlineKeyboardButton("🔍 Задать вопрос", callback_data="ask_question")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Что дальше?",
            reply_markup=reply_markup
        )
    
    except Exception as e:
        logger.error(f"Error processing document: {e}")
        await processing_msg.edit_text(
            f"❌ Ошибка при обработке файла:\n{str(e)}"
        )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    user_message = update.message.text
    user_id = update.effective_user.id

    if not user_is_authorized(user_id, context):
        if context.user_data.get('awaiting_password'):
            if user_message.strip() == ACCESS_PASSWORD:
                set_authorized(user_id, context)
                await update.message.reply_text("✅ Доступ разрешён.")
                await send_main_menu_message(update.message)
            else:
                await update.message.reply_text("❌ Неверный пароль. Попробуйте снова.")
        else:
            await request_password(update.message, context)
        return

    if context.user_data.get('awaiting_report_date'):
        pending = context.user_data['awaiting_report_date']
        report_date = parse_report_date_from_text(user_message)
        if report_date is None:
            await update.message.reply_text(
                "❌ Не удалось распознать дату. Используйте формат ГГГГ-ММ-ДД или ДД.ММ.ГГГГ"
            )
            return

        db.set_uploaded_file_report_date(pending['file_id'], report_date)
        context.user_data.pop('awaiting_report_date', None)
        await update.message.reply_text(
            f"🗓 Дата отчёта установлена: {format_report_date(report_date)}"
        )
        return

    if user_message.strip() == BUTTON_FILES:
        await send_files_menu_message(update.message)
        return

    if user_message.strip() == BUTTON_QUERIES:
        await send_queries_menu_message(update.message, context)
        return

    if user_message.strip() == BUTTON_REPORTS:
        # Начинаем процесс формирования отчета
        await update.message.reply_text(
            "📊 Формирование сводного отчета\n\n"
            "Выберите клуб:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏢 Москвич", callback_data="report_club|Москвич")],
                [InlineKeyboardButton("🌟 Анора", callback_data="report_club|Анора")],
                [InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")]
            ])
        )
        return

    if user_message.strip() == BUTTON_EMPLOYEES:
        await send_employees_menu_message(update.message)
        return

    if user_message.strip() == BUTTON_HELP:
        await update.message.reply_text(build_help_text(), parse_mode='Markdown')
        return
    
    # Обработка ввода периода для отчета
    if context.user_data.get('awaiting_report_period'):
        club_name = context.user_data.get('report_club')
        block_id = context.user_data.get('report_block', 'income')
        period = parse_period_from_text(user_message)
        
        if period is None:
            await update.message.reply_text(
                "❌ Неверный формат периода!\n\n"
                "Используйте формат: 1.11-5.12 или 1,11-5,12\n"
                "Попробуйте еще раз:"
            )
            return
        
        start_date, end_date = period
        context.user_data.pop('awaiting_report_period', None)
        context.user_data.pop('report_block', None)
        
        try:
            # Выбираем функцию генерации в зависимости от блока
            if block_id == 'expenses':
                processing_msg = await update.message.reply_text("⏳ Формирую сводный отчет по расходам...")
                
                result = await generate_expenses_period_report(club_name, start_date, end_date)
                
                if not result:
                    await processing_msg.edit_text(
                        f"📭 Нет данных за период {format_report_date(start_date)} - {format_report_date(end_date)}"
                    )
                    return
                
                report_data, total_amount = result
                
                # Формируем предпросмотр
                lines = [f"💸 Расходы за период {format_report_date(start_date)} - {format_report_date(end_date)} ({club_name}):\n"]
                
                for row in report_data:
                    expense_item = row['Статья расхода']
                    amt = Decimal(str(row['Сумма']))
                    
                    if 'итого' in str(expense_item).lower():
                        lines.append(f"\n📊 {expense_item}: {decimal_to_str(amt)}")
                    else:
                        lines.append(f"• {expense_item}: {decimal_to_str(amt)}")
                
                await processing_msg.edit_text("\n".join(lines))
                
                # Отправляем Excel файл
                excel_bytes = excel_processor.export_period_report_to_excel(
                    report_data, club_name, start_date, end_date, "Расходы"
                )
                
                filename = f"расходы_{club_name}_{start_date.strftime('%d.%m')}-{end_date.strftime('%d.%m')}.xlsx"
                await update.message.reply_document(
                    excel_bytes,
                    filename=filename,
                    caption=f"📊 Сводный отчет: Расходы\n📅 Период: {format_report_date(start_date)} - {format_report_date(end_date)}\n🏢 Клуб: {club_name}"
                )
            
            elif block_id == 'staff':
                processing_msg = await update.message.reply_text("⏳ Формирую сводный отчет по персоналу...")
                
                result = await generate_staff_statistics_period_report(club_name, start_date, end_date)
                
                if not result:
                    await processing_msg.edit_text(
                        f"📭 Нет данных за период {format_report_date(start_date)} - {format_report_date(end_date)}"
                    )
                    return
                
                report_data, total_count = result
                
                # Формируем предпросмотр
                lines = [f"👥 Статистика персонала за период {format_report_date(start_date)} - {format_report_date(end_date)} ({club_name}):\n"]
                
                for row in report_data:
                    role_name = row['Должность']
                    count = row['Количество']
                    
                    if 'итого' in str(role_name).lower():
                        lines.append(f"\n📊 {role_name}: {count}")
                    else:
                        lines.append(f"• {role_name}: {count}")
                
                await processing_msg.edit_text("\n".join(lines))
                
                # Отправляем Excel файл
                excel_bytes = excel_processor.export_period_report_to_excel(
                    report_data, club_name, start_date, end_date, "Статистика персонала"
                )
                
                filename = f"персонал_{club_name}_{start_date.strftime('%d.%m')}-{end_date.strftime('%d.%m')}.xlsx"
                await update.message.reply_document(
                    excel_bytes,
                    filename=filename,
                    caption=f"📊 Сводный отчет: Статистика персонала\n📅 Период: {format_report_date(start_date)} - {format_report_date(end_date)}\n🏢 Клуб: {club_name}"
                )
            
            elif block_id == 'payments':
                processing_msg = await update.message.reply_text("⏳ Формирую сводный отчет по типам оплат...")
                
                result = await generate_payment_types_period_report(club_name, start_date, end_date)
                
                if not result:
                    await processing_msg.edit_text(
                        f"📭 Нет данных за период {format_report_date(start_date)} - {format_report_date(end_date)}"
                    )
                    return
                
                report_data, total_amount = result
                
                # Формируем предпросмотр
                lines = [f"💳 Типы оплат за период {format_report_date(start_date)} - {format_report_date(end_date)} ({club_name}):\n"]
                
                for row in report_data:
                    payment_type = row['Тип оплаты']
                    amt = Decimal(str(row['Сумма']))
                    
                    if 'итого' in str(payment_type).lower():
                        lines.append(f"\n📊 {payment_type}: {decimal_to_str(amt)}")
                    else:
                        lines.append(f"• {payment_type}: {decimal_to_str(amt)}")
                
                await processing_msg.edit_text("\n".join(lines))
                
                # Отправляем Excel файл
                excel_bytes = excel_processor.export_period_report_to_excel(
                    report_data, club_name, start_date, end_date, "Типы оплат"
                )
                
                filename = f"типы_оплат_{club_name}_{start_date.strftime('%d.%m')}-{end_date.strftime('%d.%m')}.xlsx"
                await update.message.reply_document(
                    excel_bytes,
                    filename=filename,
                    caption=f"📊 Сводный отчет: Типы оплат\n📅 Период: {format_report_date(start_date)} - {format_report_date(end_date)}\n🏢 Клуб: {club_name}"
                )
            
            elif block_id == 'tickets':
                processing_msg = await update.message.reply_text("⏳ Формирую сводный отчет по входным билетам...")
                
                result = await generate_tickets_period_report(club_name, start_date, end_date)
                
                if not result:
                    await processing_msg.edit_text(
                        f"📭 Нет данных за период {format_report_date(start_date)} - {format_report_date(end_date)}"
                    )
                    return
                
                report_data, total_quantity, total_amount = result
                
                # Формируем предпросмотр
                lines = [f"🎟 Входные билеты за период {format_report_date(start_date)} - {format_report_date(end_date)} ({club_name}):\n"]
                
                for row in report_data:
                    price = row['Цена']
                    qty = row['Количество']
                    amt = Decimal(str(row['Сумма']))
                    
                    if 'итого' in str(price).lower():
                        lines.append(f"\n📊 {price}: {qty} билетов, сумма {decimal_to_str(amt)}")
                    else:
                        lines.append(f"• {price}: количество {qty}, сумма {decimal_to_str(amt)}")
                
                await processing_msg.edit_text("\n".join(lines))
                
                # Отправляем Excel файл
                excel_bytes = excel_processor.export_period_report_to_excel(
                    report_data, club_name, start_date, end_date, "Входные билеты"
                )
                
                filename = f"билеты_{club_name}_{start_date.strftime('%d.%m')}-{end_date.strftime('%d.%m')}.xlsx"
                await update.message.reply_document(
                    excel_bytes,
                    filename=filename,
                    caption=f"📊 Сводный отчет: Входные билеты\n📅 Период: {format_report_date(start_date)} - {format_report_date(end_date)}\n🏢 Клуб: {club_name}"
                )
            
            else:  # income (по умолчанию)
                processing_msg = await update.message.reply_text("⏳ Формирую сводный отчет по доходам...")
                
                report_data = await generate_income_period_report(club_name, start_date, end_date)
                
                if not report_data:
                    await processing_msg.edit_text(
                        f"📭 Нет данных за период {format_report_date(start_date)} - {format_report_date(end_date)}"
                    )
                    return
                
                # Формируем предпросмотр
                lines = [f"💰 Доходы за период {format_report_date(start_date)} - {format_report_date(end_date)} ({club_name}):"]
                
                for row in report_data:
                    category = row['Категория']
                    amount = Decimal(str(row['Сумма за период']))
                    lines.append(f"• {category}: {decimal_to_str(amount)}")
                
                await processing_msg.edit_text("\n".join(lines))
                
                # Отправляем Excel файл
                excel_bytes = excel_processor.export_period_report_to_excel(
                    report_data, club_name, start_date, end_date, "Доходы"
                )
                
                filename = f"доходы_{club_name}_{start_date.strftime('%d.%m')}-{end_date.strftime('%d.%m')}.xlsx"
                await update.message.reply_document(
                    excel_bytes,
                    filename=filename,
                    caption=f"📊 Сводный отчет: Доходы\n📅 Период: {format_report_date(start_date)} - {format_report_date(end_date)}\n🏢 Клуб: {club_name}"
                )
            
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            await update.message.reply_text(f"❌ Ошибка при формировании отчета: {str(e)}")
        
        return

    if context.user_data.get('employee_action'):
        await handle_employee_text_action(update, context, user_message)
        return

    if context.user_data.get('query_action') == 'search_column':
        await handle_search_query_input(update, context, user_message)
        return

    parser_result = query_parser.parse(user_message)
    action = parser_result.get('action')

    if action == 'count_records':
        await send_excel_record_count(update.message)
    elif action == 'list_files':
        await send_recent_files(update.message)
    elif action == 'latest_records':
        await send_latest_records(update.message)
    elif action == 'request_search_input':
        context.user_data['query_action'] = 'search_column'
        await update.message.reply_text(
            "Введите условие в формате `колонка=значение`",
            parse_mode='Markdown'
        )
    elif action == 'search_by_column':
        column = parser_result.get('column')
        value = parser_result.get('value')
        if column and value:
            await send_search_results(update.message, column, value)
        else:
            await update.message.reply_text(
                "❌ Не удалось распознать колонку и значение. Используйте формат `колонка=значение`.",
                parse_mode='Markdown'
            )
    else:
        await update.message.reply_text(
            "Я пока понимаю только простые запросы (количество записей, список файлов, поиск колонка=значение)."
        )
        await send_main_menu_message(update.message)


def normalize_column_name(column: str) -> str:
    return re.sub(r"\s+", "_", column.strip()).lower()


async def send_excel_record_count(target_message):
    count = db.count_excel_records()
    await target_message.reply_text(f"🔢 Записей в данных Excel: {count}")


async def send_recent_files(target_message):
    files = db.list_recent_files()

    if not files:
        await target_message.reply_text(
            "📭 Загрузите хотя бы один файл, чтобы увидеть список",
            reply_markup=get_files_keyboard()
        )
        return

    lines = ["📂 **Последние файлы:**\n"]
    for item in files:
        upload_date = item['upload_date'].strftime("%d.%m.%Y %H:%M") if item.get('upload_date') else "—"
        report_date = format_report_date(item['report_date']) if item.get('report_date') else "—"
        lines.append(
            f"• {item['file_name']} (строк: {item['row_count']}, дата отчёта: {report_date}, загружен: {upload_date})"
        )

    await target_message.reply_text(
        "\n".join(lines),
        parse_mode='Markdown',
        reply_markup=get_files_keyboard()
    )


def format_row_data(row_data: Dict[str, Any]) -> str:
    parts = []
    for key, value in row_data.items():
        parts.append(f"{key}: {value}")
    return "; ".join(parts)


async def send_latest_records(target_message, limit: int = 5):
    latest = db.get_latest_file()

    if not latest:
        await target_message.reply_text("📭 Пока нет загруженных файлов")
        return

    preview = db.get_file_preview(latest['id'], limit=limit)

    if not preview:
        await target_message.reply_text("⚠️ Не удалось получить данные последнего файла")
        return

    lines = [
        f"📄 **Предпросмотр файла {latest['file_name']} (первые {len(preview)} строк):**",
        ""
    ]

    for row in preview:
        lines.append(f"№{row['row_number']}: {format_row_data(row['data'])}")

    await target_message.reply_text(
        "\n".join(lines),
        parse_mode='Markdown',
        reply_markup=get_files_keyboard()
    )


async def send_search_results(target_message, column: str, value: str):
    normalized_column = normalize_column_name(column)
    matches = db.search_excel_by_column(normalized_column, value, limit=10)

    if not matches:
        await target_message.reply_text(
            f"ℹ️ Ничего не найдено по колонке `{normalized_column}` со значением `{value}`",
            parse_mode='Markdown'
        )
        return

    lines = [f"🔍 Результаты поиска по `{normalized_column}` содержит `{value}`:", ""]

    for item in matches:
        lines.append(
            f"📁 {item['file_name']} — строка {item['row_number']}"
        )
        lines.append(format_row_data(item['data']))
        lines.append("")

    await target_message.reply_text("\n".join(lines), parse_mode='Markdown')


async def handle_search_query_input(update: Update, context: ContextTypes.DEFAULT_TYPE, user_message: str):
    match = query_parser.COLUMN_VALUE_PATTERN.search(user_message)
    if match:
        column = match.group('column').strip()
        value = match.group('value').strip()
        await send_search_results(update.message, column, value)
        context.user_data.pop('query_action', None)
    else:
        await update.message.reply_text(
            "❌ Формат не распознан. Используйте пример: `колонка=значение`",
            parse_mode='Markdown'
        )


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на inline кнопки"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if not user_is_authorized(user_id, context):
        await query.message.reply_text("🔐 Сначала авторизуйтесь, отправив пароль.")
        context.user_data['awaiting_password'] = True
        return

    data = query.data or ""

    if data == "main_menu":
        await send_main_menu_message(query.message)

    elif data == "main_files":
        await send_files_menu_message(query.message)

    elif data in {"files_list", "my_files"}:
        await send_recent_files(query.message)

    elif data == "files_dates_by_club":
        # Показываем выбор клуба для просмотра дат
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏢 Москвич", callback_data="dates_club|Москвич")],
            [InlineKeyboardButton("🌟 Анора", callback_data="dates_club|Анора")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="files_menu")]
        ])
        await query.message.reply_text(
            "📅 Выберите клуб для просмотра дат:",
            reply_markup=keyboard
        )

    elif data.startswith("dates_club|"):
        # Показываем список дат для выбранного клуба
        club_name = data.split("|", 1)[1]
        
        # Получаем все даты для клуба
        dates = db.get_report_dates(club_name=club_name)
        
        if not dates:
            await query.message.reply_text(
                f"📭 Нет отчётов для клуба {club_name}",
                reply_markup=get_files_keyboard()
            )
            return
        
        # Группируем даты по периодам (месяцам)
        from collections import defaultdict
        dates_by_month = defaultdict(list)
        
        for dt in dates:
            month_key = dt.strftime("%B %Y")  # Например: "November 2025"
            dates_by_month[month_key].append(dt)
        
        # Формируем сообщение
        lines = [f"📅 Даты отчётов для клуба: {club_name}\n"]
        
        for month, month_dates in sorted(dates_by_month.items(), reverse=True):
            lines.append(f"\n📆 {month}:")
            for dt in sorted(month_dates, reverse=True):
                lines.append(f"  • {format_report_date(dt)}")
        
        lines.append(f"\n\n📊 Всего отчётов: {len(dates)}")
        
        # Определяем период
        if dates:
            first_date = min(dates)
            last_date = max(dates)
            lines.append(f"📅 Период: {format_report_date(first_date)} - {format_report_date(last_date)}")
        
        await query.message.reply_text(
            "\n".join(lines),
            reply_markup=get_files_keyboard()
        )

    elif data == "files_latest":
        await send_latest_records(query.message)

    elif data == "files_clear":
        confirmation_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Удалить все", callback_data="files_clear_confirm")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_files")]
        ])
        await query.message.reply_text(
            "⚠️ Удалить все загруженные файлы?\n"
            "Это действие также очистит связанные данные из базы.",
            reply_markup=confirmation_keyboard
        )

    elif data == "files_clear_confirm":
        deleted = db.clear_uploaded_files()
        await query.message.reply_text(
            f"🧼 Очистка завершена. Удалено файлов: {deleted}",
            reply_markup=get_files_keyboard()
        )
    
    elif data == "files_reprocess":
        # Переобработка ВСЕХ файлов пользователя
        try:
            # Получаем ВСЕ файлы пользователя
            with db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT id, file_name, file_content, report_date
                        FROM uploaded_files
                        WHERE user_id = %s AND file_content IS NOT NULL
                        ORDER BY upload_date DESC
                        """,
                        (user_id,)
                    )
                    all_files = cur.fetchall()
            
            if not all_files:
                await query.message.reply_text("❌ Файлы не найдены")
                return
            
            await query.message.reply_text(f"🔄 Начинаю переобработку {len(all_files)} файлов...")
            
            processed_count = 0
            for file_info in all_files:
                file_id = file_info['id']
                file_name = file_info['file_name']
                file_content = file_info['file_content']
                
                # Переобрабатываем все блоки этого файла
                try:
                    income_records = excel_processor.extract_income_records(file_content)
                    if income_records:
                        db.save_income_records(file_id, income_records)
                    
                    ticket_sales_data = excel_processor.extract_ticket_sales(file_content)
                    if ticket_sales_data.get('records'):
                        db.save_ticket_sales(file_id, ticket_sales_data['records'])
                    
                    payment_types_data = excel_processor.extract_payment_types(file_content)
                    if payment_types_data.get('records'):
                        db.save_payment_types(file_id, payment_types_data['records'])
                    
                    staff_stats = excel_processor.extract_staff_statistics(file_content)
                    if staff_stats:
                        db.save_staff_statistics(file_id, staff_stats)
                    
                    expense_data = excel_processor.extract_expense_records(file_content)
                    if expense_data.get('records'):
                        db.save_expense_records(file_id, expense_data['records'])
                    
                    cash_collection_data = excel_processor.extract_cash_collection(file_content)
                    if cash_collection_data.get('records'):
                        db.save_cash_collection(file_id, cash_collection_data['records'])
                    
                    staff_debts_data = excel_processor.extract_staff_debts(file_content)
                    if staff_debts_data.get('records'):
                        db.save_staff_debts(file_id, staff_debts_data['records'])
                    
                    notes_data = excel_processor.extract_notes_entries(file_content)
                    if notes_data:
                        notes_records = []
                        for entry in notes_data.get('безнал', []):
                            notes_records.append({
                                'category': entry.get('category', 'безнал'),
                                'entry_text': entry.get('entry_text', ''),
                                'is_total': entry.get('is_total', False),
                                'amount': entry.get('amount')
                            })
                        for entry in notes_data.get('нал', []):
                            notes_records.append({
                                'category': entry.get('category', 'нал'),
                                'entry_text': entry.get('entry_text', ''),
                                'is_total': entry.get('is_total', False),
                                'amount': entry.get('amount')
                            })
                        for text in notes_data.get('extra', []):
                            notes_records.append({
                                'category': 'прочее',
                                'entry_text': text,
                                'is_total': False,
                                'amount': None
                            })
                        if notes_records:
                            db.save_notes_entries(file_id, notes_records)
                    
                    totals_summary = excel_processor.extract_totals_summary(file_content)
                    if totals_summary:
                        db.save_totals_summary(file_id, totals_summary)
                    
                    processed_count += 1
                    
                except Exception as e:
                    logger.error(f"Error reprocessing file {file_name}: {e}")
                    await query.message.reply_text(f"❌ Ошибка при обработке {file_name}: {str(e)}")
            
            # Финальное сообщение
            await query.message.reply_text(
                f"✅ Переобработка завершена!\n\n"
                f"Обработано файлов: {processed_count} из {len(all_files)}\n\n"
                f"Все блоки обновлены с новым парсером.",
                reply_markup=get_files_keyboard()
            )
            
        except Exception as e:
            logger.error(f"Error reprocessing files: {e}")
            await query.message.reply_text(f"❌ Ошибка: {str(e)}")

    elif data == "main_queries":
        await send_queries_menu_message(query.message, context)

    elif data.startswith("report_club|"):
        # Выбор клуба для формирования отчета → предлагаем выбрать блок
        selected_club = data.split("|", 1)[1]
        context.user_data['report_club'] = selected_club
        await query.answer(f"✅ Выбран: {selected_club}")
        
        # Показываем выбор блока
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Доходы", callback_data="report_block|income")],
            [InlineKeyboardButton("🎟 Входные билеты", callback_data="report_block|tickets")],
            [InlineKeyboardButton("💳 Типы оплат", callback_data="report_block|payments")],
            [InlineKeyboardButton("👥 Статистика персонала", callback_data="report_block|staff")],
            [InlineKeyboardButton("💸 Расходы", callback_data="report_block|expenses")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ])
        await query.message.reply_text(
            f"🏢 Клуб: {selected_club}\n\n"
            "📊 Выберите блок для отчета:",
            reply_markup=keyboard
        )
    
    elif data.startswith("report_block|"):
        # Выбор блока отчета → просим ввести период
        block_id = data.split("|", 1)[1]
        club_name = context.user_data.get('report_club')
        
        if not club_name:
            await query.message.reply_text("❌ Клуб не выбран. Начните заново.")
            return
        
        context.user_data['report_block'] = block_id
        context.user_data['awaiting_report_period'] = True
        
        block_names = {
            'income': 'Доходы',
            'tickets': 'Входные билеты',
            'payments': 'Типы оплат',
            'staff': 'Статистика персонала',
            'expenses': 'Расходы'
        }
        block_name = block_names.get(block_id, block_id)
        
        await query.answer(f"✅ Блок: {block_name}")
        await query.message.reply_text(
            f"🏢 Клуб: {club_name}\n"
            f"📊 Блок: {block_name}\n\n"
            "📅 Введите период для отчета:\n\n"
            "Формат: 1.11-5.12 или 1,11-5,12\n"
            "(бот автоматически подставит текущий год)\n\n"
            "Пример: 1.11-30.11"
        )

    elif data.startswith("select_club|"):
        selected_club = data.split("|", 1)[1]
        context.user_data['current_club'] = selected_club
        await query.answer(f"✅ Выбран: {selected_club}")
        await send_report_dates_menu(query.message, context)

    elif data.startswith("query_date|"):
        date_str = data.split("|", 1)[1]
        try:
            report_date = datetime.fromisoformat(date_str).date()
        except ValueError:
            await query.message.reply_text("⚠️ Некорректная дата.")
            return
        await send_blocks_menu_message(query.message, report_date)

    elif data.startswith("query_block|"):
        _, date_str, block_id = data.split("|", 2)
        try:
            report_date = datetime.fromisoformat(date_str).date()
        except ValueError:
            await query.message.reply_text("⚠️ Некорректная дата.")
            return
        await send_report_block_data(query.message, report_date, block_id, context)

    elif data == "main_help":
        await query.message.reply_text(build_help_text(), parse_mode='Markdown')

    elif data == "employee_menu":
        await send_employees_menu_message(query.message)

    elif data == "employee_add":
        context.user_data['employee_action'] = 'add'
        await query.message.reply_text(
            "✍️ Отправьте код и ФИО сотрудника. Пример:\nД4 - Калинина Дарья Александровна",
        )

    elif data == "employee_delete":
        context.user_data['employee_action'] = 'delete'
        await query.message.reply_text("🗑 Введите код сотрудника для удаления (например, Д4)")

    elif data == "employee_search":
        context.user_data['employee_action'] = 'search'
        await query.message.reply_text("🔍 Введите код сотрудника для поиска")

    elif data == "employee_list":
        await send_employee_list(query, context)

    elif data == "employee_import":
        context.user_data['employee_action'] = 'import_text'
        await query.message.reply_text(
            "📥 Отправьте список сотрудников в формате:\nФИО\nКод\n(каждый сотрудник на двух строках)"
        )

    elif data == "employee_export":
        await export_employee_list(query, context)

    elif data == "employee_clear":
        context.user_data['employee_action'] = 'clear_confirm'
        await query.message.reply_text(
            "⚠️ Это удалит всех сотрудников из базы. Чтобы подтвердить, отправьте: "
            "`УДАЛИТЬ ВСЕХ`",
            parse_mode='Markdown'
        )
    else:
        await query.message.reply_text("Команда не поддерживается. Используйте меню ниже.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ошибок"""
    logger.error(f"Exception while handling an update: {context.error}")
    
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Произошла ошибка при обработке вашего запроса. "
            "Попробуйте еще раз или обратитесь к /help"
        )


async def handle_employee_text_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_message: str):
    """Обработка текстовых ответов для сценариев сотрудников"""
    action = context.user_data.pop('employee_action', None)

    if action == 'add':
        await add_employee_from_text(update, user_message)

    elif action == 'delete':
        await delete_employee_by_code(update, user_message)

    elif action == 'search':
        await search_employee_by_code(update, user_message)

    elif action == 'import_text':
        await import_employees_from_text(update, user_message)

    elif action == 'clear_confirm':
        if user_message.strip().upper() == 'УДАЛИТЬ ВСЕХ':
            deleted = db.clear_employees()
            await update.message.reply_text(
                f"🧼 Удалено сотрудников: {deleted}")
        else:
            await update.message.reply_text("❌ Очистка отменена")
 
 
async def add_employee_from_text(update: Update, text: str):
    """Добавление сотрудника из текста пользователя"""
    result = employee_parser.extract_code_and_name(text)
    
    if not result:
        await update.message.reply_text(
            "❌ Не удалось распознать код и ФИО.\n"
            "Убедитесь, что код (например: Оф3, Д4) и ФИО присутствуют в сообщении."
        )
        return
    
    code, name = result
    
    db.add_employee(code, name)
    await update.message.reply_text(
        f"✅ Сотрудник добавлен/обновлён:\n• Код: {code}\n• ФИО: {name}")
 
 
async def delete_employee_by_code(update: Update, code: str):
    """Удаление сотрудника по коду"""
    code = code.strip().upper()
 
    if not code:
        await update.message.reply_text("❌ Код не распознан")
        return
 
    deleted = db.delete_employee(code)
 
    if deleted:
        await update.message.reply_text(f"🗑 Удалено сотрудников: {deleted}")
    else:
        await update.message.reply_text("ℹ️ Сотрудник с таким кодом не найден")
 
 
async def search_employee_by_code(update: Update, code: str):
    """Поиск сотрудника по коду"""
    code = code.strip().upper()
 
    if not code:
        await update.message.reply_text("❌ Код не распознан")
        return
 
    employee = db.get_employee(code)
 
    if not employee:
        await update.message.reply_text("ℹ️ Сотрудник не найден")
        return
 
    await update.message.reply_text(
        f"👤 Сотрудник найден:\n• Код: {employee['employee_code']}\n• ФИО: {employee['full_name']}")
 
 
async def import_employees_from_text(update: Update, text: str):
    """Импорт списка сотрудников из текста"""
    employees = employee_parser.parse(text)
 
    if not employees:
        await update.message.reply_text("❌ Не удалось распознать сотрудников. Проверьте формат")
        return
 
    result = db.save_employees(employees)
    total = len(employees)
    await update.message.reply_text(
        f"📥 Импорт завершён:\n• Всего в тексте: {total}\n• Добавлено: {result['inserted']}\n• Обновлено: {result['updated']}")
 
 
async def send_employee_list(query, context):
    """Отправка списка сотрудников пользователю"""
    employees = db.list_employees(limit=20)
    total = db.count_employees()
 
    if not employees:
        await query.message.reply_text("📭 Список сотрудников пуст")
        return
 
    lines = ["📋 **Список сотрудников (первые 20):**\n"]
    for emp in employees:
        lines.append(f"• {emp['employee_code']}: {emp['full_name']}")
 
    if total > len(employees):
        lines.append(
            "\n… Показаны не все сотрудники. Используйте кнопку '📥 Экспорт списка (Excel)' для полного списка"
        )
 
    await query.message.reply_text('\n'.join(lines), parse_mode='Markdown')
 
 
async def export_employee_list(query, context):
    """Экспорт списка сотрудников в Excel"""
    employees = db.list_employees(limit=10000)
 
    if not employees:
        await query.message.reply_text("📭 Нет сотрудников для экспорта")
        return
 
    df = pd.DataFrame(employees)
    df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
 
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Employees', index=False)
 
    output.seek(0)
 
    await query.message.reply_document(
        document=output.getvalue(),
        filename='employees.xlsx',
        caption="📥 Список сотрудников"
    )


def build_help_text() -> str:
    return """
📚 **Подробная справка:**

**1. Авторизация:**
   • При первом запуске введите пароль `1801`
   • Можно изменить через переменную окружения `BOT_ACCESS_PASSWORD`

**2. Загрузка Excel файлов:**
   • Поддерживаемые форматы: .xlsx, .xls, .xlsm, .csv
   • Максимальный размер: 50 МБ
   • Отправьте файл как документ — бот сохранит данные в БД

**3. Быстрые запросы к данным:**
   • Кнопка "📊 Запросы к данным" в главном меню
   • "🔢 Количество записей" — общее число строк в `excel_data`
   • "📄 Последние строки" — предпросмотр последнего загруженного файла
   • "🔍 Поиск по колонке" — используйте формат `колонка=значение`

**4. Управление файлами:**
   • Кнопка "📁 Файлы" или команда /myfiles
   • Показывает список загруженных файлов и статистику

**5. Сотрудники:**
   • Кнопка "👥 Сотрудники" открывает меню
   • Добавление одного сотрудника или массовый импорт текста
   • Экспорт списка в Excel, очистка с подтверждением `УДАЛИТЬ ВСЕХ`

**6. Массовый импорт сотрудников (пример текста):**
```
Иванов Иван Иванович
Д4

Петров Пётр Петрович
Д5
```
   • Регистр и пробелы не важны — бот приводит данные к норме

❓ **Подсказка:** Используйте кнопки меню или команду /help при необходимости.
"""


def main():
    """Запуск бота"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables!")
        return
    
    application = Application.builder().token(token).build()

    application.post_init = setup_bot_commands
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("moskvich", moskvich_command))
    application.add_handler(CommandHandler("anora", anora_command))
    application.add_handler(CommandHandler("both", both_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("files", files_command))
    application.add_handler(CommandHandler("queries", queries_command))
    application.add_handler(CommandHandler("employees", employees_command))
    application.add_handler(CommandHandler("myfiles", my_files))
    application.add_handler(CommandHandler("schema", show_schema))
    application.add_handler(CommandHandler("debug", debug_data))
    application.add_handler(CommandHandler("structure", show_excel_structure))
    application.add_handler(CommandHandler("reprocess", reprocess_last_file))
    
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    application.add_error_handler(error_handler)
    
    logger.info("Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()