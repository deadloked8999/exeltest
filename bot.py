"""
Telegram бот для работы с Excel файлами и PostgreSQL через DeepSeek API
"""
import os
import logging
from typing import Optional, Dict, Any, Set
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
import re
import io
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
        [InlineKeyboardButton("📂 Последние файлы", callback_data="files_list")],
        [InlineKeyboardButton("📄 Предпросмотр последнего", callback_data="files_latest")],
        [InlineKeyboardButton("🧼 Очистить файлы", callback_data="files_clear")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_employees_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("➕ Добавить", callback_data="employee_add")],
        [InlineKeyboardButton("➖ Удалить", callback_data="employee_delete")],
        [InlineKeyboardButton("🔍 Найти по коду", callback_data="employee_search")],
        [InlineKeyboardButton("📋 Показать список", callback_data="employee_list")],
        [InlineKeyboardButton("📥 Импорт текста", callback_data="employee_import")],
        [InlineKeyboardButton("📥 Экспорт списка (Excel)", callback_data="employee_export")],
        [InlineKeyboardButton("🧼 Очистить сотрудников", callback_data="employee_clear")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_queries_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🔢 Количество записей", callback_data="query_count")],
        [InlineKeyboardButton("📄 Последние строки", callback_data="query_latest")],
        [InlineKeyboardButton("🔍 Поиск по колонке", callback_data="query_search")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


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


async def setup_bot_commands(application: Application):
    commands = [
        BotCommand("start", "Главное меню"),
        BotCommand("files", "Управление файлами"),
        BotCommand("queries", "Быстрые запросы"),
        BotCommand("employees", "Работа с сотрудниками"),
        BotCommand("help", "Описание возможностей")
    ]
    await application.bot.set_my_commands(commands)


async def send_employees_menu_message(target_message):
    await target_message.reply_text(
        "Выберите действие:",
        reply_markup=get_employees_keyboard()
    )


async def send_queries_menu_message(target_message):
    await target_message.reply_text(
        "Выберите запрос:",
        reply_markup=get_queries_keyboard()
    )


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
        
        # Обработка Excel файла
        data, stats = excel_processor.process_file(bytes(file_content), document.file_name)
        
        # Сохранение в БД
        file_id = db.save_uploaded_file(
            user_id=user.id,
            username=user.username or user.first_name,
            file_name=document.file_name,
            file_content=bytes(file_content),
            row_count=len(data)
        )
        
        db.save_excel_data(file_id, data)
        
        # Отправка статистики
        await processing_msg.edit_text(
            f"✅ Файл успешно обработан и сохранен!\n\n{stats}",
            parse_mode='Markdown'
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
        lines.append(
            f"• {item['file_name']} (строк: {item['row_count']}, загружен: {upload_date})"
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

    elif data == "main_queries":
        await send_queries_menu_message(query.message)

    elif data == "main_help":
        await query.message.reply_text(build_help_text(), parse_mode='Markdown')

    elif data == "employee_menu":
        await send_employees_menu_message(query.message)

    elif data == "query_count":
        await send_excel_record_count(query.message)

    elif data == "query_latest":
        await send_latest_records(query.message)

    elif data == "query_search":
        context.user_data['query_action'] = 'search_column'
        await query.message.reply_text(
            "Введите условие поиска в формате `колонка=значение`",
            parse_mode='Markdown'
        )

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
    
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    application.add_error_handler(error_handler)
    
    logger.info("Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()