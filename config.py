import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Базовые пути
BASE_DIR = Path(__file__).parent
NEW_ACCOUNTS_DIR = os.path.join(BASE_DIR, "new_accounts")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# Создаем необходимые директории
for dir_path in [NEW_ACCOUNTS_DIR, LOGS_DIR]:
    os.makedirs(dir_path, exist_ok=True)



# Конфигурация базы данных
DATABASE_URL = 'sqlite:///database.sqlite3'

# Настройки задержек между комментариями (в секундах)
MIN_DELAY_BETWEEN_COMMENTS = 180  # Минимальная задержка
MAX_DELAY_BETWEEN_COMMENTS = 360  # Максимальная задержка 