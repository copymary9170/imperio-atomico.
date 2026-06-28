from __future__ import annotations

import pandas as pd

from database.connection import db_transaction
from legal_v4.schema import migrate


def load_executive_report() -> dict[str, pd.DataFrame]:
    migrate()
    with db_transaction() as conn:
        matters = pd.read_sql_query("SELECT * FROM legal_v4_matters", conn)
        documents = pd.read_sql_query("SELECT * FROM legal_v4_documents WHERE active=1", conn)
        tasks = pd.read_sql_query("SELECT * FROM legal_v4_tasks", conn)
        calendar = pd.read_sql_query("SELECT * FROM legal_v4_calendar", conn)
        controls = pd.read_sql_query("SELECT * FROM legal_v4_controls", conn)
        risks = pd.read_sql_query("SELECT * FROM legal_v4_risk_assessments", conn)
    return {
        "matters": matters,
        "documents": documents,
        "tasks": tasks,
        "calendar": calendar,
        "controls": controls,
        "risks": risks,
    }


def summarize_portfolio() -> pd.DataFrame:
    report = load_executive_report()
    matters = report["matters"]
    if matters.empty:
        return pd.DataFrame(columns=["indicador", "valor"])
    summary = [
        ("Expedientes", len(matters)),
        ("Vigentes", int(matters["status"].isin(["Vigente", "Aprobado"]).sum())),
        ("Riesgo alto o critico", int(matters["risk_level"].isin(["Alto", "Critico"]).sum())),
        ("Confidenciales o restringidos", int(matters["confidentiality"].isin(["Confidencial", "Restringido"]).sum())),
        ("Documentos activos", len(report["documents"])),
        ("Tareas pendientes", int((report["tasks"]["status"] != "Completada").sum()) if not report["tasks"].empty else 0),
        ("Eventos pendientes", int((report["calendar"]["status"] != "Completado").sum()) if not report["calendar"].empty else 0),
        ("Controles pendientes", int((report["controls"]["status"] != "Completado").sum()) if not report["controls"].empty else 0),
    ]
    return pd.DataFrame(summary, columns=["indicador", "valor"])
