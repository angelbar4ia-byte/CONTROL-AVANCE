"""Cargador de CPU / Conceptos: dos formatos (§10.6 `CABECERAS_CPU.xlsx`,
y la matriz nativa de OPUS, extensión propia).

Spec §10.6 (contrato del archivo, hoja `EXPORTADOR`) · §7.3 (APU: concepto +
explosión) · §3.3 (la CLAVE manda) · §10.3 (bandeja de pendientes) · §10.8
(cada carga es una versión).

Dos formas de traer concepto + CPU, nunca mezcladas en el mismo archivo
(mismo patrón que `presupuesto.construir_arboles` con `clave_padre`/
`nivel` — se decide una sola vez por archivo, por columnas presentes en
`MapaColumnas.indices`, nunca por un flag explícito del llamador):

- **Plano** (§10.6, el que describe este módulo desde siempre): por cada
  concepto viene una fila **encabezado** (``TIPO = Concepto``) seguida de
  sus filas **componente** (``TIPO = Material | Mano de obra |
  Subcontrato``). Reconstruir el bloque por posición es la única regla
  estructural, y vive en `_agrupar_conceptos_plano`.
- **Matriz** (export nativo de OPUS, `ANALISIS_DE_BASICOS_CONCEPTOS.csv`,
  extensión propia, §cabeceras.CPU_MATRIZ): cada fila trae su propio
  padre explícito (``Clave Padre`` → ``Clave Hijo``), nunca una fila que
  describa al concepto mismo — agrupar es un `dict` por clave, no una
  máquina de estados (mismo criterio que `cuadrillas.agrupar_cuadrillas`),
  y vive en `_agrupar_conceptos_matriz`. Como ninguna fila trae la
  descripción/unidad del concepto, quien llama las da aparte
  (`descripciones_concepto`) — normalmente cruzadas contra el árbol de
  `presupuesto.construir_arboles` sobre el `CATALOGO_DE_PRESUPUESTO.csv`
  del mismo prototipo.

Módulo puro (§12.11).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.reporte import (
    ErrorDeFila,
    ErrorEnFila,
    PendientePropuesto,
    TipoPendiente,
)
from obractrl.domain.shared.diccionario import CategoriaExplosion
from obractrl.domain.shared.normalizacion import (
    ValorNoConvertible,
    a_decimal,
    esta_vacio,
    normalizar,
    texto_limpio,
)
from obractrl.domain.shared.valores import Clave

__all__ = [
    "CATEGORIA_POR_TIPO",
    "CATEGORIA_POR_TIPO_MATRIZ",
    "ComponenteCargado",
    "ConceptoCargado",
    "EncabezadoCargado",
    "FilasMatrizSinAgrupar",
    "agrupar_compuestos",
    "agrupar_conceptos",
    "agrupar_cuadrillas_matriz",
    "descripciones_de_hijos",
    "validar_origen_y_tipo",
]

_TIPO_ENCABEZADO = "concepto"
"""Valor de la columna ``TIPO`` que abre un bloque (§10.6: ``TIPO=Concepto``)."""

CATEGORIA_POR_TIPO: dict[str, CategoriaExplosion] = {
    "material": CategoriaExplosion.MATERIAL,
    "mano de obra": CategoriaExplosion.MANO_OBRA,
    "subcontrato": CategoriaExplosion.SUBCONTRATO,
}
"""``TIPO`` del archivo → `explosion.categoria` (§8.2).

Los tres valores son exactamente los que enumera el §10.6
(``TIPO=Material/Mano de obra/Subcontrato``). Un cuarto valor no se traduce
por parecido: es una excepción y va a la bandeja (§10.3), porque
`explosion.categoria` es **invariante** del §8.2 y agregarle un valor es
trabajo de programador (§8.7).
"""

CATEGORIA_POR_TIPO_MATRIZ: dict[str, CategoriaExplosion] = {
    "material": CategoriaExplosion.MATERIAL,
    "mano de obra": CategoriaExplosion.MANO_OBRA,
    "manodeobra": CategoriaExplosion.MANO_OBRA,
    "contrato": CategoriaExplosion.TRABAJO,
    "flete": CategoriaExplosion.FLETE,
}
"""``Tipo`` del componente en la matriz nativa de OPUS
(`ANALISIS_DE_BASICOS_CONCEPTOS.csv`) → `explosion.categoria`. Vocabulario
propio de este archivo, **distinto** del §10.6 plano (`CATEGORIA_POR_TIPO`,
arriba): las llaves que comparten ("mano de obra") resuelven igual en los
dos, y las que no comparte ninguno ("contrato", "flete", "manodeobra")
son nuevas aquí, así que mantenerlos separados no es duplicación — es lo
que conserva intacta la garantía de `CATEGORIA_POR_TIPO` de que el plano
solo conoce tres valores y un cuarto ahí sigue siendo una excepción,
nunca ésta.

``manodeobra`` (sin espacio) es el único alias que hace falta aquí —
verificado contra el archivo real, que no trae la forma con espacio en
este `Tipo`— pero se deja también la forma con espacio por si el
exportador la escribe distinto en otra corrida (mismo criterio que
`presupuesto._ALIAS_TIPO_RENGLON`).

``Contrato`` → `CategoriaExplosion.TRABAJO`: el genérico, sin distinguir
destajo de subcontrato por sí solo —nunca por un heurístico de este
módulo, como adivinar por el prefijo de la clave, que el cerebro prohíbe
explícitamente (cita fallos reales)—. `CATALOGO_DE_TRABAJOS.csv` (export
nativo de OPUS, §cabeceras.TRABAJOS_OPUS) sí trae esa distinción fila por
fila: quien llama a `agrupar_conceptos` puede pasar ``clase_trabajo``
(clave → `DESTAJO`/`SUBCONTRATO`, construido a partir de ese archivo) y
`_agrupar_conceptos_matriz` usa la categoría precisa en vez de ésta. Sin
``clase_trabajo`` —o para una clave que no está en él—, la fila se queda
en este genérico y se marca con `TipoPendiente.TRABAJO_SIN_CLASE` (ver
`_agrupar_conceptos_matriz`).
"""


@dataclass(frozen=True, slots=True)
class EncabezadoCargado:
    """Fila ``TIPO=Concepto``: identifica el concepto del bloque (§10.6)."""

    clave: Clave
    descripcion: str
    unidad: str | None = None
    familia: str | None = None
    precio_declarado: Decimal | None = None
    """PU de la columna F en la fila encabezado.

    Solo informativo: el §7.3 dice que el CPU **se calcula** de la explosión,
    y `PublicarVersionCPU` ya trata el precio capturado como la excepción del
    concepto sin desglose.
    """

    fila: int = 0


@dataclass(frozen=True, slots=True)
class ComponenteCargado:
    """Fila componente: un insumo dentro del APU del concepto (§7.3, §10.6).

    ``cantidad`` es la columna E, que el §10.6 define como
    "**rendimiento = CANTIDAD**": una sola columna para las dos cosas.
    """

    clave_insumo: Clave
    descripcion: str
    categoria: CategoriaExplosion
    cantidad: Decimal
    unidad: str | None = None
    precio_unitario: Decimal | None = None
    familia: str | None = None
    fila: int = 0


@dataclass(frozen=True, slots=True)
class ConceptoCargado:
    """Bloque completo: encabezado + sus componentes (§10.6)."""

    encabezado: EncabezadoCargado
    componentes: tuple[ComponenteCargado, ...] = field(default=())

    @property
    def llave(self) -> str:
        """Identidad para dedup y diff: la CLAVE del concepto (§3.3)."""
        return str(self.encabezado.clave)


@dataclass(frozen=True, slots=True)
class FilasMatrizSinAgrupar:
    """Filas de la matriz nativa de OPUS (`ANALISIS_DE_BASICOS_CONCEPTOS.csv`,
    §cabeceras.CPU_MATRIZ) leídas pero **sin agrupar** — el contrato de datos
    entre `adapters.excel.cargadores.CargadorCPU.leer()` y
    `application.casos_uso.aplicar_carga.AplicadorCPU.aplicar()`.

    `CargadorCPU.leer()` es un adapter puro (sin acceso a base, §12.11): no
    puede construir ``descripciones_concepto`` ni ``clase_trabajo`` —los dos
    mapas que este modo necesita (ver docstring del módulo, arriba)— porque
    ninguno de los dos sale del archivo que se está leyendo, sino de la base
    ya poblada por otras cargas (el árbol de presupuesto, `CATALOGO_DE_
    TRABAJOS.csv`). Por eso, cuando el archivo resulta ser la matriz
    (``clave_padre`` en sus encabezados), `CargadorCPU.leer()` no llama a
    `agrupar_conceptos` — devuelve esto en `LecturaCarga.registros` (un único
    elemento) para que sea `AplicadorCPU.aplicar()`, que sí tiene los
    repositorios inyectados, quien construya los mapas reales y agrupe.

    El modo plano (§10.6) no usa esto en absoluto: sigue devolviendo
    `ConceptoCargado` ya agrupados en `LecturaCarga.registros`, exactamente
    como antes de este cambio. `AplicadorCPU.aplicar()` distingue los dos
    formatos con ``isinstance(lectura.registros[0], FilasMatrizSinAgrupar)``
    — mismo criterio que ya usa `AplicadorDePrototipos` para distinguir el
    árbol del alta plana con `ArbolPrototipoCargado` (`domain.cargadores.
    presupuesto`), no uno nuevo inventado para esta ocasión.
    """

    mapa: MapaColumnas
    filas: tuple[tuple[int, Sequence[object]], ...]


def _clave_de(celda: object, *, columna: str) -> Clave:
    if esta_vacio(celda):
        raise ErrorEnFila(
            f"{columna}: la fila no trae clave y la clave es única por catálogo (§3.3).",
            columna=columna,
        )
    try:
        return Clave(str(celda))
    except ValueError as exc:
        raise ErrorEnFila(str(exc), columna=columna, valor=celda) from exc


def _decimal_opcional(celda: object, *, columna: str) -> Decimal | None:
    if esta_vacio(celda):
        return None
    try:
        return a_decimal(celda, campo=columna)
    except ValorNoConvertible as exc:
        raise ErrorEnFila(str(exc), columna=columna, valor=celda) from exc


def _leer_encabezado(
    fila: Sequence[object], mapa: MapaColumnas, numero: int
) -> EncabezadoCargado:
    descripcion = texto_limpio(mapa.valor(fila, "descripcion"))
    if not descripcion:
        raise ErrorEnFila(
            "descripcion: un concepto sin descripción no es identificable (§10.1).",
            columna="descripcion",
        )
    return EncabezadoCargado(
        clave=_clave_de(mapa.valor(fila, "clave"), columna="clave"),
        descripcion=descripcion,
        unidad=texto_limpio(mapa.valor(fila, "unidad")) or None,
        familia=texto_limpio(mapa.valor(fila, "familia")) or None,
        precio_declarado=_decimal_opcional(
            mapa.valor(fila, "precio_unitario"), columna="precio_unitario"
        ),
        fila=numero,
    )


def _leer_componente(
    fila: Sequence[object],
    mapa: MapaColumnas,
    numero: int,
    categoria: CategoriaExplosion,
) -> ComponenteCargado:
    # Acepta negativos a propósito: un componente de deducción (material
    # recuperado, ajuste) resta del importe del concepto en vez de sumar
    # (mismo criterio en `Componente.__post_init__`, §7.3).
    cantidad = _decimal_opcional(mapa.valor(fila, "cantidad"), columna="cantidad")
    if cantidad is None:
        raise ErrorEnFila(
            "cantidad: la columna E (rendimiento = CANTIDAD) es obligatoria en "
            "una fila componente (§10.6).",
            columna="cantidad",
        )
    return ComponenteCargado(
        # El §10.6 fija que en la fila componente la clave del insumo es la
        # columna B; los materiales se matchean por ESA clave contra catálogo
        # y almacén.
        clave_insumo=_clave_de(mapa.valor(fila, "clave_insumo"), columna="clave_insumo"),
        descripcion=texto_limpio(mapa.valor(fila, "descripcion")),
        categoria=categoria,
        cantidad=cantidad,
        unidad=texto_limpio(mapa.valor(fila, "unidad")) or None,
        precio_unitario=_decimal_opcional(
            mapa.valor(fila, "precio_unitario"), columna="precio_unitario"
        ),
        familia=texto_limpio(mapa.valor(fila, "familia")) or None,
        fila=numero,
    )


def _agrupar_conceptos_plano(
    filas: Sequence[tuple[int, Sequence[object]]], mapa: MapaColumnas
) -> tuple[
    tuple[ConceptoCargado, ...],
    tuple[ErrorDeFila, ...],
    tuple[PendientePropuesto, ...],
    int,
]:
    """Formato plano (§10.6): filas → bloques concepto+componentes.

    Devuelve ``(conceptos, errores, pendientes, omitidos)``:

    - Una fila mala **no** tumba el bloque ni el archivo (§9.3): se reporta y
      se sigue.
    - Un ``TIPO`` fuera del §10.6 va a la bandeja como `fila_no_parseada`
      (§10.3), no se traduce por parecido.
    - Un componente antes de su encabezado es un error de fila: sin concepto
      padre no hay a qué colgarlo.
    - Clave de concepto repetida dentro del archivo: **gana el último bloque**
      y el anterior cuenta como omitido, que es lo que significa "deduplica
      por clave" en el modo Actualizar (§10.2).
    """
    bloques: dict[str, ConceptoCargado] = {}
    errores: list[ErrorDeFila] = []
    pendientes: list[PendientePropuesto] = []
    omitidos = 0

    actual: EncabezadoCargado | None = None
    componentes: list[ComponenteCargado] = []

    def cerrar() -> None:
        nonlocal actual, componentes, omitidos
        if actual is None:
            return
        bloque = ConceptoCargado(encabezado=actual, componentes=tuple(componentes))
        if bloque.llave in bloques:
            omitidos += 1
        bloques[bloque.llave] = bloque
        actual = None
        componentes = []

    for numero, fila in filas:
        crudo_tipo = mapa.valor(fila, "tipo")
        tipo = normalizar(crudo_tipo)

        if not tipo:
            errores.append(
                ErrorDeFila(
                    fila=numero,
                    columna="tipo",
                    valor=None,
                    motivo=(
                        "tipo: la columna I es la que dice si la fila es "
                        "encabezado o componente (§10.6); vacía, la fila no se "
                        "puede clasificar."
                    ),
                )
            )
            continue

        if tipo == _TIPO_ENCABEZADO:
            cerrar()
            try:
                actual = _leer_encabezado(fila, mapa, numero)
            except ErrorEnFila as exc:
                errores.append(exc.con_fila(numero))
                actual = None
            continue

        categoria = CATEGORIA_POR_TIPO.get(tipo)
        if categoria is None:
            errores.append(
                ErrorDeFila(
                    fila=numero,
                    columna="tipo",
                    valor=texto_limpio(crudo_tipo),
                    motivo=(
                        f"tipo: {texto_limpio(crudo_tipo)!r} no es uno de los "
                        f"valores del §10.6 (Concepto, "
                        f"{', '.join(sorted(CATEGORIA_POR_TIPO))})."
                    ),
                )
            )
            pendientes.append(
                PendientePropuesto(
                    tipo=TipoPendiente.FILA_NO_PARSEADA,
                    entidad="explosion",
                    valor_origen=texto_limpio(crudo_tipo),
                    propuesta={"opciones": sorted(CATEGORIA_POR_TIPO)},
                    origen_ref=f"fila {numero}",
                )
            )
            continue

        if actual is None:
            errores.append(
                ErrorDeFila(
                    fila=numero,
                    columna="tipo",
                    valor=texto_limpio(crudo_tipo),
                    motivo=(
                        "Fila componente sin su fila encabezado (TIPO=Concepto) "
                        "previa: no hay concepto al cual colgarla (§10.6)."
                    ),
                )
            )
            continue

        try:
            componentes.append(_leer_componente(fila, mapa, numero, categoria))
        except ErrorEnFila as exc:
            errores.append(exc.con_fila(numero))

    cerrar()
    return tuple(bloques.values()), tuple(errores), tuple(pendientes), omitidos


def _agrupar_conceptos_matriz(
    filas: Sequence[tuple[int, Sequence[object]]],
    mapa: MapaColumnas,
    descripciones_concepto: Mapping[str, tuple[str, str | None]],
    clase_trabajo: Mapping[str, CategoriaExplosion] | None = None,
    *,
    origen: str = "concepto",
) -> tuple[
    tuple[ConceptoCargado, ...],
    tuple[ErrorDeFila, ...],
    tuple[PendientePropuesto, ...],
    int,
]:
    """Matriz nativa de OPUS (`ANALISIS_DE_BASICOS_CONCEPTOS.csv`,
    §cabeceras.CPU_MATRIZ): cada fila trae su propio ``Clave Padre`` (el
    concepto) → ``Clave Hijo`` (el insumo), nunca una fila-encabezado que
    describa al concepto mismo. Se agrupa por esa llave explícita, no por
    posición — un `dict`, no una máquina de estados (mismo criterio que
    `cuadrillas.agrupar_cuadrillas`, no el de `_agrupar_conceptos_plano`).

    - Solo entran las filas ``Origen=Concepto``: ``Material``/
      ``ManoDeObra`` son matrices de insumo compuesto (materiales con
      receta propia, cuadrillas) fuera de alcance de este cargador — se
      descartan en silencio, ni error ni pendiente, porque simplemente no
      son datos de este catálogo.
    - La descripción/unidad del concepto no vive en este archivo —ninguna
      fila describe al padre—: sale de ``descripciones_concepto`` (clave
      → (descripcion, unidad)), que construye quien llama, normalmente
      cruzando contra el árbol de `presupuesto.construir_arboles` sobre
      el `CATALOGO_DE_PRESUPUESTO.csv` del mismo prototipo. Una
      ``clave_padre`` que no cruza ahí es error de fila para **todas**
      sus filas componente: sin descripción el concepto no es
      identificable (§10.1), mismo criterio que la descripción vacía en
      `_leer_encabezado` (modo plano).
    - ``Tipo`` del componente resuelve con su propio vocabulario
      (`CATEGORIA_POR_TIPO_MATRIZ`, no `CATEGORIA_POR_TIPO`): un valor
      fuera de ese vocabulario va a la bandeja como `fila_no_parseada`,
      igual que en modo plano. ``Contrato`` → `CategoriaExplosion.
      TRABAJO` es el genérico; si ``clase_trabajo`` (clave del insumo →
      `DESTAJO`/`SUBCONTRATO`, construido por quien llama a partir de
      `CATALOGO_DE_TRABAJOS.csv`, §cabeceras.TRABAJOS_OPUS) trae esa
      clave, se usa esa categoría precisa en su lugar y la fila **no**
      lleva el pendiente. Si no la trae —archivo no disponible, o una
      clave que de verdad no cruza—, cae en el comportamiento de siempre:
      la categoría genérica más `TipoPendiente.TRABAJO_SIN_CLASE` (ver
      `CATEGORIA_POR_TIPO_MATRIZ`).
    - Por construcción, cada ``clave_padre`` es un solo grupo —no hay
      bloque repetido que deduplicar—: ``omitidos`` siempre sale en 0,
      igual que en `agrupar_cuadrillas`, y se conserva solo para que la
      firma combine con el modo plano (§9.2).
    """
    grupos: dict[str, list[tuple[int, Sequence[object]]]] = {}
    orden_grupos: list[str] = []
    errores: list[ErrorDeFila] = []
    pendientes: list[PendientePropuesto] = []

    for numero, fila in filas:
        if normalizar(mapa.valor(fila, "origen")) != origen:
            continue
        try:
            clave_padre = _clave_de(
                mapa.valor(fila, "clave_padre"), columna="clave_padre"
            )
        except ErrorEnFila as exc:
            errores.append(exc.con_fila(numero))
            continue
        llave = str(clave_padre)
        if llave not in grupos:
            grupos[llave] = []
            orden_grupos.append(llave)
        grupos[llave].append((numero, fila))

    bloques: list[ConceptoCargado] = []

    for llave_grupo in orden_grupos:
        renglones = grupos[llave_grupo]
        descripcion_unidad = descripciones_concepto.get(llave_grupo)
        if descripcion_unidad is None:
            for numero, _ in renglones:
                errores.append(
                    ErrorDeFila(
                        fila=numero,
                        columna="clave_padre",
                        valor=llave_grupo,
                        motivo=(
                            f"clave_padre: {llave_grupo!r} no cruza con ningún "
                            f"CONCEPTO del árbol de presupuesto — sin su "
                            f"descripción real el concepto no es identificable "
                            f"(§10.1)."
                        ),
                    )
                )
            continue

        descripcion, unidad = descripcion_unidad
        encabezado = EncabezadoCargado(
            clave=Clave(llave_grupo),
            descripcion=descripcion,
            unidad=unidad,
            fila=renglones[0][0],
        )

        componentes: list[ComponenteCargado] = []
        for numero, fila in renglones:
            crudo_tipo = mapa.valor(fila, "tipo")
            texto_tipo = normalizar(crudo_tipo)
            categoria = CATEGORIA_POR_TIPO_MATRIZ.get(texto_tipo)
            if categoria is None:
                errores.append(
                    ErrorDeFila(
                        fila=numero,
                        columna="tipo",
                        valor=texto_limpio(crudo_tipo),
                        motivo=(
                            f"tipo: {texto_limpio(crudo_tipo)!r} no es uno de los "
                            f"valores de la matriz nativa de OPUS "
                            f"({', '.join(sorted(CATEGORIA_POR_TIPO_MATRIZ))})."
                        ),
                    )
                )
                pendientes.append(
                    PendientePropuesto(
                        tipo=TipoPendiente.FILA_NO_PARSEADA,
                        entidad="explosion",
                        valor_origen=texto_limpio(crudo_tipo),
                        propuesta={"opciones": sorted(CATEGORIA_POR_TIPO_MATRIZ)},
                        origen_ref=f"fila {numero}",
                    )
                )
                continue

            try:
                componente = _leer_componente(fila, mapa, numero, categoria)
            except ErrorEnFila as exc:
                errores.append(exc.con_fila(numero))
                continue

            if categoria is CategoriaExplosion.TRABAJO and clase_trabajo:
                # La clave del insumo ya es un `Clave` validado (§3.3): se
                # cruza tal cual, sin volver a leer ni normalizar la celda.
                categoria_precisa = clase_trabajo.get(str(componente.clave_insumo))
                if categoria_precisa is not None:
                    categoria = categoria_precisa
                    componente = replace(componente, categoria=categoria_precisa)

            componentes.append(componente)

            if categoria is CategoriaExplosion.TRABAJO:
                # No crítico (§10.3): la fila se carga igual con la
                # categoría genérica — esto marca para reclasificar la
                # clave que no cruzó contra CATALOGO_DE_TRABAJOS.csv (o,
                # si ``clase_trabajo`` no se recibió, todas: mismo
                # comportamiento que antes de que el catálogo existiera).
                pendientes.append(
                    PendientePropuesto(
                        tipo=TipoPendiente.TRABAJO_SIN_CLASE,
                        entidad="explosion",
                        valor_origen=str(componente.clave_insumo),
                        propuesta={
                            "motivo": (
                                "CATALOGO_DE_TRABAJOS.csv no trae esta clave: "
                                "reclasificar a destajo/subcontrato a mano."
                            ),
                            "opciones": ["destajo", "subcontrato"],
                        },
                        origen_ref=f"fila {numero}",
                    )
                )

        bloques.append(
            ConceptoCargado(encabezado=encabezado, componentes=tuple(componentes))
        )

    return tuple(bloques), tuple(errores), tuple(pendientes), 0


_ORIGENES_MATRIZ = frozenset({"concepto", "material", "manodeobra"})
"""``Origen`` de la matriz nativa: la categoría del **padre** — a qué reporta el
monto (`CONOCIMIENTO.md` §10.5). ``Concepto`` es la matriz de un concepto,
``Material`` la de un compuesto de material (matriz dentro de matriz) y
``ManoDeObra`` la de una cuadrilla."""

_TIPOS_POR_ORIGEN: dict[str, frozenset[str]] = {
    "concepto": frozenset({"material", "contrato", "flete"}),
    "material": frozenset({"material", "contrato", "flete"}),
    "manodeobra": frozenset({"manodeobra"}),
}
"""``Tipo`` permitido por ``Origen``: ``Tipo`` es la naturaleza del **hijo** (el
ADN de la línea, que la explosión conserva hasta la hoja). En los archivos
reales: Concepto → Material 1,693 · Contrato 461 · Flete 35; Material →
Material 250 · Flete 16 · Contrato 1; ManoDeObra → ManoDeObra 112."""


def validar_origen_y_tipo(
    filas: Sequence[tuple[int, Sequence[object]]],
    mapa: MapaColumnas,
) -> tuple[ErrorDeFila, ...]:
    """Una fila con ``Origen`` desconocido, o cuyo ``Tipo`` no cabe en su
    ``Origen``, es error de fila — no se descarta en silencio.

    Solo revisa lo que ningún otro paso revisa: un ``Tipo`` que no existe ya lo
    reporta `_agrupar_conceptos_matriz`; aquí se atrapa el ``Origen`` que no
    existe y la pareja incoherente (una cuadrilla con material, un concepto
    con un hijo de mano de obra). Cuando el exportador cambie el vocabulario,
    esto avisa en vez de cargar de menos.
    """
    errores: list[ErrorDeFila] = []
    for numero, fila in filas:
        crudo_origen = mapa.valor(fila, "origen")
        origen = normalizar(crudo_origen)
        if origen not in _ORIGENES_MATRIZ:
            errores.append(
                ErrorDeFila(
                    fila=numero,
                    columna="origen",
                    valor=texto_limpio(crudo_origen),
                    motivo=(
                        f"origen: {texto_limpio(crudo_origen)!r} no es uno de los "
                        f"valores de la matriz nativa de OPUS "
                        f"(Concepto, Material, ManoDeObra)."
                    ),
                )
            )
            continue
        crudo_tipo = mapa.valor(fila, "tipo")
        tipo = normalizar(crudo_tipo)
        if tipo in CATEGORIA_POR_TIPO_MATRIZ and tipo not in _TIPOS_POR_ORIGEN[origen]:
            errores.append(
                ErrorDeFila(
                    fila=numero,
                    columna="tipo",
                    valor=texto_limpio(crudo_tipo),
                    motivo=(
                        f"tipo: {texto_limpio(crudo_tipo)!r} no cabe en "
                        f"origen {texto_limpio(crudo_origen)!r} (la naturaleza del "
                        f"hijo contra la categoría del padre, `CONOCIMIENTO.md` §10.5)."
                    ),
                )
            )
    return tuple(errores)


def descripciones_de_hijos(
    filas: Sequence[tuple[int, Sequence[object]]],
    mapa: MapaColumnas,
) -> dict[str, tuple[str, str | None]]:
    """Clave → (descripción, unidad) de cada ``Clave Hijo`` de la matriz.

    En la matriz nativa de OPUS ninguna fila describe al padre: la
    descripción y la unidad de un **compuesto** (``AUX-``, ``MEZ-``, ``ZA1``…
    — matriz dentro de matriz, `CONOCIMIENTO.md` §9) salen de las líneas
    donde ese compuesto aparece como hijo. Gana la primera que trae
    descripción; las 89 de los archivos reales traen una sola.
    """
    resultado: dict[str, tuple[str, str | None]] = {}
    for _, fila in filas:
        clave = texto_limpio(mapa.valor(fila, "clave_insumo"))
        descripcion = texto_limpio(mapa.valor(fila, "descripcion"))
        if not clave or not descripcion or clave in resultado:
            continue
        resultado[clave] = (descripcion, texto_limpio(mapa.valor(fila, "unidad")) or None)
    return resultado


def agrupar_compuestos(
    filas: Sequence[tuple[int, Sequence[object]]],
    mapa: MapaColumnas,
    *,
    descripciones: Mapping[str, tuple[str, str | None]] | None = None,
    clase_trabajo: Mapping[str, CategoriaExplosion] | None = None,
) -> tuple[
    tuple[ConceptoCargado, ...],
    tuple[ErrorDeFila, ...],
    tuple[PendientePropuesto, ...],
]:
    """Recetas de los compuestos de material (``Origen = Material``) de la
    matriz nativa de OPUS: la matriz dentro de la matriz (`CONOCIMIENTO.md`
    §9, `CATALOGOS.md` §7).

    Mismo agrupado que `agrupar_conceptos` en modo matriz, pero sobre las
    filas ``Origen = Material``. Las cuadrillas (``Origen = ManoDeObra``) no
    entran: las carga el cargador de cuadrillas y no forman el PU (D-12).
    ``descripciones`` es opcional: sin ella se derivan de las líneas donde el
    compuesto aparece como hijo (`descripciones_de_hijos`).
    """
    if "clave_padre" not in mapa.indices:
        return (), (), ()
    mapa_descripciones = (
        descripciones
        if descripciones is not None
        else descripciones_de_hijos(filas, mapa)
    )
    bloques, errores, pendientes, _ = _agrupar_conceptos_matriz(
        filas, mapa, mapa_descripciones, clase_trabajo, origen="material"
    )
    return bloques, errores, pendientes


def agrupar_cuadrillas_matriz(
    filas: Sequence[tuple[int, Sequence[object]]],
    mapa: MapaColumnas,
    *,
    descripciones: Mapping[str, tuple[str, str | None]],
) -> tuple[
    tuple[ConceptoCargado, ...],
    tuple[ErrorDeFila, ...],
    tuple[PendientePropuesto, ...],
]:
    """Composición de las cuadrillas (``Origen = ManoDeObra``) de la matriz
    nativa de OPUS: cada ``MOCU-``/``CUAD-`` con sus puestos (``MOCA-``) en
    jornales y la línea ``%MO`` del contratista (``cantidad 0.1`` sobre la
    base ya calculada de la propia columna ``Costo``). Se guardan en la tabla
    de cuadrillas (D-616), no como conceptos.

    Ninguna fila describe a la cuadrilla (no es hijo de nadie): su nombre y su
    unidad vienen de ``descripciones``, que arma quien llama a partir del
    catálogo de mano de obra ya cargado.
    """
    if "clave_padre" not in mapa.indices:
        return (), (), ()
    bloques, errores, pendientes, _ = _agrupar_conceptos_matriz(
        filas, mapa, descripciones, None, origen="manodeobra"
    )
    return bloques, errores, pendientes


def agrupar_conceptos(
    filas: Sequence[tuple[int, Sequence[object]]],
    mapa: MapaColumnas,
    *,
    descripciones_concepto: Mapping[str, tuple[str, str | None]] | None = None,
    clase_trabajo: Mapping[str, CategoriaExplosion] | None = None,
) -> tuple[
    tuple[ConceptoCargado, ...],
    tuple[ErrorDeFila, ...],
    tuple[PendientePropuesto, ...],
    int,
]:
    """Filas → bloques concepto+componentes, en cualquiera de los dos
    formatos del módulo (ver docstring de arriba).

    El modo se decide por columnas presentes en ``mapa.indices`` —nunca
    por un flag explícito del llamador—, mismo criterio que
    `presupuesto.construir_arboles`: ``clave_padre`` solo lo trae
    `cabeceras.CPU_MATRIZ` (la matriz nativa de OPUS); el formato plano
    del §10.6 no tiene esa columna. ``descripciones_concepto`` y
    ``clase_trabajo`` solo se usan en modo matriz —el plano ya trae su
    propia fila encabezado y nunca produce `CategoriaExplosion.TRABAJO`
    (ver `CATEGORIA_POR_TIPO`)— y se ignoran si el archivo resulta ser
    plano.

    ``clase_trabajo`` (clave del insumo → `DESTAJO`/`SUBCONTRATO`) la
    construye quien llama a partir de `CATALOGO_DE_TRABAJOS.csv`
    (§cabeceras.TRABAJOS_OPUS, §mano_de_obra.clase_de_trabajo). Sin ella
    —``None``, el default— el comportamiento es exactamente el de antes:
    todo `Tipo=Contrato` cae en la categoría genérica `TRABAJO` más el
    pendiente `TipoPendiente.TRABAJO_SIN_CLASE`.
    """
    if "clave_padre" in mapa.indices:
        bloques, errores, pendientes, omitidos = _agrupar_conceptos_matriz(
            filas, mapa, descripciones_concepto or {}, clase_trabajo
        )
        return bloques, (*validar_origen_y_tipo(filas, mapa), *errores), pendientes, omitidos
    return _agrupar_conceptos_plano(filas, mapa)
