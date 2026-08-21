"""Registro de dispositivos para Expo Push.

Spec §12.2 ("Notificaciones — Resend (correo) + **Expo Push**") · §7.9
(`Notificacion`) · §12.4 (multi-tenant) · migración 0028.

El móvil registra su `ExponentPushToken[...]` al entrar y lo da de baja al
cerrar sesión. No hay más superficie: el envío lo hace el backend desde los
manejadores de eventos, nunca el cliente.

**Por qué el alta es un `PUT` lógico y no un `POST` que falla en duplicado.**
El token de Expo cambia solo —reinstalación, restauración de respaldo, upgrade
del sistema— y la app lo reenvía en cada arranque con sesión. Si el segundo
registro devolviera 409, el cliente tendría que distinguir "ya estaba" de "no
se pudo" en cada inicio. `on conflict (token) do update` lo hace idempotente:
registrar dos veces es registrar una.

Ese `do update` además **reasigna** `usuario_id`. Es el caso del teléfono
prestado: si el token siguiera apuntando al usuario anterior, ese aparato
recibiría notificaciones de obras que su nuevo dueño no puede ver.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from obractrl.adapters.api.dependencias import ContextoActual, SesionRLS

router = APIRouter(tags=["dispositivos"])


class RegistrarDispositivoPeticion(BaseModel):
    """Lo que manda la app al entrar (`mobile/src/lib/push.ts`)."""

    token: str = Field(
        min_length=8,
        max_length=512,
        description="`ExponentPushToken[...]` que emitió Expo para esta instalación.",
    )
    plataforma: Literal["android", "ios"] = "android"
    version_app: str | None = Field(
        default=None,
        description="Versión visible del cliente (§12.12). Diagnóstico, no autorización.",
    )


class DispositivoRespuesta(BaseModel):
    token: str
    activo: bool


@router.post(
    "/dispositivos/push",
    response_model=DispositivoRespuesta,
    status_code=status.HTTP_200_OK,
    summary="Registrar el token de Expo Push de este dispositivo",
)
async def registrar_dispositivo(
    peticion: RegistrarDispositivoPeticion, ctx: ContextoActual, sesion: SesionRLS
) -> DispositivoRespuesta:
    """Alta idempotente del token (§12.2).

    Responde **200 y no 201** porque casi siempre es una revalidación del
    mismo token: un 201 en cada arranque mentiría sobre lo que pasó.

    `org_id` y `usuario_id` salen del token JWT, nunca del cuerpo (§12.4): si
    el cliente pudiera elegirlos, registraría su teléfono a nombre de otro y
    recibiría las notificaciones de sus obras. La política RLS
    `dispositivo_push_propio` lo refuerza aunque esta ruta se equivoque.
    """
    await sesion.execute(
        text(
            """
            insert into dispositivo_push
                (org_id, usuario_id, token, plataforma, version_app, activo, ultimo_uso)
            values
                (:org_id, :usuario_id, :token, :plataforma, :version_app, true, now())
            on conflict (token) do update
               set usuario_id  = excluded.usuario_id,
                   org_id      = excluded.org_id,
                   plataforma  = excluded.plataforma,
                   version_app = excluded.version_app,
                   activo      = true,
                   ultimo_uso  = now()
            """
        ),
        {
            "org_id": str(ctx.org_id),
            "usuario_id": str(ctx.usuario_id),
            "token": peticion.token,
            "plataforma": peticion.plataforma,
            "version_app": peticion.version_app,
        },
    )
    # `sesion_con_rls` no commitea: lo hace `UnidadDeTrabajoSQL` en los casos
    # de uso. Esta ruta no tiene caso de uso —es una escritura sin dominio,
    # como `GET /me` es una lectura sin dominio— así que confirma aquí. Sin
    # esto, el token se registraría "bien" y se perdería al cerrar la sesión.
    await sesion.commit()
    return DispositivoRespuesta(token=peticion.token, activo=True)


@router.delete(
    "/dispositivos/push/{token}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dar de baja el token de este dispositivo",
)
async def dar_de_baja(token: str, sesion: SesionRLS) -> None:
    """Baja al cerrar sesión.

    Desactiva en vez de borrar, igual que hace el envío ante un
    `DeviceNotRegistered` (ver la migración 0028): la fila es el rastro de que
    ese dispositivo existió, y volver a entrar la reactiva sin parecer un alta
    nueva.

    **No responde 404 si no existe.** Cerrar sesión no puede fallar porque el
    token ya no estuviera: el resultado que el cliente pidió —que ese aparato
    deje de recibir— se cumple igual. RLS acota el `update` al dueño (§12.4),
    así que nadie da de baja el dispositivo de otro aunque adivine el token.
    """
    await sesion.execute(
        text("update dispositivo_push set activo = false where token = :token"),
        {"token": token},
    )
    await sesion.commit()
