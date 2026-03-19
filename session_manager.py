import os
import json
from datetime import datetime
from models import Account, SessionLocal
# from config import API_ID, API_HASH
from loguru import logger
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from proxy_manager import ProxyManager

# Инициализация менеджера прокси
proxy_manager = ProxyManager()

class SessionManager:
    def __init__(self):
        self.session = SessionLocal()
        
    async def create_session(self, account: Account) -> bool:
        """Создание новой сессии для аккаунта"""
        try:
            # Проверяем прокси перед созданием сессии
            proxy = proxy_manager.get_next_proxy()
            if not proxy:
                logger.error(f"Нет доступного прокси для аккаунта {account.username}")
                return False
                
            logger.info(f"Используем прокси: {proxy['addr']}:{proxy['port']}")
            
            # Создаем клиент с прокси
            client = TelegramClient(
                StringSession(),
                account.app_id,
                account.app_hash,
                device_model=account.device_model,
                system_version=account.system_version,
                app_version=account.app_version,
                lang_code=account.lang_code,
                system_lang_code=account.system_lang_code,
                proxy=proxy
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.error(f"Аккаунт {account.username} не авторизован")
                return False
                
            # Получаем строку сессии
            session_string = client.session.save()
            
            # Обновляем данные сессии в базе
            account.session_data = {'session_string': session_string}
            account.last_used = datetime.utcnow()
            self.session.commit()
            
            logger.success(f"Создана новая сессия для аккаунта {account.username}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при создании сессии для аккаунта {account.username}: {str(e)}")
            return False
            
        finally:
            if 'client' in locals() and client.is_connected():
                await client.disconnect()
                
    def close(self):
        """Закрытие сессии базы данных"""
        self.session.close()

    @staticmethod
    async def test_session(client: TelegramClient) -> bool:
        """Проверяет работоспособность сессии"""
        try:
            await client.connect()
            if not await client.is_user_authorized():
                return False
            me = await client.get_me()
            return True
        except Exception as e:
            return False
        finally:
            await client.disconnect() 