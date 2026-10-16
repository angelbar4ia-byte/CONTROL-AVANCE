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
from dataclasses import dataclass, field
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
    "agrupar_conceptos",
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
destajo de subcontrato. El archivo que trae esa distinción fila por fila
(`CATALOGO_DE_TRABAJOS.xlsx`) no está disponible en ningún repo —decisión
confirmada con el usuario, no un heurístico de este módulo, que además el
cerebro prohíbe explícitamente (adivinar por el prefijo de la clave citó
fallos reales)—, así que cada fila así categorizada se marca también con
`TipoPendiente.TRABAJO_SIN_CLASE` (ver `_agrupar_conceptos_matriz`).
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


def _clave_de(celda: object, *, columna: str) -> Clave:
    if esta_vacio(celda):
        raise ErrorEnFila(
            f"{columna}: la fila no trae clave y la clave es única por "
            f"catálogo (§3.3).",
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


def _leer_encabezado(fila: Sequence[object], mapa: MapaColumnas, numero: int) -> EncabezadoCargado:
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
      TRABAJO` además marca la fila con el pendiente no crítico
      `TipoPendiente.TRABAJO_SIN_CLASE` (ver `CATEGORIA_POR_TIPO_MATRIZ`).
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
        if normalizar(mapa.valor(fila, "origen")) != "concepto":
            continue
        try:
            clave_padre = _clave_de(mapa.valor(fila, "clave_padre"), columna="clave_padre")
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
            componentes.append(componente)

            if categoria is CategoriaExplosion.TRABAJO:
                # No crítico (§10.3): la fila se carga igual con la
                # categoría genérica — esto solo marca para reclasificar
                # cuando llegue CATALOGO_DE_TRABAJOS.xlsx (ver
                # CATEGORIA_POR_TIPO_MATRIZ).
                pendientes.append(
                    PendientePropuesto(
                        tipo=TipoPendiente.TRABAJO_SIN_CLASE,
                        entidad="explosion",
                        valor_origen=str(componente.clave_insumo),
                        propuesta={
                            "motivo": (
                                "CATALOGO_DE_TRABAJOS.xlsx no disponible: "
                                "reclasificar a destajo/subcontrato cuando llegue."
                            ),
                            "opciones": ["destajo", "subcontrato"],
                        },
                        origen_ref=f"fila {numero}",
                    )
                )

        bloques.append(ConceptoCargado(encabezado=encabezado, componentes=tuple(componentes)))

    return tuple(bloques), tuple(errores), tuple(pendientes), 0


def agrupar_conceptos(
    filas: Sequence[tuple[int, Sequence[object]]],
    mapa: MapaColumnas,
    *,
    descripciones_concepto: Mapping[str, tuple[str, str | None]] | None = None,
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
    del §10.6 no tiene esa columna. ``descripciones_concepto`` solo se usa
    en modo matriz —el plano ya trae su propia fila encabezado— y se
    ignora si el archivo resulta ser plano.
    """
    if "clave_padre" in mapa.indices:
        return _agrupar_conceptos_matriz(filas, mapa, descripciones_concepto or {})
    return _agrupar_conceptos_plano(filas, mapa)
