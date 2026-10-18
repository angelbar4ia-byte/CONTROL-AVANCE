"""Ensamble: explosión recursiva de un presupuesto paramétrico.

Spec: skill `erp-parametrico` (cerebro CONOCIMIENTO.md §5.7-§5.10) · §7.3
(APU, `domain.catalogos.apu`) · §3.3 (la CLAVE manda en todo cruce).

**"El mismo mecanismo del APU, un piso más arriba" (skill §0).**

```
APU           concepto  → insumos    con cantidad
PARAMÉTRICO   ensamble  → conceptos  con cantidad
```

Un ensamble no tiene reglas propias de recursión: es el mismo árbol que
`apu.explotar` recorre, aplicado un nivel más arriba. La diferencia es qué
puede ser el hijo — nunca un insumo, siempre un **concepto** (ya resuelto a
su propio `PrecioUnitario` por `apu.explotar`, este módulo no vuelve a
explotarlo) o un **sub-ensamble** (que sí recursa, igual que un auxiliar o
una matriz recursan en APU).

**La referencia apunta al concepto, no al renglón (skill §3).** Un
`RenglonEnsamble` guarda la clave del concepto del catálogo compartido,
nunca una partida de presupuesto concreta: si ese presupuesto se borra o se
reordena, el ensamble sigue armable. Quien resuelve `precios_concepto`
(el aplicador) decide de qué CPU vigente sale cada precio — este módulo
solo recibe el mapa ya armado.

**Dos explosiones, no una (skill §4).** La de costo trae todo —da el
precio—; la de contratación agrupa **solo destajo**, por sub-ensamble —los
sub-ensambles son la unidad natural de contratación, porque es donde el
destajo tiene sentido para quien ejecuta—. Aquí no son dos recorridos
separados: `explotar_ensamble` hace un solo recorrido (igual de barato que
`apu.explotar`) y `agrupar_contratacion` es una vista derivada de sus
líneas, agrupando por el ensamble más cercano en la `ruta` de cada línea —
el propio ensamble raíz si el concepto cuelga directo de él, sin pasar por
ningún sub-ensamble.

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from obractrl.domain.catalogos.apu import (
    CicloEnExplosion,
    ErrorDeAPU,
    ProfundidadExcedida,
)
from obractrl.domain.shared.diccionario import OrigenCantidadEnsamble, TipoHijoEnsamble
from obractrl.domain.shared.valores import Dinero, PrecioUnitario

__all__ = [
    "ExplosionEnsambleCalculada",
    "GrupoContratacion",
    "LineaEnsamble",
    "RenglonEnsamble",
    "agrupar_contratacion",
    "explotar_ensamble",
]

_SEIS_DEC = Decimal("0.000001")
"""Misma precisión que `apu._cantidad` (numeric(18,6))."""

_PROFUNDIDAD_MAXIMA = 32
"""Mismo tope que APU (`apu._PROFUNDIDAD_MAXIMA`): cinturón de seguridad
contra la pila de Python, no una regla de negocio — un ensamble real anida
pocos niveles (recámara → ensamble de la casa)."""


def _cantidad(valor: Decimal | int | str) -> Decimal:
    return Decimal(str(valor)).quantize(_SEIS_DEC, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class RenglonEnsamble:
    """Una fila de un ensamble: el hijo es un concepto **o** un sub-ensamble
    (skill §0, §2-§3) — espeja `ck_ensamble_renglon_hijo` (migración 0061).

    `costo_unitario`/`destajo_unitario` de un concepto **nunca** se
    capturan aquí: salen de `precios_concepto` (su CPU vigente), que recibe
    `explotar_ensamble`. Para un sub-ensamble no aplican en absoluto — su
    costo es el resultado de explotarlo, igual que un auxiliar en APU.
    """

    cantidad: Decimal
    origen: OrigenCantidadEnsamble
    clave_concepto: str | None = None
    clave_sub_ensamble: str | None = None
    orden: int = 0

    def __post_init__(self) -> None:
        tiene_concepto = bool(self.clave_concepto)
        tiene_sub_ensamble = bool(self.clave_sub_ensamble)
        if tiene_concepto == tiene_sub_ensamble:
            raise ErrorDeAPU(
                "Un renglón de ensamble apunta a un concepto o a un "
                "sub-ensamble, nunca a los dos ni a ninguno "
                "(`ck_ensamble_renglon_hijo`, migración 0061)."
            )
        object.__setattr__(self, "cantidad", _cantidad(self.cantidad))

    @property
    def tipo_hijo(self) -> TipoHijoEnsamble:
        return (
            TipoHijoEnsamble.CONCEPTO
            if self.clave_concepto
            else TipoHijoEnsamble.ENSAMBLE
        )

    @property
    def referencia(self) -> str:
        """Clave del hijo — la identidad del cruce (§3.3)."""
        return self.clave_concepto or self.clave_sub_ensamble or ""


@dataclass(frozen=True, slots=True)
class LineaEnsamble:
    """Un renglón del árbol de ensamble ya explotado.

    Mismas dos cantidades que `apu.LineaExplosion`: `cantidad_unitaria` es
    lo que dice el renglón (por unidad del padre inmediato); `cantidad` es
    la acumulada por unidad del ensamble **raíz** — el producto del camino.

    A diferencia de `apu.LineaExplosion` (donde `es_destajo` es un booleano
    de la categoría del insumo), aquí cada línea trae **las dos** cifras —
    `costo_unitario` y `destajo_unitario` — porque un concepto siempre es
    una mezcla (material + mano de obra + lo que sea), nunca una cosa pura.
    """

    ruta: tuple[str, ...]
    nivel: int
    tipo_hijo: TipoHijoEnsamble
    referencia: str
    cantidad_unitaria: Decimal
    cantidad: Decimal
    costo_unitario: Decimal
    destajo_unitario: Decimal
    importe: Decimal
    importe_destajo: Decimal


@dataclass(frozen=True, slots=True)
class ExplosionEnsambleCalculada:
    """Resultado completo de explotar un ensamble: árbol + precio (skill §4,
    "explosión de costo")."""

    clave: str
    lineas: tuple[LineaEnsamble, ...]
    precio: PrecioUnitario


@dataclass(frozen=True, slots=True)
class GrupoContratacion:
    """Lo que se paga y se programa de un ensamble o sub-ensamble: solo
    destajo (skill §4, "explosión de contratación").

    `clave` es el ensamble más cercano del que cuelgan estas líneas —el
    raíz mismo si el concepto no está bajo ningún sub-ensamble— porque
    "los sub-ensambles son la unidad natural de contratación".
    """

    clave: str
    ruta: tuple[str, ...]
    destajo_total: Decimal
    lineas: tuple[LineaEnsamble, ...]


def _resolver(
    clave: str,
    *,
    composiciones: Mapping[str, Sequence[RenglonEnsamble]],
    precios_concepto: Mapping[str, PrecioUnitario],
    camino: tuple[str, ...],
    factor: Decimal,
) -> tuple[list[LineaEnsamble], Decimal, Decimal]:
    """Explota ``clave``: sus líneas y su ``(costo, destajo)`` **por
    unidad** — mismo contrato que `apu._resolver`, con concepto en vez de
    insumo y sub-ensamble en vez de auxiliar/matriz.

    Un ensamble ausente de ``composiciones`` no tiene renglones — hoja sin
    desglose, igual que un concepto sin `Explosion` en APU.
    """
    if clave in camino:
        raise CicloEnExplosion([*camino, clave])
    if len(camino) >= _PROFUNDIDAD_MAXIMA:
        raise ProfundidadExcedida([*camino, clave])

    ruta = (*camino, clave)
    lineas: list[LineaEnsamble] = []
    costo = Decimal(0)
    destajo = Decimal(0)

    for renglon in sorted(
        composiciones.get(clave, ()), key=lambda r: (r.orden, r.referencia)
    ):
        cantidad_acumulada = _cantidad(renglon.cantidad * factor)

        if renglon.tipo_hijo is TipoHijoEnsamble.ENSAMBLE:
            lineas_hijo, costo_unitario, destajo_unitario = _resolver(
                renglon.referencia,
                composiciones=composiciones,
                precios_concepto=precios_concepto,
                camino=ruta,
                factor=cantidad_acumulada,
            )
        else:
            precio = precios_concepto.get(renglon.referencia)
            costo_unitario = precio.total.monto if precio else Decimal(0)
            destajo_unitario = precio.destajo.monto if precio else Decimal(0)
            lineas_hijo = []

        lineas.append(
            LineaEnsamble(
                ruta=ruta,
                nivel=len(ruta),
                tipo_hijo=renglon.tipo_hijo,
                referencia=renglon.referencia,
                cantidad_unitaria=renglon.cantidad,
                cantidad=cantidad_acumulada,
                costo_unitario=costo_unitario,
                destajo_unitario=destajo_unitario,
                importe=Dinero(cantidad_acumulada * costo_unitario).monto,
                importe_destajo=Dinero(cantidad_acumulada * destajo_unitario).monto,
            )
        )
        lineas.extend(lineas_hijo)

        costo += renglon.cantidad * costo_unitario
        destajo += renglon.cantidad * destajo_unitario

    return lineas, costo, destajo


def explotar_ensamble(
    clave: str,
    *,
    composiciones: Mapping[str, Sequence[RenglonEnsamble]],
    precios_concepto: Mapping[str, PrecioUnitario] | None = None,
) -> ExplosionEnsambleCalculada:
    """Explosión de costo de un ensamble (skill §4): árbol completo —
    materiales, destajos, subcontratos, todo lo que ya resolvió el CPU de
    cada concepto.

    ``composiciones`` mapea clave de ensamble → sus renglones; debe traer
    **todos** los ensambles alcanzables desde ``clave`` por sub-ensamble.
    ``precios_concepto`` da el CPU vigente de cada concepto hoja —
    resuelto por quien llama (el aplicador), este módulo no lo calcula.

    Levanta :class:`CicloEnExplosion` si un ensamble se contiene a sí
    mismo, directa o indirectamente, vía sub-ensambles.
    """
    lineas, costo, destajo = _resolver(
        clave,
        composiciones=composiciones,
        precios_concepto=precios_concepto or {},
        camino=(),
        factor=Decimal(1),
    )
    return ExplosionEnsambleCalculada(
        clave=clave,
        lineas=tuple(lineas),
        precio=_precio(costo, destajo),
    )


def _precio(costo: Decimal, destajo: Decimal) -> PrecioUnitario:
    """Mismo cuidado de redondeo que `apu._precio`: acota el destajo si el
    redondeo a centavos lo empuja un centavo arriba del total."""
    total_dinero = Dinero(costo)
    destajo_dinero = Dinero(destajo)
    if destajo_dinero.monto > total_dinero.monto:
        destajo_dinero = total_dinero
    return PrecioUnitario(total=total_dinero, destajo=destajo_dinero)


def agrupar_contratacion(
    lineas: Sequence[LineaEnsamble],
) -> tuple[GrupoContratacion, ...]:
    """Explosión de contratación (skill §4): solo destajo, agrupado por el
    ensamble más cercano de cada línea — `ruta[-1]`, que es siempre un
    ensamble (el raíz o un sub-ensamble; un concepto nunca tiene hijos).

    Vista derivada de `lineas`, no un segundo recorrido del árbol: las dos
    explosiones conviven sobre el mismo resultado de `explotar_ensamble`
    (skill §6, "las dos conviven sobre el mismo documento" — dicho ahí de
    extracción/generación, pero el mismo principio aplica aquí).

    Solo entran líneas de concepto con destajo propio (`importe_destajo >
    0`): una línea de sub-ensamble no se cuenta aparte, su destajo ya está
    repartido entre sus propios conceptos hoja — sumarla también sería
    contarlo dos veces.
    """
    grupos: dict[tuple[str, ...], list[LineaEnsamble]] = {}
    for linea in lineas:
        if linea.tipo_hijo is not TipoHijoEnsamble.CONCEPTO:
            continue
        if linea.importe_destajo <= 0:
            continue
        grupos.setdefault(linea.ruta, []).append(linea)

    return tuple(
        GrupoContratacion(
            clave=ruta[-1],
            ruta=ruta,
            destajo_total=Dinero(
                sum((linea.importe_destajo for linea in de_ruta), Decimal(0))
            ).monto,
            lineas=tuple(de_ruta),
        )
        for ruta, de_ruta in sorted(grupos.items())
    )
