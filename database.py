"""
Модуль для работы с PostgreSQL базой данных
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import logging
from typing import List, Dict, Any, Optional
import hashlib
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Database:
    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        """Инициализация подключения к БД"""
        self.connection_params = {
            'host': host,
            'port': port,
            'database': database,
            'user': user,
            'password': password
        }
        self._init_database()
    
    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для работы с подключением"""
        conn = psycopg2.connect(**self.connection_params)
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()
    
    def _init_database(self):
        """Инициализация схемы БД"""
        try:
            with open('schema.sql', 'r', encoding='utf-8') as f:
                schema = f.read()
            
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(schema)
            logger.info("Database schema initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    def save_uploaded_file(self, user_id: int, username: str, file_name: str, 
                          file_content: bytes, row_count: int) -> int:
        """Сохранение информации о загруженном файле"""
        file_hash = hashlib.sha256(file_content).hexdigest()
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO uploaded_files (user_id, username, file_name, file_hash, row_count)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_id, username, file_name, file_hash, row_count)
                )
                file_id = cur.fetchone()[0]
                logger.info(f"File saved with ID: {file_id}")
                return file_id
    
    def save_excel_data(self, file_id: int, data: List[Dict[str, Any]]):
        """Сохранение данных из Excel в БД"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                for row_idx, row_data in enumerate(data, start=1):
                    for column_name, value in row_data.items():
                        # Определение типа данных
                        data_type = type(value).__name__
                        
                        cur.execute(
                            """
                            INSERT INTO excel_data (file_id, row_number, column_name, column_value, data_type)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (file_id, row_idx, column_name, str(value) if value is not None else None, data_type)
                        )
                logger.info(f"Saved {len(data)} rows of Excel data for file_id: {file_id}")
 
    # --- Работа с сотрудниками ---

    def save_employees(self, employees: List[Dict[str, str]]) -> Dict[str, int]:
        """Массовое добавление/обновление сотрудников"""
        if not employees:
            return {"inserted": 0, "updated": 0}

        inserted = 0
        updated = 0

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                for employee in employees:
                    code = employee.get('employee_code')
                    name = employee.get('full_name')

                    if not code or not name:
                        continue

                    cur.execute(
                        """
                        INSERT INTO employees (employee_code, full_name)
                        VALUES (%s, %s)
                        ON CONFLICT (employee_code) DO UPDATE
                        SET full_name = EXCLUDED.full_name,
                            created_at = CURRENT_TIMESTAMP
                        RETURNING (xmax = 0) AS inserted
                        """,
                        (code, name)
                    )

                    result = cur.fetchone()
                    if result and result[0]:
                        inserted += 1
                    else:
                        updated += 1

        return {"inserted": inserted, "updated": updated}

    def add_employee(self, employee_code: str, full_name: str):
        """Добавление одного сотрудника"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO employees (employee_code, full_name)
                    VALUES (%s, %s)
                    ON CONFLICT (employee_code) DO UPDATE
                    SET full_name = EXCLUDED.full_name,
                        created_at = CURRENT_TIMESTAMP
                    """,
                    (employee_code, full_name)
                )

    def delete_employee(self, employee_code: str) -> int:
        """Удаление сотрудника по коду"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM employees
                    WHERE employee_code = %s
                    RETURNING id
                    """,
                    (employee_code,)
                )
                deleted = cur.fetchall()
                return len(deleted)

    def clear_employees(self) -> int:
        """Полная очистка таблицы сотрудников"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM employees RETURNING id")
                deleted = cur.fetchall()
                return len(deleted)

    def clear_uploaded_files(self) -> int:
        """Полная очистка загруженных файлов и связанных данных"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM uploaded_files RETURNING id")
                deleted = cur.fetchall()
                return len(deleted)

    def get_employee(self, employee_code: str) -> Optional[Dict[str, Any]]:
        """Получение одного сотрудника по коду"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT employee_code, full_name, created_at
                    FROM employees
                    WHERE employee_code = %s
                    """,
                    (employee_code,)
                )
                result = cur.fetchone()
                return dict(result) if result else None

    def list_employees(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """Получение списка сотрудников"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT employee_code, full_name, created_at
                    FROM employees
                    ORDER BY employee_code
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset)
                )
                return [dict(row) for row in cur.fetchall()]

    def count_employees(self) -> int:
        """Подсчет сотрудников"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM employees")
                return cur.fetchone()[0]

    def search_employees(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Поиск сотрудников по ФИО"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                like_query = f"%{query}%"
                cur.execute(
                    """
                    SELECT employee_code, full_name, created_at
                    FROM employees
                    WHERE full_name ILIKE %s
                    ORDER BY full_name
                    LIMIT %s
                    """,
                    (like_query, limit)
                )
                return [dict(row) for row in cur.fetchall()]

    # --- Запросы к Excel данным ---

    def count_excel_records(self) -> int:
        """Количество записей в excel_data"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM excel_data")
                return cur.fetchone()[0]

    def list_recent_files(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Список последних загруженных файлов"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, file_name, upload_date, row_count
                    FROM uploaded_files
                    ORDER BY upload_date DESC
                    LIMIT %s
                    """,
                    (limit,)
                )
                return [dict(row) for row in cur.fetchall()]

    def get_latest_file(self) -> Optional[Dict[str, Any]]:
        """Последний загруженный файл"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, file_name, upload_date, row_count
                    FROM uploaded_files
                    ORDER BY upload_date DESC
                    LIMIT 1
                    """
                )
                result = cur.fetchone()
                return dict(result) if result else None

    def get_file_preview(self, file_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Предпросмотр строк конкретного файла"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT row_number, column_name, column_value
                    FROM excel_data
                    WHERE file_id = %s
                    ORDER BY row_number, column_name
                    """,
                    (file_id,)
                )

                preview: List[Dict[str, Any]] = []
                current_row = None
                row_data: Dict[str, Any] = {}

                for record in cur.fetchall():
                    row_number = record['row_number']
                    column_name = record['column_name']
                    column_value = record['column_value']

                    if current_row is None:
                        current_row = row_number

                    if row_number != current_row:
                        preview.append({'row_number': current_row, 'data': row_data})
                        if len(preview) >= limit:
                            break
                        current_row = row_number
                        row_data = {}

                    row_data[column_name] = column_value

                if current_row is not None and len(preview) < limit:
                    preview.append({'row_number': current_row, 'data': row_data})

                return preview[:limit]

    def search_excel_by_column(self, column_name: str, search_value: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Поиск строк по указанной колонке"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    WITH matches AS (
                        SELECT file_id, row_number
                        FROM excel_data
                        WHERE column_name = %s AND column_value ILIKE %s
                        ORDER BY row_number
                        LIMIT %s
                    )
                    SELECT m.file_id,
                           m.row_number,
                           e.column_name,
                           e.column_value,
                           u.file_name
                    FROM matches m
                    JOIN excel_data e ON e.file_id = m.file_id AND e.row_number = m.row_number
                    JOIN uploaded_files u ON u.id = m.file_id
                    ORDER BY u.upload_date DESC, m.row_number, e.column_name
                    """,
                    (column_name, f"%{search_value}%", limit)
                )

                grouped: Dict[tuple, Dict[str, Any]] = {}

                for record in cur.fetchall():
                    key = (record['file_id'], record['row_number'])
                    if key not in grouped:
                        grouped[key] = {
                            'file_name': record['file_name'],
                            'row_number': record['row_number'],
                            'data': {}
                        }
                    grouped[key]['data'][record['column_name']] = record['column_value']

                return list(grouped.values())
 
    def execute_query(self, sql: str, params: tuple = None) -> List[Dict[str, Any]]:
        """Выполнение SQL запроса и возврат результатов"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                try:
                    results = cur.fetchall()
                    return [dict(row) for row in results]
                except psycopg2.ProgrammingError:
                    # Запрос не возвращает результаты (INSERT, UPDATE, DELETE)
                    return []
    
    def save_user_query(self, user_id: int, query_text: str, 
                       generated_sql: str, result_count: int):
        """Сохранение запроса пользователя в лог"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_queries (user_id, query_text, generated_sql, result_count)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (user_id, query_text, generated_sql, result_count)
                )
    
    def save_custom_data(self, user_id: int, data_key: str, data_value: str):
        """Сохранение пользовательских данных"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_custom_data (user_id, data_key, data_value)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id) DO UPDATE 
                    SET data_value = EXCLUDED.data_value,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, data_key, data_value)
                )
    
    def get_database_schema(self) -> str:
        """Получение схемы базы данных для контекста DeepSeek"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        table_name,
                        column_name,
                        data_type,
                        is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                    ORDER BY table_name, ordinal_position
                """)
                columns = cur.fetchall()
                
                schema_description = "Database Schema:\n\n"
                current_table = None
                
                for col in columns:
                    if col['table_name'] != current_table:
                        current_table = col['table_name']
                        schema_description += f"\nTable: {current_table}\n"
                    
                    nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                    schema_description += f"  - {col['column_name']}: {col['data_type']} ({nullable})\n"
                
                return schema_description
    
    def get_user_files(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение списка файлов пользователя"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, file_name, upload_date, row_count
                    FROM uploaded_files
                    WHERE user_id = %s
                    ORDER BY upload_date DESC
                    """,
                    (user_id,)
                )
                return [dict(row) for row in cur.fetchall()]


