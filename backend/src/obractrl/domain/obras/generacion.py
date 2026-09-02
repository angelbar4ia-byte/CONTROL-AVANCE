"""Planeación de actividades desde el prototipo — Workflow A (§11.3 A.2).

Spec §7.4 (árbol WBS) · §7.5 (programa base) · §7.6 (actividad) · §11.3 A.

El §11.3 A.2 lo dice completo: *"el servicio recorre el árbol `PrototipoNodo`
(etapas → niveles → conceptos) y crea las `Actividad` (concepto, frente,
nivel, `cant_base`, `precio_unitario`/`precio_destajo` desde el CPU vigente);
instancia `ProgramaObra` desde el `ProgramaBase`"*. Eso es exactamente lo que
hace `planear_actividades`, y nada más: **decide qué actividades deben
existir**; escribirlas es del caso de uso (§12.11).

Tres fuentes se cruzan aquí:

* **el árbol** (`NodoPrototipo`) da qué conceptos entran y con qué cantidad.
  Solo las hojas de tipo ``concepto`` se vuelven actividad; ``etapa`` y
  ``nivel`` son estructura, y su `nivel_id`/`etapa_id` se **hereda** hacia
  abajo —el nodo concepto casi nunca los trae, los trae su ancestro;
* **el CPU vigente** (`precios`) da `precio_unitario` y `precio_destajo`. Sin
  CPU no hay actividad: no se inventa un precio cero, se falla con la lista
  completa de conceptos sin precio para que Control de obra la corrija de una
  sola pasada;
* **el programa base** (`ItemProgramaBase`) da `frente_id`, `duracion_dias`,
  `dependencias` y `tramos` —la interrupción de la actividad, §7.6, que es de
  la secuencia constructiva del prototipo y por eso baja desde aquí. Es
  opcional: sin programa base la actividad nace con un día
  de duración y sin frente, y la programación se ajusta después (§11.2
  `PATCH /actividades/{id}/programacion`).

Módulo puro: recibe y devuelve dataclasses, no toca la BD (§12.11) — igual que
`domain.programacion.cpm`, de donde se reutiliza `Dependencia` tal cual para
no tener dos formas de la misma precedencia. `ItemProgramaBase` y el criterio
con el que un item le toca a un nodo (`item_aplicable`) viven en
`domain.programacion.reglas`, que es su contexto (§7.5): la generación de la
obra los **consume**, no los redefine — si discreparan, una obra nacería con
un cronograma distinto del que le instancia `POST /obras/{id}/programa`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from obractrl.domain.obras.reglas import ErrorDeObra
from obractrl.domain.programacion.cpm import Dependencia, Tramo
from obractrl.domain.programacion.reglas import (
    DURACION_POR_DEFECTO,
    ItemProgramaBase,
    item_aplicable,
)
from obractrl.domain.shared.diccionario import ClaseNodo, ModoPago
from obractrl.domain.shared.valores import PrecioUnitario

__all__ = [
    "ActividadPlaneada",
    "ErrorDeGeneracion",
    "ItemProgramaBase",
    "NodoPrototipo",
    "planear_actividades",
]

_DURACION_POR_DEFECTO = DURACION_POR_DEFECTO
"""Alias local del default del §7.5, que ahora vive en `programacion.reglas`."""


class ErrorDeGeneracion(ErrorDeObra):
    """El prototipo no alcanza para generar la obra (§11.3 A.2)."""


@dataclass(frozen=True, slots=True)
class NodoPrototipo:
    """Un nodo del árbol WBS del prototipo (§7.4).

    Llega ya ordenado en recorrido en profundidad —padre antes que hijos—
    desde `RepositorioObras.arbol_prototipo`.
    """

    id: str
    tipo: ClaseNodo
    nombre: str
    parent_id: str | None = None
    concepto_id: str | None = None
    nivel_id: str | None = None
    etapa_id: str | None = None
    cantidad: Decimal = Decimal(0)


@dataclass(frozen=True, slots=True)
class ActividadPlaneada:
    """Una `Actividad` antes de existir en la BD (§7.6)."""

    prototipo_nodo_id: str
    concepto_id: str
    descripcion: str
    cant_base: Decimal
    precio: PrecioUnitario
    modo_pago: ModoPago
    orden: int
    frente_id: str | None = None
    nivel_id: str | None = None
    etapa_id: str | None = None
    duracion_dias: Decimal = _DURACION_POR_DEFECTO
    dependencias: tuple[Dependencia, ...] = field(default=())
    tramos: tuple[Tramo, ...] = field(default=())
    inicio_dias: Decimal | None = None


def _indexar(nodos: Sequence[NodoPrototipo]) -> dict[str, NodoPrototipo]:
    indice: dict[str, NodoPrototipo] = {}
    for nodo in nodos:
        if nodo.id in indice:
            raise ErrorDeGeneracion(
                f"El árbol del prototipo trae el nodo {nodo.id!r} dos veces."
            )
        indice[nodo.id] = nodo
    return indice


def _heredar(
    nodo: NodoPrototipo, indice: Mapping[str, NodoPrototipo], campo: str
) -> str | None:
    """Sube por el árbol hasta encontrar el primer ancestro con `campo`.

    El nodo `concepto` rara vez trae `nivel_id`/`etapa_id` propios: los trae
    la rama que lo contiene (etapa → nivel → concepto, §7.4). Sin esta
    herencia la actividad nacería sin nivel ni etapa y el Gantt no podría
    agruparla.
    """
    actual: NodoPrototipo | None = nodo
    vistos: set[str] = set()

    while actual is not None:
        valor = getattr(actual, campo)
        if valor:
            return str(valor)

        if actual.id in vistos:
            raise ErrorDeGeneracion(
                f"El árbol del prototipo tiene un ciclo en el nodo {actual.id!r}: "
                f"no se puede recorrer."
            )
        vistos.add(actual.id)

        if actual.parent_id is None:
            return None
        padre = indice.get(actual.parent_id)
        if padre is None:
            raise ErrorDeGeneracion(
                f"El nodo {actual.id!r} apunta a un padre {actual.parent_id!r} que "
                f"no está en el árbol: el prototipo está incompleto (§7.4)."
            )
        actual = padre

    return None


def planear_actividades(
    *,
    nodos: Sequence[NodoPrototipo],
    precios: Mapping[str, PrecioUnitario],
    programa_base: Sequence[ItemProgramaBase] = (),
    modo_pago: ModoPago = ModoPago.DESTAJO,
) -> list[ActividadPlaneada]:
    """Recorre el árbol y devuelve las actividades a crear (§11.3 A.2).

    `precios` mapea `concepto_id` → CPU vigente. `programa_base` es opcional.
    El orden de salida respeta el del árbol de entrada, que ya viene en
    recorrido en profundidad (§7.4).
    """
    indice = _indexar(nodos)
    sin_precio: list[str] = []
    planeadas: list[ActividadPlaneada] = []

    for nodo in nodos:
        if nodo.tipo is not ClaseNodo.CONCEPTO:
            continue

        if not nodo.concepto_id:
            raise ErrorDeGeneracion(
                f"El nodo {nodo.id!r} es de tipo 'concepto' pero no apunta a "
                f"ningún concepto (§7.4)."
            )

        if nodo.cantidad < 0:
            raise ErrorDeGeneracion(
                f"La cantidad del nodo {nodo.id!r} es negativa ({nodo.cantidad}): "
                f"no puede ser la 'cant_base' de una actividad (§6)."
            )

        precio = precios.get(str(nodo.concepto_id))
        if precio is None:
            sin_precio.append(str(nodo.concepto_id))
            continue

        etapa_id = _heredar(nodo, indice, "etapa_id")
        item = item_aplicable(nodo.id, etapa_id, programa_base)

        planeadas.append(
            ActividadPlaneada(
                prototipo_nodo_id=nodo.id,
                concepto_id=str(nodo.concepto_id),
                descripcion=nodo.nombre,
                cant_base=nodo.cantidad,
                precio=precio,
                modo_pago=modo_pago,
                orden=len(planeadas),
                frente_id=item.frente_id if item else None,
                nivel_id=_heredar(nodo, indice, "nivel_id"),
                etapa_id=etapa_id,
                duracion_dias=item.duracion_dias if item else _DURACION_POR_DEFECTO,
                dependencias=item.dependencias if item else (),
                # Sin los tramos la actividad nacería con los días de trabajo
                # del item pero sin el hueco, y su span saldría corto: las
                # sucesoras arrancarían antes de que el último tramo cierre.
                tramos=item.tramos if item else (),
                # El ancla baja con el resto de la plantilla: si el prototipo
                # dice que esta actividad arranca el día 30, la obra generada
                # nace con ella clavada ahí y no en el día que le tocaría.
                inicio_dias=item.inicio_dias if item else None,
            )
        )

    if sin_precio:
        # Se listan todos, no solo el primero: Control de obra corrige el
        # catálogo de una sola pasada en vez de generar-fallar-repetir.
        faltantes = ", ".join(sorted(set(sin_precio)))
        raise ErrorDeGeneracion(
            f"No hay CPU vigente para {len(set(sin_precio))} concepto(s) del "
            f"prototipo: {faltantes}. Carga su precio antes de generar la obra "
            f"(§11.3 A.2)."
        )

    if not planeadas:
        raise ErrorDeGeneracion(
            "El árbol del prototipo no tiene ningún nodo de tipo 'concepto': no "
            "hay nada que generar (§7.4)."
        )

    return planeadas
