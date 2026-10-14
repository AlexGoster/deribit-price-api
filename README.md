# Deribit Index Price API

Тестовое задание на Junior Python Backend: получение индексных цен `btc_usd` и
`eth_usd` каждую минуту, хранение в PostgreSQL и API на FastAPI. Клиент написан на
aiohttp, периодический сбор — на asyncio, без Celery. Приложение и база запускаются
в **двух контейнерах**.

## Быстрый запуск

Нужны Git и Docker Desktop с включёнными Linux containers / Docker Compose.

```sh
git clone https://github.com/AlexGoster/deribit-price-api.git
cd deribit-price-api
cp .env.example .env
docker compose up --build -d
docker compose logs -f app
```

В PowerShell вместо `cp` можно использовать `Copy-Item .env.example .env`.
Откройте [Swagger UI](http://localhost:8000/docs) или
[ReDoc](http://localhost:8000/redoc). Первый сбор происходит сразу после запуска,
затем каждые 60 секунд. Если биржа недоступна, API работает, но новых записей нет;
причина видна в `docker compose logs app`. История до запуска не загружается.

В `.env` задайте свой `POSTGRES_PASSWORD`. Шаблон содержит только демонстрационный
пароль. Для Compose используйте пароль из букв и цифр; специальные символы в
`DATABASE_URL` требуют URL-кодирования при запуске вне Docker. В Compose адрес БД
собирается из `POSTGRES_*`, поэтому `DATABASE_URL` из файла нужен только для
локального запуска Python. Если порт занят, добавьте `APP_PORT=8015` в `.env` и
открывайте `http://localhost:8015/docs`.

```sh
docker compose ps
docker compose stop
docker compose start
docker compose down
```

`down` сохраняет данные в именованном томе. `down -v` **удаляет историю**.
PostgreSQL не публикует порт на компьютер, API доступно только через localhost.
Это демонстрационный локальный запуск; публичный сервер потребует HTTPS, контроля
доступа, ограничений запросов и резервных копий.

## API

Каждый метод получения цен — GET с обязательным query-параметром `ticker`:

| Метод | Пример | Ответ |
|---|---|---|
| Вся история | `/prices?ticker=btc_usd` | Массив, сортировка по времени и id |
| Последняя цена | `/prices/latest?ticker=eth_usd` | Объект; 404, если записей нет |
| За дату | `/prices/by-date?ticker=btc_usd&date=2026-10-14` | Массив за календарный день UTC |

Поддерживаются только `btc_usd` и `eth_usd`, в нижнем регистре. Отсутствующий или
неизвестный ticker, отсутствующая/некорректная дата дают 422. Пустая история — `[]`.
Недоступность БД при запросе — 503 без внутренних подробностей в ответе.
Дата имеет формат `YYYY-MM-DD`. День включает начало суток и исключает начало
следующих: `[00:00:00 UTC, 00:00:00 UTC следующего дня)`. Максимальная дата
`9999-12-31` не поддерживается, поскольку невозможно вычислить следующий день.

Пример структуры (значения ниже иллюстративные):

```json
{"id": 1, "ticker": "btc_usd", "price": "65000.12345678", "timestamp": 1791936000}
```

`price` — десятичная **строка** в JSON, чтобы не терять точность при преобразовании
во float. В БД это `NUMERIC(20,8)`, в Python — Decimal. `timestamp` — целое число
секунд UNIX, время наблюдения после успешного ответа биржи, не время сделки.

PowerShell:

```powershell
Invoke-RestMethod 'http://localhost:8000/prices?ticker=btc_usd'
Invoke-RestMethod 'http://localhost:8000/prices/latest?ticker=eth_usd'
$day = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd')
Invoke-RestMethod "http://localhost:8000/prices/by-date?ticker=btc_usd&date=$day"
```

curl (Linux/macOS):

```sh
curl 'http://localhost:8000/prices?ticker=btc_usd'
curl 'http://localhost:8000/prices/latest?ticker=eth_usd'
curl 'http://localhost:8000/prices/by-date?ticker=btc_usd&date=2026-10-14'
```

## Design decisions

1. **Index price.** Использован официальный
   [public/get_index_price](https://docs.deribit.com/api-reference/market-data/public-get_index_price),
   параметр `index_name`, поле `result.index_price`. Это индекс USD, а не цена
   последней сделки или `estimated_delivery_price`. Авторизация Deribit не нужна.
2. **Неоднозначность даты.** ТЗ не определяет диапазон или точное время. Выбран
   календарный день UTC; контракт явно описан выше и проверяется тестом границ.
   Слова «git» в ТЗ достаточно для репозитория Git; результат размещён на GitHub.
3. **Простые слои.** DeribitClient отвечает за HTTP и проверку данных,
   PriceRepository — за SQL, PriceCollector — за расписание, роуты — за HTTP API.
   Зависимости передаются через конструкторы и FastAPI Depends. Нет глобального
   изменяемого экземпляра приложения, соединения или сборщика: `create_app`
   создаёт их, lifespan управляет временем жизни.
4. **asyncio в одном процессе.** Сбор начинается сразу. Следующий цикл учитывает
   длительность предыдущего, используя монотонные часы. Если цикл занял больше
   минуты, следующий начинается сразу без накопления пропущенных запусков.
   Тикеры обрабатываются последовательно, сбой одного не блокирует другой.
   На завершении задача отменяется, сессия HTTP и пул БД закрываются.
   Запускается ровно один Uvicorn worker: несколько работников или реплик
   создали бы несколько сборщиков. Для масштабирования сборщик следует вынести.
5. **Надёжность HTTP.** Общий таймаут запроса по умолчанию 10 секунд. Сетевые сбои,
   429 и 5xx повторяются максимум три раза с задержками 1 и 2 секунды. Остальные
   HTTP ошибки и невалидный JSON/JSON-RPC не повторяются. Перенаправления отключены,
   HTTPS проверяет сертификат. Неверная, отрицательная, бесконечная или не помещающаяся
   в NUMERIC цена не сохраняется; округление до восьми знаков — Decimal half-even.
   Старая последняя цена остаётся доступной, её свежесть определяется timestamp.
6. **PostgreSQL.** Короткая отдельная сессия и транзакция для каждого сохранения.
   Ограничения БД проверяют тикер, положительную цену и неотрицательное время.
   Индекс `(ticker, timestamp, id)` помогает выборкам; при одинаковом времени
   последней считается запись с большим id. Дубликаты наблюдений по времени
   разрешены: время в секундах не является уникальным идентификатором.
7. **Создание схемы.** Для небольшого тестового применяется `create_all` при
   старте. Оно создаёт таблицу, но не изменяет существующую схему. Для дальнейшего
   развития нужны миграции Alembic. SQLite используется только в быстрых тестах;
   Docker и CI проверяют PostgreSQL.
8. **Объём истории.** Метод возвращает все записи согласно ТЗ. В длительно
   работающем сервисе стоит согласовать пагинацию и срок хранения: без них ответ
   будет увеличиваться. Здесь этот контракт намеренно не меняется.
9. **Безопасность конфигурации.** `.env` исключён из Git и Docker build context,
   ключи биржи не используются, SQL составляется SQLAlchemy с параметрами,
   приложение в контейнере работает от непривилегированного пользователя.
   Доступа к важным файлам пользователя сервису не требуется.

## Структура

```text
app/
  main.py        — factory и lifespan
  config.py      — настройки и валидация
  client.py      — aiohttp-клиент Deribit
  collector.py   — периодический сбор
  database.py    — engine и session factory
  models.py      — таблица PostgreSQL
  repository.py  — сохранение и выборки
  schemas.py     — ticker и формат ответа
  api.py         — три GET-метода
tests/           — HTTP-контракт, репозиторий, клиент, сборщик
docs/EXPLAIN.md   — разбор для демонстрации и собеседования
```

## Тестирование и запуск без контейнера приложения

Python 3.12. БД для запуска приложения всё равно должна быть PostgreSQL.

```sh
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m pytest --cov=app --cov-report=term-missing
```

Без `TEST_DATABASE_URL` тесты используют временную SQLite. Для проверки PostgreSQL
задайте `TEST_DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DB`.
Тесты создают отдельную случайную схему на каждый тест и удаляют только её;
пользователю БД нужно право CREATE. GitHub Actions запускает этот вариант.

Для приложения скопируйте `.env.example` в `.env`, укажите настоящий
`DATABASE_URL` своей PostgreSQL и выполните:

```sh
python -m pip install -r requirements.txt
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

`requirements.txt` и `requirements-dev.txt` фиксируют версии и транзитивные
зависимости; `.in` содержит исходные ограничения для осознанного обновления.
Параметры сборщика описаны в `.env.example`. `COLLECTOR_ENABLED=false` позволяет
запустить API над существующей историей без запросов к бирже.
