"""Cargador de mano de obra / destajos: validación de fila
(§10.6 `CABECERAS_MANO_DE_OBRA.xlsx`, hoja `DESTAJOS`).

Spec §10.6 ("Mano de obra (Destajos): clave, clave_usuario, descripción,
unidad, cuadrilla, rendimiento_teórico/real, costo_unitario, familia") ·
§3.3 (la CLAVE manda).

Un renglón de mano de obra es un `Insumo` con ``tipo = 'mano_obra'`` (§7.3),
igual que un material lo es con ``tipo = 'material'``: este cargador
alimenta el mismo catálogo de insumos, no una tabla aparte.

``rendimiento_real`` del §10.6 **no** se lee aquí a propósito: sale de
cruzar contra la duración real de la obra, un cálculo posterior — este
archivo solo trae el teórico.

Extensión propia: `clase_de_trabajo`/`validar_trabajo` cargan
`CATALOGO_DE_TRABAJOS.csv` (export nativo de OPUS, §cabeceras.
TRABAJOS_OPUS) — destajos y subcontratos juntos en un solo archivo,
distinguidos por columna en vez de por archivo separado (§10.2).

Módulo puro (§12.11): recibe la fila ya leída como celdas y devuelve la
entidad validada o levanta :class:`ErrorEnFila`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.reporte import ErrorEnFila
from obractrl.domain.shared.diccionario import TipoInsumo
from obractrl.domain.shared.normalizacion import (
    ValorNoConvertible,
    a_decimal,
    esta_vacio,
    normalizar,
    texto_limpio,
)
from obractrl.domain.shared.valores import Clave

__all__ = [
    "FilaManoObra",
    "clase_de_trabajo",
    "validar_mano_obra",
    "validar_trabajo",
]


@dataclass(frozen=True, slots=True)
class FilaManoObra:
    """Una fila válida del catálogo de mano de obra / destajos (§10.6)."""

    clave: Clave
    descripcion: str
    unidad: str | None = None
    clave_unidad: str | None = None
    """Código de la unidad en su propio catálogo (§3.3) — distinto de
    ``unidad`` (el texto libre). Mismo criterio que en materiales."""

    familia: str | None = None
    cuadrilla: str | None = None
    """Clave de la cuadrilla que ejecuta este destajo — no texto libre: se
    homologa contra el catálogo de cuadrillas, dándola de alta si no
    existe (mismo criterio que unidad/familia, §8.7)."""

    rendimiento_teorico: Decimal | None = None
    costo_base: Decimal | None = None
    """``None`` = **la columna no vino** en esta fila — igual que en
    materiales, quien aplica la carga trata el ``None`` como "conserva lo
    vigente" (§10.2, modo Actualizar)."""

    tipo: TipoInsumo = TipoInsumo.MANO_OBRA

    fila: int = 0
    """Renglón del archivo. Viaja con el registro para que un pendiente
    pueda ligar al origen (§10.3) sin volver a abrir el libro."""

    @property
    def llave(self) -> str:
        """Identidad para dedup y diff: la CLAVE (§3.3, §10.2)."""
        return str(self.clave)


def _decimal_opcional(
    fila: Sequence[object], mapa: MapaColumnas, campo: str
) -> Decimal | None:
    celda = mapa.valor(fila, campo)
    if esta_vacio(celda):
        return None
    try:
        valor = a_decimal(celda, campo=campo)
    except ValorNoConvertible as exc:
        raise ErrorEnFila(str(exc), columna=campo, valor=celda) from exc
    if valor < 0:
        raise ErrorEnFila(
            f"{campo}: no puede ser negativo ({valor}).", columna=campo, valor=celda
        )
    return valor


def validar_mano_obra(
    fila: Sequence[object],
    mapa: MapaColumnas,
    numero: int = 0,
    *,
    tipo: TipoInsumo = TipoInsumo.MANO_OBRA,
) -> FilaManoObra:
    """Fila del archivo → `FilaManoObra`, o :class:`ErrorEnFila`.

    La **clave** es obligatoria y se normaliza con `Clave` (§3.3): sin ella
    no hay con qué deduplicar ni contra qué cruzar.

    ``tipo`` distingue mano de obra de subcontratos (§10.6): mismas
    cabeceras, mismo validador — lo fija `CargadorSubcontratos` vía
    `functools.partial`.
    """
    celda_clave = mapa.valor(fila, "clave")
    if esta_vacio(celda_clave):
        raise ErrorEnFila(
            "clave: la fila no trae clave y la clave es única por catálogo (§3.3).",
            columna="clave",
        )
    try:
        clave = Clave(str(celda_clave))
    except ValueError as exc:
        raise ErrorEnFila(str(exc), columna="clave", valor=celda_clave) from exc

    descripcion = texto_limpio(mapa.valor(fila, "descripcion"))
    if not descripcion:
        raise ErrorEnFila(
            "descripcion: es obligatoria (§10.1).",
            columna="descripcion",
            valor=mapa.valor(fila, "descripcion"),
        )

    return FilaManoObra(
        clave=clave,
        descripcion=descripcion,
        unidad=texto_limpio(mapa.valor(fila, "unidad")) or None,
        clave_unidad=texto_limpio(mapa.valor(fila, "clave_unidad")) or None,
        familia=texto_limpio(mapa.valor(fila, "familia")) or None,
        cuadrilla=texto_limpio(mapa.valor(fila, "cuadrilla")) or None,
        rendimiento_teorico=_decimal_opcional(fila, mapa, "rendimiento_teorico"),
        costo_base=_decimal_opcional(fila, mapa, "costo_base"),
        tipo=tipo,
        fila=numero,
    )


_CLASE_A_TIPO: dict[str, TipoInsumo] = {
    "destajo": TipoInsumo.MANO_OBRA,
    "subcontrato": TipoInsumo.SUBCONTRATO,
    "acarreo": TipoInsumo.ACARREO,
}
"""`Clase` del catálogo combinado de Trabajos (`CATALOGO_DE_TRABAJOS.csv`,
§cabeceras.TRABAJOS_OPUS) → `TipoInsumo`.

Tres clases: Destajo, Subcontrato y Acarreo. Acarreo no tiene filas en el
catálogo real (verificado) y se acepta como tipo propio (`TipoInsumo.ACARREO`,
migración 0095), decidido por el usuario; no se traduce a flete ni a otra
clase por parecido."""


_CATEGORIA_TRABAJO = "trabajo"
"""Valor esperado, normalizado, de la *categoría* (la segunda "Tipo" del
archivo — la constante, nunca la clase). No es una traducción: es el
único valor que esta columna puede tener (verificado: 265/265 filas del
archivo real), así que `clase_de_trabajo` la valida contra este literal
en vez de solo descartarla por exclusión — una segunda confirmación, no
redundante: si el exportador algún día cambia esa columna por algo
distinto de "Trabajo" (p.ej. la deja vacía, o la llena con la clase por
error), esto lo detecta con su propio mensaje en vez de que el error
genérico de "clase" (abajo) señale al lugar equivocado."""


def clase_de_trabajo(fila: Sequence[object], mapa: MapaColumnas) -> TipoInsumo:
    """La *clase* de una fila del catálogo de Trabajos — Destajo o
    Subcontrato —, para decidir con qué ``tipo`` validarla.

    El archivo repite la cabecera "Tipo" dos veces (§cabeceras.
    TRABAJOS_OPUS): la clase y, al final, la categoría genérica
    ("Trabajo", siempre). Las dos llegan juntas en la columna ``clase``
    (serie, no alias — el §8.6 rechazaría dos alias al mismo campo).
    Nunca por posición, para que esto siga funcionando si el exportador
    reordena las columnas — se distinguen por contenido, en dos pasos:

    1. Exactamente una debe decir "Trabajo" (`_CATEGORIA_TRABAJO`): es la
       categoría, y se exige explícita, no solo se asume por ser "la que
       no es la clase" — segunda confirmación de que la columna no
       cambió de forma inesperada.
    2. La que sobra es la clase real, y debe ser Destajo o Subcontrato
       (`_CLASE_A_TIPO`) — igual que antes.
    """
    valores = [texto_limpio(celda) for celda in mapa.valores(fila, "clase")]
    valores = [v for v in valores if v]

    categorias = [v for v in valores if normalizar(v) == _CATEGORIA_TRABAJO]
    if len(categorias) != 1:
        raise ErrorEnFila(
            f"clase: se esperaba que una de las dos columnas 'Tipo' dijera "
            f"literalmente 'Trabajo' (la categoría, §cabeceras.TRABAJOS_OPUS) "
            f"y se encontraron {len(categorias)} "
            f"({', '.join(categorias) or 'ninguna'}).",
            columna="clase",
            valor=", ".join(categorias) or None,
        )

    candidatos = [v for v in valores if normalizar(v) != _CATEGORIA_TRABAJO]
    if len(candidatos) != 1:
        raise ErrorEnFila(
            f"clase: se esperaba una sola clase de trabajo (Destajo, "
            f"Subcontrato o Acarreo) y se encontraron {len(candidatos)} "
            f"({', '.join(candidatos) or 'ninguna'}).",
            columna="clase",
            valor=", ".join(candidatos) or None,
        )

    texto = normalizar(candidatos[0])
    tipo = _CLASE_A_TIPO.get(texto)
    if tipo is None:
        raise ErrorEnFila(
            f"clase: {candidatos[0]!r} no es Destajo, Subcontrato ni Acarreo "
            f"(§cabeceras.TRABAJOS_OPUS).",
            columna="clase",
            valor=candidatos[0],
        )
    return tipo


def validar_trabajo(
    fila: Sequence[object], mapa: MapaColumnas, numero: int = 0
) -> FilaManoObra:
    """Fila del catálogo combinado de Trabajos (§cabeceras.TRABAJOS_OPUS)
    → `FilaManoObra`, con el ``tipo`` (mano_obra/subcontrato) que decide
    `clase_de_trabajo` — delega en `validar_mano_obra` para todo lo demás,
    mismo criterio que separa destajos de subcontratos hoy entre archivos
    (`CargadorSubcontratos`, vía `functools.partial`)."""
    tipo = clase_de_trabajo(fila, mapa)
    return validar_mano_obra(fila, mapa, numero, tipo=tipo)
