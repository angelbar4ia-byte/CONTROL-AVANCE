"""Armar el precio de un trabajo fuera de catálogo (§11.2, §7.3).

El jefe de obra lo describió así: *"el residente dice qué cuadrilla va a
utilizar, cuántas y el tiempo, también el material, y se crea el precio"*.

Lo que estas pruebas fijan son las decisiones que rodean la suma:

 1. **Un dato que falta no vale cero.** Una cuadrilla sin costo por jornada
    capturado no es gratis: no se sabe cuánto cuesta. Contarla como cero haría
    que el extra se autorizara por debajo de su costo y que alguien lo
    descubriera al pagarlo. Sale reportada.
 2. **Una jornada es una cuadrilla un día**, igual que en la planeación. Si
    aquí significara otra cosa, el precio de un extra y el conteo de gente de la
    obra hablarían de unidades distintas sobre el mismo trabajo.
 3. **El unitario se reparte entre la cantidad del trabajo**, no entre la
    gente: es lo que se cobra por m² y es con lo que se estima después.
 4. **Se redondea al final.** Redondear renglón por renglón acumula el error y
    el total deja de ser la suma de lo que la pantalla enseña.

Módulo puro: sin BD, sin reloj (§12.11).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.obras.precio_armado import (
    ErrorDePrecioArmado,
    LineaDeCuadrilla,
    LineaDeMaterial,
    armar_precio,
)


def _cuadrilla(
    *,
    cuadrillas: str = "2",
    dias: str = "3",
    costo: str | None = "1500",
    nombre: str = "Albañiles A",
) -> LineaDeCuadrilla:
    return LineaDeCuadrilla(
        cuadrilla_id="cua-1",
        nombre=nombre,
        cuadrillas=Decimal(cuadrillas),
        dias=Decimal(dias),
        costo_jornada=None if costo is None else Decimal(costo),
    )


def _material(
    *, cantidad: str = "10", costo: str | None = "250", descripcion: str = "Cemento"
) -> LineaDeMaterial:
    return LineaDeMaterial(
        insumo_id="ins-1",
        descripcion=descripcion,
        cantidad=Decimal(cantidad),
        costo=None if costo is None else Decimal(costo),
    )


class TestLaSuma:
    def test_mano_de_obra_es_cuadrillas_por_dias_por_costo(self) -> None:
        # 2 cuadrillas × 3 días = 6 jornadas × 1500 = 9000.
        precio = armar_precio(cantidad=Decimal(30), cuadrillas=[_cuadrilla()])
        assert precio.jornadas == Decimal(6)
        assert precio.mano_obra == Decimal(9000)

    def test_materiales_es_cantidad_por_costo(self) -> None:
        precio = armar_precio(cantidad=Decimal(30), materiales=[_material()])
        assert precio.materiales == Decimal(2500)

    def test_el_total_es_la_suma_de_los_dos(self) -> None:
        precio = armar_precio(
            cantidad=Decimal(30),
            cuadrillas=[_cuadrilla()],
            materiales=[_material()],
        )
        assert precio.total == Decimal(11500)

    def test_el_unitario_se_reparte_entre_la_cantidad_del_trabajo(self) -> None:
        # 11 500 entre 30 m² = 383.33 por m². Es lo que se cobra y con lo que se
        # estima después: repartirlo entre la gente daría el costo por cuadrilla,
        # que no es lo que nadie factura.
        precio = armar_precio(
            cantidad=Decimal(30),
            cuadrillas=[_cuadrilla()],
            materiales=[_material()],
        )
        assert precio.precio_unitario == Decimal("383.33")

    def test_se_redondea_al_final_y_no_renglon_por_renglon(self) -> None:
        # Tres materiales de 0.005 cada uno: redondeando cada renglón darían
        # cero y el total mentiría por 0.02.
        precio = armar_precio(
            cantidad=Decimal(1),
            materiales=[
                _material(cantidad="1", costo="0.005", descripcion=f"M{i}")
                for i in range(3)
            ],
        )
        assert precio.materiales == Decimal("0.02")


class TestLoQueFalta:
    def test_una_cuadrilla_sin_costo_no_vale_cero_sino_que_se_reporta(self) -> None:
        """El catálogo tiene 92 cuadrillas y ninguna con precio todavía.

        Si contaran como cero, el extra se autorizaría por debajo de su costo y
        nadie lo notaría hasta pagarlo.
        """
        precio = armar_precio(
            cantidad=Decimal(30), cuadrillas=[_cuadrilla(costo=None)]
        )
        assert precio.sin_costo == ("Albañiles A",)
        assert not precio.completo

    def test_un_material_sin_costo_tambien(self) -> None:
        precio = armar_precio(
            cantidad=Decimal(30), materiales=[_material(costo=None)]
        )
        assert precio.sin_costo == ("Cemento",)

    def test_con_todo_capturado_el_precio_esta_completo(self) -> None:
        precio = armar_precio(
            cantidad=Decimal(30),
            cuadrillas=[_cuadrilla()],
            materiales=[_material()],
        )
        assert precio.completo
        assert precio.sin_costo == ()

    def test_lo_que_si_tiene_costo_sigue_sumando(self) -> None:
        # Una línea incompleta no invalida el resto: el residente sigue viendo
        # cuánto lleva y qué le falta para cerrarlo.
        precio = armar_precio(
            cantidad=Decimal(30),
            cuadrillas=[_cuadrilla(), _cuadrilla(costo=None, nombre="Ayudantes")],
        )
        assert precio.mano_obra == Decimal(9000)
        assert precio.sin_costo == ("Ayudantes",)


class TestLoQueNoSePuedeArmar:
    def test_sin_cantidad_no_hay_unitario_que_calcular(self) -> None:
        with pytest.raises(ErrorDePrecioArmado, match="mayor que cero"):
            armar_precio(cantidad=Decimal(0), cuadrillas=[_cuadrilla()])

    def test_cero_cuadrillas_o_cero_dias_es_un_error_de_captura(self) -> None:
        # No es "gratis": es que alguien dejó el campo a medias.
        with pytest.raises(ErrorDePrecioArmado, match="Albañiles A"):
            armar_precio(cantidad=Decimal(30), cuadrillas=[_cuadrilla(dias="0")])

    def test_un_material_en_cero_tambien(self) -> None:
        with pytest.raises(ErrorDePrecioArmado, match="Cemento"):
            armar_precio(cantidad=Decimal(30), materiales=[_material(cantidad="0")])

    def test_sin_nada_el_precio_es_cero_y_no_un_error(self) -> None:
        # Un trabajo puede no llevar material y aun así tener precio; y el
        # formulario arranca vacío. Cero es un estado legítimo de "todavía no".
        precio = armar_precio(cantidad=Decimal(30))
        assert precio.total == 0
        assert precio.completo
