-- Создание таблицы для хранения информации о загруженных файлах
CREATE TABLE IF NOT EXISTS uploaded_files (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    username VARCHAR(255),
    file_name VARCHAR(500) NOT NULL,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    file_hash VARCHAR(64),
    row_count INTEGER DEFAULT 0
);

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


