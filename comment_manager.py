import asyncio
import json
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from telethon import TelegramClient
from telethon.tl.functions.messages import GetDiscussionMessageRequest
from telethon.tl.functions.channels import GetMessagesRequest, JoinChannelRequest, GetFullChannelRequest
from telethon.tl.functions.account import UpdateProfileRequest
from sqlalchemy import and_, or_
from loguru import logger
from models import Account, Gender, SessionLocal, CommentHistory
from config import (
    MIN_DELAY_BETWEEN_COMMENTS,
    MAX_DELAY_BETWEEN_COMMENTS
)
from telethon.sessions import MemorySession, StringSession
from proxy_manager import ProxyManager
from telethon.errors import PhoneCodeInvalidError, SessionPasswordNeededError
import time
from faker import Faker

class CommentManager:
    def __init__(self):
        self.session = SessionLocal()
        self.proxy_manager = ProxyManager()
        logger.add("logs/comment_manager.log", rotation="1 day")

    async def initialize(self):
        """Инициализация менеджера комментариев"""
        print("\nПроверка доступных прокси...")
        await self.proxy_manager.check_all_proxies()
        if not self.proxy_manager.proxies:
            print("Нет доступных прокси. Проверьте файл proxies.txt")
            return False
        return True

    def generate_name(self, gender: Gender) -> Tuple[str, str, str]:
        """Генерация имени и фамилии с учетом пола"""
        fake = Faker(['ru_RU'])
        if gender == Gender.MALE:
            first_name = fake.first_name_male()
            last_name = fake.last_name_male()
        else:
            first_name = fake.first_name_female()
            last_name = fake.last_name_female()
            
        # Возвращаем кортеж: (полное имя для display_name, имя, фамилия)
        return (f"{first_name} {last_name}", first_name, last_name)

    async def update_account_name(self, client: TelegramClient, first_name: str, last_name: str) -> bool:
        """Обновление имени аккаунта через Telegram API"""
        try:
            await client(UpdateProfileRequest(
                first_name=first_name,
                last_name=last_name
            ))
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении имени аккаунта: {str(e)}")
            return False

    async def create_client(self, account: Account) -> Optional[TelegramClient]:
        """Создание клиента Telegram с параметрами из аккаунта"""
        try:
            # Проверяем наличие всех необходимых данных аккаунта
            if not all([account.phone, account.app_id, account.app_hash, account.device_model,
                       account.system_version, account.app_version, account.lang_code,
                       account.system_lang_code]):
                logger.error(f"Недостаточно данных для аккаунта {account.phone}")
                return None

            # Получаем прокси
            proxy = self.proxy_manager.get_next_proxy()
            if not proxy:
                logger.error("Нет доступного прокси для подключения")
                return None
            
            logger.info(f"Используем прокси {proxy['addr']}:{proxy['port']} для аккаунта {account.phone}")
            
            # Форматируем прокси для Telethon
            telethon_proxy = {
                'proxy_type': proxy.get('proxy_type', 'socks5'),
                'addr': proxy['addr'],
                'port': proxy['port'],
                'username': proxy.get('username'),
                'password': proxy.get('password')
            }
            
            # Проверяем наличие и валидность строки сессии
            session_data = account.session_data
            if not session_data or not isinstance(session_data, dict):
                logger.error(f"Некорректные данные сессии для аккаунта {account.phone}")
                return None

            session_string = session_data.get('session_string')
            if not session_string:
                logger.error(f"Строка сессии отсутствует для аккаунта {account.phone}")
                return None

            try:
                # Проверяем валидность строки сессии
                test_session = StringSession(session_string)
                if not test_session:
                    logger.error(f"Некорректная строка сессии для аккаунта {account.phone}")
                    return None
            except Exception as e:
                logger.error(f"Ошибка при проверке строки сессии: {str(e)}")
                return None
            
            logger.info(f"Создаем клиент для аккаунта {account.phone}")
            # Логируем все параметры устройства
            logger.info(f"Параметры устройства для аккаунта {account.phone}:")
            logger.info(f"device_model: {account.device_model}")
            logger.info(f"system_version: {account.system_version}")
            logger.info(f"app_version: {account.app_version}")
            logger.info(f"lang_code: {account.lang_code}")
            logger.info(f"system_lang_code: {account.system_lang_code}")
            logger.info(f"app_id: {account.app_id}")
            logger.info(f"app_hash: {account.app_hash[:4]}...{account.app_hash[-4:]}")
            
            # Создаем клиент с параметрами устройства из базы данных
            client = TelegramClient(
                StringSession(session_string),
                account.app_id,
                account.app_hash,
                device_model=account.device_model,
                system_version=account.system_version,
                app_version=account.app_version,
                lang_code=account.lang_code,
                system_lang_code=account.system_lang_code,
                proxy=telethon_proxy
            )
            
            try:
                await client.connect()
                
                # Проверяем авторизацию
                if not await client.is_user_authorized():
                    logger.warning(f"Аккаунт {account.phone} не авторизован, пробуем повторную авторизацию...")
                    
                    try:
                        # Отправляем код подтверждения
                        sent_code = await client.send_code_request(account.phone)
                        
                        # Определяем тип отправленного кода
                        code_type = "Telegram" if sent_code.type.__class__.__name__ == "SentCodeTypeApp" else "SMS"
                        logger.info(f"Код подтверждения отправлен через {code_type}")
                        
                        while True:
                            code = input(f"Введите код из {code_type} для номера {account.phone}: ")
                            if not code.strip():
                                continue
                                
                            try:
                                # Пытаемся войти с кодом
                                await client.sign_in(account.phone, code)
                                logger.success(f"Код из {code_type} успешно принят")
                                
                                # Сохраняем новую строку сессии
                                new_session_string = client.session.save()
                                account.session_data = {'session_string': new_session_string}
                                self.session.commit()
                                
                                break
                            except PhoneCodeInvalidError:
                                logger.error(f"Введен неверный код из {code_type}")
                                retry = input("Попробовать ввести код снова? (д/н): ").lower()
                                if retry != 'д':
                                    raise Exception("Отменено пользователем")
                            except SessionPasswordNeededError:
                                # Если требуется пароль (двухфакторная аутентификация)
                                logger.info("Требуется двухфакторная аутентификация")
                                while True:
                                    try:
                                        password = input("Введите пароль от аккаунта (двухфакторная аутентификация): ")
                                        await client.sign_in(password=password)
                                        logger.success("Успешная авторизация с двухфакторной аутентификацией")
                                        
                                        # Сохраняем новую строку сессии
                                        new_session_string = client.session.save()
                                        account.session_data = {'session_string': new_session_string}
                                        self.session.commit()
                                        
                                        break
                                    except Exception as e:
                                        logger.error(f"Ошибка при вводе пароля: {str(e)}")
                                        retry = input("Попробовать ввести пароль снова? (д/н): ").lower()
                                        if retry != 'д':
                                            raise Exception("Отменено пользователем")
                                break
                            except Exception as e:
                                logger.error(f"Ошибка при вводе кода: {str(e)}")
                                retry = input("Попробовать ввести код снова? (д/н): ").lower()
                                if retry != 'д':
                                    raise Exception("Отменено пользователем")
                                
                    except Exception as e:
                        logger.error(f"Ошибка при повторной авторизации: {str(e)}")
                        await client.disconnect()
                        return None
                    
                    # Проверяем, что мы действительно авторизованы
                    try:
                        me = await client.get_me()
                        if not me or me.phone != account.phone:
                            logger.error(f"Несоответствие данных аккаунта для {account.phone}")
                            await client.disconnect()
                            return None
                    except Exception as e:
                        logger.error(f"Ошибка при проверке данных аккаунта: {str(e)}")
                        await client.disconnect()
                        return None
                    
                    logger.success(f"Успешное подключение аккаунта {account.phone}")
                return client
                
            except Exception as e:
                logger.error(f"Ошибка при подключении клиента: {str(e)}")
                if client:
                    await client.disconnect()
                return None
            
        except Exception as e:
            logger.error(f"Ошибка при создании клиента для аккаунта {account.phone}: {str(e)}")
            return None

    async def join_channel(self, client: TelegramClient, channel: str) -> bool:
        """Присоединение к каналу перед комментированием"""
        try:
            entity = await client.get_entity(channel)
            await client(JoinChannelRequest(entity))
            logger.info(f"Успешно присоединились к каналу {channel}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при присоединении к каналу: {str(e)}")
            return False

    async def get_discussion_group(self, client: TelegramClient, channel: str, message_id: int) -> Optional[tuple]:
        """Получение группы обсуждений для канала"""
        try:
            # Получаем информацию о канале
            channel_entity = await client.get_entity(channel)
            
            # Получаем полную информацию о канале
            full_channel = await client(GetFullChannelRequest(channel_entity))
            
            # Проверяем наличие связанной группы обсуждений
            if hasattr(full_channel, 'full_chat') and hasattr(full_channel.full_chat, 'linked_chat_id') and full_channel.full_chat.linked_chat_id:
                try:
                    # Пытаемся получить информацию о группе обсуждений
                    linked_chat = await client.get_entity(full_channel.full_chat.linked_chat_id)
                    logger.info(f"Найдена связанная группа обсуждений: {linked_chat.title}")
                    
                    # Пытаемся присоединиться к группе обсуждений
                    try:
                        await client(JoinChannelRequest(linked_chat))
                        logger.info(f"Запрошено присоединение к группе обсуждений {linked_chat.title}")
                        await asyncio.sleep(5)  # Даем время на обработку запроса
                    except Exception as e:
                        if "You have successfully requested to join this chat or channel" in str(e):
                            logger.info("Запрос на присоединение к группе отправлен")
                            await asyncio.sleep(5)  # Даем время на обработку
                        elif "You are already a participant" in str(e):
                            logger.info("Уже являемся участником группы обсуждений")
                        else:
                            logger.error(f"Ошибка при присоединении к группе: {str(e)}")
                    
                    # Проверяем, что мы действительно присоединились к группе
                    try:
                        await client.get_entity(linked_chat)
                        logger.info("Подтверждено членство в группе обсуждений")
                    except Exception as e:
                        logger.error(f"Не удалось подтвердить членство в группе: {str(e)}")
                        return None, None
                    
                    # Получаем сообщение для комментирования в группе обсуждений
                    try:
                        discussion = await client(GetDiscussionMessageRequest(
                            peer=channel_entity,
                            msg_id=message_id
                        ))
                        if discussion and discussion.messages:
                            discussion_message_id = discussion.messages[0].id
                            logger.info(f"Найдено сообщение в группе обсуждений с ID: {discussion_message_id}")
                            return linked_chat, discussion_message_id
                    except Exception as e:
                        logger.error(f"Ошибка при получении сообщения для обсуждения: {str(e)}")
                    
                except Exception as e:
                    logger.error(f"Ошибка при работе с группой обсуждений: {str(e)}")
                
            return None, None
        except Exception as e:
            logger.error(f"Ошибка при получении группы обсуждений: {str(e)}")
            return None, None

    async def post_comment(self, account: Account, post_link: str, comment_text: str) -> bool:
        """Публикация комментария"""
        client = None
        try:
            # Создаем клиент
            client = await self.create_client(account)
            if not client:
                logger.error(f"Не удалось создать клиент для аккаунта {account.phone}")
                return False

            # Получаем информацию о текущем пользователе
            me = await client.get_me()
            if not me:
                logger.error("Не удалось получить информацию о текущем пользователе")
                return False

            # Парсим ссылку на пост
            try:
                # Удаляем https://t.me/ из ссылки
                post_link = post_link.replace('https://t.me/', '')
                
                # Разделяем на канал и ID сообщения
                channel, message_id = post_link.split('/')
                message_id = int(message_id)
                
                # Получаем сущность канала
                channel_entity = await client.get_entity(channel)
                
                # Получаем сообщение
                message = await client.get_messages(channel_entity, ids=message_id)
                if not message:
                    logger.error(f"Не удалось получить сообщение {message_id} из канала {channel}")
                    return False
                
                logger.info(f"Успешно получено сообщение {message_id} из канала {channel}")
                
            except ValueError as e:
                logger.error(f"Некорректный формат ссылки на пост: {str(e)}")
                return False
            except Exception as e:
                logger.error(f"Ошибка при получении информации о посте: {str(e)}")
                return False

            # Проверяем, не комментировал ли уже этот аккаунт данный пост
            try:
                async for reply in client.iter_messages(channel_entity, reply_to=message_id, limit=100):
                    if hasattr(reply, 'from_id') and hasattr(reply.from_id, 'user_id') and reply.from_id.user_id == me.id:
                        logger.warning(f"Аккаунт {account.phone} уже комментировал этот пост")
                        return False
            except Exception as e:
                logger.warning(f"Не удалось проверить предыдущие комментарии: {str(e)}")
                # Продолжаем выполнение, так как это не критическая ошибка

            # Пытаемся присоединиться к каналу перед комментированием
            try:
                await client(JoinChannelRequest(channel_entity))
                logger.info(f"Успешно присоединились к каналу {channel}")
                # Даем время на обработку присоединения
                await asyncio.sleep(2)
            except Exception as e:
                logger.warning(f"Не удалось присоединиться к каналу {channel}: {str(e)}")
                # Продолжаем выполнение, так как возможно мы уже подписаны

            # Публикуем комментарий
            try:
                # Проверяем наличие группы обсуждений
                discussion_group, discussion_message_id = await self.get_discussion_group(client, channel, message_id)
                
                if discussion_group and discussion_message_id:
                    # Если есть группа обсуждений, сначала присоединяемся к ней
                    try:
                        # Проверяем, не являемся ли мы уже участником группы
                        try:
                            await client.get_entity(discussion_group)
                            logger.info(f"Уже являемся участником группы обсуждений {discussion_group.title}")
                        except Exception:
                            # Если не являемся участником, пытаемся присоединиться
                            try:
                                await client(JoinChannelRequest(discussion_group))
                                logger.info(f"Запрошено присоединение к группе обсуждений {discussion_group.title}")
                                await asyncio.sleep(10)  # Увеличиваем время ожидания
                            except Exception as e:
                                if "You have successfully requested to join this chat or channel" in str(e):
                                    logger.info("Запрос на присоединение к группе отправлен, ожидаем подтверждения")
                                    await asyncio.sleep(10)  # Увеличиваем время ожидания
                                elif "You are already a participant" in str(e):
                                    logger.info("Уже являемся участником группы обсуждений")
                                else:
                                    raise e
                        
                        # Даем дополнительное время на обработку
                        await asyncio.sleep(10)
                        
                        # Проверяем, что мы действительно присоединились к группе
                        try:
                            await client.get_entity(discussion_group)
                            logger.info("Подтверждено членство в группе обсуждений")
                        except Exception as e:
                            logger.error(f"Не удалось подтвердить членство в группе: {str(e)}")
                            return False
                        
                        # Пытаемся получить сообщение для комментирования
                        try:
                            discussion_message = await client.get_messages(discussion_group, ids=discussion_message_id)
                            if not discussion_message:
                                logger.error("Не удалось получить сообщение в группе обсуждений")
                                return False
                            
                            # Комментируем в группе обсуждений
                            await client.send_message(discussion_group, comment_text, reply_to=discussion_message_id)
                            logger.info(f"Комментарий успешно опубликован в группе обсуждений от аккаунта {account.phone}")
                            
                            # Проверяем, что комментарий действительно появился
                            await asyncio.sleep(2)
                            try:
                                # async for reply in client.iter_messages(discussion_group, reply_to=discussion_message_id, limit=10):
                                #     if hasattr(reply, 'from_id') and hasattr(reply.from_id, 'user_id') and reply.from_id.user_id == me.id:
                                #         logger.info(f"Подтверждено: комментарий успешно опубликован в группе обсуждений")
                                #         return True
                                async for reply in client.iter_messages(discussion_group, limit=10):
                                    if reply.reply_to and reply.reply_to.reply_to_msg_id == discussion_message_id:
                                        if hasattr(reply.from_id, 'user_id') and reply.from_id.user_id == me.id:
                                            logger.info(f"Комментарий подтвержден")
                                            return True
                            
                            except Exception as e:
                                logger.warning(f"Не удалось проверить публикацию комментария: {str(e)}")
                                # Считаем комментарий успешным, так как он был отправлен
                                return True
                            
                            logger.error("Не удалось подтвердить публикацию комментария в группе обсуждений")
                            return False
                            
                        except Exception as e:
                            logger.error(f"Ошибка при отправке комментария в группе обсуждений: {str(e)}")
                            return False
                            
                    except Exception as e:
                        logger.error(f"Ошибка при работе с группой обсуждений: {str(e)}")
                        return False
                else:
                    # Если нет группы обсуждений, комментируем под постом
                    await client.send_message(channel_entity, comment_text, reply_to=message_id)
                    logger.info(f"Комментарий успешно опубликован под постом от аккаунта {account.phone}")
                    
                    # Проверяем, что комментарий действительно появился
                    await asyncio.sleep(2)
                    try:
                        async for reply in client.iter_messages(channel_entity, reply_to=message_id, limit=10):
                            if hasattr(reply, 'from_id') and hasattr(reply.from_id, 'user_id') and reply.from_id.user_id == me.id:
                                logger.info(f"Подтверждено: комментарий успешно опубликован")
                                return True
                    except Exception as e:
                        logger.warning(f"Не удалось проверить публикацию комментария: {str(e)}")
                        # Считаем комментарий успешным, так как он был отправлен
                        return True
                    
                    logger.error("Не удалось подтвердить публикацию комментария")
                    return False
                
            except Exception as e:
                logger.error(f"Ошибка при публикации комментария: {str(e)}")
                return False
            
        except Exception as e:
            logger.error(f"Ошибка при публикации комментария: {str(e)}")
            return False
        finally:
            if client:
                await client.disconnect()

    async def get_suitable_account(self, session: SessionLocal, gender_str: str) -> Optional[Account]:
        """Получение подходящего аккаунта для комментирования"""
        try:
            # Преобразуем строковое значение пола в enum
            gender = None
            if gender_str.lower() == 'male':
                gender = Gender.MALE
            elif gender_str.lower() == 'female':
                gender = Gender.FEMALE
            
            logger.info(f"Преобразован пол из комментария: {gender_str} -> {gender}")
            
            if not gender:
                logger.error(f"Некорректное значение пола: {gender_str}")
                return None
            
            # Получаем все активные аккаунты с нужным полом
            suitable_accounts = session.query(Account).filter(
                Account.gender == gender,
                Account.is_active == True
            ).all()
            
            logger.info(f"Найдено {len(suitable_accounts)} подходящих аккаунтов для пола {gender_str}")
            
            # Логируем информацию о всех аккаунтах
            logger.info(f"Всего аккаунтов в базе: {session.query(Account).count()}")
            for acc in session.query(Account).all():
                logger.info(f"Аккаунт {acc.username}: пол={acc.gender}, активен={acc.is_active}, последнее использование={acc.last_used}")
            
            # Проверяем каждый подходящий аккаунт
            for account in suitable_accounts:
                logger.info(f"Проверяем аккаунт {account.username} с полом {account.gender}")
                logger.info(f"Статус аккаунта: активен={account.is_active}, последнее использование={account.last_used}")
                
                # Проверяем время последнего использования
                if account.last_used:
                    time_since_last_use = datetime.utcnow() - account.last_used
                    if time_since_last_use.total_seconds() < MIN_DELAY_BETWEEN_COMMENTS:
                        logger.info(f"Аккаунт {account.username} использовался слишком недавно")
                        continue
                    
                logger.info(f"Выбран аккаунт {account.username} для комментирования")
                return account
            
            logger.warning(f"Не найдено подходящих аккаунтов для пола {gender_str}")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при поиске подходящего аккаунта: {str(e)}")
            return None

    def update_account_status(self, account: Account, post_link: str, success: bool, comment_text: str):
        """Обновление статуса аккаунта после попытки комментирования"""
        max_retries = 3
        retry_delay = 2  # увеличиваем задержку между попытками
        
        for attempt in range(max_retries):
            try:
                # Создаем новую сессию для каждой попытки
                session = SessionLocal()
                
                try:
                    # Получаем актуальную версию аккаунта
                    account = session.query(Account).filter(Account.id == account.id).first()
                    if not account:
                        logger.error(f"Аккаунт {account.id} не найден в базе данных")
                        return
                    
                    if success:
                        # Обновляем время последнего использования только при успешном комментировании
                        account.last_used = datetime.utcnow()
                        
                        # Создаем новую запись в истории комментариев
                        comment = CommentHistory(
                            account_id=account.id,
                            post_link=post_link,
                            comment_text=comment_text,
                            timestamp=datetime.utcnow(),
                            success=True
                        )
                        session.add(comment)
                        
                        # Уменьшаем счетчик ошибок при успешном комментировании
                        if account.error_count > 0:
                            account.error_count -= 1
                    else:
                        # При неудаче только увеличиваем счетчик ошибок
                        account.error_count += 1
                        if account.error_count >= 3:
                            account.is_active = False
                            logger.warning(f"Аккаунт {account.username} деактивирован после множественных ошибок")

                        # Создаем запись о неудачной попытке
                        comment = CommentHistory(
                            account_id=account.id,
                            post_link=post_link,
                            comment_text=comment_text,
                            timestamp=datetime.utcnow(),
                            success=False
                        )
                        session.add(comment)

                    # Сохраняем изменения
                    session.commit()
                    logger.info(f"Статус аккаунта {account.username} успешно обновлен")
                    return
                    
                except Exception as e:
                    session.rollback()
                    raise e
                finally:
                    session.close()
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Попытка {attempt + 1} обновления статуса аккаунта не удалась: {str(e)}")
                    time.sleep(retry_delay * (attempt + 1))  # увеличиваем задержку с каждой попыткой
                else:
                    logger.error(f"Не удалось обновить статус аккаунта после {max_retries} попыток: {str(e)}")
                    # Создаем отдельную сессию для логирования ошибки
                    try:
                        error_session = SessionLocal()
                        error_comment = CommentHistory(
                            account_id=account.id,
                            post_link=post_link,
                            comment_text=f"Ошибка обновления статуса: {str(e)}",
                            timestamp=datetime.utcnow(),
                            success=False
                        )
                        error_session.add(error_comment)
                        error_session.commit()
                    except Exception as log_error:
                        logger.error(f"Не удалось записать ошибку в базу данных: {str(log_error)}")
                    finally:
                        error_session.close()

    def get_account_statistics(self, account: Account) -> dict:
        """Получение статистики аккаунта"""
        try:
            # Создаем новую сессию для получения актуальных данных
            session = SessionLocal()
            
            try:
                # Получаем актуальную версию аккаунта
                account = session.query(Account).filter(Account.id == account.id).first()
                if not account:
                    logger.error(f"Аккаунт {account.id} не найден в базе данных")
                    return None
                
                # Получаем все комментарии аккаунта
                comments = session.query(CommentHistory).filter(
                    CommentHistory.account_id == account.id
                ).order_by(CommentHistory.timestamp.desc()).all()
                
                total_comments = len(comments)
                successful_comments = sum(1 for comment in comments if comment.success)
                failed_comments = total_comments - successful_comments
                
                # Получаем уникальные посты
                unique_posts = set(comment.post_link for comment in comments)
                
                # Получаем комментарии за последний час
                hour_ago = datetime.utcnow() - timedelta(hours=1)
                recent_comments = [
                    comment for comment in comments
                    if comment.timestamp > hour_ago
                ]
                
                # Получаем комментарии за последние 24 часа
                day_ago = datetime.utcnow() - timedelta(days=1)
                comments_last_24h = [
                    comment for comment in comments
                    if comment.timestamp > day_ago
                ]
                
                # Форматируем время последнего использования
                last_used = account.last_used.strftime('%d.%m.%Y %H:%M:%S') if account.last_used else 'Нет данных'
                
                # Подготавливаем детальную информацию о комментариях
                comments_info = []
                for comment in comments:
                    comment_info = {
                        'post_link': comment.post_link,
                        'comment_text': comment.comment_text,
                        'timestamp': comment.timestamp.strftime('%d.%m.%Y %H:%M:%S'),
                        'success': comment.success,
                        'status': 'Успешно' if comment.success else 'Неудачно'
                    }
                    comments_info.append(comment_info)
                
                return {
                    'username': account.username,
                    'phone': account.phone,
                    'gender': 'Мужской' if account.gender == Gender.MALE else 'Женский',
                    'status': 'Активен' if account.is_active else 'Неактивен',
                    'total_comments': total_comments,
                    'successful_comments': successful_comments,
                    'failed_comments': failed_comments,
                    'success_rate': f"{(successful_comments / total_comments * 100):.1f}%" if total_comments > 0 else "0%",
                    'unique_posts': len(unique_posts),
                    'comments_last_hour': len(recent_comments),
                    'comments_last_24h': len(comments_last_24h),
                    'error_count': account.error_count,
                    'last_used': last_used,
                    'comments': comments_info
                }
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Ошибка при получении статистики аккаунта: {str(e)}")
            return None

    def get_overall_statistics(self) -> dict:
        """Получение общей статистики по всем аккаунтам"""
        try:
            # Создаем новую сессию для получения актуальных данных
            session = SessionLocal()
            
            try:
                # Получаем все аккаунты
                accounts = session.query(Account).all()
                total_accounts = len(accounts)
                active_accounts = sum(1 for acc in accounts if acc.is_active)
                male_accounts = sum(1 for acc in accounts if acc.gender == Gender.MALE)
                female_accounts = sum(1 for acc in accounts if acc.gender == Gender.FEMALE)
                
                # Получаем все комментарии
                comments = session.query(CommentHistory).all()
                total_comments = len(comments)
                successful_comments = sum(1 for comment in comments if comment.success)
                failed_comments = total_comments - successful_comments
                
                # Получаем уникальные посты
                unique_posts = set(comment.post_link for comment in comments)
                
                # Получаем комментарии за последний час
                hour_ago = datetime.utcnow() - timedelta(hours=1)
                comments_last_hour = sum(1 for comment in comments if comment.timestamp > hour_ago)
                
                # Получаем комментарии за последние 24 часа
                day_ago = datetime.utcnow() - timedelta(days=1)
                comments_last_24h = sum(1 for comment in comments if comment.timestamp > day_ago)
                
                # Вычисляем среднее количество комментариев на аккаунт
                avg_comments = total_comments / total_accounts if total_accounts > 0 else 0
                
                # Вычисляем процент успешных комментариев
                success_rate = (successful_comments / total_comments * 100) if total_comments > 0 else 0
                
                # Получаем последние комментарии
                recent_comments = session.query(CommentHistory).order_by(
                    CommentHistory.timestamp.desc()
                ).limit(10).all()
                
                recent_comments_info = []
                for comment in recent_comments:
                    account = session.query(Account).filter(Account.id == comment.account_id).first()
                    comment_info = {
                        'account_username': account.username if account else 'Неизвестный аккаунт',
                        'post_link': comment.post_link,
                        'comment_text': comment.comment_text,
                        'timestamp': comment.timestamp.strftime('%d.%m.%Y %H:%M:%S'),
                        'success': comment.success,
                        'status': 'Успешно' if comment.success else 'Неудачно'
                    }
                    recent_comments_info.append(comment_info)
                
                return {
                    'total_accounts': total_accounts,
                    'active_accounts': active_accounts,
                    'blocked_accounts': total_accounts - active_accounts,
                    'male_accounts': male_accounts,
                    'female_accounts': female_accounts,
                    'total_comments': total_comments,
                    'successful_comments': successful_comments,
                    'failed_comments': failed_comments,
                    'success_rate': f"{success_rate:.1f}%",
                    'comments_last_hour': comments_last_hour,
                    'comments_last_24h': comments_last_24h,
                    'unique_posts': len(unique_posts),
                    'avg_comments_per_account': round(avg_comments, 2),
                    'recent_comments': recent_comments_info,
                    'accounts': [
                        self.get_account_statistics(account)
                        for account in accounts
                    ]
                }
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Ошибка при получении общей статистики: {str(e)}")
            return None

    async def process_comments(self, post_link: str, comments: List[Dict]) -> None:
        """Обработка списка комментариев"""
        # Инициализация и проверка прокси
        if not await self.initialize():
            return

        try:
            # Создаем словари для отслеживания использованных комментариев и аккаунтов
            used_comments = {}  # {comment_text: account_username}
            used_accounts = set()  # множество использованных аккаунтов для этого поста
            
            # Получаем все аккаунты, которые уже комментировали этот пост
            session = SessionLocal()
            try:
                existing_comments = session.query(CommentHistory).filter(
                    CommentHistory.post_link == post_link,
                    CommentHistory.success == True  # Учитываем только успешные комментарии
                ).all()
                used_accounts.update(comment.account_id for comment in existing_comments)
                logger.info(f"Найдено {len(used_accounts)} аккаунтов, которые уже комментировали этот пост")
            finally:
                session.close()
            
            # Если все аккаунты уже использованы, прекращаем обработку
            if len(used_accounts) >= len(comments):
                logger.info("Все аккаунты уже использованы для комментирования этого поста")
                return
            
            for comment in comments:
                gender_str = comment.get('gender')
                text = comment.get('text')
                
                if not gender_str or not text:
                    logger.error("Некорректный формат комментария")
                    continue
                
                # Проверяем, не был ли этот текст комментария уже использован
                comment_key = text.strip().lower()
                if comment_key in used_comments:
                    logger.warning(f"Комментарий уже был использован аккаунтом {used_comments[comment_key]}")
                    continue
                    
                logger.info(f"Обработка комментария с полом: {gender_str}")
                
                # Получаем подходящий аккаунт
                session = SessionLocal()
                try:
                    account = await self.get_suitable_account(session, gender_str)
                finally:
                    session.close()
                    
                if not account:
                    logger.error(f"Не найден подходящий аккаунт для пола {gender_str}")
                    continue
                
                # Проверяем, не использовался ли уже этот аккаунт для комментирования этого поста
                if account.id in used_accounts:
                    logger.warning(f"Аккаунт {account.username} уже комментировал этот пост")
                    continue
                    
                # Публикуем комментарий
                success = await self.post_comment(account, post_link, text)
                
                if success:
                    # Обновляем статистику только при успешном комментировании
                    max_retries = 3
                    retry_delay = 2
                    
                    for attempt in range(max_retries):
                        try:
                            # Создаем новую сессию для обновления статистики
                            stats_session = SessionLocal()
                            try:
                                # Получаем актуальную версию аккаунта
                                account = stats_session.query(Account).filter(Account.id == account.id).first()
                                if not account:
                                    logger.error(f"Аккаунт {account.id} не найден в базе данных")
                                    break
                                
                                # Создаем запись в истории комментариев
                                comment_history = CommentHistory(
                                    account_id=account.id,
                                    post_link=post_link,
                                    comment_text=text,
                                    timestamp=datetime.utcnow(),
                                    success=True
                                )
                                stats_session.add(comment_history)
                                
                                # Обновляем время последнего использования аккаунта
                                account.last_used = datetime.utcnow()
                                
                                # Сохраняем изменения
                                stats_session.commit()
                                logger.info(f"Статистика успешно обновлена для аккаунта {account.username}")
                                
                                # Добавляем аккаунт в список использованных
                                used_accounts.add(account.id)
                                used_comments[comment_key] = account.username
                                break  # Выходим из цикла попыток при успехе
                                
                            except Exception as e:
                                stats_session.rollback()
                                if attempt < max_retries - 1:
                                    logger.warning(f"Попытка {attempt + 1} обновления статистики не удалась: {str(e)}")
                                    await asyncio.sleep(retry_delay * (attempt + 1))
                                else:
                                    logger.error(f"Не удалось обновить статистику после {max_retries} попыток: {str(e)}")
                            finally:
                                stats_session.close()
                                
                        except Exception as e:
                            if attempt < max_retries - 1:
                                logger.warning(f"Попытка {attempt + 1} создания сессии не удалась: {str(e)}")
                                await asyncio.sleep(retry_delay * (attempt + 1))
                            else:
                                logger.error(f"Не удалось создать сессию после {max_retries} попыток: {str(e)}")
                
                # Добавляем случайную задержку между комментариями
                delay = random.randint(MIN_DELAY_BETWEEN_COMMENTS, MAX_DELAY_BETWEEN_COMMENTS)
                logger.info(f"Ожидание {delay} секунд перед следующим комментарием")
                await asyncio.sleep(delay)
                
        except Exception as e:
            logger.error(f"Ошибка при обработке комментариев: {str(e)}")
        finally:
            session.close()

    def close(self):
        """Закрытие менеджера комментариев"""
        try:
            if hasattr(self, 'session'):
                self.session.close()
            logger.info("Менеджер комментариев успешно закрыт")
        except Exception as e:
            logger.error(f"Ошибка при закрытии менеджера комментариев: {str(e)}")