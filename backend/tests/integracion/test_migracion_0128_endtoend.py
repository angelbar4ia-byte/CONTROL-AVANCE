"""La migración 0128 (conceptos del elemento por contexto) con datos previos: relleno, repetición, bajada y subida.

Arma una base aparte, aplica las migraciones hasta la 0127, guarda conceptos como los guardaba el modelo anterior y prueba la
0128 encima: lo que ya existía queda como concepto del catálogo, autorizado y sin contexto; correrla dos veces no cambia nada;
su `down` borra solo lo que el modelo anterior no puede guardar; y vuelve a subir.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.integracion.conftest import DATABASE_URL_ADMIN

MIGRACIONES = Path(__file__).resolve().parents[3] / "database" / "migrations"
NUMERO = "20260814000128"

pytestmark = pytest.mark.skipif(shutil.which("psql") is None, reason="Requiere psql en el PATH.")


def _dsn(base: str) -> str:
    return (DATABASE_URL_ADMIN or "").replace("postgresql+asyncpg://", "postgresql://").rsplit("/", 1)[0] + "/" + base


def _psql(dsn: str, *args: str, entrada: str | None = None) -> str:
    r = subprocess.run(  # noqa: S603
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-q", "-t", "-A", *args], input=entrada, capture_output=True, text=True, check=False
    )
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.fixture
def base_en_127() -> Iterator[str]:
    nombre = f"obractrl_m128_{uuid.uuid4().hex[:8]}"
    admin = _dsn("postgres")
    _psql(admin, "-c", f"create database {nombre}")
    dsn = _dsn(nombre)
    try:
        for f in sorted(MIGRACIONES.glob("*.sql")):
            if f.name.split("_")[0] < NUMERO:
                _psql(dsn, "-f", str(f))
        yield dsn
    finally:
        _psql(admin, "-c", f"drop database if exists {nombre} with (force)")


def _sembrar(dsn: str) -> None:
    _psql(
        dsn,
        entrada="""
        insert into organizacion(id, nombre, slug) values ('11111111-1111-1111-1111-111111111111', 't', 'm128');
        insert into elemento_parametrico(id, org_id, clave, nombre, tipo, parametros, categoria, subcategoria)
          values ('22222222-2222-2222-2222-222222222222', '11111111-1111-1111-1111-111111111111', 'K-1', 'K', 'castillo', '{}', 'castillos', 'muro');
        insert into concepto(id, org_id, clave, descripcion) values
          ('33333333-3333-3333-3333-333333333333', '11111111-1111-1111-1111-111111111111', 'EST-10010', 'Acero'),
          ('44444444-4444-4444-4444-444444444444', '11111111-1111-1111-1111-111111111111', 'EST-02110', 'Colado'),
          ('55555555-5555-5555-5555-555555555555', '11111111-1111-1111-1111-111111111111', 'EST-07010', 'Completo');
        insert into elemento_concepto(org_id, elemento_id, concepto_id, unidad, toma) values
          ('11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', '33333333-3333-3333-3333-333333333333', 'pza', '{"acero": true, "alambre": true}'),
          ('11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', '44444444-4444-4444-4444-444444444444', 'ml', '{"concreto": true, "cimbra": true}'),
          ('11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', '55555555-5555-5555-5555-555555555555', 'pza', '{"acero": true, "concreto": true}');
        """,
    )


_RESUMEN = (
    "select c.clave || ':' || ec.ranura || ':' || ec.estado || ':' || coalesce(ec.nivel_min::text, '-') || ':' || coalesce(ec.alto_hasta_m::text, '-') "
    "from elemento_concepto ec join concepto c on c.id = ec.concepto_id order by c.clave"
)


def test_el_relleno_deja_lo_que_existia_autorizado_y_sin_contexto_y_se_puede_repetir(base_en_127: str) -> None:
    dsn = base_en_127
    _sembrar(dsn)
    archivo = str(MIGRACIONES / f"{NUMERO}_elemento_concepto_contextos.sql")
    _psql(dsn, "-f", archivo)
    esperado = "EST-02110:colado:autorizado:-:-\nEST-07010:completo:autorizado:-:-\nEST-10010:acero:autorizado:-:-"
    assert _psql(dsn, "-c", _RESUMEN) == esperado
    _psql(dsn, "-f", archivo)  # idempotente
    assert _psql(dsn, "-c", _RESUMEN) == esperado
    assert _psql(dsn, "-c", "select count(*) from elemento_concepto") == "3"


def test_el_down_borra_solo_lo_nuevo_y_la_subida_vuelve_a_funcionar(base_en_127: str) -> None:
    dsn = base_en_127
    _sembrar(dsn)
    subir = str(MIGRACIONES / f"{NUMERO}_elemento_concepto_contextos.sql")
    bajar = str(MIGRACIONES / "down" / f"{NUMERO}_elemento_concepto_contextos.sql")
    _psql(dsn, "-f", subir)
    _psql(
        dsn,
        entrada="""
        insert into elemento_concepto(org_id, elemento_id, concepto_id, unidad, toma, nivel_min, alto_hasta_m)
          values ('11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', '33333333-3333-3333-3333-333333333333', 'pza', '{"acero": true}', 3, 4);
        insert into elemento_concepto(org_id, elemento_id, clave_propuesta, descripcion, estado, unidad, toma)
          values ('11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'EJ-410', 'Nuevo', 'propuesto', 'pza', '{"acero": true}');
        """,
    )
    assert _psql(dsn, "-c", "select count(*) from elemento_concepto") == "5"
    _psql(dsn, "-f", bajar)
    assert _psql(dsn, "-c", "select count(*) from elemento_concepto") == "3"  # los generales del catálogo se conservan
    assert _psql(dsn, "-c", "select count(*) from information_schema.columns where table_name = 'elemento_concepto' and column_name = 'ranura'") == "0"
    _psql(dsn, "-f", subir)
    assert _psql(dsn, "-c", _RESUMEN).count("\n") == 2


def test_la_base_rechaza_lo_que_el_modelo_no_admite(base_en_127: str) -> None:
    dsn = base_en_127
    _sembrar(dsn)
    _psql(dsn, "-f", str(MIGRACIONES / f"{NUMERO}_elemento_concepto_contextos.sql"))
    base = (
        "insert into elemento_concepto(org_id, elemento_id, concepto_id, clave_propuesta, descripcion, estado, unidad, toma, nivel_min, nivel_max) "
        "values ('11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', {c}, {k}, {d}, '{e}', 'pza', '{{\"acero\": true}}', {a}, {b})"
    )
    malas = [
        base.format(c="null", k="null", d="null", e="propuesto", a="null", b="null"),  # sin concepto ni clave
        base.format(c="null", k="'EJ-1'", d="null", e="propuesto", a="null", b="null"),  # sin descripción
        base.format(c="null", k="'EJ-1'", d="'x'", e="autorizado", a="null", b="null"),  # nuevo no puede estar autorizado
        base.format(c="'33333333-3333-3333-3333-333333333333'", k="null", d="null", e="autorizado", a="3", b="2"),  # niveles al revés
        base.format(c="'33333333-3333-3333-3333-333333333333'", k="null", d="null", e="autorizado", a="null", b="null"),  # repite el general
    ]
    for sql in malas:
        r = subprocess.run(["psql", dsn, "-v", "ON_ERROR_STOP=1", "-q", "-c", sql], capture_output=True, text=True, check=False)  # noqa: S603
        assert r.returncode != 0, sql
