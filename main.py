import asyncio
from loguru import logger
from models import Account, SessionLocal, Gender, Base, engine
from comment_manager import CommentManager
from backup import create_backup
import json
from datetime import datetime
import os
from config import DATABASE_URL

def print_menu():
    print("\n=== Менеджер аккаунтов и комментариев ===")
    print("1. Добавить новые аккаунты")
    print("2. Запустить комментирование")
    print("3. Показать статистику")
    print("4. Управление аккаунтами")
    print("5. Создать резервную копию")
    print("0. Выход")
    return input("Выберите действие: ")

def print_account_menu():
    print("\n=== Управление аккаунтами ===")
    print("1. Показать все аккаунты")
    print("2. Активировать аккаунт")
    print("3. Деактивировать аккаунт")
    print("4. Удалить аккаунт")
    print("5. Сбросить время последнего использования")
    print("6. Просмотр истории комментариев")
    print("0. Назад")
    return input("Выберите действие: ")

async def process_commenting():
    post_link = input("Введите ссылку на пост: ")
    comments_file = input("Введите путь к файлу с комментариями (JSON): ")
    
    if not os.path.exists(comments_file):
        logger.error(f"Файл {comments_file} не найден")
        return
        
    try:
        with open(comments_file, 'r', encoding='utf-8') as f:
            comments = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка при чтении JSON файла: {str(e)}")
        return
    except Exception as e:
        logger.error(f"Ошибка при чтении файла с комментариями: {str(e)}")
        return

    manager = CommentManager()
    try:
        await manager.process_comments(post_link, comments)
    except Exception as e:
        logger.error(f"Ошибка при обработке комментариев: {str(e)}")
    finally:
        manager.close()

def show_statistics():
    session = SessionLocal()
    try:
        stats = Account.get_statistics(session)
        print("\n=== Статистика ===")
        print(f"Всего аккаунтов: {stats['total_accounts']}")
        print(f"Активных аккаунтов: {stats['active_accounts']}")
        print(f"Заблокированных аккаунтов: {stats['blocked_accounts']}")
        print(f"Мужских аккаунтов: {stats['male_accounts']}")
        print(f"Женских аккаунтов: {stats['female_accounts']}")
        print(f"Всего комментариев: {stats['total_comments']}")
        print(f"Успешных комментариев: {stats['successful_comments']}")
        print(f"Неуспешных комментариев: {stats['failed_comments']}")
        print(f"Комментариев за последний час: {stats['hourly_comments']}")
        print(f"Уникальных постов: {stats['unique_posts']}")
        print(f"Среднее количество комментариев на аккаунт: {stats['average_comments_per_account']:.2f}")
    except Exception as e:
        logger.error(f"Ошибка при отображении статистики: {str(e)}")
        print("Произошла ошибка при получении статистики")
    finally:
        session.close()

def view_account_history():
    """Просмотр истории комментариев аккаунта"""
    try:
        acc_id = int(input("Введите ID аккаунта: "))
    except ValueError:
        logger.error("Ошибка: ID должен быть числом")
        return

    session = SessionLocal()
    try:
        # Получаем аккаунт
        account = session.query(Account).filter(Account.id == acc_id).first()
        if not account:
            logger.error(f"Аккаунт с ID {acc_id} не найден")
            return

        # Выводим основную информацию об аккаунте
        print(f"\nИнформация об аккаунте {account.username}:")
        print(f"ID: {account.id}")
        print(f"Пол: {account.gender.value}")
        print(f"Статус: {'Активен' if account.is_active else 'Деактивирован'}")
        print(f"Последнее использование: {account.last_used.strftime('%d.%m.%Y %H:%M:%S') if account.last_used else 'Нет данных'}")
        print(f"Количество ошибок: {account.error_count}")
        
        # Получаем историю комментариев
        comment_history = account.comment_history
        if not comment_history:
            print("\nАккаунт еще не оставлял комментариев")
            return

        # Выводим историю комментариев
        print(f"\nИстория комментариев ({len(comment_history)}):")
        print("-" * 80)
        for comment in comment_history:
            status = "Успешно" if comment.success else "Неуспешно"
            print(f"Пост: {comment.post_link}")
            print(f"Комментарий: {comment.comment_text}")
            print(f"Время: {comment.timestamp.strftime('%d.%m.%Y %H:%M:%S')}")
            print(f"Статус: {status}")
            print("-" * 80)

        # Выводим статистику комментариев
        total_comments = len(comment_history)
        successful_comments = sum(1 for comment in comment_history if comment.success)
        failed_comments = total_comments - successful_comments
        unique_posts = len(set(comment.post_link for comment in comment_history))
        
        print(f"\nСтатистика комментариев:")
        print(f"Всего комментариев: {total_comments}")
        print(f"Успешных комментариев: {successful_comments}")
        print(f"Неуспешных комментариев: {failed_comments}")
        print(f"Уникальных постов: {unique_posts}")

    except Exception as e:
        logger.error(f"Ошибка при просмотре истории: {str(e)}")
    finally:
        session.close()

def manage_accounts():
    while True:
        choice = print_account_menu()
        session = SessionLocal()
        
        try:
            if choice == "1":
                accounts = session.query(Account).all()
                print("\n=== Список аккаунтов ===")
                for acc in accounts:
                    status = "Активен" if acc.is_active else "Неактивен"
                    last_used = acc.last_used.strftime("%Y-%m-%d %H:%M:%S") if acc.last_used else "Никогда"
                    gender = "Мужской" if acc.gender == Gender.MALE else "Женский"
                    print(f"ID: {acc.id} | Имя: {acc.display_name} | Username: {acc.username} | "
                          f"Пол: {gender} | Статус: {status} | Последнее использование: {last_used}")
                    print("-" * 70)
            
            elif choice == "2":
                acc_id = input("Введите ID аккаунта для активации: ")
                account = session.query(Account).filter(Account.id == acc_id).first()
                if account:
                    account.is_active = True
                    account.error_count = 0
                    session.commit()
                    print(f"Аккаунт {account.username} активирован")
                else:
                    print("Аккаунт не найден")
            
            elif choice == "3":
                acc_id = input("Введите ID аккаунта для деактивации: ")
                account = session.query(Account).filter(Account.id == acc_id).first()
                if account:
                    account.is_active = False
                    session.commit()
                    print(f"Аккаунт {account.username} деактивирован")
                else:
                    print("Аккаунт не найден")
            
            elif choice == "4":
                acc_id = input("Введите ID аккаунта для удаления: ")
                account = session.query(Account).filter(Account.id == acc_id).first()
                if account:
                    session.delete(account)
                    session.commit()
                    print(f"Аккаунт {account.username} удален")
                else:
                    print("Аккаунт не найден")
            
            elif choice == "5":
                # Сбрасываем время последнего использования для всех аккаунтов
                accounts = session.query(Account).all()
                for account in accounts:
                    account.last_used = None
                session.commit()
                print("Время последнего использования сброшено для всех аккаунтов")
                
            elif choice == "6":
                view_account_history()
            
            elif choice == "0":
                break
            
        finally:
            session.close()

def ensure_database_exists():
    """Проверка наличия базы данных и её создание при необходимости"""
    db_path = DATABASE_URL.replace('sqlite:///', '')
    if not os.path.exists(db_path):
        print("База данных не найдена. Создаю новую базу данных...")
        try:
            Base.metadata.create_all(engine)
            print("База данных успешно создана")
        except Exception as e:
            print(f"Ошибка при создании базы данных: {str(e)}")
            exit(1)

async def main():
    ensure_database_exists()
    
    logger.add("logs/main.log", rotation="1 day")
    
    while True:
        choice = print_menu()
        
        if choice == "1":
            print("Запустите add_accounts.py отдельно для добавления аккаунтов")
        
        elif choice == "2":
            await process_commenting()
        
        elif choice == "3":
            show_statistics()
        
        elif choice == "4":
            manage_accounts()
            
        elif choice == "5":
            if create_backup():
                print("Резервная копия успешно создана")
            else:
                print("Ошибка при создании резервной копии. Проверьте logs/backup.log для деталей")
                
        elif choice == "0":
            print("Программа завершена")
            break
        
        else:
            print("Неверный выбор. Попробуйте снова.")

if __name__ == "__main__":
    asyncio.run(main()) 