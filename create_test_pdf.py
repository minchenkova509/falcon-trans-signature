from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

def create_test_pdf():
    """Создает тестовый PDF файл для демонстрации"""
    filename = "test_document.pdf"
    
    # Создаем PDF
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    
    # Заголовок
    c.setFont("Helvetica-Bold", 24)
    c.drawString(width/2 - 100, height - 100, "ТЕСТОВЫЙ ДОКУМЕНТ")
    
    # Подзаголовок
    c.setFont("Helvetica", 16)
    c.drawString(width/2 - 80, height - 140, "для демонстрации работы приложения")
    
    # Основной текст
    c.setFont("Helvetica", 12)
    y_position = height - 200
    
    text_lines = [
        "Это тестовый документ для демонстрации работы приложения",
        "ФАЛКОН-ТРАНС Подпись.",
        "",
        "Данный документ содержит:",
        "• Заголовок документа",
        "• Описание назначения",
        "• Место для подписи и печати",
        "",
        "После обработки в приложении здесь появится:",
        "• Подпись генерального директора",
        "• Официальная печать компании",
        "",
        "Информация о компании:",
        "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ",
        "ФАЛКОН-ТРАНС",
        "ОГРН: 1127746519306",
        "Генеральный директор: Заикин С.С.",
        "",
        "Дата создания: 2024 год",
        "Место: Москва"
    ]
    
    for line in text_lines:
        c.drawString(50, y_position, line)
        y_position -= 20
    
    # Добавляем рамку
    c.rect(30, 30, width - 60, height - 60)
    
    c.save()
    print(f"Тестовый PDF файл создан: {filename}")

if __name__ == "__main__":
    create_test_pdf() 