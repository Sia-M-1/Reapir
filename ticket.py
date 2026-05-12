# ticket.py

import psycopg2
import json
from db import config
from utils import write_msg

# Константы для шагов FSM
STEP_CATEGORY = 'select_category'
STEP_LOCATION = 'select_location'
STEP_CLASSROOM = 'input_classroom'
STEP_DESCRIPTION = 'input_description'

def get_keyboard(buttons_list):
    keyboard = {
        "one_time": False,
        "buttons": []
    }
    for button_text in buttons_list:
        label = button_text[:39]
        
        keyboard["buttons"].append([
            {
                "action": {
                    "type": "text",
                    "label": label, 
                    "payload": {}
                },
                "color": "primary"
            }
        ])
    return keyboard

def start_ticket_process(user_vk_id, write_msg_func):
    try:
        conn = psycopg2.connect(**config())
        cur = conn.cursor()
        cur.execute("SELECT category_name FROM category")
        categories = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        keyboard = get_keyboard(categories)
        write_msg_func(user_vk_id, "Пожалуйста, выберите категорию проблемы:", keyboard=keyboard)
        return STEP_CATEGORY
    except Exception as e:
        print("Ошибка при получении категорий:", e)
        write_msg_func(user_vk_id, "Произошла ошибка при загрузке категорий. Попробуйте позже.")
        return None

def process_ticket_step(user_vk_id, message_text, user_ticket_data, user_ticket_step, write_msg_func):
    current_step = user_ticket_step.get(user_vk_id)

    if current_step == STEP_CATEGORY:
        try:
            conn = psycopg2.connect(**config())
            cur = conn.cursor()
            cur.execute("SELECT category_id FROM category WHERE category_name = %s", (message_text,))
            result = cur.fetchone()
            cur.close()
            conn.close()
            if result:
                user_ticket_data[user_vk_id]['category_id'] = result[0]
                user_ticket_step[user_vk_id] = STEP_LOCATION
                conn = psycopg2.connect(**config())
                cur = conn.cursor()
                cur.execute("SELECT location_name FROM location")
                locations = [row[0] for row in cur.fetchall()]
                cur.close()
                conn.close()
                keyboard = get_keyboard(locations)
                write_msg_func(user_vk_id, "Пожалуйста, выберите корпус:", keyboard=keyboard)
                return STEP_LOCATION
            else:
                write_msg_func(user_vk_id, "Категория не найдена. Попробуйте снова.")
                return STEP_CATEGORY
        except Exception as e:
            print("Ошибка при обработке категории:", e)
            write_msg_func(user_vk_id, "Произошла ошибка. Попробуйте снова.")
            return STEP_CATEGORY

    elif current_step == STEP_LOCATION:
        try:
            conn = psycopg2.connect(**config())
            cur = conn.cursor()
            cur.execute("SELECT location_id FROM location WHERE location_name = %s", (message_text,))
            result = cur.fetchone()
            cur.close()
            conn.close()
            if result:
                user_ticket_data[user_vk_id]['location_id'] = result[0]
                user_ticket_step[user_vk_id] = STEP_CLASSROOM
                write_msg_func(user_vk_id, "Пожалуйста, введите номер кабинета (например, 305 или Серверная):")
                return STEP_CLASSROOM
        except Exception as e:
            print("Ошибка при обработке локации:", e)
            return STEP_LOCATION

    elif current_step == STEP_CLASSROOM:
        user_ticket_data[user_vk_id]['classroom'] = message_text.strip()
        user_ticket_step[user_vk_id] = STEP_DESCRIPTION
        write_msg_func(user_vk_id, "Пожалуйста, кратко и своими словами опишите проблему")
        return STEP_DESCRIPTION

    elif current_step == STEP_DESCRIPTION:
        user_ticket_data[user_vk_id]['description'] = message_text.strip()
        try:
            conn = psycopg2.connect(**config())
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
            write_msg_func(user_vk_id, "🎉 Ваша заявка успешно сохранена! Чтобы отправить новую заявку отправьте любое сообщение для появления кнопки Создать заявку")
        except Exception as e:
            print("Ошибка при сохранении заявки:", e)
            write_msg_func(user_vk_id, "⚠️ Произошла ошибка. Попробуйте создать заявку заново.")
        finally:
            user_ticket_data.pop(user_vk_id, None)
            user_ticket_step.pop(user_vk_id, None)
        return None
