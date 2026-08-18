"""`Idempotency-Key` en las mutaciones sensibles.

Spec §11.2 ("Mutaciones sensibles con `Idempotency-Key`") · §12.3 · §12.4.

El problema real: una solicitud de cierre o una estimación que se manda dos
veces —doble clic, red que se cae después de que el servidor ya escribió, un
reintento automático— crea dos. Y son documentos con folio y con dinero
(§11.3 C y E), así que el duplicado no es un detalle cosmético.

## Cómo funciona

La dependencia corre **antes** del endpoint y sobre **la misma sesión** que va
a usar el caso de uso. Eso es lo que hace que el registro de la clave y la
mutación queden en la misma transacción: `sesion_con_rls` abre una transacción
por petición y `UnidadDeTrabajoSQL.commit()` la cierra, así que el `insert` de
aquí y el cierre que se crea después viajan juntos. O quedan los dos o no queda
ninguno.

Si la clave ya existe, la mutación **no se ejecuta**:

- misma huella (mismo método, ruta y cuerpo) → `PeticionYaProcesada` → 409,
- huella distinta → `ClaveReusada` → 422, porque reusar una clave para otra
  petición es un error del cliente, no un reintento.

## Lo que este diseño NO hace, y por qué

No guarda la respuesta original para devolverla en el reintento. Guardarla
obligaría a escribirla **después** del commit —la respuesta no existe antes—,
o sea en una segunda transacción, y un fallo justo ahí dejaría una clave sin
respuesta: el reintento tendría que contestar 409 de todas formas. Se prefiere
contestar 409 siempre, que es un contrato simple y honesto: *esto ya se
procesó, no lo repitas*. El invariante que importa —que la operación ocurra
exactamente una vez— se cumple entero.

Un cliente que necesite el cuerpo original vuelve a consultar el recurso, que
es una lectura barata y siempre disponible.

## Opcional, no obligatoria

Sin cabecera la petición pasa igual. Exigirla rompería a cualquier cliente
existente y el §11.2 la pide como mecanismo, no como requisito de admisión.
Quien la manda, se protege.
"""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from obractrl.adapters.api.dependencias import SesionRLS

__all__ = [
    "CABECERA",
    "ClaveDeIdempotenciaInvalida",
    "ClaveReusada",
    "Idempotencia",
    "PeticionYaProcesada",
]

CABECERA = "Idempotency-Key"

LARGO_MAXIMO = 128
"""Un UUID cabe de sobra. El tope existe porque el valor lo elige el cliente y
acaba en un índice único: sin él, una cabecera de 8 KB por petición."""


class PeticionYaProcesada(Exception):
    """La misma clave y la misma petición: ya se ejecutó una vez (§11.2)."""

    def __init__(self, clave: str) -> None:
        super().__init__(
            f"Esta petición ya se procesó con la clave de idempotencia "
            f"{clave!r}. No se repitió; consulta el recurso para ver cómo "
            f"quedó."
        )
        self.clave = clave


class ClaveReusada(Exception):
    """La clave ya se usó, pero para **otra** petición.

    Es un error del cliente y no un reintento: contestar como si fuera lo
    mismo ejecutaría —o daría por hecha— una operación distinta de la que se
    pidió.
    """

    def __init__(self, clave: str) -> None:
        super().__init__(
            f"La clave de idempotencia {clave!r} ya se usó para otra petición "
            f"distinta. Usa una clave nueva por cada operación."
        )
        self.clave = clave


class ClaveDeIdempotenciaInvalida(ValueError):
    """La cabecera vino vacía o desmedida."""


async def _huella(request: Request) -> str:
    """SHA-256 de método + ruta + cuerpo.

    El cuerpo se lee del `Request`; FastAPI lo cachea, así que leerlo aquí no
    se lo quita al endpoint —que lo parsea después—.
    """
    cuerpo = await request.body()
    digestor = hashlib.sha256()
    digestor.update(request.method.encode())
    digestor.update(b"\0")
    digestor.update(request.url.path.encode())
    digestor.update(b"\0")
    digestor.update(cuerpo)
    return digestor.hexdigest()


async def _registrar(sesion: SesionRLS, *, clave: str, request: Request) -> None:
    huella = await _huella(request)

    fila = (
        await sesion.execute(
            text(
                """
                select huella from idempotencia
                 where org_id = cast(current_setting('app.org_id') as uuid)
                   and usuario_id = cast(current_setting('app.usuario_id') as uuid)
                   and clave = :clave
                """
            ),
            {"clave": clave},
        )
    ).first()

    if fila is not None:
        raise (
            PeticionYaProcesada(clave)
            if fila.huella == huella
            else ClaveReusada(clave)
        )

    try:
        await sesion.execute(
            text(
                """
                insert into idempotencia
                    (org_id, usuario_id, clave, metodo, ruta, huella)
                values
                    (cast(current_setting('app.org_id') as uuid),
                     cast(current_setting('app.usuario_id') as uuid),
                     :clave, :metodo, :ruta, :huella)
                """
            ),
            {
                "clave": clave,
                "metodo": request.method,
                "ruta": request.url.path,
                "huella": huella,
            },
        )
    except IntegrityError as exc:
        # Dos peticiones idénticas **en paralelo**: la primera insertó y esta
        # choca con `uq_idempotencia`. Es el caso que el `select` de arriba no
        # puede cubrir —entre leer y escribir hay una ventana— y es justo el
        # del doble clic. Se trata igual que si la hubiéramos visto: la otra
        # está haciendo el trabajo.
        raise PeticionYaProcesada(clave) from exc


async def idempotencia(
    request: Request,
    # `SesionRLS` ya depende del contexto del JWT, así que para cuando esto
    # corre, `app.org_id` y `app.usuario_id` están fijados en la sesión.
    sesion: SesionRLS,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias=CABECERA,
            description=(
                "Clave única por operación (un UUID sirve). Si se repite, la "
                "mutación no se vuelve a ejecutar y la API responde 409. "
                "Opcional: sin ella la petición pasa igual, sin protección."
            ),
        ),
    ] = None,
) -> None:
    """Dependencia de las mutaciones sensibles (§11.2).

    Se declara en `dependencies=[...]` del endpoint: no devuelve nada, su
    efecto es dejar la clave registrada en la transacción de la petición —o
    cortarla si ya estaba.
    """
    if idempotency_key is None:
        return

    clave = idempotency_key.strip()
    if not clave or len(clave) > LARGO_MAXIMO:
        raise ClaveDeIdempotenciaInvalida(
            f"La cabecera {CABECERA} viene vacía o excede {LARGO_MAXIMO} "
            f"caracteres."
        )

    await _registrar(sesion, clave=clave, request=request)


Idempotencia = Depends(idempotencia)
"""Se usa como `dependencies=[Idempotencia]` en el endpoint."""
