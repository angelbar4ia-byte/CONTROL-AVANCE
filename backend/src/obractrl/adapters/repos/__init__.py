"""Implementaciones SQL de los puertos declarados en `application.puertos`.

Spec §12.11 — el borde. Cada clase de aquí implementa exactamente un
`Protocol` de `application/puertos/repositorios.py`; ninguna se importa desde
`domain/` ni desde `application/` (la regla de dependencia corre al revés:
el borde conoce los puertos, los puertos no conocen sus implementaciones).
"""

from obractrl.adapters.repos.actividades_sql import (
    ActividadNoModificada,
    RepositorioActividadesSQL,
)
from obractrl.adapters.repos.calendario_sql import (
    CalendarioNoConfigurado,
    RepositorioCalendarioSQL,
)
from obractrl.adapters.repos.configuracion_sql import RepositorioConfiguracionSQL
from obractrl.adapters.repos.estimaciones_sql import RepositorioEstimacionesSQL
from obractrl.adapters.repos.obras_sql import ObraNoModificada, RepositorioObrasSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL

__all__ = [
    "ActividadNoModificada",
    "CalendarioNoConfigurado",
    "ObraNoModificada",
    "RepositorioActividadesSQL",
    "RepositorioCalendarioSQL",
    "RepositorioConfiguracionSQL",
    "RepositorioEstimacionesSQL",
    "RepositorioObrasSQL",
    "UnidadDeTrabajoSQL",
]
