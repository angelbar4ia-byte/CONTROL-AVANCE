"""Aplicador del catálogo de matrices (D-609, D-610, migración 0096).

Da de alta cada matriz del catálogo como `concepto` (tipo `matriz`) y, si trae
costo, crea su versión inicial con el PU congelado (MODELO §4, D-227). Las
unidades y las familias que no existen se dan de alta (D-610).

Alcance de esta versión (decidido con el usuario):
- Solo altas. Una matriz que ya existe por clave **no se toca**: sus cambios
  de costo o de descripción quedan pendientes de decidir, y se reportan.
- Los conceptos auxiliares no entran (D-609): este aplicador recibe filas ya
  validadas por `validar_matriz_catalogo`, y el catálogo no trae `AUX`.
- `dry_run=True` calcula el mismo resultado sin escribir nada.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from obractrl.domain.cargadores.matrices_catalogo import FilaMatrizCatalogo
from obractrl.domain.shared.diccionario import TipoConcepto


@dataclass(frozen=True)
class ResultadoMatrices:
    """Qué entró, qué ya estaba y qué se dio de alta de más, sin escribir si `dry_run`."""

    altas: tuple[str, ...] = ()
    ya_existentes: tuple[str, ...] = ()
    sin_costo: tuple[str, ...] = ()
    unidades_nuevas: tuple[str, ...] = ()
    familias_nuevas: tuple[str, ...] = ()
    versiones_creadas: int = 0
    dry_run: bool = True


@dataclass
class _Estado:
    unidades_por_clave: dict[str, dict[str, Any]] = field(default_factory=dict)
    familias_por_nombre: dict[str, dict[str, Any]] = field(default_factory=dict)


class AplicadorMatricesCatalogo:
    def __init__(
        self,
        *,
        conceptos: Any,
        unidades: Any,
        familias: Any,
        versiones: Any,
    ) -> None:
        self._conceptos = conceptos
        self._unidades = unidades
        self._familias = familias
        self._versiones = versiones

    async def aplicar(
        self, filas: Sequence[FilaMatrizCatalogo], *, dry_run: bool
    ) -> ResultadoMatrices:
        vigentes = {
            str(f["clave"]): f for f in await self._conceptos.listar(solo_activos=False)
        }
        estado = _Estado(
            unidades_por_clave={
                str(u["clave"]): u
                for u in await self._unidades.listar(solo_activos=False)
            },
            familias_por_nombre={
                str(f["nombre"]): f
                for f in await self._familias.listar(
                    aplica_a="concepto", solo_activos=False
                )
            },
        )

        altas: list[str] = []
        ya: list[str] = []
        sin_costo: list[str] = []
        unidades_nuevas: list[str] = []
        familias_nuevas: list[str] = []
        versiones = 0

        for fila in filas:
            clave = str(fila.clave)
            if clave in vigentes:
                ya.append(clave)
                continue

            unidad_id = await self._unidad(fila.unidad, estado, unidades_nuevas, dry_run)
            familia_id = await self._familia(fila, estado, familias_nuevas, dry_run)

            altas.append(clave)
            if fila.costo_unitario is None:
                sin_costo.append(clave)

            if dry_run:
                continue

            concepto_id = await self._conceptos.crear(
                {
                    "tipo": str(TipoConcepto.MATRIZ),
                    "clave": clave,
                    "descripcion": fila.descripcion,
                    "unidad_id": unidad_id,
                    "familia_id": familia_id,
                }
            )
            if fila.costo_unitario is not None:
                await self._versiones.crear(
                    {"concepto_id": concepto_id, "version": 1, "pu": fila.costo_unitario}
                )
                versiones += 1

        return ResultadoMatrices(
            altas=tuple(altas),
            ya_existentes=tuple(ya),
            sin_costo=tuple(sin_costo),
            unidades_nuevas=tuple(unidades_nuevas),
            familias_nuevas=tuple(familias_nuevas),
            versiones_creadas=versiones,
            dry_run=dry_run,
        )

    async def _unidad(
        self, clave: str, estado: _Estado, nuevas: list[str], dry_run: bool
    ) -> UUID | None:
        if clave in estado.unidades_por_clave:
            return estado.unidades_por_clave[clave].get("id")
        if clave not in nuevas:
            nuevas.append(clave)
        if dry_run:
            return None
        uid = await self._unidades.crear_o_existente({"clave": clave, "nombre": clave})
        estado.unidades_por_clave[clave] = {"id": uid, "clave": clave}
        return uid

    async def _familia(
        self, fila: FilaMatrizCatalogo, estado: _Estado, nuevas: list[str], dry_run: bool
    ) -> UUID | None:
        if not fila.familia:
            return None
        padre_id = await self._dar_familia(fila.familia, None, estado, nuevas, dry_run)
        if fila.subfamilia:
            return await self._dar_familia(
                fila.subfamilia, padre_id, estado, nuevas, dry_run
            )
        return padre_id

    async def _dar_familia(
        self,
        nombre: str,
        padre_id: UUID | None,
        estado: _Estado,
        nuevas: list[str],
        dry_run: bool,
    ) -> UUID | None:
        if nombre in estado.familias_por_nombre:
            return estado.familias_por_nombre[nombre].get("id")
        if nombre not in nuevas:
            nuevas.append(nombre)
        if dry_run:
            return None
        datos: dict[str, Any] = {
            "clave": nombre,
            "nombre": nombre,
            "aplica_a": "concepto",
        }
        if padre_id is not None:
            datos["parent_id"] = padre_id
        fid = await self._familias.crear_o_existente(datos)
        estado.familias_por_nombre[nombre] = {"id": fid, "nombre": nombre}
        return fid
