import requests
import json

def send_test_request():
    # URL API
    url = "http://localhost:5000/comments/start"
    
    # Тестовые данные
    data = {
        "post_link": "https://t.me/pravdadirty/68875",
        "comments": [
            {
                "gender": "male",
                "text": "Отличный контент! Спасибо!"
            },
            {
                "gender": "female",
                "text": "Мне очень понравилось ❤"
            }
        ]
    }
    
    # Заголовки запроса
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "Accept-Charset": "utf-8"
    }
    
    try:
        print("Отправка запроса...")
        
        # Отправляем запрос
        response = requests.post(
            url,
            json=data,  # автоматически сериализует в JSON с правильной кодировкой
            headers=headers
        )
        
        # Проверяем статус ответа
        response.raise_for_status()
        
        # Получаем ответ
        print("\nОтвет сервера:")
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
        
    except requests.exceptions.RequestException as e:
        print(f"\nОшибка при отправке запроса: {str(e)}")
        if hasattr(e.response, 'text'):
            print("\nОтвет сервера:")
            try:
                error_json = e.response.json()
                print(json.dumps(error_json, ensure_ascii=False, indent=2))
            except:
                print(e.response.text)

if __name__ == "__main__":
    send_test_request() 