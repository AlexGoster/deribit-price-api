import asyncio
import json
import logging
from decimal import Decimal, InvalidOperation

import aiohttp

from app.schemas import Ticker


class DeribitError(Exception):
    """A request did not yield a valid positive index price."""


class RetryableDeribitError(DeribitError):
    pass


class DeribitClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        retry_attempts: int = 3,
        retry_delay_seconds: float = 1,
    ) -> None:
        self._session = session
        self._url = f"{base_url.rstrip('/')}/public/get_index_price"
        self._retry_attempts = retry_attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._max_response_bytes = 64 * 1024
        self._logger = logging.getLogger(__name__)

    async def get_index_price(self, ticker: Ticker) -> Decimal:
        for attempt in range(self._retry_attempts):
            try:
                return await self._request(ticker)
            except (TimeoutError, aiohttp.ClientError, RetryableDeribitError) as error:
                if attempt + 1 == self._retry_attempts:
                    raise DeribitError(f"Request failed after {attempt + 1} attempts") from error
                self._logger.warning("Retrying Deribit request for %s", ticker.value)
                await asyncio.sleep(self._retry_delay_seconds * 2**attempt)
        raise DeribitError("No request attempts configured")

    async def _request(self, ticker: Ticker) -> Decimal:
        async with self._session.get(
            self._url, params={"index_name": ticker.value}, allow_redirects=False
        ) as response:
            if response.status == 429 or response.status >= 500:
                raise RetryableDeribitError(f"Deribit HTTP {response.status}")
            if response.status != 200:
                raise DeribitError(f"Deribit HTTP {response.status}")
            body = bytearray()
            async for chunk in response.content.iter_chunked(8192):
                if len(body) + len(chunk) > self._max_response_bytes:
                    raise DeribitError("Deribit response exceeds 64 KiB")
                body.extend(chunk)
            try:
                payload = json.loads(body, parse_float=Decimal)
            except (ValueError, UnicodeError, RecursionError, InvalidOperation) as error:
                raise DeribitError("Invalid JSON response") from error
        if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
            raise DeribitError("Invalid JSON-RPC response")
        if "error" in payload:
            raise DeribitError("Deribit JSON-RPC error")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise DeribitError("Missing result object")
        raw_price = result.get("index_price")
        if isinstance(raw_price, bool) or not isinstance(raw_price, (Decimal, int, float)):
            raise DeribitError("Missing or invalid index_price")
        try:
            price = Decimal(str(raw_price))
        except InvalidOperation as error:
            raise DeribitError("Invalid price number") from error
        if not price.is_finite() or price <= 0 or price >= Decimal("1000000000000"):
            raise DeribitError("Price outside storage range")
        try:
            price = price.quantize(Decimal("0.00000001"))
        except InvalidOperation as error:
            raise DeribitError("Price outside storage precision") from error
        if price <= 0 or price >= Decimal("1000000000000"):
            raise DeribitError("Price outside storage precision")
        return price
