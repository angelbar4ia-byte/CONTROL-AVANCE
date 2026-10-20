"""Cuantificador: `ENLACE_CUANTIFICACION` y la suma de vigentes (MODELO.md
§1b).

Dominio puro — ninguna de estas pruebas toca Postgres ni PostGIS (eso lo
cubre `tests/integracion/test_cuantificacion_endtoend.py`).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.cuantificacion.reglas import (
    EnlaceCuantificacion,
    ErrorDeCuantificacion,
    MedidaDeEnlace,
    cantidad_medida,
)
from obractrl.domain.shared.diccionario import (
    MedidaCuantificacion,
    TipoNodoCuantificacion,
)


def _enlace(**kwargs: object) -> EnlaceCuantificacion:
    base: dict[str, object] = {
        "trazo_id": "trazo-1",
        "actividad_id": "act-1",
        "prototipo_nodo_id": None,
        "medida": MedidaCuantificacion.AREA,
        "factor": Decimal("1"),
    }
    base.update(kwargs)
    return EnlaceCuantificacion(**base)  # type: ignore[arg-type]


class TestConstruccion:
    def test_enlace_a_actividad_valido(self) -> None:
        e = _enlace()
        assert e.tipo_nodo is TipoNodoCuantificacion.ACTIVIDAD

    def test_enlace_a_prototipo_nodo_valido(self) -> None:
        e = _enlace(actividad_id=None, prototipo_nodo_id="proto-nodo-1")
        assert e.tipo_nodo is TipoNodoCuantificacion.PROTOTIPO_NODO

    def test_exige_exactamente_un_nodo_ninguno(self) -> None:
        with pytest.raises(ErrorDeCuantificacion, match=r"actividad.*prototipo_nodo"):
            _enlace(actividad_id=None, prototipo_nodo_id=None)

    def test_exige_exactamente_un_nodo_los_dos(self) -> None:
        with pytest.raises(ErrorDeCuantificacion, match=r"actividad.*prototipo_nodo"):
            _enlace(prototipo_nodo_id="proto-nodo-1")

    def test_factor_cero_rechaza(self) -> None:
        with pytest.raises(ErrorDeCuantificacion, match="factor"):
            _enlace(factor=Decimal("0"))

    def test_factor_negativo_rechaza(self) -> None:
        with pytest.raises(ErrorDeCuantificacion, match="factor"):
            _enlace(factor=Decimal("-1"))

    def test_conteo_con_factor_entero_acepta(self) -> None:
        e = _enlace(medida=MedidaCuantificacion.CONTEO, factor=Decimal("3"))
        assert e.medida is MedidaCuantificacion.CONTEO

    def test_conteo_con_factor_fraccionario_rechaza(self) -> None:
        with pytest.raises(ErrorDeCuantificacion, match="conteo"):
            _enlace(medida=MedidaCuantificacion.CONTEO, factor=Decimal("1.5"))

    def test_area_con_factor_fraccionario_acepta(self) -> None:
        # A diferencia de conteo, area/perimetro/longitud sí admiten un
        # factor de conversión fraccionario (MODELO.md §1b).
        e = _enlace(medida=MedidaCuantificacion.AREA, factor=Decimal("0.5"))
        assert e.factor == Decimal("0.5")


class TestCantidadMedida:
    def test_suma_solo_los_vigentes(self) -> None:
        enlaces = [
            MedidaDeEnlace(medida_valor=Decimal("12"), factor=Decimal("1"), vigente=True),
            MedidaDeEnlace(medida_valor=Decimal("8"), factor=Decimal("1"), vigente=False),
        ]
        assert cantidad_medida(enlaces) == Decimal("12")

    def test_varios_vigentes_del_mismo_nodo_suman(self) -> None:
        # Cuarenta trabes = cuarenta enlaces vigentes al mismo nodo
        # (MODELO.md §1b); aquí, tres, por brevedad.
        enlaces = [
            MedidaDeEnlace(medida_valor=Decimal("3"), factor=Decimal("1"), vigente=True),
            MedidaDeEnlace(medida_valor=Decimal("4"), factor=Decimal("1"), vigente=True),
            MedidaDeEnlace(medida_valor=Decimal("5"), factor=Decimal("1"), vigente=True),
        ]
        assert cantidad_medida(enlaces) == Decimal("12")

    def test_factor_multiplica_cada_enlace(self) -> None:
        enlaces = [
            MedidaDeEnlace(medida_valor=Decimal("10"), factor=Decimal("2"), vigente=True),
            MedidaDeEnlace(medida_valor=Decimal("5"), factor=Decimal("3"), vigente=True),
        ]
        assert cantidad_medida(enlaces) == Decimal("35")

    def test_ningun_vigente_da_cero(self) -> None:
        enlaces = [
            MedidaDeEnlace(medida_valor=Decimal("12"), factor=Decimal("1"), vigente=False),
        ]
        assert cantidad_medida(enlaces) == Decimal(0)

    def test_sin_enlaces_da_cero(self) -> None:
        assert cantidad_medida([]) == Decimal(0)

    def test_reemplazo_cambia_la_suma(self) -> None:
        # Mismo escenario que ReemplazarEnlace: el viejo pasa a no vigente,
        # el nuevo entra vigente — la suma refleja solo el vigente.
        antes = [
            MedidaDeEnlace(medida_valor=Decimal("10"), factor=Decimal("1"), vigente=True),
        ]
        assert cantidad_medida(antes) == Decimal("10")

        despues = [
            MedidaDeEnlace(medida_valor=Decimal("10"), factor=Decimal("1"), vigente=False),
            MedidaDeEnlace(medida_valor=Decimal("15"), factor=Decimal("1"), vigente=True),
        ]
        assert cantidad_medida(despues) == Decimal("15")
