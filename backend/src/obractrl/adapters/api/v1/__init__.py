"""Router raíz de la API v1.

Spec §11.2 (endpoints por contexto).

Cada módulo del §11.1 aporta su router. Al agregar uno nuevo se registra aquí
y su contrato entra solo a `openapi.json`, de donde Orval genera los hooks de
TanStack Query para web y móvil (§12.2).
"""

from __future__ import annotations

from fastapi import APIRouter

from obractrl.adapters.api.v1.avance import router as router_avance
from obractrl.adapters.api.v1.identidad import router as router_identidad

api_v1 = APIRouter()

api_v1.include_router(router_identidad)
api_v1.include_router(router_avance)

# Pendientes de implementar (§11.2). Cada uno es un módulo con su fachada:
#   proyectos · catalogos · programacion · estimacion · materiales
#   incidencias · cierres · evaluacion · cargas · expediente · reportes
__all__ = ["api_v1"]
