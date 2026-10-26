"""Repositorio de usuarios: identidad y equipo (§7.1, §5.1).

Spec §12.11 (adaptador de persistencia) · §7.1 · §12.4 (RLS) · §11.1
(comunicación entre contextos solo por fachadas).

Nació para que Notificaciones supiera a qué correo escribirle sin consultar
`usuario` desde su propio repositorio (§11.1), y con la pantalla de Equipo
(§5.1) creció al alta y la edición. La política `usuario_select`
(`database/migrations/20260814000012_rls_policies.sql`) da lectura a cualquier
usuario **de la organización del token**, así que el alcance no se filtra a
mano aquí: lo impone la base, y un usuario de otra organización simplemente no
aparece.

**Lo que este repositorio no decide.** Qué rol puede otorgar quién, y que nadie
se promueva a sí mismo, son reglas de `domain.identidad.reglas` y del trigger
de la migración 0025. Aquí solo se escribe: si la escritura viola una de esas
reglas, la base la rechaza con `insufficient_privilege` y el borde la traduce.
Duplicar la comprobación aquí sería una tercera copia que se desincroniza.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.application.puertos.repositorios import RegistroNoEncontrado

__all__ = ["RepositorioUsuariosSQL", "UsuarioNoModificado"]

_COLUMNAS = """
    id, nombre, email, rol, cedula, telefono, estatus,
    auth_user_id is not null as puede_entrar, debe_cambiar_password
"""


class UsuarioNoModificado(RegistroNoEncontrado):
    """El `UPDATE` acotado no afectó ninguna fila (§12.4).

    O el usuario ya no existe, o es de otra organización. Las dos se ven igual
    desde aquí, y las dos son un 404.
    """


class RepositorioUsuariosSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def correos_de(self, usuario_ids: list[UUID]) -> list[dict[str, Any]]:
        """`{id, nombre, email}` de los usuarios visibles de la lista.

        Se resuelve en **una** consulta con `= any(...)` —como
        `obras_sql.precios_vigentes`— y no en un `obtener()` por usuario: los
        destinatarios de un aviso son tres o cuatro, pero un N+1 aquí sería
        N+1 en cada validación de estimación.
        """
        if not usuario_ids:
            return []

        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, nombre, email
                    from usuario
                    where id = any(cast(:ids as uuid[]))
                      and estatus = 'activo'
                    order by nombre
                    """
                ),
                {"ids": [str(uid) for uid in usuario_ids]},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def de_la_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select u.id, u.nombre, u.email, u.rol::text as rol
                      from usuario u
                     where u.estatus = 'activo'
                       and (
                            u.rol = 'control_obra'
                         or (u.rol = 'residente' and exists (
                                select 1 from residente_obra ro
                                 where ro.obra_id = :obra_id and ro.residente_id = u.id))
                         or (u.rol = 'supervisor' and exists (
                                select 1
                                  from supervisor_residente sr
                                  join residente_obra ro
                                    on ro.residente_id = sr.residente_id
                                 where sr.supervisor_id = u.id and ro.obra_id = :obra_id))
                       )
                     order by u.nombre
                    """
                ),
                {"obra_id": str(obra_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def tokens_push_de(self, usuario_ids: list[UUID]) -> list[str]:
        """Tokens de Expo Push activos (§12.2, migración 0028).

        Pasa por `app.tokens_push_de`, que es `security definer`, y no por un
        `select` a `dispositivo_push`: la política `dispositivo_push_propio`
        solo deja ver los dispositivos **propios**, así que una consulta
        directa devolvería vacío justo cuando hay que avisarle a alguien más.
        La función es la única puerta a los tokens ajenos y filtra por
        organización con el mismo `app.current_org_id()` de RLS.
        """
        if not usuario_ids:
            return []

        filas = (
            await self._sesion.execute(
                text("select token from app.tokens_push_de(cast(:ids as uuid[]))"),
                {"ids": [str(uid) for uid in usuario_ids]},
            )
        ).all()
        return [str(fila.token) for fila in filas]

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Alta de usuario (§11.2, roles C y SI).

        El uuid se genera en Python, como en `proyectos_sql`, pero por otra
        razón: aquí `usuario_select` no consulta la propia tabla, así que un
        `RETURNING` funcionaría. Se genera antes porque **el caso de uso
        necesita el id para poder deshacer**: si la cuenta del proveedor de
        auth ya se creó y esta fila falla, hay que saber qué se estaba
        insertando para no dejar el alta a medias.
        """
        usuario_id = uuid4()
        await self._sesion.execute(
            text(
                """
                insert into usuario
                    (id, org_id, auth_user_id, nombre, email, rol, cedula,
                     telefono, debe_cambiar_password)
                values
                    (:id, cast(current_setting('app.org_id') as uuid),
                     cast(:auth_user_id as uuid), :nombre, :email,
                     cast(:rol as rol_usuario), :cedula, :telefono,
                     :debe_cambiar_password)
                """
            ),
            {
                "id": str(usuario_id),
                "auth_user_id": (
                    str(datos["auth_user_id"]) if datos.get("auth_user_id") else None
                ),
                "nombre": datos["nombre"],
                "email": datos["email"],
                "rol": datos["rol"],
                "cedula": datos.get("cedula"),
                "telefono": datos.get("telefono"),
                "debe_cambiar_password": datos.get("debe_cambiar_password", False),
            },
        )
        return usuario_id

    async def obtener(self, usuario_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from usuario where id = :id"),
                {"id": str(usuario_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def obtener_auth_user_id(self, usuario_id: UUID) -> UUID | None:
        """La cuenta ligada, para resetear su contraseña.

        Va aparte de `obtener` a propósito: `auth_user_id` es la llave con la
        que se opera sobre el proveedor de auth, y no tiene por qué viajar en
        cada listado del equipo ni salir en una respuesta HTTP.
        """
        fila = (
            await self._sesion.execute(
                text("select auth_user_id from usuario where id = :id"),
                {"id": str(usuario_id)},
            )
        ).first()
        return fila.auth_user_id if fila is not None else None

    async def listar(self, *, rol: str | None = None) -> list[dict[str, Any]]:
        """El equipo de la organización (§5.1).

        Incluye a los inactivos: dar de baja no borra, y la pantalla necesita
        poder mostrarlos —y reactivarlos— en vez de que desaparezcan sin que
        nadie entienda a dónde se fueron.
        """
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                      from usuario
                     where (cast(:rol as text) is null
                            or rol::text = cast(:rol as text))
                     order by estatus, nombre
                    """
                ),
                {"rol": rol},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def actualizar(self, usuario_id: UUID, cambios: dict[str, Any]) -> None:
        """Edición de perfil, rol o estatus (§11.2).

        `coalesce(:campo, columna)` deja pasar un `None` como "no lo toques".
        No sirve para borrar un teléfono —para eso el dominio manda cadena
        vacía— y a cambio evita que editar el rol borre la cédula por omisión.
        """
        resultado = await self._sesion.execute(
            text(
                """
                update usuario
                   set nombre   = coalesce(:nombre, nombre),
                       cedula   = coalesce(:cedula, cedula),
                       telefono = coalesce(:telefono, telefono),
                       rol      = coalesce(cast(:rol as rol_usuario), rol),
                       estatus  = coalesce(cast(:estatus as estatus_registro), estatus)
                 where id = :id
                """
            ),
            {
                "id": str(usuario_id),
                "nombre": cambios.get("nombre"),
                "cedula": cambios.get("cedula"),
                "telefono": cambios.get("telefono"),
                "rol": cambios.get("rol"),
                "estatus": cambios.get("estatus"),
            },
        )
        if resultado.rowcount == 0:
            raise UsuarioNoModificado(
                f"No se actualizó el usuario {usuario_id}: ya no existe o es de "
                f"otra organización."
            )

    async def marcar_contrasena_temporal(
        self, usuario_id: UUID, *, temporal: bool
    ) -> None:
        """Enciende o apaga la obligación de cambiar la contraseña (§5.1).

        La apaga el propio usuario al cambiarla; la enciende quien se la
        resetea desde Equipo.
        """
        resultado = await self._sesion.execute(
            text(
                """
                update usuario
                   set debe_cambiar_password = :temporal
                 where id = :id
                """
            ),
            {"id": str(usuario_id), "temporal": temporal},
        )
        if resultado.rowcount == 0:
            raise UsuarioNoModificado(
                f"No se actualizó el usuario {usuario_id}: ya no existe o es de "
                f"otra organización."
            )

    async def borrar(self, usuario_id: UUID) -> None:
        """Borra la fila. **Solo** para deshacer un alta a medio camino.

        Dar de baja a alguien es `estatus = 'inactivo'`: sus capturas y cierres
        siguen apuntando a esta fila y el expediente tiene que poder decir quién
        las hizo (§11.3). Este método existe únicamente para que un alta que
        falló después del `insert` no deje a nadie a medias.
        """
        await self._sesion.execute(
            text("delete from usuario where id = :id"), {"id": str(usuario_id)}
        )
