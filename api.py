from flask import Flask, jsonify, request
from models import Account, SessionLocal, Base, engine
from api_comment_manager import APICommentManager
from backup import create_backup
import asyncio
from datetime import datetime
from loguru import logger
import sys
import traceback
import json

# Настройка кодировки для всего приложения
import locale
import codecs
try:
    locale.setlocale(locale.LC_ALL, 'ru_RU.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'Russian_Russia.1251')
    except locale.Error:
        logger.warning("Не удалось установить русскую локаль. Используем системную локаль по умолчанию.")
        locale.setlocale(locale.LC_ALL, '')

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.config['JSONIFY_MIMETYPE'] = 'application/json; charset=utf-8'

def decode_text(text):
    """Функция для декодирования текста из различных кодировок"""
    if isinstance(text, bytes):
        encodings = ['utf-8', 'cp1251', 'latin1', 'utf-16', 'utf-32']
        for encoding in encodings:
            try:
                decoded = text.decode(encoding)
                # Проверяем, что текст действительно читаемый
                if all(ord(c) < 0x10000 for c in decoded):
                    return decoded
            except UnicodeDecodeError:
                continue
        # Если ничего не получилось, используем UTF-8 с заменой нечитаемых символов
        return text.decode('utf-8', errors='replace')
    elif isinstance(text, str):
        return text
    return str(text)

def normalize_text(text):
    """Нормализация текста для хранения"""
    if isinstance(text, bytes):
        text = decode_text(text)
    return text.strip()

# Настройка обработки кодировки для входящих запросов
@app.before_request
def before_request():
    if request.method == 'POST' and request.is_json:
        try:
            # Проверяем наличие данных
            if not request.data:
                return custom_jsonify({"error": "Пустой запрос"}), 400
                
            # Декодируем данные
            decoded_data = decode_text(request.get_data())
            
            # Парсим JSON
            try:
                data = json.loads(decoded_data)
                # Нормализуем текст комментариев
                if 'comments' in data:
                    for comment in data['comments']:
                        if 'text' in comment:
                            comment['text'] = normalize_text(comment['text'])
                request._cached_json = (data, True)
            except json.JSONDecodeError:
                return custom_jsonify({"error": "Неверный формат JSON"}), 400
                
        except Exception as e:
            return custom_jsonify({"error": f"Ошибка обработки запроса: {str(e)}"}), 400

# Настройка ответов JSON
def custom_jsonify(*args, **kwargs):
    """Кастомная версия jsonify с принудительной установкой кодировки"""
    response = jsonify(*args, **kwargs)
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

# Настройка логирования
logger.remove()  # Удаляем стандартный обработчик
logger.add(
    "logs/api.log",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    level="DEBUG",
    rotation="1 day",
    compression="zip",
    backtrace=True,
    diagnose=True
)
logger.add(sys.stderr, level="INFO")  # Добавляем вывод в консоль

@app.route('/statistics', methods=['GET'])
def get_statistics():
    """Получение статистики всех аккаунтов"""
    session = SessionLocal()
    try:
        stats = Account.get_statistics(session)
        return jsonify(stats), 200
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {str(e)}")
        return jsonify({"error": "Ошибка при получении статистики"}), 500
    finally:
        session.close()

@app.route('/backup', methods=['POST'])
def create_backup_endpoint():
    """Создание резервной копии базы данных"""
    try:
        if create_backup():
            return jsonify({"message": "Резервная копия успешно создана"}), 200
        return jsonify({"error": "Ошибка при создании резервной копии"}), 500
    except Exception as e:
        logger.error(f"Ошибка при создании резервной копии: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/accounts', methods=['GET'])
def get_accounts():
    """Получение списка всех аккаунтов"""
    session = SessionLocal()
    try:
        accounts = session.query(Account).all()
        accounts_list = []
        for acc in accounts:
            accounts_list.append({
                'id': acc.id,
                'username': acc.username,
                'display_name': acc.display_name,
                'gender': acc.gender.value,
                'is_active': acc.is_active,
                'last_used': acc.last_used.isoformat() if acc.last_used else None,
                'error_count': acc.error_count
            })
        return jsonify(accounts_list), 200
    except Exception as e:
        logger.error(f"Ошибка при получении списка аккаунтов: {str(e)}")
        return jsonify({"error": "Ошибка при получении списка аккаунтов"}), 500
    finally:
        session.close()

@app.route('/accounts/<int:account_id>/status', methods=['PUT'])
def update_account_status(account_id):
    """Активация/деактивация аккаунта"""
    data = request.get_json()
    if 'is_active' not in data:
        return jsonify({"error": "Не указан параметр is_active"}), 400

    session = SessionLocal()
    try:
        account = session.query(Account).filter(Account.id == account_id).first()
        if not account:
            return jsonify({"error": "Аккаунт не найден"}), 404

        account.is_active = data['is_active']
        if data['is_active']:
            account.error_count = 0
        session.commit()
        
        status = "активирован" if data['is_active'] else "деактивирован"
        return jsonify({"message": f"Аккаунт {account.username} {status}"}), 200
    except Exception as e:
        logger.error(f"Ошибка при обновлении статуса аккаунта: {str(e)}")
        return jsonify({"error": "Ошибка при обновлении статуса аккаунта"}), 500
    finally:
        session.close()

@app.route('/accounts/<int:account_id>', methods=['DELETE'])
def delete_account(account_id):
    """Удаление аккаунта"""
    session = SessionLocal()
    try:
        account = session.query(Account).filter(Account.id == account_id).first()
        if not account:
            return jsonify({"error": "Аккаунт не найден"}), 404

        session.delete(account)
        session.commit()
        return jsonify({"message": f"Аккаунт {account.username} удален"}), 200
    except Exception as e:
        logger.error(f"Ошибка при удалении аккаунта: {str(e)}")
        return jsonify({"error": "Ошибка при удалении аккаунта"}), 500
    finally:
        session.close()

@app.route('/accounts/<int:account_id>/info', methods=['GET'])
def get_account_info(account_id):
    """Получение информации об аккаунте"""
    session = SessionLocal()
    try:
        account = session.query(Account).filter(Account.id == account_id).first()
        if not account:
            return jsonify({"error": "Аккаунт не найден"}), 404

        return jsonify({
            'id': account.id,
            'username': account.username,
            'display_name': account.display_name,
            'gender': account.gender.value,
            'is_active': account.is_active,
            'last_used': account.last_used.isoformat() if account.last_used else None,
            'error_count': account.error_count
        }), 200
    except Exception as e:
        logger.error(f"Ошибка при получении информации об аккаунте: {str(e)}")
        return jsonify({"error": "Ошибка при получении информации об аккаунте"}), 500
    finally:
        session.close()

@app.route('/accounts/<int:account_id>/comments', methods=['GET'])
def get_account_comments(account_id):
    """Получение истории комментариев аккаунта"""
    session = SessionLocal()
    try:
        account = session.query(Account).filter(Account.id == account_id).first()
        if not account:
            return jsonify({"error": "Аккаунт не найден"}), 404

        comments = []
        for comment in account.comment_history:
            comments.append({
                'post_link': comment.post_link,
                'comment_text': comment.comment_text,
                'timestamp': comment.timestamp.isoformat(),
                'success': comment.success
            })

        return jsonify(comments), 200
    except Exception as e:
        logger.error(f"Ошибка при получении истории комментариев: {str(e)}")
        return jsonify({"error": "Ошибка при получении истории комментариев"}), 500
    finally:
        session.close()

@app.route('/accounts/reset-usage', methods=['POST'])
def reset_last_used():
    """Сброс времени последнего использования для всех аккаунтов"""
    session = SessionLocal()
    try:
        accounts = session.query(Account).all()
        for account in accounts:
            account.last_used = None
        session.commit()
        return jsonify({"message": "Время последнего использования сброшено для всех аккаунтов"}), 200
    except Exception as e:
        logger.error(f"Ошибка при сбросе времени использования: {str(e)}")
        return jsonify({"error": "Ошибка при сбросе времени использования"}), 500
    finally:
        session.close()

@app.route('/comments/start', methods=['POST'])
def start_commenting():
    """Запуск процесса комментирования"""
    request_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    logger.info(f"[Request ID: {request_id}] Получен запрос на комментирование")
    
    try:
        # Получаем данные из запроса
        try:
            if not request.is_json:
                raise ValueError("Неверный Content-Type. Ожидается application/json")
                
            data = request.json
            if data is None:
                raise ValueError("Пустое тело запроса или неверный формат JSON")
                
        except Exception as e:
            logger.error(f"[Request ID: {request_id}] Ошибка при разборе JSON: {str(e)}")
            return custom_jsonify({
                "error": f"Ошибка при разборе JSON: {str(e)}",
                "request_id": request_id
            }), 400

        # Логируем входные данные
        logger.info(f"[Request ID: {request_id}] Post link: {data.get('post_link')}")
        logger.info(f"[Request ID: {request_id}] Number of comments: {len(data.get('comments', []))}")
        
        # Валидация данных
        validation_errors = []
        
        if 'post_link' not in data:
            validation_errors.append("Не указан параметр post_link")
        if 'comments' not in data:
            validation_errors.append("Не указан параметр comments")
        elif not isinstance(data['comments'], list):
            validation_errors.append("Параметр comments должен быть массивом")
        elif not data['comments']:
            validation_errors.append("Массив comments не может быть пустым")
        
        # Проверка формата комментариев
        for i, comment in enumerate(data.get('comments', [])):
            if not isinstance(comment, dict):
                validation_errors.append(f"Комментарий #{i+1} должен быть объектом")
                continue
            if 'gender' not in comment:
                validation_errors.append(f"В комментарии #{i+1} отсутствует поле gender")
            elif comment['gender'] not in ['male', 'female']:
                validation_errors.append(f"В комментарии #{i+1} поле gender должно быть 'male' или 'female'")
            if 'text' not in comment:
                validation_errors.append(f"В комментарии #{i+1} отсутствует поле text")
            elif not isinstance(comment['text'], str) or not comment['text'].strip():
                validation_errors.append(f"В комментарии #{i+1} поле text должно быть непустой строкой")
            else:
                try:
                    # Нормализация текста комментария
                    text = decode_text(comment['text'].strip())
                    comment['text'] = text
                    logger.info(f"[Request ID: {request_id}] Текст комментария #{i+1}: {text}")
                except Exception as e:
                    validation_errors.append(f"В комментарии #{i+1} ошибка обработки текста: {str(e)}")
        
        if validation_errors:
            logger.error(f"[Request ID: {request_id}] Ошибки валидации: {', '.join(validation_errors)}")
            return custom_jsonify({
                "error": "Ошибки валидации",
                "details": validation_errors,
                "request_id": request_id
            }), 400
            
        if not isinstance(data['post_link'], str) or not data['post_link'].strip():
            logger.error(f"[Request ID: {request_id}] Некорректная ссылка на пост")
            return custom_jsonify({
                "error": "Некорректная ссылка на пост",
                "request_id": request_id
            }), 400

        manager = APICommentManager()
        
        try:
            # Создаем и запускаем событийный цикл для асинхронной функции
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            logger.info(f"[Request ID: {request_id}] Запуск процесса комментирования")
            result = loop.run_until_complete(manager.process_comments_with_details(data['post_link'].strip(), data['comments']))
            
            # Формируем ответ
            response = {
                "request_id": request_id,
                "post_link": data['post_link'],
                "total_comments": len(data['comments']),
                "success_count": result['success_count'],
                "error_count": result['error_count'],
                "account_results": result['account_results']
            }
            
            if result['errors']:
                logger.warning(f"[Request ID: {request_id}] Процесс комментирования завершен с ошибками: {result['errors']}")
                response["message"] = "Процесс комментирования завершен с ошибками"
                response["errors"] = result['errors']
            else:
                logger.success(f"[Request ID: {request_id}] Процесс комментирования успешно завершен")
                response["message"] = "Процесс комментирования успешно завершен"
                
            return custom_jsonify(response), 200
            
        except Exception as e:
            error_msg = f"Ошибка при комментировании: {str(e)}"
            logger.error(f"[Request ID: {request_id}] {error_msg}\n{traceback.format_exc()}")
            return custom_jsonify({
                "error": error_msg,
                "request_id": request_id,
                "details": traceback.format_exc()
            }), 500
        finally:
            try:
                logger.info(f"[Request ID: {request_id}] Закрытие менеджера комментариев")
                manager.close()
                logger.info(f"[Request ID: {request_id}] Ресурсы освобождены")
            except Exception as e:
                logger.error(f"[Request ID: {request_id}] Ошибка при закрытии менеджера: {str(e)}")
                
    except Exception as e:
        error_msg = f"Ошибка при обработке запроса: {str(e)}"
        logger.error(f"[Request ID: {request_id}] {error_msg}\n{traceback.format_exc()}")
        return custom_jsonify({
            "error": error_msg,
            "request_id": request_id,
            "details": traceback.format_exc()
        }), 500

if __name__ == '__main__':
    # Убедимся, что база данных существует
    Base.metadata.create_all(engine)
    # Запускаем сервер
    app.run(debug=True) 