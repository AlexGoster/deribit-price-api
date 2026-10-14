from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.schemas import Ticker


@pytest.mark.parametrize("path", ["/prices", "/prices/latest", "/prices/by-date?date=2026-10-14"])
async def test_ticker_is_required_and_valid(api, path):
    client, _ = api
    assert (await client.get(path)).status_code == 422
    separator = "&" if "?" in path else "?"
    assert (await client.get(f"{path}{separator}ticker=bad")).status_code == 422


async def test_empty_history_and_latest(api):
    client, _ = api
    assert (await client.get("/prices?ticker=btc_usd")).json() == []
    assert (await client.get("/prices/latest?ticker=btc_usd")).status_code == 404


async def test_sorting_tie_break_and_ticker_isolation(api):
    client, repository = api
    await repository.save(Ticker.BTC_USD, Decimal("123.12345678"), 100)
    await repository.save(Ticker.ETH_USD, Decimal("999"), 300)
    await repository.save(Ticker.BTC_USD, Decimal("124"), 100)
    await repository.save(Ticker.BTC_USD, Decimal("122"), 99)
    records = (await client.get("/prices?ticker=btc_usd")).json()
    assert [row["timestamp"] for row in records] == [99, 100, 100]
    assert Decimal(records[1]["price"]) == Decimal("123.12345678")
    latest = (await client.get("/prices/latest?ticker=btc_usd")).json()
    assert latest["id"] == records[-1]["id"]


async def test_date_is_half_open_utc_day(api):
    client, repository = api
    start = int(datetime(2026, 10, 14, tzinfo=UTC).timestamp())
    for timestamp in [start - 1, start, start + 86399, start + 86400]:
        await repository.save(Ticker.BTC_USD, Decimal("10"), timestamp)
    await repository.save(Ticker.ETH_USD, Decimal("20"), start)
    response = await client.get("/prices/by-date?ticker=btc_usd&date=2026-10-14")
    assert [row["timestamp"] for row in response.json()] == [start, start + 86399]
    assert await repository.list_by_date(Ticker.BTC_USD, date(1960, 1, 1)) == []


@pytest.mark.parametrize("value", [None, "garbage", "2026-02-30", "9999-12-31"])
async def test_invalid_date(api, value):
    client, _ = api
    query = "" if value is None else f"&date={value}"
    assert (await client.get(f"/prices/by-date?ticker=btc_usd{query}")).status_code == 422


async def test_database_failure_does_not_expose_credentials(api, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    client, repository = api

    async def failing(*args):
        raise SQLAlchemyError("postgresql://private:secret@database")

    monkeypatch.setattr(repository, "list_all", failing)
    response = await client.get("/prices?ticker=btc_usd")
    assert response.status_code == 503
    assert "secret" not in response.text
