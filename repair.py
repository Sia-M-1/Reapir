# repair.py

import time
import traceback
from collections import defaultdict
import psycopg2
import json
from vk_api.longpoll import VkEventType
from config import longpoll, vk
from utils import write_msg
import db
import registration
import admin
import ticket  # Импортируем модуль с логикой заявок

# --- 1. СЛОВАРИ ДЛЯ ХРАНЕНИЯ СОСТОЯНИЯ ---
waiting_for_input = {}          # Ожидает ли пользователь ввода пароля/ключа
authorized_users = {}          # Хранит авторизованных пользователей: user_id -> 'user'/'admin'

# --- НОВОЕ: Словари для FSM (создание заявки) ---
user_ticket_data = defaultdict(dict)  # Хранит данные заявки для каждого пользователя
user_ticket_step = {}                  # Хранит текущий шаг FSM для пользователя

# --- 2. КОНСТАНТЫ ДЛЯ ШАГОВ СОЗДАНИЯ ЗАЯВКИ ---
# (теперь не используются напрямую, только в ticket.py)


def get_keyboard(buttons_list):
    """Генерирует клавиатуру VK из списка названий кнопок."""
    keyboard = {
        "one_time": False,
        "buttons": []
    }
    for button_text in buttons_list:
        keyboard["buttons"].append([
            {
                "action": {
                    "type": "text",
                    "label": button_text,
                    "payload": {}
                },
                "color": "primary"
            }
        ])
    return keyboard


# --- 3. ФУНКЦИИ-ОБРАБОТЧИКИ СОСТОЯНИЙ ---

def handle_new_user(user_id):
    """Обрабатывает пользователя, которого нет в базе."""
    write_msg(user_id, "Здравствуйте! Вы ещё не зарегистрированы. Пройдите регистрацию (эта функция будет реализована позже).")

def handle_known_user_not_authorized(user_id):
    """Обрабатывает известного пользователя, который ещё не ввёл пароль."""
    user_data = db.get_user(user_id)
    if user_data:
        full_name = user_data[1]
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
    """
    Обрабатывает действия уже авторизованного пользователя.
    Это исправленная версия.
    """
    # Бот приветствует пользователя и предлагает начать создание заявки.
    # Кнопка "Создать заявку" появляется ТОЛЬКО здесь.
    keyboard = ticket.get_keyboard(["Создать заявку"])
    write_msg(user_id, "Вы вошли как пользователь. У Вас возникла проблема? Заполним заявку?", keyboard=keyboard)


def handle_authorized_admin(user_id):
    """Обрабатывает действия уже авторизованного администратора."""
    write_msg(user_id, "Вы вошли как администратор. Вам доступны функции управления заявками.")


# --- 4. ФУНКЦИЯ ПРОВЕРКИ ПАРОЛЯ ---
import argon2

def verify_password(plain_password, hashed_password_from_db):
    """
    Сверяет введенный пароль с хэшем из базы данных.
    Возвращает True, если пароль верный.
    """
    try:
        ph = argon2.PasswordHasher()
        hash_str = hashed_password_from_db.tobytes().decode('utf-8')
        ph.verify(hash_str, plain_password)
        return True
    except (argon2.exceptions.VerifyMismatchError, UnicodeDecodeError):
        return False
    except Exception as e:
        print(f"Неизвестная ошибка верификации: {e}")
        return False


# --- 5. ГЛАВНЫЙ ЦИКЛ БОТА ---
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
                    # Пользователь уже авторизован

                    # --- НОВАЯ ЛОГИКА: ОБРАБОТКА СОЗДАНИЯ ЗАЯВКИ ---
                    # Эта логика выполняется для ВСЕХ событий от авторизованных пользователей.

                    # 1. Если это нажатие кнопки "Создать заявку"
                    if message_text == "Создать заявку" and authorized_users[user_vk_id] == 'user':
                        # Начало создания заявки через модуль ticket.py
                        new_step = ticket.start_ticket_process(user_vk_id, write_msg)
                        if new_step:
                            user_ticket_step[user_vk_id] = new_step

                    # 2. Если пользователь находится в процессе создания заявки (FSM)
                    elif user_vk_id in user_ticket_step:
                        # Передаём управление в ticket.py для обработки шага
                        new_step = ticket.process_ticket_step(
                            user_vk_id,
                            message_text,
                            user_ticket_data,
                            user_ticket_step,
                            write_msg
                        )
                        if new_step is None:  # Процесс завершён (заявка создана или ошибка)
                            user_ticket_step.pop(user_vk_id, None)

                    # 3. Если просто сообщение (не кнопка и не создание заявки)
                    else:
                        # Просто выводим приветствие и клавиатуру заново,
                        # чтобы кнопка всегда была под рукой.
                        handle_authorized_user(user_vk_id)
                    
                    continue # Завершаем обработку для авторизованных

                # --- ЛОГИКА: Если пользователь НЕ авторизован ---
                else:
                    # --- ЛОГИКА: Проверяем, ждет ли бот ввода пароля/ключа ---
                    if user_vk_id in waiting_for_input:
                        expected_action = waiting_for_input[user_vk_id]
                        user_data = db.get_user(user_vk_id)

                        if user_data is None:
                            write_msg(user_vk_id, "Ошибка: данные пользователя не найдены.")
                            waiting_for_input.pop(user_vk_id)
                            continue

                        stored_hash = user_data[3]
                        role_id = user_data[4]
                        
                        is_correct = verify_password(message_text, stored_hash)

                        if is_correct:
                            write_msg(user_vk_id, "✅ Авторизация прошла успешно!")
                            if role_id == 2:
                                authorized_users[user_vk_id] = 'admin'
                                handle_authorized_admin(user_vk_id)
                            else:
                                authorized_users[user_vk_id] = 'user'
                                # После успешной авторизации вызываем исправленную функцию
                                handle_authorized_user(user_vk_id)
                        else:
                            write_msg(user_vk_id, "❌ Неверный пароль или ключ доступа.")
                        
                        waiting_for_input.pop(user_vk_id)

                    # --- ЛОГИКА: Если это новое сообщение от неизвестного/неавторизованного ---
                    else:
                        user_from_db = db.get_user(user_vk_id)
                        
                        if not user_from_db:
                            handle_new_user(user_vk_id)
                        else:
                            role_id = user_from_db[4]
                            
                            if role_id == 2: # Админ
                                handle_known_admin_not_authorized(user_vk_id)
                            else: # Обычный пользователь
                                handle_known_user_not_authorized(user_vk_id)

    except Exception as e:
        print(f"!!! КРИТИЧЕСКАЯ ОШИБКА В ЦИКЛЕ !!!")
        print(f"Текст ошибки: {e}")
        traceback.print_exc()
        print("Бот перезапустит цикл через 15 секунд...")
        time.sleep(15)
