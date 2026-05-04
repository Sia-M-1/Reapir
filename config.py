import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType

token = "TOKEN"

# Авторизация
vk_session = vk_api.VkApi(token=token)
longpoll = VkLongPoll(vk_session)
vk = vk_session.get_api()
