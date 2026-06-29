from __future__ import annotations

from dataclasses import asdict

from database.connection import db_transaction
from legal.application.operational_commands import (
    CreateComplianceObligationCommand,
    CreateContractCommand,
    CreateLitigationCaseCommand,
    CreateRiskCommand,
    CreateTaskCommand,
)
from legal.audit.events import AuditEvent
from legal.infrastructure.sqlite.audit_repository import SQLiteAuditRepository
from legal.migrations import migrate_all
from legal.security.rbac import LegalPermission, SecurityContext, require_permission


class LegalOperationalService:
    """Application service for operational legal records."""

    def __init__(self) -> None:
        migrate_all()

    def create_contract(self, command: CreateContractCommand, context: SecurityContext) -> int:
        require_permission(context, LegalPermission.CREATE)
        if not command.contract_type.strip():
            raise ValueError("El contrato requiere tipo.")
        if command.notice_days < 0:
            raise ValueError("Los dias de aviso no pueden ser negativos.")
        with db_transaction() as conn:
            new_id = _insert_contract(conn, command)
            _audit(conn, context, "LEGAL_CONTRACT_CREATED", "legal_contract", new_id, asdict(command))
            return new_id

    def create_risk(self, command: CreateRiskCommand, context: SecurityContext) -> int:
        require_permission(context, LegalPermission.CREATE)
        if not command.title.strip():
            raise ValueError("El riesgo requiere titulo.")
        if command.likelihood not in range(1, 6) or command.impact not in range(1, 6):
            raise ValueError("Probabilidad e impacto deben estar entre 1 y 5.")
        inherent_score = command.likelihood * command.impact
        residual_score = command.residual_score or inherent_score
        with db_transaction() as conn:
            row_id = conn.execute(
                """
                INSERT INTO legal_risks(matter_id,title,category,likelihood,impact,inherent_score,controls,residual_score,owner,review_date)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    command.matter_id,
                    command.title,
                    command.category,
                    command.likelihood,
                    command.impact,
                    inherent_score,
                    command.controls,
                    residual_score,
                    command.owner,
                    command.review_date or None,
                ),
            ).lastrowid
            _audit(conn, context, "LEGAL_RISK_CREATED", "legal_risk", row_id, asdict(command) | {"inherent_score": inherent_score})
            return int(row_id)

    def create_compliance_obligation(self, command: CreateComplianceObligationCommand, context: SecurityContext) -> int:
        require_permission(context, LegalPermission.CREATE)
        if not command.regulation.strip() or not command.obligation.strip():
            raise ValueError("La obligacion requiere regulacion y descripcion.")
        with db_transaction() as conn:
            row_id = conn.execute(
                """
                INSERT INTO legal_compliance_obligations(matter_id,regulation,obligation,authority,owner,frequency,due_date,control_reference,evidence_reference)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    command.matter_id,
                    command.regulation,
                    command.obligation,
                    command.authority,
                    command.owner,
                    command.frequency,
                    command.due_date or None,
                    command.control_reference,
                    command.evidence_reference,
                ),
            ).lastrowid
            _audit(conn, context, "LEGAL_COMPLIANCE_CREATED", "legal_compliance_obligation", row_id, asdict(command))
            return int(row_id)

    def create_litigation_case(self, command: CreateLitigationCaseCommand, context: SecurityContext) -> int:
        require_permission(context, LegalPermission.CREATE)
        if not command.proceeding_type.strip():
            raise ValueError("El litigio requiere tipo de procedimiento.")
        with db_transaction() as conn:
            row_id = conn.execute(
                """
                INSERT INTO legal_litigation_cases(matter_id,proceeding_type,authority,case_number,external_counsel,claim_amount,currency,probability,provision_amount,next_hearing_at,strategy)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    command.matter_id,
                    command.proceeding_type,
                    command.authority,
                    command.case_number,
                    command.external_counsel,
                    command.claim_amount,
                    command.currency,
                    command.probability,
                    command.provision_amount,
                    command.next_hearing_at or None,
                    command.strategy,
                ),
            ).lastrowid
            _audit(conn, context, "LEGAL_LITIGATION_CREATED", "legal_litigation_case", row_id, asdict(command))
            return int(row_id)

    def create_task(self, command: CreateTaskCommand, context: SecurityContext) -> int:
        require_permission(context, LegalPermission.CREATE)
        if not command.title.strip() or not command.assigned_to.strip():
            raise ValueError("La tarea requiere titulo y responsable.")
        with db_transaction() as conn:
            row_id = conn.execute(
                """
                INSERT INTO legal_tasks(matter_id,title,assigned_to,due_date,priority,created_by)
                VALUES(?,?,?,?,?,?)
                """,
                (command.matter_id, command.title, command.assigned_to, command.due_date or None, command.priority, command.created_by),
            ).lastrowid
            _audit(conn, context, "LEGAL_TASK_CREATED", "legal_task", row_id, asdict(command))
            return int(row_id)


def _insert_contract(conn, command: CreateContractCommand) -> int:
    return int(
        conn.execute(
            """
            INSERT INTO legal_contracts(matter_id,contract_type,effective_date,end_date,renewal_type,notice_days,amount,currency,governing_law)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                command.matter_id,
                command.contract_type,
                command.effective_date or None,
                command.end_date or None,
                command.renewal_type,
                command.notice_days,
                command.amount,
                command.currency,
                command.governing_law,
            ),
        ).lastrowid
    )


def _audit(conn, context: SecurityContext, action: str, entity_type: str, entity_id: int, after: dict) -> None:
    audit = SQLiteAuditRepository(conn)
    event = AuditEvent(
        actor=context.user,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before={},
        after=after,
        context={"session_id": context.session_id, "correlation_id": context.correlation_id},
        previous_hash=audit.last_hash(),
    ).seal()
    audit.add(event)
