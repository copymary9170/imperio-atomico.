from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from database.schema import init_schema
from services.gestion_negocio_service import (
    alertas_negocio,
    consolidado_sucursal,
    cuentas_por_cobrar_resumen,
    cuentas_por_pagar_resumen,
    dashboard_kpis,
    dashboard_payload,
    normalize_filters,
    pedidos_pendientes,
    productos_mas_vendidos,
    rentabilidad_linea_negocio,
    servicios_mas_rentables,
    ventas_tiempo,
)


class NegocioDashboardHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items() if v}
        filters = normalize_filters(query)

        routes = {
            "/api/v1/dashboard/gestion-negocio": lambda: dashboard_payload(query),
            "/api/v1/dashboard/gestion-negocio/kpis": lambda: dashboard_kpis(filters),
            "/api/v1/dashboard/gestion-negocio/consolidado-sucursal": lambda: consolidado_sucursal(filters),
            "/api/v1/dashboard/gestion-negocio/rentabilidad-linea": lambda: rentabilidad_linea_negocio(filters),
            "/api/v1/dashboard/gestion-negocio/ventas": lambda: ventas_tiempo(filters, query.get("grano", "dia")),
            "/api/v1/dashboard/gestion-negocio/productos-top": lambda: productos_mas_vendidos(filters, int(query.get("limit", 10))),
            "/api/v1/dashboard/gestion-negocio/servicios-rentables": lambda: servicios_mas_rentables(filters, int(query.get("limit", 10))),
            "/api/v1/dashboard/gestion-negocio/pedidos-pendientes": lambda: pedidos_pendientes(filters),
            "/api/v1/dashboard/gestion-negocio/cxc": lambda: cuentas_por_cobrar_resumen(filters),
            "/api/v1/dashboard/gestion-negocio/cxp": lambda: cuentas_por_pagar_resumen(filters),
            "/api/v1/dashboard/gestion-negocio/alertas": lambda: alertas_negocio(filters),
        }

        endpoint = routes.get(parsed.path)
        if not endpoint:
            self._send_json({"error": "Ruta no encontrada", "path": parsed.path}, status=404)
            return

        try:
            self._send_json(endpoint())
        except Exception as exc:
            self._send_json({"error": "Error procesando solicitud", "detail": str(exc)}, status=500)


def run_server(host: str = "0.0.0.0", port: int = 8091) -> None:
    init_schema()
    server = ThreadingHTTPServer((host, port), NegocioDashboardHandler)
    print(f"API Gestión Negocio escuchando en http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
