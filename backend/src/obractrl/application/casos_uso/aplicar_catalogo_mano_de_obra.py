"""Catálogo de mano de obra y semilla de cuadrillas de OPUS (D-616).

Dos aplicadores que no ignoran ninguna columna de su archivo:

- `AplicadorCatalogoManoDeObra` — `CATALOGO_DE_MANO_DE_OBRA.csv`: los 58
  puestos (insumos de mano de obra) y las 39 cuadrillas, que se guardan en la
  tabla de cuadrillas. Las 28 columnas del cálculo del salario real van a
  `mano_de_obra_opus`.
- `AplicadorSemillaCuadrillas` — `SEMILLA-cuadrilla-rendimiento.csv`: liga
  cada destajo a su cuadrilla y guarda su rendimiento teórico, su origen y las
  tres columnas de referencia.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.aplicar_carga import (
    Aplicacion,
    _operacion,
    _recorte,
    _resolver_o_dar_de_alta,
)
from obractrl.application.puertos.cargadores import RepositorioCargas
from obractrl.application.puertos.repositorios import (
    RepositorioCuadrillas,
    RepositorioFamilias,
    RepositorioInsumos,
    RepositorioManoDeObraOpus,
    RepositorioUnidades,
)
from obractrl.domain.cargadores.homologacion import Homologador
from obractrl.domain.cargadores.mano_de_obra_catalogo import (
    CAMPOS_DE_CALCULO,
    FilaManoDeObraOpus,
)
from obractrl.domain.cargadores.reporte import ErrorDeFila
from obractrl.domain.cargadores.semilla_cuadrillas import FilaSemilla
from obractrl.domain.cargadores.versionado import diferenciar
from obractrl.domain.proyectos.reglas import ErrorDeProyecto
from obractrl.domain.shared.diccionario import ModoCarga, TipoInsumo

__all__ = ["AplicadorCatalogoManoDeObra", "AplicadorSemillaCuadrillas"]

_CAMPOS_INSUMO = (
    "descripcion",
    "unidad_id",
    "familia_id",
    "costo_base",
    "costo_unitario",
    "fecha_costo",
    "tipo_opus",
    "desglosable",
    "cuadrilla_id",
    "rendimiento_teorico",
    "origen_rendimiento",
    "ref_descripcion",
    "ref_unidad",
    "ref_costo_unitario",
    "estatus",
    "iva_aplica",
    "factor_conversion",
    "costo_base_actualizado",
    "costo_promedio_almacen",
    "costo_ultimo",
    "origen",
    "comentarios",
    "costo_base_me",
    "revisar",
)
"""Lo que el snapshot guarda de un insumo tocado: coincide con lo que la
reversa sabe restaurar (`cargas_sql`)."""

_CAMPOS_CUADRILLA = (
    "nombre",
    "unidad_id",
    "estatus",
    "familia_id",
    "desglosable",
    "fecha_costo",
    "tipo_opus",
    "costo_jornada",
)


def _normal(valor: Any) -> str:
    """Comparable: `Decimal('560.000000') == Decimal('560')` y `None` aparte."""
    if valor is None:
        return "∅"
    if isinstance(valor, Decimal):
        return str(valor.normalize())
    return str(valor)


def _huella(detalle: dict[str, Any]) -> str:
    return "|".join(f"{campo}={_normal(detalle.get(campo))}" for campo in sorted(detalle))


@dataclass(slots=True)
class _Estado:
    unidades: Homologador
    id_unidad: dict[str, UUID]
    nuevas_unidades: dict[str, UUID | None]
    familias: Homologador
    id_familia: dict[str, UUID]
    nuevas_familias: dict[str, UUID | None]


class AplicadorCatalogoManoDeObra:
    """Puestos → insumos de mano de obra. Cuadrillas → tabla de cuadrillas."""

    def __init__(
        self,
        *,
        insumos: RepositorioInsumos,
        cuadrillas: RepositorioCuadrillas,
        unidades: RepositorioUnidades,
        familias: RepositorioFamilias,
        detalle: RepositorioManoDeObraOpus,
        cargas: RepositorioCargas,
    ) -> None:
        self._insumos = insumos
        self._cuadrillas = cuadrillas
        self._unidades = unidades
        self._familias = familias
        self._detalle = detalle
        self._cargas = cargas

    async def aplicar(
        self,
        lectura: Any,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        if modo is ModoCarga.REEMPLAZAR:
            raise ErrorDeProyecto(
                "El catálogo de mano de obra no soporta el modo Reemplazar: "
                "puestos y cuadrillas se actualizan, no se sustituyen. Usa Actualizar."
            )

        insumos_filas = await self._insumos.listar(solo_activos=False)
        insumo_por_clave = {str(f["clave"]): f for f in insumos_filas}
        cuadrillas_filas = await self._cuadrillas.listar(solo_activos=False)
        cuadrilla_por_clave = {str(f["clave"]): f for f in cuadrillas_filas}
        detalle_por_clave = {str(f["clave"]): f for f in await self._detalle.listar()}

        unidades_filas = await self._unidades.listar(solo_activos=False)
        familias_filas = await self._familias.listar(aplica_a="material", solo_activos=False)
        estado = _Estado(
            unidades=Homologador.desde(
                unidades_filas, mapeos=await self._cargas.mapeos("unidad")
            ),
            id_unidad={str(f["clave"]): f["id"] for f in unidades_filas},
            nuevas_unidades={},
            familias=Homologador.desde(
                familias_filas, mapeos=await self._cargas.mapeos("familia")
            ),
            id_familia={str(f["clave"]): f["id"] for f in familias_filas},
            nuevas_familias={},
        )

        errores: list[ErrorDeFila] = []
        entrantes: dict[str, dict[str, Any]] = {}
        filas: dict[str, FilaManoDeObraOpus] = {}
        sub_ids: dict[str, UUID | None] = {}

        for registro in lectura.registros:
            fila: FilaManoDeObraOpus = registro
            existente = (
                cuadrilla_por_clave.get(fila.llave)
                if fila.es_cuadrilla
                else insumo_por_clave.get(fila.llave)
            ) or {}
            unidad_id = existente.get("unidad_id")
            if fila.unidad:
                unidad_id = await _resolver_o_dar_de_alta(
                    fila.unidad,
                    homologador=estado.unidades,
                    id_por_clave=estado.id_unidad,
                    creadas=estado.nuevas_unidades,
                    crear=self._unidades.crear_o_existente,
                    dry_run=dry_run,
                )
            familia_id = existente.get("familia_id")
            if fila.familia:
                familia_id = await _resolver_o_dar_de_alta(
                    fila.familia,
                    homologador=estado.familias,
                    id_por_clave=estado.id_familia,
                    creadas=estado.nuevas_familias,
                    crear=self._familias.crear_o_existente,
                    dry_run=dry_run,
                )
                if fila.subfamilia:
                    sub = estado.familias.resolver(fila.subfamilia)
                    if sub is not None:
                        familia_id = estado.id_familia.get(sub, familia_id)
                    else:
                        if fila.subfamilia not in sub_ids:
                            sub_ids[fila.subfamilia] = (
                                None
                                if dry_run
                                else await self._familias.crear_o_existente(
                                    {
                                        "clave": fila.subfamilia,
                                        "nombre": fila.subfamilia,
                                        "aplica_a": "material",
                                        "parent_id": familia_id,
                                    }
                                )
                            )
                        familia_id = sub_ids[fila.subfamilia] or familia_id

            filas[fila.llave] = fila
            entrantes[fila.llave] = {
                "descripcion": fila.descripcion,
                "unidad_id": unidad_id,
                "familia_id": familia_id,
                "fecha": fila.fecha,
                "tipo_opus": fila.tipo_opus,
                "es_cuadrilla": fila.es_cuadrilla,
                "detalle": _huella(
                    {
                        "utilizar_hoja_fsr": fila.utilizar_hoja_fsr,
                        "categoria_fsr": fila.categoria_fsr,
                        **fila.calculo,
                    }
                ),
            }

        vigentes: dict[str, dict[str, Any]] = {}
        for clave in entrantes:
            es_cuadrilla = entrantes[clave]["es_cuadrilla"]
            actual = (cuadrilla_por_clave if es_cuadrilla else insumo_por_clave).get(clave)
            if actual is None:
                continue
            det = detalle_por_clave.get(clave) or {}
            vigentes[clave] = {
                "descripcion": actual.get("nombre") if es_cuadrilla else actual.get("descripcion"),
                "unidad_id": actual.get("unidad_id"),
                "familia_id": actual.get("familia_id"),
                "fecha": actual.get("fecha_costo"),
                "tipo_opus": actual.get("tipo_opus"),
                "es_cuadrilla": es_cuadrilla,
                "detalle": _huella(
                    {
                        "utilizar_hoja_fsr": det.get("utilizar_hoja_fsr", False),
                        "categoria_fsr": det.get("categoria_fsr"),
                        **{c: det.get(c) for c in CAMPOS_DE_CALCULO},
                    }
                )
                if det
                else "",
            }

        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=ModoCarga.ACTUALIZAR)
        operaciones: list[dict[str, Any]] = []
        creados = {"puestos": 0, "cuadrillas": 0}

        if not dry_run:
            for cambio in (*diff.altas, *diff.cambios):
                fila = filas[cambio.clave]
                destino = cambio.despues
                if fila.es_cuadrilla:
                    dueno = await self._guardar_cuadrilla(
                        fila, destino, cuadrilla_por_clave.get(fila.llave), operaciones
                    )
                    creados["cuadrillas"] += 1
                else:
                    dueno = await self._guardar_puesto(
                        fila, destino, insumo_por_clave.get(fila.llave), operaciones
                    )
                    creados["puestos"] += 1
                datos = {
                    "insumo_id": None if fila.es_cuadrilla else dueno,
                    "cuadrilla_id": dueno if fila.es_cuadrilla else None,
                    "utilizar_hoja_fsr": fila.utilizar_hoja_fsr,
                    "categoria_fsr": fila.categoria_fsr,
                    "fecha": fila.fecha,
                    **fila.calculo,
                }
                antes = detalle_por_clave.get(fila.llave)
                detalle_id, es_alta = await self._detalle.upsert(fila.llave, datos)
                operaciones.append(
                    _operacion(
                        "mano_de_obra_opus",
                        detalle_id,
                        "insert" if es_alta else "update",
                        antes=None if es_alta or antes is None else dict(antes),
                        despues={"clave": fila.llave},
                    )
                )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            errores=tuple(errores),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios),
            omitidos=diff.omitidos + lectura.omitidos,
            detalle={
                "puestos": creados["puestos"],
                "cuadrillas": creados["cuadrillas"],
                "unidades_creadas": len(estado.nuevas_unidades),
                "familias_creadas": len(estado.nuevas_familias) + len(sub_ids),
            },
        )

    async def _guardar_puesto(
        self,
        fila: FilaManoDeObraOpus,
        destino: dict[str, Any],
        actual: dict[str, Any] | None,
        operaciones: list[dict[str, Any]],
    ) -> UUID:
        costo = fila.calculo.get("costo_unitario")
        campos = {
            "descripcion": destino["descripcion"],
            "unidad_id": destino["unidad_id"],
            "familia_id": destino["familia_id"],
            "costo_base": costo if costo is not None else Decimal(0),
            "costo_unitario": costo,
            "fecha_costo": fila.fecha,
            "tipo_opus": fila.tipo_opus,
            "desglosable": False,
        }
        if actual is None:
            nuevo_id = await self._insumos.crear(
                {
                    "tipo": str(TipoInsumo.MANO_OBRA),
                    "clave": fila.llave,
                    "descripcion": campos["descripcion"],
                    "unidad_id": campos["unidad_id"],
                    "familia_id": campos["familia_id"],
                    "costo_base": campos["costo_base"],
                }
            )
            await self._insumos.actualizar(
                nuevo_id,
                {
                    k: v
                    for k, v in campos.items()
                    if k in ("costo_unitario", "fecha_costo", "tipo_opus", "desglosable")
                },
            )
            operaciones.append(_operacion("insumo", nuevo_id, "insert", despues=dict(campos)))
            return nuevo_id
        await self._insumos.actualizar(actual["id"], campos)
        operaciones.append(
            _operacion(
                "insumo",
                actual["id"],
                "update",
                antes=_recorte(actual, _CAMPOS_INSUMO),
                despues=dict(campos),
            )
        )
        return actual["id"]

    async def _guardar_cuadrilla(
        self,
        fila: FilaManoDeObraOpus,
        destino: dict[str, Any],
        actual: dict[str, Any] | None,
        operaciones: list[dict[str, Any]],
    ) -> UUID:
        campos = {
            "nombre": destino["descripcion"],
            "unidad_id": destino["unidad_id"],
            "familia_id": destino["familia_id"],
            "desglosable": True,
            "fecha_costo": fila.fecha,
            "tipo_opus": fila.tipo_opus,
            "costo_jornada": fila.calculo.get("costo_unitario"),
        }
        if actual is None:
            nuevo_id = await self._cuadrillas.crear(
                {"clave": fila.llave, "nombre": campos["nombre"], "unidad_id": campos["unidad_id"]}
            )
            await self._cuadrillas.actualizar(nuevo_id, campos)
            operaciones.append(_operacion("cuadrilla", nuevo_id, "insert", despues=dict(campos)))
            return nuevo_id
        await self._cuadrillas.actualizar(actual["id"], campos)
        operaciones.append(
            _operacion(
                "cuadrilla",
                actual["id"],
                "update",
                antes=_recorte(actual, _CAMPOS_CUADRILLA),
                despues=dict(campos),
            )
        )
        return actual["id"]


class AplicadorSemillaCuadrillas:
    """Liga cada destajo a su cuadrilla y guarda su rendimiento teórico."""

    def __init__(
        self,
        *,
        insumos: RepositorioInsumos,
        cuadrillas: RepositorioCuadrillas,
        cargas: RepositorioCargas,
    ) -> None:
        self._insumos = insumos
        self._cuadrillas = cuadrillas
        self._cargas = cargas

    async def aplicar(
        self,
        lectura: Any,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        if modo is ModoCarga.REEMPLAZAR:
            raise ErrorDeProyecto(
                "La semilla de cuadrillas no soporta el modo Reemplazar: solo liga "
                "destajos que ya existen. Usa Actualizar."
            )
        insumo_por_clave = {
            str(f["clave"]): f for f in await self._insumos.listar(solo_activos=False)
        }
        cuadrilla_por_clave = {
            str(f["clave"]): f for f in await self._cuadrillas.listar(solo_activos=False)
        }

        errores: list[ErrorDeFila] = []
        entrantes: dict[str, dict[str, Any]] = {}
        planes: dict[str, tuple[FilaSemilla, dict[str, Any]]] = {}

        for registro in lectura.registros:
            fila: FilaSemilla = registro
            destajo = insumo_por_clave.get(fila.llave)
            if destajo is None:
                errores.append(
                    ErrorDeFila(
                        fila=fila.fila,
                        columna="clave",
                        valor=fila.llave,
                        motivo=(
                            f"clave: el destajo {fila.llave!r} no existe. Carga primero el "
                            f"catálogo de trabajos (la semilla solo liga destajos existentes)."
                        ),
                    )
                )
                continue
            cuadrilla = cuadrilla_por_clave.get(str(fila.cuadrilla))
            if cuadrilla is None:
                errores.append(
                    ErrorDeFila(
                        fila=fila.fila,
                        columna="cuadrilla",
                        valor=str(fila.cuadrilla),
                        motivo=(
                            f"cuadrilla: {str(fila.cuadrilla)!r} no existe. Carga primero el "
                            f"catálogo de mano de obra (las 39 cuadrillas)."
                        ),
                    )
                )
                continue
            nuevos = {
                "cuadrilla_id": cuadrilla["id"],
                "rendimiento_teorico": fila.rendimiento_teorico,
                "origen_rendimiento": fila.origen,
                "ref_descripcion": fila.descripcion_ref,
                "ref_unidad": fila.unidad_ref,
                "ref_costo_unitario": fila.costo_ref,
            }
            entrantes[fila.llave] = {k: _normal(v) for k, v in nuevos.items()}
            planes[fila.llave] = (fila, nuevos)

        vigentes = {
            clave: {
                campo: _normal(insumo_por_clave[clave].get(campo))
                for campo in (
                    "cuadrilla_id",
                    "rendimiento_teorico",
                    "origen_rendimiento",
                    "ref_descripcion",
                    "ref_unidad",
                    "ref_costo_unitario",
                )
            }
            for clave in entrantes
        }
        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=ModoCarga.ACTUALIZAR)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for cambio in (*diff.altas, *diff.cambios):
                _, nuevos = planes[cambio.clave]
                destajo = insumo_por_clave[cambio.clave]
                await self._insumos.actualizar(destajo["id"], nuevos)
                operaciones.append(
                    _operacion(
                        "insumo",
                        destajo["id"],
                        "update",
                        antes=_recorte(destajo, _CAMPOS_INSUMO),
                        despues=dict(nuevos),
                    )
                )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            errores=tuple(errores),
            insertados=0,
            actualizados=len(diff.altas) + len(diff.cambios),
            omitidos=diff.omitidos + lectura.omitidos,
            detalle={"destajos_ligados": len(planes)},
        )
