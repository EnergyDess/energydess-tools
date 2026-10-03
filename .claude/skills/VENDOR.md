# Сторонние скиллы — откуда, под какой лицензией, что изменено

Заведено 2026-10-03, письмо M1 (BACKLOG №384). Это СПРАВОЧНЫЕ материалы.
В проекте главнее `energydess-motion/SKILL.md`: при противоречии его
токенам и запретам побеждает он. Эта строка вставлена в начало каждого
`SKILL.md` ниже — других изменений в текстах нет.

| Папка | Источник (коммит) | Лицензия | Что взято |
|---|---|---|---|
| `animate`, `animation-vocabulary`, `find-animation-opportunities`, `improve-animations`, `review-animations`, `emil-design-eng` | github.com/emilkowalski/skills (e8a175d) | MIT, © 2026 Emil Kowalski | только `.md`; не взяты `animate-expo`, `apple-design`, `mobile-native`, `write-swift`, `ask-sonner`, `break-ui`, `pick-ui-library`, `prototype` — к вебу без библиотек не относятся |
| `impeccable` | github.com/pbakaus/impeccable (e103efe), `.claude/skills/impeccable` | Apache-2.0 (файлы `LICENSE`, `NOTICE.md`) | только `.md`; папка `scripts/` (CLI на Node) не взята — режимы, которые её зовут (live, generate), в проекте не работают |
| `taste-skill` | github.com/Leonxlnx/taste-skill (ce26fc2), `skills/taste-skill` | MIT, © 2026 Leonxlnx | только основной скилл; не взяты варианты с GSAP, случайной вёрсткой и генерацией картинок — прямо спорят с нашими запретами |

Изменение копий (требование Apache-2.0 §4b): в каждый `SKILL.md` после
фронтматтера добавлена одна цитата о старшинстве `energydess-motion`.

Обновить: клонировать источник, скопировать `.md` поверх, вернуть строку
о старшинстве, поправить коммит в таблице.
