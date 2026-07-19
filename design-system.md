# design-system.md — energydess.ru

> **Единственный источник правды по визуалу.** Заменяет собой `SYSTEM.md` и все дизайн-упоминания в других MD-файлах. Если где-то в коде или комментариях встречаются правила, противоречащие этому файлу — они legacy и подлежат удалению.
>
> **Как читать:** сначала «Философия и принципы» — они объясняют «почему». Затем токены и правила — они «как». Потом компоненты и per-tool identity — «где применять».

---

## 0. Философия и принципы

**Позиционирование:** премиальный SaaS-инструментарий 2026. Референсы направления — Linear, Vercel, Raycast, Штруцель. Ощущение — сдержанная уверенность, «инструмент профессионала», а не «домашний проект с эффектами».

**Пять принципов, из которых выводится всё остальное:**

1. **Тёмный — не значит чёрный.** Плоский `#000` читается как «мы не подумали». Наш фон — двухслойный нейтральный с ощутимой (но не крикливой) разницей между уровнями. Глубина возникает из этой лесенки, а не из градиентов.
2. **Типографика — герой сцены.** Крупные, жирные, чистые заголовки. Никаких градиентных заливок букв, никаких decorative-шрифтов с «характером». Читаемость важнее выразительности.
3. **Цветовая дисциплина.** База — нейтральная. Акцент — один на инструмент, применяется в 3-7% пикселей интерфейса. Всё, что цветное без причины — визуальный шум.
4. **Движение — микро, не макро.** Никаких плавающих блобов, интерактивных частиц, аврор-эффектов. Только тонкие ambient-эффекты на лендинге и осмысленные микроинтеракции (ховеры, появление секций).
5. **Один signature-элемент.** Вся «дерзость» тратится в одной точке — на бегущей обводке secondary-CTA. Всё остальное — тишина.

**Что мы НЕ делаем (список запретов):**

- ❌ Aurora blobs, плавающие блобы, интерактивные частицы за мышкой
- ❌ Градиентные заливки заголовков (`background-clip: text` с цветным градиентом)
- ❌ Градиентные кнопки (`linear-gradient` как fill CTA)
- ❌ Эмодзи как иконки UI-элементов (💪 🥗 🎮 📝 в шапках карточек, метках, категориях)
- ❌ Разноцветные метки категорий (розовый КАРЬЕРА + жёлтый ФИТНЕС + голубой ПИТАНИЕ)
- ❌ Decorative-шрифты с характером (Syne, Playfair, Fraunces) для UI
- ❌ Микроскопический вторичный текст, невидимая навигация, «исчезающая» шапка при скролле
- ❌ Радужные подсветки, неоновые свечения (кроме одного тонкого glow на H1)
- ❌ Переключатель светлой/тёмной темы (до отдельного решения)

---

## 1. Токены — базовые

### 1.1. Поверхности (лесенка)

```css
:root {
  /* Фоновая лесенка — шаги ощутимы глазом */
  --surface-0: #0A0B0D;   /* фон страницы (база) */
  --surface-1: #141520;   /* карточки, панели */
  --surface-2: #1E2030;   /* вложенные блоки: инпуты, textarea, под-карточки */
  --surface-3: #2A2C45;   /* активные/выделенные вложенные элементы */

  /* Границы — обязательны на карточках */
  --border:        rgba(255,255,255,0.08);   /* стандартная граница */
  --border-strong: rgba(255,255,255,0.14);   /* hover, акцентные блоки */
  --border-hairline: rgba(255,255,255,0.06); /* разделители секций */
}
```

**Железные правила:**
- Любая `.card` — фон `--surface-1` + `border: 1px solid var(--border)`.
- Инпут/textarea/под-блок внутри карточки — фон `--surface-2`.
- Активный/выделенный элемент — `--surface-3` или акцентная рамка.
- Никогда два соседних по вложенности элемента в один и тот же `--surface-*`.

### 1.2. Текст

```css
:root {
  --font:      'Manrope', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'JetBrains Mono', 'DM Mono', monospace;

  --text:       #E8ECF8;   /* основной */
  --text-2:     #AEB8D4;   /* вторичный — ЕДИНЫЙ токен */
  --text-faint: #7A83A0;   /* приглушённый, используется редко */
  --text-strong: #FFFFFF;  /* максимальный контраст, для H1 hero */
}
```

**Правила:**
- Один шрифт для всего UI — **Manrope**. `Syne` удаляется.
- `JetBrains Mono` — для меток, кода, чисел (обзоры данных).
- Вторичный текст — только `--text-2`. Хардкод-серые (`#c7d3ea`, `#81899b`, `#5a6888`) удалить из всех шаблонов.
- Минимальный `font-weight` — **400**. Веса 300 и тоньше запрещены.
- Заголовки — **600-800**.

### 1.3. Типографическая шкала

```css
:root {
  /* Все размеры в rem/clamp, никаких px для текста */
  --text-display: clamp(2.5rem, 5vw, 4.5rem);   /* H1 hero (40→72px), weight 800 */
  --text-h1:      clamp(1.75rem, 4vw, 3rem);    /* H1 обычный (28→48px), weight 700 */
  --text-h2:      clamp(1.375rem, 3vw, 2rem);   /* H2 (22→32px), weight 700 */
  --text-h3:      clamp(1.125rem, 2vw, 1.5rem); /* H3 (18→24px), weight 600 */
  --text-body-lg: 1.0625rem;                    /* 17px — крупный body, weight 400 */
  --text-body:    1rem;                         /* 16px — стандартный body, weight 400 */
  --text-body-sm: 0.9375rem;                    /* 15px — вторичный body, weight 400 */
  --text-nav:     0.9375rem;                    /* 15px — навигация, weight 500 */
  --text-caption: 0.8125rem;                    /* 13px — метки, weight 500 */
  --text-mono:    0.75rem;                      /* 12px — uppercase mono-labels, weight 500, tracking +0.1em */
}
```

**Правила:**
- Hero-заголовок H1 (главная страница) получает `--text-strong` (белый) + тонкий glow: `text-shadow: 0 0 40px rgba(255,255,255,0.15);`
- Никаких градиентных заливок текста (`background-clip: text` с color-gradient).
- Uppercase mono-labels (типа `PERSONAL AI TOOLS`) — `--font-mono`, tracking `+0.1em`, `--text-2` или акцент.
- Line-height: заголовки — `1.1`, body — `1.6`, caption — `1.4`.

### 1.4. Акценты (per-tool identity)

```css
:root {
  /* Универсальный акцент — используется на лендинге и в общих CTA */
  --accent-brand: #4F8FFF;      /* electric blue, primary CTA */
  --accent-brand-hover: #6BA0FF;
  --accent-brand-dim: rgba(79,143,255,0.15); /* фон акцентных чипов */

  /* Инструменты — каждый со своим акцентом */
  --accent-hh:         #4F8FFF;  /* HH-ассистент: electric blue */
  --accent-hh-dim:     rgba(79,143,255,0.15);
  --accent-nutrition:  #10B981;  /* Дневник питания: emerald */
  --accent-nutrition-dim: rgba(16,185,129,0.15);
  --accent-workout:    #F59E0B;  /* Программа тренировок: amber */
  --accent-workout-dim: rgba(245,158,11,0.15);
  --accent-enshrouded: #D97706;  /* Enshrouded: copper */
  --accent-enshrouded-dim: rgba(217,119,6,0.15);

  /* Семантические */
  --success: #10B981;
  --warning: #F59E0B;
  --error:   #EF4444;
}
```

**Правило акцентного контроля:** акцент применяется ТОЛЬКО в этих местах:
1. Primary CTA-кнопка внутри инструмента
2. Иконка инструмента в шапке карточки/страницы
3. Активная вкладка в под-навигации
4. Progress-indicators, графики, круг калорий
5. Focus-ring на активном инпуте

Всё остальное — нейтральная база.

### 1.5. Радиусы

```css
:root {
  --radius-sm:  8px;   /* кнопки, инпуты, чипы */
  --radius-md:  12px;  /* small cards, dropdowns */
  --radius-lg:  16px;  /* стандартные карточки */
  --radius-xl:  24px;  /* модалки, hero-блоки */
}
```

### 1.6. Тени

```css
:root {
  --shadow-sm:  0 1px 2px rgba(0,0,0,0.3);
  --shadow-md:  0 4px 12px rgba(0,0,0,0.4);
  --shadow-lg:  0 12px 32px rgba(0,0,0,0.5);
  --shadow-glow-brand: 0 0 24px rgba(79,143,255,0.25);
}
```

**Правила:**
- Карточка в покое — `--shadow-sm` или без тени.
- Карточка на hover — `--shadow-md`.
- Модалка, dropdown, всплывающие меню — `--shadow-lg`.
- Focused-элементы (только CTA hero-секции) — `--shadow-glow-brand`.

### 1.7. Отступы (шкала)

```css
:root {
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 48px;
  --space-8: 72px;
  --space-9: 96px;
  --space-10: 128px;
}
```

**Правила:**
- Отступ между секциями страницы (desktop) — `--space-9` (96px) или `--space-10` (128px).
- Отступ между секциями (mobile) — `--space-7` (48px).
- Внутри карточки padding — `--space-5` (24px) или `--space-6` (32px).
- Gap в grid/flex — из шкалы. Никаких `gap: 20px` в inline-стилях.

### 1.8. Motion

```css
:root {
  --ease:       cubic-bezier(0.4, 0, 0.2, 1);
  --ease-out:   cubic-bezier(0, 0, 0.2, 1);
  --dur-fast:   150ms;   /* микро — ховеры кнопок */
  --dur-base:   200ms;   /* стандарт — большинство транзиций */
  --dur-slow:   400ms;   /* появление секций при скролле */
}
```

**Правила:**
- Все `transition` — только через переменные, единый easing.
- Ховер карточки: граница → `--border-strong`, `translateY(-2px)`, тень → `--shadow-md`.
- Ховер CTA-кнопки: `scale(1.02)`, лёгкое затемнение цвета акцента.
- Появление секций при скролле: fade + `translateY(20px → 0)`, длительность `--dur-slow`.
- Respect `prefers-reduced-motion: reduce` — все анимации отключаются.

---

## 2. Компонентная база

### 2.1. Buttons

**Primary CTA:**
```css
.btn-primary {
  background: var(--accent-brand);
  color: white;
  font-weight: 600;
  font-size: var(--text-body);
  padding: var(--space-3) var(--space-5);
  border-radius: var(--radius-sm);
  border: none;
  cursor: pointer;
  transition: transform var(--dur-fast) var(--ease), background var(--dur-fast) var(--ease);
}
.btn-primary:hover {
  background: var(--accent-brand-hover);
  transform: scale(1.02);
}
```

**Secondary (outline):**
```css
.btn-secondary {
  background: transparent;
  color: var(--text);
  border: 1px solid var(--border-strong);
  padding: var(--space-3) var(--space-5);
  border-radius: var(--radius-sm);
  transition: border-color var(--dur-fast) var(--ease), background var(--dur-fast) var(--ease);
}
.btn-secondary:hover {
  border-color: var(--accent-brand);
  background: var(--accent-brand-dim);
}
```

**Ghost/text:**
```css
.btn-ghost {
  background: transparent;
  color: var(--text-2);
  border: none;
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
}
.btn-ghost:hover {
  color: var(--text);
}
```

**Signature — running-border button (см. раздел 3).**

### 2.2. Cards

```css
.card {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  transition: border-color var(--dur-base) var(--ease),
              transform var(--dur-base) var(--ease),
              box-shadow var(--dur-base) var(--ease);
}
.card:hover {
  border-color: var(--border-strong);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}
```

Вложенные под-блоки в карточке (инпуты, поля досье) — `background: var(--surface-2)`.

### 2.3. Inputs

```css
.input, .textarea, .select {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: var(--space-3) var(--space-4);
  color: var(--text);
  font-family: var(--font);
  font-size: var(--text-body);
  transition: border-color var(--dur-fast) var(--ease), box-shadow var(--dur-fast) var(--ease);
}
.input:focus, .textarea:focus, .select:focus {
  outline: none;
  border-color: var(--accent-brand);
  box-shadow: 0 0 0 3px var(--accent-brand-dim);
}
.input::placeholder {
  color: var(--text-faint);
}
```

Внутри инструмента — заменить `--accent-brand` на акцент инструмента.

### 2.4. Chips / labels

```css
.chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-3);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-2);
  font-size: var(--text-caption);
  font-weight: 500;
}
.chip.active {
  background: var(--accent-brand-dim);
  color: var(--accent-brand);
  border-color: var(--accent-brand);
}
```

Uppercase-метка секций (типа `PERSONAL AI TOOLS`):
```css
.eyebrow {
  font-family: var(--font-mono);
  font-size: var(--text-mono);
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-2);
}
```

### 2.5. Modals

```css
.modal-backdrop {
  position: fixed; inset: 0;
  background: rgba(6, 7, 13, 0.7);
  backdrop-filter: blur(8px);
  z-index: 100;
}
.modal {
  background: var(--surface-1);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-xl);
  padding: var(--space-6);
  box-shadow: var(--shadow-lg);
  max-width: 480px;
  margin: 10vh auto;
}
```

### 2.6. Section dividers

```css
.divider {
  height: 1px;
  background: var(--border-hairline);
  border: none;
  margin: var(--space-8) 0;
}
```

Между секциями лендинга — тонкие hairline-линии. Никаких градиентных плавных переходов фона.

---

## 3. Signature element — running-border button

**Единственная фишка, которая делает сайт узнаваемым.** Применяется к secondary/tertiary CTA («Уже есть аккаунт», «Узнать больше», «Meet Glaze»-style ссылки). НЕ применяется к primary CTA (там достаточно сплошной заливки).

Механика: тонкая обводка 1px, вокруг которой бежит короткая светящаяся точка/дуга. Цикл 3-4 секунды, easing linear (равномерно). Реализация через SVG с `stroke-dasharray` + анимация `stroke-dashoffset`.

**HTML:**
```html
<a href="/login" class="btn-signature">
  <svg class="signature-border" preserveAspectRatio="none">
    <rect x="0.5" y="0.5" width="calc(100% - 1px)" height="calc(100% - 1px)" rx="8" ry="8"/>
  </svg>
  <span>Уже есть аккаунт</span>
</a>
```

**CSS:**
```css
.btn-signature {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-5);
  color: var(--text);
  font-weight: 500;
  text-decoration: none;
  border-radius: var(--radius-sm);
  isolation: isolate;
}

.signature-border {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
  z-index: -1;
  overflow: visible;
}

.signature-border rect {
  fill: transparent;
  stroke: var(--accent-brand);
  stroke-width: 1;
  stroke-opacity: 0.4;
  stroke-dasharray: 40 1000;  /* короткий отрезок + длинный «невидимый» */
  stroke-dashoffset: 0;
  animation: run-border 4s linear infinite;
  filter: drop-shadow(0 0 4px var(--accent-brand));
}

@keyframes run-border {
  to { stroke-dashoffset: -1040; }  /* полный периметр примерно 1040 при бордере среднего размера */
}

@media (prefers-reduced-motion: reduce) {
  .signature-border rect { animation: none; }
}
```

**Примечание для реализации:** точная длина `stroke-dasharray` зависит от периметра конкретной кнопки. Fable — вычисли периметр программно через JS (`getTotalLength()`) при инициализации каждой такой кнопки, или задай через CSS-переменную на элементе. Не хардкодь 1040.

**Правила использования:**
- НЕ применять к primary CTA внутри инструментов (там достаточно заливки).
- НЕ применять к более чем 2-3 кнопкам на одной странице (перестанет быть signature).
- Применять на: hero-secondary CTA лендинга, «Узнать больше» карточек инструментов, key-links в футере.

---

## 4. Sticky-навигация

**Верхняя шапка ВСЕГДА прикреплена при скролле.** Никакой «исчезающей» шапки.

```css
.site-header {
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(10, 11, 13, 0.7);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-bottom: 1px solid var(--border-hairline);
  height: 64px;
  display: flex;
  align-items: center;
  padding: 0 var(--space-6);
}
```

**Структура шапки (desktop):**
```
[Logo]              [Global search: «Найти инструмент, письмо, продукт...»]              [Avatar ▼]
```

- **Логотип** слева. Клик → главная (лендинг для неавторизованных, dashboard для авторизованных).
- **Глобальный поиск** в центре, ширина 40-50% шапки. Placeholder меняется контекстно.
- **Аватар справа** — кругляшка 32×32 с инициалами на цветном фоне (`--accent-brand-dim`) или загруженным фото. Клик → dropdown:
  - Профиль
  - Настройки (если появятся)
  - Админ (только для admin)
  - Выйти

**Mobile:**
- Логотип + иконка поиска + аватар. Поиск разворачивается в полноширинный оверлей при клике.

**НЕ используем:** горизонтальные ссылки «Главная / Профиль / Админ / Выйти» вразнобой в шапке. Всё уходит в аватар-дропдаун. Это освобождает шапку и делает её премиальной.

---

## 5. Глобальный поиск

Placeholder: `«Найти инструмент, письмо, продукт или упражнение…»`

Ищет по индексу:
- Названия инструментов (быстрый переход)
- Сохранённые письма (по компании, названию вакансии)
- Продукты в базе питания (пользовательские)
- Упражнения из базы (по названию мышцы)

Технически: сначала клиентский поиск (Fuse.js по in-memory индексу), для больших сущностей — API-endpoint `/api/search?q=...`. Реализация — отдельная задача, но UI-хук должен быть заложен в шапку сразу.

Результаты выводятся в dropdown под инпутом:
```
[инструменты] HH-ассистент
[письма]      Riseon — Senior AI Video Creator
[продукты]    Йогурт крем-чиз соленая карамель
```

Первая колонка — тег категории, `--text-caption` uppercase mono, цвет `--text-2`.

---

## 6. Полноценный футер

По образцу Linear. На каждой странице (кроме auth-страниц и модалок).

```
[Logo]     Продукт           Инструменты        Ресурсы           Связаться
           Главная            HH-ассистент       Документация      Telegram
           О проекте          Дневник питания    Changelog         Email
           Тарифы             Тренировки         Статус            GitHub
           Roadmap            Enshrouded         Блог              
           Приватность

──────────────────────────────────────────────────────────────────────────
© 2026 EnergyDess               Made with intent in Balashikha, MO
```

Стили:
- Фон `--surface-0` (тот же что body — визуально сливается с концом контента).
- Разделитель сверху: hairline 1px.
- Padding сверху `--space-9`, снизу `--space-6`.
- Ссылки: `--text-2`, hover → `--text`, transition `--dur-fast`.

---

## 7. Per-tool identity

### 7.1. Общее правило

Каждый инструмент имеет:
- **Один акцентный цвет** (из блока `1.4`)
- **Одну иконку** в шапке страницы (Lucide, `stroke-width: 1.5`, размер 24px, цвет = акцент инструмента)
- **Один mono-label** над заголовком (uppercase mono, цвет = акцент)

Всё остальное — общая база.

### 7.2. HH-ассистент

- **Акцент:** `--accent-hh` (#4F8FFF electric blue)
- **Иконка:** Lucide `Briefcase`
- **Mono-label:** `КАРЬЕРА`
- **Mood:** «профессиональный кабинет». Строго, ясно, минимум визуальных отвлечений.
- **Класс темы на body:** `.theme-hh`

### 7.3. Дневник питания

- **Акцент:** `--accent-nutrition` (#10B981 emerald)
- **Иконка:** Lucide `Salad`
- **Mono-label:** `ПИТАНИЕ`
- **Mood:** «журнал здоровья». Чистый, аккуратный, без «фитнес-неона».
- **Класс темы:** `.theme-nutrition`

### 7.4. Программа тренировок

- **Акцент:** `--accent-workout` (#F59E0B amber)
- **Иконка:** Lucide `Dumbbell`
- **Mono-label:** `ТРЕНИРОВКИ`
- **Mood:** «прогресс без хайпа». Энергия через акцент, но никаких огня и молний.
- **Класс темы:** `.theme-workout`

### 7.5. Enshrouded

- **Акцент:** `--accent-enshrouded` (#D97706 copper/ember)
- **Иконка:** Lucide `Shield`
- **Mono-label:** `ИГРЫ · ENSHROUDED`
- **Mood:** «атмосфера туманов». Тёплый янтарь на холодной базе. Без летающих огоньков.
- **Класс темы:** `.theme-enshrouded`
- **Особое:** карточки сетов получают мягкое `--shadow-glow` с акцентным цветом при hover — это единственное место, где мы допускаем glow вокруг карточек.

### 7.6. Механика тем

```css
/* Общая механика (все токены) живёт в :root */

.theme-hh {
  --tool-accent: var(--accent-hh);
  --tool-accent-dim: var(--accent-hh-dim);
}
.theme-nutrition {
  --tool-accent: var(--accent-nutrition);
  --tool-accent-dim: var(--accent-nutrition-dim);
}
.theme-workout {
  --tool-accent: var(--accent-workout);
  --tool-accent-dim: var(--accent-workout-dim);
}
.theme-enshrouded {
  --tool-accent: var(--accent-enshrouded);
  --tool-accent-dim: var(--accent-enshrouded-dim);
}

/* Внутри инструмента используем --tool-accent вместо --accent-brand */
.theme-hh .btn-primary { background: var(--tool-accent); }
.theme-hh .btn-primary:hover { filter: brightness(1.1); }
.theme-hh .input:focus { border-color: var(--tool-accent); box-shadow: 0 0 0 3px var(--tool-accent-dim); }
```

---

## 8. Иконочная система — Lucide

**Подключение (CDN):**
```html
<script src="https://unpkg.com/lucide@latest"></script>
<script>lucide.createIcons();</script>
```

**Использование в шаблонах:**
```html
<i data-lucide="briefcase" class="tool-icon"></i>
```

**Правила:**
- `stroke-width: 1.5` (единая толщина по всему сайту).
- Размеры: 16px (inline с текстом), 20px (в кнопках), 24px (в шапках карточек), 32px (в hero-блоках).
- Цвет: наследуется из `currentColor`.
- В шапке карточки инструмента иконка — цвет акцента инструмента.
- В навигации и кнопках — цвет наследуется от текста.

**Список используемых иконок (обновляется по мере необходимости):**
- Инструменты: `Briefcase`, `Salad`, `Dumbbell`, `Shield`
- Действия: `ChevronDown`, `ChevronRight`, `X`, `Check`, `Plus`, `Trash2`, `Edit3`, `Copy`, `Save`
- Навигация: `Search`, `User`, `Settings`, `LogOut`, `Home`
- Состояния: `AlertCircle`, `Info`, `CheckCircle2`, `Loader2`

**Эмодзи разрешены ТОЛЬКО:**
- В описательном тексте уведомлений (`🎉 Программа готова!`)
- В UI-copy, где смысл эмодзи прямой (например, в welcome-сообщении «Привет 👋» — но и это лучше без)
- **НИКОГДА** — в иконках инструментов, метках категорий, заголовках карточек.

---

## 9. Атмосферный слой

Только на **лендинге** (незалогиненная главная). На всех остальных страницах — чистый двухслойный фон без эффектов.

**Компоненты:**

1. **Тонкий noise-текстур overlay** — статичный SVG-noise, 3-5% opacity, накладывается на весь фон.
   ```css
   body::before {
     content: '';
     position: fixed; inset: 0;
     background-image: url('/static/noise.svg');
     opacity: 0.04;
     pointer-events: none;
     z-index: 1;
   }
   ```

2. **Мягкий радиальный glow за H1** — статичный, не анимированный.
   ```css
   .hero::before {
     content: '';
     position: absolute;
     top: 30%; left: 50%;
     transform: translate(-50%, -50%);
     width: 800px; height: 400px;
     background: radial-gradient(ellipse, var(--accent-brand-dim), transparent 70%);
     filter: blur(60px);
     pointer-events: none;
     z-index: -1;
   }
   ```

**Что удаляется:**
- `static/effects.js` — целиком
- Все `window.PARTICLE_THEME` конфиги в шаблонах
- Класс `.particles-*`, `.aurora-*`, `.blob-*` и все связанные стили

---

## 10. Информационная архитектура — правила

### 10.1. Профиль (`/profile`)

Секции сверху вниз:

1. **Аватар и имя** — крупный аватар слева (96×96px), справа `<h2>Отображаемое имя</h2>` + кнопка «Изменить». По умолчанию — инициалы на `--surface-2` с текстом акцентного цвета.
2. **Email** — поле с текущим email + кнопка «Изменить email». Изменение через модалку с подтверждением текущим паролем.
3. **Пароль** — кнопка «Сменить пароль» → модалка (текущий → новый → повтор).
4. **Часовой пояс** — select, автоопределение через `Intl.DateTimeFormat().resolvedOptions().timeZone`.
5. **Уведомления** — тумблеры (email на новые письма от системы, email на еженедельные отчёты, и т.д.)
6. **Удаление аккаунта** — внизу, красная secondary-кнопка с текстом «Удалить аккаунт», клик → модалка с двухшаговым подтверждением (вводом email и текущего пароля).

**Что удаляется из профиля:** блок «Моё резюме» — переезжает в HH-ассистент.

### 10.2. HH-ассистент — вкладка «Настройки»

Внутри `/hh` появляется система табов:
- **Написать письмо** (основная) — текущая функциональность (вакансия → анализ → генерация)
- **История писем** — то, что сейчас снизу
- **Досье** — все 7 разделов, которые сейчас в отдельной свёрнутой карточке
- **Резюме** — то, что переезжает из профиля
- **Правила** (опционально) — few-shot management, defaults для custom_context

Табы сверху, sticky под шапкой. Оформление — Lucide-иконки + текст, активный таб — акцентная линия снизу.

### 10.3. Breadcrumbs

Единый паттерн на всех страницах внутри инструментов:
```
[Home icon] / Инструменты / HH-ассистент / Написать письмо
```

Стили: `--text-caption`, цвет `--text-2`, разделитель `/` в `--text-faint`. Последний элемент (текущая страница) — `--text`, weight 500.

### 10.4. Правило «всегда есть путь назад»

С любой страницы должны работать:
- Клик по логотипу → главная
- Аватар → профиль/выйти
- Breadcrumb → любой уровень выше
- Browser back button (не ломать history)

Никаких «вернуться» кнопок в отдельных местах — всё через единые механизмы шапки и breadcrumb.

### 10.5. UI-copy

Правила из frontend-design skill:
- Кнопки называют действие в активном залоге: «Сохранить резюме», не «Отправить».
- Одна и та же операция называется одинаково через весь флоу: кнопка «Опубликовать» → тост «Опубликовано» (не «Успешно опубликовано»).
- Никаких «Успешно», «Ошибка!» без содержания. Вместо «Ошибка!» — «Не удалось сохранить: сеть недоступна. Попробуйте ещё раз.»
- **Убрать метку «ДОСТУПЕН»** на карточках инструментов — она ничего не сообщает. Заменить на короткое описание того, ЧТО инструмент делает («Готовит письмо за 30 секунд»), или убрать вовсе.
- В пустых состояниях — не «Здесь пусто», а «Ещё не написано ни одного письма. Начните с вакансии →».

---

## 11. Legacy — что удаляется/заменяется

**Файлы на удаление:**
- `static/effects.js` — целиком
- `static/theme.js` — заглушка, целиком
- `SYSTEM.md` — заменяется этим файлом (можно переименовать в `SYSTEM.md.legacy` на 2 недели как страховку)
- Файл `THEME-workout.md` — не существует, ссылку в CLAUDE.md удалить

**CSS-переменные на удаление:**
- `--grad-btn` — заменяется на однотонный `--accent-brand` и `--tool-accent`
- `--font-head: 'Syne'` — заменяется на `--font: 'Manrope'` для всего
- `--bg4` — не используется, удалить
- Все переменные внутри `html.light { ... }` — блок целиком удалить (мёртвый код)
- `--accent`, `--accent-2` (старые cyan/purple) — заменить на новую систему акцентов

**Хардкод-цвета для замены (в HTML-шаблонах, особенно `hh.html`):**
- `#c7d3ea`, `#dde2f0`, `rgba(199,211,234,*)` → `--text` или `--text-2` по смыслу
- `#81899b`, `#7a83a0`, `#5a6888` → `--text-2` или `--text-faint`
- `#161a2c`, `#141524`, `#0e0e1a` → `--surface-1` / `--surface-0`
- `#1e2036`, `#191b30` → `--surface-2`
- `linear-gradient(135deg, #a78bfa, #60a5fa)` на заголовках → удалить, заменить на однотонный `--text-strong`
- `linear-gradient(135deg, #7c4dff 0%, #00d4ff 100%)` на кнопках → заменить на `background: var(--accent-brand)` или `var(--tool-accent)`

**JS/HTML-конфиги на удаление:**
- `window.PARTICLE_THEME = ...` в шаблонах
- Скрипты подключения `effects.js`
- Скрипты подключения `theme.js`
- Все inline-стили `<style>` внутри `hh.html` (переносятся в `style.css` или удаляются как дубли)

---

## 12. Чек-лист приёмки страницы

Перед тем как считать страницу готовой:

- [ ] Не осталось hardcode-цветов (grep `#[0-9a-fA-F]{3,6}` даёт 0)
- [ ] Не осталось inline-стилей `<style>` в шаблоне (всё в `style.css`)
- [ ] Все шрифты — Manrope (или JetBrains Mono для меток). Syne нет.
- [ ] Все размеры текста — из шкалы (`--text-*`) или через clamp. Никаких `font-size: 14px` в inline.
- [ ] Все отступы — из шкалы `--space-*`.
- [ ] Шапка sticky, не исчезает при скролле.
- [ ] Есть breadcrumb (если это внутренняя страница инструмента).
- [ ] Есть футер.
- [ ] Все иконки — Lucide. Эмодзи в UI-элементах нет.
- [ ] Focus-состояния видны (ring из `--tool-accent-dim`).
- [ ] Prefers-reduced-motion работает (анимации отключаются).
- [ ] На мобильном (390px) вёрстка не ломается, ничего не режется.
- [ ] Если применяется тема инструмента — класс `.theme-*` на body, primary-акцент = `--tool-accent`.

---

## 13. Приложение: полный CSS-скелет :root

Для копирования в `style.css`:

```css
:root {
  /* Fonts */
  --font: 'Manrope', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;

  /* Surfaces */
  --surface-0: #0A0B0D;
  --surface-1: #141520;
  --surface-2: #1E2030;
  --surface-3: #2A2C45;

  /* Borders */
  --border: rgba(255,255,255,0.08);
  --border-strong: rgba(255,255,255,0.14);
  --border-hairline: rgba(255,255,255,0.06);

  /* Text */
  --text: #E8ECF8;
  --text-2: #AEB8D4;
  --text-faint: #7A83A0;
  --text-strong: #FFFFFF;

  /* Text sizes */
  --text-display: clamp(2.5rem, 5vw, 4.5rem);
  --text-h1: clamp(1.75rem, 4vw, 3rem);
  --text-h2: clamp(1.375rem, 3vw, 2rem);
  --text-h3: clamp(1.125rem, 2vw, 1.5rem);
  --text-body-lg: 1.0625rem;
  --text-body: 1rem;
  --text-body-sm: 0.9375rem;
  --text-nav: 0.9375rem;
  --text-caption: 0.8125rem;
  --text-mono: 0.75rem;

  /* Accents */
  --accent-brand: #4F8FFF;
  --accent-brand-hover: #6BA0FF;
  --accent-brand-dim: rgba(79,143,255,0.15);

  --accent-hh: #4F8FFF;
  --accent-hh-dim: rgba(79,143,255,0.15);
  --accent-nutrition: #10B981;
  --accent-nutrition-dim: rgba(16,185,129,0.15);
  --accent-workout: #F59E0B;
  --accent-workout-dim: rgba(245,158,11,0.15);
  --accent-enshrouded: #D97706;
  --accent-enshrouded-dim: rgba(217,119,6,0.15);

  /* Semantic */
  --success: #10B981;
  --warning: #F59E0B;
  --error: #EF4444;

  /* Radii */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 24px;

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
  --shadow-lg: 0 12px 32px rgba(0,0,0,0.5);
  --shadow-glow-brand: 0 0 24px rgba(79,143,255,0.25);

  /* Spacing */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 48px;
  --space-8: 72px;
  --space-9: 96px;
  --space-10: 128px;

  /* Motion */
  --ease: cubic-bezier(0.4, 0, 0.2, 1);
  --ease-out: cubic-bezier(0, 0, 0.2, 1);
  --dur-fast: 150ms;
  --dur-base: 200ms;
  --dur-slow: 400ms;
}

body {
  background: var(--surface-0);
  color: var(--text);
  font-family: var(--font);
  font-size: var(--text-body);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

---

## 14. Финальное напоминание

**Мы платим за одну фишку — running-border кнопка. Всё остальное — тишина и дисциплина.** Если возникает соблазн добавить эффект / градиент / декоративный элемент — сначала спроси: «Это нужно для понимания или для украшения?» Если для украшения — не добавлять.

Референс восприятия: страница должна работать одинаково хорошо для человека, который увидит её на 4K-мониторе с идеальной цветопередачей, и для человека, который откроет её на телефоне под ярким солнцем. Если приём разрушается в одном из этих сценариев — он не проходит.
