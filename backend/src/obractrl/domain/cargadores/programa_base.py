"""Cargador del programa base de un prototipo: el cronograma real (extensión
propia, no está en el §10.6).

Spec §7.5 (`ProgramaBase`/`ProgramaBaseItem`) · §6 (ruta crítica) · §10.3
(bandeja de pendientes) · cerebro `1-mundo/PROGRAMA-CPM.md` y `MODELO.md`
§5c (D-442, D-443) — la referencia funcional completa de este archivo real,
ya cargado una vez por `backend/core/programa.py`.

**El archivo real** (`PROGRAMA_<PROTOTIPO>.xlsx`, hoja `Hoja1` —`Hoja2` es un
histograma de recurso por periodo sin encabezados ni columnas de identidad,
y no se lee, ver `cabeceras.PROGRAMA_BASE`—) trae, apilados uno tras otro,
los programas de **varios** prototipos (siete, en el archivo real de
Zafiro): cada bloque arranca en una fila `Tipo=Capítulo` y termina donde
empieza el siguiente `Capítulo`, igual que `CATALOGO_DE_PRESUPUESTO.csv`
(`domain.cargadores.presupuesto`). Este módulo separa el archivo en un
:class:`BloqueProgramaCargado` por `Capítulo`; el aplicador elige el que
corresponde al `prototipo_id` pedido (§11.3 G: se declara explícito antes de
subir, nunca se adivina del archivo).

**La jerarquía se reconstruye por `Nivel` + posición, nunca por un
`clave_padre`** que este archivo no trae (a diferencia del árbol nativo de
OPUS que `presupuesto.construir_arboles` sí puede leer por esa columna): una
pila de `(nivel, clave)` que se vacía cuando aparece una fila de nivel igual
o menor, mismo principio que esa función pero sin sus reglas de huecos y de
WBS —aquí no hacen falta, el único dato que importa de cada fila es su
`ruta` (la cadena de claves ancestro→…→propia, sin el `Capítulo` raíz).

**Por qué `ruta` y no `clave` a secas.** La misma clave de `CONCEPTO` puede
colgar de dos `Subcapítulo`/`Nivel 2`/`Nivel 3` distintos del mismo
prototipo (confirmado contra el archivo real: 18 claves de concepto se
repiten solo dentro del bloque de Zafiro) — el mismo caso de negocio que ya
resolvió `prototipo_nodo.uq_prototipo_nodo_posicion` (migración 0038,
`(prototipo_id, parent_id, clave)`). Resolver por clave sola sería
ambigüedad real; `ruta` es exactamente esa misma identidad, llevada
recursivamente hasta la raíz, y es lo que el aplicador cruza contra el árbol
de `prototipo_nodo` YA cargado (`application.casos_uso.aplicar_carga.
AplicadorProgramaBase`) para encontrar el `prototipo_nodo_id` estable.

**Vínculos** (columna `Vínculos`, D-442/D-443): el texto fuente
``<fila><FS|SS|FF|SF>[±horas]``, varias separadas por coma
(``"80SF, 68SS+120.00000"``). La predecesora se cita por **número de fila
del archivo**, que no es estable (cambia si alguien inserta un renglón) —
por eso `resolver_vinculos` solo entrega aquí la predecesora **resuelta a
otra fila del archivo** (`fila_predecesora`, un `int`), nunca el texto
crudo; es el aplicador quien la traduce a algo verdaderamente estable (el
`prototipo_nodo_id` de esa fila, §6 `Dependencia.ref`), porque esa
traducción necesita el árbol ya cargado en la base.

El desfase viene en **horas** y la jornada es de 8 (D-442/D-443,
`_JORNADA_HORAS`): se convierte a días dividiendo entre 8 antes de construir
cualquier dependencia.

**Un bloque también puede ser predecesora** (D-442, corregido por D-443:
"se lee sin ella" — sin la propia sucesora). El motor CPM de ObraCtrl
(`domain.programacion.cpm`) no modela actividades-bloque como el
`motor_cpm.py` de cerebro —cada `Dependencia.ref` apunta siempre a una
actividad concreta—, así que aquí el bloque se resuelve de inmediato a la
partida concreta que fija su extremo (D-443: el máximo `término` entre sus
partidas para `FS`/`FF`, el mínimo `inicio` para `SS`/`SF`, excluyendo
siempre a la propia sucesora); el empate lo rompe la fila más chica del
archivo, de forma determinista. Si el bloque no tiene ninguna partida que no
sea la propia sucesora, el vínculo se rechaza (`predecesora_sin_partidas`).

**Ciclos y vínculos incumplidos** (D-442/D-443): se rechazan el autovínculo
y los ciclos reales; de un ciclo se rechaza el vínculo cuya holgura —medida
con las fechas que el propio archivo ya trae, en días de calendario, igual
que hace cerebro— ya es negativa, y si ninguno la tiene, el que cae en la
fila más alta del archivo (la lectura más simple de "el último que se
escribió" sobre un archivo estático, sin historial de edición: el renglón
que aparece más abajo). Un vínculo rechazado no detiene la carga
(`TipoPendiente.VINCULO_RECHAZADO`, no crítico); uno que las fechas
contradicen pero no cierra ciclo **sí se carga**, marcado con
`TipoPendiente.VINCULO_INCUMPLIDO` (también no crítico).

Solo un `Concepto` con fecha de inicio y días de trabajo positivos es una
partida —lo único que el CPM programa de verdad—; los bloques
(`Capítulo`/`Subcapítulo`/`Nivel 2`/`Nivel 3`) no.

`dias_laborables` (no `dias_calendario`) es la cifra que se guarda en
`ItemProgramaBase.duracion_dias`: es la convención ya establecida en
`domain.programacion.calendario`/`cpm` (duración en la escala del calendario
del cronograma, nunca corridos a secas).

Módulo puro: recibe filas ya resueltas por columna (`MapaColumnas`) y
devuelve dataclasses; no toca la BD ni abre el archivo (§12.11).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.reporte import ErrorDeFila, ErrorEnFila
from obractrl.domain.shared.normalizacion import (
    ValorNoConvertible,
    a_decimal,
    a_entero,
    a_fecha,
    esta_vacio,
    texto_limpio,
)
from obractrl.domain.shared.valores import Clave

__all__ = [
    "TOKEN_VINCULO",
    "BloqueProgramaCargado",
    "DependenciaResuelta",
    "FilaProgramaBase",
    "ProgramaLeido",
    "RechazoVinculo",
    "TokenVinculo",
    "VinculoIncumplido",
    "leer_programa_base",
    "resolver_vinculos",
]

TOKEN_VINCULO = re.compile(r"^(\d+)(FS|SS|FF|SF)([+-]\d+(?:\.\d+)?)?$")
"""Formato fuente de un vínculo, traducido fiel de cerebro
(`backend/core/programa.py::TOKEN`): número de fila + tipo (MS Project) +
desfase opcional en horas, con signo."""

_JORNADA_HORAS = 8.0
"""El desfase del archivo viene en horas y la jornada es de 8 (D-442/D-443,
`1-mundo/MODELO.md` §5c): se divide entre esto para obtener días."""

_TIPOS_DE_FILA = ("Capítulo", "Subcapítulo", "Nivel 2", "Nivel 3", "Concepto")
"""Los cinco tipos de renglón del archivo real — mismos que documenta
cerebro (`programa.py::TIPOS_DE_FILA`)."""

_TIPOS_CON_SUBARBOL = frozenset({"Subcapítulo", "Nivel 2", "Nivel 3"})
"""Los que pueden ser predecesora-bloque de D-442/D-443 (nunca `Capítulo`:
sería predecesora de todo el programa, y el archivo real no cita ninguno)."""


@dataclass(frozen=True, slots=True)
class TokenVinculo:
    """Un vínculo ya separado de su celda, antes de resolverlo contra el
    archivo (§formato del módulo). `fila_predecesora` es `None` cuando el
    texto no cumple `TOKEN_VINCULO` — se conserva para reportarlo, no se
    pierde la fila entera por un solo token mal escrito."""

    texto: str
    fila_predecesora: int | None
    tipo: str = ""
    lag_dias: float = 0.0


def leer_vinculos(texto: str) -> tuple[TokenVinculo, ...]:
    """Separa el texto fuente de una celda en sus tokens (§formato del
    módulo), traducción fiel de cerebro (`programa.py::leer_vinculos`)."""
    tokens: list[TokenVinculo] = []
    for crudo in texto.split(","):
        token = crudo.strip()
        if not token:
            continue
        coincide = TOKEN_VINCULO.match(token)
        if coincide is None:
            tokens.append(TokenVinculo(texto=token, fila_predecesora=None))
            continue
        horas = float(coincide.group(3) or 0)
        tokens.append(
            TokenVinculo(
                texto=token,
                fila_predecesora=int(coincide.group(1)),
                tipo=coincide.group(2),
                lag_dias=horas / _JORNADA_HORAS,
            )
        )
    return tuple(tokens)


@dataclass(frozen=True, slots=True)
class FilaProgramaBase:
    """Un renglón del archivo real, ya tipado (§formato del módulo)."""

    fila: int
    """Número de fila del archivo (base 1, contando el encabezado) — lo que
    cita la columna `Vínculos` de otras filas. No es una identidad estable
    fuera de este archivo (ver `ruta`)."""

    tipo: str
    nivel: int
    clave: str | None
    descripcion: str | None
    inicio: date | None = None
    termino: date | None = None
    dias_laborables: Decimal = Decimal(0)
    vinculos: tuple[TokenVinculo, ...] = ()
    ruta: tuple[str, ...] = ()
    """Cadena de claves del `Capítulo`/raíz hacia esta fila, sin el propio
    `Capítulo` (igual que `prototipo_nodo`, cuyos nodos de primer nivel
    tienen `parent_id is null`): identidad estable de la fila dentro de su
    prototipo, inmune a que la misma clave se repita bajo otro padre."""

    @property
    def es_partida(self) -> bool:
        """Un `Concepto` con clave, fecha de inicio y días positivos: lo
        único que el CPM programa de verdad (cerebro `programa.py::
        Fila.es_partida`)."""
        return (
            self.tipo == "Concepto"
            and bool(self.clave)
            and self.inicio is not None
            and self.dias_laborables > 0
        )


@dataclass(frozen=True, slots=True)
class BloqueProgramaCargado:
    """El programa de **un** prototipo dentro del archivo (§formato del
    módulo): desde su fila `Capítulo` hasta la última antes del siguiente."""

    clave_prototipo: str
    filas: tuple[FilaProgramaBase, ...]
    por_fila: dict[int, FilaProgramaBase] = field(default_factory=dict)
    """Índice rápido por número de fila del archivo, para resolver los
    tokens de `Vínculos` (que citan filas, nunca claves) en una sola
    pasada."""

    @property
    def partidas(self) -> tuple[FilaProgramaBase, ...]:
        return tuple(f for f in self.filas if f.es_partida)


def _a_entero_opcional(celda: object, *, columna: str) -> int | None:
    if esta_vacio(celda):
        return None
    try:
        return a_entero(celda, campo=columna)
    except ValorNoConvertible as exc:
        raise ErrorEnFila(str(exc), columna=columna, valor=celda) from exc


def _a_decimal_opcional(celda: object, *, columna: str) -> Decimal:
    if esta_vacio(celda):
        return Decimal(0)
    try:
        valor = a_decimal(celda, campo=columna)
    except ValorNoConvertible as exc:
        raise ErrorEnFila(str(exc), columna=columna, valor=celda) from exc
    if valor < 0:
        raise ErrorEnFila(
            f"{columna}: no puede ser negativo ({valor}).", columna=columna, valor=celda
        )
    return valor


def _a_fecha_opcional(celda: object, *, columna: str) -> date | None:
    if esta_vacio(celda):
        return None
    try:
        return a_fecha(celda, campo=columna)
    except ValorNoConvertible as exc:
        raise ErrorEnFila(str(exc), columna=columna, valor=celda) from exc


def _leer_fila(fila: Sequence[object], mapa: MapaColumnas, numero: int) -> FilaProgramaBase:
    crudo_tipo = texto_limpio(mapa.valor(fila, "tipo"))
    if crudo_tipo not in _TIPOS_DE_FILA:
        raise ErrorEnFila(
            f"tipo: {crudo_tipo!r} no es uno de los valores esperados "
            f"({', '.join(_TIPOS_DE_FILA)}).",
            columna="tipo",
            valor=crudo_tipo,
        )

    nivel = _a_entero_opcional(mapa.valor(fila, "nivel"), columna="nivel")
    if nivel is None:
        raise ErrorEnFila(
            "nivel: toda fila la necesita — es lo único que arma el árbol "
            "de este archivo (no trae clave_padre).",
            columna="nivel",
        )
    if nivel < 0:
        raise ErrorEnFila(f"nivel: no puede ser negativo ({nivel}).", columna="nivel", valor=nivel)

    celda_clave = mapa.valor(fila, "clave")
    clave = None if esta_vacio(celda_clave) else str(Clave(str(celda_clave)))
    descripcion = texto_limpio(mapa.valor(fila, "descripcion")) or None

    inicio = _a_fecha_opcional(mapa.valor(fila, "fecha_inicio"), columna="fecha_inicio")
    termino = _a_fecha_opcional(mapa.valor(fila, "fecha_termino"), columna="fecha_termino")
    if inicio is not None and termino is not None and termino < inicio:
        raise ErrorEnFila(
            f"fecha_termino: {termino} es anterior a fecha_inicio ({inicio}).",
            columna="fecha_termino",
            valor=termino,
        )

    dias = _a_decimal_opcional(mapa.valor(fila, "dias_laborables"), columna="dias_laborables")

    texto_vinculos = texto_limpio(mapa.valor(fila, "vinculos"))
    vinculos = leer_vinculos(texto_vinculos) if texto_vinculos else ()

    return FilaProgramaBase(
        fila=numero,
        tipo=crudo_tipo,
        nivel=nivel,
        clave=clave,
        descripcion=descripcion,
        inicio=inicio,
        termino=termino,
        dias_laborables=dias,
        vinculos=vinculos,
    )


def leer_programa_base(
    filas: Sequence[tuple[int, Sequence[object]]], mapa: MapaColumnas
) -> tuple[tuple[BloqueProgramaCargado, ...], tuple[ErrorDeFila, ...]]:
    """Filas planas del archivo real → un bloque por `Capítulo` (prototipo).

    Una fila mala no tumba el archivo (§9.3): se reporta y se sigue, igual
    que el resto de los cargadores. Una fila sin ningún `Capítulo` previo
    que la encabece tampoco tumba nada — simplemente no pertenece a ningún
    bloque y se reporta como tal.
    """
    bloques: list[BloqueProgramaCargado] = []
    errores: list[ErrorDeFila] = []

    clave_actual: str | None = None
    filas_actuales: list[FilaProgramaBase] = []
    pila: list[tuple[int, str]] = []
    """`(nivel, clave)` de los ancestros abiertos del bloque actual, sin el
    propio `Capítulo` — así `ruta` nace vacía para los hijos directos del
    prototipo, igual que `prototipo_nodo.parent_id is null`."""

    def cerrar() -> None:
        nonlocal clave_actual, filas_actuales, pila
        if clave_actual is not None:
            bloques.append(
                BloqueProgramaCargado(
                    clave_prototipo=clave_actual,
                    filas=tuple(filas_actuales),
                    por_fila={f.fila: f for f in filas_actuales},
                )
            )
        clave_actual, filas_actuales, pila = None, [], []

    for numero, cruda in filas:
        try:
            leida = _leer_fila(cruda, mapa, numero)
        except ErrorEnFila as exc:
            errores.append(exc.con_fila(numero))
            continue

        if leida.tipo == "Capítulo":
            cerrar()
            if leida.clave is None:
                errores.append(
                    ErrorDeFila(
                        fila=numero,
                        columna="clave",
                        motivo="Capítulo: la fila no trae la clave del prototipo.",
                    )
                )
                continue
            clave_actual = leida.clave
            filas_actuales.append(leida)
            continue

        if clave_actual is None:
            errores.append(
                ErrorDeFila(
                    fila=numero,
                    columna="tipo",
                    valor=leida.tipo,
                    motivo="Fila sin un Capítulo previo que la encabece: no hay bloque al que pertenece.",
                )
            )
            continue

        while pila and pila[-1][0] >= leida.nivel:
            pila.pop()
        ruta = tuple(clave for _, clave in pila) + ((leida.clave,) if leida.clave else ())
        con_ruta = FilaProgramaBase(
            fila=leida.fila,
            tipo=leida.tipo,
            nivel=leida.nivel,
            clave=leida.clave,
            descripcion=leida.descripcion,
            inicio=leida.inicio,
            termino=leida.termino,
            dias_laborables=leida.dias_laborables,
            vinculos=leida.vinculos,
            ruta=ruta,
        )
        filas_actuales.append(con_ruta)
        if leida.clave is not None:
            pila.append((leida.nivel, leida.clave))

    cerrar()
    return tuple(bloques), tuple(errores)


# --- Vínculos: D-442/D-443 ------------------------------------------------


@dataclass(frozen=True, slots=True)
class DependenciaResuelta:
    """Un vínculo aceptado, ya traducido a la partida concreta que lo fija
    (nunca a un bloque, D-443): `fila_predecesora` es siempre una fila
    `es_partida`."""

    fila_predecesora: int
    fila_sucesora: int
    tipo: str
    lag_dias: float


@dataclass(frozen=True, slots=True)
class RechazoVinculo:
    """Un vínculo que D-442/D-443 rechaza. No detiene la carga — el resto
    del programa se construye igual (`TipoPendiente.VINCULO_RECHAZADO`)."""

    fila_sucesora: int
    token: str
    motivo: str
    """``formato`` · ``autovinculo`` · ``predecesora_desconocida`` ·
    ``predecesora_sin_partidas`` · ``sucesora_bloque`` · ``cierra_un_ciclo``
    — mismo vocabulario que cerebro (`programa.py::Rechazado.motivo`)."""


@dataclass(frozen=True, slots=True)
class VinculoIncumplido:
    """Un vínculo que SÍ se carga pero cuyas fechas (las del propio
    archivo) lo contradicen — la alerta de D-442/D-443, no un error."""

    fila_predecesora: int
    fila_sucesora: int
    tipo: str
    lag_dias: float
    holgura: float


@dataclass(frozen=True, slots=True)
class ProgramaLeido:
    """El bloque de un prototipo con sus vínculos ya resueltos (D-442/D-443)."""

    bloque: BloqueProgramaCargado
    dependencias: tuple[DependenciaResuelta, ...]
    rechazos: tuple[RechazoVinculo, ...]
    incumplidos: tuple[VinculoIncumplido, ...]


def _descendientes_partida(bloque: BloqueProgramaCargado, fila_bloque: FilaProgramaBase) -> tuple[FilaProgramaBase, ...]:
    """Las partidas (`es_partida`) que cuelgan de este bloque, a cualquier
    profundidad — lo que D-442/D-443 llama "lo que el catálogo mete
    adentro"."""
    posiciones = {f.fila: i for i, f in enumerate(bloque.filas)}
    inicio = posiciones[fila_bloque.fila] + 1
    out: list[FilaProgramaBase] = []
    for f in bloque.filas[inicio:]:
        if f.nivel <= fila_bloque.nivel:
            break
        if f.es_partida:
            out.append(f)
    return tuple(out)


def _holgura(pred: FilaProgramaBase, suc: FilaProgramaBase, tipo: str, lag_dias: float) -> float:
    """Holgura del vínculo con las fechas que el propio archivo trae, en
    días de calendario (naturales) — una verificación de consistencia del
    archivo en sí, previa e independiente del calendario (laboral o
    natural) con el que el programa base termine instanciándose; mismas
    cuatro fórmulas que cerebro (`motor_cpm.py::holgura_vinculo`)."""
    assert pred.inicio is not None and pred.termino is not None  # noqa: S101 — es_partida ya lo exige
    assert suc.inicio is not None and suc.termino is not None  # noqa: S101
    if tipo == "FS":
        return (suc.inicio - pred.termino).days - 1 - lag_dias
    if tipo == "SS":
        return (suc.inicio - pred.inicio).days - lag_dias
    if tipo == "FF":
        return (suc.termino - pred.termino).days - lag_dias
    # "SF"
    return (suc.termino - pred.inicio).days - lag_dias


def _extremo_de_bloque(
    candidatas: Sequence[FilaProgramaBase], tipo: str
) -> FilaProgramaBase:
    """La partida que fija el extremo de un bloque leído sin su sucesora
    (D-443): el `término` más tardío para `FS`/`FF`, el `inicio` más
    temprano para `SS`/`SF`. El empate lo rompe la fila más chica del
    archivo, determinista."""
    if tipo in ("FS", "FF"):
        return min(candidatas, key=lambda f: (-_toordinal(f.termino), f.fila))
    return min(candidatas, key=lambda f: (_toordinal(f.inicio), f.fila))


def _toordinal(d: date | None) -> int:
    assert d is not None  # noqa: S101 — solo se llama sobre partidas
    return d.toordinal()


def _componente_con_ciclo(aristas: Sequence[tuple[int, int]]) -> frozenset[int] | None:
    """Un componente fuertemente conexo con más de un nodo (Kosaraju,
    iterativo), o `None` si el grafo es acíclico — mismo algoritmo que
    cerebro (`programa.py::_componente_con_ciclo`), aquí sobre filas."""
    siguientes: dict[int, list[int]] = {}
    anteriores: dict[int, list[int]] = {}
    nodos: list[int] = []
    for a, b in aristas:
        for n in (a, b):
            if n not in siguientes:
                siguientes[n], anteriores[n] = [], []
                nodos.append(n)
        siguientes[a].append(b)
        anteriores[b].append(a)

    visto: set[int] = set()
    orden: list[int] = []
    for inicio in nodos:
        if inicio in visto:
            continue
        pila: list[tuple[int, int]] = [(inicio, 0)]
        visto.add(inicio)
        while pila:
            nodo, i = pila[-1]
            vecinos = siguientes[nodo]
            if i < len(vecinos):
                pila[-1] = (nodo, i + 1)
                vecino = vecinos[i]
                if vecino not in visto:
                    visto.add(vecino)
                    pila.append((vecino, 0))
            else:
                orden.append(nodo)
                pila.pop()

    asignado: dict[int, int] = {}
    for nodo in reversed(orden):
        if nodo in asignado:
            continue
        componente = [nodo]
        asignado[nodo] = 1
        pendientes = [nodo]
        while pendientes:
            n = pendientes.pop()
            for m in anteriores[n]:
                if m not in asignado:
                    asignado[m] = 1
                    componente.append(m)
                    pendientes.append(m)
        if len(componente) > 1:
            return frozenset(componente)
    return None


def resolver_vinculos(bloque: BloqueProgramaCargado) -> ProgramaLeido:
    """Resuelve los vínculos de un bloque contra sus propias filas
    (D-442/D-443). Nunca contra otro bloque — un token siempre cita una
    fila del mismo archivo, y el archivo real no mezcla prototipos en una
    sola celda de `Vínculos`."""
    aceptados: list[tuple[int, int, str, float]] = []
    rechazos: list[RechazoVinculo] = []

    for sucesora in bloque.filas:
        if not sucesora.vinculos:
            continue
        if not sucesora.es_partida:
            for token in sucesora.vinculos:
                rechazos.append(
                    RechazoVinculo(sucesora.fila, token.texto, "sucesora_bloque")
                )
            continue

        for token in sucesora.vinculos:
            if token.fila_predecesora is None:
                rechazos.append(RechazoVinculo(sucesora.fila, token.texto, "formato"))
                continue
            if token.fila_predecesora == sucesora.fila:
                rechazos.append(RechazoVinculo(sucesora.fila, token.texto, "autovinculo"))
                continue

            predecesora = bloque.por_fila.get(token.fila_predecesora)
            if predecesora is None:
                rechazos.append(
                    RechazoVinculo(sucesora.fila, token.texto, "predecesora_desconocida")
                )
                continue

            if predecesora.tipo == "Concepto":
                if not predecesora.es_partida:
                    rechazos.append(
                        RechazoVinculo(sucesora.fila, token.texto, "predecesora_desconocida")
                    )
                    continue
                aceptados.append((predecesora.fila, sucesora.fila, token.tipo, token.lag_dias))
                continue

            # Predecesora-bloque (D-442/D-443): se resuelve a la partida que
            # fija su extremo, "sin ella" (D-443) — nunca a la propia sucesora.
            candidatas = tuple(
                f for f in _descendientes_partida(bloque, predecesora) if f.fila != sucesora.fila
            )
            if not candidatas:
                rechazos.append(
                    RechazoVinculo(sucesora.fila, token.texto, "predecesora_sin_partidas")
                )
                continue
            extremo = _extremo_de_bloque(candidatas, token.tipo)
            aceptados.append((extremo.fila, sucesora.fila, token.tipo, token.lag_dias))

    aceptados = _sin_ciclos(aceptados, bloque, rechazos)

    incumplidos = [
        VinculoIncumplido(fp, fs, tipo, lag, holgura)
        for fp, fs, tipo, lag in aceptados
        if (holgura := _holgura(bloque.por_fila[fp], bloque.por_fila[fs], tipo, lag)) < 0
    ]

    return ProgramaLeido(
        bloque=bloque,
        dependencias=tuple(
            DependenciaResuelta(fp, fs, tipo, lag) for fp, fs, tipo, lag in aceptados
        ),
        rechazos=tuple(rechazos),
        incumplidos=tuple(incumplidos),
    )


def _sin_ciclos(
    aceptados: list[tuple[int, int, str, float]],
    bloque: BloqueProgramaCargado,
    rechazos: list[RechazoVinculo],
) -> list[tuple[int, int, str, float]]:
    """Quita, de cada ciclo real, el vínculo que las fechas del propio
    archivo ya contradicen (holgura negativa); si ninguno, el de la fila
    sucesora más alta —"el último que se escribió" no existe en un archivo
    estático sin historial, así que se interpreta como el renglón que
    aparece más abajo, de forma determinista y documentada.

    Todas las aristas ya citan partidas (los bloques se resolvieron antes),
    así que un solo ciclo de Kosaraju basta — a diferencia de cerebro
    (`programa.py::_sin_ciclos`), que necesita una segunda pasada porque ahí
    los bloques siguen siendo nodos del grafo hasta que el motor CPM falla.
    """
    vivos = list(aceptados)
    while True:
        componente = _componente_con_ciclo([(fp, fs) for fp, fs, _, _ in vivos])
        if componente is None:
            return vivos
        indices_del_ciclo = [
            i
            for i, (fp, fs, _, _) in enumerate(vivos)
            if fp in componente and fs in componente
        ]

        def peor(i: int) -> tuple[float, int]:
            fp, fs, tipo, lag = vivos[i]
            holgura = _holgura(bloque.por_fila[fp], bloque.por_fila[fs], tipo, lag)
            return (-holgura, fs)

        indice_a_quitar = max(indices_del_ciclo, key=peor)
        fp, fs, tipo, _lag = vivos.pop(indice_a_quitar)
        token = next(
            (t.texto for t in bloque.por_fila[fs].vinculos if t.fila_predecesora == fp and t.tipo == tipo),
            f"{fp}{tipo}",
        )
        rechazos.append(RechazoVinculo(fs, token, "cierra_un_ciclo"))
