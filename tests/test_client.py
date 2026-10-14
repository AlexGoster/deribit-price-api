from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock

import aiohttp
import pytest
from aiohttp import web

from app.client import DeribitClient, DeribitError
from app.schemas import Ticker


@asynccontextmanager
async def exchange_server(handler):
    application = web.Application()
    application.router.add_get("/public/get_index_price", handler)
    runner = web.AppRunner(application)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        await runner.cleanup()


async def test_real_http_contract_and_retry():
    statuses = [429, 503, 200]
    tickers = []

    async def handler(request):
        tickers.append(request.query["index_name"])
        return web.Response(
            status=statuses.pop(0),
            text='{"jsonrpc":"2.0","result":'
            '{"index_price":123.12345678,"estimated_delivery_price":999}}',
        )

    async with exchange_server(handler) as url, aiohttp.ClientSession() as session:
        client = DeribitClient(session, url, retry_delay_seconds=0)
        assert await client.get_index_price(Ticker.BTC_USD) == Decimal("123.12345678")
    assert tickers == ["btc_usd"] * 3


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[]",
        '{"jsonrpc":"2.0","error":{"code":1}}',
        '{"jsonrpc":"2.0","result":{}}',
        '{"jsonrpc":"2.0","result":{"index_price":true}}',
        '{"jsonrpc":"2.0","result":{"index_price":"100"}}',
        '{"jsonrpc":"2.0","result":{"index_price":-1}}',
        '{"jsonrpc":"2.0","result":{"index_price":NaN}}',
        '{"jsonrpc":"2.0","result":{"index_price":1000000000000}}',
        '{"jsonrpc":"2.0","result":{"index_price":0.000000001}}',
        pytest.param(
            '{"jsonrpc":"2.0","result":{"index_price":1e999999999999999999999}}',
            id="extreme-exponent",
        ),
        pytest.param("[" * 2000 + "0" + "]" * 2000, id="deep-nesting"),
        pytest.param(
            " " * (64 * 1024) + '{"jsonrpc":"2.0","result":{"index_price":100}}',
            id="oversized-response",
        ),
    ],
)
async def test_invalid_exchange_data_is_rejected(body):
    async def handler(request):
        assert request.query["index_name"] == "eth_usd"
        return web.Response(text=body)

    async with exchange_server(handler) as url, aiohttp.ClientSession() as session:
        with pytest.raises(DeribitError):
            await DeribitClient(session, url).get_index_price(Ticker.ETH_USD)


async def test_timeout_has_bounded_retries():
    async with aiohttp.ClientSession() as session:
        client = DeribitClient(session, "https://www.deribit.com/api/v2", retry_delay_seconds=0)
        request = AsyncMock(side_effect=TimeoutError())
        client._request = request
        with pytest.raises(DeribitError, match="3 attempts"):
            await client.get_index_price(Ticker.BTC_USD)
    assert request.await_count == 3


async def test_permanent_http_error_is_not_retried():
    attempts = []

    async def handler(request):
        attempts.append(request)
        return web.Response(status=400)

    async with exchange_server(handler) as url, aiohttp.ClientSession() as session:
        with pytest.raises(DeribitError, match="HTTP 400"):
            await DeribitClient(session, url).get_index_price(Ticker.BTC_USD)
    assert len(attempts) == 1
