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
from enum import StrEnum

from obractrl.domain.catalogos.apu import (
    CicloEnExplosion,
    ErrorDeAPU,
    ProfundidadExcedida,
)
from obractrl.domain.shared.diccionario import OrigenCantidadEnsamble, TipoHijoEnsamble
from obractrl.domain.shared.valores import Dinero, PrecioUnitario

__all__ = [
    "CohorteInsuficiente",
    "EstadoRenglonGenerado",
    "ExplosionEnsambleCalculada",
    "GrupoContratacion",
    "LineaEnsamble",
    "ObservacionTasa",
    "PartidaExistente",
    "RenglonEnsamble",
    "RenglonGenerado",
    "TasaCalculada",
    "ValorPartida",
    "agrupar_contratacion",
    "calcular_tasa",
    "explotar_ensamble",
    "receta_por_concepto",
    "reconciliar_generacion",
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
    factor: Decimal = Decimal(1),
) -> ExplosionEnsambleCalculada:
    """Explosión de costo de un ensamble (skill §4): árbol completo —
    materiales, destajos, subcontratos, todo lo que ya resolvió el CPU de
    cada concepto.

    ``composiciones`` mapea clave de ensamble → sus renglones; debe traer
    **todos** los ensambles alcanzables desde ``clave`` por sub-ensamble.
    ``precios_concepto`` da el CPU vigente de cada concepto hoja —
    resuelto por quien llama (el aplicador), este módulo no lo calcula.

    ``factor``: cuántas veces entra ``clave`` en la instancia que se está
    generando (skill §6; `prototipo_nodo.ensamble_factor`, migración
    0062) — mismo papel que `RenglonEnsamble.cantidad` cuando un
    sub-ensamble cuelga de un padre, aplicado aquí porque la raíz no tiene
    un renglón padre que lo cargue. Por defecto 1: una explosión normal,
    sin instancia de por medio, sigue dando exactamente lo de antes.

    Levanta :class:`CicloEnExplosion` si un ensamble se contiene a sí
    mismo, directa o indirectamente, vía sub-ensambles.
    """
    lineas, costo, destajo = _resolver(
        clave,
        composiciones=composiciones,
        precios_concepto=precios_concepto or {},
        camino=(),
        factor=factor,
    )
    # `costo`/`destajo` que devuelve `_resolver` son el precio **por una
    # unidad** de `clave` —no usan `factor` en su propia acumulación, solo
    # lo propagan a las líneas hijas (igual que el costo de un sub-ensamble
    # no depende de cuántas veces lo multiplique su padre)— así que aquí sí
    # hay que escalarlos.
    return ExplosionEnsambleCalculada(
        clave=clave,
        lineas=tuple(lineas),
        precio=_precio(costo * factor, destajo * factor),
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


# --- Tasa y dispersión (skill §5.7) --------------------------------------
#
# "Un paramétrico global no funciona" — probado contra los siete
# prototipos reales: el costo por m² varía 36% entre ellos. Por eso la
# tasa nunca se calcula contra `prototipo.m2`: se calcula contra el
# divisor propio del ensamble (`ensamble.divisor_concepto_id`), sobre una
# cohorte declarada a mano (`ensamble_cohorte`) — nunca una partición
# derivada, porque "número de plantas" parecía la cohorte correcta de
# cimentación y no lo era (B-52/D-312: escala con el desplante).
#
# Qué cuenta como dato confiable para aprender —"no construir el corpus
# paramétrico sobre cantidades capturadas y llamarlo estadística" (regla
# 12 del skill)— es una decisión de quien llama (el aplicador que resuelve
# `ObservacionTasa` desde la base), nunca de este módulo: aquí solo entra
# estadística pura sobre lo que ya se decidió confiable.


class CohorteInsuficiente(ErrorDeAPU):
    """Menos de dos observaciones: no hay con qué medir dispersión.

    Con un solo dato la dispersión no es cero, es indefinida — tratarla
    como 0% sería exactamente "un número disfrazado de certeza" (regla 9
    del skill), solo que al revés: certeza fabricada en vez de ausente.
    """

    def __init__(self, n: int) -> None:
        super().__init__(
            f"Se necesitan al menos 2 observaciones para calcular tasa y "
            f"dispersión; llegaron {n}."
        )
        self.n = n


@dataclass(frozen=True, slots=True)
class ObservacionTasa:
    """Un punto de la cohorte (skill §5.7): cuánto costó el ensamble en un
    prototipo de referencia, y cuánto valía ahí su divisor.

    Quien arma esta lista ya decidió que el dato es confiable — este
    módulo no sabe de `modo_cantidad` ni debe saberlo (§12.11): esa
    política vive en el aplicador que resuelve estas observaciones desde
    `partida_presupuesto`/`prototipo_nodo`.
    """

    prototipo_clave: str
    numerador: Decimal
    divisor: Decimal

    def __post_init__(self) -> None:
        if self.divisor <= 0:
            raise ErrorDeAPU(
                f"El divisor de {self.prototipo_clave!r} no puede ser cero "
                f"ni negativo ({self.divisor}): no hay con qué normalizar "
                f"la tasa de ese prototipo."
            )

    @property
    def razon(self) -> Decimal:
        return self.numerador / self.divisor


@dataclass(frozen=True, slots=True)
class TasaCalculada:
    """Tasa y dispersión de un ensamble sobre su cohorte (skill §5.7,
    regla 9: "la dispersión se guarda junto al valor" — las dos cifras
    nacen y viajan juntas, nunca una sin la otra)."""

    tasa: Decimal
    dispersion: Decimal
    """Coeficiente de variación, en por ciento (Acabados a 5% es
    utilizable; Herrería a 38% es una adivinanza, skill §5.7)."""
    n: int
    prototipos: tuple[str, ...]


_TASA_DEC = Decimal("0.000001")
"""Misma precisión que `ensamble.tasa` (numeric(18,6), migración 0061)."""

_DISPERSION_DEC = Decimal("0.0001")
"""Misma precisión que `ensamble.dispersion` (numeric(7,4), migración 0061)."""


def calcular_tasa(observaciones: Sequence[ObservacionTasa]) -> TasaCalculada:
    """Tasa (media de numerador÷divisor) y dispersión (CV, en %) sobre la
    cohorte ya filtrada por quien llama.

    Exige al menos dos observaciones (:class:`CohorteInsuficiente`): con
    una sola no hay variación que medir.

    Desviación estándar **poblacional** (``n``, no ``n - 1``) — verificado
    reproduciendo el CV real del skill (§5.7, cimentación contra
    desplante, los siete prototipos): con ``n - 1`` da 6.52%, con ``n``
    da 6.03%, y el skill reporta "6.0%". La cohorte se trata como el
    universo bajo análisis en ese momento, no como una muestra de un
    universo más grande.
    """
    n = len(observaciones)
    if n < 2:
        raise CohorteInsuficiente(n)

    razones = [o.razon for o in observaciones]
    media = sum(razones, Decimal(0)) / n
    varianza = sum(((r - media) ** 2 for r in razones), Decimal(0)) / n
    desviacion = varianza.sqrt()
    dispersion = (desviacion / media * 100) if media != 0 else Decimal(0)

    return TasaCalculada(
        tasa=media.quantize(_TASA_DEC, rounding=ROUND_HALF_UP),
        dispersion=dispersion.quantize(_DISPERSION_DEC, rounding=ROUND_HALF_UP),
        n=n,
        prototipos=tuple(sorted(o.prototipo_clave for o in observaciones)),
    )


# --- Generación: reconciliar contra lo ya construido (skill §6) ---------
#
# Extracción (migración 0061) arma la plantilla desde lo ya hecho.
# Generación va al revés: compone un presupuesto a partir de un ensamble.
# La pregunta que resuelve esta sección no es "cuánto cuesta" —eso ya lo
# responde `explotar_ensamble`— sino "qué hago con lo que ya existe": al
# regenerar, una partida generada antes puede haberse quedado igual, haber
# sido editada a mano, o haber dejado de aparecer en la receta del
# ensamble. El skill lo resume en una regla (§8, regla 11): "nunca
# arrasar ni respetar en silencio" — y la cobertura (§6, "el residuo mide
# cobertura") exige que nada salga del presupuesto sin que alguien lo vea.
#
# Esta sección solo clasifica; no decide qué hacer con cada clase. Quien
# aplique la clasificación (el caso de uso) sabe que NUEVO/ACTUALIZADO son
# seguros de escribir sin preguntar, y que DESVINCULADO/CONFLICTO/SOBRA
# nunca se escriben solos — se reportan para que el usuario decida.

_CUATRO_DEC = Decimal("0.0001")
"""Misma precisión que `partida_presupuesto.precio_unitario` (numeric(18,4),
migración 0006)."""


@dataclass(frozen=True, slots=True)
class ValorPartida:
    """Lo que importa comparar de una partida: cuánto y a qué precio.

    No es `PrecioUnitario`/`Dinero` (`domain.shared.valores`): esas
    cuantizan a centavo, pero `partida_presupuesto.precio_unitario` guarda
    cuatro decimales (migración 0006) — redondear a dos aquí haría parecer
    "editado a mano" a una partida que el catálogo solo ajustó en el
    tercer o cuarto decimal.
    """

    cantidad: Decimal
    precio_unitario: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "cantidad", _cantidad(self.cantidad))
        object.__setattr__(
            self,
            "precio_unitario",
            Decimal(str(self.precio_unitario)).quantize(
                _CUATRO_DEC, rounding=ROUND_HALF_UP
            ),
        )


def receta_por_concepto(
    lineas: Sequence[LineaEnsamble],
) -> dict[str, ValorPartida]:
    """La cantidad **total** que el ensamble pide de cada concepto hoja,
    sumada a través de todos los caminos por los que aparezca.

    Un concepto puede entrar por más de un camino —directo y también
    dentro de un sub-ensamble— sin que sea doble contabilidad (skill §2,
    regla 3 de §8): lo que Generación necesita escribir es el total, no
    una línea por camino. El precio no se suma —es el mismo `PrecioUnitario`
    para ese concepto en cualquier camino, ya resuelto por
    `explotar_ensamble` desde `precios_concepto`— así que se toma una vez.
    """
    cantidades: dict[str, Decimal] = {}
    precios: dict[str, Decimal] = {}
    for linea in lineas:
        if linea.tipo_hijo is not TipoHijoEnsamble.CONCEPTO:
            continue
        cantidades[linea.referencia] = (
            cantidades.get(linea.referencia, Decimal(0)) + linea.cantidad
        )
        precios.setdefault(linea.referencia, linea.costo_unitario)

    return {
        clave: ValorPartida(cantidad=cantidad, precio_unitario=precios[clave])
        for clave, cantidad in cantidades.items()
    }


class EstadoRenglonGenerado(StrEnum):
    """Qué hacer con un concepto al regenerar (skill §6, §8 regla 11).

    Solo `NUEVO` y `ACTUALIZADO` son seguros de escribir sin preguntar:
    el primero no pisa nada, el segundo confirma que nadie lo tocó desde
    la última generación. Los otros tres nunca se escriben solos.
    """

    NUEVO = "nuevo"
    """En la receta de hoy; no existía ninguna partida para ese concepto
    en esta instancia. Se puede crear sin preguntar."""

    ACTUALIZADO = "actualizado"
    """En la receta y ya existía, con snapshot, y la partida sigue igual
    a su propio snapshot: nadie la tocó desde que se generó. Se refresca
    con el valor de hoy sin preguntar."""

    DESVINCULADO = "desvinculado"
    """En la receta y ya existía, con snapshot, pero la partida ya NO
    coincide con su snapshot: alguien la editó a mano. Nunca se pisa —se
    expone con las tres cifras (lo que el usuario puso, lo que tenía al
    generarse, lo que el ensamble pide hoy) para que decida."""

    CONFLICTO = "conflicto"
    """En la receta y ya existe una partida para ese concepto en esta
    instancia, pero sin snapshot: es una partida capturada a mano, nunca
    generada por este ensamble. No se sabe si es "la misma cosa" — se
    expone para que el usuario decida si la vincula o la deja aparte."""

    SOBRA = "sobra"
    """Existía una partida (generada antes, con o sin snapshot) para un
    concepto que la receta de hoy ya no incluye. Nunca se borra sola: el
    residuo es justamente lo que mide cobertura (skill §6) y nada sale del
    presupuesto sin que el usuario lo decida."""


@dataclass(frozen=True, slots=True)
class PartidaExistente:
    """Lo que ya hay en el presupuesto para un concepto, dentro de la
    instancia que se está regenerando."""

    actual: ValorPartida
    snapshot: ValorPartida | None
    """Lo que esta partida tenía al generarse la última vez. `None`: nunca
    la generó ningún ensamble (es capturada), aunque el concepto coincida
    con uno de la receta de hoy — ver `EstadoRenglonGenerado.CONFLICTO`."""


@dataclass(frozen=True, slots=True)
class RenglonGenerado:
    """Un concepto, clasificado para Generación (ver `EstadoRenglonGenerado`
    para qué hacer con cada estado)."""

    clave_concepto: str
    estado: EstadoRenglonGenerado
    receta: ValorPartida | None
    """Lo que el ensamble pide hoy. `None` solo en `SOBRA`: la receta de
    hoy ya no incluye este concepto."""
    existente: PartidaExistente | None
    """Lo que ya hay en el presupuesto. `None` solo en `NUEVO`: no existía
    ninguna partida para este concepto en esta instancia."""


def reconciliar_generacion(
    *,
    receta: Mapping[str, ValorPartida],
    existentes: Mapping[str, PartidaExistente],
) -> tuple[RenglonGenerado, ...]:
    """Clasifica cada concepto de la receta y cada partida ya existente
    (skill §6, §8 regla 11) — ver `EstadoRenglonGenerado`.

    No escribe nada ni decide qué hacer con cada clase: eso es del
    aplicador (§12.11), que sabe cuáles estados aplicar solo y cuáles
    reportar sin tocar.
    """
    resultado: list[RenglonGenerado] = []

    for clave, pedido in receta.items():
        existente = existentes.get(clave)
        if existente is None:
            resultado.append(
                RenglonGenerado(
                    clave_concepto=clave,
                    estado=EstadoRenglonGenerado.NUEVO,
                    receta=pedido,
                    existente=None,
                )
            )
        elif existente.snapshot is None:
            resultado.append(
                RenglonGenerado(
                    clave_concepto=clave,
                    estado=EstadoRenglonGenerado.CONFLICTO,
                    receta=pedido,
                    existente=existente,
                )
            )
        elif existente.actual == existente.snapshot:
            resultado.append(
                RenglonGenerado(
                    clave_concepto=clave,
                    estado=EstadoRenglonGenerado.ACTUALIZADO,
                    receta=pedido,
                    existente=existente,
                )
            )
        else:
            resultado.append(
                RenglonGenerado(
                    clave_concepto=clave,
                    estado=EstadoRenglonGenerado.DESVINCULADO,
                    receta=pedido,
                    existente=existente,
                )
            )

    for clave, existente in existentes.items():
        if clave not in receta:
            resultado.append(
                RenglonGenerado(
                    clave_concepto=clave,
                    estado=EstadoRenglonGenerado.SOBRA,
                    receta=None,
                    existente=existente,
                )
            )

    return tuple(sorted(resultado, key=lambda r: r.clave_concepto))
