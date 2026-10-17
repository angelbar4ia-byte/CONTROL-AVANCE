"""Cargador de ingeniería del lote: qué se planeó comprar/usar en una casa
real, ANTES de construir (cerebro `CONOCIMIENTO.md` §11.4-§11.9).

**Contrato distinto a TODOS los demás cargadores de este paquete, y hay que
decirlo explícito: este archivo NO TIENE ENCABEZADOS.** Cada uno de los
`domain/cargadores/*.py` existentes recibe ``(filas, MapaColumnas)`` porque
alguien, en algún lado, nombró las columnas — por texto (§8.6) o por letra
fija (§10.6). Aquí no hay fila de encabezado que leer: la ingeniería del
lote es una tabla sin cabecera cuyo significado por columna se reconoce
**por los datos**, nunca por nombre (CONOCIMIENTO.md §11.4, "Sin
encabezados: hay que reconocer qué columna es qué por los datos, no por el
nombre"). Por eso este módulo no usa `cabeceras.resolver_encabezados` ni
`MapaColumnas`: sus funciones reciben directamente listas de celdas, con la
posición fija que el propio formato define (col 0 = clave del agrupador,
col 1 = clave del insumo, col 2 = descripción, col 3 = unidad, col 4 =
cantidad, col 5 = precio, col 6 = importe — CONOCIMIENTO.md §11.5), y la
detectan por **ancho de columna**, no por un encabezado que no existe.

**Las cinco estructuras** (CONOCIMIENTO.md §11.8), detectadas por conteo de
columnas y presencia/ausencia de agrupador — nunca por el nombre del
archivo ni por un flag explícito:

- **COMPLETA** — 7 columnas, con al menos un agrupador cuya clave empieza
  con ``NIV-``/``ECO-``: la fila trae etapa/nivel de verdad.
- **SUELTA** — 7 columnas, columna 0 siempre vacía: nunca hay agrupador, la
  fila no dice a qué etapa pertenece (solo el *nombre del archivo* lo dice,
  y eso queda fuera de este módulo puro — lo decide quien orquesta la
  carga, §11.8: "la estructura vive en el nombre, no en el contenido").
- **CON_CONCEPTO** — 7 columnas, con agrupador, pero su clave NO empieza
  con ``NIV-``/``ECO-``: el agrupador es un concepto (p. ej. ``ALB-01212``,
  §11.8).
- **SIN_COSTEAR** — 7 columnas, con agrupador ``NIV-``/``ECO-``, pero al
  menos una fila de insumo sin clave (columna 1 vacía) y sin precio/importe
  — no identificable ni valuable, nunca se inventa ninguno de los dos
  (§11.8).
- **AJENA** — ancho de columna distinto de 7: título y encabezados propios,
  columnas corridas, clave embebida en la descripción (§11.8, ej.
  ``CIM_CAMARAS.csv``, 5 columnas). Esta fase no la parsea: se reporta como
  pendiente crítico (`TipoPendiente.ESTRUCTURA_AJENA_SIN_PARSEAR`) para que
  alguien la trabaje aparte — inventar una extracción por regex sobre la
  descripción sería adivinar un contrato que el archivo no da (§3.3).

**Partición en bloques** (§11.8): una fila completamente vacía es parte de
una "racha" de blancos; al cerrar la racha, lo que sigue es un agrupador
nuevo o el archivo se acaba. Verificado contra los 4 archivos grandes de
`ALAMO 18`: 159 rachas de blancos en total, de las cuales 4 son la fila en
blanco de apertura de cada archivo (antes de su primer bloque, no un
separador ENTRE bloques) — las 155 restantes sí son separador real: 151
seguidas de un agrupador y 4 que cierran el archivo, igual que el cerebro
reporta (líneas 2233-2235 de `CONOCIMIENTO.md`). `particionar_bloques` no
distingue ese detalle de conteo (una lista de bloques no necesita saberlo);
lo dejamos anotado aquí porque es la clase de discrepancia que este
encargo pide verificar, no copiar.

**La etapa/agrupador vigente se arrastra, nunca se reinicia por bloque**
(mismo criterio que ``_insumos_por_etapa`` de
`backend/core/tests/test_reversion_alamo18.py` del cerebro, traducido con
fidelidad): dentro de un bloque "completo" puede haber agrupadores
anidados (`NIV-00001` → `ECO-00001` → `EST-01060`, este último un concepto
auxiliar con su propia MO ancla, §11.13) sin que una fila en blanco los
separe — por eso una sola pasada, de arriba a abajo del archivo, arrastra
dos variables independientes:

- ``agrupador`` — la clave del último renglón "solo agrupador" visto (col 0
  con clave, col 1 vacía, col 2 con descripción), de cualquier prefijo.
- ``etapa`` — igual, pero **solo** cuando ese agrupador empieza con
  ``ECO-``: es el nivel que de verdad importa para identificar y revertir
  (CONOCIMIENTO.md §11.9/D-489: "los candidatos de un destajo son los
  conceptos de **su misma etapa** (`ECO-`)"), y es justo el que
  ``_insumos_por_etapa`` del cerebro actualiza.

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from obractrl.domain.cargadores.reporte import (
    ErrorDeFila,
    PendientePropuesto,
    TipoPendiente,
)
from obractrl.domain.shared.valores import Clave

__all__ = [
    "ES_DESTAJO",
    "BloqueIngenieria",
    "FilaInsumoIngenieria",
    "LoteIngenieriaLeido",
    "TipoEstructuraIngenieria",
    "detectar_estructura",
    "leer_ingenieria_lote",
    "particionar_bloques",
]


class TipoEstructuraIngenieria(StrEnum):
    """Las cinco formas en que llega un archivo de ingeniería del lote
    (CONOCIMIENTO.md §11.8). Ver el docstring del módulo para el criterio
    exacto de detección de cada una."""

    COMPLETA = "completa"
    SUELTA = "suelta"
    CON_CONCEPTO = "con_concepto"
    SIN_COSTEAR = "sin_costear"
    AJENA = "ajena"


ES_DESTAJO = re.compile(r"MO[A-Z]?-")
"""Huella de un insumo-destajo (mano de obra/cuadrilla): ``MO-``, ``MOA-``,
``MOC-``, ``MOE-``, ``MOG-``, ``MOH-``, ``MOS-``... Traducido tal cual de
`backend/core/tests/test_reversion_alamo18.py::ES_DESTAJO` del cerebro —
``.match()`` (no ``.search()``), así que ancla al principio de la clave sin
necesitar un ``^`` explícito."""

_PREFIJO_ETAPA = re.compile(r"^ECO-")
_ANCHO_ESPERADO = 7


def _vacio(celda: str) -> bool:
    return not celda.strip()


def _es_fila_en_blanco(fila: Sequence[str]) -> bool:
    return all(_vacio(c) for c in fila)


def _es_agrupador(fila: Sequence[str]) -> bool:
    """Col 0 con clave, col 1 vacía, col 2 con descripción (§11.5/§11.8).

    Es la fila "solo agrupador": una etapa/nivel, o un concepto que abre su
    propio bloque (`CON_CONCEPTO`, o un concepto auxiliar anidado dentro de
    uno `COMPLETA`, §11.13). Se repite literal, sin reinterpretarla, porque
    es el mismo predicado que usa la referencia del cerebro para decidir
    cuándo actualizar la etapa vigente.
    """
    return not _vacio(fila[0]) and _vacio(fila[1]) and not _vacio(fila[2])


def _es_insumo_sin_clave(fila: Sequence[str]) -> bool:
    """Col 0 y col 1 vacías, col 2 con descripción: una línea de insumo sin
    identidad (`SIN_COSTEAR`, §11.8) — nunca se confunde con una fila en
    blanco (que no tiene ni descripción) ni con un agrupador (que tiene
    col 0)."""
    return _vacio(fila[0]) and _vacio(fila[1]) and not _vacio(fila[2])


def detectar_estructura(filas: Sequence[Sequence[str]]) -> TipoEstructuraIngenieria:
    """Una de las cinco estructuras del §11.8, por conteo de columnas y
    presencia/ausencia de agrupador — nunca por el nombre del archivo.

    El orden de las comprobaciones importa y está documentado en el módulo:
    ancho de columna primero (decide `AJENA` de un plumazo, porque sin 7
    columnas ninguna otra regla tiene sentido), después "¿hay algún
    agrupador?" (decide `SUELTA`), después "¿hay alguna línea sin clave?"
    (decide `SIN_COSTEAR`: el archivo real de `ALAMO 18` que la define,
    `AJU._GUALDRA_PB.csv`, SÍ trae agrupador `NIV-`/`ECO-` además de la
    línea sin clave — por eso esta regla va antes de la de `CON_CONCEPTO`,
    no después), y al final "¿algún agrupador es `NIV-`/`ECO-`?" (decide
    entre `COMPLETA` y `CON_CONCEPTO`).
    """
    if not filas:
        return TipoEstructuraIngenieria.AJENA
    if len(filas[0]) != _ANCHO_ESPERADO:
        return TipoEstructuraIngenieria.AJENA

    agrupadores = [f for f in filas if _es_agrupador(f)]
    if not agrupadores:
        return TipoEstructuraIngenieria.SUELTA
    if any(_es_insumo_sin_clave(f) for f in filas):
        return TipoEstructuraIngenieria.SIN_COSTEAR
    if any(_PREFIJO_ETAPA.match(f[0].strip()) or f[0].strip().startswith("NIV-") for f in agrupadores):
        return TipoEstructuraIngenieria.COMPLETA
    return TipoEstructuraIngenieria.CON_CONCEPTO


@dataclass(frozen=True, slots=True)
class FilaInsumoIngenieria:
    """Una línea de insumo ya validada, con la etapa/agrupador que le tocó
    al recorrer el archivo de arriba a abajo (§11.5, §11.9)."""

    clave: str
    descripcion: str
    unidad: str | None
    cantidad: Decimal
    precio: Decimal | None
    importe: Decimal | None
    etapa: str | None
    """El último agrupador `ECO-` visto antes de esta fila, o ``None`` si
    el archivo no trae ninguno todavía (`SUELTA`, o antes del primer `ECO-`
    de un `COMPLETA`). Es lo que consume la reversión por destajo
    (§11.9/D-489): "los candidatos ... son los conceptos de ESA MISMA
    etapa"."""

    agrupador: str | None
    """El último agrupador de CUALQUIER prefijo visto antes de esta fila
    (`NIV-`, `ECO-`, un concepto auxiliar como `EST-01060`, o el concepto
    de un archivo `CON_CONCEPTO`). Más fino que `etapa`; no lo usa la
    reversión de esta fase, pero es la información que el §11.4 pide no
    tirar ("arrastra el último agrupador visto")."""

    fila: int

    @property
    def es_destajo(self) -> bool:
        return bool(ES_DESTAJO.match(self.clave))


@dataclass(frozen=True, slots=True)
class BloqueIngenieria:
    """Un tramo del archivo entre dos rachas de blancos (§11.8).

    No se usa para decidir la etapa/agrupador de una `FilaInsumoIngenieria`
    (eso lo hace la pasada continua de `leer_ingenieria_lote`, que no se
    reinicia en cada bloque — ver el docstring del módulo); esta es la
    unidad estructural que el §11.8 verifica aparte ("155 bloques de filas
    vacías").
    """

    fila_inicio: int
    fila_fin: int
    abre_con_agrupador: bool
    agrupador: str | None
    insumos: tuple[FilaInsumoIngenieria, ...]


def particionar_bloques(
    filas_insumo: Sequence[FilaInsumoIngenieria], filas_crudas: Sequence[Sequence[str]]
) -> tuple[BloqueIngenieria, ...]:
    """Parte el archivo en bloques separados por rachas de filas en blanco.

    Recibe las filas crudas (para encontrar las rachas de blancos por
    posición) y las `FilaInsumoIngenieria` ya validadas (para no volver a
    parsear números): cada bloque se queda con las que caen en su rango de
    filas. La fila en blanco de apertura del archivo (antes de que exista
    ningún bloque) no abre un bloque vacío — no es "el separador entre dos
    bloques" del §11.8, es el formato que trae el exportador antes del
    primer agrupador (ver el docstring del módulo: 159 rachas en los 4
    archivos grandes, 4 de ellas justamente esta apertura).
    """
    bloques: list[BloqueIngenieria] = []
    n = len(filas_crudas)
    rangos: list[tuple[int, int]] = []
    inicio_actual: int | None = None
    vio_contenido = False
    for idx, fila in enumerate(filas_crudas):
        if _es_fila_en_blanco(fila):
            if inicio_actual is not None and vio_contenido:
                rangos.append((inicio_actual, idx))
                inicio_actual = None
                vio_contenido = False
            continue
        if inicio_actual is None:
            inicio_actual = idx
        vio_contenido = True
    if inicio_actual is not None and vio_contenido:
        rangos.append((inicio_actual, n))

    por_fila = {f.fila: f for f in filas_insumo}
    for inicio, fin in rangos:
        agrupador = filas_crudas[inicio][0].strip() if _es_agrupador(filas_crudas[inicio]) else None
        insumos = tuple(
            por_fila[idx] for idx in range(inicio, fin) if idx in por_fila
        )
        bloques.append(
            BloqueIngenieria(
                fila_inicio=inicio,
                fila_fin=fin,
                abre_con_agrupador=agrupador is not None,
                agrupador=agrupador,
                insumos=insumos,
            )
        )
    return tuple(bloques)


@dataclass(frozen=True, slots=True)
class LoteIngenieriaLeido:
    """Empaqueta el resultado de :func:`leer_ingenieria_lote` como un único
    ``registro`` de `LecturaCarga` (mismo patrón que
    `domain.cargadores.cpu.FilasMatrizSinAgrupar`): el adaptador de Excel
    (`adapters.excel.cargadores.CargadorIngenieriaLote`) no tiene acceso a
    la base (§12.11) y por eso no puede resolver nada contra el catálogo —
    solo envuelve lo que el dominio puro ya decidió. Es
    `AplicadorIngenieriaLote.aplicar()` quien desempaqueta esto e inyecta
    los repositorios que hacen falta."""

    estructura: TipoEstructuraIngenieria
    insumos: tuple[FilaInsumoIngenieria, ...]
    bloques: tuple[BloqueIngenieria, ...]


def _decimal_opcional(celda: str) -> Decimal | None:
    """`$1,234.56` → `Decimal`; vacío o `-` → `None` (mismo criterio que
    `_numero` de los dos archivos de prueba del cerebro, nunca `float`)."""
    limpio = celda.replace("$", "").replace(",", "").strip()
    if limpio in ("", "-"):
        return None
    try:
        return Decimal(limpio)
    except InvalidOperation:
        return None


def leer_ingenieria_lote(
    filas: Sequence[Sequence[str]],
) -> tuple[
    TipoEstructuraIngenieria,
    tuple[FilaInsumoIngenieria, ...],
    tuple[BloqueIngenieria, ...],
    tuple[ErrorDeFila, ...],
    tuple[PendientePropuesto, ...],
]:
    """Lee un archivo completo de ingeniería del lote: estructura, filas de
    insumo validadas, bloques, errores y pendientes.

    `filas` son celdas de texto crudas, en el orden del archivo, SIN fila de
    encabezado (ver el docstring del módulo). ``fila`` en cada error/
    pendiente/`FilaInsumoIngenieria` es el índice base 0 dentro de esta
    lista — quien la invoque desde un adaptador de Excel/CSV decide cómo
    traducirlo al número de renglón real del archivo.

    Devuelve siempre los cinco elementos, incluso para `AJENA`: ahí
    ``insumos``/``bloques`` salen vacíos y el único pendiente es
    `TipoPendiente.ESTRUCTURA_AJENA_SIN_PARSEAR`, marcado crítico — esta
    fase no intenta extraer la clave embebida en la descripción (§11.8).
    """
    estructura = detectar_estructura(filas)

    if estructura is TipoEstructuraIngenieria.AJENA:
        pendiente = PendientePropuesto(
            tipo=TipoPendiente.ESTRUCTURA_AJENA_SIN_PARSEAR,
            entidad="ingenieria_lote",
            valor_origen=f"ancho={len(filas[0]) if filas else 0}",
            propuesta={
                "motivo": (
                    "Ancho de columna distinto de 7, con título/encabezados "
                    "propios y clave embebida en la descripción (§11.8). "
                    "Esta fase no la parsea automáticamente."
                )
            },
            critico=True,
        )
        return estructura, (), (), (), (pendiente,)

    insumos: list[FilaInsumoIngenieria] = []
    errores: list[ErrorDeFila] = []
    pendientes: list[PendientePropuesto] = []
    agrupador: str | None = None
    etapa: str | None = None

    for idx, fila in enumerate(filas):
        if _es_fila_en_blanco(fila):
            continue
        if _es_agrupador(fila):
            clave_agrupador = fila[0].strip()
            agrupador = clave_agrupador
            if _PREFIJO_ETAPA.match(clave_agrupador):
                etapa = clave_agrupador
            continue
        if _es_insumo_sin_clave(fila):
            pendientes.append(
                PendientePropuesto(
                    tipo=TipoPendiente.INSUMO_SIN_COSTEAR,
                    entidad="fila_insumo_ingenieria",
                    valor_origen=fila[2].strip(),
                    propuesta={
                        "etapa": etapa,
                        "agrupador": agrupador,
                        "motivo": "Sin clave de insumo y sin precio/importe (§11.8).",
                    },
                    origen_ref=f"fila {idx}",
                )
            )
            continue

        # Ni fila en blanco, ni agrupador, ni insumo sin clave (los tres
        # casos ya se atendieron arriba): lo que queda sin clave (col 1
        # vacía) no es un patrón verificado en los 11 archivos reales — se
        # ignora en silencio solo porque de verdad no trae nada legible.
        clave_celda = fila[1].strip()
        if not clave_celda:
            continue
        cantidad = _decimal_opcional(fila[4]) if len(fila) > 4 else None
        if cantidad is None:
            errores.append(
                ErrorDeFila(
                    fila=idx,
                    columna="cantidad",
                    valor=fila[4] if len(fila) > 4 else None,
                    motivo="cantidad: la fila trae clave de insumo pero la cantidad no es un número (§11.5).",
                )
            )
            continue
        try:
            clave = str(Clave(clave_celda))
        except ValueError as exc:
            errores.append(ErrorDeFila(fila=idx, columna="clave", valor=clave_celda, motivo=str(exc)))
            continue

        insumos.append(
            FilaInsumoIngenieria(
                clave=clave,
                descripcion=fila[2].strip(),
                unidad=fila[3].strip() or None,
                cantidad=cantidad,
                precio=_decimal_opcional(fila[5]) if len(fila) > 5 else None,
                importe=_decimal_opcional(fila[6]) if len(fila) > 6 else None,
                etapa=etapa,
                agrupador=agrupador,
                fila=idx,
            )
        )

    bloques = particionar_bloques(insumos, filas)
    return estructura, tuple(insumos), bloques, tuple(errores), tuple(pendientes)
