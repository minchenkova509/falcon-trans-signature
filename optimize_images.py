#!/usr/bin/env python3
"""
Скрипт для оптимизации изображений печатей
Уменьшает размер файлов для лучшей загрузки на Render
"""

from PIL import Image
import os

def optimize_image(input_path, output_path, max_size=(300, 300), quality=85):
    """Оптимизирует изображение"""
    try:
        with Image.open(input_path) as img:
            # Конвертируем в RGBA если нужно
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # Изменяем размер если изображение слишком большое
            if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Сохраняем с оптимизацией
            img.save(output_path, 'PNG', optimize=True, compress_level=9)
            
            # Получаем размер файла
            file_size = os.path.getsize(output_path)
            print(f"✓ {os.path.basename(input_path)} -> {os.path.basename(output_path)} ({file_size/1024:.1f}KB)")
            
    except Exception as e:
        print(f"✗ Ошибка при оптимизации {input_path}: {e}")

def main():
    """Основная функция"""
    print("🔧 Оптимизация изображений печатей...")
    
    # Создаем папку для оптимизированных изображений
    optimized_dir = "static/images/optimized"
    os.makedirs(optimized_dir, exist_ok=True)
    
    # Список файлов для оптимизации
    images = [
        ("falcon_seal.png", (200, 200)),
        ("falcon_signature.png", (150, 100)),
        ("ip_seal.png", (200, 200)),
        ("ip_signature.png", (150, 100)),
        ("ip_seal_signature.png", (250, 200))
    ]
    
    for filename, max_size in images:
        input_path = f"static/images/{filename}"
        output_path = f"{optimized_dir}/{filename}"
        
        if os.path.exists(input_path):
            optimize_image(input_path, output_path, max_size)
        else:
            print(f"⚠️ Файл не найден: {input_path}")
    
    print("\n✅ Оптимизация завершена!")
    print(f"📁 Оптимизированные файлы сохранены в: {optimized_dir}")

if __name__ == "__main__":
    main() 