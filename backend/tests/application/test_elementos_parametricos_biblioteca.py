"""El caso de uso de elementos paramétricos con la clasificación de la biblioteca, sin base de datos (repositorio en memoria)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from obractrl.application.casos_uso.elementos_parametricos import (
    ComandoCrearElementoParametrico,
    ElementoParametricoNoEncontrado,
    GestionarElementosParametricos,
)
from obractrl.domain.cuantificacion.clasificacion_de_elementos import ElementoDuplicado
from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
)


class _Uow:
    async def __aenter__(self) -> _Uow:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> None:
        return None


class _Repo:
    def __init__(self) -> None:
        self.filas: dict[uuid.UUID, dict[str, Any]] = {}

    async def clave_en_uso(self, clave: str, *, salvo: uuid.UUID | None = None) -> bool:
        return any(f["clave"] == clave and f["id"] != salvo for f in self.filas.values())

    async def buscar_duplicado(self, firma: str, *, salvo: uuid.UUID | None = None) -> dict[str, Any] | None:
        return next((f for f in self.filas.values() if f["firma"] == firma and f["id"] != salvo), None)

    async def crear(self, **kw: Any) -> uuid.UUID:
        nuevo = uuid.uuid4()
        self.filas[nuevo] = {"id": nuevo, "version": 1, **kw}
        return nuevo

    async def obtener(self, elemento_id: uuid.UUID) -> dict[str, Any] | None:
        return self.filas.get(elemento_id)

    async def actualizar(self, elemento_id: uuid.UUID, **kw: Any) -> None:
        self.filas[elemento_id].update(kw)

    async def obras_congeladas_con(self, elemento_id: uuid.UUID) -> list[uuid.UUID]:
        return []


@pytest.fixture
def repo() -> _Repo:
    return _Repo()


@pytest.fixture
def casos(repo: _Repo) -> GestionarElementosParametricos:
    return GestionarElementosParametricos(elementos=repo, uow=_Uow())  # type: ignore[arg-type]


def _cmd(clave: str, **extra: Any) -> ComandoCrearElementoParametrico:
    base = {"nombre": clave, "tipo": "lineal", "parametros": {"ancho": 0.15, "alto": 0.2}, "autor_id": uuid.uuid4()}
    return ComandoCrearElementoParametrico(clave=clave, **{**base, **extra})


async def test_crear_guarda_la_clasificacion_y_la_firma(casos: GestionarElementosParametricos, repo: _Repo) -> None:
    nuevo = await casos.crear(_cmd("ce-1"))
    fila = repo.filas[nuevo]
    assert (fila["categoria"], fila["subcategoria"]) == ("cadenas", "cerramiento")
    assert len(fila["firma"]) == 64


async def test_un_duplicado_se_rechaza_con_la_clave_del_existente_y_la_subcategoria_lo_distingue(
    casos: GestionarElementosParametricos, repo: _Repo
) -> None:
    await casos.crear(_cmd("CE-1"))
    with pytest.raises(ElementoDuplicado) as e:
        await casos.crear(_cmd("CE-2"))
    assert e.value.clave_igual == "CE-1"
    await casos.crear(_cmd("CD-1", subcategoria="desplante"))  # misma geometría, otro uso: no es duplicado
    assert len(repo.filas) == 2


async def test_la_clasificacion_invalida_se_rechaza_antes_de_guardar(casos: GestionarElementosParametricos, repo: _Repo) -> None:
    with pytest.raises(ErrorDeElementoParametrico):
        await casos.crear(_cmd("X-1", categoria="castillos"))
    assert repo.filas == {}


async def test_validar_posicion_usa_la_subcategoria_del_elemento(casos: GestionarElementosParametricos) -> None:
    desplante = await casos.crear(_cmd("CD-1", subcategoria="desplante"))
    cerramiento = await casos.crear(_cmd("CE-1"))
    await casos.validar_posicion(desplante, "desplante")
    await casos.validar_posicion(cerramiento, "remate")
    with pytest.raises(ErrorDeElementoParametrico, match="solo se coloca en desplante"):
        await casos.validar_posicion(desplante, "cerramiento")
    with pytest.raises(ErrorDeElementoParametrico, match="solo se coloca en cerramiento o remate"):
        await casos.validar_posicion(cerramiento, "desplante")
    with pytest.raises(ElementoParametricoNoEncontrado):
        await casos.validar_posicion(uuid.uuid4(), "desplante")
