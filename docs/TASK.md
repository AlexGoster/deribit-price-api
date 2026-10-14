# Соответствие заданию

Требования переписаны из предоставленного скриншота. Контакты работодателя и
личные данные в репозиторий не включаются.

| Требование | Реализация |
|---|---|
| Каждую минуту btc_usd и eth_usd из Deribit | `PriceCollector`, интервал 60 секунд |
| Именно index price | `public/get_index_price`, `result.index_price` |
| Тикер, цена, UNIX timestamp | Модель `Price` |
| PostgreSQL | Compose `postgres:16-alpine`, asyncpg, SQLAlchemy |
| Внешнее API на FastAPI | `/prices`, `/prices/latest`, `/prices/by-date` |
| Все методы GET, ticker обязателен | Query enum без значения по умолчанию |
| Все данные валюты | `/prices?ticker=...` |
| Последняя цена | `/prices/latest?ticker=...` |
| Фильтр по дате | `/prices/by-date?ticker=...&date=YYYY-MM-DD`, день UTC |
| Без Celery | Фоновая задача asyncio в lifespan |
| Git и подробный README | Публичный GitHub, README, Design decisions |
| Unit-тесты (дополнительно) | pytest, локальный HTTP-сервер, временная БД |
| Два контейнера (дополнительно) | app и db |
| aiohttp (дополнительно) | Переиспользуемая ClientSession |
| OOP, чистые имена, отсутствие глобального состояния | Классы с явными зависимостями, app factory |

Неоднозначные детали явно зафиксированы в README: трактовка даты, время
наблюдения, округление цены и однопроцессный запуск сборщика.
