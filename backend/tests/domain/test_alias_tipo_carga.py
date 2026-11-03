"""Nombres alternos de tipo de carga (D-606, CATALOGOS.md §3): «Contrato» es «trabajos»."""

from __future__ import annotations

import pytest

from obractrl.domain.shared.diccionario import TipoCarga, tipo_carga_con_alias


@pytest.mark.parametrize("valor", ["Contrato", "contrato", "  CONTRATO "])
def test_contrato_resuelve_a_trabajos(valor: str) -> None:
    assert TipoCarga(tipo_carga_con_alias(valor)) == TipoCarga.TRABAJOS


def test_un_canonico_pasa_sin_cambio() -> None:
    assert TipoCarga(tipo_carga_con_alias("trabajos")) == TipoCarga.TRABAJOS


def test_un_valor_desconocido_sigue_rechazado() -> None:
    with pytest.raises(ValueError):
        TipoCarga(tipo_carga_con_alias("inventado"))
