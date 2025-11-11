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
        "🔐 Введите пароль для доступа к боту (по умолчанию 1801)",
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
        [KeyboardButton(BUTTON_EMPLOYEES), KeyboardButton(BUTTON_HELP)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_files_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📄 Список файлов", callback_data="files_list")],
        [InlineKeyboardButton("🔍 Последние записи", callback_data="files_latest")],
        [InlineKeyboardButton("🔄 Обновить последний файл", callback_data="files_reprocess")],
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


def get_query_dates_keyboard(dates: List[date]) -> InlineKeyboardMarkup:
    keyboard = []
    for dt in dates:
        label = format_report_date(dt)
        callback_data = f"query_date|{dt.isoformat()}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])
    keyboard.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)


def get_blocks_keyboard(report_date: date) -> InlineKeyboardMarkup:
    keyboard = []
    for block_id, block_label in QUERY_BLOCKS:
        callback_data = f"query_block|{report_date.isoformat()}|{block_id}"
        keyboard.append([InlineKeyboardButton(block_label, callback_data=callback_data)])
    keyboard.append([InlineKeyboardButton("⬅️ К выбору даты", callback_data="main_queries")])
    keyboard.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)


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


async def send_queries_menu_message(target_message):
    await send_report_dates_menu(target_message)


async def send_report_dates_menu(target_message):
    dates = db.get_report_dates()
    if not dates:
        await target_message.reply_text(
            "📭 Пока нет отчётов с установленной датой. Загрузите файл и укажите дату."
        )
        return

    await target_message.reply_text(
        "Выберите дату отчёта:",
        reply_markup=get_query_dates_keyboard(dates)
    )


async def send_blocks_menu_message(target_message, report_date: date):
    await target_message.reply_text(
        f"Дата отчёта: {format_report_date(report_date)}\nВыберите блок:",
        reply_markup=get_blocks_keyboard(report_date)
    )


async def send_report_block_data(target_message, report_date: date, block_id: str):
    file_info = db.get_file_by_report_date(report_date)
    if not file_info:
        await target_message.reply_text("⚠️ Отчёт на эту дату не найден.")
        return

    file_id = file_info['id']
    block_label = next((label for bid, label in QUERY_BLOCKS if bid == block_id), block_id)

    if block_id == 'income':
        records = db.list_income_records(file_id)
        if not records:
            await target_message.reply_text("📭 Нет данных по доходам для этой даты.")
            return
        
        # Отладка: проверим, что приходит из базы
        logger.info(f"Income records from DB: {records}")
        
        lines = [f"💰 Доходы ({format_report_date(report_date)}):"]
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
        excel_bytes = excel_processor.export_to_excel_with_header(display_rows, report_date, "Доходы")
        await target_message.reply_document(excel_bytes, filename=f"доходы_{format_report_date(report_date)}.xlsx", caption=f"📅 Дата: {format_report_date(report_date)}")
        return

    if block_id == 'tickets':
        records = db.list_ticket_sales(file_id)
        if not records:
            await target_message.reply_text("📭 Нет данных по входным билетам для этой даты.")
            return
        lines = [f"🎟 Входные билеты ({format_report_date(report_date)}):"]
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
        
        excel_bytes = excel_processor.export_to_excel_with_header(display_rows, report_date, "Входные билеты")
        await target_message.reply_document(excel_bytes, filename=f"входные_билеты_{format_report_date(report_date)}.xlsx", caption=f"📅 Дата: {format_report_date(report_date)}")
        return

    if block_id == 'payments':
        records = db.list_payment_types(file_id)
        if not records:
            await target_message.reply_text("📭 Нет данных по типам оплат для этой даты.")
            return
        lines = [f"💳 Типы оплат ({format_report_date(report_date)}):"]
        display_rows = []
        for rec in records:
            label = rec['payment_type']
            lines.append(f"• {label}: {decimal_to_str(rec['amount'])}")
            display_rows.append({
                'Тип оплаты': label,
                'Сумма': decimal_to_float(rec['amount'])
            })
        await target_message.reply_text("\n".join(lines))
        excel_bytes = excel_processor.export_to_excel_with_header(display_rows, report_date, "Типы оплат")
        await target_message.reply_document(excel_bytes, filename=f"типы_оплат_{format_report_date(report_date)}.xlsx", caption=f"📅 Дата: {format_report_date(report_date)}")
        return

    if block_id == 'staff':
        records = db.list_staff_statistics(file_id)
        if not records:
            await target_message.reply_text("📭 Нет данных по персоналу для этой даты.")
            return
        lines = [f"👥 Статистика персонала ({format_report_date(report_date)}):"]
        display_rows = []
        total_staff = 0
        for rec in records:
            lines.append(f"• {rec['role_name']}: {rec['staff_count']}")
            display_rows.append({
                'Должность': rec['role_name'],
                'Количество': rec['staff_count']
            })
            total_staff += rec['staff_count'] or 0
        lines.append(f"Всего персонала: {total_staff}")
        await target_message.reply_text("\n".join(lines))
        excel_bytes = excel_processor.export_to_excel(display_rows, file_name="staff.xlsx")
        await target_message.reply_document(excel_bytes, filename=f"персонал_{report_date.isoformat()}.xlsx")
        return

    if block_id == 'expenses':
        records = db.list_expense_records(file_id)
        if not records:
            await target_message.reply_text("📭 Нет данных по расходам для этой даты.")
            return
        lines = [f"💸 Расходы ({format_report_date(report_date)}):"]
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
        excel_bytes = excel_processor.export_to_excel_with_header(display_rows, report_date, "Расходы")
        await target_message.reply_document(excel_bytes, filename=f"расходы_{format_report_date(report_date)}.xlsx", caption=f"📅 Дата: {format_report_date(report_date)}")
        return

    if block_id == 'cash':
        records = db.list_cash_collection(file_id)
        if not records:
            await target_message.reply_text("📭 Нет данных по инкассации для этой даты.")
            return
        lines = [f"🏦 Инкассация ({format_report_date(report_date)}):"]
        display_rows = []
        for rec in records:
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
        await target_message.reply_text("\n".join(lines))
        excel_bytes = excel_processor.export_to_excel(display_rows, file_name="cash_collection.xlsx")
        await target_message.reply_document(excel_bytes, filename=f"инкассация_{report_date.isoformat()}.xlsx")
        return

    if block_id == 'debts':
        records = db.list_staff_debts(file_id)
        if not records:
            await target_message.reply_text("📭 Нет данных по долгам персонала для этой даты.")
            return
        lines = [f"📌 Долги по персоналу ({format_report_date(report_date)}):"]
        display_rows = []
        for rec in records:
            lines.append(f"• {rec['debt_type']}: {decimal_to_str(rec['amount'])}")
            display_rows.append({
                'Тип долга': rec['debt_type'],
                'Сумма': decimal_to_float(rec['amount'])
            })
        await target_message.reply_text("\n".join(lines))
        excel_bytes = excel_processor.export_to_excel(display_rows, file_name="staff_debts.xlsx")
        await target_message.reply_document(excel_bytes, filename=f"долги_{report_date.isoformat()}.xlsx")
        return

    if block_id == 'notes':
        records = db.list_notes_entries(file_id)
        if not records:
            await target_message.reply_text("📭 Нет примечаний для этой даты.")
            return
        lines = [f"📝 Примечания ({format_report_date(report_date)}):"]
        display_rows = []
        for rec in records:
            prefix = rec['category'].capitalize()
            entry_text = rec['entry_text']
            if rec.get('is_total'):
                lines.append(f"• {prefix} итого: {decimal_to_str(rec.get('amount'))}")
            else:
                lines.append(f"• {prefix}: {entry_text}")
            display_rows.append({
                'Категория': rec['category'],
                'Запись': entry_text,
                'Сумма': decimal_to_float(rec.get('amount'))
            })
        await target_message.reply_text("\n".join(lines))
        excel_bytes = excel_processor.export_to_excel(display_rows, file_name="notes.xlsx")
        await target_message.reply_document(excel_bytes, filename=f"примечания_{report_date.isoformat()}.xlsx")
        return

    if block_id == 'totals':
        records = db.list_totals_summary(file_id)
        if not records:
            await target_message.reply_text("📭 Нет итогового баланса для этой даты.")
            return
        lines = [f"📊 Итоговый баланс ({format_report_date(report_date)}):"]
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
        excel_bytes = excel_processor.export_to_excel(display_rows, file_name="totals.xlsx")
        await target_message.reply_document(excel_bytes, filename=f"итого_{report_date.isoformat()}.xlsx")
        return

    await target_message.reply_text("⚠️ Неизвестный блок.")


async def setup_bot_commands(application: Application):
    commands = [
        BotCommand("start", "Главное меню"),
        BotCommand("files", "Управление файлами"),
        BotCommand("queries", "Быстрые запросы"),
        BotCommand("employees", "Работа с сотрудниками"),
        BotCommand("help", "Описание возможностей")
    ]
    await application.bot.set_my_commands(commands)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    welcome_message = """
👋 **Привет!** Я твой помощник для работы с данными.

🧠 **Что я умею:**
• Анализировать Excel и CSV файлы и сохранять их в PostgreSQL
• Добавлять новые записи в базу по твоим словам
• Удалять ненужные записи по описанию запроса
• Отвечать на вопросы к данным естественным языком

🛠 **Как начать:**
1. Отправь Excel/CSV файл как документ — я загружу и разберу его.
2. Спрашивай, что нужно найти: «Покажи продажи за март».
3. Добавляй данные командами вроде «Запиши: клиент Иванов, сумма 5000».
4. Удаляй записи: «Удали всех клиентов из Москвы», «Удалить последние загрузки».

📋 **Полезные команды:**
/myfiles — список загруженных файлов
/schema — структура базы данных
/help — подробная инструкция

Готов к работе, просто напиши что нужно! 🚀
"""
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

    user_id = update.effective_user.id
    if not user_is_authorized(user_id, context):
        await request_password(update.message, context)
        return

    context.user_data.pop('awaiting_password', None)
    await send_main_menu_message(update.message)


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

    await send_queries_menu_message(update.message)


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
        
        # Сохранение в БД
        file_id = db.save_uploaded_file(
            user_id=user.id,
            username=user.username or user.first_name,
            file_name=document.file_name,
            file_content=bytes(file_content),
            row_count=len(data),
            report_date=report_date
        )
        
        db.save_excel_data(file_id, data)

        income_records = excel_processor.extract_income_records(bytes(file_content))
        if income_records:
            db.save_income_records(file_id, income_records)
            income_total = next(
                (record['amount'] for record in income_records if record['category'].strip().lower() == 'итого за смену'),
                None
            )
            if income_total is not None:
                total_str = format(income_total, '0.2f')
                await update.message.reply_text(
                    f"💰 Блок 'Доходы' обработан. Итог за смену: {total_str}")
 
        ticket_sales_data = excel_processor.extract_ticket_sales(bytes(file_content))
        if ticket_sales_data.get('records'):
            db.save_ticket_sales(file_id, ticket_sales_data['records'])

            if not ticket_sales_data.get('totals_match', True):
                calc_amount = ticket_sales_data.get('calculated_amount') or Decimal('0.00')
                reported_amount = ticket_sales_data.get('total_amount') or Decimal('0.00')
                await update.message.reply_text(
                    "⚠️ В блоке 'Входные билеты' сумма строк не совпадает с 'Итого'.\n"
                    f"По строкам: {format(calc_amount, '0.2f')} | В строке 'Итого': {format(reported_amount, '0.2f')}"
                )

            ticket_total_amount = ticket_sales_data.get('total_amount')

            if ticket_total_amount is not None:
                tickets_total_str = format(ticket_total_amount, '0.2f')
                income_entry_amount = None
                if income_records:
                    income_entry_amount = next(
                        (record['amount'] for record in income_records if record['category'].strip().lower() == 'входные билеты'),
                        None
                    )

                if income_entry_amount is not None:
                    difference = ticket_total_amount - income_entry_amount
                    if difference.copy_abs() > Decimal('0.01'):
                        await update.message.reply_text(
                            "⚠️ Расхождение между блоками 'Доходы' и 'Входные билеты'.\n"
                            f"Доходы → 'Входные билеты': {format(income_entry_amount, '0.2f')}\n"
                            f"Входные билеты → Итого: {tickets_total_str}"
                        )

                await update.message.reply_text(
                    f"🎟 Блок 'Входные билеты' обработан. Итого сумма: {tickets_total_str}")

        payment_types_data = excel_processor.extract_payment_types(bytes(file_content))
        if payment_types_data.get('records'):
            db.save_payment_types(file_id, payment_types_data['records'])

            if not payment_types_data.get('totals_match', True):
                calc_total = payment_types_data.get('calculated_total') or Decimal('0.00')
                reported_total = payment_types_data.get('reported_total') or Decimal('0.00')
                await update.message.reply_text(
                    "⚠️ В блоке 'Типы оплат' суммы строк не совпадают с 'ИТОГО'.\n"
                    f"По строкам: {format(calc_total, '0.2f')} | 'ИТОГО': {format(reported_total, '0.2f')}"
                )

            payment_total = payment_types_data.get('reported_total') or Decimal('0.00')
            income_total = None

            if income_records:
                income_total = next(
                    (record['amount'] for record in income_records if record['category'].strip().lower() == 'итого'),
                    None
                )

            if income_total is not None and (payment_total - income_total).copy_abs() > Decimal('0.01'):
                await update.message.reply_text(
                    "⚠️ Расхождение между 'ИТОГО' в блоке 'Доходы' и 'Типы оплат'.\n"
                    f"Доходы → Итого: {format(income_total, '0.2f')}\n"
                    f"Типы оплат → Итого: {format(payment_total, '0.2f')}"
                )

            cash_total = payment_types_data.get('cash_total')
            msg_lines = ["💳 Блок 'Типы оплат' обработан."]
            if cash_total is not None:
                msg_lines.append(f"Итого касса: {format(cash_total, '0.2f')}")
            msg_lines.append(f"Итого: {format(payment_total, '0.2f')}")
            await update.message.reply_text("\n".join(msg_lines))

        staff_stats = excel_processor.extract_staff_statistics(bytes(file_content))
        if staff_stats:
            db.save_staff_statistics(file_id, staff_stats)
            total_staff = sum(item.get('staff_count', 0) for item in staff_stats)
            await update.message.reply_text(
                "👥 Блок 'Статистика персонала' обработан.\n"
                f"Всего персонала на смене: {total_staff}"
            )
 
        expense_data = excel_processor.extract_expense_records(bytes(file_content))
        if expense_data.get('records'):
            db.save_expense_records(file_id, expense_data['records'])

            if not expense_data.get('totals_match', True):
                calc_total = expense_data.get('calculated_total') or Decimal('0.00')
                reported_total = expense_data.get('reported_total') or Decimal('0.00')
                await update.message.reply_text(
                    "⚠️ В блоке 'Расходы' сумма строк не совпадает с 'Итого'.\n"
                    f"По строкам: {format(calc_total, '0.2f')} | 'Итого': {format(reported_total, '0.2f')}"
                )

            expenses_total = expense_data.get('reported_total') or Decimal('0.00')
            income_total = None
            if income_records:
                income_total = next(
                    (record['amount'] for record in income_records if record['category'].strip().lower() == 'итого'),
                    None
                )

            msg_lines = ["💸 Блок 'Расходы' обработан."]
            msg_lines.append(f"Итого расходы: {format(expenses_total, '0.2f')}")

            if income_total is not None:
                balance = income_total - expenses_total
                msg_lines.append(f"Финансовый результат (Итого доходы - Расходы): {format(balance, '0.2f')}")

            await update.message.reply_text("\n".join(msg_lines))

        staff_debts_data = excel_processor.extract_staff_debts(bytes(file_content))
        if staff_debts_data.get('records'):
            db.save_staff_debts(file_id, staff_debts_data['records'])

            if not staff_debts_data.get('totals_match', True):
                calc_total = staff_debts_data.get('calculated_total') or Decimal('0.00')
                reported_total = staff_debts_data.get('reported_total') or Decimal('0.00')
                await update.message.reply_text(
                    "⚠️ В блоке 'Долги по персоналу' сумма строк не совпадает с 'Итого'.\n"
                    f"По строкам: {format(calc_total, '0.2f')} | 'Итого': {format(reported_total, '0.2f')}"
                )

            debts_total = staff_debts_data.get('reported_total') or Decimal('0.00')
            await update.message.reply_text(
                "📌 Блок 'Долги по персоналу' обработан.\n"
                f"Итого задолженность: {format(debts_total, '0.2f')}"
            )
        else:
            staff_debts_data = {}
 
        cash_collection_data = excel_processor.extract_cash_collection(bytes(file_content))
        if cash_collection_data.get('records'):
            db.save_cash_collection(file_id, cash_collection_data['records'])
 
            if not cash_collection_data.get('totals_match', True):
                calc_total = cash_collection_data.get('calculated_total') or Decimal('0.00')
                reported_total = cash_collection_data.get('reported_total') or Decimal('0.00')
                await update.message.reply_text(
                    "⚠️ В блоке 'Инкассация' сумма строк не совпадает с 'Итого'.\n"
                    f"По строкам: {format(calc_total, '0.2f')} | 'Итого': {format(reported_total, '0.2f')}"
                )
 
            collection_total = cash_collection_data.get('reported_total') or Decimal('0.00')
            await update.message.reply_text(
                "🏦 Блок 'Инкассация' обработан.\n"
                f"Итого наличных после смены: {format(collection_total, '0.2f')}"
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

            msg_lines = ["📝 Блок 'Примечание' сохранён."]

            if staff_debts_data.get('records'):
                bn_debt = next((rec['amount'] for rec in staff_debts_data['records'] if 'бн' in rec['debt_type'].lower()), None)
                cash_debt = next((rec['amount'] for rec in staff_debts_data['records'] if 'нал' in rec['debt_type'].lower()), None)

                note_bn_total = next((entry['amount'] for entry in notes_data.get('безнал', []) if entry.get('is_total')), None)
                note_cash_total = next((entry['amount'] for entry in notes_data.get('нал', []) if entry.get('is_total')), None)

                mismatches = []
                if bn_debt is not None and note_bn_total is not None and (bn_debt - note_bn_total).copy_abs() > Decimal('0.01'):
                    mismatches.append(
                        f"Безнал: долги {format(bn_debt, '0.2f')} ≠ примечания {format(note_bn_total, '0.2f')}"
                    )
                if cash_debt is not None and note_cash_total is not None and (cash_debt - note_cash_total).copy_abs() > Decimal('0.01'):
                    mismatches.append(
                        f"Нал: долги {format(cash_debt, '0.2f')} ≠ примечания {format(note_cash_total, '0.2f')}"
                    )

                if mismatches:
                    msg_lines.append("⚠️ Несовпадение с блоком 'Долги по персоналу':")
                    msg_lines.extend(mismatches)

            await update.message.reply_text("\n".join(msg_lines))

        totals_summary = excel_processor.extract_totals_summary(bytes(file_content))
        if totals_summary:
            db.save_totals_summary(file_id, totals_summary)

            mismatches = []
            for entry in totals_summary:
                p_type = entry['payment_type'].lower()
                net = entry['net_profit']
                income = entry['income_amount']
                expense = entry['expense_amount']

                expected_net = income - expense
                if (expected_net - net).copy_abs() > Decimal('0.01'):
                    mismatches.append(
                        f"{entry['payment_type']}: чистая прибыль {format(net, '0.2f')} ≠ доход ({format(income, '0.2f')}) - расход ({format(expense, '0.2f')})"
                    )

            msg_lines = ["📊 Блок 'Итого' обработан."]
            if mismatches:
                msg_lines.append("⚠️ Обнаружены несоответствия:")
                msg_lines.extend(mismatches)
            await update.message.reply_text("\n".join(msg_lines))

        # Отправка статистики
        await processing_msg.edit_text(
            f"✅ Файл успешно обработан и сохранен!\n\n{stats}",
            parse_mode='Markdown'
        )
        
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
        await send_queries_menu_message(update.message)
        return

    if user_message.strip() == BUTTON_EMPLOYEES:
        await send_employees_menu_message(update.message)
        return

    if user_message.strip() == BUTTON_HELP:
        await update.message.reply_text(build_help_text(), parse_mode='Markdown')
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
        # Переобработка последнего файла
        try:
            # Получаем последний файл пользователя
            with db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT id, file_name, file_content, report_date
                        FROM uploaded_files
                        WHERE user_id = %s
                        ORDER BY upload_date DESC
                        LIMIT 1
                        """,
                        (user_id,)
                    )
                    file_info = cur.fetchone()
            
            if not file_info or not file_info.get('file_content'):
                await query.message.reply_text("❌ Файл не найден или не сохранён")
                return
            
            file_id = file_info['id']
            file_name = file_info['file_name']
            file_content = file_info['file_content']
            
            await query.message.reply_text(f"🔄 Переобработка файла {file_name}...")
            
            # Переобрабатываем все блоки
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
            
            await query.message.reply_text("✅ Файл обновлён! Все блоки переобработаны с новым парсером.", reply_markup=get_files_keyboard())
            
        except Exception as e:
            logger.error(f"Error reprocessing file: {e}")
            await query.message.reply_text(f"❌ Ошибка: {str(e)}")

    elif data == "main_queries":
        await send_report_dates_menu(query.message)

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
        await send_report_block_data(query.message, report_date, block_id)

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