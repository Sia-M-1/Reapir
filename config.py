import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType

# --- КОНФИГУРАЦИЯ ПАРОЛЕЙ ---
# Пароль для регистрации новых пользователей
USER_REGISTRATION_PASSWORD = "1111111"
# Ключ доступа для регистрации администраторов
ADMIN_REGISTRATION_KEY = "2222222"

token = "TOKEN_VK_API"

# Авторизация
vk_session = vk_api.VkApi(token=token)
longpoll = VkLongPoll(vk_session)
vk = vk_session.get_api()
