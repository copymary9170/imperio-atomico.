from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from uuid import uuid4


@dataclass(slots=True)
class AuditEvent:
    actor: str
    action: str
    entity_type: str
    entity_id: str | int | None
    before: dict | None = None
    after: dict | None = None
    context: dict | None = None
    previous_hash: str = ""
    event_uuid: str = field(default_factory=lambda: str(uuid4()))
    event_time: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    event_hash: str = ""

    def seal(self) -> "AuditEvent":
        self.event_hash = build_event_hash(self)
        return self


def build_event_hash(event: AuditEvent) -> str:
    payload = asdict(event)
    payload["event_hash"] = ""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
