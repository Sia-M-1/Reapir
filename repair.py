import sys
sys.stdout.reconfigure(encoding='utf-8') 
import time
import traceback
from collections import defaultdict
import psycopg2
from vk_api.longpoll import VkEventType
from config import longpoll, vk, USER_REGISTRATION_PASSWORD, ADMIN_REGISTRATION_KEY
from utils import write_msg
from hash import hash_password
import db
from db import config
import admin
import ticket

# Словари для хранения состояния
waiting_for_input = {}          # Ожидает ли пользователь ввода пароля/ключа (password / admin_key)
authorized_users = {}          # Хранит авторизованных: user_id -> 'user' / 'admin'
current_admin_ticket = {}      # Хранит ID заявки, которую админ просматривает в данный момент.
registration_state = {}        # Хранит состояние регистрации для каждого пользователя

# Словари для создание заявки
user_ticket_data = defaultdict(dict)  # Хранит данные заявки для каждого пользователя
user_ticket_step = {}                  # Хранит текущий шаг создания заявки для пользователя

def get_keyboard(buttons_list):
    """Генерирует клавиатуру VK из списка названий кнопок"""
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

def handle_authorized_user(user_id):
    """Обрабатывает действия уже авторизованного пользователя"""
    keyboard = ticket.get_keyboard(["Создать заявку"])
    write_msg(user_id, "Поздравляем! Вы вошли как пользователь. У Вас возникла проблема? Хотите заполнить заявку?", keyboard=keyboard)


def handle_authorized_admin(user_id):
    """Обрабатывает действия уже авторизованного администратора"""
    admin.show_admin_menu(user_id)

# Функция проверки пароля
import argon2

def verify_password(plain_password, hashed_password_from_db):
    """Сверяет введенный пароль с хэшем из базы данных. Возвращает True, если пароль верный"""
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

# ГЛАВНЫЙ ЦИКЛ БОТА
print("Бот запущен и готов к работе!")
db.init_db()  # Подключение к БД при запуске

while True:
    try:
        for event in longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW and event.to_me:
                user_vk_id = str(event.user_id)
                message_text = event.text

                # Авторизован ли пользователь
                if user_vk_id in authorized_users:
                    # Пользователь уже авторизован
                    # Обработка создания заявки
                    if authorized_users[user_vk_id] == 'user':
                        # Если нажатие кнопки "Создать заявку"
                        if message_text == "Создать заявку":
                            new_step = ticket.start_ticket_process(user_vk_id, write_msg)
                            if new_step:
                                user_ticket_step[user_vk_id] = new_step

                        # Если пользователь находится в процессе создания заявки 
                        elif user_vk_id in user_ticket_step:
                            # Создание заявки
                            new_step = ticket.process_ticket_step(
                                user_vk_id,
                                message_text,
                                user_ticket_data,
                                user_ticket_step,
                                write_msg,
                                authorized_users
                            )
                            if new_step is None:
                                user_ticket_step.pop(user_vk_id, None)

                        # Если просто сообщение (не кнопка и не создание заявки)
                        else:
                            handle_authorized_user(user_vk_id)
                    
                    # Обработка дейтвий администратора
                    elif authorized_users[user_vk_id] == 'admin':
                        # Блок для обработки действий админа
                        # Кнопка "Посмотреть заявки"
                        if message_text == "Посмотреть заявки":
                            admin.list_active_tickets(user_vk_id)
                        
                        # Кнопки заявок
                        elif message_text.startswith("Заявка "):
                            try:
                                ticket_num = int(message_text.split()[1])
                                # Сохранение ID выбранной заявки в переменную состояния
                                current_admin_ticket[user_vk_id] = ticket_num
                                admin.show_ticket_details(user_vk_id, ticket_num)
                            except:
                                write_msg(user_vk_id, "Некорректный номер заявки.")
                        
                        # Кнопки смены статуса 
                        elif message_text in ["Принять", "Отклонить", "Закрыть"]:
                            # Получаем ID заявки из переменной состояния для этого админа
                            ticket_id_to_change = current_admin_ticket.get(user_vk_id)
                            
                            if ticket_id_to_change is None:
                                write_msg(user_vk_id, "Сначала выберите заявку")
                                continue

                            status_map = {
                                "Принять": "В работе",
                                "Отклонить": "Отклонена",
                                "Закрыть": "Выполнена"
                            }
                            
                            admin.change_ticket_status(user_vk_id, ticket_id_to_change, status_map[message_text])
                        
                        elif message_text == "Назад":
                            # Возвращение к списку активных заявок
                            admin.list_active_tickets(user_vk_id)
                    
                    continue

                # Если пользователь не авторизован 
                else:
                    # Проверка, есть ли пользователь в бд
                    user_from_db = db.get_user(user_vk_id)

                    if not user_from_db:
                        # Сценарий 1: регистрация
                        # Приветствие и кнопка "Зарегистрироваться"
                        if user_vk_id not in registration_state:
                            keyboard = get_keyboard(["Зарегистрироваться"])
                            write_msg(user_vk_id, "Здравствуйте! Похоже, что вы ещё не зарегистрированы. Давайте пройдём регистрацию!", keyboard=keyboard)
                            registration_state[user_vk_id] = 'awaiting_click'
                        
                        # Пользователь нажал "Зарегистрироваться"
                        elif registration_state[user_vk_id] == 'awaiting_click' and message_text == "Зарегистрироваться":
                            registration_state[user_vk_id] = 'role_choice'
                            keyboard = get_keyboard(["Пользователь", "Администратор"])
                            write_msg(user_vk_id, "Пожалуйста, выберите роль, используя кнопки ниже", keyboard=keyboard)

                        # Пользователь выбрал роль
                        elif registration_state[user_vk_id] == 'role_choice':
                            if message_text == "Пользователь":
                                registration_state[user_vk_id] = 'password_input'
                                write_msg(user_vk_id, "Отлично, Ваша роль - пользователь! После регистрации и авторизации Вам будет доступна функция создания заявки на получение тех.поддержки! Для продолжения регистрации введите, пожалуйста, пароль.\nПеред регистрацией Вам должны были его сообщить!")
                            elif message_text == "Администратор":
                                registration_state[user_vk_id] = 'password_input'
                                write_msg(user_vk_id, "Отлично, Ваша роль - администратор! После регистрации и авторизации Вам будет доступна функция просмотра и управления заявками! Для продолжения регистрации введите, пожалуйста, ключ доступа.\nПеред регистрацией Вам должны были его сообщить!")

                        # Пользователь вводит пароль
                        elif registration_state[user_vk_id] == 'password_input':
                            # Проверка пароля из config.py
                            if message_text == ADMIN_REGISTRATION_KEY:
                                # Пароль (ключ) верный
                                # Для администратора сразу к вводу ФИО, минуя должность
                                registration_state[user_vk_id] = {'step': 'fio_input_admin', 'password': message_text}
                                write_msg(user_vk_id, "Ключ доступа принят! Пожалуйста, введите Ваше полное ФИО (в формате Иванов Иван Иванович). Внимательно проверьте правильность написания, после регистрации их нельзя будет изменить!")
                            elif message_text == USER_REGISTRATION_PASSWORD:
                                # Пароль верный - сохранение (для пользователя)
                                registration_state[user_vk_id] = {'step': 'position_choice', 'password': message_text}
                                keyboard = get_keyboard(["Преподаватель", "Иной персонал", "Администрация"])
                                write_msg(user_vk_id, "Поздравляем! Пароль верный! Можно продолжить регистрацию!\nПожалуйста, выберите должность!", keyboard=keyboard)
                            else:
                                # Пароль неверный. Сброс.
                                registration_state.pop(user_vk_id, None)
                                write_msg(user_vk_id, "Похоже Вы ввели неверный пароль! Нажмите любую кнопку, чтобы пройти регистрацию заново")

                        # Пользователь выбирает должность
                        elif isinstance(registration_state.get(user_vk_id), dict) and registration_state[user_vk_id].get('step') == 'position_choice':
                            valid_positions = ["Преподаватель", "Иной персонал", "Администрация"]
                            if message_text in valid_positions:
                                # Сохранение должности и переход к вводу ФИО
                                reg_data = registration_state[user_vk_id]
                                reg_data['position'] = message_text
                                reg_data['step'] = 'fio_input'
                                write_msg(user_vk_id, "Введите Ваше полное ФИО (в формате Иванов Иван Иванович). Внимательно проверьте написание!\nПосле отправки сообщения данные изменить нельзя!")
                            
                        # Пользователь вводит ФИО
                        elif isinstance(registration_state.get(user_vk_id), dict):
                            reg_data = registration_state[user_vk_id]
                            fio = message_text
                            # Начало блока сохранения
                            try:
                                conn = psycopg2.connect(**config())
                                cur = conn.cursor()

                                if reg_data.get('step') == 'fio_input_admin':
                                    # Поток администратора: сохранение без должности
                                    cur.execute("""
                                        INSERT INTO users (user_id, full_name, password_hash, role_id)
                                        VALUES (%s, %s, %s, 2)
                                    """, (user_vk_id, fio, hash_password(ADMIN_REGISTRATION_KEY)))
                                    write_msg(user_vk_id, f"🎉 Администратор {fio} успешно зарегистрирован! Отправьте любое сообщение, чтобы пройти авторизацию!")

                                elif reg_data.get('step') == 'fio_input':
                                    # Поток пользователя: должность уже выбрана ранее
                                    cur.execute("SELECT post_id FROM position WHERE post_name = %s", (reg_data['position'],))
                                    post_row = cur.fetchone()
                                    post_id = post_row[0] if post_row else None
                                    cur.execute("""
                                        INSERT INTO users (user_id, full_name, post_id, password_hash, role_id)
                                        VALUES (%s, %s, %s, %s, 1)
                                    """, (user_vk_id, fio, post_id, hash_password(USER_REGISTRATION_PASSWORD)))
                                    write_msg(user_vk_id, f"🎉 Пользователь {fio} успешно зарегистрирован! Отправьте любое сообщение, чтобы пройти авторизацию!")
                                conn.commit()

                            except Exception as e:
                                print("Ошибка при сохранении в БД:", e)
                                write_msg(user_vk_id, "⚠️ Произошла ошибка при сохранении данных. Попробуйте еще раз.")
                            finally:
                                # Конец блока сохранения - очистка состояния регистрации
                                registration_state.pop(user_vk_id, None)


                    else:
                        # Сценарий 2: авторизация
                        # Проверка, ждет ли пользователь ввода пароля/ключа
                        if user_vk_id in waiting_for_input:
                            expected_action = waiting_for_input[user_vk_id]
                            user_data = db.get_user(user_vk_id)

                            if user_data is None:
                                write_msg(user_vk_id, "Ошибка: данные пользователя не найдены")
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
                                write_msg(user_vk_id, "❌ Неверный пароль или ключ доступа")
                            
                            waiting_for_input.pop(user_vk_id)

                        else:
                            # Пользователь есть в БД, но еще не ввел пароль
                            # Приветствие по ФИО и запрос пароля
                            full_name = user_from_db[1]
                            role_id = user_from_db[4]
                            
                            if role_id == 2: # Админ
                                write_msg(user_vk_id, f"Здравствуйте, {full_name}! Для входа введите ключ доступа")
                                waiting_for_input[user_vk_id] = 'admin_key'
                            else: # Обычный пользователь
                                write_msg(user_vk_id, f"Здравствуйте, {full_name}! Для входа в систему введите Ваш пароль")
                                waiting_for_input[user_vk_id] = 'password'

    except Exception as e:
        print(f"!!! КРИТИЧЕСКАЯ ОШИБКА В ЦИКЛЕ !!!")
        print(f"Текст ошибки: {e}")
        traceback.print_exc()
        print("Бот перезапустит цикл через 15 секунд...")
        time.sleep(15)