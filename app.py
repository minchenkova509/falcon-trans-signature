from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
import os
import io
import time
import logging
import traceback
from pathlib import Path
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
import tempfile
import base64
from PIL import Image, ImageDraw, ImageFont
import json

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Константы для единиц измерения
MM_TO_PT = 72/25.4  # 1 мм = 2.83465 пунктов
PT_TO_MM = 25.4/72  # 1 пункт = 0.352778 мм

# Константы для смещения и масштабирования печати
SHIFT_MM = 50       # поднять на 5 см (опустили еще на 1 см)
SCALE = 2.64        # увеличить в 2.64 раза (добавили 2 см к размерам)

def mm(v):
    """Конвертирует миллиметры в пункты"""
    return v * MM_TO_PT

def pt_to_mm(v):
    """Конвертирует пункты в миллиметры"""
    return v * PT_TO_MM

def pil_to_png_bytes(pil_img: Image.Image, opacity: float = 1.0) -> bytes:
    """PIL.Image -> PNG bytes, с учётом общей прозрачности."""
    img = pil_img.convert("RGBA")
    if opacity < 0.999:
        r,g,b,a = img.split()
        a = a.point(lambda v: int(v * opacity))
        img = Image.merge("RGBA", (r,g,b,a))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=False, compress_level=0)
    return buf.getvalue()

def draw_png_bytes(c, png_bytes: bytes, x, y, w, h):
    """Каждый вызов — НОВЫЙ BytesIO, иначе ReportLab может читать "середину" буфера."""
    # Проверяем, что PNG байты корректны
    if not png_bytes or len(png_bytes) < 100:
        raise ValueError(f"Invalid PNG bytes: length={len(png_bytes) if png_bytes else 0}")
    
    # Проверяем, что это действительно PNG
    if not png_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError("Not a valid PNG file")
    
    bio = io.BytesIO(png_bytes)
    bio.seek(0)
    c.drawImage(ImageReader(bio), x, y, width=w, height=h, mask='auto')

def make_overlay(page_w, page_h, items):
    """items: [{png_bytes,x,y,w,h}] -> overlay PDF page"""
    packet = io.BytesIO()
    c = rl_canvas.Canvas(packet, pagesize=(page_w, page_h))
    for it in items:
        draw_png_bytes(c, it["png_bytes"], it["x"], it["y"], it["w"], it["h"])
    c.showPage(); c.save(); packet.seek(0)
    return PdfReader(packet).pages[0]

def normalize_rect_visual_to_user(page, x, y, w, h):
    """
    x,y,w,h — в pt от визуального нижнего-левого угла.
    Возвращает координаты в user-space страницы с учётом /Rotate и CropBox.
    Для 90°/270° корректно меняем w↔h.
    """
    pw = float(page.mediabox.width)
    ph = float(page.mediabox.height)
    rot = int(page.get("/Rotate", 0)) % 360

    if rot == 0:
        nx, ny, nw, nh = x, y, w, h
    elif rot == 90:
        nx = y
        ny = pw - (x + w)
        nw, nh = h, w   # swap
    elif rot == 180:
        nx = pw - (x + w)
        ny = ph - (y + h)
        nw, nh = w, h
    elif rot == 270:
        nx = ph - (y + h)
        ny = x
        nw, nh = h, w   # swap
    else:
        nx, ny, nw, nh = x, y, w, h

    # CropBox offset
    crop = page.cropbox
    nx += float(crop.lower_left[0])
    ny += float(crop.lower_left[1])
    return nx, ny, nw, nh

def merge_on_page(page, items):
    """Корректно учитываем CropBox и Rotate без поворота оверлея."""
    pw, ph = float(page.mediabox.width), float(page.mediabox.height)

    # Нормализуем координаты для каждого элемента
    normalized_items = []
    for i, it in enumerate(items):
        nx, ny, nw, nh = normalize_rect_visual_to_user(page, it["x"], it["y"], it["w"], it["h"])
        
        # Защитные бортики: clamp в границы страницы
        nx = max(0.0, min(nx, pw - nw))
        ny = max(0.0, min(ny, ph - nh))
        
        # Проверяем размеры
        if nw <= 0 or nh <= 0 or nw > pw*2 or nh > ph*2:
            raise ValueError(f"Invalid size: {(nw,nh)} for page {(pw,ph)}")
        
        # Логирование для отладки
        logging.info(f"rot= {int(page.get('/Rotate', 0))}, "
              f"in= ({it['x']:.2f}, {it['y']:.2f}, {it['w']:.2f}, {it['h']:.2f}), "
              f"norm= ({nx:.2f}, {ny:.2f}, {nw:.2f}, {nh:.2f}), "
              f"mb= ({pw:.2f}, {ph:.2f}), "
              f"crop= ({float(page.cropbox.lower_left[0]):.2f}, {float(page.cropbox.lower_left[1]):.2f})")
        
        normalized_items.append({
            "png_bytes": it["png_bytes"],
            "x": nx,
            "y": ny,
            "w": nw,
            "h": nh
        })

    # Создаем оверлей с нормализованными координатами
    overlay_page = make_overlay(pw, ph, normalized_items)

    # НЕ поворачиваем оверлей - вся магия в пересчете координат
    page.merge_page(overlay_page)

# Предкеш PNG печатей для производительности (будет инициализирован после определения функций)
SEAL_BYTES_FALCON = None
SEAL_BYTES_FALCON_SIGNATURE = None
SEAL_BYTES_IP = None
SEAL_BYTES_IP_SIGNATURE = None

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024  # 64MB max file size for batch processing
app.config['UPLOAD_FOLDER'] = 'uploads'

# Создаем папку для загрузок если её нет
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Инициализируем кеш печатей при создании приложения (для Gunicorn)
try:
    # Инициализация будет выполнена после определения всех функций
    pass
except Exception as e:
    print(f"Warning: Could not initialize seal cache during app creation: {e}")

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
    c = rl_canvas.Canvas(packet, pagesize=(page_w_pt, page_h_pt))

    for seal in seals_for_page:
        x_pt = float(seal['xPt'])
        y_pt = float(seal['yPt'])
        w_pt = float(seal['wPt'])
        h_pt = float(seal['hPt'])
        opacity = float(seal.get('opacity', 1.0))
        seal_type = seal.get('type', 'falcon')

        # Используем предкешированные PNG байты
        if seal_type == "falcon":
            seal_bytes = SEAL_BYTES_FALCON
        else:  # ip
            seal_bytes = SEAL_BYTES_IP

        # Применяем прозрачность
        if opacity < 0.999:
            # Создаем временное изображение с прозрачностью
            img = Image.open(io.BytesIO(seal_bytes))
            img = _img_with_opacity(img, opacity)
            seal_bytes = pil_to_png_bytes(img)

        # Рисуем с использованием новой функции
        draw_png_bytes(c, seal_bytes, x_pt, y_pt, w_pt, h_pt)

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
    if add_signature:
        img = create_signature_block(seal_type, add_signature)
    else:
        # Для простых печатей используем create_company_seal
        img = create_company_seal(seal_type)
        # Масштабируем до нужного размера
        original_width, original_height = img.size
        max_width = 176
        max_height = 136
        width_ratio = max_width / original_width
        height_ratio = max_height / original_height
        scale_factor = min(width_ratio, height_ratio)
        new_width = int(original_width * scale_factor)
        new_height = int(original_height * scale_factor)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    return pil_to_png_bytes(img)

def initialize_seal_cache():
    """Инициализирует кеш печатей"""
    global SEAL_BYTES_FALCON, SEAL_BYTES_FALCON_SIGNATURE, SEAL_BYTES_IP, SEAL_BYTES_IP_SIGNATURE
    try:
        print("🔄 Initializing seal cache...")
        SEAL_BYTES_FALCON = seal_png_bytes('falcon', False)
        print(f"✅ FALCON seal: {len(SEAL_BYTES_FALCON)} bytes")
        SEAL_BYTES_FALCON_SIGNATURE = seal_png_bytes('falcon', True)
        print(f"✅ FALCON signature: {len(SEAL_BYTES_FALCON_SIGNATURE)} bytes")
        SEAL_BYTES_IP = seal_png_bytes('ip', False)
        print(f"✅ IP seal: {len(SEAL_BYTES_IP)} bytes")
        SEAL_BYTES_IP_SIGNATURE = seal_png_bytes('ip', True)
        print(f"✅ IP signature: {len(SEAL_BYTES_IP_SIGNATURE)} bytes")
        print("🎉 Seal cache initialization completed successfully")
    except Exception as e:
        print(f"❌ Error initializing seal cache: {e}")
        import traceback
        traceback.print_exc()
        raise

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

    # Используем стандартные координаты вместо интеллектуального поиска
    coordinates = get_standard_seal_coordinates(page_width, page_height, seal_type, add_signature)
    
    # Создаем PNG байты печати
    signature_block = create_signature_block(seal_type, add_signature)
    seal_bytes = pil_to_png_bytes(signature_block)

    # Получаем размеры печати из созданного изображения
    signature_width = signature_block.size[0]
    signature_height = signature_block.size[1]

    # Обрабатываем все страницы
    for page_num in range(len(reader.pages)):
        page = reader.pages[page_num]
        
        # Добавляем подпись только на последнюю страницу
        if page_num == len(reader.pages) - 1:
            # Создаем items для merge_on_page
            items = [{
                "png_bytes": seal_bytes,
                "x": coordinates['x'],
                "y": coordinates['y'],
                "w": coordinates['width'],
                "h": coordinates['height']
            }]
            
            # Используем новую функцию для корректной обработки
            merge_on_page(page, items)
        
        writer.add_page(page)

    # Сохраняем результат
    with open(output_pdf_path, 'wb') as output_file:
        writer.write(output_file)

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
            'y': mm(MARGIN_BOTTOM_MM + SHIFT_MM),  # поднимаем на SHIFT_MM
            'w': mm(SIGNATURE_WIDTH_MM * SCALE),    # увеличиваем в SCALE раз
            'h': mm(SIGNATURE_HEIGHT_MM * SCALE)    # увеличиваем в SCALE раз
        }
        
        seal = {
            'x': signature['x'] + signature['w'] + mm(GAP_MM),
            'y': signature['y'],
            'w': mm(SEAL_WIDTH_MM * SCALE),         # увеличиваем в SCALE раз
            'h': mm(SEAL_HEIGHT_MM * SCALE)         # увеличиваем в SCALE раз
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
            'y': mm(MARGIN_BOTTOM_MM + SHIFT_MM),   # поднимаем на SHIFT_MM
            'width': mm(SEAL_WIDTH_MM * SCALE),     # увеличиваем в SCALE раз
            'height': mm(SEAL_HEIGHT_MM * SCALE)    # увеличиваем в SCALE раз
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
    
    # Обрабатываем все страницы
    for page_num in range(len(reader.pages)):
        page = reader.pages[page_num]
        
        # Добавляем подпись только на последнюю страницу
        if page_num == len(reader.pages) - 1:
            # Создаем items для merge_on_page
            items = [{
                "png_bytes": seal_bytes,
                "x": coordinates['x'],
                "y": coordinates['y'],
                "w": coordinates['width'],
                "h": coordinates['height']
            }]
            
            # Используем новую функцию для корректной обработки
            merge_on_page(page, items)
        
        writer.add_page(page)
    
    # Сохраняем результат
    with open(output_pdf_path, 'wb') as output_file:
        writer.write(output_file)

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

@app.route('/test-batch')
def test_batch():
    return send_file('test_batch_upload.html')

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
        data = request.get_json(force=True)
        logging.info(f"DEBUG: Получены данные: {len(data.get('seals', []))} печатей")

        if not data or 'pdfData' not in data:
            raise ValueError("Missing pdfData (base64) in request")

        if 'seals' not in data or not isinstance(data['seals'], list):
            raise ValueError("Missing or invalid 'seals' array")

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
            raise ValueError("Неверный формат данных PDF")

        # Создаем временный файл для исходного PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
            temp_pdf.write(pdf_data)
            temp_pdf_path = temp_pdf.name

        # Создаем временный файл для результата
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_result:
            result_path = temp_result.name

        try:
            # Проверяем инициализацию кеша печатей
            if SEAL_BYTES_FALCON is None or SEAL_BYTES_IP is None:
                logging.info("Кеш печатей не инициализирован, инициализируем...")
                initialize_seal_cache()
                # Дополнительная проверка после инициализации
                if SEAL_BYTES_FALCON is None or SEAL_BYTES_IP is None:
                    raise ValueError("Failed to initialize seal cache")
                logging.info(f"Кеш инициализирован: FALCON={len(SEAL_BYTES_FALCON)} байт, IP={len(SEAL_BYTES_IP)} байт")
            
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
                    # Используем новую систему координат
                    items = []
                    for seal in seals_by_page[i]:
                        # Валидация координат
                        required_keys = ['xPt', 'yPt', 'wPt', 'hPt']
                        if not all(key in seal and isinstance(seal[key], (int, float)) for key in required_keys):
                            raise ValueError(f"Invalid seal coordinates: {seal}")
                        
                        # Выбираем правильные PNG байты
                        seal_type = seal.get('type', 'falcon')
                        if seal_type == 'falcon':
                            png_bytes = SEAL_BYTES_FALCON
                        else:  # ip
                            png_bytes = SEAL_BYTES_IP
                        
                        # Проверяем, что PNG байты корректны
                        if not png_bytes or len(png_bytes) < 100:
                            raise ValueError(f"Invalid PNG bytes for seal type: {seal_type}")
                        
                        # Конвертируем координаты из редактора в новый формат
                        items.append({
                            "png_bytes": png_bytes,
                            "x": float(seal['xPt']),
                            "y": float(seal['yPt']),
                            "w": float(seal['wPt']),
                            "h": float(seal['hPt'])
                        })
                    
                    # Используем новую функцию merge_on_page
                    merge_on_page(page, items)
                writer.add_page(page)

            # Сохраняем результат
            with open(result_path, 'wb') as output_file:
                writer.write(output_file)

            # Проверяем размер файла
            file_size = os.path.getsize(result_path)
            logging.info(f"DEBUG: Размер созданного PDF: {file_size} байт")

            if file_size == 0:
                raise ValueError("Создан пустой PDF файл")

            # Читаем результат и отправляем
            with open(result_path, 'rb') as f:
                result_data = f.read()

            # Кодируем в base64 для отправки
            result_base64 = base64.b64encode(result_data).decode('utf-8')
            logging.info(f"DEBUG: Размер base64 данных: {len(result_base64)} символов")

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
        logging.exception("save_document failed")
        return jsonify({
            'success': False,
            'error': f'{e}',
            'trace': traceback.format_exc()[:4000]  # чтобы увидеть корень
        }), 400

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

# Инициализируем кеш печатей после определения всех функций
def init_seal_cache():
    try:
        initialize_seal_cache()
        print("✅ Seal cache initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize seal cache: {e}")

# Вызываем инициализацию
init_seal_cache()

@app.route('/batch-stamp', methods=['POST'])
def batch_stamp():
    """Обработка файлов через FormData с ключом 'files' - отдаем поштучно в JSON"""
    try:
        files = request.files.getlist("files")  # КЛЮЧ 'files'
        
        if not files:
            return jsonify({'error': 'Файлы не найдены'}), 400
        
        # Получаем конфигурацию
        config_str = request.form.get('config', '{}')
        try:
            config = json.loads(config_str)
        except json.JSONDecodeError:
            config = {}
        
        # Параметры обработки с дефолтами
        x_mm = float(config.get('x', 17.6))
        y_mm = float(config.get('y', 67.6))
        w_mm = float(config.get('width', 46.4))
        h_mm = float(config.get('height', 35.9))
        opacity = float(config.get('opacity', 0.95))
        
        items = []
        
        for file in files:
            try:
                # Проверяем тип файла
                if not file.filename.lower().endswith('.pdf'):
                    items.append({
                        'filename': file.filename,
                        'ok': False,
                        'error': 'Не PDF файл'
                    })
                    continue
                
                # Читаем файл в байты
                pdf_bytes = file.read()
                
                # Создаем временные файлы
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_input:
                    temp_input.write(pdf_bytes)
                    input_path = temp_input.name
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_output:
                    output_path = temp_output.name
                
                try:
                    # Обрабатываем файл с нашими координатами
                    coordinates = {
                        'x': mm(x_mm),
                        'y': mm(y_mm),
                        'width': mm(w_mm),
                        'height': mm(h_mm)
                    }
                    
                    add_signature_to_pdf_batch(input_path, output_path, 'falcon', False, coordinates)
                    
                    # Читаем результат
                    with open(output_path, 'rb') as f:
                        stamped_bytes = f.read()
                    
                    # Создаем data URL
                    data_url = "data:application/pdf;base64," + base64.b64encode(stamped_bytes).decode("utf-8")
                    
                    # Санитизируем имя файла
                    name = secure_filename(Path(file.filename).stem) or "document"
                    out_name = f"{name}_stamped.pdf"
                    
                    items.append({
                        'filename': out_name,
                        'ok': True,
                        'pdfData': data_url,
                        'size': len(stamped_bytes)
                    })
                    
                finally:
                    # Удаляем временные файлы
                    if os.path.exists(input_path):
                        os.unlink(input_path)
                    if os.path.exists(output_path):
                        os.unlink(output_path)
                        
            except Exception as e:
                logging.exception(f"Error processing {file.filename}")
                items.append({
                    'filename': file.filename,
                    'ok': False,
                    'error': str(e)
                })
        
        return jsonify({
            "success": True, 
            "items": items, 
            "count": len(items), 
            "ts": int(time.time())
        })
        
    except Exception as e:
        logging.exception("batch_stamp failed")
        return jsonify({'error': f'Ошибка при обработке: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080))) 