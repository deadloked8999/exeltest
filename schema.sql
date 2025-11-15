-- Создание таблицы для хранения информации о загруженных файлах
CREATE TABLE IF NOT EXISTS uploaded_files (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    username VARCHAR(255),
    file_name VARCHAR(500) NOT NULL,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    file_hash VARCHAR(64),
    row_count INTEGER DEFAULT 0,
    report_date DATE,
    file_content BYTEA
);

ALTER TABLE uploaded_files
    ADD COLUMN IF NOT EXISTS report_date DATE;

ALTER TABLE uploaded_files
    ADD COLUMN IF NOT EXISTS file_content BYTEA;

ALTER TABLE uploaded_files
    ADD COLUMN IF NOT EXISTS club_name VARCHAR(50);

-- Создание таблицы для хранения данных из Excel файлов
CREATE TABLE IF NOT EXISTS excel_data (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES uploaded_files(id) ON DELETE CASCADE,
    row_number INTEGER NOT NULL,
    column_name VARCHAR(255) NOT NULL,
    column_value TEXT,
    data_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание индексов для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_excel_data_file_id ON excel_data(file_id);
CREATE INDEX IF NOT EXISTS idx_excel_data_column_name ON excel_data(column_name);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_user_id ON uploaded_files(user_id);

-- Таблица для блока «ДОХОДЫ»
CREATE TABLE IF NOT EXISTS income_records (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES uploaded_files(id) ON DELETE CASCADE,
    category VARCHAR(255) NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_income_records_file_id ON income_records(file_id);
CREATE INDEX IF NOT EXISTS idx_income_records_category ON income_records(category);

-- Таблица для блока «ВХОДНЫЕ БИЛЕТЫ»
CREATE TABLE IF NOT EXISTS ticket_sales (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES uploaded_files(id) ON DELETE CASCADE,
    price_label VARCHAR(255),
    price_value NUMERIC(14,2),
    quantity INTEGER,
    amount NUMERIC(14,2),
    is_total BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ticket_sales_file_id ON ticket_sales(file_id);

-- Таблица для блока «ТИПЫ ОПЛАТ ЗА СМЕНУ»
CREATE TABLE IF NOT EXISTS payment_types (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES uploaded_files(id) ON DELETE CASCADE,
    payment_type VARCHAR(255),
    amount NUMERIC(14,2),
    is_total BOOLEAN DEFAULT FALSE,
    is_cash_total BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_payment_types_file_id ON payment_types(file_id);

-- Таблица для блока «Статистика персонала»
CREATE TABLE IF NOT EXISTS staff_statistics (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES uploaded_files(id) ON DELETE CASCADE,
    role_name VARCHAR(255) NOT NULL,
    staff_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_staff_statistics_file_id ON staff_statistics(file_id);

-- Таблица для блока «Расходы»
CREATE TABLE IF NOT EXISTS expense_records (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES uploaded_files(id) ON DELETE CASCADE,
    expense_item VARCHAR(255) NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    is_total BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_expense_records_file_id ON expense_records(file_id);

-- Таблица для блока «Прочие расходы»
CREATE TABLE IF NOT EXISTS misc_expenses_records (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES uploaded_files(id) ON DELETE CASCADE,
    expense_item VARCHAR(255) NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    is_total BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_misc_expenses_records_file_id ON misc_expenses_records(file_id);

-- Таблица для блока «Инкассация»
CREATE TABLE IF NOT EXISTS cash_collection (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES uploaded_files(id) ON DELETE CASCADE,
    currency_label VARCHAR(255) NOT NULL,
    quantity NUMERIC(14,2),
    exchange_rate NUMERIC(14,4),
    amount NUMERIC(14,2) NOT NULL,
    is_total BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cash_collection_file_id ON cash_collection(file_id);

-- Таблица для блока «Долги по персоналу»
CREATE TABLE IF NOT EXISTS staff_debts (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES uploaded_files(id) ON DELETE CASCADE,
    debt_type VARCHAR(255) NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    is_total BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_staff_debts_file_id ON staff_debts(file_id);

-- Таблица для блока «Примечание»
CREATE TABLE IF NOT EXISTS notes_entries (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES uploaded_files(id) ON DELETE CASCADE,
    category VARCHAR(50) NOT NULL,
    entry_text TEXT NOT NULL,
    is_total BOOLEAN DEFAULT FALSE,
    amount NUMERIC(14,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notes_entries_file_id ON notes_entries(file_id);

-- Таблица для блока «Итого»
CREATE TABLE IF NOT EXISTS totals_summary (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES uploaded_files(id) ON DELETE CASCADE,
    payment_type VARCHAR(50) NOT NULL,
    income_amount NUMERIC(14,2) NOT NULL,
    expense_amount NUMERIC(14,2) NOT NULL,
    net_profit NUMERIC(14,2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_totals_summary_file_id ON totals_summary(file_id);

-- Создание таблицы для логов запросов пользователей
CREATE TABLE IF NOT EXISTS user_queries (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    query_text TEXT NOT NULL,
    generated_sql TEXT,
    result_count INTEGER DEFAULT 0,
    query_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы для пользовательских данных (добавленных через DeepSeek)
CREATE TABLE IF NOT EXISTS user_custom_data (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    data_key VARCHAR(255) NOT NULL,
    data_value TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_custom_data_key ON user_custom_data(data_key);

CREATE TABLE IF NOT EXISTS employees (
    id SERIAL PRIMARY KEY,
    employee_code VARCHAR(10) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_employees_full_name ON employees(full_name);

-- Таблица для расходов вне смены
CREATE TABLE IF NOT EXISTS off_shift_expenses (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    username VARCHAR(255),
    club_name VARCHAR(50) NOT NULL,
    expense_item VARCHAR(255) NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    payment_type VARCHAR(50) NOT NULL,
    expense_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Добавляем колонку payment_type если её нет (для существующих баз)
ALTER TABLE off_shift_expenses 
    ADD COLUMN IF NOT EXISTS payment_type VARCHAR(50) DEFAULT 'Наличные';

-- Обновляем существующие записи без payment_type
UPDATE off_shift_expenses 
SET payment_type = 'Наличные' 
WHERE payment_type IS NULL;

-- Делаем payment_type обязательным
ALTER TABLE off_shift_expenses 
    ALTER COLUMN payment_type SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_off_shift_expenses_user_id ON off_shift_expenses(user_id);
CREATE INDEX IF NOT EXISTS idx_off_shift_expenses_club_name ON off_shift_expenses(club_name);
CREATE INDEX IF NOT EXISTS idx_off_shift_expenses_date ON off_shift_expenses(expense_date);
CREATE INDEX IF NOT EXISTS idx_off_shift_expenses_payment_type ON off_shift_expenses(payment_type);


