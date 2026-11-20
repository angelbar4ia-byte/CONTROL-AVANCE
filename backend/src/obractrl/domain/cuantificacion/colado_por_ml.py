"""Colado y cimbra por metro lineal de las trabes, contratrabes y nervaduras, y su destajo por ml (decisión D8, Q51 y Q52 ejecutadas en la fase 2 de la losa).

Hasta la 3B el camino estaba solo **contemplado**: el catálogo paga el concreto y la cimbra de una trabe dentro de la losa, por m², y no
trae destajo por ml. El usuario decidió (D8, 2026-11-19) que el concepto de colado y cimbra por ml y el destajo por ml de las trabes se
registran **con la fase de la losa**. Aquí se construye como **propuesta**:

- Cada trabe, contratrabe y nervaduras de la biblioteca (36 elementos) tiene su **concepto nuevo de colado y cimbra por ml**, con la
  **clave provisional** del mockup (``EJ-701``, ``EJ-703``… una por elemento; ver ``CLAVES_PROVISIONALES``). Toma el concreto y, si el
  elemento lleva cimbra, la cimbra (la nervadura no: el casetón la forma). El acero sigue pagándose con su auxiliar del catálogo (AUX-xxxxx).
- Es una **propuesta** (clase ``concepto_nuevo`` de ``propuesta_de_estructura``): Costos o Control de obra la proponen y solo Control de
  obra la autoriza. **No se edita el catálogo, no hay precio y no hay destajo con importe**: el destajo por ml se registra como
  *placeholder* (clave provisional ``<concepto>-MO``, unidad ml, importe ``null``) que Costos define después. Sin destajo la mano de obra
  del concepto queda **sin mano de obra** y así se documenta (regla del usuario: no se inventan destajos).
- Se usa cuando la trabe va **suelta** (trabe de liga, contratrabe corrida) o cuando la zona de la losa lo decide (``pago = propio`` en la
  matriz de la losa): entonces el concreto y la cimbra del elemento los paga este concepto y **no** el concepto de la losa por m². Con
  ``pago = en_la_losa`` (valor conservador, lo que ya hace el catálogo) los paga la losa y este concepto no entra: no hay doble conteo.

Las claves provisionales del mockup repiten números entre familias (la ``EJ-761`` de T-16-35x30 y la de la columna C-1, la ``EJ-771`` de
T-22-15x25 y la del castillo EST-02130): aquí solo se registran las de esta familia y, al proponer, se rechaza una clave que ya esté propuesta
para otro elemento. Función pura, sin base de datos.
"""

from __future__ import annotations

from typing import Any

from obractrl.domain.cuantificacion.elementos_lineales import (
    TIPO_LINEAL,
    EntradaElementoEstructural,
    calcular_elemento,
    elemento_estructural,
)

__all__ = [
    "CLAVES_PROVISIONALES",
    "MOTIVOS_DEL_CONCEPTO",
    "clave_provisional_de_colado",
    "concepto_de_colado",
    "concepto_nuevo_de_colado",
]

CLAVES_PROVISIONALES: dict[str, str] = {
    "T-3-15x25": "EJ-701", "T-1-15x25": "EJ-703", "T-1-15x15": "EJ-705", "T-2-20x30": "EJ-707", "T-4-25x25": "EJ-709",
    "T-2-20x25": "EJ-711", "N1-10x30": "EJ-713", "N-1-12x25": "EJ-715", "N-2-10x25": "EJ-717", "N-1-10x25": "EJ-719",
    "N-2-12x25": "EJ-721", "T-5-12x30": "EJ-723", "CT1-15x25": "EJ-725", "CT1-20x30": "EJ-727", "CT2-15x20": "EJ-729",
    "CT3-25x30": "EJ-731", "CT3-30x30": "EJ-733", "CT4-30x30": "EJ-735", "CT4-25x30": "EJ-737", "T-1-15x20": "EJ-739",
    "T-2-12x20": "EJ-741", "T-3B-12x15": "EJ-743", "T-10-15x30": "EJ-745", "T-11-15x25": "EJ-747", "T-12-15x25": "EJ-749",
    "T-13-15x30": "EJ-751", "T-13p-20x30": "EJ-753", "T-14-17x60": "EJ-755", "T-14-17x70": "EJ-757", "T-15-35x30": "EJ-759",
    "T-16-35x30": "EJ-761", "T-17-12x12": "EJ-763", "T-18-35x25": "EJ-765", "T-21-15x20": "EJ-767", "T-22p-12x20": "EJ-769",
    "T-22-15x25": "EJ-771",
}
"""Elemento → clave provisional de su concepto de colado y cimbra por ml (mockup, ``conceptos_del_elemento``). Provisional: Control de obra la
confirma al autorizar; no choca con ninguna clave del catálogo (se comprueba en las pruebas contra los CSV de opus)."""

MOTIVOS_DEL_CONCEPTO: tuple[str, ...] = (
    "D8 (Q51): el catálogo paga el concreto y la cimbra de la trabe dentro de la losa, por m²; este concepto nuevo la paga por metro lineal "
    "cuando la trabe va suelta o la zona de la losa lo decide.",
    "D8 (Q52): el catálogo de trabajos no trae destajo por ml para trabes, contratrabes ni nervaduras. El destajo por ml se registra sin "
    "importe, pendiente de definir por Costos; el concepto queda sin mano de obra mientras tanto. Sin precio.",
    "Clave provisional: pendiente de autorizar por Control de obra.",
)


def clave_provisional_de_colado(clave: str) -> str | None:
    """La clave provisional del concepto de colado y cimbra por ml del elemento, o ``None`` si no es una trabe, contratrabe o nervadura."""
    return CLAVES_PROVISIONALES.get(clave)


def _por_ml(clave: str) -> dict[str, Any]:
    """Lo que el elemento gasta de concreto y cimbra por metro lineal, con el desperdicio de partida del cálculo."""
    r = calcular_elemento(EntradaElementoEstructural(clave=clave, modo="ml"))
    return {f["clave"]: round(float(f["por_unidad"]), 6) for f in r["insumos"] if f["parte"] in ("concreto", "cimbra")}


def concepto_de_colado(clave: str, *, con_insumos: bool = True) -> dict[str, Any] | None:
    """El concepto de colado y cimbra por ml de un elemento (`None` si no le toca): clave provisional, descripción, unidad, qué toma, los
    insumos por ml y el destajo por ml **sin importe**. No crea nada. ``con_insumos=False`` omite el cálculo de los insumos (el cálculo del propio
    elemento llama a esta función para mostrar el camino y no puede volver a calcularse a sí mismo)."""
    e = elemento_estructural(clave)
    provisional = CLAVES_PROVISIONALES.get(clave)
    if e is None or provisional is None or e["tipo"] != TIPO_LINEAL:
        return None
    con_cimbra = bool(e["lados"])
    nombre = str(e["nombre"]).rstrip(".")
    descripcion = f"Colado y cimbra de {nombre}" if con_cimbra else f"Colado de {nombre}"
    return {
        "elemento_clave": clave,
        "clave": provisional,
        "descripcion": descripcion,
        "unidad": "ml",
        "toma": {"concreto": True, "cimbra": con_cimbra},
        "insumos_por_ml": _por_ml(clave) if con_insumos else {},
        "acero": {"clave": e["catalogo"][0]["clave"], "descripcion": e["catalogo"][0]["descripcion"], "unidad": "ml"},
        "destajo_por_ml": {
            "clave_provisional": f"{provisional}-MO",
            "descripcion": f"MO de {'colado y cimbrado' if con_cimbra else 'colado'} de {nombre}, por ml",
            "unidad": "ml",
            "importe": None,
            "estado": "por_definir",
        },
        "clave_provisional": True,
    }


def concepto_nuevo_de_colado(clave: str) -> dict[str, Any] | None:
    """La propuesta de concepto nuevo (clase ``concepto_nuevo`` de ``propuesta_de_estructura``) del colado y cimbra por ml del elemento."""
    c = concepto_de_colado(clave)
    if c is None:
        return None
    return {
        "elemento_clave": clave,
        "concepto_clave": c["clave"],
        "clase": "concepto_nuevo",
        "resumen": (
            f"Concepto nuevo {c['clave']} (clave provisional): {c['descripcion']}, por metro lineal; "
            f"destajo por ml {c['destajo_por_ml']['clave_provisional']} sin importe, sin precio"
        ),
        "detalle": {
            "descripcion": c["descripcion"],
            "unidad": "ml",
            "clave_provisional": True,
            "toma": c["toma"],
            "insumos": c["insumos_por_ml"],
            "destajo_por_ml": c["destajo_por_ml"],
            "motivos": list(MOTIVOS_DEL_CONCEPTO),
            "cambios": [],
        },
    }
