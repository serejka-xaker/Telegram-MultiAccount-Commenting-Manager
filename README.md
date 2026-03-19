# Telegram-MultiAccount-Commenting-Manager

Программа для автоматизации написания комментариев под постами в Telegram c множества аккаунтов

## Требования

- Python 3.10 или выше
- Telegram аккаунты
- Прокси (SOCKS5/HTTP)

## Структура проекта

```
├── add_accounts.py    # Скрипт для добавления аккаунтов в базу данных
├── main.py           # Основное меню управления программой
├── api.py            # API версия основного меню
├── config.py         # Файл для настройки задержки между комментариями, будет время между MIN_DELAY_BETWEEN_COMMENTS и MAX_DELAY_BETWEEN_COMMENTS
├── proxies.txt       # Файл со списком прокси
├── new_accounts/     # Папка для новых аккаунтов (для импорта)
└── accounts/         # Папка для хранения аккаунтов (опционально)
```

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/serejka-xaker/Telegram-MultiAccount-Commenting-Manager.git
cd Telegram-MultiAccount-Commenting-Manager
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

## Настройка

### 1. Подготовка аккаунтов
- Создайте папку с данными аккаунта в директории `new_accounts/`
- Каждый аккаунт в отдельной папке
- Структура папки аккаунта должна содержать необходимые файлы сессии Telegram

### 2. Настройка прокси
- Добавьте прокси в файл `proxies.txt` в формате:
```
proxy_type://username:password@host:port
```
Пример:
```
socks5://user:pass@proxy.example.com:1080
http://user:pass@proxy.example.com:8080
```
А также без proxy_type, пример:
```
user:pass@proxy.example.com:1080
```
И без авторизации, пример:
```
proxy.example.com:1080
```
## Использование

### Добавление аккаунтов
1. Запустите скрипт добавления аккаунтов:
```bash
python add_accounts.py
```
2. Следуйте инструкциям в консоли для импорта аккаунтов из папки `new_accounts`

### Управление через консоль
Запустите основное приложение:
```bash
python main.py
```

### Управление через API
Для использования API версии:
```bash
python api.py
```

## Основные функции

- Импорт и управление Telegram аккаунтами
- Настройка и использование прокси
- Автоматизация комментариев
- Управление через консоль или API

## Решение проблем

1. Если пишет что не найден подходящий аккаунт для комментариев - необходимо сбросить время последнего использования


**Описание API методов и их использование**

## 1. Получение статистики аккаунтов

**Метод:** `GET http://localhost:5000/statistics`
**Описание:** Возвращает статистику всех аккаунтов.
**Пример запроса:**

```http
GET http://localhost:5000/statistics HTTP/1.1
```

**Пример ответа:**

```json
{
    "total_accounts": 10,
    "active_accounts": 8,
    "inactive_accounts": 2
}
```

## 2. Создание резервной копии базы данных

**Метод:** `POST http://localhost:5000/backup`
**Описание:** Создаёт резервную копию базы данных.
**Пример запроса:**

```http
POST http://localhost:5000/backup HTTP/1.1
```

**Пример ответа:**

```json
{
    "message": "Резервная копия успешно создана"
}
```

## 3. Получение списка аккаунтов

**Метод:** `GET http://localhost:5000/accounts`
**Описание:** Возвращает список всех аккаунтов.
**Пример запроса:**

```http
GET http://localhost:5000/accounts HTTP/1.1
```

**Пример ответа:**

```json
[
    {
        "id": 1,
        "username": "user1",
        "display_name": "User One",
        "gender": "male",
        "is_active": true,
        "last_used": "2025-03-14T12:00:00",
        "error_count": 0
    }
]
```

## 4. Обновление статуса аккаунта

**Метод:** `PUT http://localhost:5000/accounts/{account_id}/status`
**Описание:** Активация или деактивация аккаунта.
**Пример запроса:**

```http
PUT http://localhost:5000/accounts/1/status HTTP/1.1
Content-Type: application/json

{
    "is_active": false
}
```

**Пример ответа:**

```json
{
    "message": "Аккаунт user1 деактивирован"
}
```

## 5. Удаление аккаунта

**Метод:** `DELETE http://localhost:5000/accounts/{account_id}`
**Описание:** Удаляет аккаунт по ID.
**Пример запроса:**

```http
DELETE http://localhost:5000/accounts/1 HTTP/1.1
```

**Пример ответа:**

```json
{
    "message": "Аккаунт user1 удален"
}
```

## 6. Получение информации об аккаунте

**Метод:** `GET http://localhost:5000/accounts/{account_id}/info`
**Описание:** Возвращает информацию об аккаунте.
**Пример запроса:**

```http
GET http://localhost:5000/accounts/1/info HTTP/1.1
```

**Пример ответа:**

```json
{
    "id": 1,
    "username": "user1",
    "display_name": "User One",
    "gender": "male",
    "is_active": true,
    "last_used": "2025-03-14T12:00:00",
    "error_count": 0
}
```

## 7. Получение истории комментариев аккаунта

**Метод:** `GET http://localhost:5000/accounts/{account_id}/comments`
**Описание:** Возвращает историю комментариев аккаунта.
**Пример запроса:**

```http
GET http://localhost:5000/accounts/1/comments HTTP/1.1
```

**Пример ответа:**

```json
[
    {
        "comment_text": "Отличный пост!",
        "timestamp": "2025-03-14T12:00:00",
        "success": true
    }
]
```

## 8. Сброс времени последнего использования аккаунтов

**Метод:** `POST http://localhost:5000/accounts/reset-usage`
**Описание:** Сбрасывает поле `last_used` у всех аккаунтов.
**Пример запроса:**

```http
POST http://localhost:5000/accounts/reset-usage HTTP/1.1
```

**Пример ответа:**

```json
{
    "message": "Время последнего использования сброшено для всех аккаунтов"
}
```

## 9. Запуск процесса комментирования

**Метод:** `POST http://localhost:5000/comments/start`
**Описание:** Запускает процесс комментирования.
**Пример запроса:**

```http
POST http://localhost:5000/comments/start HTTP/1.1
Content-Type: application/json

{
    "post_link": "https://example.com/post1",
    "comments": [
        {"gender": "male", "text": "Отличный пост!"},
        {"gender": "female", "text": "Согласна с автором!"}
    ]
}
```

**Пример ответа:**

```json
{
    "request_id": "20250314_120000",
    "post_link": "https://example.com/post1",
    "total_comments": 2,
    "success_count": 2,
    "error_count": 0,
    "message": "Процесс комментирования успешно завершен"
}
```


