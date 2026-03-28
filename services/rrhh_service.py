from __future__ import annotations

from datetime import date, time
from typing import Any

from repositories.rrhh_repository import RRHHRepository


class RRHHService:
    def __init__(self, repository: RRHHRepository | None = None) -> None:
        self.repository = repository or RRHHRepository()
        self.repository.ensure_schema()

    def crear_empleado(
        self,
        *,
        nombre: str,
        documento: str,
        puesto: str,
        area: str,
        fecha_ingreso: date,
        estado: str,
        usuario: str,
    ) -> int:
        nombre_limpio = (nombre or "").strip()
        documento_limpio = (documento or "").strip()
        puesto_limpio = (puesto or "").strip()
        area_limpia = (area or "").strip()

        if not nombre_limpio:
            raise ValueError("El nombre es obligatorio")
        if not documento_limpio:
            raise ValueError("El documento es obligatorio")
        if not puesto_limpio:
            raise ValueError("El puesto es obligatorio")
        if not area_limpia:
            raise ValueError("El área es obligatoria")
        if estado not in {"activo", "inactivo"}:
            raise ValueError("El estado debe ser activo o inactivo")

        return self.repository.create_employee(
            nombre=nombre_limpio,
            documento=documento_limpio,
            puesto=puesto_limpio,
            area=area_limpia,
            fecha_ingreso=fecha_ingreso.isoformat(),
            estado=estado,
            created_by=usuario,
        )

    def listar_empleados(self, estado: str | None = None) -> list[dict[str, Any]]:
        return self.repository.list_employees(estado=estado)

    def cambiar_estado_empleado(self, *, empleado_id: int, estado: str) -> None:
        if estado not in {"activo", "inactivo"}:
            raise ValueError("Estado de empleado no válido")
        self.repository.update_employee_status(empleado_id=empleado_id, estado=estado)

    def registrar_asistencia(
        self,
        *,
        empleado_id: int,
        fecha: date,
        hora_entrada: time | None,
        hora_salida: time | None,
        usuario: str,
    ) -> int:
        if not hora_entrada and not hora_salida:
            raise ValueError("Debes registrar al menos hora de entrada o hora de salida")
        if hora_entrada and hora_salida and hora_salida <= hora_entrada:
            raise ValueError("La hora de salida debe ser mayor a la hora de entrada")

        return self.repository.upsert_attendance(
            empleado_id=empleado_id,
            fecha=fecha.isoformat(),
            hora_entrada=hora_entrada.strftime("%H:%M") if hora_entrada else None,
            hora_salida=hora_salida.strftime("%H:%M") if hora_salida else None,
            usuario=usuario,
        )

    def listar_asistencia(
        self,
        *,
        fecha_desde: date,
        fecha_hasta: date,
        empleado_id: int | None = None,
    ) -> list[dict[str, Any]]:
        if fecha_hasta < fecha_desde:
            raise ValueError("La fecha final no puede ser menor a la inicial")
        return self.repository.list_attendance(
            fecha_desde=fecha_desde.isoformat(),
            fecha_hasta=fecha_hasta.isoformat(),
            empleado_id=empleado_id,
        )

    def crear_solicitud(
        self,
        *,
        empleado_id: int,
        tipo: str,
        motivo: str,
        fecha_inicio: date,
        fecha_fin: date,
        usuario: str,
    ) -> int:
        if tipo not in {"vacaciones", "permiso", "incapacidad"}:
            raise ValueError("Tipo de solicitud no válido")
        if fecha_fin < fecha_inicio:
            raise ValueError("La fecha fin no puede ser menor a la fecha inicio")

        return self.repository.create_request(
            empleado_id=empleado_id,
            tipo=tipo,
            motivo=(motivo or "").strip(),
            fecha_inicio=fecha_inicio.isoformat(),
            fecha_fin=fecha_fin.isoformat(),
            created_by=usuario,
        )

    def listar_solicitudes(
        self,
        *,
        estado: str | None = None,
        fecha_desde: date | None = None,
        fecha_hasta: date | None = None,
    ) -> list[dict[str, Any]]:
        if fecha_desde and fecha_hasta and fecha_hasta < fecha_desde:
            raise ValueError("La fecha final no puede ser menor a la inicial")
        return self.repository.list_requests(
            estado=estado,
            fecha_desde=fecha_desde.isoformat() if fecha_desde else None,
            fecha_hasta=fecha_hasta.isoformat() if fecha_hasta else None,
        )

    def resolver_solicitud(
        self,
        *,
        solicitud_id: int,
        accion: str,
        comentario: str,
        admin_usuario: str,
    ) -> None:
        estado = {"aprobar": "aprobado", "rechazar": "rechazado"}.get(accion)
        if not estado:
            raise ValueError("Acción de aprobación no válida")

        self.repository.resolve_request(
            solicitud_id=solicitud_id,
            estado=estado,
            comentario=(comentario or "").strip(),
            admin_usuario=admin_usuario,
        )

    def indicadores(self) -> dict[str, int]:
        return self.repository.get_dashboard_metrics()
