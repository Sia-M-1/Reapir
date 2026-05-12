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
import ticket # Импортируем модуль с логикой заявок

# --- 1. СЛОВАРИ ДЛЯ ХРАНЕНИЯ СОСТОЯНИЯ ---
waiting_for_input = {}
authorized_users = {}

# --- НОВОЕ: Словари для FSM (создание заявки) ---
user_ticket_data = defaultdict(dict)
user_ticket_step = {}

# --- 2. КОНСТАНТЫ ДЛЯ ШАГОВ СОЗДАНИЯ ЗАЯВКИ ---
STEP_CATEGORY = 'select_category'
STEP_LOCATION = 'select_location'
STEP_CLASSROOM = 'input_classroom'
STEP_DESCRIPTION = 'input_description'


def write_msg(user_id, message, keyboard=None):
    """Функция для отправки сообщения пользователю с поддержкой клавиатуры."""
    params = {
        'user_id': user_id,
        'message': message,
        'random_id': 0,
    }
    if keyboard:
        params['keyboard'] = json.dumps(keyboard, ensure_ascii=False)
    vk.messages.send(**params)


def get_keyboard(buttons_list):
    """
    Генерирует клавиатуру VK из списка названий кнопок.
    """
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
    """Обрабатывает действия уже авторизованного пользователя."""
    # Просто приветствуем пользователя и показываем кнопку.
    # Вся сложная логика теперь в другом файле.
    keyboard = ticket.get_keyboard(["Создать заявку"])
    write_msg(user_id, "Вы вошли как пользователь.", keyboard=keyboard)


def handle_authorized_admin(user_id):
    """Обрабатывает действия уже авторизованного администратора."""
    write_msg(user_id, "Вы вошли как администратор. Вам доступны функции управления заявками.")


# --- 4. ФУНКЦИЯ ПРОВЕРКИ ПАРОЛЯ (ИСПРАВЛЕННАЯ) ---
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
                    if authorized_users[user_vk_id] == 'admin':
                        handle_authorized_admin(user_vk_id)
                    else:
                        handle_authorized_user(user_vk_id)
                    continue # Пропускаем остальную логику авторизации

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
                            handle_authorized_user(user_vk_id)
                    else:
                        write_msg(user_vk_id, "❌ Неверный пароль или ключ доступа.")
                    
                    waiting_for_input.pop(user_vk_id)

                else:
                    # --- ЛОГИКА: Если это новое сообщение от неизвестного/неавторизованного ---
                    user_from_db = db.get_user(user_vk_id)
                    
                    if not user_from_db:
                        handle_new_user(user_vk_id)
                    else:
                        role_id = user_from_db[4]
                        
                        if role_id == 2: # Админ
                            handle_known_admin_not_authorized(user_vk_id)
                        else: # Обычный пользователь
                            handle_known_user_not_authorized(user_vk_id)

            # --- НОВАЯ ЛОГИКА: ОБРАБОТКА СОЗДАНИЯ ЗАЯВКИ ---
            # Эта логика выполняется для ВСЕХ событий, включая нажатия кнопок
            if event.type == VkEventType.MESSAGE_NEW and event.to_me:
                user_vk_id = str(event.user_id)
                message_text = event.text

                # --- НАЧАЛО СОЗДАНИЯ ЗАЯВКИ (Кнопка) ---
                if message_text == "Создать заявку":
                    # Проверяем, что это пользователь (не админ) и он авторизован
                    if authorized_users.get(user_vk_id) == 'user':
                        user_ticket_step[user_vk_id] = STEP_CATEGORY

                        try:
                            conn = psycopg2.connect(**db.config())
                            cur = conn.cursor()
                            cur.execute("SELECT category_name FROM category")
                            categories = [row[0] for row in cur.fetchall()]
                            cur.close()
                            conn.close()
                            
                            keyboard = get_keyboard(categories)
                            write_msg(user_vk_id, "Пожалуйста, выберите категорию проблемы:", keyboard=keyboard)
                            
                        except Exception as e:
                            print("Ошибка при получении категорий:", e)
                            write_msg(user_vk_id, "Произошла ошибка при загрузке категорий. Попробуйте позже.")
                    else:
                        write_msg(user_vk_id, "Эта функция доступна только пользователям.")
                
                # --- ПРОЦЕСС СОЗДАНИЯ ЗАЯВКИ (FSM) ---
                elif user_vk_id in user_ticket_step:
                    current_step = user_ticket_step[user_vk_id]
                    
                    # ШАГ 1: Выбор категории (пользователь нажал кнопку с названием категории)
                    if current_step == STEP_CATEGORY:
                        try:
                            conn = psycopg2.connect(**db.config())
                            cur = conn.cursor()
                            cur.execute("SELECT category_id FROM category WHERE category_name = %s", (message_text,))
                            result = cur.fetchone()
                            cur.close()
                            conn.close()
                            
                            if result:
                                user_ticket_data[user_vk_id]['category_name'] = message_text
                                user_ticket_data[user_vk_id]['category_id'] = result[0]
                                user_ticket_step[user_vk_id] = STEP_LOCATION

                                conn = psycopg2.connect(**db.config())
                                cur = conn.cursor()
                                cur.execute("SELECT location_name FROM location")
                                locations = [row[0] for row in cur.fetchall()]
                                cur.close()
                                conn.close()
                                
                                keyboard = get_keyboard(locations)
                                write_msg(user_vk_id, "Пожалуйста, выберите корпус:", keyboard=keyboard)
                            else:
                                write_msg(user_vk_id, "Категория не найдена. Попробуйте снова или начните сначала.")
                                
                        except Exception as e:
                            print("Ошибка при обработке категории:", e)
                            write_msg(user_vk_id, "Произошла ошибка. Попробуйте снова.")
                    
                    # ШАГ 2: Выбор локации (пользователь нажал кнопку с названием корпуса)
                    elif current_step == STEP_LOCATION:
                        try:
                            conn = psycopg2.connect(**db.config())
                            cur = conn.cursor()
                            cur.execute("SELECT location_id FROM location WHERE location_name = %s", (message_text,))
                            result = cur.fetchone()
                            cur.close()
                            conn.close()
                            
                            if result:
                                user_ticket_data[user_vk_id]['location_name'] = message_text
                                user_ticket_data[user_vk_id]['location_id'] = result[0]
                                user_ticket_step[user_vk_id] = STEP_CLASSROOM
                                write_msg(user_vk_id, "Пожалуйста, введите номер кабинета (например, 305 или А-102):")
                            
                        except Exception as e:
                            print("Ошибка при обработке локации:", e)
                    
                    # ШАГ 3: Ввод кабинета (пользователь ввел текст)
                    elif current_step == STEP_CLASSROOM:
                        user_ticket_data[user_vk_id]['classroom'] = message_text.strip()
                        user_ticket_step[user_vk_id] = STEP_DESCRIPTION
                        write_msg(user_vk_id, "Пожалуйста, кратко опишите проблему:")
                    
                    # ШАГ 4: Ввод описания и сохранение в БД
                    elif current_step == STEP_DESCRIPTION:
                        user_ticket_data[user_vk_id]['description'] = message_text.strip()
                        
                        try:
                            conn = psycopg2.connect(**db.config())
                            cur = conn.cursor()
                            
                            data = user_ticket_data[user_vk_id]
                            
                            query = """
                                INSERT INTO tickets 
                                (user_id, category_id, location_id, status_id, creation_date, description, classroom, priority_id) 
                                VALUES (%s, %s, %s, 1, CURRENT_DATE, %s, %s, 1);
                                """
                            
                            values = (
                                user_vk_id,
                                data['category_id'],
                                data['location_id'],
                                data['description'],
                                data['classroom']
                            )
                            
                            cur.execute(query, values)
                            conn.commit()
                            
                            write_msg(user_vk_id, "🎉 Ваша заявка успешно сохранена!")
                            
                        except Exception as e:
                            print("Ошибка при сохранении заявки:", e)
                            write_msg(user_vk_id, "⚠️ Произошла ошибка при сохранении заявки. Пожалуйста, попробуйте создать её заново.")
                        
                        finally:
                            # Очистка данных после завершения процесса
                            user_ticket_data.pop(user_vk_id, None)
                            user_ticket_step.pop(user_vk_id, None)

    except Exception as e:
        print(f"!!! КРИТИЧЕСКАЯ ОШИБКА В ЦИКЛЕ !!!")
        print(f"Текст ошибки: {e}")
        traceback.print_exc()
        print("Бот перезапустит цикл через 15 секунд...")
        time.sleep(15)
