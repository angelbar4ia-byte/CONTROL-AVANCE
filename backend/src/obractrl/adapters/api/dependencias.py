"""Dependencias del borde HTTP: autenticación y contexto RLS.

Spec §12.4 · §11.2 (convenciones de API).

`org_id` y `rol` salen del token; nunca de la petición. Un cliente no puede
pedir datos de otra organización aunque lo intente: RLS filtra por el
contexto que se fija aquí.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.domain.shared.diccionario import Rol
from obractrl.infrastructure.config import Config, obtener_config
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls

__all__ = ["ContextoActual", "SesionRLS", "exigir_rol"]

_log = logging.getLogger(__name__)
_bearer = HTTPBearer(auto_error=False)
"""`auto_error=False` a propósito.

Con `True`, FastAPI responde una petición **sin** cabecera `Authorization` con
un **403 "Not authenticated"**, que le dice al cliente lo contrario de lo que
pasa: 403 significa "te identifiqué y no puedes", y aquí nadie se identificó.
Un front que distingue "manda a login" de "muestra "no tienes permiso"" —el
nuestro lo hace— acabaría enseñando la pantalla equivocada, y el 403 tampoco
lleva `WWW-Authenticate`.

Apagándolo, la falta de credenciales cae en `contexto_actual` y sale por
`_no_autorizado`, igual que un token expirado o inválido: 401 con
`WWW-Authenticate: Bearer` (RFC 9110 §11.6.1).
"""


def _no_autorizado(detalle: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detalle,
        headers={"WWW-Authenticate": "Bearer"},
    )


@lru_cache(maxsize=4)
def _cliente_jwks(url: str) -> PyJWKClient:
    """Un cliente JWKS por URL, cacheado.

    `PyJWKClient` guarda las llaves que ya trajo, así que cachear la instancia
    es lo que evita una petición HTTP al proveedor en cada request. Ante un
    `kid` desconocido —una rotación de llaves— vuelve a consultar el JWKS él
    solo, sin redespliegue.
    """
    return PyJWKClient(url, cache_keys=True)


def _llave_de_verificacion(token: str, cfg: Config) -> str:
    """Llave con la que se verifica la firma.

    Supabase firma con llaves **asimétricas** (ES256) y publica la pública en
    el JWKS del proyecto; el secreto compartido nunca llega al backend. Si no
    hay JWKS configurado se cae al `jwt_secret`, que es el esquema HS256
    antiguo y sigue sirviendo para entornos que aún lo usen (§12.4).
    """
    url = cfg.jwks_url_efectiva
    if not url:
        return cfg.jwt_secret
    try:
        return _cliente_jwks(url).get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientError as exc:
        # No se distingue del token inválido hacia afuera: que el JWKS no
        # responda o no tenga el `kid` no es algo que el cliente pueda
        # arreglar, y detallarlo solo daría pistas de la infraestructura.
        # Al log sí, que es donde el operador puede actuar.
        _log.warning("JWKS falló (%s): %s: %s", url, type(exc).__name__, exc)
        raise _no_autorizado("Token inválido.") from exc


async def contexto_actual(
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    cfg: Annotated[Config, Depends(obtener_config)],
) -> ContextoSesion:
    """Extrae `org_id`, `usuario_id` y `rol` del JWT (§12.4)."""
    if credenciales is None:
        # Sin cabecera `Authorization`. Mismo 401 que un token malo: al
        # cliente no se le dice si el problema fue no mandarlo o mandarlo mal
        # —no cambia lo que tiene que hacer, que es autenticarse—.
        raise _no_autorizado("Falta la cabecera Authorization: Bearer <token>.")

    try:
        claims = jwt.decode(
            credenciales.credentials,
            _llave_de_verificacion(credenciales.credentials, cfg),
            algorithms=cfg.jwt_algoritmos,
            audience=cfg.jwt_audiencia,
            # Tolerancia de reloj (§12.4). El token lo emite Supabase y lo
            # valida otro host: si el nuestro va unos segundos atrasado, el
            # `iat` parece futuro y PyJWT lo rechaza como prematuro
            # (`ImmatureSignatureError`) aunque sea legítimo. Pasó en
            # producción y se veía como "token inválido" intermitente.
            #
            # La holgura recorta lo mismo por el otro lado —un token seguiría
            # siendo aceptado unos segundos tras expirar—, y por eso se
            # mantiene en el orden de segundos y no de minutos.
            leeway=cfg.jwt_holgura_segundos,
        )
    except jwt.ExpiredSignatureError as exc:
        raise _no_autorizado("El token expiró.") from exc
    except jwt.InvalidTokenError as exc:
        # Al cliente se le responde siempre lo mismo —no se le dice por qué
        # falló, sería darle pistas—, pero el operador necesita distinguir
        # "firma mala" de "audiencia equivocada" o "algoritmo no soportado":
        # los tres dan 401 y sin esto no hay forma de separarlos.
        _log.warning("JWT rechazado: %s: %s", type(exc).__name__, exc)
        raise _no_autorizado("Token inválido.") from exc
    except (ValueError, TypeError) as exc:
        # Llave y algoritmo incompatibles: p. ej. el proveedor firma ES256
        # pero falta `SUPABASE_URL` y se cayó al secreto HS256, así que se
        # intenta leer un string como llave EC. `cryptography` levanta
        # ValueError, que NO es InvalidTokenError y sin este caso escapaba
        # como 500. Un despliegue mal configurado no debe verse como una
        # falla del cliente ni tirar la petición con un error opaco.
        raise _no_autorizado("Token inválido.") from exc

    org_id = claims.get("org_id")
    usuario_id = claims.get("usuario_id") or claims.get("sub")
    rol = claims.get("rol")

    if not org_id or not usuario_id or not rol:
        raise _no_autorizado(
            "El token no trae org_id, usuario_id y rol. Sin ellos no se puede "
            "fijar el contexto RLS."
        )

    try:
        rol_canonico = Rol(rol)
    except ValueError as exc:
        raise _no_autorizado(f"Rol desconocido en el token: {rol!r}") from exc

    return ContextoSesion(
        org_id=UUID(str(org_id)),
        usuario_id=UUID(str(usuario_id)),
        rol=rol_canonico.value,
    )


ContextoActual = Annotated[ContextoSesion, Depends(contexto_actual)]


async def sesion_rls(ctx: ContextoActual) -> AsyncIterator[AsyncSession]:
    """Sesión de BD con el contexto RLS ya aplicado."""
    async with sesion_con_rls(ctx) as sesion:
        yield sesion


SesionRLS = Annotated[AsyncSession, Depends(sesion_rls)]


def exigir_rol(*roles: Rol):
    """Guarda de RBAC para un endpoint (§12.4).

    RBAC en la API **y** reforzado por RLS: esto da un 403 legible; RLS es lo
    que garantiza el aislamiento aunque la guarda faltara.

        @router.post("/cierres/{id}/autorizar",
                     dependencies=[Depends(exigir_rol(Rol.SUPERVISOR))])
    """
    permitidos = {r.value for r in roles}

    async def _guarda(ctx: ContextoActual) -> None:
        if ctx.rol not in permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"El rol {ctx.rol!r} no puede ejecutar esta acción. "
                    f"Roles permitidos: {', '.join(sorted(permitidos))}."
                ),
            )

    return _guarda
