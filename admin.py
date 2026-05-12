import psycopg2
from db import config
from utils import write_msg
from collections import defaultdict

# Словарь для хранения данных выбранного тикета у админа
admin_ticket_data = defaultdict(dict)

def get_keyboard(buttons_list):
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
    """Показывает админу кнопку 'Посмотреть заявки'."""
    keyboard = get_keyboard(["Посмотреть заявки"])
    write_msg(user_id, "Вы вошли как администратор. Вам доступны функции управления заявками.", keyboard=keyboard)

def list_active_tickets(user_id):
    """Выводит список активных заявок (не выполнены и не отклонены)."""
    try:
        conn = psycopg2.connect(**config())
        cur = conn.cursor()
        # Только активные заявки
        cur.execute("""
            SELECT t.ticket_id, u.full_name, c.category_name, l.location_name, t.classroom, t.description, s.status_name
            FROM tickets t
            JOIN users u ON t.user_id = u.user_id
            JOIN category c ON t.category_id = c.category_id
            JOIN location l ON t.location_id = l.location_id
            JOIN status s ON t.status_id = s.status_id
            WHERE s.status_name NOT IN ('Выполнена', 'Отклонена')
            ORDER BY t.ticket_id DESC
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            write_msg(user_id, "Активных заявок нет.")
            return

        # Формируем кнопки по заявкам
        buttons = [f"Заявка {row[0]}" for row in rows]
        keyboard = get_keyboard(buttons)
        write_msg(user_id, "Выберите заявку для просмотра:", keyboard=keyboard)

        # Сохраняем данные заявок для быстрого доступа по кнопке
        for row in rows:
            admin_ticket_data[user_id][row[0]] = row

    except Exception as e:
        print("Ошибка при получении заявок:", e)
        write_msg(user_id, "Произошла ошибка при загрузке заявок.")

def show_ticket_details(user_id, ticket_id):
    """Показывает детали выбранной заявки и кнопки для смены статуса."""
    ticket = admin_ticket_data[user_id].get(ticket_id)
    if not ticket:
        write_msg(user_id, "Заявка не найдена.")
        return

    (tid, fio, category, location, classroom, description, status) = ticket
    message = (
        f"Заявка №{tid}\n"
        f"Пользователь: {fio}\n"
        f"Категория: {category}\n"
        f"Корпус: {location}\n"
        f"Кабинет: {classroom}\n"
        f"Описание: {description}\n"
        f"Статус: {status}"
    )
    keyboard = get_keyboard(["Принять", "Отклонить", "Закрыть"])
    write_msg(user_id, message, keyboard=keyboard)

def change_ticket_status(user_id, ticket_id, new_status_name):
    """Меняет статус заявки и отправляет уведомление пользователю."""
    try:
        conn = psycopg2.connect(**config())
        cur = conn.cursor()

        # Получаем user_id пользователя, создавшего заявку
        cur.execute("SELECT user_id FROM tickets WHERE ticket_id = %s", (ticket_id,))
        user_row = cur.fetchone()
        if not user_row:
            write_msg(user_id, "Заявка не найдена.")
            return
        user_vk_id = user_row[0]

        # Получаем id нового статуса
        cur.execute("SELECT status_id FROM status WHERE status_name = %s", (new_status_name,))
        status_row = cur.fetchone()
        if not status_row:
            write_msg(user_id, "Ошибка: статус не найден.")
            return
        new_status_id = status_row[0]

        # Обновляем статус заявки
        cur.execute("UPDATE tickets SET status_id = %s WHERE ticket_id = %s", (new_status_id, ticket_id))
        conn.commit()

        # Уведомление пользователю
        if new_status_name == 'В работе':
            msg_user = "🎉 Поздравляем! Ваша заявка была рассмотрена и принята в работу!"
        elif new_status_name == 'Отклонена':
            msg_user = "❌ Приносим извинения, Ваша заявка была отклонена. Попробуйте отправить новую или связаться с администратором."
        elif new_status_name == 'Выполнена':
            msg_user = "🎉 Поздравляем! Ваша заявка была рассмотрена и отработана! Надеемся проблема решилась!"
        
        write_msg(user_vk_id, msg_user)
        
        # Уведомление админу
        write_msg(user_id, f"✅ Статус заявки №{ticket_id} успешно изменён на '{new_status_name}'.")
        
    except Exception as e:
        print("Ошибка при изменении статуса:", e)
        write_msg(user_id, "⚠️ Произошла ошибка при изменении статуса заявки.")
