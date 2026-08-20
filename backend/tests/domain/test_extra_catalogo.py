"""Alta extra-catálogo (§11.2, §5.1).

Lo que se fija aquí son las dos reglas que hacen útil esta ruta y no solo
posible: **no hay extra sin orden de cambio**, y **no hay extra sin precio del
modo de pago que se eligió**. La primera es de autorización; la segunda es más
sutil y por eso importa: una actividad sin precio no se puede estimar (§11.3 E),
así que sería trabajo real que nadie va a cobrar.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.obras.extra_catalogo import (
    ActividadExtra,
    ErrorDeExtraCatalogo,
    puede_dar_de_alta_extra,
)
from obractrl.domain.shared.diccionario import EstatusActividad, ModoPago, Rol

OBRA = "11111111-1111-1111-1111-111111111111"


def _crear(**cambios: object) -> ActividadExtra:
    datos: dict[str, object] = {
        "obra_id": OBRA,
        "descripcion": "Demoler muro que el proyecto no traía",
        "orden_cambio": "OC-2026-014",
        "cant_base": Decimal("12.5"),
        "rol": Rol.RESIDENTE,
        "modo_pago": ModoPago.DESTAJO,
        "precio_destajo": Decimal("350"),
    }
    datos.update(cambios)
    return ActividadExtra.crear(**datos)  # type: ignore[arg-type]


class TestQuienDaDeAlta:
    def test_el_residente_si(self) -> None:
        assert puede_dar_de_alta_extra(Rol.RESIDENTE)

    @pytest.mark.parametrize(
        "rol", [Rol.SUPERVISOR, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE]
    )
    def test_los_demas_no(self, rol: Rol) -> None:
        """Quien da de alta un extra afirma que ese trabajo existe en la obra, y
        el único que puede afirmarlo es quien está ahí (§11.2)."""
        assert not puede_dar_de_alta_extra(rol)

    def test_el_alta_lo_rechaza_con_el_campo_marcado(self) -> None:
        with pytest.raises(ErrorDeExtraCatalogo) as excinfo:
            _crear(rol=Rol.CONTROL_OBRA)
        assert excinfo.value.campo == "rol"


class TestOrdenDeCambio:
    def test_es_obligatoria(self) -> None:
        with pytest.raises(ErrorDeExtraCatalogo, match="orden de cambio") as excinfo:
            _crear(orden_cambio="")
        assert excinfo.value.campo == "orden_cambio"

    def test_solo_espacios_es_lo_mismo_que_vacía(self) -> None:
        with pytest.raises(ErrorDeExtraCatalogo):
            _crear(orden_cambio="    ")

    def test_se_normaliza(self) -> None:
        assert _crear(orden_cambio="  OC-2026-014  ").orden_cambio == "OC-2026-014"


class TestDatosDelTrabajo:
    def test_la_descripcion_es_obligatoria(self) -> None:
        with pytest.raises(ErrorDeExtraCatalogo) as excinfo:
            _crear(descripcion="   ")
        assert excinfo.value.campo == "descripcion"

    def test_la_descripcion_se_normaliza(self) -> None:
        assert _crear(descripcion="  Demoler   muro  ").descripcion == "Demoler muro"

    @pytest.mark.parametrize("cantidad", [Decimal(0), Decimal("-1")])
    def test_la_cantidad_debe_ser_positiva(self, cantidad: Decimal) -> None:
        with pytest.raises(ErrorDeExtraCatalogo) as excinfo:
            _crear(cant_base=cantidad)
        assert excinfo.value.campo == "cant_base"

    def test_la_duracion_debe_ser_positiva(self) -> None:
        with pytest.raises(ErrorDeExtraCatalogo) as excinfo:
            _crear(duracion_dias=Decimal(0))
        assert excinfo.value.campo == "duracion_dias"


class TestPrecio:
    def test_un_destajo_sin_precio_de_destajo_no_se_puede_estimar(self) -> None:
        with pytest.raises(ErrorDeExtraCatalogo, match="nadie lo cobra") as excinfo:
            _crear(precio_destajo=Decimal(0))
        assert excinfo.value.campo == "precio_destajo"

    def test_por_concepto_pide_el_unitario_y_no_el_destajo(self) -> None:
        # Se exige el precio del modo elegido, no los dos: un trabajo por
        # concepto no tiene por qué traer precio de destajo.
        extra = _crear(
            modo_pago=ModoPago.CONCEPTO,
            precio_unitario=Decimal("1200"),
            precio_destajo=Decimal(0),
        )
        assert extra.precio_unitario == Decimal("1200")

    def test_por_concepto_sin_unitario_falla(self) -> None:
        with pytest.raises(ErrorDeExtraCatalogo) as excinfo:
            _crear(modo_pago=ModoPago.CONCEPTO, precio_destajo=Decimal("350"))
        assert excinfo.value.campo == "precio_unitario"

    def test_los_precios_negativos_no_pasan(self) -> None:
        with pytest.raises(ErrorDeExtraCatalogo, match="negativos"):
            _crear(precio_unitario=Decimal("-1"))


class TestEstatusInicial:
    def test_nace_en_extra_catalogo(self) -> None:
        """Es el equivalente de `programada` para un extra, y lo que permite
        listar «lo que di de alta y todavía no empieza» (§8.2)."""
        assert _crear().estatus is EstatusActividad.EXTRA_CATALOGO
