import time
from config import longpoll, vk
from vk_api.longpoll import VkEventType
import db

# --- 1. СЛОВАРИ ДЛЯ ХРАНЕНИЯ СОСТОЯНИЯ ---
# Словарь для хранения ожидаемого действия пользователя:
# Ключ: user_id, Значение: что бот ждёт от пользователя ('password', 'admin_key')
waiting_for_input = {}

# Словарь для хранения авторизованных пользователей:
# Ключ: user_id, Значение: роль пользователя ('user' или 'admin')
authorized_users = {}


def write_msg(user_id, message):
    """Функция для отправки сообщения пользователю."""
    vk.messages.send(user_id=user_id, message=message, random_id=0)


# --- 2. ФУНКЦИИ-ОБРАБОТЧИКИ СОСТОЯНИЙ ---

def handle_new_user(user_id):
    """Обрабатывает пользователя, которого нет в базе."""
    write_msg(user_id, "Здравствуйте! Вы ещё не зарегистрированы. Пройдите регистрацию (эта функция будет реализована позже).")

def handle_known_user_not_authorized(user_id):
    """Обрабатывает известного пользователя, который ещё не ввёл пароль."""
    user_data = db.get_user(user_id)
    if user_data:
        full_name = user_data[1]  # Полное имя пользователя
        write_msg(user_id, f"Здравствуйте, {full_name}! Для входа в систему введите ваш пароль.")
    else:
        write_msg(user_id, "Для входа в систему введите ваш пароль.")
    waiting_for_input[user_id] = 'password'

def handle_known_admin_not_authorized(user_id):
    """Обрабатывает известного администратора, который ещё не ввёл ключ."""
    user_data = db.get_user(user_id)
    if user_data:
        full_name = user_data[1]
        write_msg(user_id, f"Здравствуйте, {full_name}! Для входа введите ключ доступа.")
    else:
        write_msg(user_id, "Для входа введите ключ доступа.")
    waiting_for_input[user_id] = 'admin_key'


def handle_authorized_user(user_id):
    """Обрабатывает действия уже авторизованного пользователя."""
    write_msg(user_id, "Вы вошли как пользователь. Вы можете создать заявку.")
    # Здесь будет логика создания заявки (кнопки и т.д.)

def handle_authorized_admin(user_id):
    """Обрабатывает действия уже авторизованного администратора."""
    write_msg(user_id, "Вы вошли как администратор. Вам доступны функции управления заявками.")
    # Здесь будет логика для админа (кнопки "Просмотреть заявки" и т.д.)


# --- 3. ФУНКЦИЯ ПРОВЕРКИ ПАРОЛЯ (та же, что и раньше) ---
import argon2

def verify_password(plain_password, hashed_password_from_db):
    """
    Сверяет введенный пароль с хэшем из базы данных.
    Возвращает True, если пароль верный.
    """
    try:
        ph = argon2.PasswordHasher()
        # hashed_password_from_db приходит как объект памяти (memoryview) или bytes.
        # Приводим его к строке (декодируем байты).
        # .tobytes() нужен для compatibility с memoryview, который может вернуть psycopg2.
        hash_str = hashed_password_from_db.tobytes().decode('utf-8')
        
        # Теперь передаем строку в верификатор. Он сам разберет формат.
        ph.verify(hash_str, plain_password)
        return True

    except (argon2.exceptions.VerifyMismatchError, UnicodeDecodeError):
        # VerifyMismatchError — пароль не совпал.
        # UnicodeDecodeError — если в базе мусор или не BYTEA.
        return False
    except Exception as e:
        print(f"Неизвестная ошибка верификации: {e}")
        return False


# --- 4. ГЛАВНЫЙ ЦИКЛ БОТА ---
print("Бот запущен и готов к работе!")
db.init_db()  # Проверяем подключение к БД при запуске

while True:
    try:
        for event in longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW and event.to_me:
                user_vk_id = str(event.user_id)
                message_text = event.text

                # --- ЛОГИКА: Проверяем, авторизован ли пользователь ---
                if user_vk_id in authorized_users:
                    # Пользователь уже авторизован, направляем в нужный обработчик
                    if authorized_users[user_vk_id] == 'admin':
                        handle_authorized_admin(user_vk_id)
                    else:
                        handle_authorized_user(user_vk_id)
                    continue # Пропускаем остальную логику

                # --- ЛОГИКА: Проверяем, ждет ли бот ввода пароля/ключа ---
                if user_vk_id in waiting_for_input:
                    # Бот ждет от этого пользователя ввод
                    expected_action = waiting_for_input[user_vk_id]
                    user_data = db.get_user(user_vk_id)

                    if user_data is None:
                        # Пользователь удален из БД во время ожидания
                        write_msg(user_vk_id, "Ошибка: данные пользователя не найдены.")
                        waiting_for_input.pop(user_vk_id)
                        continue

                    # Получаем хэш пароля из данных пользователя (4-й столбец)
                    stored_hash = user_data[3]
                    role_id = user_data[4]
                    
                    is_correct = verify_password(message_text, stored_hash)

                    if is_correct:
                        write_msg(user_vk_id, "✅ Авторизация прошла успешно!")
                        # Сохраняем статус авторизации
                        if role_id == 2:
                            authorized_users[user_vk_id] = 'admin'
                            handle_authorized_admin(user_vk_id)
                        else:
                            authorized_users[user_vk_id] = 'user'
                            handle_authorized_user(user_vk_id)
                    else:
                        write_msg(user_vk_id, "❌ Неверный пароль или ключ доступа.")
                    
                    # Очищаем ожидание ввода в любом случае
                    waiting_for_input.pop(user_vk_id)

                else:
                    # --- ЛОГИКА: Если это новое сообщение от неизвестного/неавторизованного ---
                    user_from_db = db.get_user(user_vk_id)
                    
                    if not user_from_db:
                        handle_new_user(user_vk_id)
                    else:
                        # Пользователь есть в базе, но не авторизован сейчас
                        role_id = user_from_db[4]
                        
                        if role_id == 2: # Админ
                            handle_known_admin_not_authorized(user_vk_id)
                        else: # Обычный пользователь (и другие роли)
                            handle_known_user_not_authorized(user_vk_id)

    except Exception as e:
        print(f"Произошла критическая ошибка: {e}. Бот перезапустится через 15 секунд...")
        time.sleep(15)