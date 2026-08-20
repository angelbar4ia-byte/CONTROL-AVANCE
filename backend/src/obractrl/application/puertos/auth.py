"""Puerto del proveedor de autenticación.

Spec §12.4 (auth y JWT) · §5.1 (el alta la hace Control de obra) · §12.11
(inversión de dependencias).

**Por qué es un puerto y no una llamada suelta.** Crear la cuenta es un efecto
*fuera* de la transacción de Postgres: si el caso de uso llamara a Supabase
directamente, la capa de aplicación conocería `httpx`, la service key y el
formato de la Admin API — y el día que el proveedor cambie, el cambio se
esparce por los casos de uso. Con el puerto, el adaptador es un archivo.

EL PROBLEMA QUE ESTE PUERTO NO PUEDE ESCONDER

Un alta toca dos sistemas: `auth.users` en Supabase y `usuario` en Postgres. No
hay transacción que abarque los dos. El orden que elige `CrearUsuario` es
**primero la cuenta, después la fila**, y no es arbitrario:

· Si falla la fila después de crear la cuenta, queda una cuenta huérfana que
  puede autenticarse pero cuyo JWT no trae `org_id` ni `rol` — y sin esos
  claims **RLS no le deja ver absolutamente nada** (§12.4). Falla cerrado, y el
  caso de uso además la borra.
· Al revés, quedaría una fila de `usuario` sin `auth_user_id`: una persona que
  aparece en la lista del equipo, a la que se le asignan obras, y que no puede
  entrar. Falla *abierto* en la interfaz y en silencio.

Entre dos fallas parciales se elige la que no miente.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

__all__ = [
    "CorreoYaRegistrado",
    "CuentaDeAuth",
    "ErrorDelProveedorDeAuth",
    "ProveedorDeAuth",
    "ProveedorDeAuthNoConfigurado",
]


class ErrorDelProveedorDeAuth(RuntimeError):
    """El proveedor rechazó la operación o no respondió.

    Fallo **de infraestructura**: la petición era válida. El borde lo traduce a
    503, mismo criterio que `ColaNoDisponible` y `AlmacenamientoNoConfigurado`.
    """


class ProveedorDeAuthNoConfigurado(ErrorDelProveedorDeAuth):
    """Faltan `SUPABASE_URL` o `SUPABASE_SERVICE_KEY` en este entorno (§12.8).

    Se distingue del fallo de red porque la acción del operador es otra: aquí
    hay que poner una variable, no revisar un servicio.
    """


class CorreoYaRegistrado(ValueError):
    """Ese correo ya tiene cuenta en el proveedor.

    **No** es un error de infraestructura: es un conflicto legible que el borde
    convierte en 409. Va aparte porque es el único fallo del alta que la
    persona que la está haciendo puede resolver sola.
    """


@dataclass(frozen=True, slots=True)
class CuentaDeAuth:
    """Lo único que ObraCtrl guarda del proveedor: el id de la cuenta.

    Va a `usuario.auth_user_id`, que es la llave con la que el auth hook
    (migración 0015) encuentra la fila y copia `org_id`, `rol` y `usuario_id`
    al JWT.
    """

    id: UUID
    email: str


@runtime_checkable
class ProveedorDeAuth(Protocol):
    async def crear_cuenta(
        self, *, email: str, contrasena: str, nombre: str
    ) -> CuentaDeAuth:
        """Crea la cuenta con una contraseña ya elegida y la deja usable.

        El correo queda confirmado sin que la persona haga clic en nada: no hay
        nada que confirmar cuando la contraseña la fijó alguien más. Lo que sí
        hay es la obligación de cambiarla, y esa vive en
        `usuario.debe_cambiar_password`, no aquí.
        """
        ...

    async def fijar_contrasena(self, *, auth_user_id: UUID, contrasena: str) -> None:
        """Reemplaza la contraseña de una cuenta (reseteo desde el equipo)."""
        ...

    async def borrar_cuenta(self, *, auth_user_id: UUID) -> None:
        """Borra la cuenta. Solo para deshacer un alta a medio camino.

        Dar de baja a una persona **no** pasa por aquí: eso es
        `usuario.estatus = 'inactivo'`, porque sus capturas y cierres siguen
        apuntando a su fila y el expediente tiene que poder decir quién las
        hizo (§11.3).
        """
        ...
