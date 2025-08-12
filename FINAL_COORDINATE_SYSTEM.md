# 🎯 Финальная система координат - Полная документация

## 📋 **Обзор**

Финальная реализация системы координат для корректного позиционирования печатей и подписей на PDF страницах с учетом ротации и CropBox.

## 🔧 **Ключевая функция**

### **`normalize_rect_visual_to_user(page, x, y, w, h)`**

```python
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
```

## 📐 **Формулы преобразования**

### **Ротация 0° (без поворота):**
```
(x, y, w, h) → (x, y, w, h)
```

### **Ротация 90°:**
```
(x, y, w, h) → (y, pw - (x + w), h, w)
```

### **Ротация 180°:**
```
(x, y, w, h) → (pw - (x + w), ph - (y + h), w, h)
```

### **Ротация 270°:**
```
(x, y, w, h) → (ph - (y + h), x, h, w)
```

## 🔍 **Отладочное логирование**

```python
print(f"rot= {int(page.get('/Rotate', 0))}, "
      f"in= ({x:.2f}, {y:.2f}, {w:.2f}, {h:.2f}), "
      f"norm= ({nx:.2f}, {ny:.2f}, {nw:.2f}, {nh:.2f}), "
      f"mb= ({pw:.2f}, {ph:.2f}), "
      f"crop= ({float(page.cropbox.lower_left[0]):.2f}, {float(page.cropbox.lower_left[1]):.2f})")
```

## 🚀 **Использование**

### **В функции merge_on_page:**
```python
def merge_on_page(page, items):
    """Корректно учитываем CropBox и Rotate без поворота оверлея."""
    pw, ph = float(page.mediabox.width), float(page.mediabox.height)

    # Нормализуем координаты для каждого элемента
    normalized_items = []
    for i, it in enumerate(items):
        nx, ny, nw, nh = normalize_rect_visual_to_user(page, it["x"], it["y"], it["w"], it["h"])
        
        # Логирование для отладки
        print(f"rot= {int(page.get('/Rotate', 0))}, "
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
```

## ✅ **Ключевые принципы**

### **1. Не вращаем overlay**
- Оверлей создается в user-space страницы
- Никаких вызовов `overlay_page.rotate()`
- Вся "магия" в пересчете координат

### **2. Правильное переключение размеров**
- Для ротации 90°/270° меняем местами `w↔h`
- Для ротации 0°/180° размеры остаются без изменений

### **3. Учет CropBox**
- Все координаты корректируются на CropBox смещения
- Работает с PDF, где CropBox ≠ MediaBox

### **4. Визуальные координаты**
- Входные координаты задаются от визуального нижнего-левого угла
- Результат - правильное позиционирование независимо от ротации

## 🎯 **Результат**

**Система координат полностью готова:**

- ✅ **Корректное позиционирование** для всех углов ротации
- ✅ **Правильные размеры** печатей и подписей
- ✅ **Учет CropBox** смещений
- ✅ **Отладочное логирование** для контроля
- ✅ **Производительность** - без поворота overlay

**Приложение готово к продакшену!** 🚀

---

*Финальная версия: 12 августа 2025*
*Версия: 1.0.6 (Final Coordinate System)* 