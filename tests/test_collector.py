import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

from app.client import DeribitError
from app.collector import PriceCollector
from app.schemas import Ticker


async def test_collection_saves_both_prices_and_observation_time():
    client = AsyncMock()
    client.get_index_price.side_effect = [Decimal("100"), Decimal("20")]
    repository = AsyncMock()
    collector = PriceCollector(client, repository, clock=lambda: 1234.9)
    assert await collector.collect_once() == 2
    repository.save.assert_any_await(Ticker.BTC_USD, Decimal("100"), 1234)
    repository.save.assert_any_await(Ticker.ETH_USD, Decimal("20"), 1234)


async def test_one_exchange_failure_does_not_block_other_ticker():
    client = AsyncMock()
    client.get_index_price.side_effect = [DeribitError("offline"), Decimal("20")]
    repository = AsyncMock()
    collector = PriceCollector(client, repository)
    assert await collector.collect_once() == 1
    assert repository.save.await_args.args[0] == Ticker.ETH_USD


async def test_periodic_loop_can_stop_without_waiting_full_interval():
    client = AsyncMock()
    client.get_index_price.return_value = Decimal("100")
    repository = AsyncMock()
    collector = PriceCollector(client, repository, interval_seconds=60)
    task = asyncio.create_task(collector.run())
    for _ in range(100):
        if repository.save.await_count == 2:
            break
        await asyncio.sleep(0.001)
    collector.stop()
    await asyncio.wait_for(task, timeout=1)
    assert repository.save.await_count == 2
