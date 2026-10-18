"""Explosión de un ensamble paramétrico (skill erp-parametrico §0, §4).

El caso que manda: una casa con dos recámaras iguales (un sub-ensamble
repetido) más un concepto suelto directo — para comprobar a la vez que la
cantidad se acumula por el camino (igual que un auxiliar de APU) y que la
explosión de contratación agrupa el destajo por sub-ensamble sin contarlo
dos veces.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

import pytest

from obractrl.domain.catalogos.apu import (
    CicloEnExplosion,
    ErrorDeAPU,
    ProfundidadExcedida,
)
from obractrl.domain.catalogos.ensamble import (
    RenglonEnsamble,
    agrupar_contratacion,
    explotar_ensamble,
)
from obractrl.domain.shared.diccionario import OrigenCantidadEnsamble, TipoHijoEnsamble
from obractrl.domain.shared.valores import Dinero, PrecioUnitario


def concepto(clave: str, cantidad: str, origen: OrigenCantidadEnsamble, orden: int = 0) -> RenglonEnsamble:
    return RenglonEnsamble(
        cantidad=Decimal(cantidad), origen=origen, clave_concepto=clave, orden=orden
    )


def sub_ensamble(clave: str, cantidad: str, orden: int = 0) -> RenglonEnsamble:
    return RenglonEnsamble(
        cantidad=Decimal(cantidad),
        origen=OrigenCantidadEnsamble.MANUAL,
        clave_sub_ensamble=clave,
        orden=orden,
    )


class TestRenglonEnsamble:
    def test_apunta_a_un_concepto_o_a_un_sub_ensamble_pero_no_a_ambos(self) -> None:
        with pytest.raises(ErrorDeAPU, match="nunca a los dos"):
            RenglonEnsamble(
                cantidad=Decimal(1),
                origen=OrigenCantidadEnsamble.MANUAL,
                clave_concepto="EST-1",
                clave_sub_ensamble="ENS-1",
            )

    def test_tiene_que_apuntar_a_algo(self) -> None:
        with pytest.raises(ErrorDeAPU, match="nunca a los dos"):
            RenglonEnsamble(cantidad=Decimal(1), origen=OrigenCantidadEnsamble.MANUAL)

    def test_tipo_hijo_y_referencia(self) -> None:
        renglon = concepto("EST-MURO", "4", OrigenCantidadEnsamble.MANUAL)
        assert renglon.tipo_hijo is TipoHijoEnsamble.CONCEPTO
        assert renglon.referencia == "EST-MURO"

        sub = sub_ensamble("RECAMARA-A", "2")
        assert sub.tipo_hijo is TipoHijoEnsamble.ENSAMBLE
        assert sub.referencia == "RECAMARA-A"


_PRECIOS: Mapping[str, PrecioUnitario] = {
    "EST-MURO": PrecioUnitario(total=Dinero("100.00"), destajo=Dinero("40.00")),
    "EST-PISO": PrecioUnitario(total=Dinero("50.00"), destajo=Dinero("0.00")),
    "EST-LOSA": PrecioUnitario(total=Dinero("200.00"), destajo=Dinero("80.00")),
}


class TestExplosionDeCosto:
    """CASA-A: 2 × RECAMARA-A (MURO×4 + PISO×1) + 1 × EST-LOSA suelto."""

    composicion: Mapping[str, Sequence[RenglonEnsamble]] = {
        "CASA-A": [
            sub_ensamble("RECAMARA-A", "2", orden=1),
            concepto("EST-LOSA", "1", OrigenCantidadEnsamble.HEREDADA_CONCEPTO, orden=2),
        ],
        "RECAMARA-A": [
            concepto("EST-MURO", "4", OrigenCantidadEnsamble.MANUAL, orden=1),
            concepto("EST-PISO", "1", OrigenCantidadEnsamble.HEREDADA_CONCEPTO, orden=2),
        ],
    }

    def test_el_costo_total_suma_el_sub_ensamble_y_el_concepto_suelto(self) -> None:
        # RECAMARA-A = 4×100 + 1×50 = 450 por unidad.
        # CASA-A = 2×450 + 1×200 = 1,100.
        calculada = explotar_ensamble("CASA-A", composiciones=self.composicion, precios_concepto=_PRECIOS)
        assert calculada.precio.total == Dinero("1100.00")

    def test_el_destajo_arrastra_el_del_sub_ensamble(self) -> None:
        # RECAMARA-A destajo = 4×40 + 1×0 = 160.
        # CASA-A destajo = 2×160 + 1×80 = 400.
        calculada = explotar_ensamble("CASA-A", composiciones=self.composicion, precios_concepto=_PRECIOS)
        assert calculada.precio.destajo == Dinero("400.00")

    def test_las_lineas_van_en_recorrido_padre_antes_que_hijos(self) -> None:
        calculada = explotar_ensamble("CASA-A", composiciones=self.composicion, precios_concepto=_PRECIOS)
        assert [(linea.nivel, linea.referencia) for linea in calculada.lineas] == [
            (1, "RECAMARA-A"),
            (2, "EST-MURO"),
            (2, "EST-PISO"),
            (1, "EST-LOSA"),
        ]

    def test_la_cantidad_del_nieto_se_acumula_por_el_camino(self) -> None:
        calculada = explotar_ensamble("CASA-A", composiciones=self.composicion, precios_concepto=_PRECIOS)
        muro = next(linea for linea in calculada.lineas if linea.referencia == "EST-MURO")
        # 4 por unidad de recámara × 2 recámaras por unidad de casa.
        assert muro.cantidad_unitaria == Decimal("4.000000")
        assert muro.cantidad == Decimal("8.000000")
        assert muro.ruta == ("CASA-A", "RECAMARA-A")
        assert muro.importe == Decimal("800.00")  # 8 × 100
        assert muro.importe_destajo == Decimal("320.00")  # 8 × 40

    def test_la_linea_del_sub_ensamble_trae_su_costo_explotado(self) -> None:
        calculada = explotar_ensamble("CASA-A", composiciones=self.composicion, precios_concepto=_PRECIOS)
        recamara = next(linea for linea in calculada.lineas if linea.referencia == "RECAMARA-A")
        assert recamara.tipo_hijo is TipoHijoEnsamble.ENSAMBLE
        assert recamara.costo_unitario == Decimal("450")
        assert recamara.destajo_unitario == Decimal("160")
        assert recamara.importe == Decimal("900.00")  # 2 × 450
        assert recamara.importe_destajo == Decimal("320.00")  # 2 × 160

    def test_un_concepto_sin_precio_vale_cero_sin_romper_la_explosion(self) -> None:
        """Un concepto hoja sin CPU vigente todavía no es un error — vale
        cero, igual que un concepto sin `Explosion` en APU."""
        calculada = explotar_ensamble(
            "CASA-A", composiciones=self.composicion, precios_concepto={}
        )
        assert calculada.precio.total == Dinero("0.00")

    def test_un_sub_ensamble_repetido_en_dos_ramas_no_es_ciclo(self) -> None:
        composicion = {
            "CASA-B": [sub_ensamble("BANO-X", "1", orden=1), sub_ensamble("BANO-Y", "1", orden=2)],
            "BANO-X": [sub_ensamble("REGADERA", "1")],
            "BANO-Y": [sub_ensamble("REGADERA", "1")],
            "REGADERA": [concepto("EST-REG", "1", OrigenCantidadEnsamble.MANUAL)],
        }
        precios = {"EST-REG": PrecioUnitario(total=Dinero("10.00"), destajo=Dinero("0"))}
        calculada = explotar_ensamble("CASA-B", composiciones=composicion, precios_concepto=precios)
        assert calculada.precio.total == Dinero("20.00")


class TestCiclos:
    def test_el_ciclo_directo_falla_con_error_de_dominio(self) -> None:
        composicion = {"ENS-A": [sub_ensamble("ENS-A", "1")]}
        with pytest.raises(CicloEnExplosion):
            explotar_ensamble("ENS-A", composiciones=composicion)

    def test_el_ciclo_indirecto_tambien(self) -> None:
        composicion = {
            "ENS-A": [sub_ensamble("ENS-B", "1")],
            "ENS-B": [sub_ensamble("ENS-A", "1")],
        }
        with pytest.raises(CicloEnExplosion):
            explotar_ensamble("ENS-A", composiciones=composicion)

    def test_el_ciclo_profundo_no_cuelga(self) -> None:
        composicion = {f"ENS-{i}": [sub_ensamble(f"ENS-{i + 1}", "1")] for i in range(40)}
        composicion["ENS-39"] = [sub_ensamble("ENS-0", "1")]
        with pytest.raises(ProfundidadExcedida):
            explotar_ensamble("ENS-0", composiciones=composicion)


class TestAgruparContratacion:
    """CASA-A del fixture de arriba: 2 recámaras + losa suelta."""

    composicion = TestExplosionDeCosto.composicion

    def test_agrupa_el_destajo_por_sub_ensamble(self) -> None:
        calculada = explotar_ensamble("CASA-A", composiciones=self.composicion, precios_concepto=_PRECIOS)
        grupos = agrupar_contratacion(calculada.lineas)

        por_clave = {g.clave: g for g in grupos}
        assert set(por_clave) == {"RECAMARA-A", "CASA-A"}
        # El destajo de las dos recámanas (muro×8 a $40) cae bajo RECAMARA-A.
        assert por_clave["RECAMARA-A"].destajo_total == Decimal("320.00")
        # La losa, suelta en CASA-A, cae bajo CASA-A mismo (su ruta[-1]).
        assert por_clave["CASA-A"].destajo_total == Decimal("80.00")

    def test_el_sub_ensamble_no_se_cuenta_aparte_de_sus_propios_conceptos(self) -> None:
        """Si se sumara también la línea de RECAMARA-A (nivel 1, tipo
        ENSAMBLE) el destajo se contaría dos veces: una por la línea del
        sub-ensamble y otra por sus conceptos hoja."""
        calculada = explotar_ensamble("CASA-A", composiciones=self.composicion, precios_concepto=_PRECIOS)
        grupos = agrupar_contratacion(calculada.lineas)
        total = sum((g.destajo_total for g in grupos), Decimal(0))
        assert total == calculada.precio.destajo.monto == Decimal("400.00")

    def test_sin_destajo_no_hay_grupo(self) -> None:
        composicion = {
            "ENS-SOLO-MATERIAL": [concepto("EST-PISO", "1", OrigenCantidadEnsamble.MANUAL)],
        }
        calculada = explotar_ensamble(
            "ENS-SOLO-MATERIAL", composiciones=composicion, precios_concepto=_PRECIOS
        )
        assert agrupar_contratacion(calculada.lineas) == ()
