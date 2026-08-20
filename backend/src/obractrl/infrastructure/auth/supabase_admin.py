"""Admin API de Supabase: crear y administrar cuentas (§12.4).

Implementa `application.puertos.auth.ProveedorDeAuth`. Por HTTP con `httpx`
—ya es dependencia— en vez de sumar `supabase-py`: son tres endpoints y el SDK
arrastra el cliente de PostgREST y el de Storage, que aquí no se usan y sí
tendrían que actualizarse.

LA SERVICE KEY

Es la llave que **salta RLS por completo**: quien la tiene lee y escribe
cualquier fila de cualquier organización. Por eso:

· Vive solo en el backend (§10.7). El front usa la *anon key* y depende de RLS.
· Solo la usa este archivo, y solo para `auth.users` — nunca para consultar
  tablas de negocio, que es justo la tentación que la vuelve peligrosa: una
  consulta con service key es una consulta sin aislamiento.
· No sale en ningún log ni mensaje de error. Lo que se registra es el código
  HTTP y el correo, que es el rastro que el operador necesita.

Sin `SUPABASE_SERVICE_KEY` el adaptador levanta `ProveedorDeAuthNoConfigurado`
y el borde responde 503: el alta no se puede hacer en ese entorno, y el resto
del sistema sigue funcionando (§12.8).
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx

from obractrl.application.puertos.auth import (
    CorreoYaRegistrado,
    CuentaDeAuth,
    ErrorDelProveedorDeAuth,
    ProveedorDeAuthNoConfigurado,
)
from obractrl.infrastructure.config import Config, obtener_config

__all__ = ["AdminDeSupabase"]

_log = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 10.0
"""Corre dentro de una petición HTTP del usuario: no puede colgarla."""


class AdminDeSupabase:
    """Adaptador de la Admin API (§12.4)."""

    def __init__(
        self, cfg: Config | None = None, cliente: httpx.AsyncClient | None = None
    ) -> None:
        self._cfg = cfg or obtener_config()
        # Inyectable para probar contra un transporte falso, igual que
        # `ClienteResend`. No se prueba contra Supabase real: una prueba que
        # crea cuentas de verdad deja basura en un proyecto compartido.
        self._cliente = cliente

    # --- Puerto ---------------------------------------------------------

    async def crear_cuenta(
        self, *, email: str, contrasena: str, nombre: str
    ) -> CuentaDeAuth:
        datos = await self._peticion(
            "POST",
            "/auth/v1/admin/users",
            json={
                "email": email,
                "password": contrasena,
                # No hay nada que confirmar: la contraseña la fijó Control de
                # obra, no la persona. Sin esto la cuenta nace pendiente y el
                # primer login falla con "Email not confirmed", que no dice
                # nada de lo que en realidad pasó.
                "email_confirm": True,
                # El nombre viaja al metadata para que el proveedor tenga algo
                # legible en su propio panel. La fuente de verdad del perfil
                # sigue siendo la tabla `usuario` (§7.1).
                "user_metadata": {"nombre": nombre},
            },
            email=email,
        )
        identificador = datos.get("id")
        if not identificador:
            raise ErrorDelProveedorDeAuth(
                "El proveedor creó la cuenta pero no devolvió su id."
            )
        return CuentaDeAuth(id=UUID(str(identificador)), email=email)

    async def fijar_contrasena(self, *, auth_user_id: UUID, contrasena: str) -> None:
        await self._peticion(
            "PUT",
            f"/auth/v1/admin/users/{auth_user_id}",
            json={"password": contrasena},
        )

    async def borrar_cuenta(self, *, auth_user_id: UUID) -> None:
        await self._peticion("DELETE", f"/auth/v1/admin/users/{auth_user_id}")

    # --- Plomería -------------------------------------------------------

    def _base(self) -> tuple[str, str]:
        faltantes = [
            nombre
            for nombre, valor in (
                ("SUPABASE_URL", self._cfg.supabase_url),
                ("SUPABASE_SERVICE_KEY", self._cfg.supabase_service_key),
            )
            if not valor
        ]
        if faltantes:
            # Se nombran las variables, nunca su valor: quien opera el
            # despliegue necesita saber cuál poner, y el nombre no es secreto.
            raise ProveedorDeAuthNoConfigurado(
                "El alta de usuarios no está configurada en este entorno; "
                f"faltan: {', '.join(faltantes)} (§12.8)."
            )
        return self._cfg.supabase_url.rstrip("/"), self._cfg.supabase_service_key

    async def _peticion(
        self,
        metodo: str,
        ruta: str,
        *,
        json: dict[str, object] | None = None,
        email: str | None = None,
    ) -> dict[str, object]:
        base, service_key = self._base()
        cabeceras = {
            # La Admin API pide la llave en las dos cabeceras: `apikey` la usa
            # el gateway para enrutar y `Authorization` la usa GoTrue para
            # autorizar. Con una sola responde 401 sin explicar cuál falta.
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        }

        try:
            if self._cliente is not None:
                respuesta = await self._cliente.request(
                    metodo, f"{base}{ruta}", json=json, headers=cabeceras
                )
            else:
                async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as cliente:
                    respuesta = await cliente.request(
                        metodo, f"{base}{ruta}", json=json, headers=cabeceras
                    )
        except httpx.HTTPError as exc:
            _log.warning(
                "El proveedor de auth no respondió (%s) en %s.",
                type(exc).__name__,
                ruta,
            )
            raise ErrorDelProveedorDeAuth(
                f"El proveedor de autenticación no respondió "
                f"({type(exc).__name__}); reintenta en un momento."
            ) from exc

        if respuesta.status_code in (409, 422) and _es_correo_repetido(respuesta.text):
            # GoTrue devuelve 422 con `email_exists` cuando el correo ya tiene
            # cuenta. Es el único fallo del alta que la persona que la hace
            # puede resolver sola, así que se distingue: el borde lo vuelve un
            # 409 legible y no un 503 de "algo pasó".
            raise CorreoYaRegistrado(
                f"Ya existe una cuenta con el correo {email}."
                if email
                else "Ya existe una cuenta con ese correo."
            )

        if respuesta.status_code >= 400:
            # El cuerpo del error describe la petición rechazada y **no** trae
            # la llave, pero sí puede traer el correo: al log va el código y la
            # ruta; el cuerpo solo en debug.
            _log.warning(
                "El proveedor de auth respondió %s en %s.",
                respuesta.status_code,
                ruta,
            )
            _log.debug("Cuerpo del rechazo: %s", respuesta.text)
            raise ErrorDelProveedorDeAuth(
                f"El proveedor de autenticación rechazó la operación "
                f"(HTTP {respuesta.status_code})."
            )

        if not respuesta.content:
            return {}
        cuerpo = respuesta.json()
        return cuerpo if isinstance(cuerpo, dict) else {}


def _es_correo_repetido(cuerpo: str) -> bool:
    """¿El rechazo fue porque el correo ya existe?

    GoTrue ha usado varios textos para lo mismo según la versión
    (`email_exists`, `User already registered`, `duplicate key`), así que se
    reconocen todos: acertar aquí es la diferencia entre un 409 que dice qué
    pasó y un 503 que no.
    """
    bajo = cuerpo.lower()
    return any(
        marca in bajo
        for marca in ("email_exists", "already registered", "already been registered")
    )
