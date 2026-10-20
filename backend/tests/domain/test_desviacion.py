"""Desviación: la entidad y las nueve causas de CONOCIMIENTO.md §13.6.

Dominio puro — ninguna de estas pruebas toca Postgres (eso lo cubre
`tests/integracion/test_desviaciones_repo.py`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from obractrl.domain.desviacion.desviacion import Desviacion, ErrorDeDesviacion
from obractrl.domain.desviacion.nueve_causas import (
    CausaRaiz,
    DestinoHallazgo,
    QuienPaga,
    destino_de_causa,
    quien_paga,
)
from obractrl.domain.shared.diccionario import CausaDesviacion, TipoDesviacion

AHORA = datetime(2026, 10, 16, tzinfo=UTC)


def _consumo(**kwargs: object) -> Desviacion:
    base: dict[str, object] = {
        "insumo_id": "ins-1",
        "concepto_id": None,
        "obra_id": "obra-1",
        "tipo": TipoDesviacion.CONSUMO,
        "monto": Decimal("500"),
        "cantidad_plan": Decimal("10"),
        "cantidad_real": Decimal("12"),
        "precio_plan": None,
        "precio_real": None,
        "detectada_en": AHORA,
    }
    base.update(kwargs)
    return Desviacion(**base)  # type: ignore[arg-type]


def _precio(**kwargs: object) -> Desviacion:
    base: dict[str, object] = {
        "insumo_id": "ins-1",
        "concepto_id": None,
        "obra_id": "obra-1",
        "tipo": TipoDesviacion.PRECIO,
        "monto": Decimal("500"),
        "cantidad_plan": None,
        "cantidad_real": None,
        "precio_plan": Decimal("100"),
        "precio_real": Decimal("120"),
        "detectada_en": AHORA,
    }
    base.update(kwargs)
    return Desviacion(**base)  # type: ignore[arg-type]


class TestConstruccion:
    def test_consumo_valido(self) -> None:
        d = _consumo()
        assert d.tipo is TipoDesviacion.CONSUMO
        assert d.tipo_nodo.value == "insumo"
        assert d.tiene_causa is False

    def test_precio_valido(self) -> None:
        d = _precio()
        assert d.tipo is TipoDesviacion.PRECIO
        assert d.tiene_causa is False

    def test_concepto_en_vez_de_insumo(self) -> None:
        d = _consumo(insumo_id=None, concepto_id="con-1")
        assert d.tipo_nodo.value == "concepto"

    def test_exige_exactamente_un_nodo_ninguno(self) -> None:
        with pytest.raises(ErrorDeDesviacion, match=r"insumo.*concepto"):
            _consumo(insumo_id=None, concepto_id=None)

    def test_exige_exactamente_un_nodo_los_dos(self) -> None:
        with pytest.raises(ErrorDeDesviacion, match=r"insumo.*concepto"):
            _consumo(concepto_id="con-1")

    def test_consumo_no_acepta_precio_plan(self) -> None:
        with pytest.raises(ErrorDeDesviacion, match="consumo"):
            _consumo(precio_plan=Decimal("100"))

    def test_consumo_no_acepta_precio_real(self) -> None:
        with pytest.raises(ErrorDeDesviacion, match="consumo"):
            _consumo(precio_real=Decimal("100"))

    def test_precio_no_acepta_cantidad_plan(self) -> None:
        with pytest.raises(ErrorDeDesviacion, match="precio"):
            _precio(cantidad_plan=Decimal("10"))

    def test_precio_no_acepta_cantidad_real(self) -> None:
        with pytest.raises(ErrorDeDesviacion, match="precio"):
            _precio(cantidad_real=Decimal("10"))

    def test_causa_null_es_estado_valido(self) -> None:
        # Regla de captura 3 (MODELO.md §5g): "sin causa" no es un dato
        # faltante, es una fila completa.
        d = _consumo(causa=None)
        assert d.tiene_causa is False

    def test_causa_coherente_con_tipo(self) -> None:
        d = _consumo(causa=CausaDesviacion.DESPERDICIO_MAYOR_AL_TEORICO)
        assert d.causa is CausaDesviacion.DESPERDICIO_MAYOR_AL_TEORICO

    def test_causa_de_precio_en_fila_de_consumo_rechaza(self) -> None:
        with pytest.raises(ErrorDeDesviacion, match="tipo"):
            _consumo(causa=CausaDesviacion.MERCADO)

    def test_causa_de_consumo_en_fila_de_precio_rechaza(self) -> None:
        with pytest.raises(ErrorDeDesviacion, match="tipo"):
            _precio(causa=CausaDesviacion.RETRABAJO)

    def test_causa_capturada_en_exige_causa(self) -> None:
        with pytest.raises(ErrorDeDesviacion, match="causa"):
            _consumo(causa=None, causa_capturada_en=AHORA)

    def test_causa_capturada_en_independiente_de_detectada_en(self) -> None:
        # Regla de captura 4 (MODELO.md §5g): puede llegar después, sin
        # penalización — aquí solo se prueba que el dominio lo permite, no
        # que haya una regla de "después de".
        despues = datetime(2026, 11, 1, tzinfo=UTC)
        d = _consumo(
            causa=CausaDesviacion.RETRABAJO,
            causa_capturada_por="usr-1",
            causa_capturada_en=despues,
        )
        assert d.causa_capturada_en == despues
        assert d.detectada_en == AHORA


class TestDestinoDeCausa:
    @pytest.mark.parametrize(
        ("causa", "destino"),
        [
            (CausaRaiz.ERROR_DE_EJECUCION, DestinoHallazgo.DESVIACION),
            (CausaRaiz.NECESARIO_PARA_EJECUTAR, DestinoHallazgo.DESVIACION),
            (CausaRaiz.OMISION_DE_PRESUPUESTO, DestinoHallazgo.EJECUTADO_SIN_RESPALDO),
            (CausaRaiz.OMISION_DE_PROYECTO, DestinoHallazgo.EJECUTADO_SIN_RESPALDO),
            (
                CausaRaiz.PETICION_NUEVA_DEL_CLIENTE,
                DestinoHallazgo.ORDEN_DE_CAMBIO_O_INCIDENCIA,
            ),
            (
                CausaRaiz.CONTRATO_CAMBIADO_SIN_PROPAGAR,
                DestinoHallazgo.ORDEN_DE_CAMBIO_O_INCIDENCIA,
            ),
            (CausaRaiz.FALTA_DE_INSUMOS, DestinoHallazgo.PROGRAMA),
            (
                CausaRaiz.MEJORA_DE_PROYECTO,
                DestinoHallazgo.ORDEN_DE_CAMBIO_O_INCIDENCIA,
            ),
        ],
    )
    def test_destino_sin_contexto(
        self, causa: CausaRaiz, destino: DestinoHallazgo
    ) -> None:
        assert destino_de_causa(causa) is destino

    def test_temporalidad_sin_dano_va_a_programa(self) -> None:
        assert (
            destino_de_causa(CausaRaiz.TEMPORALIDAD_O_CLIMA) is DestinoHallazgo.PROGRAMA
        )
        assert (
            destino_de_causa(CausaRaiz.TEMPORALIDAD_O_CLIMA, hubo_dano=False)
            is DestinoHallazgo.PROGRAMA
        )

    def test_temporalidad_con_dano_va_a_incidencia(self) -> None:
        assert (
            destino_de_causa(CausaRaiz.TEMPORALIDAD_O_CLIMA, hubo_dano=True)
            is DestinoHallazgo.ORDEN_DE_CAMBIO_O_INCIDENCIA
        )

    def test_solo_error_de_ejecucion_y_necesario_terminan_en_desviacion(self) -> None:
        # MODELO.md §5g, D-347: "de las nueve, solo 1 ... y 2 ... terminan ahí".
        terminan_en_desviacion = {
            c
            for c in CausaRaiz
            if destino_de_causa(c) is DestinoHallazgo.DESVIACION
        }
        assert terminan_en_desviacion == {
            CausaRaiz.ERROR_DE_EJECUCION,
            CausaRaiz.NECESARIO_PARA_EJECUTAR,
        }


class TestQuienPaga:
    def test_error_de_ejecucion_sin_contratista_activo_paga_constructora(self) -> None:
        assert quien_paga(CausaRaiz.ERROR_DE_EJECUCION) is QuienPaga.CONSTRUCTORA

    def test_error_de_ejecucion_con_contratista_activo_paga_contratista(self) -> None:
        assert (
            quien_paga(CausaRaiz.ERROR_DE_EJECUCION, contratista_activo=True)
            is QuienPaga.CONTRATISTA
        )

    def test_error_de_ejecucion_contratista_explicitamente_inactivo(self) -> None:
        assert (
            quien_paga(CausaRaiz.ERROR_DE_EJECUCION, contratista_activo=False)
            is QuienPaga.CONSTRUCTORA
        )

    @pytest.mark.parametrize(
        "causa",
        [
            CausaRaiz.NECESARIO_PARA_EJECUTAR,
            CausaRaiz.OMISION_DE_PRESUPUESTO,
            CausaRaiz.OMISION_DE_PROYECTO,
        ],
    )
    def test_causas_de_omision_pagan_constructora(self, causa: CausaRaiz) -> None:
        assert quien_paga(causa) is QuienPaga.CONSTRUCTORA

    @pytest.mark.parametrize(
        "causa",
        [CausaRaiz.PETICION_NUEVA_DEL_CLIENTE, CausaRaiz.CONTRATO_CAMBIADO_SIN_PROPAGAR],
    )
    def test_causas_de_cliente_paga_cliente(self, causa: CausaRaiz) -> None:
        assert quien_paga(causa) is QuienPaga.CLIENTE

    def test_falta_de_insumos_no_tiene_quien_paga(self) -> None:
        # Causa de tiempo, no de costo (§13.6) — ningún valor de QuienPaga
        # describe esto honestamente.
        assert quien_paga(CausaRaiz.FALTA_DE_INSUMOS) is None

    def test_temporalidad_sin_dano_no_paga_nadie(self) -> None:
        assert quien_paga(CausaRaiz.TEMPORALIDAD_O_CLIMA) is QuienPaga.NADIE
        assert (
            quien_paga(CausaRaiz.TEMPORALIDAD_O_CLIMA, hubo_dano=False)
            is QuienPaga.NADIE
        )

    def test_temporalidad_con_dano_paga_constructora(self) -> None:
        assert (
            quien_paga(CausaRaiz.TEMPORALIDAD_O_CLIMA, hubo_dano=True)
            is QuienPaga.CONSTRUCTORA
        )

    def test_mejora_de_proyecto_sin_definir(self) -> None:
        # Citado así del cerebro: no se inventa una respuesta.
        assert quien_paga(CausaRaiz.MEJORA_DE_PROYECTO) is QuienPaga.SIN_DEFINIR

    def test_las_nueve_causas_tienen_respuesta(self) -> None:
        # No debe faltar ninguna rama: nueve causas, nueve llamadas válidas
        # (una devuelve None a propósito, documentado arriba).
        for causa in CausaRaiz:
            quien_paga(causa)  # no debe levantar
