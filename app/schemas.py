from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Ticker(StrEnum):
    BTC_USD = "btc_usd"
    ETH_USD = "eth_usd"


class PriceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: Ticker
    price: Decimal
    timestamp: int
