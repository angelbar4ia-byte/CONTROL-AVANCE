"""El caso de uso de los insumos del elemento y su comparación, sin base de datos (repositorios en memoria)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from obractrl.application.casos_uso.elementos_parametricos import (
    ElementoParametricoNoEncontrado,
    GestionarElementosParametricos,
)
from obractrl.application.casos_uso.insumos_de_elemento import (
    ComandoAgregarInsumos,
    ComandoCrearInsumoProvisional,
    GestionarInsumosDeElemento,
)
from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
)
from obractrl.domain.cuantificacion.insumos_permitidos import Insumo, InsumoNoPermitido

AUTOR = uuid.uuid4()


class _Uow:
    commits = 0

    async def __aenter__(self) -> _Uow:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> None:
        _Uow.commits += 1


def _i(clave: str, clase: str, fam: str, sub: str | None, unidad: str = "kg") -> tuple[uuid.UUID, Insumo]:
    return uuid.uuid4(), Insumo(clave, clave.lower(), clase, fam, sub, unidad, 10.0)


class _Insumos:
    def __init__(self) -> None:
        self.base = [
            _i("ACE-00001", "material", "Aceros", "Consumible"),
            _i("MEZ-01020", "material", "Mezclas", "Concretos", "m3"),
            _i("PET-00004", "material", "Pétreos", "Piedras", "m3"),
            _i("CUAD-001", "mano_obra", "Cuadrillas", "Albañilería y Estructura", "jornal"),
        ]
        self.agregados: list[tuple[uuid.UUID, str, float]] = []
        self.creados: list[dict[str, Any]] = []

    async def todos(self) -> list[tuple[uuid.UUID, Insumo]]:
        return list(self.base)

    async def por_claves(self, claves: list[str]) -> dict[str, tuple[uuid.UUID, Insumo]]:
        return {i.clave.upper(): (iid, i) for iid, i in self.base if i.clave.upper() in {c.upper() for c in claves}}

    async def por_id(self, insumo_id: uuid.UUID) -> tuple[uuid.UUID, Insumo] | None:
        return next(((iid, i) for iid, i in self.base if iid == insumo_id), None)

    async def agregar(self, *, elemento_id: uuid.UUID, insumo_id: uuid.UUID, clase: str, cantidad: float, autor_id: uuid.UUID) -> bool:
        if any(a[0] == insumo_id for a in self.agregados):
            return False
        self.agregados.append((insumo_id, clase, cantidad))
        return True

    async def unidad_id(self, unidad: str) -> uuid.UUID | None:
        return uuid.uuid4() if unidad.lower() in ("jornal", "kg") else None

    async def asegurar_familia(self, nombre: str, *, padre: str | None = None) -> uuid.UUID:
        return uuid.uuid4()

    async def crear_provisional(self, **kw: Any) -> uuid.UUID:
        self.creados.append(kw)
        nuevo = uuid.uuid4()
        self.base.append((nuevo, Insumo(kw["clave"], kw["descripcion"], "herramienta", None, None, None, None, True)))
        return nuevo


class _Elementos:
    def __init__(self) -> None:
        self.elemento = {"id": uuid.uuid4(), "tipo": "castillo", "parametros": {"alto": 2.5}, "materiales": {"concreto": "MEZ-01020"}}
        self.filas: list[dict[str, Any]] = []

    async def obtener(self, elemento_id: uuid.UUID) -> dict[str, Any] | None:
        return self.elemento if elemento_id == self.elemento["id"] else None

    async def conceptos_por_contexto(self, elemento_id: uuid.UUID) -> list[dict[str, Any]]:
        return list(self.filas)


class _Conceptos:
    def __init__(self, filas: list[dict[str, Any]]) -> None:
        self.filas = filas

    async def composicion_recursiva(self, concepto_id: uuid.UUID) -> list[dict[str, Any]]:
        return self.filas


def _caso(filas: list[dict[str, Any]] | None = None) -> tuple[GestionarInsumosDeElemento, _Elementos, _Insumos]:
    e, i = _Elementos(), _Insumos()
    return GestionarInsumosDeElemento(elementos=e, insumos=i, conceptos=_Conceptos(filas or []), uow=_Uow()), e, i  # type: ignore[arg-type]


async def test_un_insumo_de_otra_familia_no_se_agrega_y_nada_se_guarda() -> None:
    caso, e, i = _caso()
    bueno, malo = i.base[0][0], i.base[2][0]
    with pytest.raises(InsumoNoPermitido, match=r"PET-00004 \(Pétreos · Piedras\)"):
        await caso.agregar(ComandoAgregarInsumos(e.elemento["id"], [(bueno, 1.0), (malo, 1.0)], AUTOR))
    assert i.agregados == []
    assert await caso.agregar(ComandoAgregarInsumos(e.elemento["id"], [(bueno, 1.0), (i.base[3][0], 0.5)], AUTOR)) == 2
    assert [a[1] for a in i.agregados] == ["material", "mano_obra"]
    assert await caso.agregar(ComandoAgregarInsumos(e.elemento["id"], [(bueno, 1.0)], AUTOR)) == 0  # no se repite


async def test_sin_insumos_o_con_cantidad_negativa_o_elemento_ajeno() -> None:
    caso, e, i = _caso()
    with pytest.raises(ErrorDeElementoParametrico, match="al menos un insumo"):
        await caso.agregar(ComandoAgregarInsumos(e.elemento["id"], [], AUTOR))
    with pytest.raises(ErrorDeElementoParametrico, match="negativa"):
        await caso.agregar(ComandoAgregarInsumos(e.elemento["id"], [(i.base[0][0], -1)], AUTOR))
    with pytest.raises(ElementoParametricoNoEncontrado):
        await caso.agregar(ComandoAgregarInsumos(uuid.uuid4(), [(i.base[0][0], 1)], AUTOR))


async def test_el_insumo_provisional_se_crea_sin_precio_y_sin_inventar_uno() -> None:
    caso, e, i = _caso()
    nuevo = await caso.crear_provisional(
        ComandoCrearInsumoProvisional(e.elemento["id"], "herramienta", "ins-a001", "ANDAMIO", "jornal", AUTOR, subfamilia="Andamios")
    )
    (creado,) = i.creados
    assert creado["clave"] == "INS-A001" and creado["tipo"] == "herramienta"
    assert "costo_base" not in creado and "precio" not in creado  # el precio nunca viaja: el repositorio guarda 0 y marca provisional
    assert (await i.por_id(nuevo)) is not None
    with pytest.raises(ErrorDeElementoParametrico, match="Ya existe"):
        await caso.crear_provisional(ComandoCrearInsumoProvisional(e.elemento["id"], "herramienta", "INS-A001", "ANDAMIO", "jornal", AUTOR))
    with pytest.raises(ErrorDeElementoParametrico, match="no existe en el catálogo de unidades"):
        await caso.crear_provisional(ComandoCrearInsumoProvisional(e.elemento["id"], "herramienta", "INS-A002", "x", "galón", AUTOR))


async def test_la_comparacion_usa_las_cantidades_del_elemento_y_la_composicion_del_catalogo() -> None:
    filas_del_catalogo = [
        {"concepto_clave": "EST-X", "tipo_hijo": "insumo", "categoria": "material", "cantidad": 0.0225, "insumo_clave": "MEZ-01020"},
        {"concepto_clave": "EST-X", "tipo_hijo": "insumo", "categoria": "material", "cantidad": 0.5, "insumo_clave": "ACE-00001"},
    ]
    caso, e, _ = _caso(filas_del_catalogo)
    fila = uuid.uuid4()
    e.filas = [
        {"id": fila, "concepto_id": uuid.uuid4(), "clave": "EST-X", "descripcion": "x", "unidad": "ml", "toma": {"concreto": True}, "estado": "autorizado"}
    ]
    r = await caso.comparacion(e.elemento["id"])
    (c,) = r["conceptos"]
    marcas = {f["clave"]: f["marca"] for f in c["filas"]}
    assert marcas == {"MEZ-01020": "=", "ACE-00001": "solo_catalogo"}  # 0.15 × 0.15 por ml = 0.0225 m³
    assert c["resumen"]["="] == 1 and c["avisos"] == []


async def test_los_materiales_exigen_la_base_de_insumos() -> None:
    class _ElementosVacios:
        async def clave_en_uso(self, *a: Any, **k: Any) -> bool:
            return False

    caso = GestionarElementosParametricos(elementos=_ElementosVacios(), uow=_Uow())  # type: ignore[arg-type]
    from obractrl.application.casos_uso.elementos_parametricos import (
        ComandoCrearElementoParametrico,
    )

    with pytest.raises(ErrorDeElementoParametrico, match="falta la base de insumos"):
        await caso.crear(ComandoCrearElementoParametrico("K-1", "Castillo", "castillo", {}, AUTOR, materiales={"concreto": "MEZ-01020"}))
