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
    CohorteInsuficiente,
    EstadoRenglonGenerado,
    ObservacionTasa,
    PartidaExistente,
    RenglonEnsamble,
    ValorPartida,
    agrupar_contratacion,
    calcular_tasa,
    explotar_ensamble,
    receta_por_concepto,
    reconciliar_generacion,
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


class TestObservacionTasa:
    def test_el_divisor_no_puede_ser_cero_ni_negativo(self) -> None:
        with pytest.raises(ErrorDeAPU, match="no puede ser cero"):
            ObservacionTasa(prototipo_clave="CAS-1", numerador=Decimal(100), divisor=Decimal(0))
        with pytest.raises(ErrorDeAPU, match="no puede ser cero"):
            ObservacionTasa(prototipo_clave="CAS-1", numerador=Decimal(100), divisor=Decimal(-1))

    def test_la_razon_es_numerador_entre_divisor(self) -> None:
        obs = ObservacionTasa(prototipo_clave="CAS-1", numerador=Decimal(100), divisor=Decimal(4))
        assert obs.razon == Decimal(25)


class TestCalcularTasa:
    def test_exige_al_menos_dos_observaciones(self) -> None:
        with pytest.raises(CohorteInsuficiente):
            calcular_tasa([ObservacionTasa(prototipo_clave="CAS-1", numerador=Decimal(100), divisor=Decimal(1))])

    def test_reproduce_el_cv_real_de_cimentacion_contra_desplante(self) -> None:
        """cerebro CONOCIMIENTO.md §5.7 / skill erp-parametrico §5: los
        siete prototipos reales, cimentación medida contra el área de
        desplante de su propia losa (B-52/D-312) — "los siete caen en el
        mismo rango, CV 6.0%". Verificado con los $/m² de desplante que el
        skill reporta ya calculados para cada uno."""
        valores_reales = {
            "Zafiro 1.0": "1039",
            "Rubi": "1048",
            "Zafiro Plus": "1078",
            "Jade": "1053",
            "Diamante -": "1206",
            "Diamante +": "1201",
            "Oro": "1082",
        }
        observaciones = [
            ObservacionTasa(prototipo_clave=clave, numerador=Decimal(valor), divisor=Decimal(1))
            for clave, valor in valores_reales.items()
        ]
        resultado = calcular_tasa(observaciones)
        assert resultado.n == 7
        assert resultado.tasa == Decimal("1101.000000")
        # El skill redondea a un decimal ("CV 6.0%"); aquí se compara con
        # esa misma precisión para no exigir más de lo que la fuente trae.
        assert round(resultado.dispersion, 1) == Decimal("6.0")

    def test_la_dispersion_es_poblacional_no_de_muestra(self) -> None:
        """Mismo caso que arriba: con desviación de muestra (n-1) el CV
        saldría 6.52%, no 6.0% — la diferencia que decidió esta regla."""
        valores = ["1039", "1048", "1078", "1053", "1206", "1201", "1082"]
        observaciones = [
            ObservacionTasa(prototipo_clave=f"P{i}", numerador=Decimal(v), divisor=Decimal(1))
            for i, v in enumerate(valores)
        ]
        resultado = calcular_tasa(observaciones)
        assert resultado.dispersion != Decimal("6.5151")
        assert round(resultado.dispersion, 1) == Decimal("6.0")

    def test_dos_tasas_iguales_dan_dispersion_cero(self) -> None:
        observaciones = [
            ObservacionTasa(prototipo_clave="A", numerador=Decimal(100), divisor=Decimal(1)),
            ObservacionTasa(prototipo_clave="B", numerador=Decimal(100), divisor=Decimal(1)),
        ]
        resultado = calcular_tasa(observaciones)
        assert resultado.tasa == Decimal("100.000000")
        assert resultado.dispersion == Decimal("0.0000")

    def test_los_prototipos_vienen_ordenados_y_sin_depender_del_orden_de_entrada(self) -> None:
        a = ObservacionTasa(prototipo_clave="ZZZ", numerador=Decimal(10), divisor=Decimal(1))
        b = ObservacionTasa(prototipo_clave="AAA", numerador=Decimal(20), divisor=Decimal(1))
        assert calcular_tasa([a, b]).prototipos == ("AAA", "ZZZ")


class TestRecetaPorConcepto:
    """CASA-A del fixture de arriba: 2 recámaras (MURO×4, PISO×1) + losa suelta."""

    composicion = TestExplosionDeCosto.composicion

    def test_suma_la_cantidad_de_un_concepto_repetido_por_dos_caminos(self) -> None:
        calculada = explotar_ensamble(
            "CASA-A", composiciones=self.composicion, precios_concepto=_PRECIOS
        )
        receta = receta_por_concepto(calculada.lineas)

        assert receta["EST-MURO"] == ValorPartida(
            cantidad=Decimal("8"), precio_unitario=Decimal("100")
        )
        assert receta["EST-PISO"] == ValorPartida(
            cantidad=Decimal("2"), precio_unitario=Decimal("50")
        )
        assert receta["EST-LOSA"] == ValorPartida(
            cantidad=Decimal("1"), precio_unitario=Decimal("200")
        )

    def test_no_incluye_lineas_de_sub_ensamble(self) -> None:
        calculada = explotar_ensamble(
            "CASA-A", composiciones=self.composicion, precios_concepto=_PRECIOS
        )
        receta = receta_por_concepto(calculada.lineas)
        assert "RECAMARA-A" not in receta


class TestReconciliarGeneracion:
    def test_concepto_sin_partida_previa_es_nuevo(self) -> None:
        resultado = reconciliar_generacion(
            receta={"EST-MURO": ValorPartida(Decimal(8), Decimal(100))},
            existentes={},
        )
        assert [r.estado for r in resultado] == [EstadoRenglonGenerado.NUEVO]
        assert resultado[0].existente is None

    def test_partida_sin_tocar_desde_que_se_generó_se_actualiza(self) -> None:
        snapshot = ValorPartida(Decimal(8), Decimal(100))
        resultado = reconciliar_generacion(
            receta={"EST-MURO": ValorPartida(Decimal(10), Decimal(105))},
            existentes={
                "EST-MURO": PartidaExistente(actual=snapshot, snapshot=snapshot)
            },
        )
        assert [r.estado for r in resultado] == [EstadoRenglonGenerado.ACTUALIZADO]

    def test_partida_editada_a_mano_se_marca_desvinculada(self) -> None:
        snapshot = ValorPartida(Decimal(8), Decimal(100))
        editada = ValorPartida(Decimal(9), Decimal(100))  # el usuario cambió la cantidad
        resultado = reconciliar_generacion(
            receta={"EST-MURO": ValorPartida(Decimal(8), Decimal(100))},
            existentes={
                "EST-MURO": PartidaExistente(actual=editada, snapshot=snapshot)
            },
        )
        assert [r.estado for r in resultado] == [EstadoRenglonGenerado.DESVINCULADO]
        assert resultado[0].existente is not None
        assert resultado[0].existente.actual == editada

    def test_partida_capturada_sin_snapshot_es_conflicto_no_desvinculado(self) -> None:
        """Una partida que coincide en concepto pero nunca la generó ningún
        ensamble (capturada a mano) no es lo mismo que una editada después
        de generarse: no se sabe si es "la misma cosa"."""
        capturada = ValorPartida(Decimal(8), Decimal(100))
        resultado = reconciliar_generacion(
            receta={"EST-MURO": ValorPartida(Decimal(8), Decimal(100))},
            existentes={
                "EST-MURO": PartidaExistente(actual=capturada, snapshot=None)
            },
        )
        assert [r.estado for r in resultado] == [EstadoRenglonGenerado.CONFLICTO]

    def test_concepto_que_ya_no_esta_en_la_receta_sobra_y_no_se_borra_sola(self) -> None:
        snapshot = ValorPartida(Decimal(1), Decimal(200))
        resultado = reconciliar_generacion(
            receta={},
            existentes={
                "EST-LOSA": PartidaExistente(actual=snapshot, snapshot=snapshot)
            },
        )
        assert [r.estado for r in resultado] == [EstadoRenglonGenerado.SOBRA]
        assert resultado[0].receta is None

    def test_clasifica_varios_conceptos_a_la_vez_y_ordena_por_clave(self) -> None:
        snapshot_piso = ValorPartida(Decimal(2), Decimal(50))
        resultado = reconciliar_generacion(
            receta={
                "EST-MURO": ValorPartida(Decimal(8), Decimal(100)),  # nuevo
                "EST-PISO": ValorPartida(Decimal(2), Decimal(50)),  # actualizado
            },
            existentes={
                "EST-PISO": PartidaExistente(actual=snapshot_piso, snapshot=snapshot_piso),
                "EST-LOSA": PartidaExistente(  # sobra
                    actual=ValorPartida(Decimal(1), Decimal(200)),
                    snapshot=ValorPartida(Decimal(1), Decimal(200)),
                ),
            },
        )
        assert [(r.clave_concepto, r.estado) for r in resultado] == [
            ("EST-LOSA", EstadoRenglonGenerado.SOBRA),
            ("EST-MURO", EstadoRenglonGenerado.NUEVO),
            ("EST-PISO", EstadoRenglonGenerado.ACTUALIZADO),
        ]
