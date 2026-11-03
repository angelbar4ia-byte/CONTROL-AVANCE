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
    "CATALOGO_MATRICES_OPUS",
    "COLUMNAS_CPU",
    "CONCEPTOS_AUXILIARES",
    "CONCEPTOS_BASE",
    "CPU",
    "CPU_MATRIZ",
    "CUADRILLAS",
    "ETAPAS_CONSTRUCTIVAS",
    "FAMILIAS",
    "INGENIERIA_LOTE",
    "MANO_DE_OBRA",
    "MAPA_CPU",
    "MATERIALES",
    "NIVELES",
    "PRESUPUESTO",
    "PROGRAMA_BASE",
    "PROTOTIPOS",
    "SUBCONTRATOS",
    "TRABAJOS_OPUS",
    "UNIDADES",
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

    series: dict[str, str] = field(default_factory=dict)
    """Cabecera **repetida** (ya normalizada) → campo canónico que la colecciona.

    Para las columnas que el archivo real reparte en varias en vez de una lista
    separada por comas: `ESPECIALIDAD 1 … ESPECIALIDAD 5`, `TIPO 1`, `TIPO 2`.
    Se busca por prefijo, así que `"especialidad"` captura las cinco, y también
    la columna a secas cuando el archivo no la numera.

    A diferencia de `alias`, aquí la repetición **no es ambigüedad**: son cinco
    huecos del mismo dato, y el campo recibe la tupla de índices en el orden en
    que aparecen. Un archivo que numera hasta ESPECIALIDAD 8 sigue cargando sin
    tocar el contrato.
    """

    @property
    def canonicas(self) -> frozenset[str]:
        return (
            frozenset(self.obligatorias)
            | frozenset(self.opcionales)
            | frozenset(self.series.values())
        )


@dataclass(frozen=True, slots=True)
class MapaColumnas:
    """Campo canónico → índice de columna (base 0) en la hoja."""

    indices: dict[str, int]
    ignoradas: tuple[str, ...] = ()
    """Cabeceras del archivo que no mapean a ningún campo del contrato.

    No son un error: el archivo de almacén trae 46 columnas y el §10.6 solo
    nombra 16. Se listan para que el reporte diga qué se dejó fuera.
    """

    series: dict[str, tuple[int, ...]] = field(default_factory=dict)
    """Campo canónico → todas las columnas que lo alimentan, en orden."""

    def valor(self, fila: Sequence[object], campo: str) -> object:
        """Celda de ``campo`` en ``fila``, o ``None`` si la columna no vino."""
        indice = self.indices.get(campo)
        if indice is None or indice >= len(fila):
            return None
        return fila[indice]

    def valores(self, fila: Sequence[object], campo: str) -> tuple[object, ...]:
        """Las celdas de una serie, sin las vacías y sin repetir.

        Los huecos se descartan porque son la forma normal del archivo: un
        contratista con dos especialidades deja tres columnas en blanco. Las
        repetidas también, porque duplicar un puente no dice nada nuevo y la
        única de la tabla lo rechazaría de todos modos.
        """
        vistos: list[object] = []
        for indice in self.series.get(campo, ()):
            if indice >= len(fila):
                continue
            celda = fila[indice]
            if celda is None or not str(celda).strip():
                continue
            clave = normalizar(celda)
            if clave and clave not in {normalizar(v) for v in vistos}:
                vistos.append(celda)
        return tuple(vistos)


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

    Las **series** (`especificacion.series`) se resuelven antes que todo lo
    demás y no pasan por la regla 3: `ESPECIALIDAD 1 … 5` son cinco huecos del
    mismo dato, no cinco candidatas a serlo, así que se coleccionan en orden en
    vez de pelearse por una sola casilla.
    """
    indices: dict[str, int] = {}
    por_alias_propio: set[str] = set()
    ignoradas: list[str] = []
    series: dict[str, list[int]] = {}

    for posicion, crudo in enumerate(encabezados):
        texto = normalizar(crudo)
        if not texto:
            continue

        de_serie = _campo_de_serie(texto, especificacion.series)
        if de_serie is not None:
            series.setdefault(de_serie, []).append(posicion)
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

    faltantes = [
        c
        for c in especificacion.obligatorias
        if c not in indices and c not in series
    ]
    if faltantes:
        raise ErrorDeCabecera(
            f"{especificacion.archivo}: faltan las columnas obligatorias "
            f"{', '.join(faltantes)} (§10.6). Encabezados leídos: "
            f"{', '.join(str(e) for e in encabezados if normalizar(e)) or '(ninguno)'}."
        )

    return MapaColumnas(
        indices=indices,
        ignoradas=tuple(ignoradas),
        series={campo: tuple(cols) for campo, cols in series.items()},
    )


def _campo_de_serie(texto: str, series: dict[str, str]) -> str | None:
    """¿Esta cabecera es uno de los huecos de una serie?

    Coincide la cabecera exacta (`TIPO`) o la numerada (`TIPO 1`, `TIPO 2`),
    nunca una que solo empiece igual: sin el corte por sufijo, un prefijo
    `"tipo"` se tragaría `TIPO DE CAMBIO` y el dato se cargaría en la columna
    equivocada sin que nadie lo note.
    """
    for prefijo, campo in series.items():
        if texto == prefijo:
            return campo
        resto = texto.removeprefix(f"{prefijo} ")
        if resto != texto and resto.isdigit():
            return campo
    return None


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

CONCEPTOS_BASE = EspecificacionArchivo(
    tipo="Catálogo de conceptos",
    archivo="CABECERAS_CONCEPTOS.xlsx",
    hoja=None,
    obligatorias=("clave", "descripcion"),
    opcionales=("unidad", "clave_unidad", "especialidad"),
    alias={
        # `especialidad` va **primero** a propósito: `plantillas.py` rotula la
        # columna con el primer alias del campo, y la plantilla que alguien
        # descarga tiene que decir "especialidad". Rotulada "frente", quien la
        # llene escribiría OBRA o INSTALACIONES —el vocabulario de la etapa— y
        # el oficio quedaría capturado en el eje equivocado.
        "especialidad": "especialidad",
        # El archivo real del cliente sí la rotula "FRENTE", y se sigue
        # aceptando: sus quince valores —ESTRUCTURA, ACABADOS, CARPINTERIA…—
        # no son los cuatro frentes de la etapa. La traducción vive aquí, en el
        # borde, para que adentro los dos ejes no se confundan.
        "frente": "especialidad",
    },
)
"""Catálogo base de identidad de conceptos (§8.7): clave, descripción,
unidad y la especialidad con la que se ejecuta (§8.3, migración 0047). La
composición (qué lleva cada concepto y con qué costo) es CPU (`CPU`, más
abajo), un archivo y un cargador distintos.

El archivo real de conceptos auxiliares (mismo contrato, ver
`CONCEPTOS_AUXILIARES`) trae también costo y familia (`CLAVE UNIDAD,
UNIDAD, COSTO BASE M.N., COSTO BASE M.E., COSTO UNITARIO, FECHA,
FAMILIA`) — mismas columnas que `MATERIALES`. Confirmado con el usuario:
el costo se ignora aquí a propósito (es composición/CPU, no identidad,
§8.7); `clave_unidad` sí se captura —igual que en `MATERIALES`— porque es
identidad de la unidad, no costo."""

CONCEPTOS_AUXILIARES = EspecificacionArchivo(
    tipo="Catálogo de conceptos auxiliares",
    archivo="CABECERAS_CONCEPTOS_AUXILIARES.xlsx",
    hoja=None,
    obligatorias=CONCEPTOS_BASE.obligatorias,
    # Las de `CONCEPTOS_BASE` **menos** la especialidad: un auxiliar es un
    # componente de otro concepto, no algo que se contrate por oficio, y el
    # aplicador de auxiliares no recibe el catálogo de especialidades. Dejarla
    # en el contrato haría que la columna se leyera y se tirara en silencio,
    # que es justo lo que le pasó a RFC y CONTACTO en contratistas.
    opcionales=tuple(c for c in CONCEPTOS_BASE.opcionales if c != "especialidad"),
)
"""Mismo contrato que `CONCEPTOS_BASE`: un concepto auxiliar es un
`concepto` más (`tipo=auxiliar`, §7.3), con su propio archivo y su propio
tipo de carga porque es su propio catálogo desde el punto de vista de
quien lo sube — pero comparte validador (`conceptos_base.
validar_concepto_base`) y la misma tabla `concepto`: la clave es única sin
importar el tipo (`uq_concepto_clave`), así que un archivo de auxiliares
que repita la clave de un concepto normal actualiza ESE registro, no crea
uno paralelo (§3.3)."""

NIVELES = EspecificacionArchivo(
    tipo="Catálogo de niveles de construcción",
    archivo="CATALOGO_DE_NIVELES.xlsx",
    hoja=None,
    obligatorias=("clave", "descripcion"),
    opcionales=(),
)
"""Catálogo base de identidad de niveles (§10.1): clave, descripción, nada
más — orden/importe quedan en su default y se llenan a mano. El archivo
real trae columnas propias de la herramienta de origen (TIPO, DESCRIPCIÓN
CORTA, UNIDAD, CANTIDAD, PRECIO UNITARIO, TOTAL) que no tienen dónde vivir
en este catálogo tan simple; se ignoran sin romper (§10.6, mismo criterio
que el resto de los cargadores con columnas de más)."""

ETAPAS_CONSTRUCTIVAS = EspecificacionArchivo(
    tipo="Catálogo de etapas de construcción",
    archivo="CATALOGO_DE_ETAPAS_DE_CONSTRUCCION.xlsx",
    hoja=None,
    obligatorias=("clave", "descripcion"),
    opcionales=("frente",),
    alias={
        # `DESCRIPCIÓN CORTA` se manda a un campo que la especificación **no**
        # declara, así que acaba en `ignoradas`. Sin este alias, el mapa global
        # del §8.6 la canoniza como `descripcion` y choca con la columna
        # `DESCRIPCIÓN` de al lado: el archivo entero se rechazaría por
        # ambigüedad. Es una forma de decir "esta columna se ignora a
        # propósito", no un campo a medio implementar.
        "descripcion corta": "descripcion_corta",
    },
    series={
        # El archivo real trae **dos** columnas llamadas "TIPO": la primera es
        # el tipo de renglón de la herramienta que lo exportó (`Nivel 2` en las
        # cincuenta filas) y la última es el frente (`OBRA`, `INSTALACIONES`,
        # `SUBCONTRATOS`, `PINTURA`). Normalizadas son la misma cadena, así que
        # la regla de ambigüedad rechazaría el archivo y por posición sería
        # frágil. Se leen las dos como serie y `validar_etapa_constructiva`
        # descarta el tipo de renglón, que es un vocabulario cerrado y conocido.
        "tipo": "frente",
    },
)
"""Catálogo base de identidad de etapas (§10.1): clave, descripción y el
frente al que pertenece la etapa (§8.3, migración 0045).

`etapa_constructiva.nivel_id` no se resuelve aquí: el archivo real no trae a
qué nivel pertenece cada etapa, así que asumir un nivel sería inventar una
relación que el archivo no da (§3.3). Se llena a mano desde el catálogo
mientras no haya un archivo real que sí la traiga.

El **frente** sí viene, y es la clase de fuerza de trabajo que se contrata
—OBRA, INSTALACIONES, SUBCONTRATOS, PINTURA—: los mismos cuatro valores que
la columna `TIPO` del catálogo de contratistas. No confundir con la
especialidad, que es el oficio y vive en el concepto (`CONCEPTOS_BASE`)."""

UNIDADES = EspecificacionArchivo(
    tipo="Catálogo de unidades",
    archivo="CATALOGO_DE_UNIDADES.xlsx",
    hoja="Hoja1",
    obligatorias=("clave", "nombre"),
    opcionales=(),
    alias={
        # El archivo real trae "UNIDAD" (la clave corta, KG/PZ/...) y
        # "SINONIMO" (el nombre descriptivo, Kilogramo/Pieza/...) —
        # confirmado con el usuario, ver `domain.cargadores.unidades`. Sin
        # estos alias, "unidad" resolvería al campo global homónimo (usado
        # en otros archivos como referencia ajena, no como esta identidad)
        # y "sinonimo"/su variante no resolverían a nada — las filas se
        # descartarían en silencio.
        "unidad": "clave",
        "sinonimo": "nombre",
        # "SINOMIMO": la letra M/N invertida tal como trae el archivo real
        # (verificado en vivo, no es un typo de este módulo).
        "sinomimo": "nombre",
    },
)
"""Catálogo base de identidad de unidades (§3.5): clave, nombre, nada más
—sinónimos/factor quedan en su default y se llenan a mano—. El archivo real
trae además "CLAVE UNIDAD" (un consecutivo numérico del sistema de origen,
sin dónde vivir aquí; se ignora sin romper, §10.6) y una segunda hoja con un
subconjunto sin sinónimo, ordenado distinto — no es el catálogo a cargar,
por eso `hoja` fija "Hoja1" en vez de la hoja activa."""

CONTRATISTAS = EspecificacionArchivo(
    tipo="Catálogo de contratistas",
    archivo="CATALOGO_DE_CONTRATISTAS.xlsx",
    hoja=None,
    obligatorias=("clave", "razon_social"),
    opcionales=("rfc", "contacto", "telefono", "email", "frentes", "especialidades"),
    alias={
        # "CONTRATISTA" es el nombre de ESTE contratista, no una referencia a
        # otro: en materiales y almacén la misma cabecera apunta a un tercero,
        # y sin este alias propio la razón social de cada fila se descartaría
        # en silencio. Mismo caso que "FAMILIA" en `FAMILIAS`.
        "contratista": "razon_social",
        "razon social": "razon_social",
        "nombre": "razon_social",
        "correo": "email",
        "tel": "telefono",
        # `rfc` y `contacto` se declaran aunque la cabecera se llame igual que
        # el campo: el mapa global del §8.6 no los conoce —ningún otro archivo
        # los trae— y `canonizar_encabezado` los devolvería como `None`, así
        # que sin este alias la columna se ignoraría en silencio.
        "rfc": "rfc",
        "contacto": "contacto",
        "telefono": "telefono",
        "email": "email",
        # Los frentes que sabe hacer, separados por coma. Plural primero
        # porque es el rótulo que `plantillas.py` pone en la plantilla y la
        # columna admite varios; el singular se sigue aceptando porque quien
        # llena el archivo escribe cualquiera de los dos.
        "frentes": "frentes",
        "frente": "frentes",
    },
    series={
        # El archivo real no trae una lista separada por comas: reparte los
        # frentes en `TIPO 1` y `TIPO 2`, y los oficios en `ESPECIALIDAD 1..5`.
        # Se leen como series y no como alias porque cinco columnas del mismo
        # dato no son cinco candidatas a serlo: son cinco huecos, y la regla de
        # ambigüedad rechazaría el archivo entero.
        "tipo": "frentes",
        "especialidad": "especialidades",
    },
)
"""Catálogo de contratistas (§8.3, §10.6).

El contratista es la fuerza de trabajo: pone las cuadrillas con las que se
ejecuta un frente. `frentes` es la lista de claves que sabe hacer —`EST, INS`—
y alimenta `contratista_frente`, que es **capacidad de catálogo** y no la
asignación a una obra: quién lleva INSTALACIONES en MAPLE 01 se decide al
planear esa obra.

`hoja=None` —la activa— porque este archivo no viene de un exportador con hoja
fija: lo escribe alguien de la constructora y no hay contrato que la nombre."""


FAMILIAS = EspecificacionArchivo(
    tipo="Catálogo de familias",
    archivo="CATALOGO_DE_FAMILIAS.xlsx",
    hoja="Hoja1",
    obligatorias=("clave", "nombre"),
    opcionales=(),
    alias={
        # "FAMILIA" es el nombre de LA familia que esta fila identifica, no
        # una referencia a otra — sin este alias propio resolvería al campo
        # global "familia" (usado en MATERIALES/CPU como referencia ajena),
        # que esta especificación no declara, y la fila se descartaría en
        # silencio. Ver `domain.cargadores.familias`.
        "familia": "nombre",
    },
)
"""Catálogo base de identidad de familias (§3.5): clave, nombre, nada más
—`parent_id`/`aplica_a`/`iva_aplica` quedan en su default y se llenan a
mano—. El archivo real trae además "PREFIJO" (ACA/ADH/PET/...), sin dónde
vivir en `familia` hoy; se ignora sin romper, mismo criterio que "TIPO" en
niveles/etapas (§10.6). Trae también una segunda hoja con la cuenta de
materiales por familia (mayúsculas inconsistentes, duplicados) — no es el
catálogo a cargar, por eso `hoja` fija "Hoja1"."""

MATERIALES = EspecificacionArchivo(
    tipo="Catálogo de materiales",
    archivo="CABECERAS_MATERIALES.xlsx",
    hoja=None,
    obligatorias=("clave", "descripcion"),
    opcionales=(
        "unidad",
        "clave_unidad",
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
        # El export nativo de OPUS 2025 (`CATALOGO_DE_MATERIALES.csv` y,
        # con el mismo contrato, `CATALOGO_DE_FLETES.csv`) rotula la misma
        # columna "Costo base M. N." —con un espacio entre "M." y "N." que
        # `normalizar` no quita (no colapsa puntuación, solo espacios
        # dobles, §shared.normalizacion.normalizar)—, así que es un
        # string distinto de "COSTO BASE M.N." y necesita su propio alias;
        # sin él, las 386+9 filas de ambos archivos cargarían con
        # `costo_base=None` en silencio. Mismo razonamiento que arriba
        # para "Costo base M. E."/"Costo unitario": se dejan sin mapear.
        "costo base m. n.": "costo_base",
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
"""Catálogo de materiales (§10.1, §10.6): sirve tanto al archivo de la
generación anterior (`CABECERAS_MATERIALES.xlsx`) como al export nativo
de OPUS 2025 (`CATALOGO_DE_MATERIALES.csv`, 386 filas verificadas, y
`CATALOGO_DE_FLETES.csv`, 9 filas — mismo contrato de columnas, un flete
es `tipo=material` más: `CategoriaExplosion.FLETE`, migración 0052, es
categoría de la *explosión* del CPU, no un tipo de insumo distinto) —
mismo criterio que `PRESUPUESTO`: un archivo real nunca trae las dos
cabeceras de costo a la vez, así que las dos resuelven al mismo
`costo_base` sin ambigüedad (§8.6)."""

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
# primero no aporta nada (todo el archivo es de un solo tipo — los
# subcontratos van en `catalogo_de_SUBCONTRATOS.xlsx`, mismas cabeceras,
# ver SUBCONTRATOS abajo) y el segundo es la referencia del sistema externo
# del cliente, no algo que el catálogo interno necesite. RENDIMIENTO REAL
# tampoco se lee — sale de cruzar contra la duración real de la obra, un
# cálculo posterior.

MANO_DE_OBRA = EspecificacionArchivo(
    tipo="Mano de obra / Destajos",
    archivo="CABECERAS_MANO_DE_OBRA.xlsx",
    hoja="DESTAJOS",
    obligatorias=("clave", "descripcion"),
    opcionales=(
        "unidad",
        "clave_unidad",
        "familia",
        "cuadrilla",
        "rendimiento_teorico",
        "costo_base",
    ),
    alias={
        "desctripcion": "descripcion",
        "cuadrilla": "cuadrilla",
        "rendimiento teorico": "rendimiento_teorico",
        "rendimiento_teorico": "rendimiento_teorico",
        "costo unitario": "costo_base",
        "costo_unitario": "costo_base",
    },
)

# `catalogo_de_SUBCONTRATOS.xlsx` trae exactamente las mismas cabeceras que
# `CABECERAS_MANO_DE_OBRA.xlsx` (TIPO=Subcontrato en vez de Individual,
# claves SUB-xxxxx) pero en su propia hoja — no reusar el objeto de arriba
# tal cual: su `hoja="DESTAJOS"` no existe en este archivo.

SUBCONTRATOS = EspecificacionArchivo(
    tipo="Subcontratos",
    archivo="catalogo_de_SUBCONTRATOS.xlsx",
    hoja="SUBCONTRATOS",
    obligatorias=MANO_DE_OBRA.obligatorias,
    opcionales=MANO_DE_OBRA.opcionales,
    alias=dict(MANO_DE_OBRA.alias),
)

# --- Trabajos: destajos + subcontratos, export nativo de OPUS -----------
#
# `CATALOGO_DE_TRABAJOS.csv` trae en un solo archivo lo que la generación
# anterior repartía en dos (`CABECERAS_MANO_DE_OBRA.xlsx` hoja `DESTAJOS` +
# `catalogo_de_SUBCONTRATOS.xlsx`): 259 destajos y 6 subcontratos,
# distinguidos por columna, no por archivo (265 filas, verificado). No
# reusa `MANO_DE_OBRA`: sus cabeceras son otras ("Costo base M. N." en vez
# de "COSTO UNITARIO", sin `cuadrilla`/`rendimiento_teorico`) y, sobre
# todo, la columna que aquí importa no tiene dónde vivir en ese contrato.
#
# El archivo repite la cabecera **"Tipo" dos veces** (verificado con
# `csv.reader`, nunca `DictReader` — con cabeceras duplicadas una pisa a la
# otra en silencio): la primera es la *clase* (`Destajo`/`Subcontrato`,
# la que importa — mano_de_obra.clase_de_trabajo la separa de ahí); la
# última siempre vale `Trabajo` (verificado, 265/265) y es la *categoría*,
# como `Material` en `MATERIALES_OPUS` — no aporta nada. Igual que
# `ETAPAS_CONSTRUCTIVAS` con su propia "TIPO" duplicada, las dos se leen
# como `series` (nunca por posición: si el exportador las reordena, esto
# sigue funcionando) y se descartan por contenido, no por posición.

TRABAJOS_OPUS = EspecificacionArchivo(
    tipo="Trabajos (destajos y subcontratos, export nativo de OPUS)",
    archivo="CATALOGO_DE_TRABAJOS.csv",
    hoja=None,
    obligatorias=("clave", "descripcion", "clase"),
    opcionales=("unidad", "familia", "costo_base"),
    alias={
        # Mismo razonamiento que `MATERIALES_OPUS`: "Costo base M. N." es
        # el costo base; "Costo base M. E." (siempre cero, verificado) y
        # "Costo unitario" (duplica M. N., verificado) se dejan sin mapear
        # a propósito para no chocar con el §8.6 (dos alias al mismo campo
        # son ambigüedad real).
        "costo base m. n.": "costo_base",
        # "C", "Clave usuario" (consecutivo interno de OPUS, igual que
        # "CLAVE USUARIO" en `MANO_DE_OBRA`), "Comentarios", "Subfamilia" y
        # "Fecha" no tienen dónde vivir hoy; se ignoran sin romper (§10.6).
    },
    series={
        # Las dos columnas "Tipo" del archivo real: se coleccionan en el
        # orden en que aparecen (primera, luego última) y
        # `mano_de_obra.clase_de_trabajo` descarta la que vale "Trabajo"
        # por vocabulario cerrado, no por posición.
        "tipo": "clase",
    },
)
"""Catálogo combinado de Trabajos, export nativo de OPUS 2025
(`CATALOGO_DE_TRABAJOS.csv`, 265 filas verificadas: 259 destajo, 6
subcontrato). No fija por sí solo si una fila es destajo o subcontrato —
eso es `mano_de_obra.clase_de_trabajo`, que lee la `clase` resuelta aquí y
decide el `TipoInsumo` con el que `validar_mano_obra` valida la fila
(`mano_de_obra.validar_trabajo`)."""

INGENIERIA_LOTE = EspecificacionArchivo(
    tipo="Ingeniería del lote (extensión propia, CONOCIMIENTO.md §11)",
    archivo="INGENIERIA_<OBRA>_<ETAPA>.csv",
    hoja=None,
    obligatorias=(),
    opcionales=(),
)
"""Sin encabezados ni columnas por nombre (CONOCIMIENTO.md §11.4): las siete
columnas se reconocen por posición y por los datos, nunca por un título que
el archivo no trae (ver el docstring de `domain.cargadores.
ingenieria_lote`). `obligatorias`/`opcionales` se dejan vacías a propósito
—no hay cabecera que resolver con `resolver_encabezados`— así que
`GET /cargas/plantillas/{tipo}` (`adapters.excel.plantillas`) genera un
`.xlsx` sin ninguna fila de título para este tipo: escribir rótulos ahí
sería inventar un contrato que el archivo real no tiene, y esa fila de
título terminaría leyéndose como una fila de dato más."""

CUADRILLAS = EspecificacionArchivo(
    tipo="Cuadrillas",
    archivo="CABECERAS_CUADRILLAS.xlsx",
    hoja=None,
    obligatorias=("clave_cuadrilla", "clave", "descripcion"),
    opcionales=("unidad", "cantidad", "precio_unitario"),
    alias={
        "clave cuadrilla": "clave_cuadrilla",
    },
)
"""Composición y PU de una cuadrilla (§10.6): fila cabecera (``Clave =
Clave cuadrilla``) + filas integrante. ``unidad``/``cantidad``/
``precio_unitario`` ya resuelven por el mapa global (§8.6: ``pu`` →
``precio_unitario``); solo ``Clave cuadrilla`` necesita alias propio.
``IMPORTE`` se deja sin mapear a propósito: se recalcula de la
composición, igual que en `CPU`."""

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
# Árbol de un prototipo: por CLAVE PADRE → CLAVE HIJO cuando el archivo trae
# esa columna, o por NIVEL + posición cuando no la trae (árbol nativo del
# exportador de OPUS, §árbol en `domain.cargadores.presupuesto.
# construir_arboles`). Tampoco lo describe el §10.6, así que sus campos
# propios necesitan alias explícito igual que PROTOTIPOS. `descripcion`/
# `unidad`/`cantidad`/`precio_unitario`/`tipo` ya resuelven por el mapa
# global (§8.6); `clave_padre`/`clave_hijo`/`nivel`/`indice`/`importe` no
# viven ahí, y `clave` (el nombre que le da el exportador nativo a lo que
# aquí es `clave_hijo`) sí vive ahí pero apuntando a otro campo canónico
# —de ahí su alias propio también.

PRESUPUESTO = EspecificacionArchivo(
    tipo="Presupuesto jerárquico",
    archivo="CABECERAS_PRESUPUESTO.xlsx",
    hoja=None,
    obligatorias=("clave_hijo", "descripcion", "tipo"),
    opcionales=(
        "indice",
        "clave_padre",
        "nivel",
        "unidad",
        "cantidad",
        "precio_unitario",
        "importe",
        "wbs",
    ),
    alias={
        "indice": "indice",
        "clave padre": "clave_padre",
        "clave_padre": "clave_padre",
        "clave hijo": "clave_hijo",
        "clave_hijo": "clave_hijo",
        # El archivo de prueba hecho a mano rotula la columna "CLAVE HIJO";
        # el exportador nativo de OPUS la rotula a secas "Clave" —sin
        # `clave_padre` no hay hijo que distinguir de un padre—. Sin este
        # alias, "clave" resolvería al campo global homónimo (§8.6), que
        # esta especificación no declara, y la columna se ignoraría en
        # silencio: ninguna fila tendría clave (§3.3).
        "clave": "clave_hijo",
        "importe": "importe",
        "wbs": "wbs",
        # El archivo real del exportador de OPUS no trae `clave_padre`: la
        # cabecera literal es "Nivel " (con espacio al final — `normalizar`
        # colapsa espacios y la deja en "nivel"). Sin este alias, "nivel" no
        # resuelve a nada en el mapa global (§8.6) y la columna se
        # ignoraría en silencio, que es justo lo que le faltaba al árbol
        # nativo para reconstruirse (`construir_arboles`).
        "nivel": "nivel",
    },
)
"""``wbs`` es opcional (§7.4): no todo archivo real la trae. Cuando sí viene,
`construir_arboles` la usa solo para avisar —§10.3, `TipoPendiente.
WBS_INCONSISTENTE`, no crítico— si no coincide con la que el propio TIPO de
cada fila ya implica; nunca decide la identidad de la fila ni bloquea la
carga.

``clave_padre`` y ``nivel`` son las dos formas de dar la identidad
padre-hijo (§árbol): el archivo de prueba hecho a mano trae la primera, el
exportador nativo de OPUS trae la segunda y nunca las dos juntas. Las dos
son opcionales aquí porque el contrato exige **una u otra**, no las dos —
una regla de "al menos una" que no se puede expresar con `obligatorias`
(eso exigiría ambas) y que por tanto valida `construir_arboles`, no este
módulo (§12.11: aquí solo se resuelven columnas, no se decide el árbol)."""

# --- CPU / Conceptos: matriz nativa de OPUS (extensión propia) ----------
#
# A diferencia de `CPU` (arriba), que resuelve por LETRA porque el §10.6
# solo fija columnas para el formato plano, este archivo es el export
# nativo de OPUS del mismo dato (concepto + CPU) y sí nombra sus propias
# cabeceras — distinto vocabulario del §10.6 (`Clave Hijo` en vez de
# "clave insumo", `Costo` en vez de "costo unitario") y una columna
# `Origen` que el §10.6 no tiene en absoluto. Mismo criterio que
# `PRESUPUESTO` (también extensión propia, más arriba en este archivo):
# sus columnas propias necesitan alias explícito, no caen en el mapa
# global de sinónimos del §8.6.
#
# Cada fila es un componente con su propio padre explícito (`Clave Padre`
# → `Clave Hijo`), nunca una fila-encabezado que describa al concepto
# mismo — por eso `clave_insumo` reusa el campo canónico que ya usa el
# componente del formato plano (`ComponenteCargado.clave_insumo`) en vez
# de inventar uno nuevo: es el mismo dato, "la clave del insumo de esta
# fila", solo que la columna real se llama distinto.

CPU_MATRIZ = EspecificacionArchivo(
    tipo="Análisis de básicos conceptos (matriz nativa de OPUS)",
    archivo="ANALISIS_DE_BASICOS_CONCEPTOS.csv",
    hoja=None,
    obligatorias=("clave_padre", "clave_insumo", "descripcion", "cantidad", "tipo", "origen"),
    opcionales=("unidad", "precio_unitario"),
    alias={
        "clave padre": "clave_padre",
        "clave_padre": "clave_padre",
        # El exportador nombra "Clave Hijo" al insumo del componente —
        # mismo dato que `clave_insumo` en el formato plano (§10.6), solo
        # que ahí la columna se llama "clave insumo"/"B" y aquí "Clave
        # Hijo". Sin este alias, "clave hijo" no resuelve a nada en el
        # mapa global y la columna se ignoraría en silencio: ninguna fila
        # tendría el insumo que compone (§3.3).
        "clave hijo": "clave_insumo",
        "clave_hijo": "clave_insumo",
        # "Costo" a secas, no "costo unitario" — el mapa global del §8.6
        # solo conoce la segunda forma. Sin este alias la columna F se
        # ignoraría y ningún componente traería PU.
        "costo": "precio_unitario",
        # `Origen` (Concepto/Material/ManoDeObra) no vive en ningún otro
        # archivo ni en el mapa global: sin alias propio se descartaría en
        # silencio, y es la columna que decide si la fila es de este
        # alcance (solo `Origen=Concepto`, §domain.cargadores.cpu.
        # _agrupar_conceptos_matriz) o de una matriz de insumo compuesto
        # (Material/ManoDeObra) que este cargador no toca.
        "origen": "origen",
    },
)
"""Catálogo de Conceptos + CPU, export nativo de OPUS
(`ANALISIS_DE_BASICOS_CONCEPTOS.csv`, 2568 filas verificadas): matriz
donde cada fila es un componente con su propio `Clave Padre` (el
concepto) → `Clave Hijo` (el insumo), a diferencia del formato plano de
`CPU` (fila encabezado `TIPO=Concepto` + sus componentes). Ninguna fila
describe al concepto mismo —`Descripción`/`Unidad` describen siempre al
hijo—, así que su identidad (descripción, unidad) no sale de este
archivo: `domain.cargadores.cpu._agrupar_conceptos_matriz` la recibe de
afuera, cruzada contra el árbol de `presupuesto.construir_arboles` sobre
`CATALOGO_DE_PRESUPUESTO.csv` (467/468 claves cruzan; la que no cruza
queda sin descripción y por tanto sin cargar, mismo criterio que
`_leer_encabezado` en modo plano).

`importe` no se declara a propósito: la columna existe en el archivo real
(G) pero ningún campo del dominio la guarda —`ComponenteCargado` no tiene
`importe`, el §7.3 lo recalcula de cantidad × PU—, así que cae sola en
`MapaColumnas.ignoradas` sin necesidad de alias ni de un campo nuevo."""

# --- Programa base de prototipo (extensión propia, no está en el §10.6) -
#
# Export real del cronograma hecho a mano en MS Project/OPUS, el mismo
# archivo que cerebro documenta en `1-mundo/PROGRAMA-CPM.md` y carga con
# `backend/core/programa.py`. No lo describe el §10.6 — igual que
# `PRESUPUESTO` y `PROTOTIPOS` — así que sus columnas propias necesitan
# alias explícito.
#
# El archivo real (`PROGRAMA_<PROTOTIPO>.xlsx`) trae, además de las de
# abajo, unas ~190 columnas tituladas "Cantidad" repetidas (un histograma de
# recurso por periodo) y columnas de avance/holgura/rendimiento que esta
# plantilla no necesita en absoluto. A propósito **no** se declaran aquí:
# una columna fuera de `obligatorias`/`opcionales` cae sola en `ignoradas`
# sin pasar por la regla de ambigüedad de `resolver_encabezados` — declarar
# "cantidad" aquí (como hace `PRESUPUESTO`) haría que las ~190 repeticiones
# choquen entre sí y el archivo se rechazara entero por un dato que el
# programa base ni siquiera guarda (`ItemProgramaBase` no tiene cantidad).

PROGRAMA_BASE = EspecificacionArchivo(
    tipo="Programa base de prototipo (cronograma, extensión propia)",
    archivo="PROGRAMA_<PROTOTIPO>.xlsx",
    hoja="Hoja1",
    # `Hoja2` del archivo real no trae encabezados ni columnas de identidad
    # —es un histograma de recurso por periodo, puras celdas numéricas o
    # vacías bajo un renglón de título en blanco—, así que no es la hoja a
    # leer (verificado contra el archivo real, confirmado con el usuario).
    obligatorias=("tipo", "nivel", "clave", "descripcion"),
    opcionales=("fecha_inicio", "fecha_termino", "dias_laborables", "vinculos", "indice"),
    alias={
        # "Nivel " (con espacio al final, igual que `PRESUPUESTO`): profundidad
        # del renglón en el árbol —0 el Capítulo, 4 el Concepto—, la misma
        # columna con la que `programa_base.leer_programa_base` reconstruye la
        # jerarquía (ver su docstring: no hay `clave_padre` en este archivo).
        "nivel": "nivel",
        "indice": "indice",
        "fecha de inicio": "fecha_inicio",
        "fecha de termino": "fecha_termino",
        "dias laborables": "dias_laborables",
        # "Vínculos": el texto fuente `<fila><FS|SS|FF|SF>[±horas]` de D-442/
        # D-443 (`1-mundo/MODELO.md` §5c). No vive en el mapa global del §8.6.
        "vinculos": "vinculos",
        # `1-mundo/programas/PROGRAMAS-PROTOTIPOS.csv` (§7.5, Paso 4 del
        # rollout): mismo contrato, otra ortografía de cabecera —sin acento,
        # sin "fecha de" y con guion bajo en vez de espacio—. Es el archivo
        # que de verdad trae la red resuelta para los 7 prototipos (ver el
        # docstring del módulo): `PROGRAMA_ZAFIRO.xlsx` solo trae `Vínculos`
        # nativo para Zafiro, vacío en los otros 6 (verificado contra los dos
        # archivos reales), así que la carga de verdad usa este archivo.
        "inicio": "fecha_inicio",
        "termino": "fecha_termino",
        "dias_laborables": "dias_laborables",
    },
)
"""Mismas cinco filas (`Capítulo · Subcapítulo · Nivel 2 · Nivel 3 ·
Concepto`) y el mismo árbol que `PRESUPUESTO`/`construir_arboles`, por
`nivel` + posición, nunca por `clave_padre` (ninguno de los dos archivos
reales de este contrato la trae). Dos archivos reales comparten este
contrato, y no son intercambiables:

- `PROGRAMA_<PROTOTIPO>.xlsx` (p. ej. `PROGRAMA_ZAFIRO.xlsx`): el export
  nativo de OPUS/MS Project, con **siete** `Capítulo` seguidos —los siete
  prototipos—, pero `Vínculos` solo viene poblado en el bloque de Zafiro;
  los otros seis no traen ningún vínculo nativo (verificado fila por fila
  contra el archivo real: 0 de ~2,700 filas).
- `1-mundo/programas/PROGRAMAS-PROTOTIPOS.csv`: el mismo cronograma de los
  siete, pero con la red ya resuelta para los seis que no la traían (columna
  `regla`: "gemelo por clave", "losa por altura", etc. — un vínculo por
  prototipo igual de real, solo que inferido en vez de tecleado en MS
  Project). Es la fuente que exige el plan del rollout ("la red mínima") y
  la que de verdad deja comparar las fechas de ObraCtrl contra las de
  cerebro (`backend/scripts/cargar_programas_prototipos.py`).

`domain.cargadores.programa_base` parte cualquiera de los dos archivos del
`prototipo_id` pedido."""

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


# --------------------------------------------------------------------------- catálogo de matrices (D-610)
#
# `CATALOGO_DE_MATRICES.csv`: el catálogo de conceptos del sistema (también se
# llama catálogo de conceptos, y sustituye al `CATALOGO_DE_CONCEPTOS` que la
# documentación citaba). Trae las **11 columnas**, y se conservan todas (D-610).
# `C` = `+` marca una matriz desglosable: su composición está en
# `ANALISIS_DE_BASICOS_CONCEPTOS`. El costo es independiente de la composición.
# Los conceptos auxiliares (`AUX`) no entran aquí (D-609).

CATALOGO_MATRICES_OPUS = EspecificacionArchivo(
    tipo="Catálogo de matrices (conceptos, export nativo de OPUS)",
    archivo="CATALOGO_DE_MATRICES.csv",
    hoja=None,
    obligatorias=("clave", "descripcion", "unidad"),
    opcionales=(
        "matriz_desglosable",
        "tipo",
        "familia",
        "subfamilia",
        "costo_base",
        "costo_base_me",
        "costo_unitario",
        "fecha",
    ),
    alias={
        # "Costo base M. N." es el costo base; "Costo base M. E." y "Costo
        # unitario" tienen su propio campo, sin pelear por el mismo alias.
        "costo base m. n.": "costo_base",
        "costo base m. e.": "costo_base_me",
        "costo unitario": "costo_unitario",
        # `C` es el marcador de matriz desglosable (`+`), no un costo.
        "c": "matriz_desglosable",
        # Las dos que el mapa global no conoce: se declaran para no perderlas.
        "subfamilia": "subfamilia",
        "fecha": "fecha",
    },
)
"""Catálogo de matrices, export nativo de OPUS (`CATALOGO_DE_MATRICES.csv`).

Las 11 columnas del archivo se declaran (D-610): nada se descarta en silencio.
`subfamilia` está vacía en las 472 filas hoy, pero la columna se conserva para
completarla después."""

