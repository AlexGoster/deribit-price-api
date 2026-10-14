import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

from app.config import Settings
from app.main import create_app
from app.schemas import Ticker


async def test_lifespan_starts_and_cancels_collector(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.client.DeribitClient.get_index_price", AsyncMock(return_value=Decimal("100"))
    )
    application = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'lifespan.db'}",
            collector_enabled=True,
            _env_file=None,
        )
    )
    async with application.router.lifespan_context(application):
        for _ in range(100):
            latest = await application.state.repository.latest(Ticker.ETH_USD)
            if latest:
                break
            await asyncio.sleep(0.01)
        assert latest is not None
        assert latest.price == Decimal("100")
        assert any(task.get_name() == "deribit-price-collector" for task in asyncio.all_tasks())
    assert not any(task.get_name() == "deribit-price-collector" for task in asyncio.all_tasks())
