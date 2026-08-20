"""Cierre de obra final — workflow D (§11.2, §11.3 D).

Spec §5.1 (el Super intendente trae «Cierres de obra» en su sidebar) · §12.4 ·
§12.11 (controlador delgado).

Era el **único de los seis workflows del §11.3 sin nada de backend**: las tablas
existían con RLS desde la migración 0009 y no había ruta que las tocara.

## Quién puede qué

· **Abrir** — solo el Super intendente (§11.2 marca la `(SI)`). Abrir convoca a
  los cuatro roles a firmar una entrega; que lo dispare quien responde por la
  organización es lo que impide que la obra se dé por entregada desde dentro.
· **Participar** — los cuatro roles, uno cada uno. No lleva `exigir_rol`: el rol
  sale del token y el dominio decide si participa y si ya lo hizo.
· **Consultar** — quien vea la obra. RLS decide.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    AbrirCierreDeObraDep,
    ConsultarCierreDeObraDep,
    ParticiparEnCierreDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, SesionRLS, exigir_rol
from obractrl.adapters.api.idempotencia import Idempotencia
from obractrl.adapters.repos.cierres_obra_sql import RepositorioCierresDeObraSQL
from obractrl.application.casos_uso.gestionar_cierre_de_obra import (
    ComandoAbrirCierreDeObra,
    ComandoParticipar,
    ResultadoDeCierreDeObra,
)
from obractrl.domain.cierres.obra import APORTACION_POR_ROL
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["cierres-obra"])


class PendienteRespuesta(BaseModel):
    """Algo que falta para poder firmar la entrega (§11.3 D.1)."""

    clave: str
    detalle: str
    bloquea: bool = Field(
        description=(
            "Los que bloquean impiden cerrar; los demás se muestran para que "
            "alguien los mire. Un expediente vacío no es lo mismo que una "
            "estimación sin validar."
        )
    )
    cuantos: int = 0


class CierreDeObraRespuesta(BaseModel):
    """Estado del acta (§11.3 D)."""

    id: UUID
    obra_id: UUID
    estatus: str = Field(description="en_proceso | cerrada")
    pendientes: list[PendienteRespuesta]
    participaron: list[str]
    faltan: list[str] = Field(
        description="Roles que todavía no registran su parte (§11.3 D.2)."
    )
    puede_cerrarse: bool = Field(
        description="Participaron todos y no queda ningún pendiente bloqueante."
    )
    cerro_la_obra: bool = Field(
        default=False,
        description=(
            "`true` solo en la participación que completó el acta: permite decir "
            "«la obra quedó entregada» en vez de «guardado»."
        ),
    )

    @classmethod
    def desde(cls, resultado: ResultadoDeCierreDeObra) -> CierreDeObraRespuesta:
        return cls(
            id=resultado.id,
            obra_id=resultado.obra_id,
            estatus=resultado.estatus,
            pendientes=[
                PendienteRespuesta(
                    clave=p.clave,
                    detalle=p.detalle,
                    bloquea=p.bloquea,
                    cuantos=p.cuantos,
                )
                for p in resultado.pendientes
            ],
            participaron=[r.value for r in resultado.participaron],
            faltan=[r.value for r in resultado.faltan],
            puede_cerrarse=(
                not resultado.faltan
                and not any(p.bloquea for p in resultado.pendientes)
            ),
            cerro_la_obra=resultado.cerro_la_obra,
        )


class ResumenDeCierreRespuesta(BaseModel):
    """Renglón de la bandeja de cierres de obra (§5.1)."""

    id: UUID
    obra_id: UUID
    obra_clave: str
    obra_estatus: str
    estatus: str
    fecha: date | None = None
    acta: str | None = None
    abierto_por: UUID | None = None
    created_at: datetime


class ParticipacionRespuesta(BaseModel):
    id: UUID
    rol: str
    aportacion: str = Field(
        description="Qué aporta ese rol al acta: entrega, visto bueno, calidad, firma."
    )
    usuario_id: UUID
    usuario_nombre: str | None = None
    comentario: str | None = None
    evidencias: list[str] = Field(default_factory=list)
    fecha: datetime


class ParticiparPeticion(BaseModel):
    comentario: str | None = None
    evidencias: list[str] = Field(
        default_factory=list,
        description="Claves ya subidas a R2 con `POST /evidencias/presigned` (§12.2).",
    )
    acta: str | None = Field(
        default=None,
        description=(
            "Texto del acta. Lo aporta la firma del Super intendente; en los "
            "demás roles se ignora, porque el acta es del cierre y no de cada "
            "parte."
        ),
    )


@router.post(
    "/obras/{obra_id}/cierre-obra",
    response_model=CierreDeObraRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Abrir el cierre de obra final",
    dependencies=[Depends(exigir_rol(Rol.SUPER_INTENDENTE)), Idempotencia],
    responses={
        403: {"description": "Solo el super intendente abre el cierre (§11.2)."},
        404: {"description": "La obra no existe o está fuera de tu alcance."},
    },
)
async def abrir_cierre_de_obra(
    obra_id: UUID, ctx: ContextoActual, caso: AbrirCierreDeObraDep
) -> CierreDeObraRespuesta:
    """Crea el acta y **reúne los pendientes** (§11.3 D.1).

    Abrir con pendientes está permitido y es el punto: convocar al equipo es lo
    que hace que se resuelvan. Lo que no se puede es firmar con ellos.

    Idempotente por partida doble: la cabecera evita la segunda petición y
    `uq_cierre_obra` garantiza que una obra tenga un solo cierre — reabrirlo
    devuelve el que ya estaba.
    """
    resultado = await caso.ejecutar(
        ComandoAbrirCierreDeObra(
            obra_id=obra_id, usuario_id=ctx.usuario_id, rol=Rol(ctx.rol)
        )
    )
    return CierreDeObraRespuesta.desde(resultado)


@router.post(
    "/cierres-obra/{cierre_id}/participar",
    response_model=CierreDeObraRespuesta,
    summary="Registrar la parte de tu rol en el acta",
    dependencies=[Idempotencia],
    responses={
        404: {"description": "El cierre no existe o está fuera de tu alcance."},
        422: {
            "description": (
                "Ese rol ya participó, la obra ya está cerrada, o al completarse "
                "el acta quedaban pendientes que impiden entregar."
            )
        },
    },
)
async def participar(
    cierre_id: UUID,
    peticion: ParticiparPeticion,
    ctx: ContextoActual,
    caso: ParticiparEnCierreDep,
) -> CierreDeObraRespuesta:
    """Cada rol registra lo suyo (§11.3 D.2).

    El rol sale del token, nunca del cuerpo: es lo que decide qué parte del acta
    se está firmando, así que aceptarlo del cliente sería dejar que alguien
    firmara por otro.

    Con la cuarta participación el acta se completa y la obra queda
    **entregada** y congelada (§11.3 D.3) — en la misma transacción, no por
    evento: el razonamiento está en el caso de uso.
    """
    resultado = await caso.ejecutar(
        ComandoParticipar(
            cierre_id=cierre_id,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            comentario=peticion.comentario,
            evidencias=tuple(peticion.evidencias),
            acta=peticion.acta,
        )
    )
    return CierreDeObraRespuesta.desde(resultado)


@router.get(
    "/cierres-obra",
    response_model=list[ResumenDeCierreRespuesta],
    summary="Bandeja de cierres de obra",
)
async def listar_cierres_de_obra(
    sesion: SesionRLS,
    estatus: Annotated[
        str | None, Query(description="en_proceso | cerrada")
    ] = None,
) -> list[dict]:
    """Los cierres visibles (§5.1).

    Sin `exigir_rol`: el §11.2 pone la `(SI)` sobre el alta, y el acta la miran
    los cuatro roles —cada uno tiene que ir a firmar la suya—. RLS ya acota a
    las obras que cada quien ve.
    """
    return await RepositorioCierresDeObraSQL(sesion).listar(estatus=estatus)


@router.get(
    "/cierres-obra/{cierre_id}",
    response_model=CierreDeObraRespuesta,
    summary="Estado del acta y lo que falta",
    responses={404: {"description": "El cierre no existe o está fuera de tu alcance."}},
)
async def obtener_cierre_de_obra(
    cierre_id: UUID, caso: ConsultarCierreDeObraDep
) -> CierreDeObraRespuesta:
    return CierreDeObraRespuesta.desde(await caso.ejecutar(cierre_id))


@router.get(
    "/cierres-obra/{cierre_id}/participaciones",
    response_model=list[ParticipacionRespuesta],
    summary="Quién ha firmado y qué dijo",
    responses={404: {"description": "El cierre no existe o está fuera de tu alcance."}},
)
async def listar_participaciones(
    cierre_id: UUID, sesion: SesionRLS
) -> list[ParticipacionRespuesta]:
    """Las partes ya registradas (§11.3 D.2).

    Va aparte del estado y no anidada dentro porque son dos preguntas con
    ritmos distintos: el estado se consulta al abrir la pantalla y las partes
    solo cuando alguien quiere leer lo que escribieron los demás.
    """
    filas = await RepositorioCierresDeObraSQL(sesion).participaciones(cierre_id)
    return [
        ParticipacionRespuesta(
            id=fila["id"],
            rol=str(fila["rol"]),
            aportacion=APORTACION_POR_ROL.get(Rol(fila["rol"]), ""),
            usuario_id=fila["usuario_id"],
            usuario_nombre=fila.get("usuario_nombre"),
            comentario=fila.get("comentario"),
            evidencias=fila.get("evidencias") or [],
            fecha=fila["fecha"],
        )
        for fila in filas
    ]
