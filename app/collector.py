import asyncio
import logging
import time
from collections.abc import Callable
from contextlib import suppress

from sqlalchemy.exc import SQLAlchemyError

from app.client import DeribitClient, DeribitError
from app.repository import PriceRepository
from app.schemas import Ticker


class PriceCollector:
    def __init__(
        self,
        client: DeribitClient,
        repository: PriceRepository,
        interval_seconds: float = 60,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._client = client
        self._repository = repository
        self._interval_seconds = interval_seconds
        self._clock = clock
        self._stop = asyncio.Event()
        self._logger = logging.getLogger(__name__)

    async def collect_once(self) -> int:
        saved = 0
        for ticker in Ticker:
            if self._stop.is_set():
                break
            try:
                price = await self._client.get_index_price(ticker)
                # This is our observation time, not the time of a market trade.
                await self._repository.save(ticker, price, int(self._clock()))
                saved += 1
                self._logger.info("Saved index price for %s", ticker.value)
            except (DeribitError, SQLAlchemyError):
                self._logger.exception("Could not collect %s; other tickers continue", ticker.value)
        return saved

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        while not self._stop.is_set():
            started = loop.time()
            await self.collect_once()
            delay = max(0, self._interval_seconds - (loop.time() - started))
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=delay)

    def stop(self) -> None:
        self._stop.set()
