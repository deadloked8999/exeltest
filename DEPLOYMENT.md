# 🚀 Руководство по развертыванию

Инструкции по развертыванию Excel Telegram Bot на различных платформах.

---

## 🖥️ Локальное развертывание

### Windows

#### Быстрый старт
```bash
# 1. Клонируйте или скачайте проект
cd exeltest

# 2. Запустите установку
setup.bat

# 3. Отредактируйте .env файл
notepad .env

# 4. Запустите бота
run.bat
```

#### Подробно

**1. Установка PostgreSQL:**
```bash
# Скачайте с https://www.postgresql.org/download/windows/
# Установите и запомните пароль для пользователя postgres
```

**2. Создание базы данных:**
```sql
-- Откройте pgAdmin или psql
CREATE DATABASE excel_bot;
```

**3. Python окружение:**
```bash
# Проверьте Python (3.8+)
python --version

# Создайте виртуальное окружение
python -m venv venv

# Активируйте
venv\Scripts\activate

# Установите зависимости
pip install -r requirements.txt
```

---

### Linux (Ubuntu/Debian)

#### Быстрый старт
```bash
# 1. Клонируйте проект
git clone <url>
cd exeltest

# 2. Дайте права
chmod +x setup.sh run.sh

# 3. Запустите установку
./setup.sh

# 4. Отредактируйте .env
nano .env

# 5. Запустите бота
./run.sh
```

#### Подробно

**1. Установка PostgreSQL:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**2. Создание БД и пользователя:**
```bash
sudo -u postgres psql

# В psql:
CREATE DATABASE excel_bot;
CREATE USER bot_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE excel_bot TO bot_user;
\q
```

**3. Python окружение:**
```bash
# Установка Python и pip
sudo apt install python3 python3-pip python3-venv

# Создание виртуального окружения
python3 -m venv venv

# Активация
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt
```

---

### macOS

#### Быстрый старт
```bash
# 1. Установите Homebrew (если нет)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. Установите PostgreSQL
brew install postgresql
brew services start postgresql

# 3. Клонируйте проект
git clone <url>
cd exeltest

# 4. Запустите установку
chmod +x setup.sh run.sh
./setup.sh

# 5. Настройте .env
nano .env

# 6. Запустите
./run.sh
```

---

## ☁️ Облачное развертывание

### Heroku

#### 1. Подготовка
```bash
# Установите Heroku CLI
curl https://cli-assets.heroku.com/install.sh | sh

# Войдите
heroku login
```

#### 2. Создание приложения
```bash
# Создайте приложение
heroku create your-excel-bot

# Добавьте PostgreSQL
heroku addons:create heroku-postgresql:hobby-dev

# Установите переменные окружения
heroku config:set TELEGRAM_BOT_TOKEN=8376816847:AAHIZW9X6GvxikBAFoLwZB76BjddeoBmCD0
heroku config:set DEEPSEEK_API_KEY=your_key
```

#### 3. Создайте Procfile
```bash
# Создайте файл Procfile
echo "worker: python bot.py" > Procfile
```

#### 4. Деплой
```bash
git add .
git commit -m "Deploy to Heroku"
git push heroku main

# Запустите воркер
heroku ps:scale worker=1

# Просмотр логов
heroku logs --tail
```

---

### VPS (DigitalOcean, Linode, AWS EC2)

#### 1. Подключение к серверу
```bash
ssh root@your_server_ip
```

#### 2. Установка зависимостей
```bash
# Обновление системы
apt update && apt upgrade -y

# Установка необходимого ПО
apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib git

# Настройка PostgreSQL
sudo -u postgres psql
CREATE DATABASE excel_bot;
CREATE USER bot_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE excel_bot TO bot_user;
\q
```

#### 3. Настройка бота
```bash
# Создание пользователя для бота
useradd -m -s /bin/bash botuser
su - botuser

# Клонирование проекта
git clone <your_repo_url> excel_bot
cd excel_bot

# Установка
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Настройка .env
nano .env
# Заполните все необходимые переменные
```

#### 4. Создание systemd сервиса
```bash
# Выйдите из пользователя botuser
exit

# Создайте сервис
sudo nano /etc/systemd/system/excel-bot.service
```

**Содержимое файла:**
```ini
[Unit]
Description=Excel Telegram Bot
After=network.target postgresql.service

[Service]
Type=simple
User=botuser
WorkingDirectory=/home/botuser/excel_bot
Environment="PATH=/home/botuser/excel_bot/venv/bin"
ExecStart=/home/botuser/excel_bot/venv/bin/python /home/botuser/excel_bot/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Запуск сервиса:**
```bash
# Перезагрузите systemd
sudo systemctl daemon-reload

# Запустите бота
sudo systemctl start excel-bot

# Добавьте в автозагрузку
sudo systemctl enable excel-bot

# Проверьте статус
sudo systemctl status excel-bot

# Просмотр логов
sudo journalctl -u excel-bot -f
```

---

### Docker (Опционально)

#### 1. Создайте Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей системы
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Копирование файлов
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Запуск бота
CMD ["python", "bot.py"]
```

#### 2. Создайте docker-compose.yml
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: excel_bot
      POSTGRES_USER: bot_user
      POSTGRES_PASSWORD: secure_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./schema.sql:/docker-entrypoint-initdb.d/schema.sql
    ports:
      - "5432:5432"

  bot:
    build: .
    depends_on:
      - postgres
    environment:
      TELEGRAM_BOT_TOKEN: "8376816847:AAHIZW9X6GvxikBAFoLwZB76BjddeoBmCD0"
      DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY}
      DB_HOST: postgres
      DB_PORT: 5432
      DB_NAME: excel_bot
      DB_USER: bot_user
      DB_PASSWORD: secure_password
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped

volumes:
  postgres_data:
```

#### 3. Запуск с Docker
```bash
# Создайте .env файл с токенами
nano .env

# Запустите
docker-compose up -d

# Просмотр логов
docker-compose logs -f bot

# Остановка
docker-compose down
```

---

## 🔐 Безопасность при деплое

### SSL/TLS для PostgreSQL
```bash
# В postgresql.conf
ssl = on
ssl_cert_file = '/path/to/server.crt'
ssl_key_file = '/path/to/server.key'
```

### Firewall настройка
```bash
# Ubuntu/Debian
sudo ufw allow ssh
sudo ufw allow 5432/tcp  # PostgreSQL (только для локальных подключений)
sudo ufw enable

# Ограничить PostgreSQL только для localhost
sudo nano /etc/postgresql/15/main/pg_hba.conf
# Измените:
# host all all 0.0.0.0/0 md5
# На:
# host all all 127.0.0.1/32 md5
```

### Ротация логов
```bash
# Создайте конфигурацию logrotate
sudo nano /etc/logrotate.d/excel-bot
```

```
/home/botuser/excel_bot/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
```

---

## 📊 Мониторинг

### Проверка статуса
```bash
# Статус сервиса
sudo systemctl status excel-bot

# Использование ресурсов
htop

# PostgreSQL статистика
sudo -u postgres psql excel_bot -c "SELECT * FROM pg_stat_activity;"
```

### Логирование
```bash
# Просмотр логов бота
sudo journalctl -u excel-bot -f

# PostgreSQL логи
sudo tail -f /var/log/postgresql/postgresql-15-main.log
```

### Алерты (опционально)
```bash
# Установка Prometheus и Grafana для мониторинга
# или использование облачных решений
```

---

## 🔄 Обновление на продакшене

### Без даунтайма
```bash
# 1. Подключитесь к серверу
ssh root@your_server_ip

# 2. Переключитесь на пользователя бота
su - botuser
cd excel_bot

# 3. Сделайте бэкап БД
pg_dump -U bot_user excel_bot > backup_$(date +%Y%m%d_%H%M%S).sql

# 4. Обновите код
git pull origin main

# 5. Обновите зависимости (если нужно)
source venv/bin/activate
pip install -r requirements.txt --upgrade

# 6. Перезапустите сервис
exit  # Выход из botuser
sudo systemctl restart excel-bot

# 7. Проверьте статус
sudo systemctl status excel-bot
```

---

## 🆘 Решение проблем

### Бот не запускается
```bash
# Проверьте логи
sudo journalctl -u excel-bot -n 50

# Проверьте .env файл
cat /home/botuser/excel_bot/.env

# Проверьте PostgreSQL
sudo systemctl status postgresql
```

### Проблемы с базой данных
```bash
# Проверьте подключение
psql -U bot_user -h localhost excel_bot

# Проверьте наличие таблиц
\dt

# Пересоздайте схему (осторожно!)
psql -U bot_user excel_bot < schema.sql
```

### Высокое использование памяти
```bash
# Проверьте процессы
ps aux | grep python

# Перезапустите бота
sudo systemctl restart excel-bot

# Настройте PostgreSQL для оптимизации
# В postgresql.conf:
shared_buffers = 256MB
effective_cache_size = 1GB
```

---

## 📋 Чеклист деплоя

- [ ] PostgreSQL установлен и запущен
- [ ] База данных создана
- [ ] Python 3.8+ установлен
- [ ] Виртуальное окружение создано
- [ ] Зависимости установлены
- [ ] .env файл настроен с правильными ключами
- [ ] Схема БД инициализирована
- [ ] Бот запускается без ошибок
- [ ] Firewall настроен
- [ ] Systemd сервис создан (для production)
- [ ] Логирование настроено
- [ ] Бэкапы настроены
- [ ] Мониторинг настроен (опционально)

---

## 📞 Поддержка

При возникновении проблем с развертыванием:
1. Проверьте логи: `sudo journalctl -u excel-bot -f`
2. Откройте Issue в репозитории
3. Опишите: ОС, версию Python, версию PostgreSQL, текст ошибки

---

**Успешного деплоя! 🚀**


