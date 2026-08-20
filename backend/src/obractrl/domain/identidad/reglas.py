"""Reglas de identidad: quién puede dar de alta a quién, y con qué alcance.

Spec §4 (roles y alcance) · §5.1 ("el alta de usuarios la realiza Control de
obra") · §7.1 · §12.4 (RLS repite estas reglas como frontera).

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11).

**Estas reglas viven dos veces, a propósito.** Aquí dan un error legible y en
español antes de tocar la base; en `database/migrations/…_guardia_de_privilegios`
son un trigger que también cubre la ruta directa a Supabase (§10.7) y el
`UPDATE` a mano en el dashboard. La de la base es la que **garantiza**; esta es
la que **explica**. Si alguna vez discrepan, la que manda es la de la base — y
que discrepen es un bug de esta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from obractrl.domain.shared.diccionario import Rol

__all__ = [
    "ContrasenaTemporal",
    "ErrorDeIdentidad",
    "Usuario",
    "puede_asignar_alcance_de",
    "puede_dar_de_alta",
]


class ErrorDeIdentidad(ValueError):
    """Invariante rota en el alta o edición de un usuario (§4)."""


# Deliberadamente laxo: valida la *forma*, no la existencia. Un correo bien
# formado que no existe se descubre al primer intento de entrar; un correo mal
# formado se descubre ahora, que es más barato. La validación cara —¿llega?—
# la hace el proveedor de auth, no una expresión regular.
_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

LARGO_MINIMO_CONTRASENA = 12
"""Mínimo para la contraseña temporal.

Más largo que el default de Supabase (6) porque esta contraseña la elige una
persona *para otra*: no la va a recordar nadie —se comunica y se cambia—, así
que no hay razón para que sea corta, y sí para que aguante mientras viaja por
WhatsApp o por un papel.
"""


def _exigir_texto(valor: str, campo: str) -> str:
    limpio = " ".join(str(valor).split())
    if not limpio:
        raise ErrorDeIdentidad(f"El campo {campo!r} es obligatorio.")
    return limpio


def puede_dar_de_alta(quien: Rol, rol_nuevo: Rol) -> bool:
    """¿`quien` puede crear a alguien con `rol_nuevo`? (§4, §5.1)

    Control de obra da de alta al equipo —es lo que promete la pantalla de
    Login—, pero **no** puede fabricar un Super intendente: sería darse a sí
    mismo un cómplice con más privilegios de los que tiene. Ese rol solo lo
    otorga quien ya lo tiene.
    """
    if not quien.puede_configurar:
        return False
    if rol_nuevo is Rol.SUPER_INTENDENTE:
        return quien is Rol.SUPER_INTENDENTE
    return True


def puede_asignar_alcance_de(quien: Rol, rol_destino: Rol) -> bool:
    """¿`quien` puede tocar los puentes de alcance de un `rol_destino`? (§4)

    Espeja las políticas de la migración 0012, que son distintas para cada
    puente y no por capricho:

    · `supervisor_cluster` — Control de obra y Super intendente. Repartir
      clusters entre supervisores es trabajo de operación diaria.
    · `control_proyecto` — solo Super intendente. Ese puente decide **qué
      proyectos ve un Control de obra**, o sea el alcance de quien administra:
      si Control pudiera editarlo, se ampliaría su propio alcance.

    El residente no lleva puente: llega a su obra por `obra.residente_id`
    (§4), que se asigna desde la obra y no desde aquí.
    """
    if rol_destino is Rol.CONTROL_OBRA:
        return quien is Rol.SUPER_INTENDENTE
    if rol_destino is Rol.SUPERVISOR:
        return quien.puede_configurar
    return False


@dataclass(frozen=True, slots=True)
class ContrasenaTemporal:
    """La contraseña inicial que Control de obra le fija a alguien más (§5.1).

    Es un valor de dominio y no un `str` suelto porque tiene una regla propia y
    una consecuencia: **quien la recibe está obligado a cambiarla**. Esa
    obligación viaja como `debe_cambiar_password` en la fila del usuario, no
    como una convención que alguien tiene que recordar.

    Nunca se registra en el log ni vuelve en una respuesta después del alta:
    `__repr__` la oculta, porque un `repr()` accidental en una traza de Sentry
    la publicaría.
    """

    valor: str

    def __post_init__(self) -> None:
        if len(self.valor) < LARGO_MINIMO_CONTRASENA:
            raise ErrorDeIdentidad(
                f"La contraseña temporal debe tener al menos "
                f"{LARGO_MINIMO_CONTRASENA} caracteres."
            )
        if self.valor.strip() != self.valor:
            raise ErrorDeIdentidad(
                "La contraseña temporal no puede empezar ni terminar con "
                "espacios: se pierden al copiarla."
            )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "ContrasenaTemporal(<oculta>)"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return "<oculta>"


@dataclass(slots=True)
class Usuario:
    """Una persona con rol dentro de una organización (§7.1)."""

    nombre: str
    email: str
    rol: Rol
    cedula: str | None = None
    telefono: str | None = None
    activo: bool = True

    @classmethod
    def crear(
        cls,
        *,
        nombre: str,
        email: str,
        rol: Rol,
        creado_por: Rol,
        cedula: str | None = None,
        telefono: str | None = None,
    ) -> Usuario:
        """Alta de usuario (§11.2, Control de obra y Super intendente).

        `creado_por` es parte de la regla, no del contexto: quién da el alta
        determina qué roles puede otorgar, y eso es dominio (§4) — no una
        guarda del router que alguien pueda olvidar en la siguiente ruta.
        """
        if not puede_dar_de_alta(creado_por, rol):
            raise ErrorDeIdentidad(
                f"Un {creado_por.value} no puede dar de alta a un {rol.value}."
            )

        correo = _exigir_texto(email, "email").lower()
        if not _CORREO.match(correo):
            raise ErrorDeIdentidad(f"El correo no tiene una forma válida: {correo!r}.")

        return cls(
            nombre=_exigir_texto(nombre, "nombre"),
            email=correo,
            rol=rol,
            cedula=(cedula or "").strip() or None,
            telefono=(telefono or "").strip() or None,
        )

    def cambiar_rol(self, nuevo: Rol, *, por: Rol, es_uno_mismo: bool) -> None:
        """Cambio de rol de una persona ya dada de alta (§4).

        Las dos prohibiciones son la misma que aplica el trigger de la base:
        nadie se promueve a sí mismo, y el rol de Super intendente solo lo
        mueve —en cualquier dirección— quien ya lo tiene. Degradar al único
        Super intendente es la otra mitad del problema de promoverse.
        """
        if es_uno_mismo:
            raise ErrorDeIdentidad("Nadie cambia su propio rol.")
        if Rol.SUPER_INTENDENTE in (nuevo, self.rol) and por is not Rol.SUPER_INTENDENTE:
            raise ErrorDeIdentidad(
                "Solo un super intendente puede otorgar o retirar el rol de "
                "super intendente."
            )
        if not por.puede_configurar:
            raise ErrorDeIdentidad(f"Un {por.value} no puede cambiar roles.")
        self.rol = nuevo

    def desactivar(self, *, por: Rol, es_uno_mismo: bool) -> None:
        """Baja de un usuario (§7.1).

        Se desactiva, no se borra: sus capturas, cierres y estimaciones siguen
        apuntando a esta fila y el expediente técnico tiene que poder decir
        quién las hizo (§11.3).
        """
        if es_uno_mismo:
            raise ErrorDeIdentidad("Nadie se da de baja a sí mismo.")
        if not por.puede_configurar:
            raise ErrorDeIdentidad(f"Un {por.value} no puede dar de baja usuarios.")
        if self.rol is Rol.SUPER_INTENDENTE and por is not Rol.SUPER_INTENDENTE:
            raise ErrorDeIdentidad(
                "Solo un super intendente puede dar de baja a otro super intendente."
            )
        self.activo = False
