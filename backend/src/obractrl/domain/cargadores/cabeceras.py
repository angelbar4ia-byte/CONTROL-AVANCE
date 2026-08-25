"""Cabeceras canónicas de carga — el contrato de los cargadores (§10.6).

Spec §10.6 (contrato exacto de columnas por archivo) · §8.6 (mapa de
sinónimos) · §10.2 (multi-archivo) · §3.3 (la CLAVE manda).

**Este módulo no inventa columnas.** Cada especificación cita el texto del
§10.6 que la sustenta; lo que el §10.6 no nombra, no está aquí. Dos formas de
resolver columnas, según lo que el §10.6 fije para cada archivo:

- **Por nombre** (almacén, materiales): el §10.6 da las cabeceras literales,
  así que se mapean por texto vía :func:`canonizar_encabezado` (§8.6).
- **Por posición** (CPU): el §10.6 fija *letras de columna*
  ("CLAVE concepto (A) … TIPO (I)"), no nombres. Mapear por nombre ahí sería
  suponer un encabezado que el contrato no da.

Módulo puro (§12.11).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from obractrl.domain.shared.normalizacion import canonizar_encabezado, normalizar

__all__ = [
    "ALMACEN",
    "COLUMNAS_CPU",
    "CPU",
    "MANO_DE_OBRA",
    "MAPA_CPU",
    "MATERIALES",
    "PRESUPUESTO",
    "PROTOTIPOS",
    "ColumnaPorLetra",
    "ErrorDeCabecera",
    "EspecificacionArchivo",
    "MapaColumnas",
    "indice_de_letra",
    "resolver_encabezados",
]


class ErrorDeCabecera(ValueError):
    """El archivo no cumple el contrato del §10.6.

    Es un error del **archivo entero**, no de una fila: sin las columnas clave
    no hay nada que validar renglón por renglón (§9.2).
    """


@dataclass(frozen=True, slots=True)
class EspecificacionArchivo:
    """Contrato de un archivo del §10.6."""

    tipo: str
    """Etiqueta legible del cargador, para los mensajes de error."""

    archivo: str
    """Nombre del archivo tal como lo cita el §10.6 (`CABECERAS_MATERIALES.xlsx`)."""

    hoja: str | None
    """Hoja que fija el §10.6 (`Consulta`, `EXPORTADOR`); ``None`` = la activa."""

    obligatorias: tuple[str, ...]
    """Campos canónicos sin los cuales el archivo no sirve (§3.3: la clave manda)."""

    opcionales: tuple[str, ...] = ()

    alias: dict[str, str] = field(default_factory=dict)
    """Cabecera literal del §10.6 (ya normalizada) → campo canónico.

    Gana sobre `ALIAS_ENCABEZADOS` (§8.6): dos archivos distintos pueden
    llamar distinto a lo mismo y el global no debe decidir por el contrato
    particular del archivo.
    """

    @property
    def canonicas(self) -> frozenset[str]:
        return frozenset(self.obligatorias) | frozenset(self.opcionales)


@dataclass(frozen=True, slots=True)
class MapaColumnas:
    """Campo canónico → índice de columna (base 0) en la hoja."""

    indices: dict[str, int]
    ignoradas: tuple[str, ...] = ()
    """Cabeceras del archivo que no mapean a ningún campo del contrato.

    No son un error: el archivo de almacén trae 46 columnas y el §10.6 solo
    nombra 16. Se listan para que el reporte diga qué se dejó fuera.
    """

    def valor(self, fila: Sequence[object], campo: str) -> object:
        """Celda de ``campo`` en ``fila``, o ``None`` si la columna no vino."""
        indice = self.indices.get(campo)
        if indice is None or indice >= len(fila):
            return None
        return fila[indice]


def resolver_encabezados(
    encabezados: Sequence[object], especificacion: EspecificacionArchivo
) -> MapaColumnas:
    """Fila de encabezados → mapa de columnas, homologando con el §8.6.

    Reglas, en este orden:

    1. El alias propio del archivo (§10.6) gana sobre el mapa global (§8.6).
    2. Solo se conservan los campos que la especificación declara: el archivo
       de almacén trae 46 columnas y nombrar las otras 30 sería inventar
       contrato.
    3. Dos columnas hacia el mismo campo canónico: gana la que resolvió por
       alias del archivo. Si ambas resolvieron igual de fuerte, es ambigüedad
       real y el archivo se rechaza —adivinar cuál es la buena es justo lo que
       el §3.3 prohíbe.
    4. Falta una obligatoria → :class:`ErrorDeCabecera`.
    """
    indices: dict[str, int] = {}
    por_alias_propio: set[str] = set()
    ignoradas: list[str] = []

    for posicion, crudo in enumerate(encabezados):
        texto = normalizar(crudo)
        if not texto:
            continue

        propio = especificacion.alias.get(texto)
        canonico = propio or canonizar_encabezado(crudo)
        if canonico is None or canonico not in especificacion.canonicas:
            ignoradas.append(str(crudo))
            continue

        if canonico in indices:
            anterior = indices[canonico]
            ya_era_propio = canonico in por_alias_propio
            if propio is not None and not ya_era_propio:
                # El alias del archivo (§10.6) desplaza al del mapa global (§8.6).
                indices[canonico] = posicion
                por_alias_propio.add(canonico)
                ignoradas.append(str(encabezados[anterior]))
                continue
            if (propio is not None) == ya_era_propio:
                raise ErrorDeCabecera(
                    f"{especificacion.archivo}: las columnas "
                    f"{encabezados[anterior]!r} y {crudo!r} apuntan las dos al "
                    f"campo {canonico!r}. El §10.6 define una sola y adivinar "
                    f"cuál vale es justo lo que el §3.3 no permite."
                )
            ignoradas.append(str(crudo))
            continue

        indices[canonico] = posicion
        if propio is not None:
            por_alias_propio.add(canonico)

    faltantes = [c for c in especificacion.obligatorias if c not in indices]
    if faltantes:
        raise ErrorDeCabecera(
            f"{especificacion.archivo}: faltan las columnas obligatorias "
            f"{', '.join(faltantes)} (§10.6). Encabezados leídos: "
            f"{', '.join(str(e) for e in encabezados if normalizar(e)) or '(ninguno)'}."
        )

    return MapaColumnas(indices=indices, ignoradas=tuple(ignoradas))


def indice_de_letra(letra: str) -> int:
    """``'A'`` → 0, ``'I'`` → 8 (§10.6 fija las columnas del CPU por letra)."""
    indice = 0
    for caracter in letra.strip().upper():
        indice = indice * 26 + (ord(caracter) - ord("A") + 1)
    return indice - 1


@dataclass(frozen=True, slots=True)
class ColumnaPorLetra:
    """Campo canónico anclado a una letra de columna (§10.6, archivo de CPU)."""

    campo: str
    letra: str

    @property
    def indice(self) -> int:
        return indice_de_letra(self.letra)


# --- Movimientos de almacén (§10.6) --------------------------------------
#
# Cita literal del §10.6: "clave del material = **# Parte**; descripción =
# **Parte**; familia/IVA = **Clase**; obra = **Ubicacion + Lote**;
# contratista = **Contratista**; fecha → semana de obra = **Fecha**; motivo
# (bucket KPI) = **Motivo**; cantidad con signo = **Efecto Qty**; importe con
# signo = **Efecto Costo**; costo del cruce = **C/Último** (C/Promedio solo
# valida); liga al concepto = **Referencia**; almacén = **# Almacen /
# Almacen**; usuario (bitácora) = **Usuario**".

ALMACEN = EspecificacionArchivo(
    tipo="Movimientos de almacén",
    archivo="IMPORTAADOR_ALMACEN.xlsx",
    hoja="Consulta",
    obligatorias=("clave", "ubicacion", "lote", "fecha", "motivo", "cantidad"),
    opcionales=(
        "descripcion",
        "familia",
        "contratista",
        "costo",
        "costo_ultimo",
        "costo_promedio",
        "referencia",
        "almacen_clave",
        "almacen",
        "usuario",
    ),
    alias={
        "# parte": "clave",
        "parte": "descripcion",
        "clase": "familia",
        "ubicacion": "ubicacion",
        "lote": "lote",
        "contratista": "contratista",
        "fecha": "fecha",
        "motivo": "motivo",
        "efecto qty": "cantidad",
        "efecto costo": "costo",
        "c/ultimo": "costo_ultimo",
        "c/promedio": "costo_promedio",
        "referencia": "referencia",
        "# almacen": "almacen_clave",
        "almacen": "almacen",
        "usuario": "usuario",
    },
)

# --- Catálogo de materiales (§10.6) --------------------------------------
#
# Cita literal del §10.6: "**Materiales** (`CABECERAS_MATERIALES.xlsx`):
# clave, descripción, unidad, familia, costos (base / último / promedio),
# IVA."
#
# El §10.6 nombra los campos, no las cabeceras literales de este archivo (a
# diferencia del de almacén). Por eso el alias propio se limita a las
# variantes de los mismos nombres que el §10.6 usa, y lo demás lo resuelve el
# mapa global del §8.6 (`Código`→clave, `Descripción`→descripcion,
# `U`/`UM`→unidad, `Clase`→familia).

MATERIALES = EspecificacionArchivo(
    tipo="Catálogo de materiales",
    archivo="CABECERAS_MATERIALES.xlsx",
    hoja=None,
    obligatorias=("clave", "descripcion"),
    opcionales=(
        "unidad",
        "familia",
        "costo_base",
        "costo_ultimo",
        "costo_promedio",
        "iva",
    ),
    alias={
        "costo base": "costo_base",
        "costo_base": "costo_base",
        # El archivo real trae "COSTO BASE M.N." (moneda nacional): es el
        # costo base del catálogo. "COSTO BASE M.E." (moneda extranjera) y
        # "COSTO UNITARIO" (duplica M.N. en el archivo real) se dejan sin
        # mapear a propósito — dos alias al mismo campo canónico son
        # ambigüedad real (§8.6) y el archivo se rechazaría entero.
        "costo base m.n.": "costo_base",
        "costo ultimo": "costo_ultimo",
        "costo_ultimo": "costo_ultimo",
        "c/ultimo": "costo_ultimo",
        "costo promedio": "costo_promedio",
        "costo_promedio": "costo_promedio",
        "c/promedio": "costo_promedio",
        "iva": "iva",
        "iva aplica": "iva",
        "iva_aplica": "iva",
    },
)

# --- Mano de obra / Destajos (§10.6) --------------------------------------
#
# Cita literal del §10.6: "Mano de obra (Destajos) (`CABECERAS_MANO_DE_
# OBRA.xlsx`, `DESTAJOS`): TIPO, clave usuario (mapeo), clave oficial
# (`MOA-`), descripción, unidad, cuadrilla, rendimiento teórico/real, costo
# unitario, familia."
#
# El archivo real de producción trae "DESCTRIPCIÓN" — un typo propio del
# archivo, no del §10.6 ni de este código; se homologa igual que
# "COSTO BASE M.N." en materiales. TIPO y CLAVE USUARIO no se guardan: el
# primero no aporta nada (todo el archivo es de un solo tipo, los
# subcontratos van en otro archivo del §10.6) y el segundo es la
# referencia del sistema externo del cliente, no algo que el catálogo
# interno necesite. RENDIMIENTO REAL tampoco se lee — sale de cruzar
# contra la duración real de la obra, un cálculo posterior.

MANO_DE_OBRA = EspecificacionArchivo(
    tipo="Mano de obra / Destajos",
    archivo="CABECERAS_MANO_DE_OBRA.xlsx",
    hoja="DESTAJOS",
    obligatorias=("clave", "descripcion"),
    opcionales=("unidad", "familia", "cuadrilla", "rendimiento_teorico", "costo_base"),
    alias={
        "desctripcion": "descripcion",
        "cuadrilla": "cuadrilla",
        "rendimiento teorico": "rendimiento_teorico",
        "rendimiento_teorico": "rendimiento_teorico",
        "costo unitario": "costo_base",
        "costo_unitario": "costo_base",
    },
)

# --- CPU / Conceptos (§10.6) ---------------------------------------------
#
# Cita literal del §10.6: "**CPU / Conceptos** (`CABECERAS_CPU.xlsx`, hoja
# `EXPORTADOR`, formato plano): por cada concepto, una fila **encabezado**
# (`TIPO=Concepto`, A=B) + sus filas **componente**
# (`TIPO=Material/Mano de obra/Subcontrato`). Columnas: **CLAVE concepto**
# (A), **clave insumo** (B en componente), descripción (C), unidad (D),
# **rendimiento = CANTIDAD** (E, en componente), PU (F), **FAMILIA** (H),
# **TIPO** (I)."
#
# La columna G no la nombra el §10.6, así que no se lee.

CPU = EspecificacionArchivo(
    tipo="CPU / Conceptos",
    archivo="CABECERAS_CPU.xlsx",
    hoja="EXPORTADOR",
    obligatorias=("clave", "tipo"),
    opcionales=(
        "clave_insumo",
        "descripcion",
        "unidad",
        "cantidad",
        "precio_unitario",
        "familia",
    ),
)

# --- Prototipos (extensión propia, no está en el §10.6 original) ---------
#
# A diferencia de ALMACEN y MATERIALES, este archivo no lo describe el §10.6:
# es el bulk-load que le faltaba a `POST /prototipos` (§7.2). Por eso ninguno
# de sus campos vive en el mapa global (§8.6) — todos necesitan su propio
# alias, incluida la identidad (`"nombre": "nombre"`), porque
# `canonizar_encabezado` no tiene fallback implícito.

PROTOTIPOS = EspecificacionArchivo(
    tipo="Prototipos",
    archivo="CABECERAS_PROTOTIPOS.xlsx",
    hoja=None,
    obligatorias=("proyecto_clave", "clave", "nombre"),
    opcionales=("m2", "niveles", "recamaras"),
    alias={
        "proyecto": "proyecto_clave",
        "proyecto_clave": "proyecto_clave",
        "clave proyecto": "proyecto_clave",
        "clave_proyecto": "proyecto_clave",
        "nombre": "nombre",
        "m2": "m2",
        "niveles": "niveles",
        "recamaras": "recamaras",
    },
)

# --- Presupuesto jerárquico (extensión propia, no está en el §10.6) ------
#
# Árbol de un prototipo por CLAVE PADRE → CLAVE HIJO (§7.4): tampoco lo
# describe el §10.6, así que sus campos propios necesitan alias explícito
# igual que PROTOTIPOS. `clave`/`descripcion`/`unidad`/`cantidad`/
# `precio_unitario`/`tipo` ya resuelven por el mapa global (§8.6); solo
# `clave_padre`/`clave_hijo`/`indice`/`importe` no viven ahí.

PRESUPUESTO = EspecificacionArchivo(
    tipo="Presupuesto jerárquico",
    archivo="CABECERAS_PRESUPUESTO.xlsx",
    hoja=None,
    obligatorias=("clave_hijo", "descripcion", "tipo"),
    opcionales=("indice", "clave_padre", "unidad", "cantidad", "precio_unitario", "importe"),
    alias={
        "indice": "indice",
        "clave padre": "clave_padre",
        "clave_padre": "clave_padre",
        "clave hijo": "clave_hijo",
        "clave_hijo": "clave_hijo",
        "importe": "importe",
    },
)

COLUMNAS_CPU: tuple[ColumnaPorLetra, ...] = (
    ColumnaPorLetra("clave", "A"),
    ColumnaPorLetra("clave_insumo", "B"),
    ColumnaPorLetra("descripcion", "C"),
    ColumnaPorLetra("unidad", "D"),
    ColumnaPorLetra("cantidad", "E"),
    ColumnaPorLetra("precio_unitario", "F"),
    ColumnaPorLetra("familia", "H"),
    ColumnaPorLetra("tipo", "I"),
)
"""Posiciones fijas del archivo de CPU (§10.6). No se resuelven por nombre."""

MAPA_CPU = MapaColumnas(indices={c.campo: c.indice for c in COLUMNAS_CPU})
