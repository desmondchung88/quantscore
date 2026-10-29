"""Request bodies. Validation happens here so the services and the SQL
never see an unchecked value."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def clean_username(cls, v: str) -> str:
        v = v.strip()
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username may contain letters, digits, _ and - only")
        return v

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Enter a valid email address")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    initial_cash: float = Field(default=100_000, gt=0, le=1_000_000_000)
    currency_code: str = Field(default="USD", min_length=3, max_length=3)


class PortfolioRename(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TradeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    side: Literal["BUY", "SELL"]
    quantity: float = Field(gt=0, le=10_000_000)

    @field_validator("ticker")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.strip().upper()


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class WatchlistTicker(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)

    @field_validator("ticker")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.strip().upper()


class ScreenerRequest(BaseModel):
    # Numeric bounds -- the service maps these onto allow-listed columns.
    min_market_cap: float | None = None
    max_market_cap: float | None = None
    min_pe_ratio: float | None = None
    max_pe_ratio: float | None = None
    min_price_sales_ratio: float | None = None
    max_price_sales_ratio: float | None = None
    min_price_book_ratio: float | None = None
    max_price_book_ratio: float | None = None
    min_dividend_yield: float | None = None
    max_dividend_yield: float | None = None
    min_eps: float | None = None
    max_eps: float | None = None
    min_ret_1y: float | None = None
    max_ret_1y: float | None = None
    min_ret_1m: float | None = None
    max_ret_1m: float | None = None
    min_vol_30d: float | None = None
    max_vol_30d: float | None = None
    min_last_close: float | None = None
    max_last_close: float | None = None
    min_total_score: float | None = None
    max_total_score: float | None = None
    min_valuation_score: float | None = None
    min_profitability_score: float | None = None
    min_growth_score: float | None = None
    min_dividend_score: float | None = None

    sectors: list[str] | None = None
    grades: list[str] | None = None
    search: str | None = None
    exclude_null_pe: bool = False

    sort_by: str = "total_score"
    sort_dir: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class CompareRequest(BaseModel):
    tickers: list[str] = Field(min_length=1, max_length=8)


class WeightsRequest(BaseModel):
    valuation: float = Field(default=0.30, ge=0, le=1)
    profitability: float = Field(default=0.25, ge=0, le=1)
    growth: float = Field(default=0.25, ge=0, le=1)
    dividend: float = Field(default=0.20, ge=0, le=1)


class NoteCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=1, max_length=20_000)
    ticker: str | None = Field(default=None, max_length=10)
    tags: list[str] | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    price_target: dict[str, Any] | None = None
    conviction: str | None = None
    horizon: str | None = None


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=20_000)
    ticker: str | None = Field(default=None, max_length=10)
    tags: list[str] | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    price_target: dict[str, Any] | None = None
    conviction: str | None = None
    horizon: str | None = None
