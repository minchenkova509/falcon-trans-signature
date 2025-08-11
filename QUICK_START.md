# 🚀 Быстрый старт - ФАЛКОН-ТРАНС Подпись

## Локальный запуск

### 1. Установка зависимостей
```bash
python3 -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Запуск приложения
```bash
python app.py
```

### 3. Открытие в браузере
Перейдите по адресу: `http://localhost:8080`

## Размещение на GitHub

### 1. Создание репозитория
- Перейдите на [github.com](https://github.com)
- Создайте новый репозиторий: `falcon-trans-signature`

### 2. Загрузка кода
```bash
git remote add origin https://github.com/YOUR_USERNAME/falcon-trans-signature.git
git branch -M main
git push -u origin main
```

## Развертывание на Render

### 1. Подключение к Render
- Перейдите на [render.com](https://render.com)
- Подключите GitHub репозиторий

### 2. Настройка сервиса
- **Environment:** Python 3
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn app:app`

### 3. Создание сервиса
- Нажмите "Create Web Service"
- Дождитесь развертывания

## Тестирование

### Создание тестового PDF
```bash
python create_test_pdf.py
```

### Использование приложения
1. Откройте приложение в браузере
2. Загрузите PDF файл (drag & drop или выбор файла)
3. Дождитесь обработки
4. Скачайте документ с подписью

## Возможности

✅ Загрузка PDF через drag & drop  
✅ Автоматическое добавление подписи  
✅ Официальная печать компании  
✅ Современный интерфейс  
✅ Адаптивный дизайн  
✅ Поддержка файлов до 16 МБ  

## Поддержка

- 📖 Подробная документация: `README.md`
- 🚀 Инструкции по развертыванию: `DEPLOYMENT.md`
- 📋 Настройка GitHub: `GITHUB_SETUP.md`

---

**Готово к использованию!** 🎉 