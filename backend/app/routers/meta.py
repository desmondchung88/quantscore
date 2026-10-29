"""Health and database-inventory endpoints.

/api/meta/schema is used by the UI's "Database" page and doubles as the
evidence for the report: it reads the live catalogue rather than a
hand-maintained list.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
from app.db import mongo, mysql

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/health")
def health():
    sql_ok, sql_error = True, None
    try:
        mysql.query_one("SELECT 1 AS ok")
    except Exception as exc:
        sql_ok, sql_error = False, str(exc).splitlines()[0][:200]

    return {
        "status": "ok" if (sql_ok and mongo.ping()) else "degraded",
        "mysql": {"connected": sql_ok, "database": settings.MYSQL_DB,
                  "error": sql_error},
        "mongodb": {"connected": mongo.ping(), "database": settings.MONGO_DB},
    }


@router.get("/stats")
def stats():
    counts = mysql.query_one(
        "SELECT (SELECT COUNT(*) FROM stocks)              AS stocks,"
        "       (SELECT COUNT(*) FROM sectors)             AS sectors,"
        "       (SELECT COUNT(*) FROM stock_prices)        AS price_rows,"
        "       (SELECT COUNT(*) FROM financial_snapshots) AS snapshots,"
        "       (SELECT COUNT(*) FROM users)               AS users,"
        "       (SELECT COUNT(*) FROM portfolios)          AS portfolios,"
        "       (SELECT COUNT(*) FROM transactions)        AS transactions,"
        "       (SELECT COUNT(*) FROM watchlists)          AS watchlists,"
        "       (SELECT MIN(price_date) FROM stock_prices) AS first_price_date,"
        "       (SELECT MAX(price_date) FROM stock_prices) AS last_price_date"
    )
    db = mongo.get_db()
    try:
        documents = {
            "news_articles": db[mongo.NEWS].estimated_document_count(),
            "company_profiles": db[mongo.PROFILES].estimated_document_count(),
            "research_notes": db[mongo.NOTES].estimated_document_count(),
            "activity_logs": db[mongo.ACTIVITY].estimated_document_count(),
            "bench_prices": db[mongo.BENCH_PRICES].estimated_document_count(),
        }
    except Exception as exc:
        documents = {"error": str(exc)[:200]}

    imports = mysql.query(
        "SELECT dataset_name, dataset_version, row_count, source_url, imported_at"
        "  FROM data_imports ORDER BY import_id")

    return {"relational": counts, "documents": documents, "imports": imports}


@router.get("/schema")
def schema():
    """Live inventory of tables, views, constraints, indexes and programs."""
    tables = mysql.query(
        "SELECT TABLE_NAME AS name, TABLE_TYPE AS type, TABLE_ROWS AS approx_rows"
        "  FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()"
        " ORDER BY TABLE_TYPE, TABLE_NAME")
    columns = mysql.query(
        "SELECT TABLE_NAME AS table_name, COLUMN_NAME AS column_name,"
        "       COLUMN_TYPE AS data_type, IS_NULLABLE AS nullable,"
        "       COLUMN_KEY AS key_type"
        "  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE()"
        " ORDER BY TABLE_NAME, ORDINAL_POSITION")
    foreign_keys = mysql.query(
        "SELECT CONSTRAINT_NAME AS name, TABLE_NAME AS child,"
        "       COLUMN_NAME AS child_column, REFERENCED_TABLE_NAME AS parent,"
        "       REFERENCED_COLUMN_NAME AS parent_column"
        "  FROM information_schema.KEY_COLUMN_USAGE"
        " WHERE TABLE_SCHEMA = DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL"
        " ORDER BY TABLE_NAME")
    indexes = mysql.query(
        "SELECT TABLE_NAME AS table_name, INDEX_NAME AS index_name,"
        "       GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS columns,"
        "       MAX(NON_UNIQUE) = 0 AS is_unique, MAX(INDEX_TYPE) AS index_type"
        "  FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE()"
        " GROUP BY TABLE_NAME, INDEX_NAME ORDER BY TABLE_NAME, INDEX_NAME")
    routines = mysql.query(
        "SELECT ROUTINE_NAME AS name, ROUTINE_TYPE AS type,"
        "       ROUTINE_COMMENT AS comment"
        "  FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA = DATABASE()")
    triggers = mysql.query(
        "SELECT TRIGGER_NAME AS name, EVENT_MANIPULATION AS event,"
        "       EVENT_OBJECT_TABLE AS on_table, ACTION_TIMING AS timing"
        "  FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = DATABASE()")

    db = mongo.get_db()
    collections = []
    try:
        for name in sorted(db.list_collection_names()):
            coll = db[name]
            collections.append({
                "name": name,
                "documents": coll.estimated_document_count(),
                "indexes": [
                    {"name": ix_name,
                     "keys": [[k, v] for k, v in ix.get("key", {}).items()],
                     "ttl_seconds": ix.get("expireAfterSeconds"),
                     "unique": bool(ix.get("unique"))}
                    for ix_name, ix in coll.index_information().items()
                ],
            })
    except Exception as exc:
        collections = [{"error": str(exc)[:200]}]

    return {
        "relational": {
            "tables": tables, "columns": columns, "foreign_keys": foreign_keys,
            "indexes": indexes, "routines": routines, "triggers": triggers,
        },
        "documents": {"collections": collections},
    }
