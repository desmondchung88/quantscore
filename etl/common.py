"""Shared helpers for the ETL scripts: dataset discovery and logging."""
from __future__ import annotations

import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402

CONSTITUENTS_FILE = "constituents-financials_csv.csv"
NEWS_FILES = (
    "raw_analyst_ratings.csv",
    "raw_partner_headlines.csv",
    "analyst_ratings_processed.csv",
)


class Timer:
    def __init__(self, label: str):
        self.label = label

    def __enter__(self):
        self.start = time.perf_counter()
        print(f"  -> {self.label} ...", flush=True)
        return self

    def __exit__(self, *exc):
        secs = time.perf_counter() - self.start
        print(f"     done in {secs:.1f}s", flush=True)


def banner(text: str) -> None:
    print()
    print("=" * 68)
    print(f"  {text}")
    print("=" * 68, flush=True)


def _search_roots() -> list[Path]:
    """Directories to scan for the Kaggle extracts."""
    from app.config import ROOT_DIR

    roots = [settings.DATA_DIR, ROOT_DIR, ROOT_DIR.parent, Path.cwd()]
    seen, out = set(), []
    for r in roots:
        if r and r.exists() and str(r) not in seen:
            seen.add(str(r))
            out.append(r)
    return out


def find_file(filename: str) -> Path | None:
    """Locate a dataset file anywhere up to two levels below the data roots."""
    for root in _search_roots():
        direct = root / filename
        if direct.is_file():
            return direct
        for depth in ("*", "*/*"):
            for match in root.glob(f"{depth}/{filename}"):
                if match.is_file():
                    return match
    return None


def find_price_dir() -> Path | None:
    """Find the directory holding the per-ticker OHLCV files.

    Identified by content, not by name: a directory with many files whose
    stem looks like a ticker and whose header starts with Ticker,Date.
    """
    best: tuple[int, Path] | None = None
    for root in _search_roots():
        for candidate in [root, *[p for p in root.iterdir() if p.is_dir()]]:
            try:
                csvs = [p for p in candidate.glob("*.csv")
                        if p.stem.replace(".", "").replace("-", "").isalnum()
                        and len(p.stem) <= 6]
            except (PermissionError, OSError):
                continue
            if len(csvs) < 50:
                continue
            try:
                header = csvs[0].open("r", encoding="utf-8").readline().strip().lower()
            except OSError:
                continue
            if not header.startswith("ticker,date") and "close" not in header:
                continue
            if best is None or len(csvs) > best[0]:
                best = (len(csvs), candidate)
    return best[1] if best else None


def require(path: Path | None, what: str) -> Path:
    if path is None:
        print(f"\nFATAL: could not locate {what}.", file=sys.stderr)
        print(f"Searched under: {[str(p) for p in _search_roots()]}", file=sys.stderr)
        print("Set DATA_DIR in .env to the folder holding the Kaggle extracts.",
              file=sys.stderr)
        sys.exit(1)
    return path
