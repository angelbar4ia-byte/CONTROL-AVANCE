"""Caso de uso: generar la obra desde su prototipo (§11.3 workflow A).

Spec §7.4 (árbol WBS) · §7.5 (programa) · §7.6 (actividad) · §12.11 (capa de
aplicación).

Misma forma que el resto de los casos de uso: carga el estado, deja que el
dominio decida —`Obra.exigir_generable` y `planear_actividades`— y solo
entonces persiste. Ninguna regla vive aquí, solo la secuencia:

1. cargar la obra y verificar que se puede generar (§11.3 A.2);
2. leer el árbol del prototipo, el CPU vigente de sus conceptos y el programa
   base;
3. planear las actividades en el dominio (módulo puro);
4. instanciar el `ProgramaObra` y escribir las actividades **en la misma
   unidad de trabajo**: una obra a medio generar es peor que una sin generar.

**Evento `ObraGenerada` (§11.3 A.3):** el paso 3 del workflow dispara un job
de CPM inicial. El job vive en la Fase 3 del roadmap (Programación · CPM),
junto con el resto del motor; aquí se devuelve el `ProgramaObra` recién
instanciado para que quien encole ese job tenga a qué apuntar.

**Dependencias del cronograma:** las `dependencias` del `ProgramaBase` se
copian **tal cual** a la actividad. Sus `ref` apuntan a nodos o claves del
prototipo, no a los ids de las actividades recién creadas; resolverlas es
parte de la Fase 3, donde vive la instanciación versionada del programa
(§11.2 `POST /obras/{id}/programa`). Mientras tanto no rompen nada: el motor
CPM ignora las dependencias cuyo `ref` no está en el grafo
(`domain.programacion.cpm._orden_topologico`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from obractrl.application.puertos.repositorios import RepositorioObras, UnidadDeTrabajo
from obractrl.domain.obras.generacion import (
    ActividadPlaneada,
    ErrorDeGeneracion,
    ItemProgramaBase,
    NodoPrototipo,
    planear_actividades,
)
from obractrl.domain.obras.reglas import Obra
from obractrl.domain.programacion.cpm import Dependencia
from obractrl.domain.shared.diccionario import ClaseNodo, EstatusObra, ModoPago
from obractrl.domain.shared.valores import Avance, Clave, Dinero, PrecioUnitario

__all__ = [
    "ComandoGenerarObra",
    "ErrorDeGeneracion",
    "GenerarObraDesdePrototipo",
    "ObraGenerada",
    "ObraNoEncontrada",
    "reconstruir_obra",
]


class ObraNoEncontrada(LookupError):
    """La obra no existe o está fuera del alcance del usuario (RLS)."""


@dataclass(frozen=True, slots=True)
class ComandoGenerarObra:
    obra_id: UUID
    modo_pago: ModoPago = ModoPago.DESTAJO
    """Cómo se pagarán las actividades generadas (§6). El default es destajo,
    que es el modo con el que trabaja la cuadrilla en obra."""


@dataclass(frozen=True, slots=True)
class ObraGenerada:
    """Resultado del workflow A: qué se creó y sobre qué programa."""

    obra_id: UUID
    programa_obra_id: UUID
    n_actividades: int


def reconstruir_obra(fila: dict) -> Obra:
    """Reconstruye la entidad desde lo persistido para aplicarle la siguiente
    operación — no pasa por `Obra.crear`, eso ya ocurrió."""
    return Obra(
        cluster_id=str(fila["cluster_id"]),
        clave=Clave(fila["clave"]),
        prototipo_id=str(fila["prototipo_id"]) if fila["prototipo_id"] else None,
        residente_id=str(fila["residente_id"]) if fila["residente_id"] else None,
        estatus=EstatusObra(fila["estatus"]),
        fecha_inicio=fila["fecha_inicio"],
        fecha_fin=fila["fecha_fin"],
        avance=Avance(fila["avance_pct"] or 0),
        m2=fila["m2"],
        es_urba=bool(fila["es_urba"]),
    )


def _a_nodo(fila: dict) -> NodoPrototipo:
    return NodoPrototipo(
        id=str(fila["id"]),
        tipo=ClaseNodo(fila["tipo"]),
        nombre=fila["nombre"],
        parent_id=str(fila["parent_id"]) if fila["parent_id"] else None,
        concepto_id=str(fila["concepto_id"]) if fila["concepto_id"] else None,
        nivel_id=str(fila["nivel_id"]) if fila["nivel_id"] else None,
        etapa_id=str(fila["etapa_id"]) if fila["etapa_id"] else None,
        cantidad=Decimal(str(fila["cantidad"] or 0)),
    )


def _a_item(fila: dict) -> ItemProgramaBase:
    return ItemProgramaBase(
        duracion_dias=Decimal(str(fila["duracion_dias"])),
        prototipo_nodo_id=str(fila["prototipo_nodo_id"])
        if fila["prototipo_nodo_id"]
        else None,
        etapa_id=str(fila["etapa_id"]) if fila["etapa_id"] else None,
        frente_id=str(fila["frente_id"]) if fila["frente_id"] else None,
        dependencias=tuple(
            Dependencia.desde_jsonb(dep) for dep in (fila["dependencias"] or [])
        ),
        orden=fila["orden"],
    )


def _a_precio(fila: dict) -> PrecioUnitario:
    return PrecioUnitario(
        total=Dinero(fila["precio_unitario"]),
        destajo=Dinero(fila["precio_destajo"]),
    )


def _a_registro(planeada: ActividadPlaneada) -> dict:
    """Aplana la actividad planeada a lo que espera el repositorio."""
    return {
        "concepto_id": planeada.concepto_id,
        "descripcion": planeada.descripcion,
        "frente_id": planeada.frente_id,
        "nivel_id": planeada.nivel_id,
        "etapa_id": planeada.etapa_id,
        "cant_base": planeada.cant_base,
        "precio_unitario": planeada.precio.total.monto,
        "precio_destajo": planeada.precio.destajo.monto,
        "modo_pago": planeada.modo_pago.value,
        "duracion_dias": planeada.duracion_dias,
        "dependencias": json.dumps(
            [
                {"ref": dep.ref, "tipo": dep.tipo, "lag_dias": dep.lag_dias}
                for dep in planeada.dependencias
            ]
        ),
    }


class GenerarObraDesdePrototipo:
    """Workflow A: `POST /obras/{id}/generar` (Control de obra, §11.2)."""

    def __init__(self, *, obras: RepositorioObras, uow: UnidadDeTrabajo) -> None:
        self._obras = obras
        self._uow = uow

    async def ejecutar(self, cmd: ComandoGenerarObra) -> ObraGenerada:
        fila = await self._obras.obtener(cmd.obra_id)
        if fila is None:
            raise ObraNoEncontrada(
                f"Obra {cmd.obra_id} no encontrada en tu alcance."
            )

        obra = reconstruir_obra(fila)
        prototipo_id = obra.exigir_generable(
            ya_tiene_actividades=await self._obras.tiene_actividades(cmd.obra_id)
        )

        nodos = [_a_nodo(f) for f in await self._obras.arbol_prototipo(UUID(prototipo_id))]
        conceptos = [
            UUID(nodo.concepto_id)
            for nodo in nodos
            if nodo.tipo is ClaseNodo.CONCEPTO and nodo.concepto_id
        ]
        precios = {
            concepto_id: _a_precio(datos)
            for concepto_id, datos in (
                await self._obras.precios_vigentes(conceptos)
            ).items()
        }
        programa_base = [
            _a_item(f) for f in await self._obras.items_programa_base(UUID(prototipo_id))
        ]

        planeadas = planear_actividades(
            nodos=nodos,
            precios=precios,
            programa_base=programa_base,
            modo_pago=cmd.modo_pago,
        )

        async with self._uow:
            programa_obra_id = await self._obras.instanciar_programa(cmd.obra_id)
            await self._obras.crear_actividades(
                cmd.obra_id,
                programa_obra_id,
                [_a_registro(planeada) for planeada in planeadas],
            )
            await self._uow.commit()

        return ObraGenerada(
            obra_id=cmd.obra_id,
            programa_obra_id=programa_obra_id,
            n_actividades=len(planeadas),
        )
