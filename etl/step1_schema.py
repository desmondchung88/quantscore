"""Step 1 -- build the relational schema and the stored programs."""
from __future__ import annotations

from pathlib import Path

from common import BACKEND, Timer, banner

from app.db import mysql


def main() -> None:
    banner("STEP 1  Relational schema")

    sql_dir = Path(BACKEND) / "sql"
    schema = (sql_dir / "01_schema.sql").read_text(encoding="utf-8")
    programs = (sql_dir / "02_programs.sql").read_text(encoding="utf-8")

    with Timer("CREATE DATABASE + 12 tables, constraints and indexes"):
        n = mysql.run_script(schema, server_level=True)
        print(f"     {n} statements executed")

    with Timer("Views, triggers and stored procedures"):
        n = mysql.run_script(programs)
        print(f"     {n} statements executed")

    tables = mysql.query(
        "SELECT TABLE_NAME, TABLE_TYPE FROM information_schema.TABLES"
        " WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_TYPE, TABLE_NAME"
    )
    base = [t["TABLE_NAME"] for t in tables if t["TABLE_TYPE"] == "BASE TABLE"]
    views = [t["TABLE_NAME"] for t in tables if t["TABLE_TYPE"] == "VIEW"]
    print(f"\n  Tables ({len(base)}): {', '.join(base)}")
    print(f"  Views  ({len(views)}): {', '.join(views)}")

    routines = mysql.query(
        "SELECT ROUTINE_NAME FROM information_schema.ROUTINES"
        " WHERE ROUTINE_SCHEMA = DATABASE()"
    )
    triggers = mysql.query(
        "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS"
        " WHERE TRIGGER_SCHEMA = DATABASE()"
    )
    print(f"  Procedures ({len(routines)}): "
          f"{', '.join(r['ROUTINE_NAME'] for r in routines)}")
    print(f"  Triggers   ({len(triggers)}): "
          f"{', '.join(t['TRIGGER_NAME'] for t in triggers)}")


if __name__ == "__main__":
    main()
