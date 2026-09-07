FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ── КАКОЙ КОММИТ В ЭТОМ ОБРАЗЕ (BACKLOG №245, E.5) ───────────────────
# `.git/` в образ НЕ едет (`.dockerignore`), поэтому спросить об этом
# git внутри контейнера нельзя — и `/version` отвечал «unknown» с
# первого дня, а ось коммита у `check_deploy.py` была слепа. Отпечаток
# впекается на сборке: `deploy.yml` передаёт `--build-arg`.
# Умолчание «unknown» намеренно: собранный вручную образ обязан
# говорить, что отпечатка у него нет, а не выдавать чужой.
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=$GIT_COMMIT

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
