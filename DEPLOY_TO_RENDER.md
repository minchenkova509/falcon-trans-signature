# 🚀 Развертывание на Render - Пошаговая инструкция

## 📋 Что нужно сделать

### 1. Создать репозиторий на GitHub

1. Перейдите на https://github.com
2. Нажмите "New repository"
3. Название: `falcon-trans-signature`
4. Описание: `ФАЛКОН-ТРАНС Подпись - веб-приложение для добавления печатей к PDF`
5. Выберите "Public"
6. НЕ ставьте галочки (README, .gitignore, license)
7. Нажмите "Create repository"

### 2. Загрузить код на GitHub

После создания репозитория, выполните эти команды в терминале:

```bash
# Добавить удаленный репозиторий
git remote add origin https://github.com/YOUR_USERNAME/falcon-trans-signature.git

# Загрузить код
git branch -M main
git push -u origin main
```

### 3. Развернуть на Render

1. Перейдите на https://render.com
2. Нажмите "New +" → "Web Service"
3. Подключите GitHub аккаунт
4. Выберите репозиторий `falcon-trans-signature`
5. Настройки:
   - **Name:** `falcon-trans-signature`
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Plan:** `Free`

6. Нажмите "Create Web Service"

## ⚙️ Конфигурация Render

### Автоматические настройки:
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn app:app`
- **Environment:** Python 3.9.16

### Переменные окружения (если нужны):
```
PYTHON_VERSION=3.9.16
```

## 📁 Структура проекта

```
falcon-trans-signature/
├── app.py                 # Основное приложение Flask
├── requirements.txt       # Зависимости Python
├── render.yaml           # Конфигурация Render
├── static/
│   ├── images/           # Печати и подписи
│   ├── css/             # Стили
│   └── js/              # JavaScript
├── templates/            # HTML шаблоны
└── uploads/             # Временные файлы
```

## 🔧 Файлы для деплоя

### Обязательные:
- ✅ `app.py` - Flask приложение
- ✅ `requirements.txt` - зависимости
- ✅ `render.yaml` - конфигурация Render
- ✅ `static/images/` - печати и подписи
- ✅ `templates/` - HTML шаблоны

### Дополнительные:
- ✅ `README.md` - документация
- ✅ `.gitignore` - исключения Git

## 🌐 После деплоя

1. **URL приложения:** `https://falcon-trans-signature.onrender.com`
2. **Время развертывания:** ~5-10 минут
3. **Автоматические обновления:** при push в main ветку

## 📱 Тестирование

1. Откройте URL приложения
2. Проверьте главную страницу
3. Протестируйте загрузку PDF
4. Проверьте редактор печати
5. Убедитесь, что все печати загружаются

## 🔄 Обновления

Для обновления приложения:
```bash
git add .
git commit -m "Описание изменений"
git push origin main
```

Render автоматически пересоберет и развернет приложение.

## 💡 Полезные ссылки

- **GitHub:** https://github.com/YOUR_USERNAME/falcon-trans-signature
- **Render Dashboard:** https://dashboard.render.com
- **Приложение:** https://falcon-trans-signature.onrender.com

---

**Приложение будет работать 24/7 без перерывов!** 🎉 