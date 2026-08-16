"""APU: explosión recursiva de un concepto y su CPU.

Spec §7.3 (explosión y CPU) · §11.1 (value object `PrecioUnitario`, entidades
puras para el contexto pesado) · §10.6 (cabeceras del archivo de CPU) ·
§3.3 (la CLAVE manda en todo cruce).

**El modelo (§7.3).** Un concepto se compone de `Explosion`: filas que
apuntan a un **insumo** (material, mano de obra, equipo) o a **otro
concepto** (auxiliar o matriz), cada una con su `cantidad`/`rendimiento` y su
`costo_unitario`. Como un hijo puede ser otro concepto, la composición es un
**árbol** que hay que recorrer hasta las hojas.

**Los dos números (§7.3, cita literal).** "el **destajo** = mano de obra o
subcontrato (lo que cobra la cuadrilla); el **CPU** = costo total (materiales
+ auxiliares + matrices + MO + equipo)". Es decir: el destajo **no** es otra
suma paralela, es la **porción** del mismo árbol cuya categoría es mano de
obra, destajo o subcontrato — incluida la que viene dentro de un auxiliar o
de una matriz, que también trae su propia mano de obra. Por eso la recursión
devuelve **las dos** cifras a la vez, y `PrecioUnitario` puede exigir
`destajo <= total` sin que sea un accidente.

**Ciclos.** La base solo impide el ciclo *directo*
(`ck_explosion_no_ciclo_directo`, migración 0005): A→B→A pasa el `CHECK` y
colgaría cualquier recorrido ingenuo. Aquí se detecta con el camino de la
recursión y se levanta :class:`CicloEnExplosion`, igual que hace
`domain.programacion.cpm` con el cronograma.

**Identidad por CLAVE (§3.3).** El dominio habla de claves, no de uuids: "en
todos los catálogos la clave es única… todo análisis, mapeo y cruce prioriza
la comparación por CLAVE". El adaptador traduce uuid ↔ clave en el borde.

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from obractrl.domain.shared.diccionario import CategoriaExplosion, TipoHijoExplosion
from obractrl.domain.shared.valores import Dinero, PrecioUnitario

__all__ = [
    "CATEGORIAS_DE_DESTAJO",
    "CicloEnExplosion",
    "Componente",
    "ErrorDeAPU",
    "ExplosionCalculada",
    "LineaExplosion",
    "ProfundidadExcedida",
    "VersionCPU",
    "calcular_cpu",
    "explotar",
    "publicar_version",
    "siguiente_version",
    "vigente_de",
]

CATEGORIAS_DE_DESTAJO: frozenset[CategoriaExplosion] = frozenset(
    {
        CategoriaExplosion.MANO_OBRA,
        CategoriaExplosion.DESTAJO,
        CategoriaExplosion.SUBCONTRATO,
    }
)
"""Categorías que cobra la cuadrilla (§7.3): "destajo = mano de obra o subcontrato"."""

_CUATRO_DEC = Decimal("0.0001")
"""Precisión de `explosion.costo_unitario` / `importe` (numeric(18,4), 0005)."""

_SEIS_DEC = Decimal("0.000001")
"""Precisión de `explosion.cantidad` / `rendimiento` (numeric(18,6), 0005)."""

_PROFUNDIDAD_MAXIMA = 32
"""Tope de anidamiento de auxiliares/matrices.

No es una regla de negocio, es un cinturón de seguridad: la detección de
ciclos ya corta cualquier recursión infinita legítima, pero un catálogo con
decenas de miles de conceptos y un anidamiento absurdo agotaría la pila de
Python antes de terminar. El §7.3 anida auxiliares y matrices dentro de
conceptos —dos o tres niveles en la práctica—, así que 32 es holgado.
"""


class ErrorDeAPU(ValueError):
    """Composición de APU inválida (§7.3)."""


class CicloEnExplosion(ErrorDeAPU):
    """Un concepto se contiene a sí mismo: su CPU no es calculable.

    El `CHECK` de la base solo cubre el ciclo directo (A→A); este es el caso
    indirecto (A→B→A), que solo se ve recorriendo el árbol.
    """

    def __init__(self, camino: Sequence[str]) -> None:
        super().__init__(
            "La explosión del concepto tiene un ciclo y no se puede calcular: "
            + " → ".join(camino)
            + ". Un concepto no puede contenerse a sí mismo, ni directa ni "
            "indirectamente (§7.3)."
        )
        self.camino = list(camino)


class ProfundidadExcedida(ErrorDeAPU):
    """La explosión anida más allá del tope razonable (§7.3)."""

    def __init__(self, camino: Sequence[str]) -> None:
        super().__init__(
            f"La explosión excede {_PROFUNDIDAD_MAXIMA} niveles de anidamiento: "
            + " → ".join(camino)
            + ". Revisa la composición: un APU real anida auxiliares y "
            "matrices, no cadenas de esa profundidad (§7.3)."
        )
        self.camino = list(camino)


def _cantidad(valor: Decimal | int | str) -> Decimal:
    return Decimal(str(valor)).quantize(_SEIS_DEC, rounding=ROUND_HALF_UP)


def _costo(valor: Decimal | int | str) -> Decimal:
    return Decimal(str(valor)).quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class Componente:
    """Una fila de `Explosion`: el hijo es un insumo **o** un concepto (§7.3).

    Espeja `ck_explosion_hijo` de la migración 0005 —exactamente uno de los
    dos— para que el invariante no dependa solo de la base.

    ``costo_unitario`` es el **PU declarado en el APU** (columna F del archivo
    de CPU, §10.6). Es opcional: cuando la fila viene sin PU, el costo lo pone
    el catálogo (`costo_base_actualizado` = costo vigente, §10.1) a través del
    mapa ``costos_insumo`` que recibe :func:`explotar`. Para un hijo de tipo
    concepto **siempre** se ignora: el costo de un auxiliar o una matriz es el
    resultado de explotarlo, no un número capturado.
    """

    categoria: CategoriaExplosion
    cantidad: Decimal
    clave_insumo: str | None = None
    clave_concepto: str | None = None
    costo_unitario: Decimal | None = None
    orden: int = 0

    def __post_init__(self) -> None:
        tiene_insumo = bool(self.clave_insumo)
        tiene_concepto = bool(self.clave_concepto)
        if tiene_insumo == tiene_concepto:
            raise ErrorDeAPU(
                "Un componente apunta a un insumo o a un concepto, nunca a los "
                "dos ni a ninguno (§7.3, `ck_explosion_hijo`)."
            )
        if self.cantidad < 0:
            raise ErrorDeAPU(
                f"La cantidad/rendimiento de un componente no puede ser "
                f"negativa: {self.cantidad}."
            )
        if self.costo_unitario is not None and self.costo_unitario < 0:
            raise ErrorDeAPU(
                f"El costo unitario de un componente no puede ser negativo: "
                f"{self.costo_unitario}."
            )
        object.__setattr__(self, "cantidad", _cantidad(self.cantidad))
        if self.costo_unitario is not None:
            object.__setattr__(self, "costo_unitario", _costo(self.costo_unitario))

    @property
    def tipo_hijo(self) -> TipoHijoExplosion:
        return (
            TipoHijoExplosion.INSUMO
            if self.clave_insumo
            else TipoHijoExplosion.CONCEPTO
        )

    @property
    def referencia(self) -> str:
        """Clave del hijo — la identidad del cruce (§3.3)."""
        return self.clave_insumo or self.clave_concepto or ""

    @property
    def es_destajo(self) -> bool:
        """Lo que cobra la cuadrilla (§7.3)."""
        return self.categoria in CATEGORIAS_DE_DESTAJO


@dataclass(frozen=True, slots=True)
class LineaExplosion:
    """Un renglón del árbol ya explotado, listo para `GET /conceptos/{id}/explosion`.

    ``cantidad_unitaria`` es lo que dice la fila de `Explosion` (por unidad del
    **padre inmediato**); ``cantidad`` es la acumulada por unidad del concepto
    **raíz** —el producto del camino—, que es la que sirve para cruzar contra
    el consumo real de almacén (§10.5).
    """

    ruta: tuple[str, ...]
    nivel: int
    tipo_hijo: TipoHijoExplosion
    referencia: str
    categoria: CategoriaExplosion
    cantidad_unitaria: Decimal
    cantidad: Decimal
    costo_unitario: Decimal
    importe: Decimal
    es_destajo: bool


@dataclass(frozen=True, slots=True)
class ExplosionCalculada:
    """Resultado completo de explotar un concepto: árbol + precio (§7.3)."""

    clave: str
    lineas: tuple[LineaExplosion, ...]
    precio: PrecioUnitario


def _resolver(
    clave: str,
    *,
    composiciones: Mapping[str, Sequence[Componente]],
    costos_insumo: Mapping[str, Decimal],
    camino: tuple[str, ...],
    factor: Decimal,
) -> tuple[list[LineaExplosion], Decimal, Decimal]:
    """Explota ``clave``: sus líneas y su ``(total, destajo)`` **por unidad**.

    Un concepto ausente de ``composiciones`` es una hoja sin desglose: cuesta
    cero por sí mismo. No es un error — un `basico` puede no tener explosión,
    y el repositorio solo devuelve filas de los conceptos que sí la tienen.

    Las líneas salen en recorrido **padre antes que hijos**, igual que
    `arbol_prototipo` (§7.4): la recursión tiene que costear al hijo primero,
    pero la lista se arma emitiendo la línea del componente y **después** las
    de su subárbol.
    """
    if clave in camino:
        raise CicloEnExplosion([*camino, clave])
    if len(camino) >= _PROFUNDIDAD_MAXIMA:
        raise ProfundidadExcedida([*camino, clave])

    ruta = (*camino, clave)
    lineas: list[LineaExplosion] = []
    total = Decimal(0)
    destajo = Decimal(0)

    for componente in sorted(
        composiciones.get(clave, ()), key=lambda c: (c.orden, c.referencia)
    ):
        cantidad_acumulada = _cantidad(componente.cantidad * factor)
        lineas_hijo: list[LineaExplosion] = []

        if componente.tipo_hijo is TipoHijoExplosion.CONCEPTO:
            lineas_hijo, hijo_total, hijo_destajo = _resolver(
                componente.referencia,
                composiciones=composiciones,
                costos_insumo=costos_insumo,
                camino=ruta,
                factor=cantidad_acumulada,
            )
            costo_unitario = _costo(hijo_total)
            # El auxiliar/matriz aporta su total al CPU y su **propia** mano de
            # obra al destajo (§7.3): la cuadrilla también cobra lo que hay
            # dentro del auxiliar, no solo la MO del primer nivel.
            aporte_total = componente.cantidad * hijo_total
            aporte_destajo = componente.cantidad * hijo_destajo
        else:
            costo_unitario = (
                componente.costo_unitario
                if componente.costo_unitario is not None
                else _costo(costos_insumo.get(componente.referencia, Decimal(0)))
            )
            aporte_total = componente.cantidad * costo_unitario
            aporte_destajo = aporte_total if componente.es_destajo else Decimal(0)

        lineas.append(
            LineaExplosion(
                ruta=ruta,
                nivel=len(ruta),
                tipo_hijo=componente.tipo_hijo,
                referencia=componente.referencia,
                categoria=componente.categoria,
                cantidad_unitaria=componente.cantidad,
                cantidad=cantidad_acumulada,
                costo_unitario=costo_unitario,
                importe=_costo(cantidad_acumulada * costo_unitario),
                es_destajo=componente.es_destajo,
            )
        )
        lineas.extend(lineas_hijo)

        total += aporte_total
        destajo += aporte_destajo

    return lineas, total, destajo


def explotar(
    clave: str,
    *,
    composiciones: Mapping[str, Sequence[Componente]],
    costos_insumo: Mapping[str, Decimal] | None = None,
) -> ExplosionCalculada:
    """Explosión recursiva de un concepto con su CPU (§7.3).

    ``composiciones`` mapea clave de concepto → sus filas de `Explosion`;
    debe traer **todos** los conceptos alcanzables desde ``clave``, porque uno
    ausente se toma como hoja sin desglose. ``costos_insumo`` da el costo
    vigente del catálogo (§10.1) para los componentes que no traen PU propio.

    Levanta :class:`CicloEnExplosion` si el concepto se contiene a sí mismo,
    directa o indirectamente.
    """
    lineas, total, destajo = _resolver(
        clave,
        composiciones=composiciones,
        costos_insumo=costos_insumo or {},
        camino=(),
        factor=Decimal(1),
    )
    return ExplosionCalculada(
        clave=clave,
        lineas=tuple(lineas),
        precio=_precio(total, destajo),
    )


def _precio(total: Decimal, destajo: Decimal) -> PrecioUnitario:
    """Arma el `PrecioUnitario` cuidando el redondeo a centavos.

    `Dinero` redondea a centavos (§3.5) y `PrecioUnitario` exige
    ``destajo <= total``. Con un destajo que es casi todo el total —un
    concepto `SUB-` es 100% subcontrato— redondear cada cifra por separado
    puede empujar el destajo un centavo por encima. Acotarlo aquí es
    aritmética de redondeo, no una regla de negocio: la invariante del §7.3
    sigue siendo del value object.
    """
    total_dinero = Dinero(total)
    destajo_dinero = Dinero(destajo)
    if destajo_dinero.monto > total_dinero.monto:
        destajo_dinero = total_dinero
    return PrecioUnitario(total=total_dinero, destajo=destajo_dinero)


def calcular_cpu(
    clave: str,
    *,
    composiciones: Mapping[str, Sequence[Componente]],
    costos_insumo: Mapping[str, Decimal] | None = None,
) -> PrecioUnitario:
    """CPU del concepto con su desglose de destajo (§7.3, §11.1)."""
    return explotar(
        clave, composiciones=composiciones, costos_insumo=costos_insumo
    ).precio


# --- Versionado de CPU (§7.3, §10.8) -------------------------------------


@dataclass(frozen=True, slots=True)
class VersionCPU:
    """Una versión del precio unitario de un concepto (§7.3).

    La **variante** es la receta alterna del §2.2 (`mortero` vs
    `cemento+arena`): el esquema permite un vigente **por variante**
    (`uq_cpu_vigente`), así que toda la vigencia de aquí es "por concepto y
    variante". La receta base es ``variante = None``.
    """

    version: int
    precio: PrecioUnitario
    vigente: bool = False
    variante: str | None = None

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ErrorDeAPU(
                f"La versión de un CPU empieza en 1: {self.version}."
            )


def _de_la_variante(
    versiones: Sequence[VersionCPU], variante: str | None
) -> list[VersionCPU]:
    return [v for v in versiones if v.variante == variante]


def vigente_de(
    versiones: Sequence[VersionCPU], *, variante: str | None = None
) -> VersionCPU | None:
    """La versión vigente de la variante, o ``None`` si aún no hay ninguna.

    Levanta :class:`ErrorDeAPU` si el conjunto trae más de una vigente: es el
    mismo invariante que `uq_cpu_vigente` impone en la base, verificado aquí
    para que el dominio no dependa de que la base lo atrape.
    """
    vigentes = [v for v in _de_la_variante(versiones, variante) if v.vigente]
    if len(vigentes) > 1:
        raise ErrorDeAPU(
            f"Hay {len(vigentes)} versiones vigentes del CPU "
            f"(variante {variante!r}): "
            f"{', '.join(str(v.version) for v in sorted(vigentes, key=lambda x: x.version))}. "
            f"Solo una versión puede estar vigente por concepto y variante (§7.3)."
        )
    return vigentes[0] if vigentes else None


def siguiente_version(
    versiones: Sequence[VersionCPU], *, variante: str | None = None
) -> int:
    """Consecutivo de la próxima versión de la variante (§7.3, §10.8)."""
    de_la_variante = _de_la_variante(versiones, variante)
    return max((v.version for v in de_la_variante), default=0) + 1


def publicar_version(
    versiones: Sequence[VersionCPU],
    precio: PrecioUnitario,
    *,
    variante: str | None = None,
) -> tuple[VersionCPU, tuple[int, ...]]:
    """Nueva versión vigente del CPU (§11.2 `POST /conceptos/{id}/cpu`).

    Devuelve la versión nueva —ya vigente— y las versiones que hay que
    **retirar** para que siga habiendo una sola vigente. Publicar no borra
    nada: el histórico queda para comparar y restaurar (§10.8).
    """
    # Valida de paso que el estado de partida sea consistente: publicar sobre
    # un conjunto con dos vigentes escondería el problema en vez de exponerlo.
    anterior = vigente_de(versiones, variante=variante)
    nueva = VersionCPU(
        version=siguiente_version(versiones, variante=variante),
        precio=precio,
        vigente=True,
        variante=variante,
    )
    return nueva, (anterior.version,) if anterior is not None else ()
