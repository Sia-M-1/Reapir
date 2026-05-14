import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType

# --- КОНФИГУРАЦИЯ ПАРОЛЕЙ ---
# Пароль для регистрации новых пользователей
USER_REGISTRATION_PASSWORD = "USER_PASSWORD"
# Ключ доступа для регистрации администраторов
ADMIN_REGISTRATION_KEY = "ADMIN_KEY"

token = "TOKEN"

# Авторизация
vk_session = vk_api.VkApi(token=token)
longpoll = VkLongPoll(vk_session)
vk = vk_session.get_api()
