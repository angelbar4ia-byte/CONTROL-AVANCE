"""SQL de las plantillas de muro, el artefacto (migración 0133). RLS por organización."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.domain.cuantificacion.muro_plantilla import ErrorDePlantillaDeMuro

__all__ = ["RepositorioPlantillasDeMuroSQL"]

_COLUMNAS = """
    p.id, p.raiz_id, p.version, p.vigente, p.nombre, p.tipo, p.material, p.ubicacion, p.altura_m, p.partes, p.elementos, p.acabado,
    p.validacion, p.propuso_id, u1.nombre as propuso_nombre, p.propuso_rol, p.validada_por, u2.nombre as validada_por_nombre,
    p.validada_en, p.created_at, p.updated_at, p.prototipo, p.planta, p.notas, p.por_confirmar,
    (select count(*) from trazo t where t.muro_plantilla_id = p.id) as trazos
"""
_DE = """
    from muro_plantilla p
    left join usuario u1 on u1.id = p.propuso_id
    left join usuario u2 on u2.id = p.validada_por
"""


class RepositorioPlantillasDeMuroSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def listar(self) -> list[dict[str, Any]]:
        """Las versiones vigentes de cada plantilla, por nombre."""
        filas = (
            await self._sesion.execute(text(f"select {_COLUMNAS} {_DE} where p.vigente order by lower(p.nombre)"))
        ).mappings().all()
        return [dict(f) for f in filas]

    async def obtener(self, plantilla_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(text(f"select {_COLUMNAS} {_DE} where p.id = :i"), {"i": str(plantilla_id)})
        ).mappings().one_or_none()
        return dict(fila) if fila else None

    async def versiones(self, raiz_id: UUID) -> list[dict[str, Any]]:
        """Todas las versiones de la plantilla, de la más nueva a la más vieja (los trazos ya medidos usan las anteriores)."""
        filas = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} {_DE} where p.raiz_id = :r order by p.version desc"), {"r": str(raiz_id)}
            )
        ).mappings().all()
        return [dict(f) for f in filas]

    async def _en_conflicto(self, error: IntegrityError, nombre: str) -> ErrorDePlantillaDeMuro:
        if "ux_muro_plantilla_nombre" in str(error.orig):
            return ErrorDePlantillaDeMuro(f"Ya hay una plantilla de muro llamada «{nombre}».")
        return ErrorDePlantillaDeMuro("La plantilla choca con otra versión: vuelve a abrirla.")

    async def crear(self, *, plantilla_id: UUID, raiz_id: UUID, version: int, datos: dict[str, Any], autor_id: UUID, rol: str) -> None:
        """Inserta una plantilla (la versión 1 o una versión nueva). Nace por validar."""
        try:
            async with self._sesion.begin_nested():
                await self._sesion.execute(
                    text(
                        """
                        insert into muro_plantilla (id, org_id, raiz_id, version, vigente, nombre, tipo, material, ubicacion, altura_m,
                                                    partes, elementos, acabado, propuso_id, propuso_rol,
                                                    prototipo, planta, notas, por_confirmar)
                        select :id, app.current_org_id(), :raiz, :v, true, :nombre, :tipo, :material, :ubicacion, :altura,
                               cast(:partes as jsonb), cast(:elementos as jsonb), cast(:acabado as jsonb), :autor, :rol,
                               :prototipo, :planta, :notas, :por_confirmar
                        """
                    ),
                    self._valores(datos)
                    | {"id": str(plantilla_id), "raiz": str(raiz_id), "v": version, "autor": str(autor_id), "rol": rol},
                )
        except IntegrityError as e:
            raise await self._en_conflicto(e, datos["nombre"]) from e

    @staticmethod
    def _valores(datos: dict[str, Any]) -> dict[str, Any]:
        return {
            "nombre": datos["nombre"],
            "tipo": datos["tipo"],
            "material": datos["material"],
            "ubicacion": datos["ubicacion"],
            "altura": datos["altura_m"],
            "partes": json.dumps(datos["partes"]),
            "elementos": json.dumps(datos["elementos"]),
            "acabado": json.dumps(datos["acabado"]) if datos.get("acabado") is not None else None,
            "prototipo": datos.get("prototipo"),
            "planta": datos.get("planta"),
            "notas": datos.get("notas"),
            "por_confirmar": bool(datos.get("por_confirmar")),
        }

    async def reemplazar(self, plantilla_id: UUID, datos: dict[str, Any], *, autor_id: UUID, rol: str) -> None:
        """Edita en el lugar una plantilla aún por validar."""
        try:
            async with self._sesion.begin_nested():
                await self._sesion.execute(
                    text(
                        """
                        update muro_plantilla set nombre = :nombre, tipo = :tipo, material = :material, ubicacion = :ubicacion,
                               altura_m = :altura, partes = cast(:partes as jsonb), elementos = cast(:elementos as jsonb),
                               acabado = cast(:acabado as jsonb), propuso_id = :autor, propuso_rol = :rol,
                               prototipo = :prototipo, planta = :planta, notas = :notas, por_confirmar = :por_confirmar
                         where id = :id
                        """
                    ),
                    self._valores(datos) | {"id": str(plantilla_id), "autor": str(autor_id), "rol": rol},
                )
        except IntegrityError as e:
            raise await self._en_conflicto(e, datos["nombre"]) from e

    async def retirar(self, plantilla_id: UUID) -> None:
        """La versión deja de ser la vigente (sigue existiendo para los trazos que la usan)."""
        await self._sesion.execute(text("update muro_plantilla set vigente = false where id = :i"), {"i": str(plantilla_id)})

    async def validar(self, plantilla_id: UUID, *, usuario_id: UUID) -> None:
        await self._sesion.execute(
            text("update muro_plantilla set validacion = 'validada', validada_por = :u, validada_en = now() where id = :i"),
            {"i": str(plantilla_id), "u": str(usuario_id)},
        )

    async def trazos_de_la_raiz(self, raiz_id: UUID) -> int:
        """Cuántos trazos usan alguna versión de la plantilla."""
        return int(
            (
                await self._sesion.execute(
                    text(
                        "select count(*) from trazo t join muro_plantilla p on p.id = t.muro_plantilla_id where p.raiz_id = :r"
                    ),
                    {"r": str(raiz_id)},
                )
            ).scalar_one()
        )

    async def obras_de_la_plantilla(self, plantilla_id: UUID) -> list[UUID]:
        """Las obras con trazos que usan esta versión de la plantilla (para rehacer lo que sus conceptos toman al editarla en el lugar)."""
        filas = (
            await self._sesion.execute(
                text(
                    "select distinct p.obra_id from trazo t join plano p on p.id = t.plano_id "
                    "where t.muro_plantilla_id = :i and t.hueco_de is null and not t.propuesta"
                ),
                {"i": str(plantilla_id)},
            )
        ).scalars().all()
        return [UUID(str(o)) for o in filas]

    async def eliminar_raiz(self, raiz_id: UUID) -> None:
        await self._sesion.execute(text("delete from muro_plantilla where raiz_id = :r"), {"r": str(raiz_id)})
