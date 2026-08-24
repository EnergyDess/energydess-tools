/* ══ ДИКТОФОН — СИСТЕМНЫЙ КОМПОНЕНТ ═══════════════════════════════════

   Запись голоса кнопкой: оверлей поверх строки ввода, волна, пауза,
   отмена, отправка. Распознавание — `/nutrition/api/transcribe`.

   ─────────────────────────────────────────────────────────────────────
   ПОЧЕМУ ОТДЕЛЬНЫМ ФАЙЛОМ, А НЕ ВТОРОЙ КОПИЕЙ В АПТЕЧКЕ

   До 2026-08-24 эти ~200 строк жили ИНЛАЙНОМ в `templates/nutrition.html`
   и потребитель у них был один. Аптечке понадобился тот же диктофон,
   и копия была бы ровно тем дублем, против которого заведена задача 126:
   две реализации записи голоса разошлись бы молча — правку паузы или
   отмены внесли бы в одну.

   Вынесено ЦЕЛИКОМ, а не переписано похоже. Дневник зовёт тот же файл;
   его собственная обёртка `attachVoiceButton` осталась на месте и стала
   тонкой.

   ─────────────────────────────────────────────────────────────────────
   ЧТО ПРИШЛОСЬ ПАРАМЕТРИЗОВАТЬ — ТРИ ВЕЩИ, И ВСЕ ТРИ СТРАНИЧНЫЕ

   · КОНТЕЙНЕР. Оверлей ложится `position: absolute` поверх строки
     ввода, и найти её надо было селектором `.chat-input-row, .s-bar` —
     это имена дневника. Стало: контейнер приходит параметром либо
     берётся из `data-voice-box` на самой кнопке;

   · СООБЩЕНИЕ ОБ ОТКАЗЕ. `toast()` объявлен в дневнике. Стало:
     обработчик приходит параметром. Умолчания «промолчать» тут НЕТ —
     микрофон, которому не дали доступ, обязан сказать об этом, иначе
     нажатие выглядит как сломанная кнопка (§6.0.1);

   · ЧТО ДЕЛАТЬ С ЗАПИСЬЮ. Дневнику нужен пузырь в переписке, аптечке —
     текст в поле. Стало: `готово(blob, длительность, столбики)`.

   ─────────────────────────────────────────────────────────────────────
   ЦВЕТ ДОРОЖКИ ПЕРЕЕХАЛ С `--success` НА `--tool-accent`

   И это НЕ меняет дневник ни на пиксель: `--success` и
   `--accent-nutrition` объявлены ОДНИМ И ТЕМ ЖЕ значением `#10B981`
   (`style.css`). Зато у аптечки дорожка становится её собственной
   бирюзой, а не зелёной из чужого раздела, — то есть компонент начинает
   вести себя как системный (CLAUDE.md §4).

   ФОЛБЭКА У ЧТЕНИЯ ТОКЕНА НЕТ НАМЕРЕННО — он был снят задачей 18 и
   возвращаться не должен: строка `|| '#10B981'` прятала ровно то, ради
   чего цвет и читается из токена. Не разрешился — причина в консоль,
   дорожка остаётся без заливки, то есть отказ ВИДЕН глазом.            */

const ДИКТОФОН_СТОЛБИКОВ = 27;
const ДИКТОФОН_ПАУЗА = `<svg fill="currentColor" viewBox="0 0 24 24"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>`;
const ДИКТОФОН_МИКРОФОН = `<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v2a7 7 0 01-14 0v-2M12 19v4M8 23h8"/></svg>`;

/* Запись одна на страницу: два диктофона разом означали бы две дорожки
   поверх одной строки ввода и два потока с микрофона */
let голосЗапись = null;

/* Подписка кнопки на запись.
     кнопка   — элемент или его id
     настройки:
       контейнер — селектор родителя для оверлея (или `data-voice-box`)
       готово    — async (blob, длительность, столбики) => {}
       сообщить  — (текст) => {}   отказ микрофона и браузера           */
function подключитьДиктофон(кнопка, настройки) {
  const б = typeof кнопка === 'string' ? document.getElementById(кнопка) : кнопка;
  if (!б) return;
  б.addEventListener('click', () => голосСтарт(б, настройки));
  // На Android долгое нажатие иначе открывает системное меню «Копировать»
  б.addEventListener('contextmenu', (e) => e.preventDefault());
}

function голосДлит(сек) {
  сек = Math.max(0, Math.round(сек));
  const м = Math.floor(сек / 60), с = сек % 60;
  return `${м}:${с.toString().padStart(2, '0')}`;
}

/* Настоящая длительность записи без времени на паузе */
function голосПрошло(зап) {
  let пауза = зап.pausedMs;
  if (зап.paused) пауза += Date.now() - зап.pauseStart;
  return (Date.now() - зап.startTime) - пауза;
}

async function голосСтарт(б, настройки) {
  if (голосЗапись) return;
  const сказать = настройки.сообщить || ((т) => console.warn('[диктофон] ' + т));
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    сказать('Запись голоса не поддерживается этим браузером'); return;
  }
  const сел = настройки.контейнер || б.dataset.voiceBox;
  const контейнер = сел ? б.closest(сел) : б.parentElement;
  if (!контейнер) { сказать('Некуда показать запись'); return; }

  let поток;
  try {
    поток = await navigator.mediaDevices.getUserMedia({audio: true});
  } catch {
    сказать('Доступ к микрофону не разрешён'); return;
  }

  const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']
    .find(t => MediaRecorder.isTypeSupported(t)) || '';
  const рекордер = new MediaRecorder(поток, mime ? {mimeType: mime} : undefined);
  const куски = [];
  рекордер.ondataavailable = (ev) => { if (ev.data.size) куски.push(ev.data); };

  const звук = new (window.AudioContext || window.webkitAudioContext)();
  if (звук.state === 'suspended') звук.resume();
  const анализ = звук.createAnalyser();
  анализ.fftSize = 256;
  звук.createMediaStreamSource(поток).connect(анализ);

  const оверлей = document.createElement('div');
  оверлей.className = 'voice-rec-overlay';
  оверлей.innerHTML = `
    <button class="btn-icon btn-icon-round voice-rec-del" title="Удалить" aria-label="Удалить запись">
      <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4a1 1 0 011-1h6a1 1 0 011 1v2m2 0v14a1 1 0 01-1 1H6a1 1 0 01-1-1V6h14z"/></svg>
    </button>
    <div class="voice-rec-dot"></div>
    <span class="voice-rec-timer">0:00</span>
    <div class="voice-rec-wave"><canvas></canvas></div>
    <button class="btn-icon btn-icon-round voice-rec-send" title="Отправить" aria-label="Отправить запись">
      <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
    </button>`;
  контейнер.appendChild(оверлей);
  б.classList.add('voice-active');

  /* Плавающая кнопка паузы над кнопкой отправки — тап ставит на паузу
     и снимает её, без удержания пальца */
  const пауза = document.createElement('button');
  пауза.className = 'voice-pause-float';
  пауза.title = 'Пауза';
  пауза.setAttribute('aria-label', 'Пауза');
  пауза.innerHTML = ДИКТОФОН_ПАУЗА;
  document.body.appendChild(пауза);

  голосЗапись = {
    б, настройки, контейнер, оверлей, пауза, рекордер, поток, куски, звук, анализ,
    startTime: Date.now(), paused: false, pausedMs: 0, pauseStart: 0,
    амплитуды: [], rafId: null, timerId: null,
  };

  /* Позиционируем после того, как анимация появления отрисуется: иначе
     геометрия считается по стартовому кадру `scale(.97)` и кнопка съезжает */
  requestAnimationFrame(() => requestAnimationFrame(голосПоложениеПаузы));
  window.addEventListener('resize', голосПоложениеПаузы);

  оверлей.querySelector('.voice-rec-del').onclick = голосОтмена;
  оверлей.querySelector('.voice-rec-send').onclick = голосОтправить;
  пауза.onclick = голосПереключитьПаузу;

  рекордер.start();
  голосЗапись.timerId = setInterval(() => {
    if (!голосЗапись) return;
    const эл = голосЗапись.оверлей.querySelector('.voice-rec-timer');
    if (эл) эл.textContent = голосДлит(голосПрошло(голосЗапись) / 1000);
    голосПоложениеПаузы();
  }, 200);
  голосЦикл();
}

function голосПоложениеПаузы() {
  if (!голосЗапись) return;
  const отпр = голосЗапись.оверлей.querySelector('.voice-rec-send')
                 .getBoundingClientRect();
  const пл = голосЗапись.пауза.getBoundingClientRect();
  голосЗапись.пауза.style.left = (отпр.left + отпр.width / 2 - пл.width / 2) + 'px';
  голосЗапись.пауза.style.top = (отпр.top - пл.height - 16) + 'px';
}

function голосПереключитьПаузу() {
  const з = голосЗапись;
  if (!з) return;
  if (!з.paused) {
    з.paused = true;
    з.pauseStart = Date.now();
    з.рекордер.pause();
    cancelAnimationFrame(з.rafId);
    з.оверлей.querySelector('.voice-rec-dot').classList.add('paused');
    з.пауза.classList.add('is-paused');
    з.пауза.title = 'Продолжить';
    з.пауза.innerHTML = ДИКТОФОН_МИКРОФОН;
  } else {
    з.pausedMs += Date.now() - з.pauseStart;
    з.paused = false;
    з.рекордер.resume();
    з.оверлей.querySelector('.voice-rec-dot').classList.remove('paused');
    з.пауза.classList.remove('is-paused');
    з.пауза.title = 'Пауза';
    з.пауза.innerHTML = ДИКТОФОН_ПАУЗА;
    голосЦикл();
  }
}

function голосЦикл() {
  if (!голосЗапись || голосЗапись.paused) return;
  const з = голосЗапись;
  const данные = new Uint8Array(з.анализ.fftSize);
  з.анализ.getByteTimeDomainData(данные);
  let сумма = 0;
  for (let i = 0; i < данные.length; i++) {
    const v = (данные[i] - 128) / 128; сумма += v * v;
  }
  з.амплитуды.push(Math.min(1, Math.sqrt(сумма / данные.length) * 4));
  голосВолна(з.оверлей.querySelector('canvas'), з.амплитуды);
  з.rafId = requestAnimationFrame(голосЦикл);
}

function голосВолна(canvas, амплитуды) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
    canvas.width = w * dpr; canvas.height = h * dpr;
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  /* Цвет — ИЗ ТОКЕНА РАЗДЕЛА, а не хардкодом: canvas `var()` не понимает,
     поэтому значение читается со стороны.

     У `<body>`, А НЕ У КОРНЯ, И ЭТО ЗАМЕР. Тема раздела объявляется
     классом `.theme-*` НА `<body>` (CLAUDE.md §4) — у корня токена
     нет вовсе. Первая версия этого файла читала `documentElement`
     и получала ПУСТУЮ СТРОКУ и в аптечке, и в дневнике: волна
     осталась бы без заливки на обоих экранах.

     Замер: `documentElement` → '' на `/medkit` и на `/nutrition`;
     `body` → '#06B6D4' и '#10B981' соответственно.

     Дефект был бы НЕМЫМ вдвойне: прежний код читал `--success`, тот
     объявлен в `:root` и разрешался, — то есть перевод на токен
     раздела выглядел бы правкой без последствий. Нашла ПРОБА
     (`py check_medkit_ui.py --ввод`), а не чтение.

     Запрет фолбэка — в шапке файла. */
  const дорожка = getComputedStyle(document.body)
                    .getPropertyValue('--tool-accent').trim();
  if (!дорожка) console.warn('[диктофон] токен --tool-accent не разрешился — '
                             + 'дорожка голоса останется без цвета');
  else ctx.fillStyle = дорожка;
  const шир = 3, зазор = 2, n = Math.floor(w / (шир + зазор));
  const данные = амплитуды.slice(-n);
  const отступ = n - данные.length;
  данные.forEach((v, i) => {
    const вы = Math.max(2, v * h);
    ctx.fillRect((отступ + i) * (шир + зазор), (h - вы) / 2, шир, вы);
  });
}

/* Удалить запись, не отправляя */
function голосОтмена() {
  if (!голосЗапись) return;
  const з = голосЗапись;
  голосЗапись = null;
  голосУбрать(з);
  з.рекордер.onstop = () => {
    з.поток.getTracks().forEach(t => t.stop());
    з.звук.close();
  };
  з.рекордер.stop();
}

/* Завершить и отдать наружу */
function голосОтправить() {
  if (!голосЗапись) return;
  const з = голосЗапись;
  голосЗапись = null;
  const длительность = голосПрошло(з) / 1000;
  голосУбрать(з);
  const столбики = голосСтолбики(з.амплитуды, ДИКТОФОН_СТОЛБИКОВ);
  з.рекордер.onstop = () => {
    з.поток.getTracks().forEach(t => t.stop());
    з.звук.close();
    /* Меньше полусекунды — промах по кнопке, а не сообщение */
    if (длительность < 0.6) return;
    const blob = new Blob(з.куски, {type: з.рекордер.mimeType || 'audio/webm'});
    з.настройки.готово(blob, длительность, столбики);
  };
  з.рекордер.stop();
}

function голосУбрать(з) {
  clearInterval(з.timerId);
  cancelAnimationFrame(з.rafId);
  window.removeEventListener('resize', голосПоложениеПаузы);
  з.оверлей.remove();
  з.пауза.remove();
  з.б.classList.remove('voice-active');
}

function голосСтолбики(массив, n) {
  if (!массив.length) return new Array(n).fill(0.15);
  const из = [];
  for (let i = 0; i < n; i++) из.push(массив[Math.floor(i / n * массив.length)]);
  return из;
}

/* Распознавание. Адрес ОДИН на всех потребителей: второй эндпоинт
   означал бы вторую настройку модели, расходящуюся молча */
async function голосВТекст(blob) {
  const фд = new FormData();
  фд.append('file', blob, 'voice.webm');
  try {
    const отв = await fetch('/nutrition/api/transcribe', {method: 'POST', body: фд});
    const д = await отв.json();
    return (д.text || '').trim();
  } catch { return ''; }
}
