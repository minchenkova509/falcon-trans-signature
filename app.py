from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
import os
import io
import time
from pathlib import Path
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
import tempfile
import base64
from PIL import Image, ImageDraw, ImageFont
import json

# Константы для единиц измерения
MM_TO_PT = 72/25.4  # 1 мм = 2.83465 пунктов
PT_TO_MM = 25.4/72  # 1 пункт = 0.352778 мм

def mm(v):
    """Конвертирует миллиметры в пункты"""
    return v * MM_TO_PT

def pt_to_mm(v):
    """Конвертирует пункты в миллиметры"""
    return v * PT_TO_MM

# Предкеш PNG печатей для производительности (будет инициализирован после определения функций)
SEAL_BYTES_FALCON = None
SEAL_BYTES_FALCON_SIGNATURE = None
SEAL_BYTES_IP = None
SEAL_BYTES_IP_SIGNATURE = None

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

# Создаем папку для загрузок если её нет
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.errorhandler(413)
def too_large(e):
    """Обработчик ошибки превышения размера файла"""
    return jsonify({'error': 'Файл слишком большой. Максимальный размер: 16 МБ'}), 413

@app.errorhandler(500)
def internal_error(e):
    """Обработчик внутренних ошибок сервера"""
    return jsonify({'error': 'Внутренняя ошибка сервера. Попробуйте позже.'}), 500

@app.errorhandler(404)
def not_found(e):
    """Обработчик ошибки 404"""
    return jsonify({'error': 'Страница не найдена'}), 404

def _img_with_opacity(pil_img: Image.Image, opacity: float) -> Image.Image:
    """Применяет прозрачность к изображению"""
    if opacity >= 0.999:
        return pil_img
    pil_img = pil_img.convert("RGBA")
    r, g, b, a = pil_img.split()
    a = a.point(lambda v: int(v * opacity))
    return Image.merge("RGBA", (r, g, b, a))

def _make_overlay(page_w_pt, page_h_pt, seals_for_page, stamp_factory):
    """Создаёт PDF-оверлей размера страницы и рисует все печати."""
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_w_pt, page_h_pt))

    for seal in seals_for_page:
        x_pt = float(seal['xPt'])
        y_pt = float(seal['yPt'])
        w_pt = float(seal['wPt'])
        h_pt = float(seal['hPt'])
        opacity = float(seal.get('opacity', 1.0))
        seal_type = seal.get('type', 'falcon')

        pil_img = stamp_factory(seal_type)  # ваша create_company_seal(...)
        pil_img = _img_with_opacity(pil_img, opacity)

        buf = io.BytesIO()
        pil_img.save(buf, 'PNG', optimize=False, compress_level=0)
        buf.seek(0)

        c.drawImage(ImageReader(buf), x_pt, y_pt, width=w_pt, height=h_pt, mask='auto')

    c.showPage()
    c.save()
    packet.seek(0)
    return PdfReader(packet)

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

def seal_png_bytes(seal_type, add_signature=False):
    """Создает PNG байты печати для переиспользования"""
    img = create_signature_block(seal_type, add_signature)
    buf = io.BytesIO()
    img.save(buf, 'PNG', optimize=False, compress_level=0)
    return buf.getvalue()

def initialize_seal_cache():
    """Инициализирует кеш печатей"""
    global SEAL_BYTES_FALCON, SEAL_BYTES_FALCON_SIGNATURE, SEAL_BYTES_IP, SEAL_BYTES_IP_SIGNATURE
    SEAL_BYTES_FALCON = seal_png_bytes('falcon', False)
    SEAL_BYTES_FALCON_SIGNATURE = seal_png_bytes('falcon', True)
    SEAL_BYTES_IP = seal_png_bytes('ip', False)
    SEAL_BYTES_IP_SIGNATURE = seal_png_bytes('ip', True)

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

def get_standard_seal_coordinates(page_width_pt, page_height_pt, seal_type="falcon", add_signature=False):
    """
    Возвращает стандартные координаты для печати и подписи на последней странице
    Координаты в пунктах (pt), от левого нижнего угла страницы
    
    Args:
        page_width_pt: ширина страницы в пунктах
        page_height_pt: высота страницы в пунктах
        seal_type: тип печати ("falcon" или "ip")
        add_signature: добавлять ли подпись
    
    Returns:
        dict: координаты и размеры {x, y, width, height}
    """
    # Стандартные размеры в миллиметрах (из боевого режима)
    SEAL_WIDTH_MM = 17.6
    SEAL_HEIGHT_MM = 13.6
    SIGNATURE_WIDTH_MM = 53
    SIGNATURE_HEIGHT_MM = 28
    GAP_MM = 6  # Отступ между подписью и печатью
    
    # Отступы от краев страницы в миллиметрах
    MARGIN_LEFT_MM = 17.6
    MARGIN_BOTTOM_MM = 17.6
    
    if add_signature:
        # Разделяем подпись и печать как два объекта
        signature = {
            'x': mm(MARGIN_LEFT_MM),
            'y': mm(MARGIN_BOTTOM_MM),
            'w': mm(SIGNATURE_WIDTH_MM),
            'h': mm(SIGNATURE_HEIGHT_MM)
        }
        
        seal = {
            'x': signature['x'] + signature['w'] + mm(GAP_MM),
            'y': signature['y'],
            'w': mm(SEAL_WIDTH_MM),
            'h': mm(SEAL_HEIGHT_MM)
        }
        
        # Возвращаем общий блок, который включает и подпись, и печать
        return {
            'x': signature['x'],
            'y': signature['y'],
            'width': seal['x'] + seal['w'] - signature['x'],
            'height': max(signature['h'], seal['h'])
        }
    else:
        # Только печать
        return {
            'x': mm(MARGIN_LEFT_MM),
            'y': mm(MARGIN_BOTTOM_MM),
            'width': mm(SEAL_WIDTH_MM),
            'height': mm(SEAL_HEIGHT_MM)
        }

def add_signature_to_pdf_batch(input_pdf_path, output_pdf_path, seal_type="falcon", add_signature=False, coordinates=None):
    """
    Добавляет подпись и печать к PDF на последней странице с точными координатами
    
    Args:
        input_pdf_path: путь к входному PDF
        output_pdf_path: путь к выходному PDF
        seal_type: тип печати ("falcon" или "ip")
        add_signature: добавлять ли подпись
        coordinates: словарь с координатами {x, y, width, height} в пунктах
    """
    # Читаем исходный PDF
    reader = PdfReader(input_pdf_path)
    writer = PdfWriter()
    
    # Получаем размеры страницы
    page = reader.pages[0]
    page_width = float(page.mediabox.width)
    page_height = float(page.mediabox.height)
    
    # Если координаты не указаны, используем стандартные
    if coordinates is None:
        coordinates = get_standard_seal_coordinates(page_width, page_height, seal_type, add_signature)
    
    # Выбираем предкешированные PNG байты
    if seal_type == "falcon":
        if add_signature:
            seal_bytes = SEAL_BYTES_FALCON_SIGNATURE
        else:
            seal_bytes = SEAL_BYTES_FALCON
    else:  # ip
        if add_signature:
            seal_bytes = SEAL_BYTES_IP_SIGNATURE
        else:
            seal_bytes = SEAL_BYTES_IP
    
    try:
        # Создаем PDF с подписью
        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=(page_width, page_height))
        
        # Добавляем изображение с указанными координатами
        can.drawImage(ImageReader(io.BytesIO(seal_bytes)), 
                     coordinates['x'], coordinates['y'],
                     width=coordinates['width'], height=coordinates['height'],
                     mask='auto')  # Поддержка прозрачности
        can.save()
        
        # Получаем PDF с подписью
        packet.seek(0)
        signature_pdf = PdfReader(packet)
        
        # Объединяем страницы
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            if page_num == len(reader.pages) - 1:  # Добавляем подпись на последнюю страницу
                # Получаем ротацию страницы
                rotation = int(page.get('/Rotate', 0)) % 360
                
                # Учитываем CropBox смещение
                crop = page.cropbox
                x_offset = float(crop.lower_left[0])
                y_offset = float(crop.lower_left[1])
                
                # Учитываем CropBox смещение
                crop = page.cropbox
                x_offset = float(crop.lower_left[0])
                y_offset = float(crop.lower_left[1])
                
                # Смещаем координаты на CropBox оффсет
                adjusted_coordinates = {
                    'x': coordinates['x'] + x_offset,
                    'y': coordinates['y'] + y_offset,
                    'width': coordinates['width'],
                    'height': coordinates['height']
                }
                
                # Создаем оверлей с правильными координатами
                overlay_packet = io.BytesIO()
                overlay_can = canvas.Canvas(overlay_packet, pagesize=(page_width, page_height))
                overlay_can.drawImage(ImageReader(io.BytesIO(seal_bytes)), 
                                    adjusted_coordinates['x'], adjusted_coordinates['y'],
                                    width=adjusted_coordinates['width'], height=adjusted_coordinates['height'],
                                    mask='auto')
                overlay_can.save()
                overlay_packet.seek(0)
                final_overlay = PdfReader(overlay_packet)
                final_overlay_page = final_overlay.pages[0]
                
                # Поворачиваем оверлей если страница повернута
                if rotation:
                    final_overlay_page.rotate(rotation)
                
                page.merge_page(final_overlay_page)
            writer.add_page(page)
        
        # Сохраняем результат
        with open(output_pdf_path, 'wb') as output_file:
            writer.write(output_file)
            
    finally:
        # Очищаем буферы
        packet.close()
        if 'overlay_packet' in locals():
            overlay_packet.close()

def cleanup_old_files():
    """Очищает старые файлы из папки uploads (старше 1 часа)"""
    try:
        upload_folder = app.config['UPLOAD_FOLDER']
        if not os.path.exists(upload_folder):
            return

        current_time = time.time()
        max_age = 3600  # 1 час в секундах

        for filename in os.listdir(upload_folder):
            file_path = os.path.join(upload_folder, filename)
            if os.path.isfile(file_path):
                file_age = current_time - os.path.getmtime(file_path)
                if file_age > max_age:
                    try:
                        os.unlink(file_path)
                        print(f"Удален старый файл: {filename}")
                    except Exception as e:
                        print(f"Ошибка при удалении файла {filename}: {e}")
    except Exception as e:
        print(f"Ошибка при очистке файлов: {e}")

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

@app.route('/api-docs')
def api_docs():
    return render_template('api_docs.html')

@app.route('/batch')
def batch():
    return render_template('batch.html')

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
        # Очищаем старые файлы перед обработкой
        cleanup_old_files()

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

@app.route('/api/seals', methods=['GET'])
def get_available_seals():
    """Возвращает информацию о доступных печатях"""
    seals = [
        {
            'id': 'falcon',
            'name': 'ФАЛКОН-ТРАНС (ООО)',
            'type': 'company',
            'description': 'Официальная печать компании ФАЛКОН-ТРАНС',
            'image_url': '/static/images/falcon_seal.png'
        },
        {
            'id': 'ip',
            'name': 'ИП Заикина',
            'type': 'individual',
            'description': 'Печать индивидуального предпринимателя',
            'image_url': '/static/images/ip_seal.png'
        }
    ]
    return jsonify({'seals': seals})

@app.route('/api/stats', methods=['GET'])
def get_usage_stats():
    """Возвращает статистику использования приложения"""
    try:
        # Подсчитываем количество файлов в папке uploads
        upload_folder = app.config['UPLOAD_FOLDER']
        if os.path.exists(upload_folder):
            files_count = len([f for f in os.listdir(upload_folder) if f.endswith('.pdf')])
        else:
            files_count = 0

        stats = {
            'total_processed_files': files_count,
            'max_file_size_mb': app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024),
            'available_seals': 2,  # falcon и ip
            'service_status': 'active',
            'version': '1.0.0'
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': f'Ошибка при получении статистики: {str(e)}'}), 500

@app.route('/api/coordinates', methods=['GET'])
def get_seal_coordinates():
    """Возвращает стандартные координаты для печати и подписи"""
    try:
        # Получаем параметры из запроса
        seal_type = request.args.get('seal_type', 'falcon')
        add_signature = request.args.get('add_signature', 'false').lower() == 'true'

                # Стандартные размеры страницы A4 (в пунктах)
        page_width_pt = 595.276  # A4 ширина
        page_height_pt = 841.890  # A4 высота
        
        # Получаем координаты
        coordinates = get_standard_seal_coordinates(page_width_pt, page_height_pt, seal_type, add_signature)
        
        # Добавляем информацию о единицах измерения
        response = {
            'coordinates': coordinates,
            'units': 'points (pt)',
            'page_size': {
                'width_pt': page_width_pt,
                'height_pt': page_height_pt,
                'width_mm': pt_to_mm(page_width_pt),
                'height_mm': pt_to_mm(page_height_pt)
            },
            'seal_type': seal_type,
            'add_signature': add_signature,
            'description': {
                'x': 'Отступ от левого края страницы',
                'y': 'Отступ от нижнего края страницы',
                'width': 'Ширина печати/блока подписи',
                'height': 'Высота печати/блока подписи'
            },
            'note': 'Координаты справочные для A4. При применении к реальному документу используются фактические размеры последней страницы.'
        }

        return jsonify(response)

    except Exception as e:
        return jsonify({'error': f'Ошибка при получении координат: {str(e)}'}), 500

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

            # Группируем печати по странице (0-based)
            seals_by_page = {}
            for seal in data.get('seals', []):
                i = int(seal.get('pageIndex', 0))
                seals_by_page.setdefault(i, []).append(seal)

            for i, page in enumerate(reader.pages):
                if i in seals_by_page:
                    page_w_pt = float(page.mediabox.width)
                    page_h_pt = float(page.mediabox.height)
                    overlay = _make_overlay(page_w_pt, page_h_pt, seals_by_page[i], create_company_seal)
                    page.merge_page(overlay.pages[0])  # flatten по сути
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

@app.route('/api/batch-process', methods=['POST'])
def batch_process_files():
    """Пакетная обработка файлов с точными координатами"""
    try:
        data = request.get_json()

        if not data or 'files' not in data:
            return jsonify({'error': 'Неверные данные запроса'}), 400

        # Параметры обработки
        seal_type = data.get('seal_type', 'falcon')
        add_signature = data.get('add_signature', False)
        coordinates = data.get('coordinates')  # {x, y, width, height} в пунктах

        # Валидация координат
        if coordinates:
            required_keys = ['x', 'y', 'width', 'height']
            if not all(key in coordinates for key in required_keys):
                return jsonify({'error': 'Неверный формат координат'}), 400

        results = []

        for file_data in data['files']:
            try:
                # Декодируем PDF из base64
                pdf_data_str = file_data['pdfData']
                if isinstance(pdf_data_str, str):
                    if pdf_data_str.startswith('data:'):
                        pdf_data = base64.b64decode(pdf_data_str.split(',')[1])
                    else:
                        pdf_data = base64.b64decode(pdf_data_str)
                else:
                    continue

                # Создаем временные файлы
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_input:
                    temp_input.write(pdf_data)
                    input_path = temp_input.name

                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_output:
                    output_path = temp_output.name

                try:
                    # Обрабатываем файл
                    add_signature_to_pdf_batch(input_path, output_path, seal_type, add_signature, coordinates)

                    # Читаем результат
                    with open(output_path, 'rb') as f:
                        result_data = f.read()

                    # Кодируем в base64
                    result_base64 = base64.b64encode(result_data).decode('utf-8')

                    # Санитизируем имя файла
                    original_filename = file_data.get('filename', 'document.pdf')
                    name = secure_filename(Path(original_filename).stem) or "document"
                    out_name = f"{name}_stamped.pdf"
                    
                    results.append({
                        'success': True,
                        'filename': out_name,
                        'pdfData': f'data:application/pdf;base64,{result_base64}',
                        'size': len(result_data)
                    })

                finally:
                    # Удаляем временные файлы
                    if os.path.exists(input_path):
                        os.unlink(input_path)
                    if os.path.exists(output_path):
                        os.unlink(output_path)

            except Exception as e:
                results.append({
                    'success': False,
                    'filename': file_data.get('filename', 'unknown.pdf'),
                    'error': str(e)
                })

        return jsonify({
            'success': True,
            'results': results,
            'total_files': len(data['files']),
            'processed_files': len([r for r in results if r['success']])
        })

    except Exception as e:
        return jsonify({'error': f'Ошибка при пакетной обработке: {str(e)}'}), 500

if __name__ == '__main__':
    # Инициализируем кеш печатей при запуске
    initialize_seal_cache()
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080))) 