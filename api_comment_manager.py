from typing import List, Dict, Optional
from loguru import logger
import asyncio
import random
from comment_manager import CommentManager
from models import CommentHistory
from config import MIN_DELAY_BETWEEN_COMMENTS, MAX_DELAY_BETWEEN_COMMENTS

class APICommentManager(CommentManager):
    """Расширенная версия CommentManager для API с поддержкой детальной информации о результатах"""
    
    async def process_comments_with_details(self, post_link: str, comments: List[Dict]) -> Dict:
        """
        Версия process_comments для API, возвращающая детальную информацию о результатах
        
        Args:
            post_link (str): Ссылка на пост для комментирования
            comments (List[Dict]): Список комментариев с полями 'gender' и 'text'
            
        Returns:
            Dict: Словарь с результатами:
                - success_count: количество успешных комментариев
                - error_count: количество ошибок
                - account_results: список результатов по каждому аккаунту
                - errors: список ошибок
        """
        # Инициализация и проверка прокси
        if not await self.initialize():
            return {
                "success_count": 0,
                "error_count": 1,
                "account_results": [],
                "errors": ["Ошибка инициализации прокси"]
            }

        account_results = []
        success_count = 0
        error_details = []

        # Проверяем, есть ли уже комментарии к этому посту
        existing_comments = self.session.query(CommentHistory).filter(
            CommentHistory.post_link == post_link
        ).all()
        
        existing_account_ids = [comment.account_id for comment in existing_comments]
        logger.info(f"Найдено {len(existing_account_ids)} аккаунтов, которые уже комментировали этот пост")

        # Словари для отслеживания использованных комментариев и аккаунтов
        used_comments = {}  # {comment_text: account_username}
        used_accounts = set(existing_account_ids)  # множество использованных аккаунтов для этого поста

        for comment in comments:
            try:
                # Нормализация текста комментария
                comment_text = comment['text'].strip()
                if isinstance(comment_text, bytes):
                    comment_text = comment_text.decode('utf-8')

                # Проверяем, не был ли этот текст комментария уже использован
                comment_key = comment_text.lower()
                if comment_key in used_comments:
                    error_msg = f"Комментарий уже был использован аккаунтом {used_comments[comment_key]}"
                    logger.warning(error_msg)
                    error_details.append(error_msg)
                    continue

                # Получаем подходящий аккаунт
                account = await self.get_suitable_account(self.session, comment['gender'])
                
                if not account:
                    error_msg = f"Не найден подходящий аккаунт для пола {comment['gender']}"
                    logger.error(error_msg)
                    error_details.append(error_msg)
                    continue

                # Проверяем, не использовался ли уже этот аккаунт для комментирования этого поста
                if account.id in used_accounts:
                    error_msg = f"Аккаунт {account.username} уже комментировал этот пост"
                    logger.warning(error_msg)
                    error_details.append(error_msg)
                    continue

                result = {
                    "username": account.username,
                    "gender": comment['gender'],
                    "success": False,
                    "error": None,
                    "comment_text": comment_text  # Используем нормализованный текст
                }

                try:
                    # Пытаемся опубликовать комментарий
                    comment_success = await self.post_comment(account, post_link, comment_text)
                    
                    if comment_success:
                        success_count += 1
                        result["success"] = True
                        # Обновляем статистику аккаунта
                        self.update_account_status(account, post_link, True, comment_text)
                        # Добавляем в использованные
                        used_accounts.add(account.id)
                        used_comments[comment_key] = account.username
                    else:
                        error_msg = f"Не удалось опубликовать комментарий от аккаунта {account.username}"
                        result["error"] = error_msg
                        error_details.append(error_msg)
                        # Обновляем статистику аккаунта с ошибкой
                        self.update_account_status(account, post_link, False, comment_text)

                except Exception as e:
                    error_msg = f"Ошибка при публикации комментария от аккаунта {account.username}: {str(e)}"
                    result["error"] = error_msg
                    error_details.append(error_msg)
                    logger.error(f"Ошибка при публикации комментария: {str(e)}")
                    # Обновляем статистику аккаунта с ошибкой
                    self.update_account_status(account, post_link, False, comment_text)

                finally:
                    account_results.append(result)

                # Ждем случайное время перед следующим комментарием
                if comment != comments[-1]:  # Если это не последний комментарий
                    delay = random.randint(MIN_DELAY_BETWEEN_COMMENTS, MAX_DELAY_BETWEEN_COMMENTS)
                    logger.info(f"Ожидание {delay} секунд перед следующим комментарием")
                    await asyncio.sleep(delay)

            except Exception as e:
                error_msg = f"Ошибка при обработке комментария: {str(e)}"
                error_details.append(error_msg)
                logger.error(error_msg)

        # Возвращаем детальный результат
        return {
            "success_count": success_count,
            "error_count": len(error_details),
            "account_results": account_results,
            "errors": error_details
        } 