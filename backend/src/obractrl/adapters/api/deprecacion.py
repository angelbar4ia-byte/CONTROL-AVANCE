"""Deprecar un endpoint con ventana, no de un día para otro.

Spec §12.12 ("Contrato compatible hacia atrás: la API **no rompe** clientes
viejos — cambios **aditivos**, **deprecación con ventana**") · RFC 8594
(`Deprecation` y `Sunset`) · §11.2.

## El problema que resuelve

Desde la Fase 15 hay un cliente que no se puede actualizar a voluntad: la app
de Play. Retirar una ruta el día que deja de usarse en la web rompería a todo
el que aún no actualizó, y eso puede ser semanas (§12.13).

La ventana convierte ese riesgo en un procedimiento: se anuncia, se espera, se
retira. Y las tres partes quedan **en el contrato**, no en la cabeza de nadie:

1. `deprecated: true` y `x-sunset` en la operación de OpenAPI, que es lo que
   `scripts/verificar_compatibilidad.py` verifica en CI —quitar una ruta antes
   de su fecha pone el build en rojo—.
2. Las cabeceras `Deprecation` y `Sunset` del RFC 8594 en **cada respuesta**,
   para que un cliente se entere sin leer el contrato.
3. Un aviso en el log la primera vez que alguien la llama tras el vencimiento,
   que es la señal de que todavía hay quien depende de ella.

## Cómo se usa

    from obractrl.adapters.api.deprecacion import deprecar

    @router.get(
        "/obras/{obra_id}/programa",
        **deprecar(desde="2026-09-01", meses=6, en_favor_de="GET /obras/{id}/ruta-critica"),
    )

`deprecar` devuelve los `kwargs` del decorador —`deprecated`, `openapi_extra`,
`dependencies` y una nota al final del `description`—, así que marcar una ruta
es una línea y no cuatro cosas que se pueden desincronizar.

**Hoy no hay ninguna ruta deprecada**, y eso es lo correcto: la Fase 16 agrega
endpoints, no quita. Esto es el mecanismo listo para el primero que haga
falta; sin él, la primera deprecación se improvisaría bajo presión.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from fastapi import Depends, Response

__all__ = ["CABECERA_DEPRECATION", "CABECERA_SUNSET", "deprecar", "fecha_de_retiro"]

_log = logging.getLogger(__name__)

CABECERA_DEPRECATION = "Deprecation"
CABECERA_SUNSET = "Sunset"

MESES_POR_OMISION = 6
"""Ventana por defecto. Seis meses porque el peor caso conocido es un teléfono
de obra que solo actualiza cuando su dueño entra a Play — y eso, con una app
que funciona, puede tardar meses (§12.13)."""


def fecha_de_retiro(desde: str, meses: int = MESES_POR_OMISION) -> date:
    """Fin de la ventana. Se calcula con 30 días por mes.

    Aproximar el mes es deliberado: la fecha es un compromiso operativo, no un
    vencimiento contractual, y una aritmética de calendario exacta agregaría
    una dependencia (`dateutil`) para mover el resultado tres días.
    """
    return date.fromisoformat(desde) + timedelta(days=30 * meses)


def deprecar(
    *,
    desde: str,
    meses: int = MESES_POR_OMISION,
    en_favor_de: str | None = None,
    motivo: str | None = None,
) -> dict[str, Any]:
    """Marca una operación como deprecada con su ventana.

    `desde` es el día en que se anuncia —normalmente el del release— y no
    "hoy" calculado en tiempo de ejecución: si la fecha se moviera con cada
    despliegue, la ventana nunca terminaría de correr y el contrato diría algo
    distinto en cada regeneración.
    """
    retiro = fecha_de_retiro(desde, meses)
    anuncio = date.fromisoformat(desde)

    nota = f"**Deprecada** desde {anuncio}; se retira a partir de {retiro} (§12.12)."
    if en_favor_de:
        nota += f" Usa `{en_favor_de}` en su lugar."
    if motivo:
        nota += f" {motivo}"

    async def _cabeceras(respuesta: Response) -> None:
        # RFC 8594: `Deprecation` en formato fecha HTTP y `Sunset` igual. Se
        # ponen en la respuesta y no en un middleware para que solo las lleven
        # las rutas deprecadas — una cabecera `Deprecation` en todas sería
        # ruido que nadie mira.
        respuesta.headers[CABECERA_DEPRECATION] = _http_date(anuncio)
        respuesta.headers[CABECERA_SUNSET] = _http_date(retiro)
        if en_favor_de:
            respuesta.headers["Link"] = f'<{en_favor_de}>; rel="successor-version"'

        if date.today() >= retiro:
            # Ya venció y alguien la sigue llamando: es el dato que decide si
            # se puede retirar de verdad o si hay que extender la ventana.
            _log.warning(
                "Se llamó una ruta deprecada cuya ventana venció el %s.", retiro
            )

    return {
        "deprecated": True,
        "description": nota,
        "openapi_extra": {"x-sunset": retiro.isoformat()},
        "dependencies": [Depends(_cabeceras)],
    }


_DIAS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MESES = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def _http_date(dia: date) -> str:
    """Fecha en formato IMF-fixdate (RFC 9110 §5.6.7), que es lo que piden las
    dos cabeceras. Se arma a mano y en inglés: `strftime('%a, %d %b %Y')`
    depende del locale del proceso, y en un servidor con locale español
    escribiría "mié" donde el RFC exige "Wed"."""
    return (
        f"{_DIAS[dia.weekday()]}, {dia.day:02d} {_MESES[dia.month - 1]} "
        f"{dia.year} 00:00:00 GMT"
    )
