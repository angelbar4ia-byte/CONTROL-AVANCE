"""Endpoints de organización (§5.1 "Configuración", Control de obra).

Spec §12.4 (RLS) · §10.7 (RLS como frontera).

Un solo endpoint por ahora: el reinicio. No hay vista previa ni reversa —
a diferencia de una carga (§10.2/§10.8), esto se pidió explícitamente sin
deshacer, con confirmación simple en la pantalla.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from obractrl.adapters.api.casos_uso import ReiniciarOrganizacionDep
from obractrl.adapters.api.dependencias import exigir_rol
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(prefix="/organizacion", tags=["organizacion"])


@router.post(
    "/reiniciar",
    summary="Reinicio de organización: borrado profundo, sin deshacer",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA))],
    responses={
        403: {"description": "Solo Control de obra puede reiniciar la organización."},
    },
)
async def reiniciar_organizacion(caso_uso: ReiniciarOrganizacionDep) -> dict[str, int]:
    """Borra todo lo operativo de la organización (catálogos, proyectos,
    prototipos, presupuestos, programación, avance, cargas, incidencias),
    preservando `usuario`. Devuelve cuántas filas se borraron por tabla."""
    return await caso_uso.ejecutar()
