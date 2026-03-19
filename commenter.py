import asyncio
import json
from loguru import logger
from models import Account, SessionLocal
from session_manager import SessionManager
from telethon.tl.functions.messages import SendMessageRequest
from telethon.tl.types import InputPeerChannel
from telethon.tl.functions.channels import JoinChannelRequest
import re
import random
from datetime import datetime
from config import MIN_DELAY_BETWEEN_COMMENTS, MAX_DELAY_BETWEEN_COMMENTS

async def comment_on_post(post_url: str, comments_file: str):
    """Комментирование поста с использованием аккаунтов из базы данных"""
    # Извлекаем channel_id и post_id из URL
    match = re.search(r't\.me/c/(\d+)/(\d+)', post_url)
    if not match:
        print("Некорректная ссылка на пост")
        return
        
    channel_id = int(match.group(1))
    post_id = int(match.group(2))
    
    # Загружаем комментарии
    try:
        with open(comments_file, 'r', encoding='utf-8') as f:
            all_comments = json.load(f)
            
        if not all_comments:
            print("Файл с комментариями пуст")
            return
    except Exception as e:
        print(f"Ошибка при чтении файла с комментариями: {str(e)}")
        return
        
    # Получаем активные аккаунты из базы
    session = SessionLocal()
    try:
        accounts = session.query(Account).filter_by(is_active=True).all()
        if not accounts:
            print("Нет активных аккаунтов")
            return
            
        print(f"Найдено {len(accounts)} активных аккаунтов")
        
        # Проверяем, достаточно ли комментариев
        if len(all_comments) < len(accounts):
            print(f"Внимание: количество комментариев ({len(all_comments)}) меньше количества аккаунтов ({len(accounts)})")
            print("Некоторые комментарии будут использованы повторно")
            # Дублируем комментарии, чтобы хватило на всех
            while len(all_comments) < len(accounts):
                all_comments.extend(all_comments[:len(accounts) - len(all_comments)])
        
        # Перемешиваем комментарии
        random.shuffle(all_comments)
        
        # Распределяем комментарии между аккаунтами
        for i, account in enumerate(accounts):
            try:
                # Выбираем уникальный комментарий для этого аккаунта
                comment = all_comments[i]
                print(f"\nАккаунт {account.username} будет использовать комментарий: {comment}")
                
                # Создаем клиент из данных аккаунта
                client = await SessionManager.create_client_from_account(account)
                
                try:
                    # Подключаемся и проверяем авторизацию
                    await client.connect()
                    if not await client.is_user_authorized():
                        print(f"Аккаунт {account.username} не авторизован")
                        continue
                        
                    # Присоединяемся к каналу
                    channel = await client.get_entity(InputPeerChannel(channel_id, 0))
                    await client(JoinChannelRequest(channel))
                    
                    # Отправляем комментарий
                    await client(SendMessageRequest(
                        peer=channel,
                        message=comment,
                        reply_to_msg_id=post_id
                    ))
                    
                    print(f"Комментарий отправлен от аккаунта {account.username}")
                    
                    # Обновляем статистику
                    if not account.commented_posts:
                        account.commented_posts = []
                    if post_url not in account.commented_posts:
                        account.commented_posts.append(post_url)
                        
                    # Добавляем запись в историю комментариев
                    if not account.comments_history:
                        account.comments_history = []
                    account.comments_history.append({
                        'post_url': post_url,
                        'timestamp': datetime.utcnow().isoformat(),
                        'comment': comment
                    })
                    
                    session.commit()
                    
                    # Делаем случайную паузу между комментариями
                    delay = random.uniform(MIN_DELAY_BETWEEN_COMMENTS, MAX_DELAY_BETWEEN_COMMENTS)
                    print(f"Ожидание {delay:.1f} секунд перед следующим комментарием...")
                    await asyncio.sleep(delay)
                    
                finally:
                    await client.disconnect()
                    
            except Exception as e:
                print(f"Ошибка при комментировании от аккаунта {account.username}: {str(e)}")
                continue
                
    finally:
        session.close()

if __name__ == "__main__":
    post_url = input("Введите ссылку на пост: ")
    comments_file = input("Введите путь к файлу с комментариями (JSON): ")
    asyncio.run(comment_on_post(post_url, comments_file)) 