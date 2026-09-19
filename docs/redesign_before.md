# Замер «до» редизайна залогиненной части

Собрано командой `py measure_redesign.py docs/redesign_before.md` (задача 352, письмо 1, блок 1). Руками не правится.

## 1. CSS-переменные

| вид | объявлено | не используется | где (файл:строка первой) |
|---|---:|---:|---|
| цвет | 72 | 0 | static/style.css×63, static/nutrition.css×6, static/enshrouded.css×2, static/landing.css×1 |
| шрифт | 2 | 0 | static/style.css×2 |
| размер шрифта | 11 | 1 | static/style.css×11 |
| отступ | 10 | 0 | static/style.css×10 |
| скругление | 4 | 0 | static/style.css×4 |
| тень | 4 | 0 | static/style.css×4 |
| анимация | 5 | 0 | static/style.css×5 |
| прочее | 40 | 1 | static/landing.css×18, static/nutrition.css×7, static/style.css×7, static/workout.css×4 |

Не используются (ни `var()`, ни строкой в скрипте):
- размер шрифта: `--text-display` — static/style.css:350 = `clamp(2.5rem, 5vw, 4.5rem)`
- прочее: `--status-missed` — static/workout.css:86 = `var(--text-faint)`

Полный список объявлений:
- `--admin-bar-h` [прочее] static/admin.css:134 = `40px` (var: 2)
- `--cat` [цвет] static/enshrouded.css:31 = `#d48a2a` (var: 6)
- `--rar` [цвет] static/enshrouded.css:48 = `#8a8a8a` (var: 8)
- `--ens-slot` [прочее] static/enshrouded.css:394 = `4.25rem` (var: 1)
- `--meter-h` [прочее] static/hh.css:322 = `3px` (var: 1)
- `--apt-slot` [прочее] static/medkit.css:813 = `52px` (var: 1)
- `--prot` [цвет] static/nutrition.css:62 = `#f472b6` (var: 4)
- `--fat` [цвет] static/nutrition.css:63 = `#fbbf24` (var: 4)
- `--carb` [цвет] static/nutrition.css:64 = `#60a5fa` (var: 4)
- `--wat` [цвет] static/nutrition.css:65 = `#38bdf8` (var: 12)
- `--nav-h` [прочее] static/nutrition.css:66 = `4rem` (var: 5)
- `--hdr-h` [прочее] static/nutrition.css:67 = `3.375rem` (var: 3)
- `--nut-glow` [цвет] static/nutrition.css:74 = `color-mix(in srgb, var(--tool-accent) 25%, transparent)` (var: 4)
- `--meter-over-ink` [цвет] static/nutrition.css:995 = `color-mix(in srgb, var(--wat) 60%, var(--surface-0))` (var: 1)
- `--nut-aside` [прочее] static/nutrition.css:1840 = `15rem` (var: 3)
- `--app-aside` [прочее] static/nutrition.css:1840 = `var(--nut-aside)` (var: 1)
- `--nut-u` [прочее] static/nutrition.css:1868 = `1rem` (var: 167)
- `--nut-summary` [прочее] static/nutrition.css:2023 = `calc(18 * var(--nut-u))` (var: 3)
- `--nut-water-pad` [прочее] static/nutrition.css:2023 = `calc(0.875 * var(--nut-u))` (var: 2)
- `--font` [шрифт] static/style.css:296 = `'Manrope', 'Manrope Fallback', 'Manrope Fallback Android',` (var: 68)
- `--font-mono` [шрифт] static/style.css:298 = `'JetBrains Mono', 'JetBrains Mono Fallback', monospace` (var: 62)
- `--surface-0` [цвет] static/style.css:301 = `#0A0B0D` (var: 55)
- `--surface-1` [цвет] static/style.css:302 = `#141520` (var: 48)
- `--surface-2` [цвет] static/style.css:303 = `#1E2030` (var: 97)
- `--surface-3` [цвет] static/style.css:304 = `#2A2C45` (var: 31)
- `--surface-sunken` [цвет] static/style.css:309 = `#0e0f16` (var: 28)
- `--border` [цвет] static/style.css:312 = `rgba(255,255,255,0.08)` (var: 158)
- `--border-strong` [цвет] static/style.css:313 = `rgba(255,255,255,0.14)` (var: 74)
- `--border-hairline` [цвет] static/style.css:314 = `rgba(255,255,255,0.06)` (var: 18)
- `--border-contrast` [цвет] static/style.css:341 = `rgba(255,255,255,0.36)` (var: 5)
- `--text` [цвет] static/style.css:344 = `#E8ECF8` (var: 183)
- `--text-2` [цвет] static/style.css:345 = `#AEB8D4` (var: 247)
- `--text-faint` [цвет] static/style.css:346 = `#7A83A0` (var: 125)
- `--text-strong` [цвет] static/style.css:347 = `#FFFFFF` (var: 33)
- `--text-display` [размер шрифта] static/style.css:350 = `clamp(2.5rem, 5vw, 4.5rem)` (var: 0)
- `--text-h1` [размер шрифта] static/style.css:351 = `clamp(1.75rem, 4vw, 3rem)` (var: 7)
- `--text-h2` [размер шрифта] static/style.css:352 = `clamp(1.375rem, 3vw, 2rem)` (var: 5)
- `--text-h3` [размер шрифта] static/style.css:353 = `clamp(1.125rem, 2vw, 1.5rem)` (var: 20)
- `--text-body-xl` [размер шрифта] static/style.css:357 = `1.125rem` (var: 2)
- `--text-body-lg` [размер шрифта] static/style.css:358 = `1.0625rem` (var: 24)
- `--text-body` [размер шрифта] static/style.css:359 = `1rem` (var: 35)
- `--text-body-sm` [размер шрифта] static/style.css:360 = `0.9375rem` (var: 94)
- `--text-nav` [размер шрифта] static/style.css:361 = `0.9375rem` (var: 2)
- `--text-caption` [размер шрифта] static/style.css:362 = `0.8125rem` (var: 277)
- `--text-mono` [размер шрифта] static/style.css:363 = `0.75rem` (var: 35)
- `--accent-brand` [цвет] static/style.css:366 = `#4F8FFF` (var: 97)
- `--accent-brand-hover` [цвет] static/style.css:375 = `#146AFF` (var: 4)
- `--accent-brand-dim` [цвет] static/style.css:376 = `rgba(79,143,255,0.15)` (var: 30)
- `--landing-card-bg` [цвет] static/style.css:381 = `#101018` (var: 1)
- `--landing-card-line` [цвет] static/style.css:382 = `rgba(255,255,255,0.5)` (var: 3)
- `--landing-glow-blue` [цвет] static/style.css:383 = `rgba(70,90,255,0.28)` (var: 1)
- `--landing-glow-violet` [цвет] static/style.css:384 = `rgba(150,70,230,0.25)` (var: 1)
- `--landing-soft` [цвет] static/style.css:385 = `#A9B0FF` (var: 5)
- `--landing-soft-line` [цвет] static/style.css:386 = `rgba(169,176,255,0.4)` (var: 2)
- `--landing-mini-bg` [цвет] static/style.css:387 = `rgba(255,255,255,0.05)` (var: 3)
- `--landing-mini-line` [цвет] static/style.css:388 = `rgba(255,255,255,0.1)` (var: 3)
- `--landing-ghost-bg` [цвет] static/style.css:390 = `rgba(10,10,20,0.55)` (var: 1)
- `--landing-sky-0` [цвет] static/style.css:407 = `#0a0b12` (var: 1)
- `--landing-sky-1` [цвет] static/style.css:408 = `#0a0b13` (var: 1)
- `--landing-sky-2` [цвет] static/style.css:409 = `#0b0c15` (var: 1)
- `--landing-sky-3` [цвет] static/style.css:410 = `#0b0c17` (var: 1)
- `--landing-sky-4` [цвет] static/style.css:411 = `#0c0d19` (var: 1)
- `--landing-sky-5` [цвет] static/style.css:412 = `#0c0e1a` (var: 1)
- `--landing-sky-6` [цвет] static/style.css:413 = `#0c0e1a` (var: 1)
- `--landing-sky-diag-blue` [цвет] static/style.css:414 = `rgba(40,60,190,0.03)` (var: 1)
- `--landing-sky-diag-violet` [цвет] static/style.css:415 = `rgba(120,60,210,0.04)` (var: 1)
- `--landing-sky-band-1` [цвет] static/style.css:416 = `rgba(55,80,220,0.04)` (var: 1)
- `--landing-sky-band-2` [цвет] static/style.css:417 = `rgba(120,70,220,0.045)` (var: 1)
- `--landing-sky-band-3` [цвет] static/style.css:418 = `rgba(70,90,240,0.05)` (var: 1)
- `--landing-sky-band-4` [цвет] static/style.css:419 = `rgba(145,75,235,0.055)` (var: 1)
- `--landing-star` [цвет] static/style.css:424 = `rgba(255,255,255,0.42)` (var: 3)
- `--landing-star-dim` [цвет] static/style.css:425 = `rgba(255,255,255,0.30)` (var: 2)
- `--landing-tool-bg` [цвет] static/style.css:429 = `rgba(255,255,255,0.02)` (var: 1)
- `--landing-tool-line` [цвет] static/style.css:430 = `rgba(255,255,255,0.14)` (var: 1)
- `--landing-window-line` [цвет] static/style.css:436 = `rgba(255,255,255,0.10)` (var: 1)
- `--accent-hh` [цвет] static/style.css:457 = `#4F8FFF` (var: 4)
- `--accent-hh-dim` [цвет] static/style.css:458 = `rgba(79,143,255,0.15)` (var: 3)
- `--accent-hh-hover` [цвет] static/style.css:459 = `#146AFF` (var: 1)
- `--accent-nutrition` [цвет] static/style.css:460 = `#10B981` (var: 4)
- `--accent-nutrition-dim` [цвет] static/style.css:461 = `rgba(16,185,129,0.15)` (var: 3)
- `--accent-nutrition-hover` [цвет] static/style.css:462 = `#12D595` (var: 1)
- `--accent-workout` [цвет] static/style.css:463 = `#F59E0B` (var: 4)
- `--accent-workout-dim` [цвет] static/style.css:464 = `rgba(245,158,11,0.15)` (var: 3)
- `--accent-workout-hover` [цвет] static/style.css:465 = `#F6AA28` (var: 1)
- `--accent-enshrouded` [цвет] static/style.css:466 = `#D97706` (var: 4)
- `--accent-enshrouded-dim` [цвет] static/style.css:467 = `rgba(217,119,6,0.15)` (var: 3)
- `--accent-enshrouded-hover` [цвет] static/style.css:468 = `#A25904` (var: 2)
- `--accent-medkit` [цвет] static/style.css:474 = `#06B6D4` (var: 4)
- `--accent-medkit-dim` [цвет] static/style.css:475 = `rgba(6,182,212,0.15)` (var: 3)
- `--accent-medkit-hover` [цвет] static/style.css:476 = `#07D0F2` (var: 1)
- `--letterbox` [цвет] static/style.css:484 = `#000` (var: 2)
- `--success` [цвет] static/style.css:486 = `#10B981` (var: 42)
- `--success-strong` [цвет] static/style.css:494 = `#34D399` (var: 3)
- `--warning` [цвет] static/style.css:495 = `#F59E0B` (var: 67)
- `--error` [цвет] static/style.css:496 = `#EF4444` (var: 94)
- `--avatar-size` [прочее] static/style.css:502 = `36px` (var: 3)
- `--radius-sm` [скругление] static/style.css:505 = `8px` (var: 121)
- `--radius-md` [скругление] static/style.css:506 = `12px` (var: 47)
- `--radius-lg` [скругление] static/style.css:507 = `16px` (var: 11)
- `--radius-xl` [скругление] static/style.css:508 = `24px` (var: 2)
- `--shadow-sm` [тень] static/style.css:511 = `0 1px 2px rgba(0,0,0,0.3)` (var: 2)
- `--shadow-md` [тень] static/style.css:512 = `0 4px 12px rgba(0,0,0,0.4)` (var: 8)
- `--shadow-lg` [тень] static/style.css:513 = `0 12px 32px rgba(0,0,0,0.5)` (var: 13)
- `--shadow-glow-brand` [тень] static/style.css:514 = `0 0 24px rgba(79,143,255,0.25)` (var: 1)
- `--space-1` [отступ] static/style.css:517 = `4px` (var: 145)
- `--space-2` [отступ] static/style.css:518 = `8px` (var: 416)
- `--space-3` [отступ] static/style.css:519 = `12px` (var: 437)
- `--space-4` [отступ] static/style.css:520 = `16px` (var: 260)
- `--space-5` [отступ] static/style.css:521 = `24px` (var: 147)
- `--space-6` [отступ] static/style.css:522 = `32px` (var: 88)
- `--space-7` [отступ] static/style.css:523 = `48px` (var: 45)
- `--space-8` [отступ] static/style.css:524 = `72px` (var: 9)
- `--space-9` [отступ] static/style.css:525 = `96px` (var: 6)
- `--space-10` [отступ] static/style.css:526 = `128px` (var: 4)
- `--ease` [анимация] static/style.css:529 = `cubic-bezier(0.4, 0, 0.2, 1)` (var: 102)
- `--ease-out` [анимация] static/style.css:530 = `cubic-bezier(0, 0, 0.2, 1)` (var: 28)
- `--dur-fast` [анимация] static/style.css:531 = `150ms` (var: 85)
- `--dur-base` [анимация] static/style.css:532 = `200ms` (var: 26)
- `--dur-slow` [анимация] static/style.css:533 = `400ms` (var: 12)
- `--tool-accent` [прочее] static/style.css:552 = `var(--accent-hh)` (var: 270)
- `--tool-accent-dim` [прочее] static/style.css:553 = `var(--accent-hh-dim)` (var: 34)
- `--tool-accent-hover` [прочее] static/style.css:554 = `var(--accent-hh-hover)` (var: 2)
- `--tool-accent-ink` [прочее] static/style.css:555 = `var(--text-strong)` (var: 11)
- `--viewer-w` [прочее] static/style.css:1989 = `94vw` (var: 5)
- `--viewer-h` [прочее] static/style.css:1989 = `88vh` (var: 4)
- `--status-done` [прочее] static/workout.css:83 = `var(--success)` (var: 7)
- `--status-partial` [прочее] static/workout.css:84 = `var(--warning)` (var: 1)
- `--status-skipped` [прочее] static/workout.css:85 = `var(--text-faint)` (var: 6)
- `--status-missed` [прочее] static/workout.css:86 = `var(--text-faint)` (var: 0)
- `--pf-fan-mid` [прочее] static/landing.css:88 = `calc(20vh + 50%)` (var: 5)
- `--pf-scrim` [прочее] static/landing.css:149 = `72%` (var: 1)
- `--pf-sky-tail` [прочее] static/landing.css:181 = `min(40vh, 24rem)` (var: 3)
- `--pf-sky-b1` [прочее] static/landing.css:187 = `24%` (var: 1)
- `--pf-sky-b3` [прочее] static/landing.css:188 = `38%` (var: 1)
- `--pf-sky-b2` [прочее] static/landing.css:189 = `50%` (var: 1)
- `--pf-sky-b4` [прочее] static/landing.css:190 = `62%` (var: 1)
- `--pf-name` [прочее] static/landing.css:264 = `9.35cqi` (var: 3)
- `--pf-head-up` [прочее] static/landing.css:370 = `6.5svh` (var: 2)
- `--pf-cta-a` [прочее] static/landing.css:421 = `var(--accent-brand-hover)` (var: 1)
- `--pf-cta-b` [цвет] static/landing.css:422 = `color-mix(in srgb, var(--accent-brand-hover) 50%, var(--erro` (var: 1)
- `--pf-cta-c` [прочее] static/landing.css:423 = `var(--accent-enshrouded-hover)` (var: 1)
- `--pf-feed-fade` [прочее] static/landing.css:541 = `clamp(2rem, 9vw, 14rem)` (var: 4)
- `--pf-tools-side` [прочее] static/landing.css:709 = `max(var(--space-6), calc((100% - 1600px) / 2 + var(--space-6` (var: 1)
- `--pf-tool-n-size` [прочее] static/landing.css:756 = `clamp(3rem, 6vw, 7rem)` (var: 1)
- `--pf-fill-now` [прочее] static/landing.css:1071 = `0` (var: 2)
- `--pf-proj-n-size` [прочее] static/landing.css:1155 = `clamp(3rem, 6vw, 7rem)` (var: 3)
- `--pf-proj-gap` [прочее] static/landing.css:1190 = `var(--space-3)` (var: 2)
- `--pf-tail-x` [прочее] static/landing.css:1338 = `50%` (var: 1)

## 2. Прямые значения мимо переменных (залогиненные стили)

| вид | всего | файлов |
|---|---:|---:|
| цвет | 45 | 3 |
| размер шрифта | 45 | 6 |
| отступ | 113 | 10 |
| скругление | 71 | 8 |
| тень | 28 | 7 |
| (инлайновый style= с числом/цветом в шаблонах) | 0 | 0 |

Топ-10 файлов (сумма по всем видам):

| файл | всего | цвет | кегль | отступ | скругл. | тень |
|---|---:|---:|---:|---:|---:|---:|
| static/style.css | 124 | 25 | 13 | 60 | 14 | 12 |
| static/nutrition.css | 64 | 9 | 8 | 2 | 39 | 6 |
| static/medkit.css | 31 | 11 | 1 | 15 | 4 | 0 |
| static/workout_profile.css | 28 | 0 | 13 | 14 | 1 | 0 |
| static/workout.css | 27 | 0 | 9 | 6 | 9 | 3 |
| static/hh.css | 9 | 0 | 0 | 6 | 1 | 2 |
| static/admin.css | 6 | 0 | 0 | 3 | 2 | 1 |
| static/enshrouded.css | 5 | 0 | 1 | 1 | 0 | 3 |
| static/verify.css | 5 | 0 | 0 | 3 | 1 | 1 |
| static/profile.css | 3 | 0 | 0 | 3 | 0 | 0 |

Примеры (до трёх на вид и файл):
- отступ · static/admin.css: 550: padding: var(--space-2) var(--space-3) var(--space-2) 36px ‖ 719: padding: 3px var(--space-2) ‖ 728: margin-top: 2px
- отступ · static/enshrouded.css: 464: padding: 0 3px
- отступ · static/hh.css: 187: margin-top: 2px ‖ 297: margin: calc(-1 * var(--space-3) - 1px) calc(-1 * var(--sp ‖ 365: gap: 2px
- отступ · static/medkit.css: 778: padding: 1px 5px ‖ 863: padding: 4px ‖ 867: padding: 4px
- отступ · static/nutrition.css: 678: margin-top: 0.0625rem ‖ 2091: margin-bottom: calc(var(--nut-water-pad) + 1px)
- отступ · static/profile.css: 74: margin-top: 2px ‖ 295: padding: 6px 0 ‖ 343: padding-right: 40px
- отступ · static/style.css: 678: padding-top: 60px ‖ 1812: padding-bottom: env(safe-area-inset-bottom, 14px) ‖ 1827: padding: 12px 16px 10px
- отступ · static/verify.css: 79: padding: var(--space-4) 20px ‖ 80: margin: 20px 0 ‖ 102: margin-top: 1px
- отступ · static/workout.css: 373: margin-top: 2px ‖ 461: margin-top: 2px ‖ 470: padding-left: 1.1em
- отступ · static/workout_profile.css: 55: gap: 10px ‖ 62: padding: 6px 0 ‖ 76: padding: 9px 16px
- размер шрифта · static/enshrouded.css: 465: font-size: 0.625rem
- размер шрифта · static/medkit.css: 3205: font-size: 0.6875rem
- размер шрифта · static/nutrition.css: 284: font-size: 0.62rem ‖ 354: font-size: 1.65rem ‖ 601: font-size: 1.2rem
- размер шрифта · static/style.css: 595: font-size: clamp(16px, 13px + 0.15625vw, 19px) ‖ 1839: font-size: 1.05rem ‖ 1845: font-size: 0.97rem
- размер шрифта · static/workout.css: 115: font-size: clamp(1.6rem, 3vw, 2.2rem) ‖ 192: font-size: 1.2rem ‖ 462: font-size: 1.5rem
- размер шрифта · static/workout_profile.css: 55: font-size: 0.9375rem ‖ 57: font-size: 0.8125rem ‖ 60: font-size: 1.0625rem
- скругление · static/admin.css: 284: border-radius: 999px ‖ 719: border-radius: 999px
- скругление · static/hh.css: 402: border-radius: 999px
- скругление · static/medkit.css: 1095: border-radius: 999px ‖ 3053: border-radius: 11px ‖ 3204: border-radius: 20px
- скругление · static/nutrition.css: 167: border-radius: 0.5625rem ‖ 290: border-radius: 0.4375rem ‖ 395: border-radius: 0.875rem
- скругление · static/style.css: 1409: border-radius: 999px ‖ 1684: border-radius: calc(var(--radius-sm) - 2px) ‖ 1811: border-radius: 20px 20px 0 0
- скругление · static/verify.css: 35: border-radius: 20px
- скругление · static/workout.css: 342: border-radius: 999px ‖ 379: border-radius: 999px ‖ 416: border-radius: 999px
- скругление · static/workout_profile.css: 77: border-radius: 99px
- тень · static/admin.css: 563: box-shadow: 0 0 0 3px var(--accent-brand-dim)
- тень · static/enshrouded.css: 283: box-shadow: 0 0 0 10px var(--tool-accent-dim) ‖ 454: box-shadow: 0 0 10px color-mix(in srgb, var(--rar) 30%, transp ‖ 455: box-shadow: 0 0 18px color-mix(in srgb, var(--rar) 55%, transp
- тень · static/hh.css: 587: box-shadow: 0 0 0 3px var(--tool-accent-dim) ‖ 891: box-shadow: 0 0 0 1px var(--accent-brand), 0 0 24px rgba(79,14
- тень · static/nutrition.css: 101: box-shadow: 0 0 120px color-mix(in srgb, var(--tool-accent) 9% ‖ 450: box-shadow: 0 0 0 2px var(--surface-1), 0 0 0 4px var(--tool-a ‖ 508: box-shadow: 0 0 8px color-mix(in srgb, var(--wat) 35%, transpa
- тень · static/style.css: 1299: box-shadow: 0 0 0 3px var(--tool-accent-dim, var(--accent-bran ‖ 2053: box-shadow: 0 4px 16px rgba(0,0,0,.4) ‖ 2314: box-shadow: 0 0 0 3px var(--tool-accent-dim, var(--accent-bran
- тень · static/verify.css: 42: box-shadow: 0 0 40px color-mix(in srgb,
- тень · static/workout.css: 180: box-shadow: 0 0 0 1px var(--tool-accent) ‖ 201: box-shadow: 0 4px 18px color-mix(in srgb, var(--tool-accent) 4 ‖ 352: box-shadow: 0 0 0 2px var(--tool-accent)
- цвет · static/medkit.css: 1102: background: rgba(10, 11, 13, 0.72) ‖ 2609: background: rgba(239, 68, 68, 0.12) ‖ 2610: border: 1px solid rgba(239, 68, 68, 0.35)
- цвет · static/nutrition.css: 344: stroke: #ef4444 ‖ 356: background: linear-gradient(135deg, #fff 10%, var(--tool-accen ‖ 561: background: rgba(56,189,248,.1)
- цвет · static/style.css: 1173: background: rgba(10, 11, 13, .72) ‖ 1804: background: rgba(0,0,0,.85) ‖ 2052: background: rgba(15,18,32,.85)

## 3. Варианты компонентов (класс — субъект правила в залогиненных стилях)

| вид | классов | из них в style.css | страничных |
|---|---:|---:|---:|
| кнопки | 97 | 26 | 71 |
| карточки | 87 | 13 | 74 |
| поля ввода | 37 | 11 | 26 |
| вкладки | 15 | 4 | 11 |
| чипы | 43 | 12 | 31 |
| пустые состояния | 18 | 10 | 8 |

### кнопки: 97
- `.add-btn` — css: nutrition.css; разметка: hh.html, nutrition.html
- `.add-btn-gap` — css: nutrition.css; разметка: nutrition.html
- `.add-btn-gap-sm` — css: nutrition.css; разметка: nutrition.html
- `.ai-btn` — css: nutrition.css; разметка: nutrition.html
- `.ai-btn-gap` — css: nutrition.css; разметка: nutrition.html
- `.ai-estimate-btn` — css: nutrition.css; разметка: nutrition.html
- `.analyze-btn` — css: hh.css; разметка: hh.html
- `.apt-ai-hint-btn` — css: medkit.css; разметка: medkit.html
- `.apt-ai-item-btn` — css: medkit.css; разметка: medkit.html
- `.apt-ai-item-phbtn` — css: medkit.css; разметка: medkit.html
- `.apt-for-btn` — css: medkit.css; разметка: _medkit_who.html
- `.avatar-btn` — css: style.css; разметка: _header.html
- `.avatar-upload-btn` — css: profile.css; разметка: profile.html
- `.btn` — css: medkit.css, style.css; разметка: _admin_subnav.html, _header.html, _landing_card.html, _medkit_buy.html, _medkit_circle.html, _medkit_circle_help.html, _medkit_grid.html, _medkit_who.html, admin_exercises.html, admin_products.html, attach-menu.js, demo_program.html, enshrouded.html, hh.html, landing.html, login.html, medkit.html, nutrition.html, profile.html, register.html, reset_password.html, ui.js, verify_pending.html, verify_required.html, workout.html, workout_profile.html
- `.btn-block` — css: style.css; разметка: forgot_password.html, login.html, medkit.html, nutrition.html, register.html, reset_password.html, verify_required.html
- `.btn-danger` — css: style.css; разметка: _medkit_buy.html, _medkit_circle.html, _medkit_grid.html, admin_enshrouded.html, admin_landing.html, admin_products.html, medkit.html, profile.html, workout_profile.html
- `.btn-ghost` — css: profile.css, style.css; разметка: _header.html, _medkit_grid.html, medkit.html, nutrition.html, profile.html, workout.html
- `.btn-icon` — css: nutrition.css, style.css; разметка: _medkit_cats.html, _medkit_circle.html, _medkit_grid.html, admin_products.html, enshrouded.html, hh.html, login.html, medkit.html, nutrition.html, register.html, reset_password.html, voice-input.js, workout_profile.html
- `.btn-icon-accent` — css: style.css; разметка: medkit.html, nutrition.html
- `.btn-icon-danger` — css: style.css; разметка: _medkit_cats.html, admin_products.html, hh.html, medkit.html, nutrition.html
- `.btn-icon-outline` — css: style.css; разметка: enshrouded.html, medkit.html, nutrition.html
- `.btn-icon-overlay` — css: medkit.css, style.css; разметка: _medkit_grid.html, medkit.html, nutrition.html, workout_profile.html
- `.btn-icon-round` — css: style.css; разметка: medkit.html, nutrition.html, voice-input.js
- `.btn-icon-sm` — css: style.css; разметка: _medkit_cats.html, _medkit_circle.html, hh.html, medkit.html, nutrition.html
- `.btn-icon-solid` — css: style.css; разметка: medkit.html, nutrition.html
- `.btn-lg` — css: style.css; разметка: —
- `.btn-primary` — css: medkit.css, profile.css, style.css; разметка: 404.html, _header.html, _medkit_circle.html, _medkit_grid.html, account_deleted.html, admin_enshrouded.html, admin_exercises.html, botamin.html, forgot_password.html, hh.html, login.html, medkit.html, nutrition.html, profile.html, register.html, reset_password.html, tool_preview.html, verify_pending.html, workout.html
- `.btn-secondary` — css: profile.css, style.css; разметка: 404.html, _ens_rows.html, _header.html, _landing_card.html, _medkit_buy.html, _medkit_circle.html, _medkit_grid.html, admin_enshrouded.html, admin_landing.html, admin_products.html, hh.html, medkit.html, nutrition.html, profile.html, tool_preview.html, verify_pending.html, verify_required.html
- `.btn-signature` — css: style.css; разметка: —
- `.btn-sm` — css: style.css; разметка: _landing_card.html, _medkit_buy.html, _medkit_circle.html, _medkit_grid.html, medkit.html, workout_profile.html
- `.btn-soft` — css: style.css; разметка: _medkit_grid.html, medkit.html
- `.chat-attach-btn` — css: nutrition.css; разметка: nutrition.html
- `.copy-btn` — css: style.css; разметка: hh.html
- `.dosie-add-btn` — css: hh.css; разметка: hh.html
- `.draft-clear-btn` — css: hh.css; разметка: hh.html
- `.ex-btn` — css: admin.css; разметка: admin_exercises.html
- `.ex-btn-approve` — css: admin.css; разметка: admin_exercises.html
- `.ex-btn-howto` — css: admin.css; разметка: admin_exercises.html
- `.ex-btn-replace` — css: admin.css; разметка: admin_exercises.html
- `.ex-btn-wrong` — css: admin.css; разметка: admin_exercises.html
- `.ex-page-btn` — css: admin.css; разметка: admin_exercises.html
- `.eye-btn` — css: style.css; разметка: login.html, nutrition.html, register.html, reset_password.html
- `.fetch-btn` — css: hh.css; разметка: hh.html
- `.food-save-btn` — css: admin.css; разметка: admin_products.html
- `.frac-btns` — css: nutrition.css; разметка: nutrition.html
- `.generate-btn` — css: hh.css; разметка: hh.html
- `.hint-btn` — css: style.css; разметка: _medkit_circle_help.html, medkit.html, nutrition.html
- `.history-copy-btn` — css: hh.css; разметка: hh.html
- `.ing-add-btn` — css: nutrition.css; разметка: nutrition.html
- `.nut-nav-btn` — css: nutrition.css; разметка: nutrition.html
- `.pmbtn` — css: hh.css; разметка: hh.html
- `.pmbtn-desc` — css: hh.css; разметка: hh.html
- `.pmbtn-title` — css: hh.css; разметка: hh.html
- `.por-edit-btn` — css: nutrition.css; разметка: nutrition.html
- `.save-btn-flush` — css: nutrition.css; разметка: nutrition.html
- `.save-btn-gap` — css: nutrition.css; разметка: nutrition.html
- `.scan-torch-btn` — css: style.css; разметка: medkit.html, nutrition.html
- `.segmented-btn` — css: medkit.css, style.css; разметка: _medkit_grid.html, enshrouded.html, hh.html, medkit.html, nutrition.html, profile.html
- `.setting-btn` — css: profile.css; разметка: profile.html
- `.slot-btn` — css: enshrouded.css; разметка: enshrouded.html
- `.tab-btn` — css: medkit.css, style.css; разметка: _admin_subnav.html, _medkit_circle.html, hh.html
- `.undo-bar-btn` — css: style.css; разметка: hh.html, medkit.html
- `.verify-resend-btn` — css: verify.css; разметка: verify_required.html
- `.voice-play-btn` — css: nutrition.css; разметка: nutrition.html
- `.warn-force-btn` — css: hh.css; разметка: hh.html
- `.water-btn` — css: nutrition.css; разметка: nutrition.html
- `.water-btn-manual` — css: nutrition.css; разметка: nutrition.html
- `.water-btns` — css: nutrition.css; разметка: nutrition.html
- `.wk-action-btn` — css: workout.css; разметка: workout.html, workout_profile.html
- `.wk-btn` — css: workout.css; разметка: workout.html
- `.wk-btn-ghost` — css: workout.css; разметка: workout.html
- `.wk-btn-primary` — css: workout.css; разметка: workout.html
- `.wk-chat-add-eq-btn` — css: workout.css; разметка: workout.html
- `.wk-chat-photo-btn` — css: workout.css; разметка: workout.html
- `.wk-complete-btn` — css: workout.css; разметка: workout.html
- `.wk-day-btn` — css: workout.css; разметка: workout.html
- `.wk-ex-altbtn` — css: workout.css; разметка: workout.html
- `.wk-ex-chartbtn` — css: workout.css; разметка: workout.html
- `.wk-ex-progbtn` — css: workout.css; разметка: workout.html
- `.wk-home-btn` — css: workout.css; разметка: workout.html, workout_profile.html
- `.wk-machine-prompt-btn` — css: workout.css; разметка: workout.html
- `.wk-machine-prompt-btns` — css: workout.css; разметка: workout.html
- `.wk-mesocycle-btn` — css: workout.css; разметка: workout.html
- `.wk-preset-btn` — css: workout.css; разметка: workout.html
- `.wk-profile-btn` — css: workout_profile.css; разметка: workout_profile.html
- `.wk-profile-btn-danger` — css: workout_profile.css; разметка: workout_profile.html
- `.wk-profile-btn-sm` — css: workout_profile.css; разметка: workout_profile.html
- `.wk-progress-keep-btn` — css: workout.css; разметка: workout.html
- `.wk-progress-suggestion-btns` — css: workout.css; разметка: workout.html
- `.wk-progress-up-btn` — css: workout.css; разметка: workout.html
- `.wk-regen-btn` — css: workout.css; разметка: workout.html
- `.wk-save-sets-btn` — css: workout.css; разметка: workout.html
- `.wk-skip-btn` — css: workout.css; разметка: workout.html
- `.wk-skip-reason-btn` — css: workout.css; разметка: workout.html
- `.wk-stuck-try-btn` — css: workout.css; разметка: workout.html
- `.wk-swap-revert-btn` — css: workout.css; разметка: workout.html
- `.wk-tip-btn` — css: workout.css; разметка: workout.html

### карточки: 87
- `.a-box` — css: nutrition.css; разметка: nutrition.html
- `.a-box-title` — css: nutrition.css; разметка: nutrition.html
- `.a-panel` — css: nutrition.css; разметка: nutrition.html
- `.a-panel-box` — css: nutrition.css; разметка: nutrition.html
- `.accent-box` — css: nutrition.css; разметка: nutrition.html
- `.accent-box-calc` — css: nutrition.css; разметка: nutrition.html
- `.accent-box-gap` — css: nutrition.css; разметка: nutrition.html
- `.accent-box-targets` — css: nutrition.css; разметка: nutrition.html
- `.admin-panel` — css: admin.css; разметка: admin_enshrouded.html, admin_products.html, admin_usage.html, admin_users.html
- `.analysis-card` — css: hh.css; разметка: hh.html
- `.apt-buy-box` — css: medkit.css; разметка: medkit.html
- `.apt-card` — css: medkit.css; разметка: _medkit_grid.html
- `.apt-card-dead` — css: medkit.css; разметка: _medkit_grid.html
- `.apt-card-foot` — css: medkit.css; разметка: _medkit_grid.html
- `.apt-doses-box` — css: medkit.css; разметка: medkit.html
- `.auth-box` — css: style.css; разметка: account_deleted.html, forgot_password.html, login.html, register.html, reset_password.html, verify_pending.html, verify_required.html
- `.auth-turnstile` — css: style.css; разметка: login.html, register.html
- `.card` — css: style.css; разметка: _landing_card.html, _medkit_buy.html, _medkit_grid.html, admin_enshrouded.html, admin_exercises.html, admin_products.html, admin_usage.html, admin_users.html, botamin.html, demo_landing.html, demo_program.html, enshrouded.html, hh.html, index.html, landing.html, nutrition.html, profile.html, tool_preview.html, workout.html, workout_profile.html
- `.card-banner` — css: enshrouded.css; разметка: enshrouded.html
- `.card-body` — css: enshrouded.css; разметка: _landing_card.html, admin_exercises.html, enshrouded.html
- `.card-compact` — css: style.css; разметка: nutrition.html
- `.card-flush` — css: style.css; разметка: _medkit_grid.html, enshrouded.html, nutrition.html
- `.card-meta` — css: enshrouded.css; разметка: _landing_card.html, admin_exercises.html, enshrouded.html
- `.card-name` — css: enshrouded.css; разметка: admin_exercises.html, enshrouded.html
- `.card-nested` — css: style.css; разметка: nutrition.html
- `.card-prog` — css: enshrouded.css; разметка: enshrouded.html
- `.card-static` — css: style.css; разметка: _landing_card.html, hh.html, nutrition.html, profile.html
- `.card-top` — css: enshrouded.css; разметка: enshrouded.html
- `.chart-box` — css: nutrition.css; разметка: nutrition.html, workout.html
- `.danger-card` — css: profile.css; разметка: profile.html
- `.dosie-view-card` — css: hh.css; разметка: hh.html
- `.ex-card` — css: admin.css; разметка: admin_exercises.html, workout.html
- `.ex-card-actions` — css: admin.css; разметка: admin_exercises.html
- `.ex-card-badge` — css: admin.css; разметка: admin_exercises.html
- `.ex-card-body` — css: admin.css; разметка: admin_exercises.html
- `.ex-card-meta` — css: admin.css; разметка: admin_exercises.html
- `.ex-card-name` — css: admin.css; разметка: admin_exercises.html
- `.ex-card-name-en` — css: admin.css; разметка: admin_exercises.html
- `.ex-card-play` — css: admin.css; разметка: admin_exercises.html
- `.ex-card-thumb` — css: admin.css; разметка: admin_exercises.html
- `.ex-card-thumb-empty` — css: admin.css; разметка: admin_exercises.html
- `.ex-card-warn` — css: admin.css; разметка: admin_exercises.html
- `.ex-video-box` — css: admin.css; разметка: admin_exercises.html
- `.fd-card` — css: nutrition.css; разметка: nutrition.html
- `.landing-card` — css: admin.css; разметка: _landing_card.html
- `.landing-card-acts` — css: admin.css; разметка: _landing_card.html
- `.landing-card-body` — css: admin.css; разметка: _landing_card.html
- `.landing-card-del` — css: admin.css; разметка: _landing_card.html
- `.landing-card-frame` — css: admin.css; разметка: _landing_card.html
- `.landing-card-meta` — css: admin.css; разметка: _landing_card.html
- `.landing-card-msg` — css: admin.css; разметка: _landing_card.html
- `.landing-card-n` — css: admin.css; разметка: _landing_card.html, admin_landing.html
- `.landing-card-sub` — css: admin.css; разметка: _landing_card.html
- `.landing-card-title` — css: admin.css; разметка: _landing_card.html
- `.macro-card` — css: nutrition.css; разметка: nutrition.html
- `.meal-card` — css: nutrition.css; разметка: nutrition.html
- `.panel` — css: hh.css; разметка: admin_enshrouded.html, admin_products.html, admin_usage.html, admin_users.html, hh.html, nutrition.html, panel-refresh.js, workout.html
- `.panel-title` — css: hh.css; разметка: hh.html, workout.html
- `.panel-title-grow` — css: hh.css; разметка: hh.html
- `.result-panel` — css: hh.css; разметка: hh.html
- `.resume-view-card` — css: hh.css; разметка: hh.html
- `.set-card` — css: enshrouded.css; разметка: enshrouded.html
- `.tab-panel` — css: hh.css; разметка: hh.html
- `.tool-card` — css: style.css; разметка: index.html
- `.tool-card-arrow` — css: style.css; разметка: index.html
- `.tool-card-desc` — css: style.css; разметка: index.html
- `.tool-card-foot` — css: style.css; разметка: index.html
- `.tool-card-icon` — css: style.css; разметка: index.html
- `.tool-card-title` — css: style.css; разметка: index.html
- `.vacancy-card` — css: hh.css; разметка: hh.html
- `.warn-box` — css: hh.css; разметка: hh.html
- `.warn-box-score` — css: hh.css; разметка: hh.html
- `.warn-box-text` — css: hh.css; разметка: hh.html
- `.water-card` — css: nutrition.css; разметка: nutrition.html
- `.wk-card` — css: workout.css; разметка: workout.html, workout_profile.html
- `.wk-chat-panel` — css: workout.css; разметка: workout.html
- `.wk-done-panel` — css: workout.css; разметка: workout.html
- `.wk-eq-card` — css: workout.css; разметка: workout.html, workout_profile.html
- `.wk-ex-card` — css: workout.css; разметка: workout.html
- `.wk-light-checkbox` — css: workout.css; разметка: workout.html
- `.wk-nutrition-box` — css: workout.css; разметка: workout.html
- `.wk-progedit-panel` — css: workout.css; разметка: workout.html
- `.wk-progress-chart-panel` — css: workout.css; разметка: workout.html
- `.wk-skip-panel` — css: workout.css; разметка: workout.html
- `.wk-skip-panel-title` — css: workout.css; разметка: workout.html
- `.wk-warmup-card` — css: workout.css; разметка: workout.html
- `.wk-weight-chart-box` — css: workout.css; разметка: workout.html

### поля ввода: 37
- `.apt-ref-field` — css: medkit.css; разметка: medkit.html
- `.apt-search-input` — css: medkit.css; разметка: medkit.html
- `.chat-input-row` — css: nutrition.css; разметка: nutrition.html, workout.html
- `.chat-input-row-modal` — css: nutrition.css; разметка: nutrition.html
- `.compare-select` — css: nutrition.css; разметка: nutrition.html
- `.dosie-field` — css: hh.css; разметка: hh.html
- `.ens-a-field` — css: admin.css; разметка: admin_enshrouded.html
- `.ens-fields` — css: enshrouded.css; разметка: enshrouded.html
- `.ex-replace-input` — css: admin.css; разметка: admin_exercises.html
- `.f-field` — css: nutrition.css; разметка: nutrition.html
- `.f-field-wide` — css: nutrition.css; разметка: nutrition.html
- `.field-label` — css: nutrition.css, style.css; разметка: _medkit_circle.html, admin_enshrouded.html, admin_usage.html, enshrouded.html, forgot_password.html, hh.html, login.html, medkit.html, nutrition.html, register.html, reset_password.html
- `.g-input` — css: nutrition.css; разметка: nutrition.html
- `.identity-fields` — css: profile.css; разметка: profile.html
- `.input` — css: enshrouded.css, hh.css, medkit.css, nutrition.css, profile.css, style.css; разметка: _header.html, _medkit_circle.html, _medkit_who.html, admin_enshrouded.html, admin_exercises.html, admin_landing.html, admin_products.html, admin_usage.html, admin_users.html, demo_program.html, email-typo.js, enshrouded.html, header-search.js, hh.html, landing.html, medkit.html, modal.js, nutrition.html, profile.html, ui.js, workout.html, workout_profile.html
- `.input-compact` — css: style.css; разметка: enshrouded.html, hh.html, medkit.html, nutrition.html
- `.input-nested` — css: style.css; разметка: hh.html
- `.input-sm` — css: style.css; разметка: _medkit_who.html, admin_exercises.html, admin_products.html, enshrouded.html, nutrition.html
- `.input-wrap` — css: medkit.css, style.css; разметка: _medkit_circle.html, login.html, medkit.html, nutrition.html, register.html, reset_password.html
- `.scale-input` — css: nutrition.css; разметка: nutrition.html
- `.search-input-admin` — css: admin.css; разметка: _admin_head.html
- `.select` — css: admin.css, medkit.css, style.css; разметка: admin_enshrouded.html, admin_exercises.html, hh.html, medkit.html, modal.js, nutrition.html, profile.html, workout_profile.html
- `.select-arrow` — css: profile.css; разметка: profile.html
- `.select-styled` — css: profile.css; разметка: profile.html
- `.select-wrap` — css: profile.css; разметка: profile.html
- `.tag-text-input` — css: hh.css; разметка: hh.html
- `.textarea` — css: style.css; разметка: hh.html, medkit.html, modal.js
- `.textarea-compact` — css: style.css; разметка: hh.html, medkit.html
- `.textarea-grow` — css: style.css; разметка: hh.html
- `.textarea-nested` — css: style.css; разметка: hh.html
- `.tz-select` — css: profile.css; разметка: profile.html
- `.wk-chat-input` — css: workout.css; разметка: workout.html
- `.wk-chat-input-row` — css: workout.css; разметка: workout.html
- `.wk-field-gap` — css: workout_profile.css; разметка: workout_profile.html
- `.wk-machine-fixed-input` — css: workout.css; разметка: workout.html
- `.wk-photo-compare-selects` — css: workout_profile.css; разметка: workout_profile.html
- `.wk-set-input` — css: workout.css; разметка: workout.html

### вкладки: 15
- `.admin-tabs` — css: admin.css; разметка: _admin_subnav.html
- `.apt-circle-tabs` — css: medkit.css; разметка: _medkit_circle.html
- `.apt-circle-tabsrow` — css: medkit.css; разметка: _medkit_circle.html
- `.ens-tab` — css: enshrouded.css; разметка: enshrouded.html
- `.ens-tab-cnt` — css: enshrouded.css; разметка: enshrouded.html
- `.ens-tab-ico` — css: enshrouded.css; разметка: enshrouded.html
- `.ens-tabs` — css: enshrouded.css; разметка: enshrouded.html
- `.hh-tabs` — css: hh.css; разметка: hh.html
- `.nut-tab` — css: nutrition.css; разметка: nutrition.html
- `.s-tabs` — css: nutrition.css; разметка: enshrouded.html, nutrition.html
- `.tab-bar` — css: style.css; разметка: _admin_subnav.html, _medkit_circle.html, hh.html
- `.tab-bar-lg` — css: style.css; разметка: _admin_subnav.html
- `.tab-bar-sticky` — css: style.css; разметка: hh.html
- `.tab-btn` — css: medkit.css, style.css; разметка: _admin_subnav.html, _medkit_circle.html, hh.html
- `.tab-panel` — css: hh.css; разметка: hh.html

### чипы: 43
- `.analysis-score-badge` — css: hh.css; разметка: hh.html
- `.analysis-tags` — css: hh.css; разметка: hh.html
- `.apt-ai-item-ind-tag` — css: medkit.css; разметка: medkit.html
- `.apt-badge-own` — css: medkit.css; разметка: _medkit_circle.html
- `.apt-buy-tag` — css: medkit.css; разметка: _medkit_buy.html
- `.apt-buy-tag-ai` — css: medkit.css; разметка: —
- `.apt-buy-tag-expired` — css: medkit.css; разметка: —
- `.apt-buy-tag-low` — css: medkit.css; разметка: —
- `.apt-chips` — css: medkit.css; разметка: medkit.html
- `.apt-doses-tag` — css: medkit.css; разметка: medkit.html
- `.apt-own-tag` — css: medkit.css; разметка: medkit.html
- `.badge` — css: style.css; разметка: _medkit_circle.html, _medkit_grid.html, admin_exercises.html, demo_landing.html, demo_program.html, hh.html, index.html, workout.html
- `.badge-blue` — css: style.css; разметка: index.html
- `.badge-green` — css: style.css; разметка: —
- `.badge-muted` — css: style.css; разметка: _medkit_circle.html, _medkit_grid.html, index.html
- `.badge-warn` — css: style.css; разметка: hh.html
- `.chip` — css: medkit.css, nutrition.css, style.css; разметка: _admin_head.html, _medkit_cats.html, admin_enshrouded.html, demo_program.html, hh.html, medkit.html, nutrition.html, workout.html
- `.chip-danger` — css: style.css; разметка: _medkit_cats.html
- `.chip-dashed` — css: style.css; разметка: _medkit_cats.html, medkit.html
- `.chip-n` — css: style.css; разметка: _admin_head.html, _medkit_cats.html, _medkit_circle.html
- `.chip-outline` — css: style.css; разметка: admin_enshrouded.html
- `.chip-row` — css: admin.css; разметка: _admin_head.html
- `.chip-wrap` — css: style.css; разметка: hh.html
- `.ex-badge-approved` — css: admin.css; разметка: —
- `.ex-badge-no_video` — css: admin.css; разметка: —
- `.ex-badge-wrong` — css: admin.css; разметка: —
- `.ex-card-badge` — css: admin.css; разметка: admin_exercises.html
- `.lvl-tag` — css: enshrouded.css; разметка: enshrouded.html
- `.resume-badge` — css: hh.css; разметка: hh.html
- `.resume-badge-ok` — css: hh.css; разметка: hh.html
- `.resume-badge-warn` — css: hh.css; разметка: hh.html
- `.s-chips` — css: nutrition.css; разметка: nutrition.html
- `.stagger-in` — css: style.css; разметка: index.html
- `.tag-chip` — css: hh.css; разметка: hh.html
- `.tag-chip-x` — css: hh.css; разметка: hh.html
- `.tag-match` — css: hh.css; разметка: hh.html
- `.tag-miss` — css: hh.css; разметка: hh.html
- `.tag-text-input` — css: hh.css; разметка: hh.html
- `.tag-wrap` — css: hh.css; разметка: hh.html
- `.wk-day-status-badge` — css: workout.css; разметка: workout.html
- `.wk-painzone-chip` — css: workout.css; разметка: workout.html
- `.wk-pb-badge` — css: workout.css; разметка: workout.html
- `.wk-warmup-badge` — css: workout.css; разметка: workout.html

### пустые состояния: 18
- `.admin-empty` — css: admin.css; разметка: admin_enshrouded.html, admin_exercises.html, admin_landing.html, admin_products.html, admin_usage.html, admin_users.html
- `.apt-empty` — css: medkit.css; разметка: _medkit_grid.html
- `.apt-empty-find` — css: medkit.css; разметка: _medkit_grid.html, medkit.html
- `.chat-empty` — css: nutrition.css; разметка: nutrition.html
- `.empty-state` — css: style.css; разметка: _header.html, _medkit_circle.html, _medkit_grid.html, admin_enshrouded.html, admin_exercises.html, admin_landing.html, admin_products.html, admin_usage.html, admin_users.html, enshrouded.html, hh.html, nutrition.html, workout.html
- `.empty-state-block` — css: style.css; разметка: _medkit_grid.html
- `.empty-state-hero` — css: style.css; разметка: _medkit_circle.html, _medkit_grid.html, enshrouded.html, hh.html
- `.empty-state-icon` — css: style.css; разметка: _medkit_circle.html, _medkit_grid.html, enshrouded.html, hh.html
- `.empty-state-inline` — css: style.css; разметка: _header.html, nutrition.html, workout.html
- `.empty-state-sub` — css: style.css; разметка: _medkit_circle.html, _medkit_grid.html, nutrition.html
- `.empty-state-title` — css: style.css; разметка: _medkit_circle.html, _medkit_grid.html, nutrition.html
- `.empty-state-xl` — css: style.css; разметка: _medkit_circle.html
- `.ex-card-thumb-empty` — css: admin.css; разметка: admin_exercises.html
- `.meal-empty` — css: nutrition.css; разметка: nutrition.html
- `.media-slot-empty` — css: style.css; разметка: _media_slot.html
- `.nut-empty` — css: nutrition.css; разметка: nutrition.html
- `.search-empty` — css: style.css; разметка: _header.html
- `.wk-progress-chart-empty` — css: workout.css; разметка: workout.html

## 4. Шрифты в залогиненных стилях

| font-family | объявлений | файлы |
|---|---:|---|
| `var(--font)` | 55 | admin.css, hh.css, medkit.css, nutrition.css, profile.css, style.css, workout.css, workout_profile.css |
| `var(--font-mono)` | 47 | admin.css, enshrouded.css, hh.css, medkit.css, nutrition.css, profile.css, style.css, workout.css |
| `inherit` | 6 | medkit.css, nutrition.css, style.css |
| `font: inherit` | 5 | admin.css, nutrition.css, style.css, workout.css |
| `'JetBrains Mono'` | 2 | style.css |
| `'Manrope'` | 2 | style.css |
| `'Manrope Fallback'` | 1 | style.css |
| `'Manrope Fallback Android'` | 1 | style.css |
| `'JetBrains Mono Fallback'` | 1 | style.css |
| `font: 600 1rem/1 var(--font)` | 1 | style.css |

| font-weight | объявлений |
|---|---:|
| `600` | 107 |
| `700` | 55 |
| `500` | 37 |
| `800` | 11 |
| `400` | 5 |
| `400 500` | 2 |
| `400 800` | 2 |

@font-face в залогиненных стилях: style.css: 'JetBrains Mono' 400 500; style.css: 'JetBrains Mono' 400 500; style.css: 'Manrope' 400 800; style.css: 'Manrope' 400 800; style.css: 'Manrope Fallback' ?; style.css: 'Manrope Fallback Android' ?; style.css: 'JetBrains Mono Fallback' ?

## 5. Цвета инструментов (фон страницы `--surface-0` = #0A0B0D)

| инструмент | переменная | значение | к фону | наведение | тусклый | где |
|---|---|---|---:|---|---|---|
| hh | `--accent-hh` | #4F8FFF | 6.29 | #146AFF | `rgba(79,143,255,0.15)` | static/style.css:457 |
| nutrition | `--accent-nutrition` | #10B981 | 7.76 | #12D595 | `rgba(16,185,129,0.15)` | static/style.css:460 |
| medkit | `--accent-medkit` | #06B6D4 | 8.11 | #07D0F2 | `rgba(6,182,212,0.15)` | static/style.css:474 |
| enshrouded | `--accent-enshrouded` | #D97706 | 6.18 | #A25904 | `rgba(217,119,6,0.15)` | static/style.css:466 |
| workout | `--accent-workout` | #F59E0B | 9.17 | #F6AA28 | `rgba(245,158,11,0.15)` | static/style.css:463 |

Классы тем объявляют `--tool-accent`, `--tool-accent-dim`, `--tool-accent-hover`, `--tool-accent-ink` (style.css, блоки `.theme-*`).

## 6. Светлая тема

| признак | совпадений в static/*.css, static/*.js, templates, main.py, database.py |
|---|---:|
| `html\.light` | 0 |
| `\.theme-light` | 0 |
| `data-theme=\"light` | 0 |
| `prefers-color-scheme\s*:\s*light` | 0 |
| `theme\.js` | 0 |
| `localStorage\.\w+\(\s*['\"][^'\"]*them` | 0 |

`color-scheme` в коде: workout.css: dark×2, workout_profile.css: dark×1

## 7. design-system.md §13 (скелет :root) против static/style.css

- токенов в скелете §13: 99; в `:root` кода: 100
- есть в коде, нет в скелете: ['--surface-sunken']
- есть в скелете, нет в коде: нет
- значение расходится: нет
- строк в design-system.md: 5766; разделов верхнего уровня: 15

## 8. Скриншоты «до» (review_screenshots/redesign-before/, в git не входят — §8.0)

Кадров: 14 — enshrouded-1920.png, enshrouded-390.png, hh-1920.png, hh-390.png, launcher-1920.png, launcher-390.png, medkit-1920.png, medkit-390.png, nutrition-1920.png, nutrition-390.png, profile-1920.png, profile-390.png, workout-1920.png, workout-390.png
