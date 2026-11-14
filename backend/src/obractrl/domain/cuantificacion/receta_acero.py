"""Receta del acero de los elementos lineales y de pieza (castillos, columnas, trabes, cadenas).

Dominio puro del mockup de elementos paramétricos (funciones `corteDe` y `muestra` de `app.js`, decisiones M-xx de
la especificación): dado el armado de un elemento calcula, **por pieza** (castillo, columna, trabe por pieza) o **por
metro lineal de trazo** (cadena, trabe por ml):

- **Varillas longitudinales** con traslape de ``traslape_varilla_diametros`` diámetros (40) y puntas de anclaje por
  diámetro (``puntas_inferior_diametros`` + ``puntas_superior_diametros``). En una pieza de altura/largo conocido la
  varilla se corta con la **regla de cortes**: módulos de 1, 1.5, 2, 3, 4 y 6 m (los que caben en la barra comercial),
  con a lo más ``max_piezas_corte`` piezas por corte (3) y una tolerancia opcional; se elige el corte que gasta menos
  material y, a igual material, el de menos piezas. Si no hay solución dentro del máximo se permite pasarlo (hasta 12
  piezas) y se avisa. En un tramo continuo (por ml) no hay cortes: se aplica el factor ``L ÷ (L − traslape)``.
- **Armex** con traslape de ``traslape_armex_cm`` (15 cm); en una pieza de castillo se corta con la misma regla de
  cortes con ``puntas_armex_cm`` (50 cm) de anclaje; en un tramo continuo (o una trabe por pieza) sale
  ``longitud ÷ (L − traslape)`` piezas.
- **Anillos por zonas** (pza y kg). Largo del anillo = perímetro del núcleo (sección menos el recubrimiento por lado)
  × ``factor_anillo`` + gancho. La calibración del mockup con el catálogo es perímetro × 1.10 + 16.5 cm de gancho
  (0.825 m el anillo 10×20), pero eso lo trae el elemento (`factor_anillo`, `gancho_cm`), no es una constante aquí.
  Zonas: ``len_cm`` es el largo de la zona (en cada extremo, en una trabe por pieza) y ``None`` es el resto/centro.
  En pieza el primer anillo de la primera zona se suma a ``ceil(largo ÷ separación)``; en ml es ``largo ÷ separación``.
- **Alambre de amarre**: kg por ml del catálogo si se da, o amarres (varillas × anillos × metros por amarre) × kg/m.
- **Cimbra por lados**: m² por la forma del elemento y consumos por ml (clavos, tablas, alambre) o por m².

Salida estructurada: piezas comerciales, kg, desperdicio (sobrante del corte, traslape, puntas) y advertencias. Los
drivers nuevos (traslapes, puntas, tolerancia, máximo de piezas) son valores por defecto de `DriversDeReceta`: quien
llame (la obra, la petición) los sustituye; aquí no se leen de ningún lado. Función pura, sin base de datos.

Lo que el catálogo contradice **no se corrige** aquí (queda documentado en las pruebas como «diferencia conocida»):
el catálogo cuenta 8 % de desperdicio en lugar del traslape de 40 diámetros (3 a 7 %), y cuenta algunos anillos más
cortos que el perímetro de su sección.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "MAXIMO_DE_PIEZAS_DE_RESPALDO",
    "MODULOS_DE_CORTE_M",
    "Armex",
    "ConsumoDeCimbra",
    "CorteDeVarilla",
    "DriversDeReceta",
    "EntradaRecetaAcero",
    "ErrorDeRecetaAcero",
    "GrupoDeVarillas",
    "Varilla",
    "ZonaDeAnillo",
    "calcular_receta_acero",
    "corte_de",
    "diametro_de_varilla_m",
]

MODULOS_DE_CORTE_M: tuple[float, ...] = (1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
"""Largos en que se corta una barra comercial (M-38): solo los que caben en la barra."""

MAXIMO_DE_PIEZAS_DE_RESPALDO = 12
"""Si no hay solución con `max_piezas_corte`, se busca hasta aquí y se avisa."""

_EPS = 1e-9

Forma = Literal["castillo", "pieza", "ml"]


class ErrorDeRecetaAcero(ErrorDeCuantificacion):
    """Un dato del armado que no vale: no se puede calcular la receta con él."""


@dataclass(frozen=True)
class DriversDeReceta:
    """Los drivers del acero. Valores del mockup (`spec.js`); «por confirmar» los marca la especificación."""

    traslape_armex_cm: float = 15.0
    traslape_varilla_diametros: float = 40.0
    """Confirmado por el usuario (NTC Concreto)."""
    puntas_inferior_diametros: float = 40.0
    """Anclaje inferior del castillo. Por confirmar con el estructurista (Q22)."""
    puntas_superior_diametros: float = 40.0
    """Anclaje superior del castillo. Por confirmar con el estructurista (Q22)."""
    puntas_armex_cm: float = 50.0
    """SUPUESTO: suma de anclaje inferior y superior del armex. Por confirmar (Q22)."""
    tolerancia_corte_cm: float = 0.0
    max_piezas_corte: int = 3
    desperdicio_acero_pct: float = 0.0
    """El catálogo usa 5 a 8 % en lugar del traslape; aquí el traslape se calcula aparte."""

    def __post_init__(self) -> None:
        for nombre in (
            "traslape_armex_cm",
            "traslape_varilla_diametros",
            "puntas_inferior_diametros",
            "puntas_superior_diametros",
            "puntas_armex_cm",
            "tolerancia_corte_cm",
            "desperdicio_acero_pct",
        ):
            if not (getattr(self, nombre) >= 0):
                raise ErrorDeRecetaAcero(f"El driver {nombre} no puede ser negativo.")
        if self.max_piezas_corte < 1 or self.max_piezas_corte > MAXIMO_DE_PIEZAS_DE_RESPALDO:
            raise ErrorDeRecetaAcero(
                f"El máximo de piezas por corte va de 1 a {MAXIMO_DE_PIEZAS_DE_RESPALDO}."
            )


@dataclass(frozen=True)
class Varilla:
    """Una varilla comercial: `numero` es el número de varilla (3 = 3/8", 4 = 1/2"…), diámetro = numero/8 pulg."""

    clave: str
    numero: int
    largo_m: float = 12.0
    peso_kg_m: float | None = None


@dataclass(frozen=True)
class Armex:
    """Armex (armadura electrosoldada). El catálogo no le da peso por metro: `peso_kg_m` queda sin dato."""

    clave: str
    largo_m: float = 6.0
    peso_kg_m: float | None = None


@dataclass(frozen=True)
class GrupoDeVarillas:
    cantidad: int
    varilla: Varilla
    etiqueta: str = ""
    """Opcional, para la vista («arriba», «abajo»)."""


@dataclass(frozen=True)
class ZonaDeAnillo:
    sep_cm: float
    peso_kg_m: float
    len_cm: float | None = None
    """Largo de la zona (en cada extremo en una trabe por pieza); `None` = el resto/centro."""
    clave: str | None = None


@dataclass(frozen=True)
class ConsumoDeCimbra:
    """Un insumo de la cimbra: `por_ml` (por metro de elemento, como el catálogo) o `por_m2` (por m² de cimbra)."""

    clave: str
    por_ml: float | None = None
    por_m2: float | None = None


@dataclass(frozen=True)
class EntradaRecetaAcero:
    """Lo que se calcula.

    - ``forma="castillo"``: pieza de altura `longitud_m`; la sección es `ancho_cm` × `peralte_cm` (en un castillo
      `peralte_cm` es el largo de la sección); la cimbra sale del perímetro por `lados_cimbra`.
    - ``forma="pieza"``: trabe/contratrabe/nervadura por pieza de largo `longitud_m`; `peralte_cm` es el peralte.
    - ``forma="ml"``: por metro lineal de trazo (`longitud_m` se ignora, vale 1).
    """

    forma: Forma
    ancho_cm: float
    peralte_cm: float
    longitud_m: float | None = None
    lados_cimbra: int = 0
    varillas: Sequence[GrupoDeVarillas] = ()
    armex: Armex | None = None
    anillos: Sequence[ZonaDeAnillo] = ()
    gancho_cm: float = 10.0
    recubrimiento_cm: float = 2.5
    factor_anillo: float = 1.0
    alambre_por_amarre_m: float = 0.3
    alambre_peso_kg_m: float = 0.0095
    alambre_kg_ml: float | None = None
    cimbra: Sequence[ConsumoDeCimbra] = ()
    cantidad: float = 1.0
    """Cuántas piezas (o ml) se piden: da los totales a comprar."""
    drivers: DriversDeReceta = field(default_factory=DriversDeReceta)


@dataclass(frozen=True)
class CorteDeVarilla:
    """Cómo se cubre un largo con módulos de corte: `n` piezas de `modulo_m` con `traslape_m` entre ellas."""

    n: int
    modulo_m: float
    total_m: float
    """Material cortado: n × módulo."""
    alto_que_cubre_m: float
    """Lo que cubre sin las puntas: n × módulo − (n − 1) × traslape − puntas."""
    necesario_m: float
    """Largo + puntas."""
    traslape_m: float
    puntas_m: float
    cubre_completo: bool
    """False solo si ni 12 piezas alcanzan (largo fuera de rango)."""
    excede_maximo: bool
    """True si hubo que pasar de `max_piezas_corte`."""

    @property
    def traslapes_m(self) -> float:
        return (self.n - 1) * self.traslape_m

    @property
    def sobrante_m(self) -> float:
        """Lo que sobra del corte sobre lo necesario (≥ 0 cuando cubre)."""
        return max(0.0, self.total_m - self.traslapes_m - self.necesario_m)


def diametro_de_varilla_m(numero: int) -> float:
    """Diámetro en metros de la varilla del número dado (número/8 de pulgada)."""
    return numero / 8 * 25.4 / 1000


def corte_de(
    largo_m: float,
    largo_barra_m: float,
    traslape_m: float,
    puntas_m: float,
    drivers: DriversDeReceta | None = None,
) -> CorteDeVarilla:
    """Regla de cortes (M-38): los módulos 1/1.5/2/3/4/6 m que caben en la barra cubren `largo + puntas`.

    Entre `n` piezas hay `n − 1` traslapes. Gana el corte que gasta menos material (`n × módulo`) y, a igual material,
    el de menos piezas; primero con a lo más `max_piezas_corte` piezas y, solo si no hay solución, hasta 12.
    """
    d = drivers or DriversDeReceta()
    necesario = largo_m + puntas_m
    tol = d.tolerancia_corte_cm / 100
    modulos = [m for m in MODULOS_DE_CORTE_M if m <= largo_barra_m + _EPS]
    if not modulos:
        raise ErrorDeRecetaAcero("Ningún módulo de corte cabe en la barra comercial.")
    mejor: tuple[int, float, float, float] | None = None  # n, módulo, total, cubre (con puntas)
    excede = False
    for tope in (d.max_piezas_corte, MAXIMO_DE_PIEZAS_DE_RESPALDO):
        if mejor is not None:
            break
        for n in range(1, tope + 1):
            for m in modulos:
                cubre = n * m - (n - 1) * traslape_m
                if cubre + tol < necesario - _EPS:
                    continue
                total = n * m
                if (
                    mejor is None
                    or total < mejor[2] - _EPS
                    or (abs(total - mejor[2]) < _EPS and n < mejor[0])
                ):
                    mejor = (n, m, total, cubre)
        excede = tope > d.max_piezas_corte
    if mejor is None:
        m = modulos[-1]
        n = MAXIMO_DE_PIEZAS_DE_RESPALDO
        return CorteDeVarilla(n, m, n * m, 0.0, necesario, traslape_m, puntas_m, False, True)
    n, m, total, cubre = mejor
    return CorteDeVarilla(
        n, m, total, cubre - puntas_m, necesario, traslape_m, puntas_m, True, excede and n > d.max_piezas_corte
    )


def _corte_a_dict(c: CorteDeVarilla) -> dict[str, Any]:
    return {
        "piezas": c.n,
        "modulo_m": c.modulo_m,
        "total_m": c.total_m,
        "alto_que_cubre_m": c.alto_que_cubre_m,
        "necesario_m": c.necesario_m,
        "traslape_m": c.traslape_m,
        "puntas_m": c.puntas_m,
        "sobrante_m": c.sobrante_m,
        "excede_maximo": c.excede_maximo,
        "cubre_completo": c.cubre_completo,
    }


def _techo(x: float) -> int:
    return math.ceil(x - 1e-9)


def _validar(e: EntradaRecetaAcero) -> float:
    if e.forma not in ("castillo", "pieza", "ml"):
        raise ErrorDeRecetaAcero("La forma es «castillo», «pieza» o «ml».")
    if not (e.ancho_cm > 0) or not (e.peralte_cm > 0):
        raise ErrorDeRecetaAcero("El ancho y el peralte de la sección van en centímetros y deben ser mayores que cero.")
    if e.forma == "ml":
        largo = 1.0
    else:
        if e.longitud_m is None or not (0 < e.longitud_m <= 30):
            raise ErrorDeRecetaAcero("El alto o largo de la pieza va en metros, entre 0 y 30.")
        largo = e.longitud_m
    if not (e.cantidad > 0):
        raise ErrorDeRecetaAcero("La cantidad debe ser mayor que cero.")
    if e.lados_cimbra < 0 or e.lados_cimbra > 4:
        raise ErrorDeRecetaAcero("Los lados de cimbra van de 0 a 4.")
    if e.armex is not None and e.varillas:
        raise ErrorDeRecetaAcero("El armado es armex o varillas con anillos, no los dos.")
    if e.armex is not None and not (e.armex.largo_m > 0):
        raise ErrorDeRecetaAcero("La pieza de armex debe tener largo.")
    for g in e.varillas:
        if g.cantidad < 1 or not (g.varilla.largo_m > 0) or g.varilla.numero < 1:
            raise ErrorDeRecetaAcero("Cada grupo de varillas lleva al menos una y su número y largo comercial.")
    for z in e.anillos:
        if not (z.sep_cm > 0) or z.peso_kg_m < 0 or (z.len_cm is not None and z.len_cm < 0):
            raise ErrorDeRecetaAcero("Cada zona de anillos lleva separación mayor que cero y largo no negativo.")
    if not (0 <= e.recubrimiento_cm < min(e.ancho_cm, e.peralte_cm) / 2):
        raise ErrorDeRecetaAcero("El recubrimiento no cabe en la sección.")
    if e.gancho_cm < 0 or not (e.factor_anillo > 0):
        raise ErrorDeRecetaAcero("El gancho no es negativo y el factor del anillo es mayor que cero.")
    return largo


def _cimbra_m2(e: EntradaRecetaAcero, largo: float) -> float:
    k = e.lados_cimbra
    a = e.ancho_cm / 100
    p = e.peralte_cm / 100
    if e.forma == "castillo":
        if k <= 0:
            return 0.0
        # k=4 perímetro completo, k=3 tres lados (dos largos y uno ancho), k=2 los dos largos, k=1 uno. (El mockup
        # deja 2l también para k=1; un solo lado es l: se corrige aquí y se avisa en el informe de la lane.)
        perimetro = 2 * (p + a) if k >= 4 else (2 * p + a if k == 3 else k * p)
        return perimetro * largo
    return ((2 if k >= 2 else k) * p + (a if k >= 3 else 0.0)) * largo


def calcular_receta_acero(e: EntradaRecetaAcero) -> dict[str, Any]:
    """La receta del acero por pieza (castillo/pieza) o por metro lineal (ml), con totales para `cantidad`."""
    largo = _validar(e)
    d = e.drivers
    por_pieza = e.forma in ("castillo", "pieza")
    advertencias: list[str] = []
    sobrante_m = traslape_m = puntas_m = 0.0

    # Armex.
    armex: dict[str, Any] | None = None
    if e.armex is not None:
        lap = d.traslape_armex_cm / 100
        largo_pza = e.armex.largo_m
        if lap >= largo_pza:
            raise ErrorDeRecetaAcero("El traslape del armex no puede ser igual o mayor que la pieza.")
        corte: CorteDeVarilla | None = None
        if e.forma == "castillo":
            corte = corte_de(largo, largo_pza, lap, d.puntas_armex_cm / 100, d)
            ml = corte.total_m
            piezas = ml / largo_pza
            sobrante_m += corte.sobrante_m
            traslape_m += corte.traslapes_m
            puntas_m += corte.puntas_m
            if corte.excede_maximo or not corte.cubre_completo:
                advertencias.append(
                    "El armex no se pudo cubrir dentro del máximo de piezas por corte; revisa el alto."
                )
        else:
            piezas = largo / (largo_pza - lap)
            ml = piezas * largo_pza
            traslape_m += ml - largo
        kg = ml * e.armex.peso_kg_m if e.armex.peso_kg_m else None
        if kg is None:
            advertencias.append(
                f"El armex {e.armex.clave} no tiene peso por metro en el catálogo: los kg de acero quedan sin dato."
            )
        armex = {
            "clave": e.armex.clave,
            "largo_pieza_m": largo_pza,
            "ml": ml,
            "piezas_comerciales": piezas,
            "kg": kg,
            "traslape_m": lap,
            "puntas_m": d.puntas_armex_cm / 100 if corte else 0.0,
            "corte": _corte_a_dict(corte) if corte else None,
        }

    # Varillas longitudinales.
    f = 1 + d.desperdicio_acero_pct / 100
    varillas: list[dict[str, Any]] = []
    n_barras = 0
    kg_varillas = 0.0
    for g in e.varillas:
        v = g.varilla
        dm = diametro_de_varilla_m(v.numero)
        lap = d.traslape_varilla_diametros * dm
        puntas = (d.puntas_inferior_diametros + d.puntas_superior_diametros) * dm
        corte_v: CorteDeVarilla | None = None
        if por_pieza:
            corte_v = corte_de(largo, v.largo_m, lap, puntas, d)
            ml = g.cantidad * corte_v.total_m
            sobrante_m += g.cantidad * corte_v.sobrante_m
            traslape_m += g.cantidad * corte_v.traslapes_m
            puntas_m += g.cantidad * corte_v.puntas_m
            if corte_v.excede_maximo or not corte_v.cubre_completo:
                advertencias.append(
                    f"La varilla {v.clave} pasa de {d.max_piezas_corte} piezas por corte para cubrir "
                    f"{largo:.2f} m (más puntas)."
                )
        else:
            if lap >= v.largo_m:
                raise ErrorDeRecetaAcero("El traslape de la varilla no puede ser igual o mayor que la barra.")
            ml = g.cantidad * largo * v.largo_m / (v.largo_m - lap)
            traslape_m += ml - g.cantidad * largo
        ml *= f
        kg = ml * v.peso_kg_m if v.peso_kg_m else None
        if kg is None:
            advertencias.append(f"La varilla {v.clave} no tiene peso por metro: sus kg quedan sin dato.")
        else:
            kg_varillas += kg
        n_barras += g.cantidad
        varillas.append(
            {
                "clave": v.clave,
                "etiqueta": g.etiqueta,
                "numero": v.numero,
                "varillas": g.cantidad,
                "largo_pieza_m": v.largo_m,
                "diametro_m": dm,
                "traslape_m": lap,
                "puntas_m": puntas if por_pieza else 0.0,
                "ml": ml,
                "piezas_comerciales": ml / v.largo_m,
                "kg": kg,
                "corte": _corte_a_dict(corte_v) if corte_v else None,
            }
        )

    # Anillos por zonas.
    anillos: dict[str, Any] | None = None
    n_anillos = 0.0
    if e.varillas and e.anillos:
        rec = e.recubrimiento_cm / 100
        l_anillo = 2 * ((e.ancho_cm / 100 - 2 * rec) + (e.peralte_cm / 100 - 2 * rec)) * e.factor_anillo + e.gancho_cm / 100
        zonas_in = list(e.anillos)
        if e.forma == "ml":
            centro = next((z for z in zonas_in if z.len_cm is None), zonas_in[-1])
            zonas_in = [centro]
        extremos = 2 if e.forma == "pieza" else 1
        fijas = sum(z.len_cm / 100 * extremos for z in zonas_in if z.len_cm is not None)
        if por_pieza and fijas > largo + _EPS:
            advertencias.append("Las zonas de anillo fijas rebasan el largo de la pieza: no queda zona de centro.")
        resto = max(0.0, largo - fijas)
        zonas_out: list[dict[str, Any]] = []
        kg_anillos = 0.0
        for i, z in enumerate(zonas_in):
            lz = z.len_cm / 100 * extremos if z.len_cm is not None else resto
            sep = z.sep_cm / 100
            n = (_techo(lz / sep) + (1 if i == 0 else 0)) if por_pieza else lz / sep
            kg = n * l_anillo * z.peso_kg_m
            kg_anillos += kg
            n_anillos += n
            zonas_out.append(
                {"clave": z.clave, "len_cm": z.len_cm, "sep_cm": z.sep_cm, "largo_m": lz, "pza": n, "kg": kg}
            )
        anillos = {"largo_anillo_m": l_anillo, "pza": n_anillos, "kg": kg_anillos, "zonas": zonas_out}
    elif e.varillas and not e.anillos:
        advertencias.append("El armado de varillas no lleva anillos.")

    # Alambre de amarre.
    if e.alambre_kg_ml is not None:
        kg_alambre = e.alambre_kg_ml * largo
    elif e.armex is not None:
        kg_alambre = 0.0
    else:
        kg_alambre = n_barras * n_anillos * e.alambre_por_amarre_m * e.alambre_peso_kg_m

    # Cimbra.
    m2 = _cimbra_m2(e, largo)
    consumos = [
        {
            "clave": c.clave,
            "cantidad": (c.por_m2 * m2) if c.por_m2 is not None else (c.por_ml or 0.0) * largo,
        }
        for c in e.cimbra
    ]

    acero_kg = kg_varillas + (anillos["kg"] if anillos else 0.0) + ((armex or {}).get("kg") or 0.0)
    acero_completo = (armex is None or armex["kg"] is not None) and all(fila["kg"] is not None for fila in varillas)

    # Totales para `cantidad` (las piezas comerciales se redondean hacia arriba).
    q = e.cantidad
    totales: list[dict[str, Any]] = []
    if armex:
        totales.append(_total(armex["clave"], "pza", q * armex["piezas_comerciales"], True))
    por_clave: dict[str, float] = {}
    for fila in varillas:
        por_clave[fila["clave"]] = por_clave.get(fila["clave"], 0.0) + q * fila["piezas_comerciales"]
    totales.extend(_total(c, "pza", x, True) for c, x in por_clave.items())
    if anillos:
        for z in anillos["zonas"]:
            totales.append(_total(z["clave"] or "anillo", "kg", q * z["kg"], False))
    if kg_alambre > 0:
        totales.append(_total("alambre", "kg", q * kg_alambre, False))

    return {
        "forma": e.forma,
        "unidad": "ml" if e.forma == "ml" else "pza",
        "longitud_m": largo,
        "cantidad": q,
        "armex": armex,
        "varillas": varillas,
        "anillos": anillos,
        "alambre": {"kg": kg_alambre, "kg_por_ml": e.alambre_kg_ml},
        "cimbra": {"m2": m2, "lados": e.lados_cimbra, "consumos": consumos},
        "acero_kg": acero_kg,
        "acero_kg_completo": acero_completo,
        "desperdicio": {
            "sobrante_de_corte_m": sobrante_m,
            "traslape_m": traslape_m,
            "puntas_m": puntas_m,
            "desperdicio_acero_pct": d.desperdicio_acero_pct,
        },
        "totales": totales,
        "drivers": asdict(d),
        "advertencias": advertencias,
    }


def _total(clave: str, unidad: str, exacta: float, redondear: bool) -> dict[str, Any]:
    return {
        "clave": clave,
        "unidad": unidad,
        "cantidad_exacta": exacta,
        "cantidad_a_comprar": float(_techo(exacta)) if redondear else exacta,
    }
