import os
import json
import random
import shutil
from pathlib import Path
from faker import Faker
from datetime import datetime
from models import Account, Gender, SessionLocal, Base, engine
from config import NEW_ACCOUNTS_DIR, DATABASE_URL
from loguru import logger
from telethon.sync import TelegramClient
from telethon.tl.functions.account import UpdateProfileRequest
import asyncio
from typing import Tuple, Dict, Optional
from telethon.sessions import StringSession
from proxy_manager import ProxyManager
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from sqlalchemy.orm import Session

# Инициализация менеджера прокси
proxy_manager = ProxyManager()

# Настраиваем Faker для генерации русских имен
fake = Faker(['ru_RU'])
Faker.seed(0)  # Для воспроизводимости результатов

def ensure_database_exists():
    """Проверка наличия базы данных и её создание при необходимости"""
    db_path = DATABASE_URL.replace('sqlite:///', '')
    if not os.path.exists(db_path):
        logger.info("База данных не найдена. Создаю новую базу данных...")
        try:
            Base.metadata.create_all(engine)
            logger.info("База данных успешно создана")
        except Exception as e:
            logger.error(f"Ошибка при создании базы данных: {str(e)}")
            exit(1)

def ask_gender(username: str) -> Gender:
    """Запрос пола аккаунта у пользователя"""
    while True:
        gender_input = input(f"\nУкажите пол для аккаунта {username} (м/ж): ").lower()
        if gender_input in ['м', 'm', 'мужской', 'male']:
            return Gender.MALE
        elif gender_input in ['ж', 'f', 'женский', 'female']:
            return Gender.FEMALE
        print("Некорректный ввод. Используйте 'м' или 'ж'")

def generate_name(gender: Gender) -> Tuple[str, str, str]:
    """Генерация имени и фамилии с учетом пола"""
    # Современные русские имена
    male_names = [
        "Александр", "Дмитрий", "Максим", "Сергей", "Андрей", "Алексей", "Артём", "Илья", "Кирилл", "Михаил",
        "Иван", "Даниил", "Денис", "Егор", "Никита", "Константин", "Тимофей", "Владислав", "Евгений", "Матвей",
        "Семён", "Фёдор", "Георгий", "Лев", "Павел", "Василий", "Пётр", "Глеб", "Марк", "Ярослав"
    ]
    
    female_names = [
        "Анна", "Елена", "Мария", "Евгения", "Ольга", "Анастасия", "Татьяна", "Екатерина", "Наталья", "Марина",
        "Ирина", "Юлия", "Светлана", "Кристина", "Александра", "Вероника", "Алиса", "Дарья", "Ксения", "Ангелина",
        "Полина", "София", "Арина", "Валерия", "Виктория", "Диана", "Кира", "Лилия", "Маргарита", "Милана"
    ]
    
    # Базовые русские фамилии (мужские формы)
    base_surnames = [
        "Иванов", "Смирнов", "Кузнецов", "Попов", "Васильев", "Петров", "Соколов", "Михайлов", "Новиков", "Федоров",
        "Морозов", "Волков", "Алексеев", "Лебедев", "Семенов", "Егоров", "Павлов", "Козлов", "Степанов", "Николаев",
        "Орлов", "Андреев", "Макаров", "Никитин", "Захаров", "Зайцев", "Соловьев", "Борисов", "Яковлев", "Григорьев",
        "Романов", "Воробьев", "Сергеев", "Кузьмин", "Фролов", "Александров", "Дмитриев", "Королев", "Гусев", "Киселев",
        "Ильин", "Максимов", "Поляков", "Сорокин", "Виноградов", "Ковалев", "Белов", "Медведев", "Антонов", "Тарасов"
    ]
    
    if gender == Gender.MALE:
        first_name = random.choice(male_names)
        last_name = random.choice(base_surnames)
    else:
        first_name = random.choice(female_names)
        # Преобразуем мужскую фамилию в женскую
        base_surname = random.choice(base_surnames)
        if base_surname.endswith('ов'):
            last_name = base_surname[:-2] + 'ова'
        elif base_surname.endswith('ев'):
            last_name = base_surname[:-2] + 'ева'
        elif base_surname.endswith('ин'):
            last_name = base_surname[:-2] + 'ина'
        elif base_surname.endswith('ский'):
            last_name = base_surname[:-4] + 'ская'
        else:
            last_name = base_surname + 'а'
    
    # Возвращаем кортеж: (полное имя для display_name, имя, фамилия)
    return (f"{first_name} {last_name}", first_name, last_name)

def get_approved_name(username: str, gender: Gender, current_first_name: str = None, current_last_name: str = None) -> Tuple[str, str, str]:
    """Генерация и подтверждение имени пользователем"""
    # Если имя уже установлено, предлагаем пропустить
    if current_first_name or current_last_name:
        current_name = f"{current_first_name} {current_last_name or ''}".strip()
        print(f"\nТекущее имя для {username}: {current_name}")
        choice = input("Оставить текущее имя? (д/н): ").lower()
        if choice in ['д', 'y', 'да', 'yes']:
            return current_name, current_first_name, current_last_name or ''
    
    while True:
        display_name, first_name, last_name = generate_name(gender)
        gender_str = "мужской" if gender == Gender.MALE else "женский"
        print(f"\nСгенерированное имя для {username} (пол: {gender_str}):")
        print(f"Полное имя: {display_name}")
        
        choice = input("Подтвердить имя? (д/н/т - для теста других вариантов/в - ввести вручную): ").lower()
        if choice in ['д', 'y', 'да', 'yes']:
            return display_name, first_name, last_name
        elif choice in ['т', 't', 'тест', 'test']:
            print("\nПримеры других имен для этого пола:")
            test_names = []
            for i in range(5):
                test_display, test_first, test_last = generate_name(gender)
                test_names.append((test_display, test_first, test_last))
                print(f"{i+1}. {test_display}")
            
            while True:
                test_choice = input("\nВыберите номер имени (1-5) или нажмите Enter для возврата: ")
                if not test_choice:
                    break
                try:
                    index = int(test_choice) - 1
                    if 0 <= index < len(test_names):
                        return test_names[index]
                    else:
                        print("Некорректный номер. Выберите от 1 до 5.")
                except ValueError:
                    print("Пожалуйста, введите число от 1 до 5.")
        elif choice in ['в', 'v', 'ввод', 'manual']:
            print("\nВведите имя и фамилию вручную:")
            while True:
                manual_first = input("Введите имя: ").strip()
                manual_last = input("Введите фамилию: ").strip()
                if manual_first and manual_last:
                    manual_display = f"{manual_first} {manual_last}"
                    print(f"\nПроверьте введенное имя: {manual_display}")
                    confirm = input("Подтвердить? (д/н): ").lower()
                    if confirm in ['д', 'y', 'да', 'yes']:
                        return manual_display, manual_first, manual_last
                    elif confirm in ['н', 'n', 'нет', 'no']:
                        break
                else:
                    print("Имя и фамилия не могут быть пустыми. Попробуйте еще раз.")
        elif choice in ['н', 'n', 'нет', 'no']:
            continue
        else:
            print("Некорректный ввод. Используйте 'д' (да), 'н' (нет), 'т' (тест) или 'в' (ввод вручную)")

async def update_account_name(client: TelegramClient, first_name: str, last_name: str) -> bool:
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

async def authorize_client(phone: str, api_id: int, api_hash: str, proxy: Optional[Dict] = None) -> Optional[TelegramClient]:
    """Авторизация клиента"""
    client = None
    try:
        # Создаем клиент
        client = TelegramClient(
            StringSession(),
            api_id,
            api_hash,
            proxy=proxy
        )
        
        if not client:
            logger.error("Не удалось создать клиент")
            return None

        # Подключаемся
        await client.connect()
        if not await client.is_user_authorized():
            # Отправляем код
            await client.send_code_request(phone)
            code = input("Введите код из Telegram: ")
            
            try:
                # Вводим код
                    await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                # Если требуется пароль от двухфакторной аутентификации
                password = input("Введите пароль от двухфакторной аутентификации: ")
                await client.sign_in(password=password)
        
        return client
    except Exception as e:
        logger.error(f"Ошибка при авторизации клиента: {str(e)}")
        return None
    finally:
        if client and not client.is_connected():
            await client.disconnect()

async def reauthorize_account(account: Account) -> bool:
    """Повторная авторизация аккаунта с учетом двухфакторной аутентификации"""
    try:
        me, session_string = await authorize_client(
            account.phone,
            account.app_id,
            account.app_hash,
            account.proxy
        )
        
        # Обновляем данные сессии
        account.session_data = {
            'session_string': session_string,
            'dc_id': me.dc_id,
            'user_id': me.id
        }
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при повторной авторизации аккаунта {account.username}: {str(e)}")
        return False

async def check_proxy_availability(proxy_manager: ProxyManager, max_attempts: int = 3) -> bool:
    """Проверка доступности прокси с несколькими попытками"""
    for attempt in range(1, max_attempts + 1):
        print(f"\nПроверка доступных прокси (попытка {attempt}/{max_attempts})...")
        
        # Проверяем прокси
        await proxy_manager.check_all_proxies()
        
        if proxy_manager.proxies:
            logger.success(f"Найдено {len(proxy_manager.proxies)} рабочих прокси")
            print(f"Найдено рабочих прокси: {len(proxy_manager.proxies)}")
            
            # Выводим информацию о каждом прокси
            for i, proxy in enumerate(proxy_manager.proxies, 1):
                logger.info(f"Прокси {i}: {proxy['addr']}:{proxy['port']} (тип: {proxy.get('proxy_type', 'socks5')})")
            return True
        
        if attempt < max_attempts:
            print(f"\nНе удалось найти рабочие прокси. Повторная попытка через 5 секунд...")
            await asyncio.sleep(5)
    
    logger.error("Не удалось найти рабочие прокси после всех попыток")
    return False

def format_proxy_for_telethon(proxy: Dict) -> Dict:
    """Форматирование прокси для использования в Telethon клиенте"""
    proxy_type = proxy.get('proxy_type', 'socks5')
    formatted_proxy = {
        'proxy_type': proxy_type,
        'addr': proxy['addr'],
        'port': proxy['port'],
    }
    
    # Добавляем credentials если есть
    if 'username' in proxy and 'password' in proxy:
        formatted_proxy.update({
            'username': proxy['username'],
            'password': proxy['password']
        })
    
    return formatted_proxy

async def process_new_accounts():
    ensure_database_exists()
    
    # Проверяем прокси перед началом работы
    if not await check_proxy_availability(proxy_manager):
        return
        
    # Поиск новых аккаунтов в директории new_accounts
    accounts_dir = "new_accounts"
    
    # Проверяем существование директории new_accounts
    if not os.path.exists(accounts_dir):
        logger.error(f"Директория {accounts_dir} не существует")
        print(f"\nОшибка: Директория {accounts_dir} не существует")
        return
        
    # Проверяем, что это директория
    if not os.path.isdir(accounts_dir):
        logger.error(f"{accounts_dir} не является директорией")
        print(f"\nОшибка: {accounts_dir} не является директорией")
        return
        
    print(f"\nПоиск аккаунтов в директории: {accounts_dir}")
    
    session = SessionLocal()
    
    try:
        # Получаем список папок
        account_dirs = [d for d in os.listdir(accounts_dir) if os.path.isdir(os.path.join(accounts_dir, d))]
        
        if not account_dirs:
            logger.warning(f"В директории {accounts_dir} нет папок с аккаунтами")
            print(f"\nВ директории {accounts_dir} нет папок с аккаунтами")
            return
            
        print(f"\nНайдено папок: {len(account_dirs)}")
        
        # Проходим по всем папкам в new_accounts
        for account_dir in account_dirs:
            dir_path = os.path.join(accounts_dir, account_dir)
            print(f"\nПроверка папки: {account_dir}")
            
            # Ищем JSON файл в папке
            json_files = [f for f in os.listdir(dir_path) if f.endswith('.json')]
            if not json_files:
                print(f"В папке {account_dir} нет JSON файлов")
                continue
                
            # Берем первый найденный JSON файл
            json_file = os.path.join(dir_path, json_files[0])
            print(f"Найден JSON файл: {json_file}")
            
            try:
                # Читаем данные из JSON файла
                with open(json_file, 'r', encoding='utf-8') as f:
                    account_data = json.load(f)
                    
                # Проверяем наличие API_ID и API_HASH в JSON
                api_id = account_data.get('app_id')
                api_hash = account_data.get('app_hash')
                
                if not api_id or not api_hash:
                    print(f"В JSON файле отсутствуют app_id или app_hash")
                    continue
                    
                print(f"\nДанные из JSON файла {json_file}:")
                print(f"API_ID: {api_id}")
                print(f"API_HASH: {api_hash[:4]}...{api_hash[-4:]}")  # Показываем только начало и конец для безопасности
                
                # Получаем номер телефона из JSON
                phone = account_data.get('phone')
                if not phone:
                    print(f"В JSON файле не найден номер телефона")
                    continue
                    
                print(f"Номер телефона из JSON: {phone}")
                
                # Ищем файл сессии по номеру телефона
                session_file = os.path.join(dir_path, f"{phone}.session")
                print(f"Ожидаемый файл сессии: {session_file}")
                
                if not os.path.exists(session_file):
                    print(f"Файл сессии не найден")
                    continue
                    
                print(f"Файл сессии найден")
                
                # Создаем клиент Telethon с параметрами из JSON
                print(f"\nСоздаем клиент с параметрами:")
                print(f"API_ID: {api_id}")
                print(f"API_HASH: {api_hash[:4]}...{api_hash[-4:]}")
                
                # Получаем прокси для клиента
                proxy = proxy_manager.get_next_proxy()
                if not proxy:
                    logger.error("Нет доступного прокси для подключения")
                    print("Нет доступного прокси для подключения")
                    continue
                    
                # Форматируем прокси для Telethon
                telethon_proxy = format_proxy_for_telethon(proxy)
                print(f"Используем прокси: {proxy['addr']}:{proxy['port']}")
                
                # Получаем параметры устройства из JSON
                device = account_data.get('device', 'Desktop')
                sdk = account_data.get('sdk', 'Windows 10')
                app_version = account_data.get('app_version', '4.8.1')
                lang_pack = account_data.get('lang_pack', 'en')
                system_lang_pack = account_data.get('system_lang_pack', 'en')
                
                print(f"\nПараметры устройства из JSON:")
                print(f"Устройство: {device}")
                print(f"SDK: {sdk}")
                print(f"Версия приложения: {app_version}")
                print(f"Язык: {lang_pack}")
                print(f"Системный язык: {system_lang_pack}")
                
                client = TelegramClient(
                    session_file,
                    api_id,
                    api_hash,
                    device_model=device,
                    system_version=sdk,
                    app_version=app_version,
                    lang_code=lang_pack,
                    system_lang_code=system_lang_pack,
                    proxy=telethon_proxy
                )
                
                try:
                    print("Подключение к Telegram...")
                    await client.connect()
                    
                    if not await client.is_user_authorized():
                        logger.error(f"Аккаунт {phone} не авторизован")
                        print(f"Аккаунт {phone} не авторизован")
                        print("\nПопытка повторной авторизации...")
                        
                        if await reauthorize_account(account_data):
                            print("Повторная авторизация успешна, продолжаем обработку аккаунта")
                        else:
                            print("Не удалось повторно авторизовать аккаунт")
                            continue
                    
                    # Получаем информацию о пользователе через API
                    me = await client.get_me()
                    
                    # Получаем username из API с подробным логированием
                    if me.username:
                        username = me.username
                        logger.info(f"Получен username из API: @{username}")
                    else:
                        username = phone
                        logger.info(f"Username не установлен в Telegram, используем номер телефона: {username}")
                    
                    # Проверяем существование аккаунта в базе по обоим параметрам
                    existing_account = session.query(Account).filter(
                        (Account.username == username) | (Account.phone == phone)
                    ).first()

                    if existing_account:
                        logger.info(f"Аккаунт уже существует в базе (username: {existing_account.username}, phone: {existing_account.phone})")
                        print(f"Аккаунт уже существует в базе")
                        continue
                    
                    print(f"\nИнформация об аккаунте из API:")
                    print(f"Username: @{me.username or 'отсутствует'}")
                    print(f"Имя: {me.first_name} {me.last_name or ''}")
                    print(f"ID пользователя: {me.id}")
                    print(f"Номер телефона: {me.phone}")
                    print(f"Премиум статус: {'Да' if me.premium else 'Нет'}")
                    print(f"Верифицирован: {'Да' if me.verified else 'Нет'}")
                    
                    # Запрашиваем пол у пользователя
                    gender = ask_gender(phone)
                    # Получаем подтвержденное имя, передавая текущие имя и фамилию
                    display_name, first_name, last_name = get_approved_name(phone, gender, me.first_name, me.last_name)
                    
                    # Обновляем имя через API только если оно изменилось
                    name_updated = True
                    if first_name != me.first_name or last_name != (me.last_name or ''):
                        try:
                            name_updated = await update_account_name(client, first_name, last_name)
                            if not name_updated:
                                logger.error(f"Не удалось обновить имя для аккаунта {phone}")
                                print(f"Не удалось обновить имя для аккаунта {phone}")
                                print("Возможные причины:")
                                print("1. Аккаунт удален/деактивирован")
                                print("2. Слишком много запросов на изменение имени")
                                print("3. Проблемы с подключением к Telegram")
                                continue
                        except Exception as e:
                            logger.error(f"Ошибка при обновлении имени аккаунта {phone}: {str(e)}")
                            print(f"Ошибка при обновлении имени аккаунта {phone}: {str(e)}")
                            continue

                    # Создаем новую сессию в памяти
                    string_session = StringSession()
                    
                    # Создаем новый клиент с сессией в памяти и прокси
                    proxy = proxy_manager.get_next_proxy()
                    if not proxy:
                        logger.error("Нет доступного прокси для нового клиента")
                        print("Нет доступного прокси для нового клиента")
                        continue
                        
                    logger.info(f"Используем прокси для нового клиента: {proxy['addr']}:{proxy['port']}")
                        
                    temp_client = TelegramClient(
                        string_session,
                        api_id,
                        api_hash,
                        device_model=device,
                        system_version=sdk,
                        app_version=app_version,
                        lang_code=lang_pack,
                        system_lang_code=system_lang_pack,
                        proxy=proxy
                    )
                    
                    try:
                        # Подключаемся и копируем данные авторизации
                        await temp_client.connect()
                        
                        # Копируем данные сессии из оригинального клиента
                        temp_client.session.set_dc(
                            client.session.dc_id,
                            client.session.server_address,
                            client.session.port
                        )
                        temp_client.session.auth_key = client.session.auth_key
                        
                        # Получаем строку сессии
                        session_string = temp_client.session.save()
                        await temp_client.disconnect()
                    except Exception as e:
                        logger.error(f"Ошибка при работе с временным клиентом: {str(e)}")
                        return False

                    # Создаем новый аккаунт
                    new_account = Account(
                        username=username,
                        display_name=display_name,
                        gender=gender,
                        session_data={'session_string': session_string},
                        last_used=datetime.utcnow(),
                        commented_posts=[],
                        hourly_comments=[],  # Инициализируем список часовых комментариев
                        app_id=api_id,
                        app_hash=api_hash,
                        device_model=device,
                        system_version=sdk,
                        app_version=app_version,
                        lang_code=lang_pack,
                        system_lang_code=system_lang_pack,
                        user_id=me.id,
                        phone=phone
                    )

                    # Добавляем аккаунт в базу
                    session.add(new_account)
                    session.commit()
                    logger.success(f"Добавлен новый аккаунт: {username} с именем {display_name}")
                    print(f"Аккаунт {username} успешно добавлен в базу")
                    
                    # После успешного добавления аккаунта, можно удалить исходные файлы
                    if await process_account_data(account_data, session):
                        try:
                            # Сначала отключаем клиент
                            await client.disconnect()
                            print("Отключение от Telegram...")
                            
                            # Ждем немного, чтобы все процессы освободили файлы
                            await asyncio.sleep(2)
                            
                            # Пробуем удалить файлы с повторными попытками
                            max_attempts = 3
                            for attempt in range(max_attempts):
                                try:
                                    if os.path.exists(session_file):
                                        os.remove(session_file)
                                    if os.path.exists(json_file):
                                        os.remove(json_file)
                                    if os.path.exists(dir_path):
                                        os.rmdir(dir_path)
                                    logger.info(f"Исходные файлы аккаунта {phone} удалены")
                                    print(f"Исходные файлы аккаунта {phone} удалены")
                                    break
                                except Exception as e:
                                    if attempt < max_attempts - 1:
                                        logger.warning(f"Попытка {attempt + 1} удалить файлы не удалась: {str(e)}")
                                        await asyncio.sleep(1)
                                    else:
                                        raise e
                        except Exception as e:
                            logger.error(f"Ошибка при удалении файлов аккаунта {phone}: {str(e)}")
                            print(f"Ошибка при удалении файлов аккаунта {phone}: {str(e)}")
                            
                finally:
                    # Отключаем клиента только если он еще не отключен
                    if client.is_connected():
                        await client.disconnect()
                        print("Отключение от Telegram...")
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке аккаунта в папке {account_dir}: {str(e)}")
                print(f"Ошибка при обработке аккаунта в папке {account_dir}: {str(e)}")
                session.rollback()
                    
    except Exception as e:
        logger.error(f"Ошибка при обработке новых аккаунтов: {str(e)}")
        print(f"Ошибка при обработке новых аккаунтов: {str(e)}")
    finally:
        session.close()

async def process_account_data(account_data: Dict, session: Session) -> bool:
    """Обработка данных аккаунта и добавление в базу"""
    try:
        phone = account_data['phone']
        username = account_data.get('username') or phone
        
        # Проверяем существование аккаунта по номеру телефона или username
        existing_account = session.query(Account).filter(
            (Account.username == username) | (Account.phone == phone)
        ).first()
        
        if existing_account:
            if existing_account.phone == phone:
                logger.info(f"Аккаунт с номером {phone} уже существует в базе")
            else:
                logger.info(f"Аккаунт с username {username} уже существует в базе")
            return False
        
        logger.info(f"Добавляем новый аккаунт: username={username}, phone={phone}")
        
        # Добавляем аккаунт в базу
        new_account = Account(
            phone=phone,
            username=username,
            display_name=account_data.get('first_name', ''),
            gender=account_data.get('gender', Gender.MALE),
            app_id=account_data['app_id'],
            app_hash=account_data['app_hash'],
            device_model=account_data.get('device', 'Desktop'),
            system_version=account_data.get('sdk', 'Windows 10'),
            app_version=account_data.get('app_version', '4.8.1'),
            lang_code=account_data.get('lang_pack', 'en'),
            system_lang_code=account_data.get('system_lang_pack', 'en'),
            is_active=True,
            last_used=datetime.utcnow(),
            commented_posts=[],
            hourly_comments=[]
        )
        
        session.add(new_account)
        session.commit()
        logger.success(f"Аккаунт успешно добавлен в базу (phone: {phone}, username: {username})")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при добавлении аккаунта в базу: {str(e)}")
        session.rollback()
        return False

if __name__ == "__main__":
    logger.add("logs/add_accounts.log", rotation="1 day")
    print("=== Добавление новых аккаунтов ===")
    print("Для каждого аккаунта будет запрошен пол (м/ж)")
    print("После выбора пола вы сможете подтвердить сгенерированное имя или сгенерировать новое")
    asyncio.run(process_new_accounts()) 