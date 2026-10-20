"""Cargador del catálogo de contratistas: validación de fila (§8.3, §10.6).

El contratista es la **fuerza de trabajo**: él pone las cuadrillas con las que
un frente se ejecuta. Por eso la fila trae, además de su identidad, los frentes
que sabe hacer — es lo que después deja proponer candidatos cuando el residente
asigna quién lleva `INSTALACIONES` en una obra.

## Qué se valida y qué no

`razon_social` es la identidad obligatoria: sin ella el registro no se puede
referir ni presentar, y una fila así va a la bandeja (§10.3) en vez de entrar
a medias. `clave`, si el archivo no la trae, no tumba la fila —
`AplicadorContratistas` le genera una (§8.7) — mismo criterio que
familias/niveles/etapas/unidades: ObraCtrl ya sabe numerar un catálogo base
que llega sin ella, y el contratista no es la excepción.

`rfc`, `contacto`, `telefono` y `email` viajan como texto tal cual. **No se
valida el formato del RFC ni del correo**: un contratista real llega con el
dato incompleto o con un RFC provisional, y rechazar la fila por eso dejaría
fuera a quien sí está trabajando en la obra. El catálogo es una agenda, no un
registro fiscal.

`frentes` y `especialidades` son los **dos ejes** de lo que sabe hacer (§8.3):

* el **frente** es la clase de fuerza de trabajo —OBRA, INSTALACIONES,
  SUBCONTRATOS, PINTURA—, la misma clasificación que llevan las etapas;
* la **especialidad** es el oficio —OBRA CIVIL, ACABADOS, CARPINTERIA,
  HERRERIA…—, la misma que llevan los conceptos (migración 0047).

Los dos aceptan dos formas, porque los archivos reales usan las dos: una celda
con la lista separada por coma (`EST, INS`) o varias columnas numeradas
(`TIPO 1`, `TIPO 2`, `ESPECIALIDAD 1..5`), que la cabecera junta como serie.

Las referencias se normalizan pero **no** se comprueban contra el catálogo: eso
lo hace el aplicador, que es quien las puede resolver a ids —por clave o por
nombre, que en estos archivos viene lo segundo— y mandar a la bandeja las que
no existan. Aquí no hay con qué.

Módulo puro (§12.11): recibe la fila ya leída como celdas y devuelve la
entidad validada o levanta :class:`ErrorEnFila`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.reporte import ErrorEnFila
from obractrl.domain.shared.normalizacion import esta_vacio, texto_limpio
from obractrl.domain.shared.valores import Clave

__all__ = ["FilaContratista", "validar_contratista"]

_SEPARADORES = (",", ";", "/", "|")
"""Con qué se pueden separar los frentes en la celda. Cuatro y no uno porque el
archivo lo escribe una persona y ninguna de las cuatro formas es un error."""


@dataclass(frozen=True, slots=True)
class FilaContratista:
    """Una fila válida del catálogo de contratistas (§8.3)."""

    clave: Clave | None
    razon_social: str
    rfc: str | None = None
    contacto: str | None = None
    telefono: str | None = None
    email: str | None = None
    frentes: tuple[Clave, ...] = field(default=())
    """Frentes que sabe hacer, por clave o por nombre. Alimentan
    `contratista_frente`, que es **capacidad de catálogo** y no la asignación a
    una obra: quién lleva un frente en MAPLE 01 se decide al planear esa obra."""

    especialidades: tuple[Clave, ...] = field(default=())
    """Oficios que sabe hacer, por clave o por nombre (migración 0047).

    El otro eje: un contratista de frente OBRA puede hacer OBRA CIVIL y
    ACABADOS, y es lo que deja proponerlo cuando el trabajo pendiente es de
    ese oficio. Alimentan `contratista_especialidad`."""

    fila: int = 0
    """Renglón del archivo, para que un pendiente pueda ligar al origen (§10.3)."""

    @property
    def llave(self) -> str:
        """Identidad para dedup y diff dentro del archivo (§3.3, §10.2).

        Mismo criterio que `FilaFamilia.llave`: sin clave, el número de
        renglón evita que el pipeline confunda dos filas distintas con "la
        misma fila repetida" — `AplicadorContratistas` la reemplaza por la
        clave real (dada o generada) antes de tocar el catálogo.
        """
        return str(self.clave) if self.clave is not None else f"__sin_clave__{self.fila}"


def validar_contratista(
    fila: Sequence[object], mapa: MapaColumnas, numero: int = 0
) -> FilaContratista:
    """Fila del archivo → `FilaContratista`, o :class:`ErrorEnFila`.

    La clave, si viene, se normaliza con `Clave` (§3.3); si no viene, la
    fila igual se acepta y `AplicadorContratistas` le genera una (§8.7,
    `CON-00001` en adelante) — ObraCtrl ya tiene este mecanismo para
    familias/niveles/etapas/unidades, y un contratista sin clave propia en
    el archivo no es menos real que uno de esos catálogos sin la suya.
    """
    celda_clave = mapa.valor(fila, "clave")
    clave: Clave | None = None
    if not esta_vacio(celda_clave):
        try:
            clave = Clave(str(celda_clave))
        except ValueError as exc:
            raise ErrorEnFila(str(exc), columna="clave", valor=celda_clave) from exc

    razon_social = texto_limpio(mapa.valor(fila, "razon_social"))
    if not razon_social:
        raise ErrorEnFila(
            "razon_social: un contratista sin razón social no se puede "
            "presentar en una orden ni en una estimación (§8.3).",
            columna="razon_social",
            valor=mapa.valor(fila, "razon_social"),
        )

    return FilaContratista(
        clave=clave,
        razon_social=razon_social,
        rfc=_opcional(mapa.valor(fila, "rfc")),
        contacto=_opcional(mapa.valor(fila, "contacto")),
        telefono=_opcional(mapa.valor(fila, "telefono")),
        email=_opcional(mapa.valor(fila, "email")),
        frentes=_referencias(mapa, fila, "frentes"),
        especialidades=_referencias(mapa, fila, "especialidades"),
        fila=numero,
    )


def _opcional(celda: object) -> str | None:
    """Texto limpio, o `None` si la celda viene vacía.

    Cadena vacía y ausente son lo mismo aquí: las dos significan "no lo
    capturaron", y guardar `''` haría que la pantalla enseñara un campo lleno
    de nada en vez de decir que falta.
    """
    texto = texto_limpio(celda)
    return texto or None


def _referencias(
    mapa: MapaColumnas, fila: Sequence[object], campo: str
) -> tuple[Clave, ...]:
    """Las referencias de un campo, vengan en una celda o en varias columnas.

    Los archivos reales usan las dos formas y ninguna es un error: una plantilla
    escribe `EST, INS` en una celda y el export de la constructora reparte
    `ESPECIALIDAD 1..5`. Se juntan aquí para que el resto del cargador no tenga
    que saber cuál de las dos llegó.
    """
    celdas = mapa.valores(fila, campo) or (mapa.valor(fila, campo),)
    salida: list[Clave] = []
    vistas: set[str] = set()
    for celda in celdas:
        for clave in _claves_de_frentes(celda):
            if str(clave) in vistas:
                continue
            vistas.add(str(clave))
            salida.append(clave)
    return tuple(salida)


def _claves_de_frentes(celda: object) -> tuple[Clave, ...]:
    """`"EST, INS"` → `(Clave('EST'), Clave('INS'))`.

    Una clave mal formada se **descarta** en vez de tumbar la fila: el
    contratista sigue siendo válido sin ella, y perder toda su alta por una
    coma de más sería desproporcionado. Qué frentes no se pudieron resolver lo
    reporta el aplicador, que es quien los cruza contra el catálogo.
    """
    texto = texto_limpio(celda)
    if not texto:
        return ()

    for separador in _SEPARADORES[1:]:
        texto = texto.replace(separador, _SEPARADORES[0])

    salida: list[Clave] = []
    vistas: set[str] = set()
    for pedazo in texto.split(_SEPARADORES[0]):
        limpio = pedazo.strip()
        if not limpio:
            continue
        try:
            clave = Clave(limpio)
        except ValueError:
            continue
        if str(clave) in vistas:
            continue
        vistas.add(str(clave))
        salida.append(clave)
    return tuple(salida)
