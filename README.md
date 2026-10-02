# Meeting Skills Assistant

Заметки совещания → классификация скилла (DeepSeek) → протокол → `.docx`.

## Как это работает

1. На вход подаются **неструктурированные** заметки встречи.
2. DeepSeek-классификатор читает только `description` скиллов и выбирает подходящий (или `none`).
3. Если выбран скилл — в system prompt подставляется тело `SKILL.md` (+ `references/` при наличии).
4. Модель возвращает протокол в жёстком markdown-формате.
5. Код парсит протокол и собирает Word (`.docx`).

Отдельная ручка `/export/docx` нужна, чтобы прогнать уже готовый протокол в Word **без** LLM (удобно для отладки конвертера).

## Запуск

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # вписать DEEPSEEK_API_KEY
uvicorn src.app:app --reload --port 8000
```

Или Docker:

```powershell
docker compose up --build
```

- Swagger: http://localhost:8000/docs  
- Тесты: `pytest -q`

## API

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/health` | проверка, что сервис жив |
| GET | `/skills?q=` | список скиллов (+ поиск по name/caption) |
| POST | `/skills/reload` | перезагрузка реестра с диска |
| POST | `/assistant/process` | основной сценарий: заметки → протокол → docx |
| POST | `/export/docx` | готовый markdown-протокол → файл Word |

## Как проверить

Удобнее всего через Swagger: http://localhost:8000/docs  
Ниже — те же шаги в PowerShell.

### 1. Сервис жив

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Ожидание: `{ "status": "ok" }`

### 2. Реестр скиллов

```powershell
Invoke-RestMethod http://localhost:8000/skills
Invoke-RestMethod "http://localhost:8000/skills?q=протокол"
```

Ожидание: в списке есть `meeting-minutes`, поля `name`, `caption`, `description`, `has_files`.

### 3. Основной сценарий (DeepSeek + Word)

```powershell
$payload = @{
  text = "Совещание 18.03.2026. Участники: Анна (PM), Борис (backend), Кира (QA). Обсудили этапы: API, интеграция, регрессия. Решили не двигать релиз. Борис до 20.03 делает OpenAPI. Кире тест-план — срок не сказали. Анне обновить Jira."
  export_docx = $true
} | ConvertTo-Json

$result = Invoke-RestMethod http://localhost:8000/assistant/process `
  -Method POST `
  -ContentType "application/json" `
  -Body $payload

$result.skill_name
$result.reason
$result.protocol_markdown

# сохранить Word и открыть
[IO.File]::WriteAllBytes("$pwd\meeting.docx", [Convert]::FromBase64String($result.docx_base64))
Start-Process "$pwd\meeting.docx"
```

Ожидание:
- `skill_name` = `meeting-minutes`
- в протоколе секции `Метаданные` / `Обсуждение` / `Решения` / `Задачи`
- где срок не назван — `Не указан`
- `meeting.docx` открывается в Word, задачи видны таблицей

### 4. Негативный кейс классификатора

```powershell
$payload = @{
  text = "Переведи этот текст на английский"
  export_docx = $false
} | ConvertTo-Json

Invoke-RestMethod http://localhost:8000/assistant/process `
  -Method POST `
  -ContentType "application/json" `
  -Body $payload
```

Ожидание: `skill_name` = `null` (скилл не выбран).

### 5. Экспорт Word без LLM

Полезно, если протокол уже есть и нужно только проверить конвертер:

```powershell
$body = @{
  protocol_markdown = @"
# Протокол встречи

## Метаданные
- Дата: 18.03.2026
- Участники: Анна, Борис

## Обсуждение
Обсудили API.

## Решения
1. Не двигать релиз.

## Задачи
| Задача | Ответственный | Срок |
|--------|---------------|------|
| OpenAPI | Борис | 20.03 |
| Jira | Не указан | Не указан |
"@
} | ConvertTo-Json

Invoke-WebRequest http://localhost:8000/export/docx `
  -Method POST `
  -ContentType "application/json" `
  -Body $body `
  -OutFile protocol.docx

Start-Process .\protocol.docx
```

### 6. Автотесты

```powershell
pytest -q
```

Покрывают валидацию скиллов (битое имя, пустое тело, длинный description, нет `SKILL.md`) и сборку Word с пропущенными полями.

## Структура

```
skills/meeting-minutes/   # SKILL.md, references/, eval_queries.md
src/
  app.py                  # FastAPI
  skills.py               # загрузка + реестр
  assistant.py            # classify → skill → protocol
  deepseek.py
  protocol.py             # parse + docx
tests/
```

## Важно

- В репозиторий кладётся только `.env.example`, не `.env` с ключом.
- Без `DEEPSEEK_API_KEY` работают `/skills` и `/export/docx`; `/assistant/process` вернёт `503`.
