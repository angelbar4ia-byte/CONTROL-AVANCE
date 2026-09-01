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
    puede_registrar_proyectos_de_control,
    roles_que_cuelgan_de,
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
    """Reparto de alcance sobre UNA persona (§5.1 "Asignaciones").

    `usuario_id` es siempre **el jefe o el dueño de la cartera**, nunca el
    subordinado: se le dan cosas *a él*. Qué lista aplica lo decide su rol, y
    por eso vienen todas y no un campo polimórfico —la pantalla manda la que
    corresponde y el caso de uso rechaza el resto con un error legible en vez
    de adivinar.
    """

    usuario_id: UUID
    quien: Rol
    gente: tuple[UUID, ...] = ()
    """Personas que cuelgan de `usuario_id`.

    Si es Super intendente, supervisores y/o residentes
    (`superintendente_usuario`); si es supervisor, residentes
    (`supervisor_residente`). Es un solo campo para los dos puentes porque
    desde la pantalla es la misma acción —"esta es tu gente"— y el rol del
    destino ya dice a qué tabla va.
    """
    obras: tuple[UUID, ...] = ()
    """Obras de un residente (`residente_obra`). Es la fuente de verdad del
    alcance de obra desde la 0042."""
    clusters: tuple[UUID, ...] = ()
    """Manzanas que recorre un supervisor (`supervisor_cluster`). DATO
    TERRITORIAL: desde la 0042 ya no le abre ninguna obra."""
    proyectos: tuple[UUID, ...] = ()
    """Proyectos de un Control de obra (`control_proyecto`). INERTE desde la
    0042: Control ve toda la organización."""
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

    Arma la cadena de mando del §4: le cuelga gente a un Super intendente o a
    un supervisor, obras a un residente, y de paso mantiene los dos registros
    que ya no gobiernan alcance (clusters y proyectos).

    TRES CAPAS DE VALIDACIÓN, Y NINGUNA SOBRA

    1. **Forma** — que la lista corresponda al rol del destino. Darle obras a
       un supervisor no es un permiso denegado sino un sinsentido, y merece un
       error que lo diga.
    2. **Organigrama** — que el rol de cada asignado quepa debajo del destino
       (`roles_que_cuelgan_de`). Esto la base NO lo comprueba: sus llaves
       foráneas apuntan a `usuario` sin mirar el rol. Es la única capa que
       impide colgar un supervisor de otro supervisor.
    3. **Permiso** — quién puede repartir qué (`puede_asignar_alcance_de`).
       Aquí sí hay red debajo: las políticas de la 0042 lo vuelven a imponer, y
       además con un detalle que el dominio no puede ver —si la persona está
       en el alcance de quien reparte, y si la obra ya le era visible—. Una
       guarda olvidada en esta capa sería un 500 feo, no un agujero.

    EL ORDEN DE LAS OBRAS NO ES CASUAL

    Al reasignar, la pantalla manda primero el alta al residente destino y
    después la baja del origen. Si se hiciera al revés, un supervisor perdería
    la visibilidad de la obra en cuanto soltara al único residente que se la
    daba, y la política `residente_obra_insert` —que exige `obra_visible`—
    rechazaría el alta. Por eso aquí las altas y las bajas nunca se mezclan en
    una sola llamada: `retirar` es un booleano de toda la petición.
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
        self._exigir_forma(cmd, destino, rol_destino)

        if cmd.gente:
            await self._exigir_organigrama(cmd, destino, rol_destino)

        # `control_proyecto` se valida aparte porque su permiso ya no sale de
        # la jerarquía: quedó congelado en el de la 0012 (ver
        # `puede_registrar_proyectos_de_control`).
        if (cmd.gente or cmd.obras or cmd.clusters) and not puede_asignar_alcance_de(
            cmd.quien, rol_destino
        ):
            raise ErrorDeIdentidad(
                f"Un {cmd.quien.value} no puede cambiar el alcance de un "
                f"{rol_destino.value}."
            )
        if cmd.proyectos and not puede_registrar_proyectos_de_control(cmd.quien):
            raise ErrorDeIdentidad(
                f"Un {cmd.quien.value} no puede cambiar el alcance de un "
                f"{rol_destino.value}."
            )

        async with self._uow:
            for persona_id in cmd.gente:
                await self._mover_persona(cmd, rol_destino, persona_id)
            for obra_id in cmd.obras:
                if cmd.retirar:
                    await self._asignaciones.retirar_obra(
                        residente_id=cmd.usuario_id, obra_id=obra_id
                    )
                else:
                    await self._asignaciones.asignar_obra(
                        residente_id=cmd.usuario_id, obra_id=obra_id
                    )
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

    # --- Capa 1: la lista corresponde al rol del destino -----------------

    @staticmethod
    def _exigir_forma(
        cmd: ComandoAsignarAlcance, destino: dict, rol_destino: Rol
    ) -> None:
        quien_recibe = f"{destino['nombre']} es {rol_destino.value}"
        if cmd.gente and not roles_que_cuelgan_de(rol_destino):
            raise ErrorDeIdentidad(
                f"De un {rol_destino.value} no cuelga gente en el organigrama; "
                f"{quien_recibe}."
            )
        if cmd.obras and rol_destino is not Rol.RESIDENTE:
            raise ErrorDeIdentidad(
                f"Las obras se asignan a un residente; {quien_recibe}."
            )
        if cmd.clusters and rol_destino is not Rol.SUPERVISOR:
            raise ErrorDeIdentidad(
                f"Los clusters se asignan a un supervisor; {quien_recibe}."
            )
        if cmd.proyectos and rol_destino is not Rol.CONTROL_OBRA:
            raise ErrorDeIdentidad(
                f"Los proyectos se asignan a un control de obra; {quien_recibe}."
            )

    # --- Capa 2: el rol del asignado cabe debajo del destino -------------

    async def _exigir_organigrama(
        self, cmd: ComandoAsignarAlcance, destino: dict, rol_destino: Rol
    ) -> None:
        admitidos = roles_que_cuelgan_de(rol_destino)
        for persona_id in cmd.gente:
            persona = await self._usuarios.obtener(persona_id)
            if persona is None:
                # Mismo criterio que el resto del módulo: "no existe" y "es de
                # otra organización" se ven igual y las dos son un 404.
                raise UsuarioNoEncontrado(f"No existe el usuario {persona_id}.")
            rol_persona = Rol(persona["rol"])
            if rol_persona not in admitidos:
                raise ErrorDeIdentidad(
                    f"Un {rol_persona.value} no cuelga de un {rol_destino.value}: "
                    f"{persona['nombre']} no puede quedar bajo {destino['nombre']}."
                )

    async def _mover_persona(
        self, cmd: ComandoAsignarAlcance, rol_destino: Rol, persona_id: UUID
    ) -> None:
        """A qué puente va, según de quién cuelgue la persona."""
        if rol_destino is Rol.SUPER_INTENDENTE:
            if cmd.retirar:
                await self._asignaciones.retirar_persona_de_superintendente(
                    superintendente_id=cmd.usuario_id, usuario_id=persona_id
                )
            else:
                await self._asignaciones.asignar_persona_a_superintendente(
                    superintendente_id=cmd.usuario_id, usuario_id=persona_id
                )
            return

        if cmd.retirar:
            await self._asignaciones.retirar_residente(
                supervisor_id=cmd.usuario_id, residente_id=persona_id
            )
        else:
            await self._asignaciones.asignar_residente(
                supervisor_id=cmd.usuario_id, residente_id=persona_id
            )
