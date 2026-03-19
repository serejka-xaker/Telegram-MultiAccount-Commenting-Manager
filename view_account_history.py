from models import SessionLocal, Account
from datetime import datetime
from loguru import logger

def format_timestamp(timestamp_str: str) -> str:
    """Форматирование временной метки в читаемый вид"""
    dt = datetime.fromisoformat(timestamp_str)
    return dt.strftime("%d.%m.%Y %H:%M:%S")

def view_account_history(username: str):
    """Просмотр истории комментариев аккаунта"""
    session = SessionLocal()
    try:
        # Получаем аккаунт
        account = session.query(Account).filter(Account.username == username).first()
        if not account:
            logger.error(f"Аккаунт {username} не найден")
            return

        # Выводим основную информацию об аккаунте
        print(f"\nИнформация об аккаунте {username}:")
        print(f"Пол: {account.gender.value}")
        print(f"Статус: {'Активен' if account.is_active else 'Деактивирован'}")
        print(f"Последнее использование: {format_timestamp(account.last_used.isoformat()) if account.last_used else 'Нет данных'}")
        print(f"Количество ошибок: {account.error_count}")
        
        # Получаем историю комментариев
        comment_history = account.get_comment_history()
        if not comment_history:
            print("\nАккаунт еще не оставлял комментариев")
            return

        # Выводим историю комментариев
        print(f"\nИстория комментариев ({len(comment_history)}):")
        print("-" * 80)
        for comment in comment_history:
            print(f"Пост: {comment['post_url']}")
            print(f"Комментарий: {comment['comment']}")
            print(f"Время: {format_timestamp(comment['timestamp'])}")
            print("-" * 80)

        # Выводим список прокомментированных постов
        commented_posts = account.get_commented_posts()
        if commented_posts:
            print(f"\nСписок прокомментированных постов ({len(commented_posts)}):")
            for post in commented_posts:
                print(f"- {post}")
        else:
            print("\nСписок прокомментированных постов пуст")

    except Exception as e:
        logger.error(f"Ошибка при просмотре истории: {str(e)}")
    finally:
        session.close()

if __name__ == "__main__":
    username = input("Введите username аккаунта: ")
    view_account_history(username) 