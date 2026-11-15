"""«Confirmar cálculo → actualizar APU» y la conciliación en las dos direcciones (plan de elementos de muro, fase I; M-131).

El **APU manda**: las compras y la estimación se pagan con lo que dice el APU del concepto (concepto × coeficiente). El cálculo
del elemento (su receta puesta en insumos: piezas, mezcla, varilla, cimbra) es la **salida de material** que justifica esa
estimación. La tolerancia de ±3 % es **solo un aviso visual**, nunca bloquea.

- `planear` pone lado a lado el APU y el cálculo del elemento y dice, insumo por insumo, qué haría confirmar el cálculo: actualizar
  el renglón directo del APU, agregar el insumo si el APU no lo trae, o no tocar (el insumo viene dentro de un auxiliar, el APU
  trae un insumo que el elemento no calcula, o ya coincide). La mano de obra, el destajo y las herramientas no se tocan: el
  elemento no los calcula.
- `conciliar` multiplica por una cantidad de concepto (m², ml…) y compara el **estimado por APU** con la **salida del cálculo**: en
  cantidad y en importe, en las dos direcciones (lo estimado sin salida y la salida sin estimado).

Funciones puras, sin base de datos; no inventan precios: un insumo sin precio queda sin importe.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from obractrl.domain.cuantificacion.comparacion_con_catalogo import marca_de

__all__ = [
    "TOLERANCIA_DE_AVISO",
    "CambioDeApu",
    "LineaDelApu",
    "PlanDeActualizacion",
    "conciliar",
    "planear",
]

TOLERANCIA_DE_AVISO = 0.03
"""±3 %: solo un aviso visual (M-131)."""

_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class LineaDelApu:
    """Un insumo del APU de un concepto (los auxiliares ya expandidos hasta los insumos)."""

    clave: str
    cantidad: float
    """Lo que lleva el concepto de este insumo en total, con lo que viene dentro de sus auxiliares."""
    directa: float | None
    """Lo que está en renglones directos del concepto; `None` si el insumo solo llega por un auxiliar."""
    descripcion: str = ""
    unidad: str = ""
    costo: float | None = None
    es_mano_de_obra: bool = False


@dataclass(frozen=True, slots=True)
class CambioDeApu:
    """Un renglón directo del APU que confirmar el cálculo cambia o agrega."""

    clave: str
    accion: str  # actualizar | agregar
    antes: float | None
    despues: float


@dataclass(frozen=True, slots=True)
class PlanDeActualizacion:
    filas: list[dict[str, object]]
    cambios: list[CambioDeApu]
    avisos: list[str]

    @property
    def hay_cambios(self) -> bool:
        return bool(self.cambios)


def _distinto(a: float, b: float) -> bool:
    return abs(a - b) > max(_EPS, abs(a) * 1e-6)


def planear(
    salida: Mapping[str, float],
    apu: Sequence[LineaDelApu],
    *,
    insumos_existentes: Iterable[str] = (),
    descripciones: Mapping[str, str] | None = None,
) -> PlanDeActualizacion:
    """Lo que haría confirmar el cálculo. `salida` es el cálculo del elemento por unidad del concepto (`{clave: cantidad}`);
    `insumos_existentes` son las claves que existen en la base de insumos (un insumo que el APU no trae solo se agrega si existe)."""
    existentes = {c.upper() for c in insumos_existentes}
    descripciones = descripciones or {}
    del_apu = {x.clave.upper(): x for x in apu if not x.es_mano_de_obra}
    filas: list[dict[str, object]] = []
    cambios: list[CambioDeApu] = []
    avisos: list[str] = []
    for clave in [*del_apu, *(k.upper() for k in salida if k.upper() not in del_apu)]:
        linea = del_apu.get(clave)
        calculo = next((float(v) for k, v in salida.items() if k.upper() == clave), None)
        vigente = linea.cantidad if linea else None
        marca, dif = marca_de(vigente, calculo)
        accion, motivo = "sin_cambio", ""
        if calculo is None:
            accion, motivo = "solo_apu", "El elemento no calcula este insumo: el APU se queda como está."
        elif linea is None:
            if clave in existentes:
                accion = "agregar"
                cambios.append(CambioDeApu(clave, "agregar", None, calculo))
            else:
                accion, motivo = "sin_insumo", "El insumo no existe en la base: créalo antes de llevarlo al APU."
                avisos.append(f"{clave} no existe en la base de insumos y no se agrega al APU.")
        elif not _distinto(linea.cantidad, calculo):
            accion = "sin_cambio"
        elif linea.directa is None:
            accion, motivo = "en_auxiliar", "El insumo llega por un auxiliar: se cambia en el auxiliar, no en este concepto."
            avisos.append(f"{clave} viene dentro de un auxiliar del APU: no se modifica desde aquí.")
        else:
            nueva = linea.directa + (calculo - linea.cantidad)
            if nueva < -_EPS:
                accion, motivo = "en_auxiliar", "El ajuste dejaría el renglón directo negativo: se revisa a mano."
                avisos.append(f"{clave}: el ajuste dejaría el renglón del APU en negativo; no se modifica.")
            else:
                accion = "actualizar"
                cambios.append(CambioDeApu(clave, "actualizar", linea.directa, max(nueva, 0.0)))
        d = linea.descripcion if linea and linea.descripcion else descripciones.get(clave, "")
        filas.append(
            {
                "clave": clave,
                "descripcion": d,
                "unidad": linea.unidad if linea else "",
                "apu": vigente,
                "calculo": calculo,
                "diferencia_pct": round(dif * 100, 2) if dif is not None else None,
                "marca": marca,
                "accion": accion,
                "motivo": motivo,
            }
        )
    return PlanDeActualizacion(filas=filas, cambios=cambios, avisos=list(dict.fromkeys(avisos)))


def conciliar(
    salida: Mapping[str, float],
    apu: Sequence[LineaDelApu],
    *,
    cantidad: float,
    precios: Mapping[str, float | None] | None = None,
    descripciones: Mapping[str, str] | None = None,
    tolerancia: float = TOLERANCIA_DE_AVISO,
) -> dict[str, object]:
    """Estimado por APU (cantidad × coeficiente) contra la salida del cálculo del elemento (cantidad × lo que calcula), insumo por
    insumo y en las dos direcciones. Cada fila dice si el estimado **se justifica** con la salida y si la salida **se justifica**
    con el estimado (dentro de la tolerancia: solo un aviso). El importe usa el costo del APU o, si el insumo no está en él, el
    precio de la base; sin precio queda sin importe (no se inventa)."""
    precios = {k.upper(): v for k, v in (precios or {}).items()}
    descripciones = descripciones or {}
    del_apu = {x.clave.upper(): x for x in apu if not x.es_mano_de_obra}
    salida_n = {k.upper(): float(v) for k, v in salida.items()}
    filas: list[dict[str, object]] = []
    total_apu = Decimal(0)
    total_salida = Decimal(0)
    sin_precio = False
    for clave in [*del_apu, *(k for k in salida_n if k not in del_apu)]:
        linea = del_apu.get(clave)
        coef_apu = linea.cantidad if linea else None
        coef_salida = salida_n.get(clave)
        estimado = None if coef_apu is None else coef_apu * cantidad
        calculado = None if coef_salida is None else coef_salida * cantidad
        costo = linea.costo if linea is not None and linea.costo is not None else precios.get(clave)
        marca, dif = marca_de(coef_apu, coef_salida)
        if estimado is None:
            sentido = "salida_sin_estimado"
        elif calculado is None:
            sentido = "estimado_sin_salida"
        else:
            sentido = "se_justifican" if dif is not None and abs(dif) <= tolerancia + _EPS else "difieren"
        imp_apu = None if estimado is None or costo is None else estimado * costo
        imp_salida = None if calculado is None or costo is None else calculado * costo
        if costo is None:
            sin_precio = True
        if imp_apu is not None:
            total_apu += Decimal(str(imp_apu))
        if imp_salida is not None:
            total_salida += Decimal(str(imp_salida))
        filas.append(
            {
                "clave": clave,
                "descripcion": (linea.descripcion if linea and linea.descripcion else descripciones.get(clave, "")),
                "unidad": linea.unidad if linea else "",
                "estimado": estimado,
                "salida": calculado,
                "diferencia_cantidad": None if estimado is None or calculado is None else calculado - estimado,
                "diferencia_pct": round(dif * 100, 2) if dif is not None else None,
                "costo": costo,
                "importe_apu": imp_apu,
                "importe_salida": imp_salida,
                "diferencia_importe": None if imp_apu is None or imp_salida is None else imp_salida - imp_apu,
                "marca": marca,
                "sentido": sentido,
                "avisa": sentido == "difieren",
            }
        )
    return {
        "cantidad": cantidad,
        "manda": "apu",
        "tolerancia_pct": tolerancia * 100,
        "filas": filas,
        "importe_apu": float(total_apu),
        "importe_salida": float(total_salida),
        "sin_precio": sin_precio,
        "resumen": {
            s: sum(1 for f in filas if f["sentido"] == s)
            for s in ("se_justifican", "difieren", "estimado_sin_salida", "salida_sin_estimado")
        },
    }
