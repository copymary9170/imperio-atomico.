from __future__ import annotations

from typing import Any

from database.connection import db_transaction
from legal.migrations import migrate_all


def list_legal_matter_summary(limit: int = 500) -> list[dict[str, Any]]:
    """Return Legal Enterprise matter rows for dashboards and Streamlit tables."""

    migrate_all()
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, code, area, matter_type, title, status, risk_level, confidentiality,
                   owner, counterparty, due_date, expiration_date, created_at
              FROM legal_matters
             WHERE active=1
             ORDER BY id DESC
             LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def legal_dashboard_metrics() -> dict[str, int]:
    """Return executive counters for the enterprise legal dashboard."""

    migrate_all()
    with db_transaction() as conn:
        return {
            "matters": _count(conn, "SELECT COUNT(*) FROM legal_matters WHERE active=1"),
            "critical": _count(conn, "SELECT COUNT(*) FROM legal_matters WHERE active=1 AND risk_level IN ('Alto','Critico')"),
            "contracts": _count(conn, "SELECT COUNT(*) FROM legal_contracts"),
            "litigations": _count(conn, "SELECT COUNT(*) FROM legal_litigation_cases"),
            "open_risks": _count(conn, "SELECT COUNT(*) FROM legal_risks WHERE status <> 'Cerrado'"),
            "open_tasks": _count(conn, "SELECT COUNT(*) FROM legal_tasks WHERE status <> 'Completada'"),
            "compliance_pending": _count(conn, "SELECT COUNT(*) FROM legal_compliance_obligations WHERE status <> 'Completada'"),
        }


def list_contracts(limit: int = 200) -> list[dict[str, Any]]:
    migrate_all()
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT c.*, m.code AS matter_code, m.title AS matter_title
              FROM legal_contracts c
              JOIN legal_matters m ON m.id = c.matter_id
             ORDER BY c.id DESC
             LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def list_risks(limit: int = 200) -> list[dict[str, Any]]:
    migrate_all()
    with db_transaction() as conn:
        rows = conn.execute("SELECT * FROM legal_risks ORDER BY residual_score DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]


def list_compliance(limit: int = 200) -> list[dict[str, Any]]:
    migrate_all()
    with db_transaction() as conn:
        rows = conn.execute("SELECT * FROM legal_compliance_obligations ORDER BY due_date IS NULL, due_date, id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]


def list_litigation(limit: int = 200) -> list[dict[str, Any]]:
    migrate_all()
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT l.*, m.code AS matter_code, m.title AS matter_title
              FROM legal_litigation_cases l
              JOIN legal_matters m ON m.id = l.matter_id
             ORDER BY l.next_hearing_at IS NULL, l.next_hearing_at, l.id DESC
             LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def list_recent_audit(limit: int = 200) -> list[dict[str, Any]]:
    migrate_all()
    with db_transaction() as conn:
        rows = conn.execute("SELECT * FROM legal_audit_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]


def _count(conn, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int(row[0] or 0)
