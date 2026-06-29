from legal.application.operational_commands import (
    CreateComplianceObligationCommand,
    CreateContractCommand,
    CreateLitigationCaseCommand,
    CreateRiskCommand,
    CreateTaskCommand,
)


def test_operational_commands_are_instantiable():
    assert CreateContractCommand(matter_id=1, contract_type="Proveedor").contract_type == "Proveedor"
    assert CreateRiskCommand(title="R", category="Legal", likelihood=1, impact=1, owner="Legal").impact == 1
    assert CreateComplianceObligationCommand(regulation="Ley", obligation="Cumplir", owner="Legal").frequency == "Unica"
    assert CreateLitigationCaseCommand(matter_id=1, proceeding_type="Demanda").probability == "Posible"
    assert CreateTaskCommand(title="Revisar", assigned_to="Legal", created_by="Admin").priority == "Media"
