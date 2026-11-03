"""AplicadorMatricesCatalogo con repositorios falsos en memoria (D-609, D-610).

Las reglas: solo altas; una matriz que ya existe por clave no se toca; las
unidades y familias que faltan se dan de alta; el costo se congela como versión
1; `dry_run` no escribe nada. La prueba de extremo a extremo usa las 472 filas
reales del catálogo, y se omite si el archivo no está en este entorno.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from obractrl.application.casos_uso.aplicar_matrices_catalogo import (
    AplicadorMatricesCatalogo,
)
from obractrl.domain.cargadores.cabeceras import (
    CATALOGO_MATRICES_OPUS,
    resolver_encabezados,
)
from obractrl.domain.cargadores.matrices_catalogo import (
    FilaMatrizCatalogo,
    validar_matriz_catalogo,
)
from obractrl.domain.shared.valores import Clave


class _Conceptos:
    def __init__(self, existentes: list[dict] | None = None) -> None:
        self.filas = list(existentes or [])
        self.creados: list[dict] = []

    async def listar(self, *, solo_activos: bool = True) -> list[dict]:
        return list(self.filas)

    async def crear(self, datos: dict) -> UUID:
        self.creados.append(datos)
        nuevo = uuid4()
        self.filas.append({"id": nuevo, "clave": datos["clave"]})
        return nuevo


class _Unidades:
    def __init__(self) -> None:
        self.filas: dict[str, dict] = {}

    async def listar(self, *, solo_activos: bool = True) -> list[dict]:
        return list(self.filas.values())

    async def crear_o_existente(self, datos: dict) -> UUID:
        if datos["clave"] not in self.filas:
            self.filas[datos["clave"]] = {"id": uuid4(), "clave": datos["clave"]}
        return self.filas[datos["clave"]]["id"]


class _Familias:
    def __init__(self) -> None:
        self.filas: dict[str, dict] = {}

    async def listar(
        self, *, aplica_a: str | None = None, solo_activos: bool = True
    ) -> list[dict]:
        return [{"id": f["id"], "nombre": n} for n, f in self.filas.items()]

    async def crear_o_existente(self, datos: dict) -> UUID:
        nombre = datos["nombre"]
        if nombre not in self.filas:
            self.filas[nombre] = {"id": uuid4(), "parent_id": datos.get("parent_id")}
        return self.filas[nombre]["id"]


class _Versiones:
    def __init__(self) -> None:
        self.creadas: list[dict] = []

    async def crear(self, datos: dict) -> UUID:
        self.creadas.append(datos)
        return uuid4()

    async def listar(self, concepto_id: UUID) -> list[dict]:
        return [v for v in self.creadas if v["concepto_id"] == concepto_id]


def _fila(
    clave: str,
    *,
    unidad: str = "m2",
    costo: str | None = "10.00",
    familia: str | None = None,
    subfamilia: str | None = None,
) -> FilaMatrizCatalogo:
    return FilaMatrizCatalogo(
        clave=Clave(clave),
        descripcion=f"Concepto {clave}",
        unidad=unidad,
        matriz_desglosable=True,
        tipo="Matriz",
        familia=familia,
        subfamilia=subfamilia,
        costo_base=None if costo is None else Decimal(costo),
        costo_base_me=Decimal("0"),
        costo_unitario=None if costo is None else Decimal(costo),
    )


def _aplicador(conceptos=None):
    c = conceptos or _Conceptos()
    u, f, v = _Unidades(), _Familias(), _Versiones()
    ap = AplicadorMatricesCatalogo(conceptos=c, unidades=u, familias=f, versiones=v)
    return ap, c, u, f, v


@pytest.mark.asyncio
async def test_alta_crea_concepto_tipo_matriz_y_su_version_con_el_costo() -> None:
    ap, c, _, _, v = _aplicador()
    r = await ap.aplicar([_fila("ACA-01010", costo="71.71")], dry_run=False)
    assert r.altas == ("ACA-01010",)
    assert c.creados[0]["tipo"] == "matriz"
    assert len(v.creadas) == 1
    assert v.creadas[0]["version"] == 1
    assert v.creadas[0]["pu"] == Decimal("71.71")


@pytest.mark.asyncio
async def test_una_matriz_que_ya_existe_no_se_toca() -> None:
    existente = [{"id": uuid4(), "clave": "ACA-01010"}]
    ap, c, _, _, v = _aplicador(_Conceptos(existente))
    r = await ap.aplicar([_fila("ACA-01010", costo="99.00")], dry_run=False)
    assert r.ya_existentes == ("ACA-01010",)
    assert r.altas == ()
    assert c.creados == [] and v.creadas == []


@pytest.mark.asyncio
async def test_dry_run_calcula_el_mismo_resultado_sin_escribir() -> None:
    ap, c, u, f, v = _aplicador()
    r = await ap.aplicar([_fila("A-1", unidad="sal", familia="Acabados")], dry_run=True)
    assert r.dry_run is True
    assert r.altas == ("A-1",)
    assert r.unidades_nuevas == ("sal",)
    assert r.familias_nuevas == ("Acabados",)
    assert c.creados == [] and v.creadas == [] and u.filas == {} and f.filas == {}


@pytest.mark.asyncio
async def test_unidades_sal_y_act_se_cargan_tal_cual() -> None:
    ap, _, u, _, _ = _aplicador()
    await ap.aplicar(
        [_fila("S-1", unidad="sal"), _fila("A-1", unidad="act")], dry_run=False
    )
    assert set(u.filas) == {"sal", "act"}


@pytest.mark.asyncio
async def test_sin_costo_no_crea_version_y_se_reporta() -> None:
    ap, c, _, _, v = _aplicador()
    r = await ap.aplicar([_fila("X-1", costo=None)], dry_run=False)
    assert r.sin_costo == ("X-1",)
    assert len(c.creados) == 1 and v.creadas == []


@pytest.mark.asyncio
async def test_familia_y_subfamilia_se_dan_de_alta_con_su_padre() -> None:
    ap, _, _, f, _ = _aplicador()
    await ap.aplicar(
        [_fila("M-1", familia="Albañilería", subfamilia="Muro")], dry_run=False
    )
    assert set(f.filas) == {"Albañilería", "Muro"}
    assert f.filas["Muro"]["parent_id"] == f.filas["Albañilería"]["id"]


@pytest.mark.asyncio
async def test_sin_pedirlo_no_hay_propuestas_de_precio() -> None:
    existente = [{"id": uuid4(), "clave": "ACA-01010"}]
    ap, _, _, _, v = _aplicador(_Conceptos(existente))
    r = await ap.aplicar([_fila("ACA-01010", costo="99.00")], dry_run=False)
    assert r.propuestas_precio == ()
    assert v.creadas == []


@pytest.mark.asyncio
async def test_pedido_el_cambio_de_precio_se_propone_sin_escribirlo() -> None:
    cid = uuid4()
    existente = [{"id": cid, "clave": "ACA-01010"}]
    ap, c, _, _, v = _aplicador(_Conceptos(existente))
    v.creadas.append({"concepto_id": cid, "version": 1, "pu": Decimal("71.71")})
    r = await ap.aplicar(
        [_fila("ACA-01010", costo="80.00")], dry_run=False, proponer_cambios=True
    )
    assert len(r.propuestas_precio) == 1
    p = r.propuestas_precio[0]
    assert (p.clave, p.pu_vigente, p.pu_catalogo) == (
        "ACA-01010",
        Decimal("71.71"),
        Decimal("80.00"),
    )
    assert len(v.creadas) == 1  # solo la versión sembrada: no se escribió nada nuevo
    assert c.creados == []


@pytest.mark.asyncio
async def test_si_el_precio_coincide_no_hay_propuesta() -> None:
    cid = uuid4()
    ap, _, _, _, v = _aplicador(_Conceptos([{"id": cid, "clave": "ACA-01010"}]))
    v.creadas.append({"concepto_id": cid, "version": 1, "pu": Decimal("71.71")})
    r = await ap.aplicar(
        [_fila("ACA-01010", costo="71.71")], dry_run=False, proponer_cambios=True
    )
    assert r.propuestas_precio == ()


_MATRICES = Path(
    "/home/user/cerebro-erp-construccion/1-mundo/opus/CATALOGO_DE_MATRICES.csv"
)


@pytest.mark.asyncio
@pytest.mark.skipif(not _MATRICES.exists(), reason="CSV real de OPUS no disponible aquí")
async def test_extremo_a_extremo_con_las_472_filas_reales_en_base_vacia() -> None:
    with _MATRICES.open(newline="", encoding="utf-8-sig") as f:
        filas = list(csv.reader(f))
    mapa = resolver_encabezados(filas[0], CATALOGO_MATRICES_OPUS)
    validadas = [
        validar_matriz_catalogo(x, mapa, numero=i) for i, x in enumerate(filas[1:], 2)
    ]

    ap, _c, u, fam, _v = _aplicador()
    r = await ap.aplicar(validadas, dry_run=False)
    assert len(r.altas) == 472
    assert r.versiones_creadas == 472
    assert r.sin_costo == ()
    assert set(u.filas) == {"pza", "sal", "m2", "m", "act", "ser", "m3"}
    assert len(fam.filas) == 14  # las 14 familias; ninguna subfamilia hoy
