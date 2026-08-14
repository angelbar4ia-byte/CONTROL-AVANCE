"""Value objects del dominio.

Spec §11.1 (value objects) · §3.5 (moneda, IVA, unidades) · §6 (avance).

Cada uno encapsula sus invariantes: si existe la instancia, es válida.
Todos son inmutables y no dependen de nada externo.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

__all__ = ["MONEDA", "Avance", "Cantidad", "Dinero", "PrecioUnitario"]

MONEDA = "MXN"
"""Moneda única del sistema (§3.5)."""

_CENTAVO = Decimal("0.01")
_SEIS_DEC = Decimal("0.000001")


def _a_decimal(valor: Decimal | int | str) -> Decimal:
    """Convierte a Decimal sin pasar por float, que introduce ruido binario."""
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, float):  # pragma: no cover - defensivo
        raise TypeError(
            "No se aceptan float en importes ni cantidades: usa Decimal o str "
            "para no perder precisión (§3.5, importes en DECIMAL)."
        )
    return Decimal(str(valor))


@dataclass(frozen=True, slots=True)
class Dinero:
    """Importe en MXN, redondeado a centavos (§3.5).

    >>> Dinero("1250.5") + Dinero("0.005")
    Dinero(monto=Decimal('1250.51'))
    """

    monto: Decimal

    def __init__(self, monto: Decimal | int | str = 0) -> None:
        object.__setattr__(
            self, "monto", _a_decimal(monto).quantize(_CENTAVO, rounding=ROUND_HALF_UP)
        )

    def __add__(self, otro: Dinero) -> Dinero:
        return Dinero(self.monto + otro.monto)

    def __sub__(self, otro: Dinero) -> Dinero:
        return Dinero(self.monto - otro.monto)

    def __mul__(self, factor: Decimal | int | str) -> Dinero:
        return Dinero(self.monto * _a_decimal(factor))

    def __neg__(self) -> Dinero:
        return Dinero(-self.monto)

    def __lt__(self, otro: Dinero) -> bool:
        return self.monto < otro.monto

    @property
    def es_cero(self) -> bool:
        return self.monto == 0

    def con_iva(self, tasa: Decimal) -> Dinero:
        """Aplica IVA. La tasa es configurable; nunca se clava (§8.7)."""
        return Dinero(self.monto * (Decimal(1) + _a_decimal(tasa)))

    def formatear(self) -> str:
        """Formato es-MX para reportes (§12.10)."""
        return f"${self.monto:,.2f}"


@dataclass(frozen=True, slots=True)
class Cantidad:
    """Cantidad con unidad. Impide sumar peras con manzanas (§3.5)."""

    valor: Decimal
    unidad: str

    def __init__(self, valor: Decimal | int | str, unidad: str) -> None:
        v = _a_decimal(valor).quantize(_SEIS_DEC, rounding=ROUND_HALF_UP)
        object.__setattr__(self, "valor", v)
        object.__setattr__(self, "unidad", unidad.strip().lower())

    def _exigir_misma_unidad(self, otro: Cantidad) -> None:
        if self.unidad != otro.unidad:
            raise ValueError(
                f"No se pueden operar cantidades de distinta unidad: "
                f"{self.unidad!r} y {otro.unidad!r}. Homologa la unidad con su "
                f"factor de conversión antes de operar (§10.3)."
            )

    def __add__(self, otro: Cantidad) -> Cantidad:
        self._exigir_misma_unidad(otro)
        return Cantidad(self.valor + otro.valor, self.unidad)

    def __sub__(self, otro: Cantidad) -> Cantidad:
        self._exigir_misma_unidad(otro)
        return Cantidad(self.valor - otro.valor, self.unidad)

    def convertir(self, unidad_destino: str, factor: Decimal | int | str) -> Cantidad:
        """Convierte aplicando el factor definido al homologar (§10.3)."""
        return Cantidad(self.valor * _a_decimal(factor), unidad_destino)

    def importe(self, precio: Dinero) -> Dinero:
        return precio * self.valor


@dataclass(frozen=True, slots=True)
class Avance:
    """Porcentaje de avance, acotado a 0–100 (§6)."""

    pct: Decimal

    def __init__(self, pct: Decimal | int | str = 0) -> None:
        v = _a_decimal(pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if v < 0:
            raise ValueError(f"El avance no puede ser negativo: {v}")
        if v > 100:
            raise ValueError(f"El avance no puede exceder 100%: {v}")
        object.__setattr__(self, "pct", v)

    @classmethod
    def de_cantidades(
        cls, ejecutada: Decimal | int | str, base: Decimal | int | str
    ) -> Avance:
        """``avance_pct = cant_ejecutada / cant_base × 100`` (§6).

        Con base cero el avance es cero: no hay nada contra qué medir.
        """
        base_d = _a_decimal(base)
        if base_d <= 0:
            return cls(0)
        pct = (_a_decimal(ejecutada) / base_d) * Decimal(100)
        return cls(min(pct, Decimal(100)))

    @property
    def esta_casi_listo(self) -> bool:
        """Umbral de auto-estatus ``casi`` (§6). Configurable vía BD (§8.7)."""
        return self.pct >= Decimal(90)

    @property
    def esta_iniciado(self) -> bool:
        return self.pct > 0

    def __lt__(self, otro: Avance) -> bool:
        return self.pct < otro.pct


@dataclass(frozen=True, slots=True)
class PrecioUnitario:
    """CPU con su desglose de destajo (§7.3, §11.1).

    ``total`` es el costo completo (materiales + auxiliares + matrices + MO +
    equipo). ``destajo`` es la porción que cobra la cuadrilla (MO o
    subcontrato). Se estima por destajo, por concepto completo o por
    subcontrato (§6).
    """

    total: Dinero
    destajo: Dinero

    def __post_init__(self) -> None:
        if self.destajo.monto < 0 or self.total.monto < 0:
            raise ValueError("Un precio unitario no puede ser negativo.")
        if self.destajo.monto > self.total.monto:
            raise ValueError(
                f"El destajo ({self.destajo.formatear()}) no puede exceder el "
                f"CPU total ({self.total.formatear()}): el destajo es una "
                f"porción del total (§7.3)."
            )

    def para_modo(self, modo: str) -> Dinero:
        """Precio aplicable según el modo de pago (§6).

        ``destajo`` y ``subcontrato`` pagan mano de obra; ``concepto`` paga el
        CPU completo.
        """
        if modo in ("destajo", "subcontrato"):
            return self.destajo
        if modo == "concepto":
            return self.total
        raise ValueError(f"Modo de pago desconocido: {modo!r}")

    @property
    def materiales(self) -> Dinero:
        """Porción que no es destajo: la surte el almacén, no la paga la estimación."""
        return self.total - self.destajo
