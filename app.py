from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
import os
import io
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import tempfile
import base64
from PIL import Image, ImageDraw, ImageFont
import json

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

# Создаем папку для загрузок если её нет
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Настройки печати ФАЛКОН-ТРАНС
COMPANY_NAME = "ФАЛКОН-ТРАНС"
COMPANY_TYPE = "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ"
OGRN = "ОГРН 1127746519306"
CITY = "МОСКВА"
DIRECTOR_NAME = "Заикин С.С."

def create_company_seal():
    """Создает изображение печати компании"""
    # Создаем изображение печати
    size = 200
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Рисуем круг печати
    center = size // 2
    radius = 80
    
    # Внешний круг (синий)
    draw.ellipse([center - radius, center - radius, center + radius, center + radius], 
                 outline=(0, 0, 255, 255), width=3)
    
    # Внутренний круг
    inner_radius = radius - 15
    draw.ellipse([center - inner_radius, center - inner_radius, center + inner_radius, center + inner_radius], 
                 outline=(0, 0, 255, 255), width=1)
    
    # Добавляем текст по кругу (название компании)
    try:
        # Пытаемся использовать системный шрифт
        font_small = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 10)
    except:
        font_small = ImageFont.load_default()
    
    # Текст по кругу - название компании
    company_text = "ФАЛКОН-ТРАНС"
    text_radius = radius - 8
    
    # Размещаем текст по кругу
    for i, char in enumerate(company_text):
        angle = (i * 360 / len(company_text)) - 90  # Начинаем сверху
        x = center + int(text_radius * (angle * 3.14159 / 180))
        y = center + int(text_radius * (angle * 3.14159 / 180))
        draw.text((x-5, y-5), char, fill=(0, 0, 255, 255), font=font_small)
    
    # Центральный символ (звезда)
    star_points = []
    for i in range(5):
        angle = i * 72 - 90
        x = center + int(15 * (angle * 3.14159 / 180))
        y = center + int(15 * (angle * 3.14159 / 180))
        star_points.extend([x, y])
    
    if len(star_points) >= 6:
        draw.polygon(star_points, fill=(0, 0, 255, 255))
    
    return img

def create_signature_block():
    """Создает блок с подписью и печатью"""
    # Создаем изображение блока подписи
    width, height = 400, 200
    img = Image.new('RGBA', (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    # Заголовок "ПЕРЕВОЗЧИК"
    try:
        # Пытаемся использовать системный шрифт
        font_large = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 24)
        font_medium = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 16)
        font_small = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 12)
    except:
        # Fallback на стандартный шрифт
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    # Заголовок
    draw.text((width//2 - 60, 20), "ПЕРЕВОЗЧИК", fill=(0, 0, 0, 255), font=font_large)
    
    # Линия для подписи
    draw.line([(50, 80), (200, 80)], fill=(0, 0, 0, 255), width=2)
    draw.text((50, 90), "Генеральный директор", fill=(0, 0, 0, 255), font=font_medium)
    draw.text((50, 110), "подпись", fill=(0, 0, 0, 255), font=font_small)
    
    # Имя директора
    draw.text((220, 80), f"/{DIRECTOR_NAME}/", fill=(0, 0, 0, 255), font=font_medium)
    draw.text((220, 100), "ФИО", fill=(0, 0, 0, 255), font=font_small)
    
    # Добавляем печать
    seal = create_company_seal()
    seal = seal.resize((120, 120))
    img.paste(seal, (150, 60), seal)
    
    return img

def add_signature_to_pdf(input_pdf_path, output_pdf_path):
    """Добавляет подпись и печать к PDF"""
    # Читаем исходный PDF
    reader = PdfReader(input_pdf_path)
    writer = PdfWriter()
    
    # Получаем размеры страницы
    page = reader.pages[0]
    page_width = float(page.mediabox.width)
    page_height = float(page.mediabox.height)
    
    # Создаем блок подписи
    signature_block = create_signature_block()
    
    # Сохраняем блок подписи во временный файл
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
        signature_block.save(tmp_file.name, 'PNG')
        signature_path = tmp_file.name
    
    # Создаем PDF с подписью
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))
    
    # Добавляем изображение подписи в правый нижний угол
    signature_width = 200
    signature_height = 100
    x_position = page_width - signature_width - 50
    y_position = 50
    
    can.drawImage(signature_path, x_position, y_position, 
                 width=signature_width, height=signature_height)
    can.save()
    
    # Получаем PDF с подписью
    packet.seek(0)
    signature_pdf = PdfReader(packet)
    
    # Объединяем страницы
    for page_num in range(len(reader.pages)):
        page = reader.pages[page_num]
        if page_num == 0:  # Добавляем подпись только на первую страницу
            page.merge_page(signature_pdf.pages[0])
        writer.add_page(page)
    
    # Сохраняем результат
    with open(output_pdf_path, 'wb') as output_file:
        writer.write(output_file)
    
    # Удаляем временный файл
    os.unlink(signature_path)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Файл не выбран'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400
    
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Пожалуйста, загрузите PDF файл'}), 400
    
    try:
        # Сохраняем загруженный файл
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(input_path)
        
        # Создаем имя для выходного файла
        name, ext = os.path.splitext(filename)
        output_filename = f"{name}_с_подписью{ext}"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        
        # Добавляем подпись
        add_signature_to_pdf(input_path, output_path)
        
        # Удаляем исходный файл
        os.unlink(input_path)
        
        return jsonify({
            'success': True,
            'filename': output_filename,
            'message': 'Подпись успешно добавлена!'
        })
        
    except Exception as e:
        return jsonify({'error': f'Ошибка при обработке файла: {str(e)}'}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        return send_file(file_path, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'error': f'Ошибка при скачивании файла: {str(e)}'}), 500

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080))) 