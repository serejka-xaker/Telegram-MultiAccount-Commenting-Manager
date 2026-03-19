import os
import shutil
import json
from datetime import datetime
from pathlib import Path
from models import Account, SessionLocal
from config import BASE_DIR, NEW_ACCOUNTS_DIR
from loguru import logger

def create_backup():
    """Создание резервной копии базы данных и файлов сессий"""
    try:
        # Создаем директорию для бэкапов
        backup_dir = os.path.join(BASE_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)

        # Создаем временную директорию для сбора файлов
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_backup_path = os.path.join(backup_dir, f'temp_{timestamp}')
        os.makedirs(temp_backup_path, exist_ok=True)

        # Копируем файл базы данных
        db_file = os.path.join(BASE_DIR, 'database.sqlite3')
        if os.path.exists(db_file):
            shutil.copy2(db_file, os.path.join(temp_backup_path, 'database.sqlite3'))

        # Создаем JSON дамп данных аккаунтов
        session = SessionLocal()
        try:
            accounts = session.query(Account).all()
            accounts_data = []
            
            for account in accounts:
                account_data = {
                    'username': account.username,
                    'display_name': account.display_name,
                    'gender': account.gender.value,
                    'session_data': account.session_data,
                    'is_active': account.is_active,
                    'last_used': account.last_used.isoformat() if account.last_used else None,
                    'created_at': account.created_at.isoformat(),
                    'commented_posts': account.commented_posts,
                    'error_count': account.error_count
                }
                accounts_data.append(account_data)

            # Сохраняем данные в JSON
            with open(os.path.join(temp_backup_path, 'accounts.json'), 'w', encoding='utf-8') as f:
                json.dump(accounts_data, f, ensure_ascii=False, indent=2)

        finally:
            session.close()

        # Копируем папку new_accounts
        if os.path.exists(NEW_ACCOUNTS_DIR):
            new_accounts_backup_dir = os.path.join(temp_backup_path, 'new_accounts')
            shutil.copytree(NEW_ACCOUNTS_DIR, new_accounts_backup_dir)

        # Копируем папку accounts (если она существует)
        accounts_dir = os.path.join(BASE_DIR, "accounts")
        if os.path.exists(accounts_dir):
            accounts_backup_dir = os.path.join(temp_backup_path, 'accounts')
            shutil.copytree(accounts_dir, accounts_backup_dir)

        # Создаем архив
        archive_name = os.path.join(backup_dir, f'backup_{timestamp}.zip')
        shutil.make_archive(os.path.join(backup_dir, f'backup_{timestamp}'), 'zip', temp_backup_path)

        # Удаляем временную директорию
        shutil.rmtree(temp_backup_path)

        # Очистка старых бэкапов (оставляем только последние 5)
        backups = sorted(Path(backup_dir).glob('backup_*.zip'), key=os.path.getmtime)
        if len(backups) > 5:
            for old_backup in backups[:-5]:
                os.remove(old_backup)

        logger.success(f"Резервная копия успешно создана: {archive_name}")
        return True

    except Exception as e:
        logger.error(f"Ошибка при создании резервной копии: {str(e)}")
        if 'temp_backup_path' in locals() and os.path.exists(temp_backup_path):
            shutil.rmtree(temp_backup_path)
        return False

if __name__ == "__main__":
    logger.add("logs/backup.log", rotation="1 day")
    create_backup() 