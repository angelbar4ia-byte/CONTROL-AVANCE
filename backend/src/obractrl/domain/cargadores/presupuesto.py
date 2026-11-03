"""Cargador de presupuesto jerárquico: árbol del prototipo (extensión propia).

Spec §7.4 (árbol WBS del prototipo) · §7.3 (APU) · §3.3 (la CLAVE manda) ·
§10.3 (bandeja de pendientes) · §10.8 (versionado).

A diferencia de `materiales.py`/`cpu.py`, este archivo no está descrito por
el §10.6 — es el "presupuesto jerárquico" que el módulo de cargadores lista
desde siempre como pendiente. Cada fila es un nodo de un árbol, y la
identidad padre-hijo sale de una de **dos** columnas, nunca las dos juntas
en el mismo archivo (§cabeceras.PRESUPUESTO):

- **`clave_padre` → `clave_hijo`** (archivo hecho a mano, formato
  histórico de este cargador): DFS pre-order, sin bloques en blanco — el
  padre de una fila es la última fila vista con esa clave, dentro del
  mismo prototipo.
- **`nivel` + posición** (árbol **nativo** del exportador de OPUS, que no
  trae `clave_padre` en absoluto): el padre sale de una pila de
  posiciones — la fila más cercana hacia atrás con `nivel` menor que el
  de la fila actual. `Indice` no arma nada aquí: es solo la suma de
  control entre hermanos (§construir_arboles).

A diferencia de `agrupar_conceptos` (`cpu.py`), que mantiene un solo "bloque
abierto" de un nivel, aquí hace falta reconstruir un árbol real: la clave de
un nodo (`NIV-00001`, `ECO-00001`...) **no es única en el archivo** — se
repite idéntica en cada prototipo, así que el mapa de resolución de padres
se reinicia en cada fila `PROTOTIPO` (§construir_arboles). Tampoco es única
DENTRO de un prototipo: la misma clave de `CONCEPTO` puede colgar de dos
`ETAPA` distintas del mismo prototipo (verificado contra el archivo real).
Por eso `hijos` se indexa por la fila del padre, no por su clave — dos
ocurrencias de la misma clave son dos padres distintos, cada uno con su
propia lista de hijos (§construir_arboles).

Módulo puro (§12.11).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from obractrl.domain.cargadores.cabeceras import ErrorDeCabecera, MapaColumnas
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
    "nombre_y_m2_del_prototipo",
]


_M2_AL_FINAL = re.compile(r"\s*\(\s*([\d.,]+)\s*m\s*2\s*\)\s*$", re.IGNORECASE)


def nombre_y_m2_del_prototipo(descripcion: str) -> tuple[str, Decimal | None]:
    """Nombre limpio y m² de un prototipo a partir de la descripción de su
    fila `Capítulo` (`CATALOGOS.md` §1: «ZAFIRO 1.0 (172 M2)»).

    El archivo no trae el nombre ni los m² en columnas propias: vienen en el
    texto. El nombre queda sin el «(172 M2)» y con solo la primera letra en
    mayúscula («Zafiro 1.0», «Diamante sin chimenea»); los m², si el texto
    los trae y son mayores que cero. D-614.
    """
    texto = " ".join(descripcion.split())
    m2: Decimal | None = None
    coincidencia = _M2_AL_FINAL.search(texto)
    if coincidencia is not None:
        try:
            valor = Decimal(coincidencia.group(1).replace(",", ""))
        except InvalidOperation:
            valor = None
        m2 = valor if valor is not None and valor > 0 else None
        texto = texto[: coincidencia.start()].strip()
    return (texto.capitalize() if texto else " ".join(descripcion.split())), m2


class TipoNodoPresupuesto(StrEnum):
    """Valor de la columna TIPO, ya normalizado (§8.6: minúsculas, sin
    acentos, espacios colapsados) — así "ETAPA DE CONSTRUCCIÓN " y
    "Etapa de Construccion" resuelven igual.

    `AGRUPADOR` es el único miembro cuyo valor coincide, tal cual, con el
    texto que trae el exportador de OPUS ("Nivel 3" normalizado): los
    demás vienen del archivo de prueba hecho a mano y el exportador los
    nombra distinto (`Capítulo`, `Subcapítulo`, `Nivel 2`...) — por eso
    `_ALIAS_TIPO_RENGLON`, más abajo, traduce ese vocabulario aparte.
    """

    PROTOTIPO = "prototipo"
    NIVEL = "nivel de construccion"
    ETAPA = "etapa de construccion"
    CONCEPTO = "concepto"
    CONCEPTO_AUXILIAR = "concepto auxiliar"
    MATERIAL = "material"
    DESTAJO = "destajo"
    SUBCONTRATO = "subcontrato"
    AGRUPADOR = "nivel 3"
    """Nodo agrupador del árbol nativo de OPUS (migración 0051, `ClaseNodo.
    AGRUPADOR`): no es un concepto de catálogo —sus hijos son `CONCEPTO`
    reales, con clave propia, nunca la suya— así que recursa igual que
    `NIVEL`/`ETAPA` en vez de ser hoja como `CONCEPTO`/`CONCEPTO_AUXILIAR`
    (ver `_TIPOS_CON_HIJOS` y `aplicar_carga.AplicadorPresupuesto`)."""


_TIPOS_VALIDOS: dict[str, TipoNodoPresupuesto] = {t.value: t for t in TipoNodoPresupuesto}

_ALIAS_TIPO_RENGLON: dict[str, TipoNodoPresupuesto] = {
    # Vocabulario literal de la columna TIPO del exportador nativo de OPUS
    # (verificado contra `CATALOGO_DE_PRESUPUESTO.csv`, 3231 filas): no usa
    # las mismas palabras que el valor canónico del enum, que es el que
    # escribe el archivo de prueba hecho a mano. "concepto" y "nivel 3" ya
    # coinciden tal cual con `CONCEPTO`/`AGRUPADOR` arriba y no hacen falta
    # aquí.
    "capitulo": TipoNodoPresupuesto.PROTOTIPO,
    "subcapitulo": TipoNodoPresupuesto.NIVEL,
    "nivel 2": TipoNodoPresupuesto.ETAPA,
}

_TODOS_LOS_TIPOS_RECONOCIDOS = sorted(set(_TIPOS_VALIDOS) | set(_ALIAS_TIPO_RENGLON))


def _resolver_tipo(texto: str) -> TipoNodoPresupuesto | None:
    """Texto ya normalizado de la columna TIPO → tipo de nodo, aceptando
    los dos vocabularios que trae el §10.6 de este cargador (ver
    `TipoNodoPresupuesto`/`_ALIAS_TIPO_RENGLON`)."""
    return _TIPOS_VALIDOS.get(texto) or _ALIAS_TIPO_RENGLON.get(texto)


_TIPOS_CON_HIJOS = frozenset(
    {
        TipoNodoPresupuesto.NIVEL,
        TipoNodoPresupuesto.ETAPA,
        TipoNodoPresupuesto.AGRUPADOR,
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
    nivel: int | None = None
    """`NIVEL` declarado en la fila (columna canónica `nivel`,
    §cabeceras.PRESUPUESTO). Solo lo trae el árbol nativo de OPUS, que no
    tiene `clave_padre`: junto con la posición en el archivo es lo único
    que arma la jerarquía en ese formato (§construir_arboles). `None` en
    el formato histórico (con `clave_padre` explícita), que no trae esta
    columna."""
    wbs: str | None = None
    """Columna WBS del archivo, si la trae (opcional, §7.4). Solo se usa
    para comparar contra `_siguiente_wbs` y avisar si no coincide —nunca
    para la identidad del nodo, esa la da `clave_padre` o `nivel`+posición."""

    fila: int = 0
    """Renglón del archivo, para que un error de fila ligue al origen."""

    es_hueco: bool = False
    """Hueco de numeración del exportador nativo de OPUS (`_leer_nodo`):
    sin clave, sin descripción y sin importe propio. `construir_arboles`
    lo descarta en silencio —mismo criterio que la referencia
    (`cerebro/backend/core/importacion_opus.py::leer_presupuesto`)— salvo
    que algo con clave real cuelgue debajo, caso en el que sí se queda
    (ver `tiene_clave_debajo` en `construir_arboles`)."""


@dataclass(frozen=True, slots=True)
class ArbolPrototipoCargado:
    """El árbol completo de un prototipo: su fila `PROTOTIPO` y todo lo que
    cuelga de ella."""

    clave_prototipo: str
    raiz: NodoLeido
    hijos: dict[int, tuple[NodoLeido, ...]]
    """`fila` del padre → sus hijos directos, en el orden del archivo.

    Por fila del padre y no por su clave: la misma clave (`ECO-00006`) puede
    repetirse en dos posiciones distintas del mismo prototipo, y cada una
    tiene su propia lista de hijos — indexar por clave las fusionaría en
    una sola (bug real, ver módulo)."""

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
    hijos = arbol.hijos.get(nodo.fila, ())
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
    fila: Sequence[object],
    mapa: MapaColumnas,
    numero: int,
    tipo: TipoNodoPresupuesto,
    *,
    modo_clave_padre: bool,
) -> NodoLeido:
    celda_clave = mapa.valor(fila, "clave_hijo")
    celda_descripcion = mapa.valor(fila, "descripcion")
    celda_importe = mapa.valor(fila, "importe")

    # Hueco de numeración del exportador nativo de OPUS —de un `Nivel 2`/
    # `Nivel 3`/`Concepto` borrado—, no un dato real: sin clave, sin
    # descripción y sin importe (verificado contra el archivo real,
    # `CATALOGO_DE_PRESUPUESTO.csv`: 121 filas exactas en este patrón). Se
    # numera sola —mismo criterio que una fila sin clave en un catálogo
    # base, `claves_automaticas.generar_clave_automatica`— en vez de
    # rechazar la fila: su posición en el árbol sigue siendo real mientras
    # se termina de leer (sus hermanos SÍ cuentan en el WBS) aunque su
    # contenido esté vacío. `construir_arboles` decide después, con todo
    # su subárbol ya leído, si de verdad se descarta (`es_hueco`, mismo
    # criterio que la referencia). Solo se activa en el árbol nativo
    # (`nivel`, sin `clave_padre`): el formato histórico de este cargador
    # no trae filas así y no debe empezar a aceptarlas sin clave.
    es_placeholder = (
        not modo_clave_padre
        and esta_vacio(celda_clave)
        and esta_vacio(celda_descripcion)
        and (esta_vacio(celda_importe) or _decimal_opcional(celda_importe, columna="importe") == 0)
    )

    if es_placeholder:
        clave = f"__sin_clave__{numero}"
        descripcion = f"(sin descripción — fila {numero} del archivo)"
    else:
        clave = _clave_obligatoria(celda_clave, columna="clave_hijo")
        descripcion = texto_limpio(celda_descripcion)
        if not descripcion:
            raise ErrorEnFila(
                "descripcion: es obligatoria, es lo único legible de un nodo sin catálogo.",
                columna="descripcion",
            )

    clave_padre = _clave_opcional(mapa.valor(fila, "clave_padre"), columna="clave_padre")
    if (
        modo_clave_padre
        and tipo is not TipoNodoPresupuesto.PROTOTIPO
        and clave_padre is None
    ):
        raise ErrorEnFila(
            "clave_padre: toda fila que no sea PROTOTIPO necesita padre (§árbol).",
            columna="clave_padre",
        )

    nivel = _entero_opcional(mapa.valor(fila, "nivel"), columna="nivel")
    if nivel is not None and nivel < 0:
        raise ErrorEnFila(
            f"nivel: no puede ser negativo ({nivel}).", columna="nivel", valor=nivel
        )
    if not modo_clave_padre and nivel is None:
        # Sin `clave_padre` en el archivo, `nivel` es la única columna que
        # arma el árbol (§construir_arboles) — ninguna fila puede faltarla,
        # ni siquiera `PROTOTIPO`: su propio `nivel` (0) es lo que vacía la
        # pila y abre un árbol nuevo.
        raise ErrorEnFila(
            "nivel: toda fila la necesita cuando el archivo no trae "
            "clave_padre — es lo único que arma el árbol (§árbol).",
            columna="nivel",
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
        nivel=nivel,
        wbs=texto_limpio(mapa.valor(fila, "wbs")) or None,
        fila=numero,
        es_hueco=es_placeholder,
    )


_NIVEL_WBS: dict[TipoNodoPresupuesto, int] = {
    TipoNodoPresupuesto.PROTOTIPO: 1,
    TipoNodoPresupuesto.NIVEL: 2,
    TipoNodoPresupuesto.ETAPA: 3,
    TipoNodoPresupuesto.AGRUPADOR: 4,
    TipoNodoPresupuesto.CONCEPTO: 4,
    TipoNodoPresupuesto.CONCEPTO_AUXILIAR: 4,
    TipoNodoPresupuesto.MATERIAL: 5,
    TipoNodoPresupuesto.DESTAJO: 5,
    TipoNodoPresupuesto.SUBCONTRATO: 5,
}
"""Nivel fijo de cada TIPO en la numeración WBS (§7.4), **solo para el
formato histórico** (`clave_padre` explícita, sin columna `nivel`): ahí no
hay profundidad declarada por fila y esta tabla es la única fuente. No es
la profundidad real del árbol: una etapa sin concepto intermedio cuelga
MATERIAL directo y ese material igual cae en el nivel 5, con el 4 en 0.

El árbol nativo de OPUS (`nivel` + posición) **no usa esta tabla**: ahí
`CONCEPTO` aparece verificado en `nivel` 3 **o** 4 según cuelgue
directo de una `ETAPA` o de un `AGRUPADOR` —una tabla fija por TIPO sería
incorrecta para ese mismo TIPO en dos profundidades distintas—, así que
`construir_arboles` calcula el nivel de WBS directo de `nodo.nivel` en ese
modo, sin pasar por aquí (§construir_arboles, "no dupliques lógica": el
archivo ya trae la profundidad, no hace falta un segundo contador que
pueda desincronizarse)."""


def _siguiente_wbs(contadores: list[int], nivel: int) -> str:
    """WBS que le toca a esta fila, dado el nivel de WBS que ya se resolvió
    para ella (desde `_NIVEL_WBS[tipo]` en el formato histórico, o desde
    `nodo.nivel + 1` en el árbol nativo de OPUS): sube el contador de ese
    nivel y reinicia los más profundos (§7.4). Un solo `contadores` para
    todo el archivo —no por prototipo— porque el segmento de nivel 1
    (`PROTOTIPO`/`Capítulo`) es justamente el que numera de un prototipo al
    siguiente."""
    while len(contadores) < nivel:
        contadores.append(0)
    contadores[nivel - 1] += 1
    for indice in range(nivel, len(contadores)):
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

    La identidad padre-hijo sale de **una** de dos columnas — nunca las dos
    a la vez en el mismo archivo real (§cabeceras.PRESUPUESTO) — y se
    decide una sola vez por archivo, no fila por fila:

    - **`clave_padre`**, si el archivo la trae: formato histórico de este
      cargador, DFS pre-order por clave (sin cambio de comportamiento).
    - **`nivel`**, si no trae `clave_padre` pero sí `nivel`: árbol nativo
      del exportador de OPUS. El padre de una fila es la más cercana hacia
      atrás, dentro del mismo prototipo, con `nivel` **menor** que el de la
      fila actual — una pila de posiciones, no un mapa de claves (el
      archivo real no trae ninguna). `Indice` no participa: es solo la
      suma de control entre hermanos, y validarlo es opcional.
    - Si el archivo no trae ninguna de las dos, no hay árbol posible:
      `ErrorDeCabecera` (del archivo entero, no de una fila).

    Devuelve ``(arboles, errores, pendientes, omitidos)``, mismo contrato que
    `cpu.agrupar_conceptos`:

    - Una fila mala no tumba el árbol ni el archivo (§9.3): se reporta y se
      sigue.
    - Un `TIPO` fuera del contrato va a la bandeja como `fila_no_parseada`
      (§10.3).
    - Modo `clave_padre`: una fila cuyo `clave_padre` no corresponde a
      ningún nodo visto **en este mismo prototipo** es error de fila — sin
      padre no hay a qué colgarla.
    - Modo `nivel`: un salto de más de un nivel respecto al padre que la
      pila encuentra, o una fila que se queda sin ningún padre a media
      reconstrucción, es **pendiente no crítico**
      (`TipoPendiente.NIVEL_INCONSISTENTE`) — la fila se cuelga de la raíz
      del prototipo y la carga sigue; no es un error de fila porque el
      archivo real (verificado) no trae ninguno de estos huecos y forzar
      el árbol a medias es preferible a perder la fila.
    - Prototipo repetido en el archivo: gana el último árbol, el anterior
      cuenta como omitido.
    - Modo `nivel`: un hueco (`NodoLeido.es_hueco`, `_leer_nodo`) se
      descarta en silencio —sin error ni pendiente, cuenta como omitido—
      salvo que algo con clave real cuelgue debajo de él, a cualquier
      profundidad (`tiene_clave_debajo`): mismo criterio, verificado
      renglón por renglón, que la referencia
      (`cerebro/backend/core/importacion_opus.py::leer_presupuesto`). La
      decisión se toma cuando el hueco se desprende de la pila —ya leyó
      todo su propio subárbol— nunca antes.
    """
    modo_clave_padre = "clave_padre" in mapa.indices
    modo_nivel = "nivel" in mapa.indices
    if not modo_clave_padre and not modo_nivel:
        raise ErrorDeCabecera(
            "Presupuesto jerárquico: el archivo no trae ni `clave_padre` ni "
            "`nivel` (§cabeceras.PRESUPUESTO) — sin una de las dos no hay "
            "padre que reconstruir (§árbol)."
        )

    arboles: dict[str, ArbolPrototipoCargado] = {}
    errores: list[ErrorDeFila] = []
    pendientes: list[PendientePropuesto] = []
    omitidos = 0

    raiz: NodoLeido | None = None
    hijos: dict[int, list[NodoLeido]] = {}
    ultimo_por_clave: dict[str, NodoLeido] = {}
    pila: list[NodoLeido] = []
    """Solo en modo `nivel`: de la raíz del prototipo actual a la última
    fila leída, para encontrar el padre por `nivel` + posición. Se
    reinicia en cada `PROTOTIPO`, igual que `hijos`/`ultimo_por_clave`."""
    padre_de: dict[int, int] = {}
    """Solo en modo `nivel`: `fila` del nodo → `fila` de su padre, para
    poder desprenderlo de `hijos[padre]` si resulta hueco muerto (abajo)."""
    tiene_clave_debajo: dict[int, bool] = {}
    """Solo en modo `nivel`: `fila` → si algo con clave real (no un hueco)
    aparece en su subárbol, a cualquier profundidad. Se marca al leer cada
    fila con clave real, subiendo por toda la pila de ancestros abiertos
    en ese momento —igual que la referencia (`con_clave_debajo`)—, nunca
    al cerrar un nodo: lo que importa es si ALGO con clave existió debajo,
    sin que un hueco intermedio corte la cadena."""
    contadores_wbs = [0, 0, 0, 0, 0]

    def _descartar_si_hueco_muerto(nodo: NodoLeido) -> None:
        """Un hueco (`es_hueco`) sin nada con clave real debajo no aporta
        nada al árbol: se desprende de `hijos` y de `ultimo_por_clave`,
        igual que la referencia lo tira de `quedan` (mismo criterio,
        verificado: 121/121 huecos del archivo real caen aquí). Solo se
        llama cuando el nodo ya se desprendió de la pila —su subárbol
        completo ya se leyó— para que `tiene_clave_debajo` esté resuelto."""
        nonlocal omitidos
        if not nodo.es_hueco or tiene_clave_debajo.get(nodo.fila, False):
            return
        fila_padre = padre_de.get(nodo.fila)
        if fila_padre is not None and fila_padre in hijos:
            hijos[fila_padre] = [h for h in hijos[fila_padre] if h.fila != nodo.fila]
        if ultimo_por_clave.get(nodo.clave) is nodo:
            del ultimo_por_clave[nodo.clave]
        omitidos += 1

    def cerrar() -> None:
        nonlocal raiz, hijos, ultimo_por_clave, pila, padre_de, tiene_clave_debajo, omitidos
        if raiz is None:
            return
        for nodo_abierto in reversed(pila[1:]):  # pila[0] es la raíz, nunca hueco
            _descartar_si_hueco_muerto(nodo_abierto)
        arbol = ArbolPrototipoCargado(
            clave_prototipo=raiz.clave,
            raiz=raiz,
            hijos={fila_padre: tuple(lista) for fila_padre, lista in hijos.items()},
            nodos=dict(ultimo_por_clave),
        )
        if arbol.llave in arboles:
            omitidos += 1
        arboles[arbol.llave] = arbol
        raiz = None
        hijos = {}
        ultimo_por_clave = {}
        pila = []
        padre_de = {}
        tiene_clave_debajo = {}

    for numero, fila in filas:
        crudo_tipo = mapa.valor(fila, "tipo")
        texto_tipo = normalizar(crudo_tipo)
        tipo = _resolver_tipo(texto_tipo)

        if tipo is None:
            errores.append(
                ErrorDeFila(
                    fila=numero,
                    columna="tipo",
                    valor=texto_limpio(crudo_tipo),
                    motivo=(
                        f"tipo: {texto_limpio(crudo_tipo)!r} no es uno de los "
                        f"valores esperados ({', '.join(_TODOS_LOS_TIPOS_RECONOCIDOS)})."
                    ),
                )
            )
            pendientes.append(
                PendientePropuesto(
                    tipo=TipoPendiente.FILA_NO_PARSEADA,
                    entidad="prototipo_nodo",
                    valor_origen=texto_limpio(crudo_tipo),
                    propuesta={"opciones": _TODOS_LOS_TIPOS_RECONOCIDOS},
                    origen_ref=f"fila {numero}",
                )
            )
            continue

        try:
            nodo = _leer_nodo(fila, mapa, numero, tipo, modo_clave_padre=modo_clave_padre)
        except ErrorEnFila as exc:
            errores.append(exc.con_fila(numero))
            continue

        if modo_clave_padre:
            nivel_wbs = _NIVEL_WBS[tipo]
        else:
            assert nodo.nivel is not None  # noqa: S101 — `_leer_nodo` ya lo exige en este modo
            nivel_wbs = nodo.nivel + 1
        wbs_calculado = _siguiente_wbs(contadores_wbs, nivel_wbs)
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
            pila = [nodo]
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

        if modo_clave_padre:
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
        else:
            assert nodo.nivel is not None  # noqa: S101 — `_leer_nodo` ya lo exige en este modo
            # Saca de la pila todo lo que esté al mismo nivel o más
            # profundo que esta fila: no puede ser su ancestro. Ya leyó
            # todo su subárbol — es el momento de decidir si era un hueco
            # muerto (`_descartar_si_hueco_muerto`).
            while pila and pila[-1].nivel is not None and pila[-1].nivel >= nodo.nivel:
                _descartar_si_hueco_muerto(pila.pop())
            padre = pila[-1] if pila else None
            if padre is None:
                # El archivo real (verificado) no deja ninguna fila así:
                # toda raíz nueva es `PROTOTIPO`, que ya se atendió arriba.
                # Si pasara, no hay a qué colgarla salvo la raíz del
                # prototipo — se reporta la anomalía, no se pierde la fila.
                pendientes.append(
                    PendientePropuesto(
                        tipo=TipoPendiente.NIVEL_INCONSISTENTE,
                        entidad="prototipo_nodo",
                        valor_origen=str(nodo.nivel),
                        propuesta={
                            "accion": (
                                "Sin padre en la pila a media reconstrucción; "
                                "se cuelga de la raíz del prototipo."
                            )
                        },
                        origen_ref=f"fila {numero}",
                    )
                )
                padre = raiz
            elif nodo.nivel > padre.nivel + 1:  # type: ignore[operator]
                pendientes.append(
                    PendientePropuesto(
                        tipo=TipoPendiente.NIVEL_INCONSISTENTE,
                        entidad="prototipo_nodo",
                        valor_origen=str(nodo.nivel),
                        propuesta={"nivel_del_padre": padre.nivel},
                        origen_ref=f"fila {numero}",
                    )
                )
            if not nodo.es_hueco:
                # Sube por toda la cadena de ancestros abiertos —no solo
                # el padre inmediato— porque un hueco intermedio no corta
                # la cadena: lo único que importa es si algo con clave
                # real existe en el subárbol, a cualquier profundidad
                # (mismo criterio que la referencia, `con_clave_debajo`).
                # `pila` ya trae esa cadena completa salvo que estuviera
                # vacía (el caso sin padre de arriba, que cuelga de
                # `raiz`): ahí la cadena es solo la raíz misma.
                for ancestro in pila or (raiz,):
                    tiene_clave_debajo[ancestro.fila] = True
            pila.append(nodo)

        hijos.setdefault(padre.fila, []).append(nodo)
        padre_de[nodo.fila] = padre.fila
        if tipo in _TIPOS_CON_HIJOS:
            ultimo_por_clave[nodo.clave] = nodo

    cerrar()
    return tuple(arboles.values()), tuple(errores), tuple(pendientes), omitidos
