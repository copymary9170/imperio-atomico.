from dataclasses import dataclass

STATUS_FLOW = {
    "Borrador": {"En revision", "Archivado"},
    "En revision": {"Cambios solicitados", "Aprobado"},
    "Cambios solicitados": {"Borrador", "En revision"},
    "Aprobado": {"Pendiente de firma", "Vigente", "Archivado"},
    "Pendiente de firma": {"Vigente", "Cambios solicitados"},
    "Vigente": {"Suspendido", "Cerrado", "Archivado"},
    "Suspendido": {"Vigente", "Cerrado"},
    "Cerrado": {"Archivado"},
    "Archivado": set(),
}

FINAL_STATUSES = {"Archivado", "Cerrado"}
SIGNED_LOCK_STATUSES = {"Aprobado", "Pendiente de firma", "Vigente", "Cerrado", "Archivado"}


@dataclass(frozen=True)
class CreateMatterCommand:
    matter_type: str
    title: str
    description: str
    owner: str
    reviewer: str = ""
    approver: str = ""

    def validate(self) -> None:
        if not self.title.strip() or not self.description.strip() or not self.owner.strip():
            raise ValueError("Titulo, descripcion y responsable son obligatorios.")
        people = [p.strip().lower() for p in (self.owner, self.reviewer, self.approver) if p.strip()]
        if len(people) != len(set(people)):
            raise ValueError("Responsable, revisor y aprobador deben ser diferentes.")


def validate_transition(current_status: str, target_status: str, approver: str = "", comment: str = "") -> None:
    allowed = STATUS_FLOW.get(current_status, set())
    if target_status not in allowed:
        raise ValueError(f"Transicion no permitida: {current_status} a {target_status}.")
    if target_status in {"Aprobado", "Pendiente de firma", "Vigente"} and not approver.strip():
        raise ValueError("Debe existir aprobador antes de aprobar, firmar o activar un expediente.")
    if target_status in FINAL_STATUSES and not comment.strip():
        raise ValueError("El comentario es obligatorio para cerrar o archivar.")


def ensure_can_attach_document(status: str, signed: bool) -> None:
    if signed and status in {"Archivado", "Cerrado"}:
        raise ValueError("No se pueden adjuntar documentos firmados a expedientes cerrados o archivados.")
