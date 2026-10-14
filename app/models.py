from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, Index, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Price(Base):
    __tablename__ = "prices"
    __table_args__ = (
        CheckConstraint("price > 0", name="ck_prices_positive"),
        CheckConstraint("timestamp >= 0", name="ck_prices_timestamp"),
        CheckConstraint("ticker IN ('btc_usd', 'eth_usd')", name="ck_prices_ticker"),
        Index("ix_prices_ticker_timestamp_id", "ticker", "timestamp", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    timestamp: Mapped[int] = mapped_column(BigInteger, nullable=False)
