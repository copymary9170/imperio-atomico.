import pytest

from legal_v4.domain import CreateMatterCommand, ensure_can_attach_document, validate_transition


def test_create_matter_requires_core_fields():
    command = CreateMatterCommand("Contrato", "", "", "")
    with pytest.raises(ValueError):
        command.validate()


def test_create_matter_enforces_role_segregation():
    command = CreateMatterCommand("Contrato", "Contrato marco", "Objeto", "maria", "Maria", "ana")
    with pytest.raises(ValueError):
        command.validate()


def test_create_matter_accepts_distinct_roles():
    command = CreateMatterCommand("Contrato", "Contrato marco", "Objeto", "maria", "ana", "luisa")
    command.validate()


def test_transition_requires_approver_for_approval():
    with pytest.raises(ValueError):
        validate_transition("En revision", "Aprobado", "", "aprobacion")


def test_transition_requires_comment_for_archive():
    with pytest.raises(ValueError):
        validate_transition("Borrador", "Archivado", "ana", "")


def test_closed_matter_rejects_signed_attachment():
    with pytest.raises(ValueError):
        ensure_can_attach_document("Cerrado", True)
