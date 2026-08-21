"""El cuerpo de un error no previsto, en un solo lugar.

Spec §11.2 (`problem+json`, RFC 7807) · §11.7 (observabilidad) · §12.4.

Existe porque **dos caminos distintos** producen el mismo 500 y tienen que
decir exactamente lo mismo:

- el manejador de `Exception` que registra `main.py`, para todo lo que llega
  hasta el borde por la vía normal;
- `MiddlewareDeErroresConCORS`, que atrapa el fallo *dentro* de la pila de CORS
  para que la respuesta salga con sus cabeceras (ver su docstring: sin eso el
  navegador reporta un problema de CORS en vez del 500 que de verdad ocurrió).

Si el cuerpo viviera en el manejador, el middleware tendría que copiarlo, y el
día que uno de los dos cambie el otro se queda mintiendo.

**El detalle nunca lleva el mensaje de la excepción.** Un `str(exc)` de algo no
previsto puede traer un fragmento de SQL, una ruta del servidor o el valor de
la fila que se estaba procesando (§12.4). Lo que sí va es el `request_id`, que
es lo que permite cruzar el reporte del usuario con la traza del servidor.
"""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from obractrl.infrastructure.observabilidad import id_de_peticion

__all__ = ["TIPO_BASE", "cuerpo_de_problema", "problema_no_previsto"]

TIPO_BASE = "https://obractrl.mx/errores/"


def cuerpo_de_problema(
    *, status: int, tipo: str, titulo: str, detalle: str, ruta: str, **extra: Any
) -> dict[str, Any]:
    """El diccionario de `problem+json` (RFC 7807) con la extensión de la casa."""
    return {
        "type": f"{TIPO_BASE}{tipo}",
        "title": titulo,
        "status": status,
        "detail": detalle,
        "instance": ruta,
        # Extensión propia (RFC 7807 §3.2 las permite). Es el mismo id que va
        # en `X-Request-Id` y en cada línea de log de esta petición: es lo que
        # convierte "me falló" en algo buscable.
        "request_id": id_de_peticion(),
        **extra,
    }


def problema_no_previsto(ruta: str, *, clase: str | None = None) -> JSONResponse:
    """El 500 genérico. Lo devuelven el manejador y el middleware por igual.

    `clase` es el **nombre** de la excepción, nunca su mensaje: nombrar
    `IntegrityError` no revela nada y es lo que permite cruzar el reporte del
    usuario con la traza del servidor; `str(exc)` sí podría traer el SQL o la
    fila que se estaba procesando (§12.4).
    """
    detalle = (
        "La petición no se pudo completar por un fallo del servidor. "
        "El detalle quedó en el log; si el problema persiste, repórtalo "
    )
    detalle += f"con la clase del fallo: {clase}." if clase else "con su `request_id`."

    return JSONResponse(
        status_code=500,
        media_type="application/problem+json",
        content=cuerpo_de_problema(
            status=500,
            tipo="error-interno",
            titulo="Error interno",
            detalle=detalle,
            ruta=ruta,
        ),
    )
