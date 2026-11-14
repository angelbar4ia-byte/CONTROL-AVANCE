"""El caso de uso de los conceptos del elemento por contexto, sin base de datos (repositorio en memoria)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest

from obractrl.application.casos_uso.conceptos_de_elemento import (
    ComandoAgregarConceptoDeElemento,
    GestionarConceptosDeElemento,
)
from obractrl.application.casos_uso.elementos_parametricos import (
    ElementoParametricoNoEncontrado,
)
from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
)

ACERO = {"acero": True}
AUTOR = uuid.uuid4()


class _Uow:
    commits = 0

    async def __aenter__(self) -> _Uow:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> None:
        _Uow.commits += 1


class _Sincronizador:
    def __init__(self) -> None:
        self.llamadas: list[uuid.UUID | None] = []

    async def de_las_obras_con(self, elemento_id: uuid.UUID | None) -> None:
        self.llamadas.append(elemento_id)


class _Repo:
    def __init__(self) -> None:
        self.elemento = {"id": uuid.uuid4(), "tipo": "castillo", "parametros": {"alto": 2.6}}
        self.catalogo = {uuid.uuid4(): "EST-10010", uuid.uuid4(): "EST-10011"}
        self.filas: list[dict[str, Any]] = []

    async def obtener(self, elemento_id: uuid.UUID) -> dict[str, Any] | None:
        return self.elemento if elemento_id == self.elemento["id"] else None

    async def clave_de_concepto(self, concepto_id: uuid.UUID) -> str | None:
        return self.catalogo.get(concepto_id)

    async def concepto_con_clave(self, clave: str) -> bool:
        return clave.upper() in {v.upper() for v in self.catalogo.values()}

    async def conceptos_por_contexto(self, elemento_id: uuid.UUID) -> list[dict[str, Any]]:
        return list(self.filas)

    async def concepto_por_contexto(self, elemento_id: uuid.UUID, fila_id: uuid.UUID) -> dict[str, Any] | None:
        return next((f for f in self.filas if f["id"] == fila_id), None)

    async def agregar_concepto_por_contexto(self, **kw: Any) -> uuid.UUID:
        fila = {
            "id": uuid.uuid4(), "concepto_id": kw["concepto_id"], "clave": self.catalogo.get(kw["concepto_id"]) or kw["clave_propuesta"],
            "descripcion": kw["descripcion"] or "del catálogo", "descripcion_catalogo": None, "unidad": kw["unidad"], "toma": kw["toma"],
            "ranura": "acero", "estado": kw["estado"], "nivel_min": kw["nivel_min"], "nivel_max": kw["nivel_max"],
            "ubicacion": kw["ubicacion"], "alto_hasta_m": kw["alto_hasta_m"],
        }
        self.filas.append(fila)
        return fila["id"]  # type: ignore[no-any-return]

    async def cambiar_descripcion_de_concepto(self, fila_id: uuid.UUID, descripcion: str | None) -> None:
        next(f for f in self.filas if f["id"] == fila_id)["descripcion"] = descripcion

    async def quitar_concepto_por_contexto(self, fila_id: uuid.UUID) -> None:
        self.filas = [f for f in self.filas if f["id"] != fila_id]


@pytest.fixture
def repo() -> _Repo:
    return _Repo()


@pytest.fixture
def caso(repo: _Repo) -> GestionarConceptosDeElemento:
    return GestionarConceptosDeElemento(elementos=repo, uow=_Uow(), sincronizador=_Sincronizador())


def _cmd(repo: _Repo, **kw: Any) -> ComandoAgregarConceptoDeElemento:
    base: dict[str, Any] = {"elemento_id": repo.elemento["id"], "unidad": "pza", "toma": ACERO, "autor_id": AUTOR}
    return ComandoAgregarConceptoDeElemento(**{**base, **kw})


async def test_un_concepto_del_catalogo_queda_autorizado_y_uno_nuevo_propuesto(caso: GestionarConceptosDeElemento, repo: _Repo) -> None:
    cid = next(iter(repo.catalogo))
    await caso.agregar(_cmd(repo, concepto_id=cid, alto_hasta_m=Decimal("4.00")))
    await caso.agregar(_cmd(repo, clave_propuesta=" ej-410 ", descripcion=" Acero  hasta 8 m ", alto_hasta_m=Decimal("8")))
    assert [(f["clave"], f["estado"]) for f in repo.filas] == [("EST-10010", "autorizado"), ("EJ-410", "propuesto")]
    assert repo.filas[1]["descripcion"] == "Acero hasta 8 m"


async def test_la_lectura_elige_el_escalon_y_avisa_del_alto(caso: GestionarConceptosDeElemento, repo: _Repo) -> None:
    ids = list(repo.catalogo)
    await caso.agregar(_cmd(repo, concepto_id=ids[0], alto_hasta_m=Decimal("2.00")))
    await caso.agregar(_cmd(repo, concepto_id=ids[1], alto_hasta_m=Decimal("2.50")))
    r = await caso.por_contexto(repo.elemento["id"], nivel=1)
    assert r["por_parte"]["acero"] == "EST-10011"  # el último; el alto 2.6 lo rebasa
    assert any("no tiene escalón" in a for a in r["avisos"])
    r = await caso.por_contexto(repo.elemento["id"], nivel=1, alto_m=Decimal("1.9"))
    assert r["por_parte"]["acero"] == "EST-10010"
    assert any("no tiene escalón" in a for a in (await caso.por_contexto(repo.elemento["id"]))["avisos"])


async def test_las_reglas_de_alta(caso: GestionarConceptosDeElemento, repo: _Repo) -> None:
    cid = next(iter(repo.catalogo))
    with pytest.raises(ErrorDeElementoParametrico):  # ni uno ni otro
        await caso.agregar(_cmd(repo))
    with pytest.raises(ErrorDeElementoParametrico):  # una clave que ya es del catálogo no se propone como nueva
        await caso.agregar(_cmd(repo, clave_propuesta="est-10010", descripcion="x"))
    with pytest.raises(ErrorDeElementoParametrico):  # el nuevo necesita descripción
        await caso.agregar(_cmd(repo, clave_propuesta="EJ-1"))
    with pytest.raises(ErrorDeElementoParametrico):
        await caso.agregar(_cmd(repo, concepto_id=cid, alto_hasta_m=Decimal("500")))
    with pytest.raises(ElementoParametricoNoEncontrado):
        await caso.agregar(_cmd(repo, concepto_id=uuid.uuid4()))
    with pytest.raises(ElementoParametricoNoEncontrado):
        await caso.agregar(ComandoAgregarConceptoDeElemento(elemento_id=uuid.uuid4(), unidad="pza", toma=ACERO, autor_id=AUTOR, concepto_id=cid))
    await caso.agregar(_cmd(repo, concepto_id=cid))
    with pytest.raises(ErrorDeElementoParametrico, match="un solo concepto"):
        await caso.agregar(_cmd(repo, clave_propuesta="EJ-2", descripcion="otro acero"))


async def test_solo_la_descripcion_se_edita_y_quitar_corrige(caso: GestionarConceptosDeElemento, repo: _Repo) -> None:
    fila = await caso.agregar(_cmd(repo, clave_propuesta="EJ-1", descripcion="Uno", alto_hasta_m=Decimal("3")))
    await caso.cambiar_descripcion(repo.elemento["id"], fila, "  Dos  ")
    assert repo.filas[0]["descripcion"] == "Dos"
    with pytest.raises(ErrorDeElementoParametrico):
        await caso.cambiar_descripcion(repo.elemento["id"], fila, "   ")
    with pytest.raises(ElementoParametricoNoEncontrado):
        await caso.cambiar_descripcion(repo.elemento["id"], uuid.uuid4(), "x")
    await caso.quitar(repo.elemento["id"], fila)
    assert repo.filas == []


async def test_solo_el_concepto_general_rehace_las_tomas(repo: _Repo) -> None:
    sync = _Sincronizador()
    caso = GestionarConceptosDeElemento(elementos=repo, uow=_Uow(), sincronizador=sync)
    ids = list(repo.catalogo)
    await caso.agregar(_cmd(repo, concepto_id=ids[0], alto_hasta_m=Decimal("4")))
    await caso.agregar(_cmd(repo, concepto_id=ids[1], nivel_min=3, toma={"cimbra": True}))
    assert sync.llamadas == []  # lo contextual espera al Cuantificador
    await caso.agregar(_cmd(repo, concepto_id=ids[1], toma={"concreto": True}))
    assert sync.llamadas == [repo.elemento["id"]]
