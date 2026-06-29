from __future__ import annotations

from legal.domain.entities import LegalMatter
from legal.domain.enums import Confidentiality, MatterStatus, RiskLevel


class SQLiteLegalMatterRepository:
    """SQLite repository for enterprise legal matters."""

    def __init__(self, conn) -> None:
        self.conn = conn

    def next_code(self, matter_type: str) -> str:
        prefix = ''.join(ch for ch in matter_type.upper() if ch.isalnum())[:3] or 'LEG'
        row = self.conn.execute('SELECT COUNT(*) FROM legal_matters WHERE matter_type=?', (matter_type,)).fetchone()
        return f'{prefix}-{int(row[0]) + 1:04d}'

    def add(self, matter: LegalMatter) -> int:
        self.conn.execute(
            '''
            INSERT INTO legal_matters(
                uuid, code, area, matter_type, title, description, status, risk_level,
                confidentiality, owner, reviewer, approver, counterparty, jurisdiction,
                legal_basis, tags, legal_hold, retention_years, created_by, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''',
            (
                matter.uuid,
                matter.code,
                matter.matter_type,
                matter.matter_type,
                matter.title,
                matter.description,
                matter.status.value,
                matter.risk_level.value,
                matter.confidentiality.value,
                matter.owner,
                matter.reviewer,
                matter.approver,
                matter.counterparty,
                matter.jurisdiction,
                matter.legal_basis,
                matter.tags,
                int(matter.legal_hold),
                matter.retention_years,
                matter.created_by,
                matter.created_at.isoformat(),
            ),
        )
        return int(self.conn.execute('SELECT last_insert_rowid()').fetchone()[0])

    def get(self, matter_id: int) -> LegalMatter | None:
        row = self.conn.execute('SELECT * FROM legal_matters WHERE id=?', (matter_id,)).fetchone()
        if not row:
            return None
        return LegalMatter(
            code=row['code'],
            matter_type=row['matter_type'],
            title=row['title'],
            description=row['description'],
            owner=row['owner'],
            created_by=row['created_by'],
            reviewer=row['reviewer'] or '',
            approver=row['approver'] or '',
            status=MatterStatus(row['status']),
            risk_level=RiskLevel(row['risk_level']),
            confidentiality=Confidentiality(row['confidentiality']),
            counterparty=row['counterparty'] or '',
            jurisdiction=row['jurisdiction'] or 'Venezuela',
            legal_basis=row['legal_basis'] or '',
            tags=row['tags'] or '',
            legal_hold=bool(row['legal_hold']),
            retention_years=int(row['retention_years']),
            uuid=row['uuid'],
        )

    def update(self, matter_id: int, matter: LegalMatter) -> None:
        self.conn.execute(
            '''
            UPDATE legal_matters
               SET status=?, risk_level=?, confidentiality=?, owner=?, reviewer=?, approver=?,
                   counterparty=?, legal_basis=?, tags=?, legal_hold=?, retention_years=?, updated_at=CURRENT_TIMESTAMP
             WHERE id=?
            ''',
            (
                matter.status.value,
                matter.risk_level.value,
                matter.confidentiality.value,
                matter.owner,
                matter.reviewer,
                matter.approver,
                matter.counterparty,
                matter.legal_basis,
                matter.tags,
                int(matter.legal_hold),
                matter.retention_years,
                matter_id,
            ),
        )
