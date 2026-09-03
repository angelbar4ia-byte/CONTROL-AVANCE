"""Control de cambio: lo que mueve el costo final de una obra (§11.3, §6).

El jefe de obra lo unificó: *"pueden pedir más cantidad, dar de alta trabajo
fuera de catálogo, cambiar una actividad por otra, o pedir una que existe en el
catálogo y no estaba; todo esto al final se clasifica como control de cambio que
recae al costo de la obra final"*.

Cuatro puertas al mismo cuarto. Modelarlas como cuatro mecanismos separados
—que es como estaban— hace que nadie pueda contestar "¿cuánto se ha movido el
costo de esta obra?" sin sumar a mano de cuatro lados.

## El residente pide, Control autoriza

La **orden de cambio se captura al autorizar**, no al pedir. Antes el residente
la tecleaba él mismo al dar de alta un extra: eso funciona para trabajo que él
ve aparecer y afirma —está parado ahí—, pero una orden tecleada por quien pide
no autoriza nada.

## El umbral

`cant_programada ≤ cant_base × (1 + tolerancia/100)` es el §6 de siempre, ahora
con la tolerancia por obra. Pasarlo **no** es un error de captura: es la señal
de que hace falta un control de cambio, y la diferencia importa porque una la
corrige el residente solo y la otra necesita a Control.

Módulo puro (§12.11): sin BD, sin reloj.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from obractrl.domain.shared.diccionario import Rol

__all__ = [
    "ErrorDeControlDeCambio",
    "EstatusControlCambio",
    "LineaDeCambio",
    "SolicitudDeCambio",
    "TipoControlCambio",
    "excede_el_umbral",
    "puede_autorizar",
    "puede_solicitar",
    "techo_de",
]

_CERO = Decimal(0)


class TipoControlCambio(StrEnum):
    EXTRA_CATALOGO = "extra_catalogo"
    """Más cantidad de algo que ya está en la obra, agotado el umbral."""
    FUERA_CATALOGO = "fuera_catalogo"
    """Trabajo que no existe en el catálogo. El residente arma su precio."""
    SUSTITUCION = "sustitucion"
    """Cambiar una actividad por otra."""
    ALTA_CATALOGO = "alta_catalogo"
    """Una actividad del catálogo que no estaba en esta obra."""


class EstatusControlCambio(StrEnum):
    SOLICITADO = "solicitado"
    AUTORIZADO = "autorizado"
    RECHAZADO = "rechazado"


class ErrorDeControlDeCambio(ValueError):
    """Invariante rota en una solicitud o en su resolución."""

    def __init__(self, mensaje: str, campo: str) -> None:
        super().__init__(mensaje)
        self.campo = campo


def puede_solicitar(rol: Rol) -> bool:
    """Solo el residente (§4).

    Pedir un control de cambio es afirmar que en la obra hace falta algo que el
    proyecto no traía, y el único que puede afirmarlo es quien está ahí. Que
    después alguien lo autorice es lo que pone a Control a revisarlo.
    """
    return rol is Rol.RESIDENTE


def puede_autorizar(rol: Rol) -> bool:
    """Control de obra y el Super intendente (§4).

    No el residente, ni siquiera sobre su propia obra: autorizar lo que uno
    mismo pidió convierte el control en un trámite. Es la misma separación que
    el cierre de actividad, donde quien solicita tampoco autoriza.
    """
    return rol in (Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE)


def techo_de(
    *,
    cant_base: Decimal,
    tolerancia_pct: Decimal,
    cant_autorizada: Decimal | None = None,
) -> Decimal:
    """Hasta cuánto se puede programar esta actividad (§6).

    Manda `cant_autorizada` cuando existe: es la cantidad concreta que Control
    firmó, y una vez firmada el margen porcentual ya no decide.

    Espejo exacto de `ck_actividad_programada_vs_base` (migración 0049). Vive
    dos veces a propósito: aquí para dar un mensaje en español antes de tocar la
    base, y allá para que la ruta offline —que no pasa por el backend (§12.5)—
    tenga la misma frontera.
    """
    if cant_autorizada is not None:
        return cant_autorizada
    return cant_base * (1 + tolerancia_pct / 100)


def excede_el_umbral(
    *,
    cant_programada: Decimal,
    cant_base: Decimal,
    tolerancia_pct: Decimal,
    cant_autorizada: Decimal | None = None,
) -> bool:
    """¿Esta cantidad ya necesita autorización?

    Es una **pregunta**, no una validación: pasar el umbral no es un error de
    captura sino la señal de que hace falta un control de cambio. La diferencia
    importa porque un error lo corrige el residente solo y esto necesita a
    Control.
    """
    return cant_programada > techo_de(
        cant_base=cant_base,
        tolerancia_pct=tolerancia_pct,
        cant_autorizada=cant_autorizada,
    )


@dataclass(frozen=True, slots=True)
class LineaDeCambio:
    """Una actividad dentro de la solicitud.

    Varias por solicitud a propósito: el residente pide por sub-frente, y si se
    le agotó el cemento en tres actividades de albañilería manda una solicitud
    con tres renglones, no tres solicitudes que alguien tenga que relacionar.
    """

    cantidad: Decimal
    actividad_id: str | None = None
    """La actividad afectada. Nula en `fuera_catalogo` y `alta_catalogo`:
    todavía no existe y se crea al autorizar."""
    concepto_id: str | None = None
    descripcion: str | None = None
    precio_unitario: Decimal = _CERO
    sustituye_a: str | None = None
    """Solo en `sustitucion`: la actividad que se reemplaza."""


@dataclass(frozen=True, slots=True)
class SolicitudDeCambio:
    """Una solicitud ya validada, lista para guardarse."""

    obra_id: str
    tipo: TipoControlCambio
    motivo: str
    lineas: tuple[LineaDeCambio, ...]
    nivel_id: str | None = None
    etapa_id: str | None = None
    descuenta_ejecutado: bool = False
    """Solo en `sustitucion`. Lo ejecutado de la actividad reemplazada **se
    estima por defecto** —el trabajo se hizo y alguien lo pagó— y Control puede
    descontarlo si el caso lo pide. Se decide al autorizar, no al pedir."""

    @classmethod
    def crear(
        cls,
        *,
        obra_id: str,
        tipo: TipoControlCambio,
        motivo: str,
        lineas: tuple[LineaDeCambio, ...],
        rol: Rol,
        nivel_id: str | None = None,
        etapa_id: str | None = None,
    ) -> SolicitudDeCambio:
        if not puede_solicitar(rol):
            raise ErrorDeControlDeCambio(
                f"Un {rol.value} no solicita controles de cambio; lo hace el "
                f"residente de la obra (§4).",
                campo="rol",
            )

        texto = " ".join(str(motivo).split())
        if not texto:
            raise ErrorDeControlDeCambio(
                "Di por qué hace falta: quien autoriza no estuvo en la obra y "
                "el motivo es todo lo que va a tener para decidir.",
                campo="motivo",
            )

        if not lineas:
            raise ErrorDeControlDeCambio(
                "Una solicitud sin renglones no pide nada.", campo="lineas"
            )

        for linea in lineas:
            _validar_linea(linea, tipo)

        return cls(
            obra_id=obra_id,
            tipo=tipo,
            motivo=texto,
            lineas=lineas,
            nivel_id=nivel_id,
            etapa_id=etapa_id,
        )

    @property
    def importe(self) -> Decimal:
        """Lo que esta solicitud le mueve al costo de la obra.

        Es la cifra con la que Control decide, y por eso se calcula sobre la
        solicitud entera y no renglón por renglón: tres actividades de mil pesos
        se autorizan distinto que una de tres mil.
        """
        return sum(
            (linea.cantidad * linea.precio_unitario for linea in self.lineas), _CERO
        )


def _validar_linea(linea: LineaDeCambio, tipo: TipoControlCambio) -> None:
    if linea.cantidad <= 0:
        raise ErrorDeControlDeCambio(
            f"La cantidad debe ser mayor que cero: {linea.cantidad}.",
            campo="cantidad",
        )
    if linea.precio_unitario < 0:
        raise ErrorDeControlDeCambio(
            "El precio unitario no puede ser negativo.", campo="precio_unitario"
        )

    if tipo is TipoControlCambio.EXTRA_CATALOGO and linea.actividad_id is None:
        raise ErrorDeControlDeCambio(
            "Pedir más cantidad es sobre una actividad que ya existe: di cuál.",
            campo="actividad_id",
        )

    if tipo is TipoControlCambio.SUSTITUCION and linea.sustituye_a is None:
        raise ErrorDeControlDeCambio(
            "Una sustitución tiene que decir a qué actividad reemplaza: si no, "
            "es un alta y el costo se contaría dos veces.",
            campo="sustituye_a",
        )

    if tipo is TipoControlCambio.ALTA_CATALOGO and linea.concepto_id is None:
        raise ErrorDeControlDeCambio(
            "Traer una actividad del catálogo pide su concepto: de ahí sale su "
            "precio y su APU.",
            campo="concepto_id",
        )

    if tipo is TipoControlCambio.FUERA_CATALOGO:
        if not (linea.descripcion or "").strip():
            raise ErrorDeControlDeCambio(
                "Un trabajo fuera de catálogo necesita descripción: no hay "
                "concepto del cual tomarla.",
                campo="descripcion",
            )
        if linea.precio_unitario <= 0:
            raise ErrorDeControlDeCambio(
                "Un trabajo fuera de catálogo necesita su precio armado: sin "
                "él no se puede estimar y nadie lo cobra.",
                campo="precio_unitario",
            )
