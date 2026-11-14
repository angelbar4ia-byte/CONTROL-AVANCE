"""La migración 0129 (materiales del elemento, firma, insumos del elemento y familia Cimbra) en una base APARTE: se aplican las
migraciones hasta la 0128, se guardan datos previos, se sube la 0129, se baja y se vuelve a subir. Prueba que lo que ya existía
no cambia (la firma de un elemento sin materiales es la misma), que la migración se puede correr dos veces y que el down no
deja un objeto colgado ni choca con la unicidad de la firma."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from tests.integracion.conftest import DATABASE_URL_ADMIN

RAIZ = Path(__file__).resolve().parents[3] / "database"
MIGRACIONES = sorted((RAIZ / "migrations").glob("*.sql"))
LA_0129 = next(m for m in MIGRACIONES if m.name.startswith("20260814000129"))
DOWN_0129 = RAIZ / "migrations" / "down" / LA_0129.name

pytestmark = pytest.mark.skipif(shutil.which("psql") is None, reason="Requiere el cliente psql para aplicar las migraciones.")


def _dsn(base: str) -> str:
    u = make_url(DATABASE_URL_ADMIN or "").set(drivername="postgresql", database=base)
    return u.render_as_string(hide_password=False)


def _psql(dsn: str, *args: str) -> str:
    r = subprocess.run(["psql", dsn, "-v", "ON_ERROR_STOP=1", "-qtA", *args], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _consulta(dsn: str, sql: str) -> list[list[str]]:
    return [f.split("|") for f in _psql(dsn, "-c", sql).splitlines() if f]


@pytest.fixture
def base_apartada() -> str:
    nombre = f"obractrl_mig_{uuid.uuid4().hex[:10]}"
    mantenimiento = _dsn("postgres")
    _psql(mantenimiento, "-c", f'create database "{nombre}"')
    try:
        yield _dsn(nombre)
    finally:
        _psql(mantenimiento, "-c", f'drop database if exists "{nombre}" with (force)')


def test_ida_y_vuelta_con_datos_previos(base_apartada: str) -> None:
    dsn = base_apartada
    _psql(dsn, "-c", "create schema if not exists app")
    for m in (m for m in MIGRACIONES if m.name < LA_0129.name):
        _psql(dsn, "-q", "-f", str(m))
    org = str(uuid.uuid4())
    _psql(
        dsn,
        "-c",
        f"""
        insert into organizacion (id, nombre, slug) values ('{org}', 'Mig', 'mig-{org[:8]}');
        insert into unidad (org_id, clave, nombre) values ('{org}', 'm2', 'm2');
        insert into familia (id, org_id, clave, nombre) values ('00000000-0000-0000-0000-0000000000a1', '{org}', 'MADERAS', 'Maderas');
        insert into familia (id, org_id, parent_id, clave, nombre)
          values ('00000000-0000-0000-0000-0000000000a2', '{org}', '00000000-0000-0000-0000-0000000000a1', 'CIMBRA', 'Cimbra');
        insert into insumo (org_id, tipo, clave, descripcion, unidad_id, familia_id, costo_base)
          select '{org}', 'material', 'MAD-00001', 'CIMBRA 3 MTS', u.id, '00000000-0000-0000-0000-0000000000a2', 95 from unidad u where u.org_id = '{org}';
        insert into insumo (org_id, tipo, clave, descripcion, unidad_id, familia_id, costo_base)
          select '{org}', 'material', 'MAD-00007', 'DURMIENTE', u.id, '00000000-0000-0000-0000-0000000000a1', 750 from unidad u where u.org_id = '{org}';
        insert into elemento_parametrico (org_id, clave, nombre, tipo, parametros, categoria, subcategoria)
          values ('{org}', 'K-1', 'Castillo', 'castillo', '{{"largo": 0.15, "ancho": 0.15, "alto": 2.6}}', 'castillos', 'muro'),
                 ('{org}', 'CE-1', 'Cadena', 'lineal', '{{"ancho": 0.15, "alto": 0.2, "rec": 0.025}}', 'cadenas', 'cerramiento');
        update elemento_parametrico set firma = app.firma_elemento(categoria, subcategoria, tipo, parametros);
        """,
    )
    antes = _consulta(dsn, "select clave, firma from elemento_parametrico order by clave")
    assert len(antes) == 2 and all(f[1] for f in antes)

    # --- Sube la 0129 ----------------------------------------------------------------------------------------------
    _psql(dsn, "-q", "-f", str(LA_0129))
    assert _consulta(dsn, "select clave, firma, materiales from elemento_parametrico order by clave") == [[a, b, "{}"] for a, b in antes]
    # Sin materiales, la firma que da la base es la de siempre (cuatro argumentos como cinco).
    assert _consulta(dsn, "select count(*) from elemento_parametrico where firma = app.firma_elemento(categoria, subcategoria, tipo, parametros)") == [["2"]]
    # La familia Cimbra deja de colgar de Maderas y recibe los insumos de cimbra; lo demás de Maderas se queda.
    assert _consulta(dsn, "select clave, parent_id is null from familia where upper(clave) = 'CIMBRA'") == [["CIMBRA", "t"]]
    assert _consulta(dsn, "select i.clave, f.clave from insumo i join familia f on f.id = i.familia_id order by i.clave") == [
        ["MAD-00001", "CIMBRA"], ["MAD-00007", "MADERAS"]
    ]
    assert _consulta(dsn, "select to_regclass('elemento_insumo') is not null, (select count(*) from information_schema.columns where table_name = 'insumo' and column_name = 'provisional')") == [["t", "1"]]

    # --- Se puede volver a correr (idempotente) -----------------------------------------------------------------------
    _psql(dsn, "-q", "-f", str(LA_0129))
    assert _consulta(dsn, "select clave, firma from elemento_parametrico order by clave") == antes
    assert _consulta(dsn, "select count(*) from familia where upper(clave) = 'CIMBRA'") == [["1"]]

    # --- Con materiales: dos elementos que solo difieren en su concreto ---------------------------------------------
    _psql(
        dsn,
        "-c",
        """
        insert into elemento_parametrico (org_id, clave, nombre, tipo, parametros, categoria, subcategoria, materiales)
          select org_id, 'K-2', 'Castillo con concreto A', tipo, parametros, categoria, subcategoria, '{"concreto": "MEZ-01020"}' from elemento_parametrico where clave = 'K-1';
        insert into elemento_parametrico (org_id, clave, nombre, tipo, parametros, categoria, subcategoria, materiales)
          select org_id, 'K-3', 'Castillo con concreto B', tipo, parametros, categoria, subcategoria, '{"concreto": "MEZ-01030"}' from elemento_parametrico where clave = 'K-1';
        update elemento_parametrico set firma = app.firma_elemento(categoria, subcategoria, tipo, parametros, materiales) where clave in ('K-2', 'K-3');
        """,
    )
    assert _consulta(dsn, "select count(distinct firma) from elemento_parametrico") == [["4"]]

    # --- Baja la 0129: el esquema vuelve a ser el de la 0128 y ningún elemento se pierde ----------------------------
    _psql(dsn, "-q", "-f", str(DOWN_0129))
    assert _consulta(dsn, "select to_regclass('elemento_insumo') is null, (select count(*) from information_schema.columns where table_name in ('insumo', 'elemento_parametrico') and column_name in ('provisional', 'materiales'))") == [["t", "0"]]
    assert _consulta(dsn, "select count(*) from pg_proc where proname = 'firma_elemento'") == [["1"]]
    # La firma de lo que no tenía materiales es la misma; K-2 y K-3 ya serían idénticos a K-1: el más antiguo (K-1) conserva la
    # firma y los demás quedan sin ella (no se borran).
    firmas = dict(_consulta(dsn, "select clave, coalesce(firma, '-') from elemento_parametrico"))
    assert firmas["K-1"] == dict(antes)["K-1"] and firmas["CE-1"] == dict(antes)["CE-1"]
    assert firmas["K-2"] == "-" and firmas["K-3"] == "-"
    assert _consulta(dsn, "select count(*) from elemento_parametrico") == [["4"]]
    assert _consulta(dsn, "select parent_id is not null from familia where upper(clave) = 'CIMBRA'") == [["t"]]

    # --- Y vuelve a subir -------------------------------------------------------------------------------------------
    _psql(dsn, "-q", "-f", str(LA_0129))
    assert _consulta(dsn, "select count(*) from elemento_parametrico where materiales = '{}'") == [["4"]]
    assert _consulta(dsn, "select clave, firma from elemento_parametrico where clave in ('K-1', 'CE-1') order by clave") == antes
