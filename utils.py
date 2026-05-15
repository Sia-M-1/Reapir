import vk_api
import json

# Импортируем объект vk из config.py, чтобы иметь доступ к API
from config import vk

def write_msg(user_id, message, keyboard=None):
    """
    Универсальная функция для отправки сообщения пользователю.
    Принимает ID пользователя, текст и (опционально) клавиатуру.
    """
    params = {'user_id': user_id, 'message': message, 'random_id': 0}
    if keyboard:
        import json
        params['keyboard'] = json.dumps(keyboard, ensure_ascii=False)
    vk.messages.send(**params)