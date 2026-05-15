import argon2

def hash_password(plain_password):
    """
    Хеширует пароль с помощью алгоритма Argon2.
    Возвращает строку с хешем, готовую для сохранения в БД.
    """
    ph = argon2.PasswordHasher()
    hash_str = ph.hash(plain_password)
    return hash_str