"""Caso de uso: dar de alta al equipo y repartirle su alcance (§5.1).

Spec §4 (roles y alcance) · §5.1 ("el alta de usuarios la realiza Control de
obra") · §7.1 · §11.2 (Identidad y organización) · §12.11 (capa de aplicación).

Es lo que hoy no se puede hacer sin abrir `psql`, y por eso abre la Fase 7: la
pantalla de Login le promete al usuario que alguien lo dará de alta, y ese
alguien no tenía dónde hacerlo.

EL ALTA TOCA DOS SISTEMAS Y NO HAY TRANSACCIÓN QUE LOS ABARQUE

`auth.users` vive en Supabase; `usuario` vive en Postgres. El orden es
**primero la cuenta, después la fila**, y si la fila falla, la cuenta se borra.
El razonamiento completo está en el encabezado de
`application.puertos.auth`; en resumen: entre las dos fallas parciales
posibles se elige la que no miente. Una cuenta huérfana no puede ver nada
—su JWT no trae `org_id` ni `rol`, y RLS la deja fuera de todo—, mientras que
una fila de `usuario` sin cuenta aparece en la lista del equipo, recibe obras
asignadas y no puede entrar.

El `borrar` compensatorio puede fallar a su vez —la red no promete nada—. Si
falla, queda la cuenta huérfana y se registra; no se reintenta en bucle ni se
convierte el error original en otro distinto, porque lo que el usuario necesita
saber es que el alta no se hizo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from obractrl.application.puertos.auth import (
    CorreoYaRegistrado,
    ErrorDelProveedorDeAuth,
    ProveedorDeAuth,
)
from obractrl.application.puertos.repositorios import (
    RepositorioAsignaciones,
    RepositorioUsuarios,
    UnidadDeTrabajo,
)
from obractrl.domain.identidad.reglas import (
    ContrasenaTemporal,
    ErrorDeIdentidad,
    Usuario,
    puede_asignar_alcance_de,
)
from obractrl.domain.shared.diccionario import Rol

__all__ = [
    "ActualizarUsuario",
    "AsignarAlcance",
    "ComandoActualizarUsuario",
    "ComandoAsignarAlcance",
    "ComandoCrearUsuario",
    "ComandoResetearContrasena",
    "ContrasenaReseteada",
    "CorreoYaRegistrado",
    "CrearUsuario",
    "ErrorDeIdentidad",
    "ResetearContrasena",
    "UsuarioActualizado",
    "UsuarioCreado",
    "UsuarioNoEncontrado",
]

_log = logging.getLogger(__name__)


class UsuarioNoEncontrado(LookupError):
    """El usuario no existe o es de otra organización.

    Las dos cosas se ven igual y las dos son un 404: distinguirlas confirmaría
    la existencia de alguien que el que pregunta no tiene por qué ver (§12.4).
    """


@dataclass(frozen=True, slots=True)
class ComandoCrearUsuario:
    nombre: str
    email: str
    rol: Rol
    contrasena_temporal: str
    quien: Rol
    """Rol de quien está dando el alta. Es parte de la regla (§4), no del
    contexto: determina qué roles puede otorgar."""
    cedula: str | None = None
    telefono: str | None = None


@dataclass(frozen=True, slots=True)
class ComandoActualizarUsuario:
    usuario_id: UUID
    quien: Rol
    quien_id: UUID
    nombre: str | None = None
    cedula: str | None = None
    telefono: str | None = None
    rol: Rol | None = None
    activo: bool | None = None


@dataclass(frozen=True, slots=True)
class ComandoResetearContrasena:
    usuario_id: UUID
    contrasena_temporal: str
    quien: Rol
    quien_id: UUID


@dataclass(frozen=True, slots=True)
class ComandoAsignarAlcance:
    usuario_id: UUID
    quien: Rol
    clusters: tuple[UUID, ...] = ()
    proyectos: tuple[UUID, ...] = ()
    retirar: bool = False
    """`True` quita en vez de dar. Es un campo y no dos casos de uso porque la
    regla de quién puede tocar qué puente es idéntica en los dos sentidos."""


@dataclass(frozen=True, slots=True)
class UsuarioCreado:
    id: UUID
    usuario: Usuario


@dataclass(frozen=True, slots=True)
class UsuarioActualizado:
    id: UUID


@dataclass(frozen=True, slots=True)
class ContrasenaReseteada:
    id: UUID


class CrearUsuario:
    """`POST /usuarios` (Control de obra y Super intendente, §11.2)."""

    def __init__(
        self,
        *,
        usuarios: RepositorioUsuarios,
        auth: ProveedorDeAuth,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._usuarios = usuarios
        self._auth = auth
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCrearUsuario) -> UsuarioCreado:
        # El dominio primero: si el rol no se puede otorgar o el correo está
        # mal formado, no se crea nada en ninguno de los dos sistemas. Validar
        # después de llamar al proveedor dejaría cuentas que borrar por algo
        # que se sabía de antemano.
        usuario = Usuario.crear(
            nombre=cmd.nombre,
            email=cmd.email,
            rol=cmd.rol,
            creado_por=cmd.quien,
            cedula=cmd.cedula,
            telefono=cmd.telefono,
        )
        temporal = ContrasenaTemporal(cmd.contrasena_temporal)

        cuenta = await self._auth.crear_cuenta(
            email=usuario.email,
            contrasena=temporal.valor,
            nombre=usuario.nombre,
        )

        try:
            async with self._uow:
                usuario_id = await self._usuarios.crear(
                    {
                        "auth_user_id": cuenta.id,
                        "nombre": usuario.nombre,
                        "email": usuario.email,
                        "rol": usuario.rol.value,
                        "cedula": usuario.cedula,
                        "telefono": usuario.telefono,
                        # La eligió alguien más: cambiarla es obligatorio.
                        "debe_cambiar_password": True,
                    }
                )
                await self._uow.commit()
        except Exception:
            # Compensación: sin esto quedaría una cuenta que puede autenticarse
            # y no pertenece a ninguna organización.
            await self._deshacer_cuenta(cuenta.id)
            raise

        return UsuarioCreado(id=usuario_id, usuario=usuario)

    async def _deshacer_cuenta(self, auth_user_id: UUID) -> None:
        try:
            await self._auth.borrar_cuenta(auth_user_id=auth_user_id)
        except ErrorDelProveedorDeAuth as exc:
            # No se re-levanta: taparía la causa real del fallo, que es lo que
            # quien dio el alta necesita ver. Queda en el log, que es donde el
            # operador puede limpiar la cuenta huérfana.
            _log.error(
                "Quedó una cuenta de auth huérfana (%s) tras fallar el alta: %s",
                auth_user_id,
                exc,
            )


class ActualizarUsuario:
    """`PATCH /usuarios/{id}` (Control de obra y Super intendente, §11.2)."""

    def __init__(
        self, *, usuarios: RepositorioUsuarios, uow: UnidadDeTrabajo
    ) -> None:
        self._usuarios = usuarios
        self._uow = uow

    async def ejecutar(self, cmd: ComandoActualizarUsuario) -> UsuarioActualizado:
        actual = await self._usuarios.obtener(cmd.usuario_id)
        if actual is None:
            raise UsuarioNoEncontrado(f"No existe el usuario {cmd.usuario_id}.")

        # Se reconstruye la entidad desde la fila para que las transiciones las
        # decida el dominio y no un `if` del router. Es la misma forma que usa
        # `gestionar_incidencia`.
        usuario = Usuario(
            nombre=actual["nombre"],
            email=actual["email"],
            rol=Rol(actual["rol"]),
            cedula=actual.get("cedula"),
            telefono=actual.get("telefono"),
            activo=actual["estatus"] == "activo",
        )
        es_uno_mismo = cmd.usuario_id == cmd.quien_id

        if cmd.rol is not None and cmd.rol is not usuario.rol:
            usuario.cambiar_rol(cmd.rol, por=cmd.quien, es_uno_mismo=es_uno_mismo)

        if cmd.activo is False and usuario.activo:
            usuario.desactivar(por=cmd.quien, es_uno_mismo=es_uno_mismo)
        elif cmd.activo is True and not usuario.activo:
            if es_uno_mismo:
                raise ErrorDeIdentidad("Nadie se reactiva a sí mismo.")
            if not cmd.quien.puede_configurar:
                raise ErrorDeIdentidad(
                    f"Un {cmd.quien.value} no puede reactivar usuarios."
                )
            usuario.activo = True

        async with self._uow:
            await self._usuarios.actualizar(
                cmd.usuario_id,
                {
                    "nombre": cmd.nombre,
                    "cedula": cmd.cedula,
                    "telefono": cmd.telefono,
                    "rol": usuario.rol.value if cmd.rol is not None else None,
                    "estatus": (
                        None
                        if cmd.activo is None
                        else ("activo" if usuario.activo else "inactivo")
                    ),
                },
            )
            await self._uow.commit()

        return UsuarioActualizado(id=cmd.usuario_id)


class ResetearContrasena:
    """`POST /usuarios/{id}/contrasena` (Control de obra y SI, §5.1).

    Existe porque el camino de alta es con contraseña temporal: alguien tiene
    que poder volver a fijarla cuando la persona la pierde, y ese alguien no
    puede ser un `psql`.
    """

    def __init__(
        self,
        *,
        usuarios: RepositorioUsuarios,
        auth: ProveedorDeAuth,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._usuarios = usuarios
        self._auth = auth
        self._uow = uow

    async def ejecutar(self, cmd: ComandoResetearContrasena) -> ContrasenaReseteada:
        if not cmd.quien.puede_configurar:
            raise ErrorDeIdentidad(
                f"Un {cmd.quien.value} no puede resetear contraseñas."
            )
        if cmd.usuario_id == cmd.quien_id:
            # Cambiar la propia contraseña se hace contra el proveedor con la
            # sesión ya iniciada, no por esta ruta administrativa: aquí no se
            # pide la contraseña actual, y eso solo es aceptable para operar
            # sobre otra persona.
            raise ErrorDeIdentidad(
                "Tu propia contraseña se cambia desde tu perfil, no desde Equipo."
            )

        temporal = ContrasenaTemporal(cmd.contrasena_temporal)

        auth_user_id = await self._usuarios.obtener_auth_user_id(cmd.usuario_id)
        if auth_user_id is None:
            raise UsuarioNoEncontrado(
                f"El usuario {cmd.usuario_id} no existe, es de otra organización "
                f"o no tiene cuenta ligada."
            )

        await self._auth.fijar_contrasena(
            auth_user_id=auth_user_id, contrasena=temporal.valor
        )

        # El orden importa aquí también, y por la misma razón de siempre: si la
        # marca falla después de cambiar la contraseña, la persona entra con la
        # nueva sin que se le exija cambiarla — molesto. Al revés entraría con
        # la vieja y se le exigiría cambiar una contraseña que ya no sirve —
        # imposible de entender.
        async with self._uow:
            await self._usuarios.marcar_contrasena_temporal(
                cmd.usuario_id, temporal=True
            )
            await self._uow.commit()

        return ContrasenaReseteada(id=cmd.usuario_id)


class AsignarAlcance:
    """`POST /usuarios/{id}/alcance` (§5.1 "Asignaciones").

    Reparte clusters a un supervisor y proyectos a un Control de obra. Quién
    puede tocar cada puente lo dice `puede_asignar_alcance_de`, que espeja las
    políticas de la migración 0012 — y RLS lo vuelve a imponer, así que una
    guarda olvidada aquí sería un 500 feo, no un agujero.
    """

    def __init__(
        self,
        *,
        usuarios: RepositorioUsuarios,
        asignaciones: RepositorioAsignaciones,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._usuarios = usuarios
        self._asignaciones = asignaciones
        self._uow = uow

    async def ejecutar(self, cmd: ComandoAsignarAlcance) -> UsuarioActualizado:
        destino = await self._usuarios.obtener(cmd.usuario_id)
        if destino is None:
            raise UsuarioNoEncontrado(f"No existe el usuario {cmd.usuario_id}.")

        rol_destino = Rol(destino["rol"])
        if not puede_asignar_alcance_de(cmd.quien, rol_destino):
            raise ErrorDeIdentidad(
                f"Un {cmd.quien.value} no puede cambiar el alcance de un "
                f"{rol_destino.value}."
            )

        if cmd.clusters and rol_destino is not Rol.SUPERVISOR:
            raise ErrorDeIdentidad(
                "Los clusters se asignan a un supervisor; "
                f"{destino['nombre']} es {rol_destino.value}."
            )
        if cmd.proyectos and rol_destino is not Rol.CONTROL_OBRA:
            raise ErrorDeIdentidad(
                "Los proyectos se asignan a un control de obra; "
                f"{destino['nombre']} es {rol_destino.value}."
            )

        async with self._uow:
            for cluster_id in cmd.clusters:
                if cmd.retirar:
                    await self._asignaciones.retirar_cluster(
                        supervisor_id=cmd.usuario_id, cluster_id=cluster_id
                    )
                else:
                    await self._asignaciones.asignar_cluster(
                        supervisor_id=cmd.usuario_id, cluster_id=cluster_id
                    )
            for proyecto_id in cmd.proyectos:
                if cmd.retirar:
                    await self._asignaciones.retirar_proyecto(
                        usuario_id=cmd.usuario_id, proyecto_id=proyecto_id
                    )
                else:
                    await self._asignaciones.asignar_proyecto(
                        usuario_id=cmd.usuario_id, proyecto_id=proyecto_id
                    )
            await self._uow.commit()

        return UsuarioActualizado(id=cmd.usuario_id)
