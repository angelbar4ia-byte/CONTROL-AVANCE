"""Repositorio del detalle del catálogo de mano de obra de OPUS (D-616).

Una fila por puesto o cuadrilla con las columnas del cálculo del salario real
que `CATALOGO_DE_MANO_DE_OBRA.csv` trae y que no caben en el insumo ni en la
cuadrilla. Spec §12.11 (adaptador de persistencia) · §12.4 (RLS: lectura de la
organización, escritura solo `app.es_config()`).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["CAMPOS_NUMERICOS", "RepositorioManoDeObraOpusSQL"]

CAMPOS_NUMERICOS: tuple[str, ...] = (
    "costo_unitario",
    "salario_tabulado",
    "salario_nominal_mn",
    "fsr",
    "salario_nominal_me",
    "salario_real",
    "factor_salario_base",
    "sbc",
    "excedente_tres_salarios",
    "aplicacion_imss",
    "cuota_fija",
    "prestaciones_en_especie",
    "prestaciones_en_dinero",
    "invalidez_y_vida",
    "cesantia_en_edad_avanzada",
    "riesgos_de_trabajo",
    "guarderias",
    "sar",
    "suma_prestaciones_imss",
    "factor_cuota_patronal_imss",
    "infonavit",
    "impuesto_sobre_nomina",
    "suma_prestaciones",
    "obligacion_obrero_patronal",
    "factor_de_salario_gravable",
    "salario_gravable",
)

_COLUMNAS = "id, clave, insumo_id, cuadrilla_id, utilizar_hoja_fsr, categoria_fsr, fecha, " + ", ".join(
    CAMPOS_NUMERICOS
)


class RepositorioManoDeObraOpusSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def listar(self) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from mano_de_obra_opus order by clave")
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def upsert(self, clave: str, datos: dict[str, Any]) -> tuple[UUID, bool]:
        """Alta o actualización por clave. ``datos`` trae ``insumo_id`` o
        ``cuadrilla_id`` (uno solo), ``utilizar_hoja_fsr``, ``categoria_fsr``,
        ``fecha`` y los campos numéricos. Devuelve ``(id, es_alta)``."""
        columnas = [
            "insumo_id", "cuadrilla_id", "utilizar_hoja_fsr", "categoria_fsr", "fecha",
            *CAMPOS_NUMERICOS,
        ]
        parametros: dict[str, Any] = {"clave": clave}
        for c in columnas:
            valor = datos.get(c)
            parametros[c] = str(valor) if c.endswith("_id") and valor is not None else valor
        tipos = {
            "insumo_id": "uuid", "cuadrilla_id": "uuid", "utilizar_hoja_fsr": "boolean",
            "fecha": "date",
        }
        valores = ", ".join(
            f"cast(:{c} as {tipos.get(c, 'numeric' if c in CAMPOS_NUMERICOS else 'text')})"
            for c in columnas
        )
        asignaciones = ", ".join(f"{c} = excluded.{c}" for c in columnas)
        fila = (
            await self._sesion.execute(
                text(
                    f"""
                    insert into mano_de_obra_opus
                        (org_id, clave, {", ".join(columnas)})
                    values (cast(current_setting('app.org_id') as uuid), :clave, {valores})
                    on conflict (org_id, clave) do update set {asignaciones}
                    returning id, (xmax = 0) as es_alta
                    """
                ),
                parametros,
            )
        ).one()
        return fila.id, bool(fila.es_alta)
