import os
from uuid import uuid4

import httpx
import pytest_asyncio
from sqlalchemy import text

from app.config import Settings
from app.main import create_app


@pytest_asyncio.fixture
async def api(tmp_path):
    url = os.environ.get("TEST_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    application = create_app(Settings(database_url=url, collector_enabled=False, _env_file=None))
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://test"
        ) as client,
    ):
        yield client, application.state.repository


@pytest_asyncio.fixture(autouse=True)
async def isolated_postgres_schema(monkeypatch):
    # Never drop a user's database or shared tables: each test owns a fresh schema.
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        yield
        return
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(url)
    schema = f"test_{uuid4().hex}"
    async with engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    def isolated_engine(database_url, **kwargs):
        if database_url == url:
            kwargs["connect_args"] = {"server_settings": {"search_path": schema}}
        return create_async_engine(database_url, **kwargs)

    monkeypatch.setattr("app.database.create_async_engine", isolated_engine)
    await engine.dispose()
    try:
        yield
    finally:
        engine = create_async_engine(url)
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()
