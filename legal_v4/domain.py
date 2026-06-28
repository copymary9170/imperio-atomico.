from dataclasses import dataclass


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
