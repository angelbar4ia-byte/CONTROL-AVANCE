"""Cargador de presupuesto jerárquico: árbol del prototipo (extensión propia).

Spec §7.4 (árbol WBS del prototipo) · §7.3 (APU) · §3.3 (la CLAVE manda) ·
§10.3 (bandeja de pendientes) · §10.8 (versionado).

A diferencia de `materiales.py`/`cpu.py`, este archivo no está descrito por
el §10.6 — es el "presupuesto jerárquico" que el módulo de cargadores lista
desde siempre como pendiente. Cada fila es un nodo de un árbol reconstruido
por `CLAVE PADRE → CLAVE HIJO` entre filas consecutivas (DFS pre-order, sin
bloques en blanco): `PROTOTIPO` → `NIVEL DE CONSTRUCCION` →
`ETAPA DE CONSTRUCCIÓN` → `CONCEPTO`/`CONCEPTO AUXILIAR` →
`MATERIAL`/`DESTAJO`/`SUBCONTRATO`.

A diferencia de `agrupar_conceptos` (`cpu.py`), que mantiene un solo "bloque
abierto" de un nivel, aquí hace falta reconstruir un árbol real: la clave de
un nodo (`NIV-00001`, `ECO-00001`...) **no es única en el archivo** — se
repite idéntica en cada prototipo, así que el mapa de resolución de padres
se reinicia en cada fila `PROTOTIPO` (§construir_arboles).

Módulo puro (§12.11).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.reporte import (
    ErrorDeFila,
    ErrorEnFila,
    PendientePropuesto,
    TipoPendiente,
)
from obractrl.domain.shared.normalizacion import (
    ValorNoConvertible,
    a_decimal,
    a_entero,
    esta_vacio,
    normalizar,
    texto_limpio,
)
from obractrl.domain.shared.valores import Clave

__all__ = [
    "ArbolPrototipoCargado",
    "NodoLeido",
    "TipoNodoPresupuesto",
    "construir_arboles",
    "es_etapa_con_componentes_directos",
]


class TipoNodoPresupuesto(StrEnum):
    """Valor de la columna TIPO, ya normalizado (§8.6: minúsculas, sin
    acentos, espacios colapsados) — así "ETAPA DE CONSTRUCCIÓN " y
    "Etapa de Construccion" resuelven igual."""

    PROTOTIPO = "prototipo"
    NIVEL = "nivel de construccion"
    ETAPA = "etapa de construccion"
    CONCEPTO = "concepto"
    CONCEPTO_AUXILIAR = "concepto auxiliar"
    MATERIAL = "material"
    DESTAJO = "destajo"
    SUBCONTRATO = "subcontrato"


_TIPOS_VALIDOS: dict[str, TipoNodoPresupuesto] = {t.value: t for t in TipoNodoPresupuesto}

_TIPOS_CON_HIJOS = frozenset(
    {
        TipoNodoPresupuesto.NIVEL,
        TipoNodoPresupuesto.ETAPA,
        TipoNodoPresupuesto.CONCEPTO,
        TipoNodoPresupuesto.CONCEPTO_AUXILIAR,
    }
)
"""Tipos que pueden tener hijos. `MATERIAL`/`DESTAJO`/`SUBCONTRATO` son
siempre hoja — no se registran como padre posible, para que una fila mal
clavada como componente no "adopte" filas siguientes por error."""

_TIPOS_COMPONENTE = frozenset(
    {
        TipoNodoPresupuesto.MATERIAL,
        TipoNodoPresupuesto.DESTAJO,
        TipoNodoPresupuesto.SUBCONTRATO,
    }
)


@dataclass(frozen=True, slots=True)
class NodoLeido:
    """Una fila válida del árbol."""

    tipo: TipoNodoPresupuesto
    clave: str
    clave_padre: str | None
    descripcion: str
    unidad: str | None = None
    cantidad: Decimal | None = None
    precio_unitario: Decimal | None = None
    importe: Decimal | None = None
    indice: int | None = None
    wbs: str | None = None
    """Columna WBS del archivo, si la trae (opcional, §7.4). Solo se usa
    para comparar contra `_siguiente_wbs` y avisar si no coincide —nunca
    para la identidad del nodo, esa la da CLAVE PADRE → CLAVE HIJO."""

    fila: int = 0
    """Renglón del archivo, para que un error de fila ligue al origen."""


@dataclass(frozen=True, slots=True)
class ArbolPrototipoCargado:
    """El árbol completo de un prototipo: su fila `PROTOTIPO` y todo lo que
    cuelga de ella."""

    clave_prototipo: str
    raiz: NodoLeido
    hijos: dict[str, tuple[NodoLeido, ...]]
    """Clave del padre → sus hijos directos, en el orden del archivo."""

    nodos: dict[str, NodoLeido]
    """Clave → nodo. Atajo de consulta para el aplicador; no reemplaza a
    `hijos` para recorrer el árbol."""

    @property
    def llave(self) -> str:
        """Identidad para dedup: la clave del prototipo (§3.3)."""
        return self.clave_prototipo


def es_etapa_con_componentes_directos(arbol: ArbolPrototipoCargado, nodo: NodoLeido) -> bool:
    """¿Esta etapa cuelga materiales/destajo/subcontrato directo, sin un
    `CONCEPTO`/`CONCEPTO AUXILIAR` de por medio?

    Cuando sí, la etapa misma se trata como concepto: se identifica/crea un
    `concepto` con su propia clave y esas filas arman su APU (decisión de
    negocio confirmada contra el archivo real, ej. `ECO-00033 "PLANTA
    BAJA"`). Decidir esto es del aplicador —quien conoce el catálogo—, no
    del parseo; esta función solo describe la forma del árbol leído.
    """
    hijos = arbol.hijos.get(nodo.clave, ())
    if nodo.tipo is not TipoNodoPresupuesto.ETAPA or not hijos:
        return False
    return all(h.tipo in _TIPOS_COMPONENTE for h in hijos)


def _clave_obligatoria(celda: object, *, columna: str) -> str:
    if esta_vacio(celda):
        raise ErrorEnFila(
            f"{columna}: la fila no trae clave y la clave es la identidad "
            f"del nodo (§3.3).",
            columna=columna,
        )
    try:
        return str(Clave(str(celda)))
    except ValueError as exc:
        raise ErrorEnFila(str(exc), columna=columna, valor=celda) from exc


def _clave_opcional(celda: object, *, columna: str) -> str | None:
    if esta_vacio(celda):
        return None
    try:
        return str(Clave(str(celda)))
    except ValueError as exc:
        raise ErrorEnFila(str(exc), columna=columna, valor=celda) from exc


def _decimal_opcional(celda: object, *, columna: str) -> Decimal | None:
    if esta_vacio(celda):
        return None
    try:
        valor = a_decimal(celda, campo=columna)
    except ValorNoConvertible as exc:
        raise ErrorEnFila(str(exc), columna=columna, valor=celda) from exc
    if valor < 0:
        raise ErrorEnFila(
            f"{columna}: no puede ser negativo ({valor}).", columna=columna, valor=celda
        )
    return valor


def _entero_opcional(celda: object, *, columna: str) -> int | None:
    if esta_vacio(celda):
        return None
    try:
        return a_entero(celda, campo=columna)
    except ValorNoConvertible as exc:
        raise ErrorEnFila(str(exc), columna=columna, valor=celda) from exc


def _leer_nodo(
    fila: Sequence[object], mapa: MapaColumnas, numero: int, tipo: TipoNodoPresupuesto
) -> NodoLeido:
    clave = _clave_obligatoria(mapa.valor(fila, "clave_hijo"), columna="clave_hijo")

    clave_padre = _clave_opcional(mapa.valor(fila, "clave_padre"), columna="clave_padre")
    if tipo is not TipoNodoPresupuesto.PROTOTIPO and clave_padre is None:
        raise ErrorEnFila(
            "clave_padre: toda fila que no sea PROTOTIPO necesita padre (§árbol).",
            columna="clave_padre",
        )

    descripcion = texto_limpio(mapa.valor(fila, "descripcion"))
    if not descripcion:
        raise ErrorEnFila(
            "descripcion: es obligatoria, es lo único legible de un nodo sin catálogo.",
            columna="descripcion",
        )

    return NodoLeido(
        tipo=tipo,
        clave=clave,
        clave_padre=clave_padre,
        descripcion=descripcion,
        unidad=texto_limpio(mapa.valor(fila, "unidad")) or None,
        cantidad=_decimal_opcional(mapa.valor(fila, "cantidad"), columna="cantidad"),
        precio_unitario=_decimal_opcional(mapa.valor(fila, "precio_unitario"), columna="precio_unitario"),
        importe=_decimal_opcional(mapa.valor(fila, "importe"), columna="importe"),
        indice=_entero_opcional(mapa.valor(fila, "indice"), columna="indice"),
        wbs=texto_limpio(mapa.valor(fila, "wbs")) or None,
        fila=numero,
    )


_NIVEL_WBS: dict[TipoNodoPresupuesto, int] = {
    TipoNodoPresupuesto.PROTOTIPO: 1,
    TipoNodoPresupuesto.NIVEL: 2,
    TipoNodoPresupuesto.ETAPA: 3,
    TipoNodoPresupuesto.CONCEPTO: 4,
    TipoNodoPresupuesto.CONCEPTO_AUXILIAR: 4,
    TipoNodoPresupuesto.MATERIAL: 5,
    TipoNodoPresupuesto.DESTAJO: 5,
    TipoNodoPresupuesto.SUBCONTRATO: 5,
}
"""Nivel fijo de cada TIPO en la numeración WBS (§7.4) — no es la
profundidad del árbol: una etapa sin concepto intermedio cuelga MATERIAL
directo y ese material igual cae en el nivel 5, con el 4 en 0. Es la misma
numeración de esquema que ya trae el archivo real: verificada fila por
fila contra un archivo de 7 prototipos/8014 filas — coincide en todas
salvo 2, y esas 2 son un defecto del propio archivo (segmento de ETAPA
vacío), no de este cálculo."""


def _siguiente_wbs(contadores: list[int], tipo: TipoNodoPresupuesto) -> str:
    """WBS que le toca a esta fila, dado su TIPO: sube el contador de su
    nivel y reinicia los más profundos (§7.4). Un solo `contadores` para
    todo el archivo —no por prototipo— porque el segmento de PROTOTIPO
    (nivel 1) es justamente el que numera de un prototipo al siguiente."""
    nivel = _NIVEL_WBS[tipo]
    contadores[nivel - 1] += 1
    for indice in range(nivel, 5):
        contadores[indice] = 0
    return ".".join(str(c) for c in contadores)


def construir_arboles(
    filas: Sequence[tuple[int, Sequence[object]]], mapa: MapaColumnas
) -> tuple[
    tuple[ArbolPrototipoCargado, ...],
    tuple[ErrorDeFila, ...],
    tuple[PendientePropuesto, ...],
    int,
]:
    """Filas planas → un árbol por prototipo (§7.4).

    Devuelve ``(arboles, errores, pendientes, omitidos)``, mismo contrato que
    `cpu.agrupar_conceptos`:

    - Una fila mala no tumba el árbol ni el archivo (§9.3): se reporta y se
      sigue.
    - Un `TIPO` fuera del contrato va a la bandeja como `fila_no_parseada`
      (§10.3).
    - Una fila cuyo `clave_padre` no corresponde a ningún nodo visto **en
      este mismo prototipo** es error de fila: sin padre no hay a qué
      colgarla.
    - Prototipo repetido en el archivo: gana el último árbol, el anterior
      cuenta como omitido.
    """
    arboles: dict[str, ArbolPrototipoCargado] = {}
    errores: list[ErrorDeFila] = []
    pendientes: list[PendientePropuesto] = []
    omitidos = 0

    raiz: NodoLeido | None = None
    hijos: dict[str, list[NodoLeido]] = {}
    ultimo_por_clave: dict[str, NodoLeido] = {}
    contadores_wbs = [0, 0, 0, 0, 0]

    def cerrar() -> None:
        nonlocal raiz, hijos, ultimo_por_clave, omitidos
        if raiz is None:
            return
        arbol = ArbolPrototipoCargado(
            clave_prototipo=raiz.clave,
            raiz=raiz,
            hijos={clave: tuple(lista) for clave, lista in hijos.items()},
            nodos=dict(ultimo_por_clave),
        )
        if arbol.llave in arboles:
            omitidos += 1
        arboles[arbol.llave] = arbol
        raiz = None
        hijos = {}
        ultimo_por_clave = {}

    for numero, fila in filas:
        crudo_tipo = mapa.valor(fila, "tipo")
        texto_tipo = normalizar(crudo_tipo)
        tipo = _TIPOS_VALIDOS.get(texto_tipo)

        if tipo is None:
            errores.append(
                ErrorDeFila(
                    fila=numero,
                    columna="tipo",
                    valor=texto_limpio(crudo_tipo),
                    motivo=(
                        f"tipo: {texto_limpio(crudo_tipo)!r} no es uno de los "
                        f"valores esperados ({', '.join(sorted(_TIPOS_VALIDOS))})."
                    ),
                )
            )
            pendientes.append(
                PendientePropuesto(
                    tipo=TipoPendiente.FILA_NO_PARSEADA,
                    entidad="prototipo_nodo",
                    valor_origen=texto_limpio(crudo_tipo),
                    propuesta={"opciones": sorted(_TIPOS_VALIDOS)},
                    origen_ref=f"fila {numero}",
                )
            )
            continue

        try:
            nodo = _leer_nodo(fila, mapa, numero, tipo)
        except ErrorEnFila as exc:
            errores.append(exc.con_fila(numero))
            continue

        wbs_calculado = _siguiente_wbs(contadores_wbs, tipo)
        if nodo.wbs and nodo.wbs != wbs_calculado:
            # No crítico (§10.3): la fila se procesa igual, esto solo avisa
            # para que alguien decida si carga o corrige el archivo antes.
            pendientes.append(
                PendientePropuesto(
                    tipo=TipoPendiente.WBS_INCONSISTENTE,
                    entidad="prototipo_nodo",
                    valor_origen=nodo.wbs,
                    propuesta={"esperado": wbs_calculado},
                    origen_ref=f"fila {numero}",
                )
            )

        if tipo is TipoNodoPresupuesto.PROTOTIPO:
            cerrar()
            raiz = nodo
            ultimo_por_clave[nodo.clave] = nodo
            continue

        if raiz is None:
            errores.append(
                ErrorDeFila(
                    fila=numero,
                    columna="tipo",
                    valor=str(tipo),
                    motivo=(
                        "Fila sin una fila TIPO=PROTOTIPO previa que la "
                        "encabece: no hay árbol al cual pertenece."
                    ),
                )
            )
            continue

        padre = ultimo_por_clave.get(nodo.clave_padre or "")
        if padre is None:
            errores.append(
                ErrorDeFila(
                    fila=numero,
                    columna="clave_padre",
                    valor=nodo.clave_padre,
                    motivo=(
                        f"clave_padre: {nodo.clave_padre!r} no corresponde a "
                        f"ninguna fila anterior de este prototipo."
                    ),
                )
            )
            continue

        hijos.setdefault(nodo.clave_padre or "", []).append(nodo)
        if tipo in _TIPOS_CON_HIJOS:
            ultimo_por_clave[nodo.clave] = nodo

    cerrar()
    return tuple(arboles.values()), tuple(errores), tuple(pendientes), omitidos
