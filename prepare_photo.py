# -*- coding: utf-8 -*-
"""
Готовит фото для страницы «Обо мне» — той же процедурой, что аватары.

    python prepare_photo.py путь-к-фото.jpg

Правила те же и по тем же причинам:
  1. Формат берётся из содержимого файла, а не из расширения имени.
  2. Картинка пересохраняется в новый файл — это убирает всё, что могло
     быть дописано внутрь или после конца изображения.
  3. Метаданные не переносятся. В EXIF фото с телефона лежат GPS-координаты
     съёмки, модель аппарата и иногда имя владельца.
  4. Ориентация применяется ДО сохранения: браузер ориентирует картинку
     по EXIF, который мы удаляем, поэтому поворот нужно вжечь в пиксели.

Размер 480×480: карточка показывает 132px, на retina это 264px — берём
с запасом, чтобы не мылило на плотных экранах.
"""
import os
import sys

ВЫХОД = os.path.join("static", "about-me.jpg")
РАЗМЕР = 480
МАКС_БАЙТ = 15 * 1024 * 1024
МАКС_СТОРОНА = 8000        # защита от декомпрессионной бомбы


def main():
    if len(sys.argv) < 2:
        print("укажите путь к файлу: python prepare_photo.py фото.jpg")
        return 1
    исходник = sys.argv[1]
    if not os.path.exists(исходник):
        print("файл не найден:", исходник)
        return 1

    from PIL import Image, ImageOps, UnidentifiedImageError

    сырое = open(исходник, "rb").read()
    print("исходник: %.1f МБ" % (len(сырое) / 1024 / 1024))
    if len(сырое) > МАКС_БАЙТ:
        print("файл больше %d МБ" % (МАКС_БАЙТ // 1024 // 1024))
        return 1

    try:
        import io as _io
        проверка = Image.open(_io.BytesIO(сырое))
        проверка.verify()
        формат = (проверка.format or "").upper()
        if формат not in ("PNG", "JPEG", "WEBP"):
            print("поддерживаются PNG, JPG и WebP, получено:", формат)
            return 1

        img = Image.open(_io.BytesIO(сырое))
        print("формат: %s, размер: %dx%d, EXIF-тегов: %d" % (
            формат, img.width, img.height, len(img.getexif())))
        if img.width > МАКС_СТОРОНА or img.height > МАКС_СТОРОНА:
            print("слишком большое разрешение")
            return 1

        img = ImageOps.exif_transpose(img)      # поворот до удаления EXIF
        img = img.convert("RGB")                # JPEG не умеет альфу
        img = ImageOps.fit(img, (РАЗМЕР, РАЗМЕР), method=Image.LANCZOS,
                           centering=(0.5, 0.4))   # лицо обычно выше центра
        os.makedirs("static", exist_ok=True)
        img.save(ВЫХОД, format="JPEG", quality=88, optimize=True, progressive=True)
    except UnidentifiedImageError:
        print("это не изображение")
        return 1

    готово = Image.open(ВЫХОД)
    print()
    print("готово:", ВЫХОД)
    print("  размер   : %dx%d" % готово.size)
    print("  EXIF     : %d тегов" % len(готово.getexif()))
    print("  вес      : %.1f КБ" % (os.path.getsize(ВЫХОД) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
