from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
import os
import io
import time
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

def create_company_seal(seal_type="falcon"):
    """Загружает готовое изображение печати"""
    try:
        # Выбираем путь к печати в зависимости от типа
        if seal_type == "falcon":
            seal_path = "static/images/falcon_seal.png"
        elif seal_type == "ip":
            seal_path = "static/images/ip_seal.png"
        else:
            seal_path = "static/images/falcon_seal.png"  # По умолчанию
        
        if os.path.exists(seal_path):
            img = Image.open(seal_path)
            # Конвертируем в RGBA если нужно
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            return img
        else:
            # Если файл не найден, создаем простую заглушку
            print(f"Файл печати не найден: {seal_path}")
            print(f"Создаем простую заглушку. Загрузите файл {os.path.basename(seal_path)} в папку static/images/")
            
            # Создаем простую заглушку
            size = 200
            img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            # Простой круг
            center = size // 2
            radius = 80
            draw.ellipse([center - radius, center - radius, center + radius, center + radius], 
                        outline=(0, 0, 255, 255), width=3)
            
            # Текст в центре
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 16)
            except:
                font = ImageFont.load_default()
            
            if seal_type == "ip":
                draw.text((center - 30, center - 10), "ИП", fill=(0, 0, 255, 255), font=font)
            else:
                draw.text((center - 40, center - 10), "ФАЛКОН-ТРАНС", fill=(0, 0, 255, 255), font=font)
            
            return img
            
    except Exception as e:
        print(f"Ошибка при загрузке печати: {e}")
        # Возвращаем простую заглушку в случае ошибки
        size = 200
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        center = size // 2
        radius = 80
        draw.ellipse([center - radius, center - radius, center + radius, center + radius], 
                    outline=(0, 0, 255, 255), width=3)
        return img

def create_signature_block(seal_type="falcon", add_signature=False):
    """Создает блок с печатью и опционально подписью"""
    # Загружаем оригинальную печать
    seal = create_company_seal(seal_type)
    
    # Масштабирование с сохранением пропорций (как в pdf_processor.py)
    original_width, original_height = seal.size
    max_width = 176  # Финальный размер из pdf_processor.py
    max_height = 136  # Финальный размер из pdf_processor.py
    
    # Вычисляем коэффициент масштабирования (как в pdf_processor.py)
    width_ratio = max_width / original_width
    height_ratio = max_height / original_height
    scale_factor = min(width_ratio, height_ratio)  # Меньший коэффициент для сохранения пропорций
    
    # Новые размеры
    new_width = int(original_width * scale_factor)
    new_height = int(original_height * scale_factor)
    
    # Изменяем размер печати с высоким качеством (без размытия)
    seal = seal.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Создаем изображение с прозрачным фоном
    if add_signature:
        # Если нужна подпись, создаем больший блок
        img = Image.new('RGBA', (new_width + 200, new_height + 100), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Добавляем текст подписи
        try:
            font_large = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 20)
            font_medium = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 14)
        except:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
        
        # Текст "ПЕРЕВОЗЧИК" или "ИП"
        title = "ИП" if seal_type == "ip" else "ПЕРЕВОЗЧИК"
        draw.text((10, 10), title, fill=(0, 0, 0, 255), font=font_large)
        
        # Линия подписи
        draw.line([(10, 50), (150, 50)], fill=(0, 0, 0, 255), width=2)
        draw.text((10, 60), "подпись", fill=(0, 0, 0, 255), font=font_medium)
        
        # Размещаем печать справа
        img.paste(seal, (new_width - 50, 10), seal)
    else:
        # Только печать
        img = Image.new('RGBA', (new_width, new_height), (0, 0, 0, 0))
        img.paste(seal, (0, 0), seal)
    
    return img

def find_signature_position(page_text):
    """Интеллектуальный поиск позиции для печати"""
    signature_patterns = ['подпись', 'podpis', 'подпи', 'signature']
    signature_keywords = ['подпис', 'директор', 'заикин']
    
    # Ищем паттерны в тексте
    signature_x = None
    signature_y = None
    
    # Простой поиск по ключевым словам
    for pattern in signature_patterns + signature_keywords:
        if pattern.lower() in page_text.lower():
            # Если найдено, используем позицию на 1.5см выше и 3см левее
            return 50, 300  # x=50 (3см левее), y=300 (1.5см выше)
    
    # Если ничего не найдено, возвращаем резервную позицию
    return 20, 200  # Резервная позиция (левее и выше)

def add_signature_to_pdf(input_pdf_path, output_pdf_path, seal_type="falcon", add_signature=False):
    """Добавляет подпись и печать к PDF на последней странице"""
    # Читаем исходный PDF
    reader = PdfReader(input_pdf_path)
    writer = PdfWriter()
    
    # Получаем размеры страницы
    page = reader.pages[0]
    page_width = float(page.mediabox.width)
    page_height = float(page.mediabox.height)
    
    # Извлекаем текст с последней страницы для поиска позиции
    last_page = reader.pages[-1]
    try:
        page_text = last_page.extract_text()
    except:
        page_text = ""
    
    # Интеллектуальный поиск позиции
    x_position, y_position = find_signature_position(page_text)
    
    # Создаем блок подписи
    signature_block = create_signature_block(seal_type, add_signature)
    
    # Сохраняем блок подписи во временный файл с высоким качеством
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
        signature_block.save(tmp_file.name, 'PNG', optimize=False, compress_level=0)
        signature_path = tmp_file.name
    
    # Создаем PDF с подписью
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))
    
    # Получаем размеры печати из созданного изображения
    signature_width = signature_block.size[0]
    signature_height = signature_block.size[1]
    
    # Проверяем, что позиция не выходит за границы страницы
    if y_position > page_height - signature_height:
        y_position = page_height * 0.25  # 25% от высоты страницы
    
    # Добавляем изображение с поддержкой прозрачности
    can.drawImage(signature_path, x_position, y_position, 
                 width=signature_width, height=signature_height,
                 mask='auto')  # Поддержка прозрачности
    can.save()
    
    # Получаем PDF с подписью
    packet.seek(0)
    signature_pdf = PdfReader(packet)
    
    # Объединяем страницы
    for page_num in range(len(reader.pages)):
        page = reader.pages[page_num]
        if page_num == len(reader.pages) - 1:  # Добавляем подпись на последнюю страницу
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

@app.route('/test')
def test():
    return send_file('test_upload.html')

@app.route('/simple')
def simple():
    return render_template('simple.html')

@app.route('/editor')
def editor():
    return render_template('editor.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Файл не выбран'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400
    
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Пожалуйста, загрузите PDF файл'}), 400
    
    # Получаем параметры из формы
    seal_type = request.form.get('seal_type', 'falcon')
    add_signature = request.form.get('add_signature', 'false').lower() == 'true'
    
    try:
        # Сохраняем загруженный файл
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(input_path)
        
        # Создаем имя для выходного файла
        name, ext = os.path.splitext(filename)
        output_filename = f"{name}_с_подписью{ext}"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        
        # Добавляем подпись с выбранными параметрами
        add_signature_to_pdf(input_path, output_path, seal_type, add_signature)
        
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

@app.route('/ping')
def ping():
    """Эндпоинт для Keep Alive"""
    from datetime import datetime
    return jsonify({
        'status': 'pong', 
        'timestamp': datetime.now().isoformat(),
        'service': 'falcon-trans-signature'
    })

@app.route('/save-document', methods=['POST'])
def save_document():
    """Сохраняет документ с наложенными печатями"""
    try:
        data = request.get_json()
        print(f"DEBUG: Получены данные: {len(data.get('seals', []))} печатей")
        
        if not data or 'pdfData' not in data or 'seals' not in data:
            return jsonify({'error': 'Неверные данные'}), 400
        
        # Декодируем PDF из base64
        pdf_data_str = data['pdfData']
        if isinstance(pdf_data_str, str):
            # Если это строка с data URL
            if pdf_data_str.startswith('data:'):
                pdf_data = base64.b64decode(pdf_data_str.split(',')[1])
            else:
                # Если это просто base64 строка
                pdf_data = base64.b64decode(pdf_data_str)
        else:
            return jsonify({'error': 'Неверный формат данных PDF'}), 400
        
        # Создаем временный файл для исходного PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
            temp_pdf.write(pdf_data)
            temp_pdf_path = temp_pdf.name
        
        # Создаем временный файл для результата
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_result:
            result_path = temp_result.name
        
        try:
            # Читаем исходный PDF
            reader = PdfReader(temp_pdf_path)
            writer = PdfWriter()
            
            # Накладываем печати на соответствующие страницы
            if reader.pages and data['seals']:
                print(f"DEBUG: Накладываем {len(data['seals'])} печатей на соответствующие страницы")
                
                # Группируем печати по страницам
                seals_by_page = {}
                for seal in data['seals']:
                    page_num = seal.get('page', 1) - 1  # Нумерация страниц с 0
                    if page_num not in seals_by_page:
                        seals_by_page[page_num] = []
                    seals_by_page[page_num].append(seal)
                
                # Обрабатываем каждую страницу с печатями
                for page_num, seals in seals_by_page.items():
                    if page_num < len(reader.pages):
                        print(f"DEBUG: Обрабатываем страницу {page_num + 1} с {len(seals)} печатями")
                        
                        # Получаем страницу
                        page = reader.pages[page_num]
                        
                        # Создаем canvas для наложения печатей
                        packet = io.BytesIO()
                        c = canvas.Canvas(packet, pagesize=A4)
                        
                        # Накладываем каждую печать на эту страницу
                        for i, seal in enumerate(seals):
                            seal_type = seal.get('type', 'falcon')
                            x = float(seal['x'])
                            y = float(seal['y'])
                            width = float(seal['width'])
                            height = float(seal['height'])
                            opacity = float(seal.get('opacity', 1.0))
                            
                            # Масштабируем координаты из браузера в PDF
                            # A4 размер: 595 x 842 точек
                            # Реальные размеры iframe могут отличаться, используем более точное масштабирование
                            
                            # Получаем реальные размеры iframe из данных
                            iframe_width = data.get('iframeWidth', 800)
                            iframe_height = data.get('iframeHeight', 600)
                            
                            # Масштабируем координаты пропорционально
                            scale_x = 595 / iframe_width
                            scale_y = 842 / iframe_height
                            
                            x_scaled = x * scale_x
                            
                            # Инвертируем Y координату (браузер сверху вниз, ReportLab снизу вверх)
                            if page_num == 1:  # Вторая страница
                                # Для второй страницы корректируем Y координату
                                page_height = iframe_height / 2  # Высота одной страницы в iframe
                                adjusted_y = y - page_height  # Смещаем относительно второй страницы
                                y_scaled = 842 - (adjusted_y * scale_y) - (height * scale_y)
                            else:  # Первая страница
                                y_scaled = 842 - (y * scale_y) - (height * scale_y)
                            
                            width_scaled = width * scale_x
                            height_scaled = height * scale_y
                            
                            # Проверяем границы
                            if x_scaled < 0: x_scaled = 50
                            if y_scaled < 0: y_scaled = 50
                            if x_scaled + width_scaled > 595: x_scaled = 595 - width_scaled - 50
                            if y_scaled + height_scaled > 842: y_scaled = 842 - height_scaled - 50
                            
                            print(f"DEBUG: Печать {i+1} на странице {page_num + 1}: тип={seal_type}, x={x_scaled}, y={y_scaled}, w={width_scaled}, h={height_scaled}")
                            
                            # Загружаем изображение печати
                            seal_img = create_company_seal(seal_type)
                            
                            # Сохраняем во временный файл
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_img:
                                seal_img.save(temp_img.name, 'PNG', optimize=False, compress_level=0)
                                img_path = temp_img.name
                            
                            try:
                                # Накладываем изображение
                                c.drawImage(img_path, x_scaled, y_scaled, width=width_scaled, height=height_scaled, mask='auto')
                                print(f"DEBUG: Печать {i+1} наложена успешно на страницу {page_num + 1}")
                                
                            finally:
                                # Удаляем временный файл изображения
                                os.unlink(img_path)
                        
                        c.save()
                        print(f"DEBUG: Canvas для страницы {page_num + 1} сохранен")
                        
                        # Перемещаем canvas поверх страницы
                        packet.seek(0)
                        overlay = PdfReader(packet)
                        
                        # Накладываем overlay на страницу
                        page.merge_page(overlay.pages[0])
                        print(f"DEBUG: Печати наложены на страницу {page_num + 1}")
            
            # Добавляем все страницы в writer
            for page in reader.pages:
                writer.add_page(page)
            
            # Сохраняем результат
            with open(result_path, 'wb') as output_file:
                writer.write(output_file)
            
            # Проверяем размер файла
            file_size = os.path.getsize(result_path)
            print(f"DEBUG: Размер созданного PDF: {file_size} байт")
            
            if file_size == 0:
                return jsonify({'error': 'Создан пустой PDF файл'}), 500
            
            # Читаем результат и отправляем
            with open(result_path, 'rb') as f:
                result_data = f.read()
            
            # Кодируем в base64 для отправки
            result_base64 = base64.b64encode(result_data).decode('utf-8')
            print(f"DEBUG: Размер base64 данных: {len(result_base64)} символов")
            
            return jsonify({
                'success': True,
                'pdfData': f'data:application/pdf;base64,{result_base64}',
                'filename': f'document_with_seals_{int(time.time())}.pdf'
            })
            
        finally:
            # Удаляем временные файлы
            if os.path.exists(temp_pdf_path):
                os.unlink(temp_pdf_path)
            if os.path.exists(result_path):
                os.unlink(result_path)
                
    except Exception as e:
        print(f"Ошибка при сохранении документа: {e}")
        return jsonify({'error': f'Ошибка при сохранении: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080))) 