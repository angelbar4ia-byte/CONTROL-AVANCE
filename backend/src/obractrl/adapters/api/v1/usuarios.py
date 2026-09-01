"""Endpoints de usuarios y alcance (§11.2 "Identidad y organización").

Spec §4 (roles) · §5.1 ("Equipo" · el alta la hace Control de obra) · §7.1 ·
§12.4 (RLS) · §12.11 (controlador delgado).

Controladores delgados: validan el DTO, delegan y mapean. **Cero lógica de
negocio** — quién puede otorgar qué rol vive en `domain.identidad.reglas`, y
la base lo vuelve a imponer con el trigger de la migración 0025.

LA CONTRASEÑA TEMPORAL NO VUELVE EN NINGUNA RESPUESTA

Entra en el cuerpo de la petición y se acabó: quien la fijó ya la conoce, y
devolverla la metería en el historial del navegador, en los logs de cualquier
proxy y en la caché de TanStack Query. Por la misma razón el modelo de
respuesta del alta **no** hereda del de la petición: un `response_model` que
incluyera el campo la publicaría sin que nadie lo notara.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    ActualizarUsuarioDep,
    AsignarAlcanceDep,
    CrearUsuarioDep,
    ResetearContrasenaDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, SesionRLS, exigir_rol
from obractrl.adapters.api.idempotencia import Idempotencia
from obractrl.adapters.repos.asignaciones_sql import RepositorioAsignacionesSQL
from obractrl.adapters.repos.usuarios_sql import RepositorioUsuariosSQL
from obractrl.application.casos_uso.gestionar_usuarios import (
    ComandoActualizarUsuario,
    ComandoAsignarAlcance,
    ComandoCrearUsuario,
    ComandoResetearContrasena,
)
from obractrl.domain.identidad.reglas import LARGO_MINIMO_CONTRASENA
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["usuarios"])

ADMINISTRA = Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE))
"""El alta y la edición del equipo son de C y SI (§5.1, §11.2)."""

REPARTE = Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE, Rol.SUPERVISOR))
"""Repartir alcance incluye al supervisor, y solo desde la migración 0042.

El supervisor distribuye SU cartera entre SUS residentes —es su trabajo diario
y el usuario lo pidió así ("el supervisor a sus residentes")— pero no puede
traerse una obra que no ve: eso lo cierra `app.puede_repartir_obra()` en la
base, no esta lista de roles. Aquí solo se descarta al residente, que no
reparte nada.
"""

FiltroRol = Annotated[
    Rol | None, Query(description="Acota el listado a un rol del §4.")
]


class UsuarioRespuesta(BaseModel):
    """Una persona del equipo, como la ve la pantalla de Equipo (§5.1)."""

    id: UUID
    nombre: str
    email: str
    rol: str = Field(
        description="residente | supervisor | control_obra | super_intendente"
    )
    cedula: str | None = None
    telefono: str | None = None
    estatus: str = "activo"
    puede_entrar: bool = Field(
        description=(
            "Tiene cuenta ligada en el proveedor de auth. Un `false` aquí es "
            "alguien que aparece en el equipo y no puede iniciar sesión: "
            "normalmente, un alta que quedó a medias."
        )
    )
    debe_cambiar_password: bool = Field(
        description=(
            "Su contraseña la eligió alguien más y aún no la ha cambiado (§5.1)."
        )
    )


class CrearUsuarioPeticion(BaseModel):
    nombre: str = Field(min_length=1)
    email: str = Field(min_length=3)
    rol: Rol
    contrasena_temporal: str = Field(
        min_length=LARGO_MINIMO_CONTRASENA,
        description=(
            "La contraseña con la que entra la primera vez. Se le exigirá "
            "cambiarla. No vuelve en ninguna respuesta."
        ),
    )
    cedula: str | None = None
    telefono: str | None = None


class ActualizarUsuarioPeticion(BaseModel):
    """Todo opcional: lo que no viene, no se toca.

    `rol` y `activo` no son campos de perfil como los demás — el trigger de la
    0025 los vigila y el dominio los valida—, pero viajan en el mismo PATCH
    porque desde la pantalla son la misma acción: editar a alguien.
    """

    nombre: str | None = Field(default=None, min_length=1)
    cedula: str | None = None
    telefono: str | None = None
    rol: Rol | None = None
    activo: bool | None = Field(
        default=None,
        description=(
            "`false` da de baja. **No borra**: sus capturas y cierres siguen "
            "apuntando a esta persona y el expediente tiene que poder decir "
            "quién los hizo (§11.3)."
        ),
    )


class ResetearContrasenaPeticion(BaseModel):
    contrasena_temporal: str = Field(min_length=LARGO_MINIMO_CONTRASENA)


class AlcancePeticion(BaseModel):
    """Lo que se le da a UNA persona (§4, cadena de mando de la 0042).

    El `usuario_id` de la ruta es siempre el jefe o el dueño de la cartera. Qué
    lista aplica lo decide su rol; mandar la que no corresponde es un 422 con
    el motivo escrito, no un silencio.
    """

    gente: list[UUID] = Field(
        default_factory=list,
        description=(
            "Personas que cuelgan de él. A un super intendente, supervisores "
            "y/o residentes; a un supervisor, residentes. Mover un residente "
            "arrastra su cartera de obras con él."
        ),
    )
    obras: list[UUID] = Field(
        default_factory=list,
        description=(
            "Obras de un residente. Es lo que de verdad decide qué ve él —y, "
            "hacia arriba, su supervisor y su super intendente."
        ),
    )
    clusters: list[UUID] = Field(
        default_factory=list,
        description=(
            "Manzanas que recorre un supervisor. Dato territorial: desde la "
            "migración 0042 ya NO le abre ninguna obra."
        ),
    )
    proyectos: list[UUID] = Field(
        default_factory=list,
        description=(
            "Proyectos de un control de obra. Inerte desde la migración 0042: "
            "Control ve toda la organización."
        ),
    )
    retirar: bool = Field(
        default=False, description="Quita en vez de dar."
    )


class AlcanceRespuesta(BaseModel):
    usuario_id: UUID
    gente: list[dict] = Field(
        default_factory=list,
        description="`{id, nombre, email, rol}` de quienes cuelgan de él.",
    )
    obras: list[dict] = Field(
        default_factory=list,
        description=(
            "`{id, clave, cluster_id, estatus, avance_pct, es_principal}`. "
            "`es_principal` es el residente que quedó en `obra.residente_id`."
        ),
    )
    clusters: list[dict] = Field(
        default_factory=list, description="`{id, clave, nombre, proyecto_id}`."
    )
    proyectos: list[dict] = Field(
        default_factory=list, description="`{id, clave, nombre}`."
    )


class IdRespuesta(BaseModel):
    id: UUID


# --- Equipo --------------------------------------------------------------


@router.get(
    "/usuarios",
    response_model=list[UsuarioRespuesta],
    summary="El equipo de la organización",
)
async def listar_usuarios(sesion: SesionRLS, rol: FiltroRol = None) -> list[dict]:
    """Todos los usuarios visibles (§5.1).

    Lo puede leer cualquier rol: saber quién es el residente de una obra o a
    qué supervisor escribirle no es información privilegiada, y RLS ya acota el
    listado a la organización del token (`usuario_select`, migración 0012).
    """
    return await RepositorioUsuariosSQL(sesion).listar(
        rol=rol.value if rol else None
    )


@router.post(
    "/usuarios",
    response_model=IdRespuesta,
    status_code=status.HTTP_201_CREATED,
    # Idempotente porque el alta cruza a **otro sistema**: un doble clic
    # llamaría dos veces a la Admin API y, aunque la segunda chocaría contra
    # `uq_usuario_email_org`, dejaría el rastro de una cuenta creada y borrada
    # por compensación. Con la clave, la segunda petición ni siquiera entra.
    dependencies=[ADMINISTRA, Idempotencia],
    summary="Dar de alta a alguien del equipo",
)
async def crear_usuario(
    peticion: CrearUsuarioPeticion,
    caso: CrearUsuarioDep,
    ctx: ContextoActual,
) -> IdRespuesta:
    """Crea la cuenta y la fila (§5.1).

    `quien` sale del token y nunca del cuerpo: es lo que decide qué roles se
    pueden otorgar, así que aceptarlo del cliente sería dejar que se lo
    invente.
    """
    resultado = await caso.ejecutar(
        ComandoCrearUsuario(
            nombre=peticion.nombre,
            email=peticion.email,
            rol=peticion.rol,
            contrasena_temporal=peticion.contrasena_temporal,
            quien=Rol(ctx.rol),
            cedula=peticion.cedula,
            telefono=peticion.telefono,
        )
    )
    return IdRespuesta(id=resultado.id)


@router.patch(
    "/usuarios/{usuario_id}",
    response_model=IdRespuesta,
    dependencies=[ADMINISTRA],
    summary="Editar perfil, rol o estatus",
)
async def actualizar_usuario(
    usuario_id: UUID,
    peticion: ActualizarUsuarioPeticion,
    caso: ActualizarUsuarioDep,
    ctx: ContextoActual,
) -> IdRespuesta:
    resultado = await caso.ejecutar(
        ComandoActualizarUsuario(
            usuario_id=usuario_id,
            quien=Rol(ctx.rol),
            quien_id=ctx.usuario_id,
            nombre=peticion.nombre,
            cedula=peticion.cedula,
            telefono=peticion.telefono,
            rol=peticion.rol,
            activo=peticion.activo,
        )
    )
    return IdRespuesta(id=resultado.id)


@router.post(
    "/usuarios/{usuario_id}/contrasena",
    response_model=IdRespuesta,
    # También cruza al proveedor, y repetirla dejaría a la persona con una
    # contraseña distinta de la que le acaban de dictar.
    dependencies=[ADMINISTRA, Idempotencia],
    summary="Fijarle una contraseña temporal nueva",
)
async def resetear_contrasena(
    usuario_id: UUID,
    peticion: ResetearContrasenaPeticion,
    caso: ResetearContrasenaDep,
    ctx: ContextoActual,
) -> IdRespuesta:
    """Para cuando alguien pierde su contraseña (§5.1).

    No sirve para la propia: esta ruta no pide la contraseña actual, y eso solo
    es aceptable operando sobre otra persona. La propia se cambia contra el
    proveedor con la sesión ya iniciada.
    """
    resultado = await caso.ejecutar(
        ComandoResetearContrasena(
            usuario_id=usuario_id,
            contrasena_temporal=peticion.contrasena_temporal,
            quien=Rol(ctx.rol),
            quien_id=ctx.usuario_id,
        )
    )
    return IdRespuesta(id=resultado.id)


# --- Alcance -------------------------------------------------------------


@router.get(
    "/usuarios/{usuario_id}/alcance",
    response_model=AlcanceRespuesta,
    summary="Qué gente, obras, clusters y proyectos tiene asignados",
)
async def consultar_alcance(usuario_id: UUID, sesion: SesionRLS) -> AlcanceRespuesta:
    """Los puentes del §4.

    Las cuatro listas se piden siempre, aunque cada rol solo pueda llenar una:
    la pantalla no sabe de antemano qué rol tiene la persona que abrió, y unas
    cuantas consultas sobre índices son más baratas que una ida y vuelta extra
    para preguntar primero el rol.

    `gente` sale de dos tablas distintas —`superintendente_usuario` si es SI,
    `supervisor_residente` si es supervisor— y se devuelven concatenadas
    porque nadie es las dos cosas: la que no aplica viene vacía.

    Lo que aquí se ve ya está acotado por RLS: un supervisor ve la cartera de
    sus residentes y la suya, no la de otra rama del organigrama.
    """
    repo = RepositorioAsignacionesSQL(sesion)
    return AlcanceRespuesta(
        usuario_id=usuario_id,
        gente=(
            await repo.gente_de_superintendente(usuario_id)
            + await repo.residentes_de(usuario_id)
        ),
        obras=await repo.obras_de(usuario_id),
        clusters=await repo.clusters_de(usuario_id),
        proyectos=await repo.proyectos_de(usuario_id),
    )


@router.post(
    "/usuarios/{usuario_id}/alcance",
    response_model=IdRespuesta,
    dependencies=[REPARTE],
    summary="Asignar o retirar gente, obras, clusters y proyectos",
)
async def asignar_alcance(
    usuario_id: UUID,
    peticion: AlcancePeticion,
    caso: AsignarAlcanceDep,
    ctx: ContextoActual,
) -> IdRespuesta:
    """Arma la cadena de mando (§5.1 "Asignaciones", §4).

    Quién puede repartir a quién lo decide `puede_asignar_alcance_de`, y lo
    vuelve a decir la base con las políticas de la 0042 — con un detalle que el
    dominio no alcanza a ver: que la persona esté bajo el mando de quien
    reparte y que la obra ya le sea visible. Esa segunda mitad es la que impide
    que un supervisor se amplíe el alcance solo, y por eso vive en Postgres y
    no aquí.

    REASIGNAR ES DOS PETICIONES, Y EN ESTE ORDEN

    Para pasar una obra del residente A al B: primero un POST con `obras=[o]`
    sobre B, después otro con `retirar=true` sobre A. Al revés, quien reasigna
    puede perder de vista la obra entre las dos peticiones —si A era su único
    vínculo con ella— y el alta se rechazaría.
    """
    resultado = await caso.ejecutar(
        ComandoAsignarAlcance(
            usuario_id=usuario_id,
            quien=Rol(ctx.rol),
            gente=tuple(peticion.gente),
            obras=tuple(peticion.obras),
            clusters=tuple(peticion.clusters),
            proyectos=tuple(peticion.proyectos),
            retirar=peticion.retirar,
        )
    )
    return IdRespuesta(id=resultado.id)
