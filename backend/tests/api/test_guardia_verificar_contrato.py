"""La guardia de `verificar_contrato.py --escribir`: no regenerar el contrato
con versiones que se apartan de `backend/constraints.txt`.

El script se carga por ruta, como `verificar_compatibilidad.py` en
`test_compatibilidad_de_contrato.py`: vive fuera del paquete a propósito.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

RAIZ = Path(__file__).resolve().parents[3]


def _cargar_script() -> Any:
    ruta = RAIZ / "backend" / "scripts" / "verificar_contrato.py"
    spec = importlib.util.spec_from_file_location("verificar_contrato", ruta)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


vc = _cargar_script()

CONSTRAINTS = """\
# comentario con fastapi==9.9.9 que no cuenta
fastapi==0.141.1
starlette==1.6.0
Pydantic_Settings==2.7.0   # el nombre se normaliza
pydantic==2.13.4
ruff==0.17.2
"""


def test_lee_las_versiones_fijadas_ignorando_comentarios() -> None:
    fijadas = vc.versiones_fijadas(CONSTRAINTS)
    assert fijadas["fastapi"] == "0.141.1"
    assert fijadas["pydantic-settings"] == "2.7.0"
    assert fijadas["ruff"] == "0.17.2"


def test_sin_desvios_cuando_el_entorno_coincide() -> None:
    fijadas = vc.versiones_fijadas(CONSTRAINTS)
    instaladas = {p: fijadas[p] for p in vc.PAQUETES_DEL_CONTRATO}
    assert vc.desvios_del_entorno(fijadas, instaladas) == []


def test_marca_el_paquete_con_otra_version() -> None:
    fijadas = vc.versiones_fijadas(CONSTRAINTS)
    instaladas = {p: fijadas[p] for p in vc.PAQUETES_DEL_CONTRATO}
    instaladas["pydantic"] = "2.10.0"
    assert vc.desvios_del_entorno(fijadas, instaladas) == [
        "pydantic: instalado 2.10.0, fijado 2.13.4"
    ]


def test_marca_el_paquete_que_falta() -> None:
    fijadas = vc.versiones_fijadas(CONSTRAINTS)
    instaladas: dict[str, str | None] = {p: fijadas[p] for p in vc.PAQUETES_DEL_CONTRATO}
    instaladas["starlette"] = None
    assert vc.desvios_del_entorno(fijadas, instaladas) == [
        "starlette: instalado ninguno, fijado 1.6.0"
    ]


def test_ruff_no_cuenta_aunque_este_fijado() -> None:
    fijadas = vc.versiones_fijadas(CONSTRAINTS)
    instaladas = {p: fijadas[p] for p in vc.PAQUETES_DEL_CONTRATO}
    instaladas["ruff"] = "0.1.0"
    assert vc.desvios_del_entorno(fijadas, instaladas) == []


def test_escribir_se_niega_y_no_toca_el_contrato(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    contrato = tmp_path / "openapi.json"
    contrato.write_text("original", encoding="utf-8")
    monkeypatch.setattr(vc, "CONTRATO", contrato)
    monkeypatch.setattr(vc, "_instaladas", lambda: {"fastapi": "0.1.0"})
    monkeypatch.setattr(vc.sys, "argv", ["verificar_contrato.py", "--escribir"])

    assert vc.main() == 2
    assert contrato.read_text(encoding="utf-8") == "original"
    assert "se aparta de backend/constraints.txt" in capsys.readouterr().err
