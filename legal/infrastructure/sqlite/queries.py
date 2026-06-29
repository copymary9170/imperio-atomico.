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
        total = conn.execute("SELECT COUNT(*) AS n FROM legal_matters WHERE active=1").fetchone()["n"]
        critical = conn.execute("SELECT COUNT(*) AS n FROM legal_matters WHERE active=1 AND risk_level IN ('Alto','Critico')").fetchone()["n"]
        contracts = conn.execute("SELECT COUNT(*) AS n FROM legal_contracts").fetchone()["n"]
        litigations = conn.execute("SELECT COUNT(*) AS n FROM legal_litigation_cases").fetchone()["n"]
        risks = conn.execute("SELECT COUNT(*) AS n FROM legal_risks WHERE status <> 'Cerrado'").fetchone()["n"]
        tasks = conn.execute("SELECT COUNT(*) AS n FROM legal_tasks WHERE status <> 'Completada'").fetchone()["n"]
        return {
            "matters": int(total or 0),
            "critical": int(critical or 0),
            "contracts": int(contracts or 0),
            "litigations": int(litigations or 0),
            "open_risks": int(risks or 0),
            "open_tasks": int(tasks or 0),
        }


def list_recent_audit(limit: int = 200) -> list[dict[str, Any]]:
    migrate_all()
    with db_transaction() as conn:
        rows = conn.execute("SELECT * FROM legal_audit_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]
