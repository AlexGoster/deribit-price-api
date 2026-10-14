from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.models import Price
from app.repository import PriceRepository
from app.schemas import PriceResponse, Ticker


def get_repository(request: Request) -> PriceRepository:
    return request.app.state.repository


def create_router() -> APIRouter:
    router = APIRouter(prefix="/prices", tags=["Prices"])

    @router.get("", response_model=list[PriceResponse], summary="Все цены валюты")
    async def all_prices(
        ticker: Annotated[Ticker, Query(description="btc_usd или eth_usd")],
        repository: Annotated[PriceRepository, Depends(get_repository)],
    ) -> list[Price]:
        return await repository.list_all(ticker)

    @router.get("/latest", response_model=PriceResponse, summary="Последняя сохранённая цена")
    async def latest_price(
        ticker: Annotated[Ticker, Query()],
        repository: Annotated[PriceRepository, Depends(get_repository)],
    ) -> Price:
        record = await repository.latest(ticker)
        if record is None:
            raise HTTPException(status_code=404, detail="No stored prices for this ticker")
        return record

    @router.get(
        "/by-date", response_model=list[PriceResponse], summary="Цены за календарный день UTC"
    )
    async def prices_by_date(
        ticker: Annotated[Ticker, Query()],
        requested_date: Annotated[date, Query(alias="date", description="YYYY-MM-DD, день в UTC")],
        repository: Annotated[PriceRepository, Depends(get_repository)],
    ) -> list[Price]:
        if requested_date == date.max:
            raise HTTPException(status_code=422, detail="Date must be earlier than 9999-12-31")
        return await repository.list_by_date(ticker, requested_date)

    return router
