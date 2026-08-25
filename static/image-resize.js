/* УМЕНЬШЕНИЕ ФОТО ПЕРЕД ОТПРАВКОЙ — системный компонент.
 *
 * Потребителей два: разбор фото еды в дневнике питания и ассистент
 * заведения в аптечке. До 2026-08-25 функция лежала ИНЛАЙНОМ
 * в `templates/nutrition.html` при одном потребителе, и копия для
 * аптечки стала бы ровно тем дублем, против которого заведена
 * задача 126. Та же история и то же лекарство, что у `voice-input.js`.
 *
 * ЗАЧЕМ ВООБЩЕ. Снимок с телефона — это 12–108 Мпикс и до десятка
 * мегабайт. Отправить его как есть значит три беды сразу:
 *   1. долгая выгрузка по мобильной сети — на неё человек и смотрит,
 *      пока ничего не происходит;
 *   2. сервер раскрывает кадр в память целиком, а у машины 256 МБ
 *      (`fly.toml`). Замер 2026-08-25: 50 Мпикс просят +383 МБ.
 *      На Linux это OOM-kill, то есть ответа нет вовсе и человек
 *      получает 502 от прокси;
 *   3. картинка сверх 5 МБ — гарантированный отказ сервиса моделей.
 *
 * ФОРМАТ, КОТОРЫЙ БРАУЗЕР НЕ ОТКРЫЛ, УХОДИТ КАК ЕСТЬ. Это не оплошность:
 * HEIC с айфона браузер не рисует, а модель читает. Отказ здесь был бы
 * хуже отправки оригинала — но он ТЕПЕРЬ НАЗЫВАЕТСЯ ВСЛУХ (поле
 * `какОригинал`), иначе «уменьшили» и «не смогли уменьшить» выглядят
 * одинаково, а весят по-разному (§6.0.1).
 */
function уменьшитьФото(файл, maxDim = 1280, quality = 0.82) {
  return new Promise((resolve) => {
    const было = файл.size;
    const отдать = (blob, dataUrl, какОригинал) => resolve({
      blob: blob || файл, dataUrl: dataUrl || null,
      какОригинал: !!какОригинал, былоБайт: было,
      сталоБайт: (blob || файл).size,
    });
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        let { width, height } = img;
        if (width > maxDim || height > maxDim) {
          if (width > height) { height = Math.round(height * maxDim / width); width = maxDim; }
          else { width = Math.round(width * maxDim / height); height = maxDim; }
        }
        const canvas = document.createElement('canvas');
        canvas.width = width; canvas.height = height;
        canvas.getContext('2d').drawImage(img, 0, 0, width, height);
        canvas.toBlob(blob => отдать(blob, canvas.toDataURL('image/jpeg', quality), !blob),
                      'image/jpeg', quality);
      };
      /* Формат браузеру незнаком (HEIC) — отправляем как есть */
      img.onerror = () => отдать(файл, null, true);
      img.src = reader.result;
    };
    reader.onerror = () => отдать(файл, null, true);
    reader.readAsDataURL(файл);
  });
}

/* Имя, под которым функция жила в дневнике. Оставлено, чтобы вызов
   на той стороне не переписывался вторым способом делать то же самое. */
const resizeImage = уменьшитьФото;
