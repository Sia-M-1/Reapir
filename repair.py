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
import admin  # Импортируем модуль админ-панели
import ticket  # Импортируем модуль заявок

# --- 1. СЛОВАРИ ДЛЯ ХРАНЕНИЯ СОСТОЯНИЯ ---
waiting_for_input = {}          # Ожидает ли пользователь ввода пароля/ключа
authorized_users = {}          # Хранит авторизованных: user_id -> 'user'/'admin'

# --- НОВОЕ: Словари для FSM (создание заявки) ---
user_ticket_data = defaultdict(dict)  # Хранит данные заявки для каждого пользователя
user_ticket_step = {}                  # Хранит текущий шаг FSM для пользователя

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
    """
    keyboard = ticket.get_keyboard(["Создать заявку"])
    write_msg(user_id, "Вы вошли как пользователь. У Вас возникла проблема? Заполним заявку?", keyboard=keyboard)


def handle_authorized_admin(user_id):
    """Обрабатывает действия уже авторизованного администратора."""
    admin.show_admin_menu(user_id)


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
                    if authorized_users[user_vk_id] == 'user':
                        # 1. Если это нажатие кнопки "Создать заявку"
                        if message_text == "Создать заявку":
                            new_step = ticket.start_ticket_process(user_vk_id, write_msg)
                            if new_step:
                                user_ticket_step[user_vk_id] = new_step

                        # 2. Если пользователь находится в процессе создания заявки (FSM)
                        elif user_vk_id in user_ticket_step:
                            new_step = ticket.process_ticket_step(
                                user_vk_id,
                                message_text,
                                user_ticket_data,
                                user_ticket_step,
                                write_msg
                            )
                            if new_step is None:  # Процесс завершён
                                user_ticket_step.pop(user_vk_id, None)

                        # 3. Если просто сообщение (не кнопка и не создание заявки)
                        else:
                            handle_authorized_user(user_vk_id)
                    
                    # --- ЛОГИКА: ОБРАБОТКА ДЕЙСТВИЙ АДМИНИСТРАТОРА ---
                    elif authorized_users[user_vk_id] == 'admin':
                        # Блок, который ты просил добавить.
                        # Здесь обрабатываются все действия админа.

                        # 1. Кнопка "Посмотреть заявки"
                        if message_text == "Посмотреть заявки":
                            admin.list_active_tickets(user_vk_id)
                        
                        # 2. Кнопки заявок (Заявка 123)
                        elif message_text.startswith("Заявка "):
                            try:
                                ticket_num = int(message_text.split()[1])
                                admin.show_ticket_details(user_vk_id, ticket_num)
                            except:
                                write_msg(user_vk_id, "Некорректный номер заявки.")
                        
                        # 3. Кнопки смены статуса (Принять/Отклонить/Закрыть)
                        elif message_text in ["Принять", "Отклонить", "Закрыть"]:
                            # Находим последнюю просмотренную заявку для этого админа
                            last_ticket = None
                            for tid in admin.admin_ticket_data.get(user_vk_id, {}):
                                last_ticket = tid
                                break

                            if last_ticket is None:
                                write_msg(user_vk_id, "Сначала выберите заявку.")
                                continue

                            status_map = {
                                "Принять": "В работе",
                                "Отклонить": "Отклонена",
                                "Закрыть": "Выполнена"
                            }
                            
                            admin.change_ticket_status(user_vk_id, last_ticket, status_map[message_text])
                    
                    continue # Завершаем обработку для авторизованных

                # --- ЛОГИКА: Если пользователь НЕ авторизован ---
                else:
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
                                handle_authorized_user(user_vk_id)
                        else:
                            write_msg(user_vk_id, "❌ Неверный пароль или ключ доступа.")
                        
                        waiting_for_input.pop(user_vk_id)

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
