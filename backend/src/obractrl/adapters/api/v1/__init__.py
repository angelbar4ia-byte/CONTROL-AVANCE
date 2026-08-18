"""Router raíz de la API v1.

Spec §11.2 (endpoints por contexto).

Cada módulo del §11.1 aporta su router. Al agregar uno nuevo se registra aquí
y su contrato entra solo a `openapi.json`, de donde Orval genera los hooks de
TanStack Query para web y móvil (§12.2).
"""

from __future__ import annotations

from fastapi import APIRouter

from obractrl.adapters.api.v1.avance import router as router_avance
from obractrl.adapters.api.v1.cargas import router as router_cargas
from obractrl.adapters.api.v1.catalogos import router as router_catalogos
from obractrl.adapters.api.v1.cierres import router as router_cierres
from obractrl.adapters.api.v1.estimacion import router as router_estimacion
from obractrl.adapters.api.v1.evaluaciones import router as router_evaluaciones
from obractrl.adapters.api.v1.evidencias import router as router_evidencias
from obractrl.adapters.api.v1.expediente import router as router_expediente
from obractrl.adapters.api.v1.identidad import router as router_identidad
from obractrl.adapters.api.v1.incidencias import router as router_incidencias
from obractrl.adapters.api.v1.materiales import router as router_materiales
from obractrl.adapters.api.v1.obras import router as router_obras
from obractrl.adapters.api.v1.programacion import router as router_programacion
from obractrl.adapters.api.v1.proyectos import router as router_proyectos
from obractrl.adapters.api.v1.reportes import router as router_reportes
from obractrl.adapters.api.v1.revisiones import router as router_revisiones

api_v1 = APIRouter()

api_v1.include_router(router_identidad)
api_v1.include_router(router_proyectos)
api_v1.include_router(router_catalogos)
api_v1.include_router(router_obras)
api_v1.include_router(router_programacion)
api_v1.include_router(router_avance)
api_v1.include_router(router_cierres)
api_v1.include_router(router_estimacion)
api_v1.include_router(router_materiales)
api_v1.include_router(router_incidencias)
api_v1.include_router(router_evaluaciones)
api_v1.include_router(router_revisiones)
api_v1.include_router(router_evidencias)
api_v1.include_router(router_cargas)
api_v1.include_router(router_expediente)
api_v1.include_router(router_reportes)

# Pendientes de implementar (§11.2): `POST /reportes/{tipo}` genérico ·
# procesos (§7.9) · tiempo real (`WS /ws`).
__all__ = ["api_v1"]
