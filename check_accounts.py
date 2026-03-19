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

async def check_accounts():
    """Проверка всех аккаунтов в базе"""
    session = SessionLocal()
    
    # Проверяем прокси перед началом работы
    print("\nПроверка доступных прокси...")
    await proxy_manager.check_all_proxies()
    if not proxy_manager.proxies:
        logger.error("Нет доступных прокси. Проверьте файл proxies.txt")
        print("Нет доступных прокси. Проверьте файл proxies.txt")
        return
        
    print(f"Найдено рабочих прокси: {len(proxy_manager.proxies)}")
    
    try:
        accounts = session.query(Account).all()
        
        if not accounts:
            print("В базе нет аккаунтов")
            return
            
        print(f"\nНайдено аккаунтов в базе: {len(accounts)}")
        
        for account in accounts:
            print(f"\nПроверка аккаунта: {account.username}")
            
            # Получаем прокси для клиента
            proxy = proxy_manager.get_next_proxy()
            if not proxy:
                logger.error(f"Нет доступного прокси для аккаунта {account.username}")
                print(f"Нет доступного прокси для аккаунта {account.username}")
                continue
                
            print(f"Используем прокси: {proxy['addr']}:{proxy['port']}")
            
            try:
                # Создаем клиент с прокси
                client = TelegramClient(
                    StringSession(account.session_data['session_string']),
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
                    print(f"Аккаунт {account.username} не авторизован")
                    continue
                    
                me = await client.get_me()
                
                if not me:
                    print(f"Аккаунт {account.username} недоступен")
                    continue
                    
                print(f"Аккаунт {account.username} работает")
                print(f"Имя: {me.first_name} {me.last_name or ''}")
                print(f"Телефон: {me.phone}")
                print(f"ID: {me.id}")
                
            except Exception as e:
                print(f"Ошибка при проверке аккаунта {account.username}: {str(e)}")
                
            finally:
                if 'client' in locals() and client.is_connected():
                    await client.disconnect()
                    
    except Exception as e:
        print(f"Ошибка при проверке аккаунтов: {str(e)}")
        
    finally:
        session.close()

if __name__ == "__main__":
    logger.add("logs/check_accounts.log", rotation="1 day")
    print("=== Проверка аккаунтов ===")
    import asyncio
    asyncio.run(check_accounts()) 