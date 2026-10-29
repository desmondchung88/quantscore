"""Central configuration, read once from the environment / .env file."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

# repo root = .../quantscore
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class Settings:
    # ---- relational -------------------------------------------------
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT: int = _int("MYSQL_PORT", 3306)
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DB: str = os.getenv("MYSQL_DB", "quantscore")

    # ---- document store ---------------------------------------------
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB: str = os.getenv("MONGO_DB", "quantscore")

    # ---- auth --------------------------------------------------------
    JWT_SECRET: str = os.getenv("JWT_SECRET", "quantscore-dev-secret-change-me")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = _int("JWT_EXPIRE_MINUTES", 720)

    # ---- app ---------------------------------------------------------
    TRADE_FEE_RATE: float = float(os.getenv("TRADE_FEE_RATE", "0.0005"))
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")

    # ---- ETL ---------------------------------------------------------
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(ROOT_DIR.parent)))
    PRICE_START_DATE: str = os.getenv("PRICE_START_DATE", "2018-01-01")
    PRICE_END_DATE: str = os.getenv("PRICE_END_DATE", "2023-12-31")
    NEWS_MAX_ROWS: int = _int("NEWS_MAX_ROWS", 1_200_000)

    @property
    def sqlalchemy_url(self) -> str:
        pwd = quote_plus(self.MYSQL_PASSWORD)
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{pwd}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}?charset=utf8mb4"
        )

    @property
    def sqlalchemy_server_url(self) -> str:
        """Server-level URL with no database selected (used to run the DDL)."""
        pwd = quote_plus(self.MYSQL_PASSWORD)
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{pwd}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/?charset=utf8mb4"
        )


settings = Settings()
