"""Construcción de casos de uso para los endpoints.

Spec §12.11 (el borde ensambla; la aplicación no sabe cómo).

Cada función es una dependencia de FastAPI que arma un caso de uso con
implementaciones concretas de sus puertos, a partir de la sesión con RLS ya
fijado (`SesionRLS`, `adapters/api/dependencias.py`). Los routers dependen de
estas funciones, nunca construyen un repositorio SQL directamente: así el
router solo conoce el caso de uso (aplicación), no `adapters.repos`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from obractrl.adapters.api.dependencias import SesionRLS
from obractrl.adapters.repos.actividades_sql import RepositorioActividadesSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.capturar_avance import CapturarAvance

__all__ = ["CapturarAvanceDep"]


def obtener_capturar_avance(sesion: SesionRLS) -> CapturarAvance:
    return CapturarAvance(
        actividades=RepositorioActividadesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


CapturarAvanceDep = Annotated[CapturarAvance, Depends(obtener_capturar_avance)]
