# 🔧 Команды для настройки GitHub

## После создания репозитория на GitHub:

1. **Скопируйте URL вашего репозитория** (например: `https://github.com/alinazaikina/falcon-trans-signature.git`)

2. **Выполните эти команды в терминале:**

```bash
# Настройка Git (замените на ваше имя и email)
git config --global user.name "Alina Zaikina"
git config --global user.email "your-email@example.com"

# Добавить удаленный репозиторий (замените URL на ваш)
git remote add origin https://github.com/alinazaikina/falcon-trans-signature.git

# Переименовать ветку в main
git branch -M main

# Загрузить код на GitHub
git push -u origin main
```

## Если возникнет ошибка аутентификации:

1. **Создайте Personal Access Token на GitHub:**
   - Перейдите в Settings → Developer settings → Personal access tokens → Tokens (classic)
   - Нажмите "Generate new token"
   - Выберите "repo" права
   - Скопируйте токен

2. **Используйте токен вместо пароля:**
   - Username: ваше имя пользователя GitHub
   - Password: токен (не пароль от аккаунта)

## После успешной загрузки:

Переходите к развертыванию на Render по инструкции в `DEPLOY_TO_RENDER.md` 