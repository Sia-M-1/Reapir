import psycopg2
from db import config
from utils import write_msg

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

def show_admin_menu(user_id):
    """Показывает админу кнопку 'Посмотреть заявки' при входе."""
    keyboard = get_keyboard(["Посмотреть заявки"])
    write_msg(user_id, "Вы вошли как администратор. Вам доступны функции управления заявками.", keyboard=keyboard)

def list_active_tickets(user_id):
    """Выводит список активных заявок (со статусами 'Новая' и 'В работе')."""
    try:
        conn = psycopg2.connect(**config())
        cur = conn.cursor()
        
        # 1. ИЗМЕНЯЕМ ЗАПРОС: Добавляем JOIN с таблицей priority и выбираем priority_name
        cur.execute("""
            SELECT t.ticket_id, p.priority_name 
            FROM tickets t
            JOIN status s ON t.status_id = s.status_id
            JOIN priority p ON t.priority_id = p.priority_id
            WHERE s.status_name NOT IN ('Выполнена', 'Отклонена')
            ORDER BY t.ticket_id DESC
        """)
        
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            write_msg(user_id, "Активных заявок нет.")
            return

        # 2. ИЗМЕНЯЕМ ФОРМИРОВАНИЕ КНОПОК: Используем данные из запроса
        buttons = []
        for row in rows:
            ticket_number = row[0]
            priority_name = row[1]
            
            # Формируем строку вида "Заявка 123 (Высокий)"
            button_text = f"Заявка {ticket_number} ({priority_name})"
            buttons.append(button_text)
        
        keyboard = get_keyboard(buttons)
        write_msg(user_id, "Выберите заявку для просмотра:", keyboard=keyboard)

    except Exception as e:
        print("Ошибка при получении заявок:", e)
        write_msg(user_id, "Произошла ошибка при загрузке заявок.")


def show_ticket_details(user_id, ticket_id):
    """Показывает детали выбранной заявки и динамические кнопки для смены статуса."""
    try:
        conn = psycopg2.connect(**config())
        cur = conn.cursor()
        
        # --- ИЗМЕНЕНО: Запрос теперь берет данные только по тому ID, который мы передали ---
        cur.execute("""
            SELECT u.full_name, p.priority_name, c.category_name, l.location_name, t.classroom, t.description, s.status_name
            FROM tickets t
            JOIN users u ON t.user_id = u.user_id
            JOIN priority p ON t.priority_id = p.priority_id
            JOIN category c ON t.category_id = c.category_id
            JOIN location l ON t.location_id = l.location_id
            JOIN status s ON t.status_id = s.status_id
            WHERE t.ticket_id = %s
        """, (ticket_id,))
        
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if not row:
            write_msg(user_id, "Заявка не найдена.")
            return

        (fio, priority, category, location, classroom, description, current_status) = row

        message = (
            f"Заявка №{ticket_id}\n"
            f"Пользователь: {fio}\n"
            f"Уровень приоритета: {priority}\n"
            f"Категория: {category}\n"
            f"Корпус: {location}\n"
            f"Кабинет: {classroom}\n"
            f"Описание: {description}\n"
            f"Статус: {current_status}"
        )
        
        # Логика динамических кнопок остается прежней
        buttons_to_show = ["Назад"]
        
        if current_status == 'Новая':
             buttons_to_show.extend(["Принять", "Отклонить"])
        elif current_status == 'В работе':
             buttons_to_show.extend(["Закрыть", "Отклонить"])
        
        keyboard = get_keyboard(buttons_to_show)
        write_msg(user_id, message, keyboard=keyboard)
        
    except Exception as e:
        print("Ошибка при получении деталей заявки:", e)
        write_msg(user_id, "Произошла ошибка при загрузке деталей заявки.")


def change_ticket_status(user_id, ticket_id, new_status_name):
    """Меняет статус заявки и отправляет уведомление пользователю."""
    try:
        conn = psycopg2.connect(**config())
        cur = conn.cursor()
        
        # Получаем данные пользователя и категории для уведомления ИЗ ЕДИНОГО ЗАПРОСА!
        cur.execute("""
             SELECT t.user_id, c.category_name 
             FROM tickets t 
             JOIN category c ON t.category_id = c.category_id 
             WHERE t.ticket_id = %s
         """, (ticket_id,))
        ticket_info = cur.fetchone()
        if not ticket_info:
            write_msg(user_id, "Заявка не найдена.")
            return
             
        user_vk_id, category_name = ticket_info

         # Получаем id нового статуса
        cur.execute("SELECT status_id FROM status WHERE status_name = %s", (new_status_name,))
        status_row = cur.fetchone()
        if not status_row:
            write_msg(user_id, "Ошибка: статус не найден.")
            return
        new_status_id = status_row[0]
         
        # Обновляем статус заявки в базе данных (используем тот же курсор)
        cur.execute("UPDATE tickets SET status_id = %s WHERE ticket_id = %s", (new_status_id, ticket_id))
         
        # Формируем сообщение для пользователя с номером заявки и категорией
        if new_status_name == 'В работе':
            msg_user = f"🎉 Поздравляем! Ваша заявка №{ticket_id} ({category_name}) была принята в работу!"
        elif new_status_name == 'Отклонена':
            msg_user = f"❌ Приносим извинения, Ваша заявка №{ticket_id} ({category_name}) была отклонена."
        elif new_status_name == 'Выполнена':
            msg_user = f"🎉 Поздравляем! Ваша заявка №{ticket_id} ({category_name}) была отработана!"
         
        write_msg(user_vk_id, msg_user)
        
        # --- НОВАЯ ЛОГИКА: Проверяем, остались ли еще активные заявки? ---
        # Это нужно, чтобы понять, возвращать ли в меню или просто обновить список.
        cur.execute("SELECT COUNT(*) FROM tickets WHERE status_id != %s AND status_id != %s", (3, 4)) # 3=Выполнена, 4=Отклонена
        active_count = cur.fetchone()[0]

        # Фиксируем изменения в базе данных ОДНИМ коммитом!
        conn.commit()
         
        write_msg(user_id, f"✅ Статус заявки №{ticket_id} успешно изменён на '{new_status_name}'.")
        
        # Если заявок больше нет, возвращаем в главное меню админа
        if active_count == 0:
            show_admin_menu(user_id)
        else:
            # Если заявки еще остались, просто обновляем список
            list_active_tickets(user_id)
        
    except Exception as e:
        print("Ошибка при изменении статуса:", e)
        write_msg(user_id, "⚠️ Произошла ошибка при изменении статуса заявки.")
    finally:
        if conn:
             conn.close()
