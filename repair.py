import time
import traceback
from collections import defaultdict
import psycopg2
import json
from vk_api.longpoll import VkEventType
from config import longpoll, vk, USER_REGISTRATION_PASSWORD, ADMIN_REGISTRATION_KEY
from utils import write_msg
from hash import hash_password
import db
from db import config
import admin
import ticket

# --- 1. СЛОВАРИ ДЛЯ ХРАНЕНИЯ СОСТОЯНИЯ ---
waiting_for_input = {}          # Ожидает ли пользователь ввода пароля/ключа (password / admin_key)
authorized_users = {}          # Хранит авторизованных: user_id -> 'user' / 'admin'
current_admin_ticket = {}      # Хранит ID заявки, которую админ просматривает в данный момент.
registration_state = {}        # Хранит состояние регистрации для каждого пользователя

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

# --- 3. ФУНКЦИИ-ОБРАБОТЧИКИ СОСТОЯНИЙ (ВОЗВРАЩАЕМ НА МЕСТО) ---
# Эти функции были здесь изначально, я их восстанавливаю.

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

                    # --- ЛОГИКА: ОБРАБОТКА СОЗДАНИЯ ЗАЯВКИ (ДЛЯ ПОЛЬЗОВАТЕЛЯ) ---
                    if authorized_users[user_vk_id] == 'user':
                        # 1. Если это нажатие кнопки "Создать заявку"
                        if message_text == "Создать заявку":
                            new_step = ticket.start_ticket_process(user_vk_id, write_msg)
                            if new_step:
                                user_ticket_step[user_vk_id] = new_step

                        # 2. Если пользователь находится в процессе создания заявки (FSM)
                        elif user_vk_id in user_ticket_step:
                            # Продолжаем создание заявки
                            new_step = ticket.process_ticket_step(
                                user_vk_id,
                                message_text,
                                user_ticket_data,
                                user_ticket_step,
                                write_msg,
                                authorized_users  # добавляем сюда словарь authorised_users
                            )
                            if new_step is None:
                                user_ticket_step.pop(user_vk_id, None)

                        # 3. Если просто сообщение (не кнопка и не создание заявки)
                        else:
                            handle_authorized_user(user_vk_id)
                    
                    # --- ЛОГИКА: ОБРАБОТКА ДЕЙСТВИЙ АДМИНИСТРАТОРА ---
                    elif authorized_users[user_vk_id] == 'admin':
                        # Блок для обработки действий админа.

                        # 1. Кнопка "Посмотреть заявки"
                        if message_text == "Посмотреть заявки":
                            admin.list_active_tickets(user_vk_id)
                        
                        # 2. Кнопки заявок (Заявка 123)
                        elif message_text.startswith("Заявка "):
                            try:
                                ticket_num = int(message_text.split()[1])
                                # Сохраняем ID выбранной заявки в переменную состояния
                                current_admin_ticket[user_vk_id] = ticket_num
                                admin.show_ticket_details(user_vk_id, ticket_num)
                            except:
                                write_msg(user_vk_id, "Некорректный номер заявки.")
                        
                        # 3. Кнопки смены статуса (Принять/Отклонить/Закрыть)
                        elif message_text in ["Принять", "Отклонить", "Закрыть"]:
                            # Получаем ID заявки из переменной состояния для этого админа
                            ticket_id_to_change = current_admin_ticket.get(user_vk_id)
                            
                            if ticket_id_to_change is None:
                                write_msg(user_vk_id, "Сначала выберите заявку.")
                                continue

                            status_map = {
                                "Принять": "В работе",
                                "Отклонить": "Отклонена",
                                "Закрыть": "Выполнена"
                            }
                            
                            admin.change_ticket_status(user_vk_id, ticket_id_to_change, status_map[message_text])
                        
                        elif message_text == "Назад":
                            # Возвращаемся к списку активных заявок
                            admin.list_active_tickets(user_vk_id)
                    
                    continue # Завершаем обработку для авторизованных

                # --- ЛОГИКА: Если пользователь НЕ авторизован ---
                else:
                    # --- 1. ПРОВЕРЯЕМ, ЕСТЬ ЛИ ПОЛЬЗОВАТЕЛЬ В БАЗЕ ДАННЫХ ---
                    user_from_db = db.get_user(user_vk_id)

                    if not user_from_db:
                        # --- СЦЕНАРИЙ 1: НОВЫЙ ПОЛЬЗОВАТЕЛЬ (РЕГИСТРАЦИЯ) ---
                        # Это твоя логика регистрации, которую мы согласовали.
                        # Она работает только если пользователя НЕТ в БД.

                        # 1. Первый контакт: Приветствие и кнопка "Зарегистрироваться"
                        if user_vk_id not in registration_state:
                            keyboard = get_keyboard(["Зарегистрироваться"])
                            write_msg(user_vk_id, "Здравствуйте! Похоже, что вы ещё не зарегистрированы. Давайте пройдём регистрацию!", keyboard=keyboard)
                            registration_state[user_vk_id] = 'awaiting_click'
                        
                        # 2. Пользователь нажал "Зарегистрироваться"
                        elif registration_state[user_vk_id] == 'awaiting_click' and message_text == "Зарегистрироваться":
                            registration_state[user_vk_id] = 'role_choice'
                            keyboard = get_keyboard(["Пользователь", "Администратор"])
                            write_msg(user_vk_id, "Пожалуйста, выберите роль, используя кнопки ниже.", keyboard=keyboard)

                        # 3. Пользователь выбрал роль
                        elif registration_state[user_vk_id] == 'role_choice':
                            if message_text == "Пользователь":
                                registration_state[user_vk_id] = 'password_input'
                                write_msg(user_vk_id, "Отлично, Ваша роль - пользователь! Для продолжения регистрации введите, пожалуйста, пароль.\nПеред регистрацией Вам должны были его сообщить!")
                            elif message_text == "Администратор":
                                registration_state[user_vk_id] = 'password_input'
                                write_msg(user_vk_id, "Отлично, Ваша роль - администратор! Для продолжения регистрации введите, пожалуйста, ключ доступа.\nПеред регистрацией Вам должны были его сообщить!")

                        # 4. Пользователь вводит пароль
                        elif registration_state[user_vk_id] == 'password_input':
                            # Проверяем пароль из config.py
                            if message_text == ADMIN_REGISTRATION_KEY:
                                # Пароль (ключ) верный. Не хешируем, просто сохраняем.
                                # Сразу переходим к вводу ФИО, минуя должность.
                                registration_state[user_vk_id] = {'step': 'fio_input_admin', 'password': message_text}
                                write_msg(user_vk_id, "Ключ доступа принят! Пожалуйста, введите Ваше полное ФИО (в формате Иванов Иван Иванович).")
                            elif message_text == USER_REGISTRATION_PASSWORD:
                                # Пароль верный. Сохраняем его в переменную состояния.
                                registration_state[user_vk_id] = {'step': 'position_choice', 'password': message_text}
                                keyboard = get_keyboard(["Преподаватель", "Иной персонал", "Администрация"])
                                write_msg(user_vk_id, "Поздравляем! Пароль верный! Можно продолжить регистрацию!\nПожалуйста, выберите должность!", keyboard=keyboard)
                            else:
                                # Пароль неверный. Сброс.
                                registration_state.pop(user_vk_id, None)
                                write_msg(user_vk_id, "Похоже Вы ввели неверный пароль! Нажмите любую кнопку, чтобы пройти регистрацию заново.")

                        # 5. Пользователь выбирает должность
                        elif isinstance(registration_state.get(user_vk_id), dict) and registration_state[user_vk_id].get('step') == 'position_choice':
                            valid_positions = ["Преподаватель", "Иной персонал", "Администрация"]
                            if message_text in valid_positions:
                                # Сохраняем должность и переходим к вводу ФИО.
                                reg_data = registration_state[user_vk_id]
                                reg_data['position'] = message_text
                                reg_data['step'] = 'fio_input'
                                write_msg(user_vk_id, "Введите Ваше полное ФИО (в формате Иванов Иван Иванович). Внимательно проверьте написание!\nПосле отправки сообщения данные изменить нельзя!")
                            
                        # 6. Пользователь вводит ФИО (ОБНОВЛЕННЫЙ БЛОК - ФИНАЛЬНЫЙ ШАГ)
                        elif isinstance(registration_state.get(user_vk_id), dict):
                            reg_data = registration_state[user_vk_id]
                            fio = message_text

                            # --- НАЧАЛО БЛОКА СОХРАНЕНИЯ ---
                            try:
                                conn = psycopg2.connect(**config())
                                cur = conn.cursor()

                                if reg_data.get('step') == 'fio_input_admin':
                                    # Поток администратора: сохраняем без должности
                                    cur.execute("""
                                        INSERT INTO users (user_id, full_name, password_hash, role_id)
                                        VALUES (%s, %s, %s, 2)
                                    """, (user_vk_id, fio, hash_password(ADMIN_REGISTRATION_KEY)))
                                    write_msg(user_vk_id, f"🎉 Администратор {fio} успешно зарегистрирован!")

                                elif reg_data.get('step') == 'fio_input':
                                    # Поток пользователя: должность уже выбрана ранее
                                    cur.execute("SELECT post_id FROM position WHERE post_name = %s", (reg_data['position'],))
                                    post_row = cur.fetchone()
                                    post_id = post_row[0] if post_row else None

                                    cur.execute("""
                                        INSERT INTO users (user_id, full_name, post_id, password_hash, role_id)
                                        VALUES (%s, %s, %s, %s, 1)
                                    """, (user_vk_id, fio, post_id, hash_password(USER_REGISTRATION_PASSWORD)))
                                    write_msg(user_vk_id, f"🎉 Пользователь {fio} успешно зарегистрирован!")

                                conn.commit()

                            except Exception as e:
                                print("Ошибка при сохранении в БД:", e)
                                write_msg(user_vk_id, "⚠️ Произошла ошибка при сохранении данных. Попробуйте еще раз.")
                            finally:
                                # --- КОНЕЦ БЛОКА СОХРАНЕНИЯ ---

                                # В ЛЮБОМ СЛУЧАЕ очищаем состояние регистрации,
                                # чтобы при следующем сообщении бот начал с авторизации.
                                registration_state.pop(user_vk_id, None)


                    else:
                        # --- СЦЕНАРИЙ 2: СТАРЫЙ ПОЛЬЗОВАТЕЛЬ (АВТОРИЗАЦИЯ) ---
                        # --- А ВОТ ЗДЕСЬ ТВОЯ ИДЕАЛЬНАЯ ЛОГИКА АВТОРИЗАЦИИ ---
                        # Она осталась нетронутой.
                        
                        # Проверяем, ждет ли пользователь ввода пароля/ключа
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
                            # Пользователь есть в БД, но еще не ввел пароль.
                            # Приветствуем по ФИО и просим пароль.
                            full_name = user_from_db[1]
                            role_id = user_from_db[4]
                            
                            if role_id == 2: # Админ
                                write_msg(user_vk_id, f"Здравствуйте, {full_name}! Для входа введите ключ доступа.")
                                waiting_for_input[user_vk_id] = 'admin_key'
                            else: # Обычный пользователь
                                write_msg(user_vk_id, f"Здравствуйте, {full_name}! Для входа в систему введите ваш пароль.")
                                waiting_for_input[user_vk_id] = 'password'

    except Exception as e:
        print(f"!!! КРИТИЧЕСКАЯ ОШИБКА В ЦИКЛЕ !!!")
        print(f"Текст ошибки: {e}")
        traceback.print_exc()
        print("Бот перезапустит цикл через 15 секунд...")
        time.sleep(15)
