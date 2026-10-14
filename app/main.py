import asyncio
import logging
from contextlib import asynccontextmanager, suppress

import aiohttp
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api import create_router
from app.client import DeribitClient
from app.collector import PriceCollector
from app.config import Settings
from app.database import Database
from app.repository import PriceRepository


def create_app(settings: Settings | None = None) -> FastAPI:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    config = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        database = Database(config.database_url)
        try:
            await database.initialize()
            repository = PriceRepository(database.sessions)
            application.state.repository = repository
            application.state.database = database
            if not config.collector_enabled:
                yield
                return
            timeout = aiohttp.ClientTimeout(total=config.request_timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                client = DeribitClient(
                    session,
                    config.deribit_base_url,
                    config.retry_attempts,
                    config.retry_delay_seconds,
                )
                collector = PriceCollector(client, repository, config.poll_interval_seconds)
                task = asyncio.create_task(collector.run(), name="deribit-price-collector")
                application.state.collector = collector
                try:
                    yield
                finally:
                    collector.stop()
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
        finally:
            await database.close()

    application = FastAPI(
        title="Deribit Index Price API",
        version="1.0.0",
        description="Сохранённые индексные цены btc_usd и eth_usd. Время — UNIX seconds UTC.",
        lifespan=lifespan,
    )
    application.include_router(create_router())

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError) -> JSONResponse:
        logging.getLogger(__name__).error("Database operation failed", exc_info=error)
        return JSONResponse(status_code=503, content={"detail": "Database temporarily unavailable"})

    return application
