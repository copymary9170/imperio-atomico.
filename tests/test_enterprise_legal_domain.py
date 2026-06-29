import pytest

from legal.domain.entities import LegalMatter, LegalParty
from legal.domain.enums import MatterStatus
from legal.domain.errors import InvalidTransitionError, SegregationOfDutiesError


def test_party_requires_name_and_type():
    party = LegalParty(name="Cliente ABC", party_type="Cliente")
    party.validate()


@pytest.mark.parametrize("field", ["code", "matter_type", "title", "owner", "created_by"])
def test_matter_requires_core_fields(field):
    data = {
        "code": "LEG-0001",
        "matter_type": "Contratos",
        "title": "Contrato proveedor",
        "description": "Contrato de suministro",
        "owner": "Legal",
        "created_by": "Admin",
    }
    data[field] = ""
    matter = LegalMatter(**data)
    with pytest.raises(ValueError):
        matter.validate()


def test_segregation_of_duties_blocks_same_people():
    matter = LegalMatter(
        code="LEG-0001",
        matter_type="Contratos",
        title="Contrato proveedor",
        description="Contrato de suministro",
        owner="Maria",
        reviewer="Maria",
        approver="Ana",
        created_by="Admin",
    )
    with pytest.raises(SegregationOfDutiesError):
        matter.validate()


def test_transition_requires_allowed_path():
    matter = LegalMatter(
        code="LEG-0001",
        matter_type="Contratos",
        title="Contrato proveedor",
        description="Contrato de suministro",
        owner="Maria",
        reviewer="Ana",
        approver="Luis",
        created_by="Admin",
    )
    with pytest.raises(InvalidTransitionError):
        matter.transition_to(MatterStatus.ACTIVE)


def test_transition_to_review_is_allowed():
    matter = LegalMatter(
        code="LEG-0001",
        matter_type="Contratos",
        title="Contrato proveedor",
        description="Contrato de suministro",
        owner="Maria",
        reviewer="Ana",
        approver="Luis",
        created_by="Admin",
    )
    matter.transition_to(MatterStatus.IN_REVIEW)
    assert matter.status == MatterStatus.IN_REVIEW
