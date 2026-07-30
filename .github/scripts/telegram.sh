#!/usr/bin/env bash
# Отправка в Telegram с проверкой того, что сообщение действительно принято.
#
# Зачем отдельным файлом. Раньше каждый вызов curl был написан заново,
# и в двух из трёх мест проверки ответа не было вовсе: стояло «|| true»,
# а curl без -f считает успехом любой ответ сервера, включая 404.
# 27 июля это и произошло — уведомление о сбое ушло на URL без токена,
# Telegram ответил {"ok":false,"error_code":404}, шаг остался зелёным,
# и поломка бэкапа осталась незамеченной.
#
# Здесь проверка одна на все вызовы: и HTTP-код, и поле ok в теле.
# Telegram умеет отвечать 200 с «ok»: false, поэтому кода мало.
#
# ВАЖНО: имена переменных только латиницей — bash не поддерживает
# не-ASCII в именах и принимает такое присваивание за команду.

set -o pipefail

# Проверяет ответ Telegram. Возвращает 1 при любой неудаче.
tg_check() {
  local resp="$1" code="$2" what="$3"
  if [ "$code" != "200" ]; then
    echo "::error::Telegram не принял $what: HTTP $code, ответ: ${resp:0:300}"
    return 1
  fi
  # Без jq разобрать ответ нечем, и молчаливое «считаем неудачей» выглядело бы
  # как отказ Telegram. Пусть в логе будет настоящая причина
  if ! command -v jq >/dev/null 2>&1; then
    echo "::error::jq не установлен — ответ Telegram разобрать нечем"
    return 1
  fi
  # jq -e даёт код 1, когда результат false или null, — этого достаточно,
  # и разбирать текст ответа руками не требуется
  if ! echo "$resp" | jq -e '.ok == true' >/dev/null 2>&1; then
    echo "::error::Telegram отклонил $what: ${resp:0:300}"
    return 1
  fi
  return 0
}

# Пустой токен или chat_id дают ровно ту же картину, что была 27 июля:
# запрос уходит на битый URL и получает 404. Проверяем до отправки,
# чтобы в логе была причина, а не следствие
tg_require_secrets() {
  if [ -z "$BOT_TOKEN" ]; then
    echo "::error::Секрет TELEGRAM_BOT_TOKEN не задан"
    return 1
  fi
  if [ -z "$CHAT_ID" ]; then
    echo "::error::Секрет TELEGRAM_CHAT_ID не задан"
    return 1
  fi
  return 0
}

tg_send_message() {
  local text="$1"
  tg_require_secrets || return 1
  local out code body
  out=$(curl -sS -m 60 -w '\n%{http_code}' -X POST \
    -d "chat_id=$CHAT_ID" \
    --data-urlencode "text=$text" \
    "https://api.telegram.org/bot$BOT_TOKEN/sendMessage") || {
      echo "::error::curl не смог обратиться к Telegram (сеть или таймаут)"
      return 1
    }
  code=$(echo "$out" | tail -1)
  body=$(echo "$out" | head -n -1)
  tg_check "$body" "$code" "сообщение"
}

tg_send_document() {
  local file="$1" caption="$2"
  tg_require_secrets || return 1
  if [ ! -s "$file" ]; then
    echo "::error::Файл $file пуст или отсутствует — отправлять нечего"
    return 1
  fi
  local out code body
  # Таймаут щедрый: файл десятки мегабайт, но висеть бесконечно нельзя —
  # задача, которая не завершилась, не считается ни успехом, ни сбоем
  out=$(curl -sS -m 900 -w '\n%{http_code}' \
    -F "chat_id=$CHAT_ID" \
    -F "document=@$file" \
    -F "caption=$caption" \
    "https://api.telegram.org/bot$BOT_TOKEN/sendDocument") || {
      echo "::error::curl не смог отправить файл (сеть или таймаут)"
      return 1
    }
  code=$(echo "$out" | tail -1)
  body=$(echo "$out" | head -n -1)
  tg_check "$body" "$code" "файл" || return 1
  # Сверяем размер принятого файла с отправленным: Telegram может принять
  # запрос и сохранить не то, а «ok»: true об этом не скажет
  local sent got
  sent=$(stat -c%s "$file")
  got=$(echo "$body" | jq -r '.result.document.file_size // empty')
  if [ -n "$got" ] && [ "$got" != "$sent" ]; then
    echo "::error::Telegram принял $got байт вместо $sent — файл дошёл не целиком"
    return 1
  fi
  echo "Файл принят Telegram: $got байт"
}
