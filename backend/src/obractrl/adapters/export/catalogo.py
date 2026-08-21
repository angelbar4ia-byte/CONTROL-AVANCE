"""Qué tipos de reporte existen, quién los puede pedir y qué necesitan.

Spec §11.2 ("**Reportes** — `POST /reportes/{tipo}` → genera Excel/PDF (job),
**por alcance** · `GET /reportes/{id}` (estado/descarga)") · §5.1 · §12.11.

## Por qué una tabla y no un `if` en el router

Porque las tres cosas que distinguen a un reporte de otro —qué trabajo lo
genera, qué parámetros exige y qué roles lo pueden pedir— se leen juntas o no
se leen. Con un `if/elif` en el endpoint, agregar un reporte significa tocar
tres lugares del mismo archivo y confiar en que nadie olvide el tercero; casi
siempre el olvidado es el rol.

Aquí un reporte nuevo es **un renglón**, y `POST /reportes/{tipo}` no cambia.

## Los tipos que ya existían siguen teniendo su ruta propia

`GET /estimaciones/{id}/export` y `GET /obras/{id}/expediente/pdf` están
nombrados así en el §11.2 y **no se tocan**: son la ruta que ya usa la web
(§12.12, contrato aditivo). Lo que agrega el genérico es una segunda puerta
para los mismos dos trabajos —útil cuando el cliente es un tablero que pide
"el reporte X" sin saber qué recurso hay detrás— y **una tercera** que solo
existe aquí: `avance`, que no cuelga de ninguna entidad porque su sujeto es el
alcance del que pregunta.

## `roles=()` significa todos, no ninguno

Un reporte sin restricción de rol es lo normal cuando la frontera es RLS: el
residente que pide `avance` recibe un archivo con sus obras. Se escribe como
tupla vacía y se documenta aquí para que nadie lo lea como "nadie puede".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from obractrl.adapters.export.trabajos import (
    EXPEDIENTE_PDF,
    EXPORTAR_ESTIMACION_XLSX,
    REPORTE_DE_AVANCE_XLSX,
)
from obractrl.domain.shared.diccionario import Rol

__all__ = ["CATALOGO", "TipoDeReporte", "TipoDeReporteDesconocido", "tipo_de_reporte"]


class TipoDeReporteDesconocido(LookupError):
    """El `{tipo}` de la ruta no está en el catálogo. El borde lo traduce a 404."""


@dataclass(frozen=True, slots=True)
class TipoDeReporte:
    """Un renglón del catálogo."""

    clave: str
    trabajo: str
    """Nombre del job de Arq. Es la constante de `trabajos.py`, no un literal:
    un typo aquí sería un reporte que se encola y nunca corre."""
    descripcion: str
    formato: str
    roles: tuple[Rol, ...] = ()
    """Vacío = cualquier rol autenticado; el alcance lo pone RLS (ver arriba)."""
    requiere: tuple[str, ...] = ()
    """Parámetros obligatorios del cuerpo. Se validan en el borde, antes de
    encolar: un trabajo que falla por un parámetro faltante gasta un viaje al
    worker para responder lo que se sabía desde el principio."""

    def permite(self, rol: str) -> bool:
        return not self.roles or rol in {r.value for r in self.roles}


CATALOGO: Final[dict[str, TipoDeReporte]] = {
    "avance": TipoDeReporte(
        clave="avance",
        trabajo=REPORTE_DE_AVANCE_XLSX,
        descripcion=(
            "Estado de las obras visibles: avance, actividades, bloqueos, "
            "incidencias y cierres pendientes."
        ),
        formato="xlsx",
        # Sin roles: es el reporte "por alcance" del §11.2 en estado puro.
        # Cada quien recibe sus obras porque RLS ya filtró (§12.4).
        roles=(),
        # Ninguno obligatorio: `proyecto_id` y `cluster_id` son foco, no
        # permiso, y sin ellos el reporte es el alcance completo.
        requiere=(),
    ),
    "estimacion": TipoDeReporte(
        clave="estimacion",
        trabajo=EXPORTAR_ESTIMACION_XLSX,
        descripcion="La estimación semanal con sus renglones e importes (§11.3 E).",
        formato="xlsx",
        # Mismos roles que `GET /estimaciones/{id}/export` (§11.2). Si aquí
        # fueran más amplios, el genérico sería un rodeo para saltarse la
        # guarda de la ruta específica.
        roles=(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE),
        requiere=("estimacion_id",),
    ),
    "expediente": TipoDeReporte(
        clave="expediente",
        trabajo=EXPEDIENTE_PDF,
        descripcion="El expediente técnico de una obra en PDF (§7.9, §11.3 D).",
        formato="pdf",
        # `GET /obras/{id}/expediente/pdf` no lleva `exigir_rol`: el §11.2 dice
        # "todos lectura" y RLS acota a las obras visibles. Se replica tal cual.
        roles=(),
        requiere=("obra_id",),
    ),
}


def tipo_de_reporte(clave: str) -> TipoDeReporte:
    """Busca el tipo. Levanta `TipoDeReporteDesconocido` si no está.

    El mensaje enumera los tipos válidos: quien se equivocó escribiendo la
    ruta necesita saber cuáles hay, y son tres, no trescientos.
    """
    tipo = CATALOGO.get(clave)
    if tipo is None:
        validos = ", ".join(sorted(CATALOGO))
        raise TipoDeReporteDesconocido(
            f"No existe el reporte '{clave}'. Tipos válidos: {validos}."
        )
    return tipo
