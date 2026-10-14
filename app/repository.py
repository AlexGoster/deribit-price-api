from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Price
from app.schemas import Ticker


class PriceRepository:
    """One short-lived session per operation: safe for concurrent HTTP requests."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def save(self, ticker: Ticker, price: Decimal, timestamp: int) -> Price:
        record = Price(ticker=ticker.value, price=price, timestamp=timestamp)
        async with self._sessions() as session, session.begin():
            session.add(record)
            await session.flush()
        return record

    async def list_all(self, ticker: Ticker) -> list[Price]:
        statement = (
            select(Price).where(Price.ticker == ticker.value).order_by(Price.timestamp, Price.id)
        )
        async with self._sessions() as session:
            return list((await session.scalars(statement)).all())

    async def latest(self, ticker: Ticker) -> Price | None:
        statement = (
            select(Price)
            .where(Price.ticker == ticker.value)
            .order_by(Price.timestamp.desc(), Price.id.desc())
            .limit(1)
        )
        async with self._sessions() as session:
            return await session.scalar(statement)

    async def list_by_date(self, ticker: Ticker, day: date) -> list[Price]:
        # Half-open UTC interval includes midnight and excludes the next day.
        start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        end = start + timedelta(days=1)
        epoch = datetime(1970, 1, 1, tzinfo=UTC)
        start_timestamp = int((start - epoch).total_seconds())
        end_timestamp = int((end - epoch).total_seconds())
        statement = (
            select(Price)
            .where(
                Price.ticker == ticker.value,
                Price.timestamp >= start_timestamp,
                Price.timestamp < end_timestamp,
            )
            .order_by(Price.timestamp, Price.id)
        )
        async with self._sessions() as session:
            return list((await session.scalars(statement)).all())
