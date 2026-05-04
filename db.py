# db.py

import psycopg2
from configparser import ConfigParser

def config(filename='database.ini', section='postgresql'):
    """Читаем файл конфигурации и возвращаем параметры подключения."""
    parser = ConfigParser()
    parser.read(filename, encoding='utf-8')
    db_config = {}
    if parser.has_section(section):
        params = parser.items(section)
        for param in params:
            db_config[param[0]] = param[1]
    else:
        raise Exception(f'Секция {section} не найдена в файле {filename}')
    return db_config

def init_db():
    """Пробуем подключиться к базе данных при запуске бота."""
    conn = None
    try:
        params = config()
        print("Пробуем подключиться к базе данных...")
        conn = psycopg2.connect(**params)
        print("✅ Подключение к базе данных прошло успешно!")
        conn.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print("❌ Ошибка подключения к базе данных:", error)
        # Здесь можно добавить exit(), чтобы бот не работал без БД

def get_user(user_vk_id):
    """
    Получаем данные пользователя из базы по его VK ID.
    Возвращает строку из базы или None, если пользователя нет.
    """
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        
        # Используем %s для подстановки параметров (безопасно от SQL-инъекций)
        cur.execute("SELECT * FROM users WHERE user_id = %s", (user_vk_id,))
        
        row = cur.fetchone() # Получаем первую найденную строку
        cur.close()
        return row # Если пользователя нет, вернется None

    except (Exception, psycopg2.DatabaseError) as error:
        print("Ошибка при получении пользователя:", error)
    finally:
        if conn is not None:
            conn.close()

def get_password_hash(user_vk_id):
    """
    Получает хэш пароля пользователя из базы данных.
    Возвращает объект (bytes или memoryview), который можно передать в verify_password.
    """
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        
        # Запрашиваем поле password_hash напрямую
        cur.execute("SELECT password_hash FROM users WHERE user_id = %s", (user_vk_id,))
        
        row = cur.fetchone()
        cur.close()
        
        if row and row[0] is not None:
            return row[0] # Возвращаем как есть (bytes или memoryview)
        return None

    except Exception as error:
        print("Ошибка при получении хэша:", error)
    finally:
        if conn is not None:
            conn.close()