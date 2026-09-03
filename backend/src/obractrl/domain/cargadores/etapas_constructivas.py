"""Cargador del catálogo base de etapas de construcción: validación de
fila (§10.1).

Spec: catálogo base de identidad de etapas — clave, descripción, nada más
(orden/ponderación/importe quedan en su default; `nivel_id` queda sin
resolver — el archivo real no trae a qué nivel pertenece cada etapa, y
adivinarlo por la columna "TIPO" del archivo original sería inventar una
relación que el archivo no da: esa columna es la clasificación propia de
la herramienta de origen, no una referencia a nuestro catálogo de
niveles). Mismo criterio que `domain.cargadores.conceptos_base`: la clave
es la identidad (§3.3); si la fila no la trae, se numera sola
(`AplicadorEtapasConstructivas`, prefijo ``ECO``).

Módulo puro (§12.11): recibe la fila ya leída como celdas y devuelve la
entidad validada o levanta :class:`ErrorEnFila`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.reporte import ErrorEnFila
from obractrl.domain.shared.normalizacion import esta_vacio, normalizar, texto_limpio
from obractrl.domain.shared.valores import Clave

__all__ = [
    "FilaEtapaConstructiva",
    "es_tipo_de_renglon",
    "validar_etapa_constructiva",
]


def es_tipo_de_renglon(valor: object) -> bool:
    """¿Este "TIPO" es el del exportador y no un frente?

    El archivo real trae dos columnas llamadas `TIPO` y solo la última es el
    frente; la primera es el tipo de renglón de la herramienta de origen
    (`Nivel 2` en las cincuenta filas, `Subcapítulo` en otros catálogos suyos).

    Se descarta por **vocabulario cerrado y nombrado**, no por posición: si un
    día el exportador mueve la columna, esto sigue funcionando, y si alguien
    escribe mal un frente —`OBRAA`— no cae aquí y sale como error de fila en
    vez de perderse en silencio.
    """
    texto = normalizar(valor)
    if texto in {"subcapitulo", "capitulo", "partida", "concepto"}:
        return True
    resto = texto.removeprefix("nivel ")
    return resto != texto and resto.isdigit()


@dataclass(frozen=True, slots=True)
class FilaEtapaConstructiva:
    """Una fila válida del catálogo base de etapas de construcción (§10.1)."""

    clave: Clave | None
    descripcion: str
    frente: str | None = None
    """Clave o nombre del frente al que pertenece la etapa (§8.3).

    Viaja como texto: resolverlo contra el catálogo de `frente` es trabajo del
    aplicador, que es quien tiene la base delante. Nulo cuando el archivo no
    trae la columna o la deja vacía — una etapa sin frente es el estado normal
    mientras se captura (migración 0045).
    """

    fila: int = 0
    """Renglón del archivo. Viaja con el registro para que un pendiente
    pueda ligar al origen (§10.3), y le da una `llave` estable a una fila
    sin clave (ver abajo)."""

    @property
    def llave(self) -> str:
        """Identidad para dedup y diff dentro del archivo (§3.3, §10.2).

        Mismo criterio que `FilaConceptoBase.llave`: sin clave, el número
        de renglón evita que el pipeline confunda dos filas distintas con
        "la misma fila repetida" — `AplicadorEtapasConstructivas` reemplaza
        esto por la clave real (dada o generada) antes de tocar el
        catálogo.
        """
        return str(self.clave) if self.clave is not None else f"__sin_clave__{self.fila}"


def validar_etapa_constructiva(
    fila: Sequence[object], mapa: MapaColumnas, numero: int = 0
) -> FilaEtapaConstructiva:
    """Fila del archivo → `FilaEtapaConstructiva`, o :class:`ErrorEnFila`.

    La clave, si viene, se normaliza con `Clave` (§3.3); si no viene, la
    fila igual se acepta (ver `FilaEtapaConstructiva.clave`). La
    descripción es obligatoria — una etapa sin nombre no es identificable
    ni con clave propia ni con una generada.
    """
    celda_clave = mapa.valor(fila, "clave")
    clave: Clave | None = None
    if not esta_vacio(celda_clave):
        try:
            clave = Clave(str(celda_clave))
        except ValueError as exc:
            raise ErrorEnFila(str(exc), columna="clave", valor=celda_clave) from exc

    descripcion = texto_limpio(mapa.valor(fila, "descripcion"))
    if not descripcion:
        raise ErrorEnFila(
            "descripcion: una etapa sin descripción no es identificable (§10.1).",
            columna="descripcion",
            valor=mapa.valor(fila, "descripcion"),
        )

    return FilaEtapaConstructiva(
        clave=clave,
        descripcion=descripcion,
        frente=_frente_de(fila, mapa),
        fila=numero,
    )


def _frente_de(fila: Sequence[object], mapa: MapaColumnas) -> str | None:
    """El frente de la etapa, de entre las columnas `TIPO` del archivo.

    Se descarta el tipo de renglón del exportador (`es_tipo_de_renglon`) y lo
    que queda es el frente. Si quedaran dos, el archivo trae dos frentes para
    la misma etapa y eso **no** se resuelve adivinando: una etapa en dos frentes
    contaría su trabajo dos veces al planear cuántas cuadrillas hacen falta,
    que es justo lo que la migración 0045 evita con una columna en vez de un
    puente.
    """
    candidatos = [
        texto_limpio(celda)
        for celda in mapa.valores(fila, "frente")
        if not es_tipo_de_renglon(celda)
    ]
    candidatos = [c for c in candidatos if c]
    if not candidatos:
        return None
    if len(candidatos) > 1:
        raise ErrorEnFila(
            f"frente: la etapa trae {len(candidatos)} frentes "
            f"({', '.join(candidatos)}) y solo puede pertenecer a uno (§8.3). "
            f"En dos, su trabajo se contaría dos veces al planear cuadrillas.",
            columna="frente",
            valor=", ".join(candidatos),
        )
    return candidatos[0]
