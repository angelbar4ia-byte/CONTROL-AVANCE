"""Planeación de actividades desde el prototipo — workflow A (§11.3 A.2)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.obras.generacion import (
    ErrorDeGeneracion,
    ItemProgramaBase,
    NodoPrototipo,
    planear_actividades,
)
from obractrl.domain.programacion.cpm import Dependencia
from obractrl.domain.shared.diccionario import ClaseNodo, ModoPago
from obractrl.domain.shared.valores import Dinero, PrecioUnitario


def _precio(total: str = "1000", destajo: str = "400") -> PrecioUnitario:
    return PrecioUnitario(total=Dinero(total), destajo=Dinero(destajo))


def _arbol() -> list[NodoPrototipo]:
    """Etapa → nivel → dos conceptos, en orden de recorrido (§7.4)."""
    return [
        NodoPrototipo(
            id="n-etapa",
            tipo=ClaseNodo.ETAPA,
            nombre="Cimentación",
            etapa_id="eta-cim",
        ),
        NodoPrototipo(
            id="n-nivel",
            tipo=ClaseNodo.NIVEL,
            nombre="Planta baja",
            parent_id="n-etapa",
            nivel_id="niv-pb",
        ),
        NodoPrototipo(
            id="n-c1",
            tipo=ClaseNodo.CONCEPTO,
            nombre="Zapata corrida",
            parent_id="n-nivel",
            concepto_id="cpt-1",
            cantidad=Decimal("12.5"),
        ),
        NodoPrototipo(
            id="n-c2",
            tipo=ClaseNodo.CONCEPTO,
            nombre="Firme de concreto",
            parent_id="n-nivel",
            concepto_id="cpt-2",
            cantidad=Decimal("40"),
        ),
    ]


_PRECIOS = {"cpt-1": _precio(), "cpt-2": _precio("2500", "900")}


class TestRecorridoDelArbol:
    def test_solo_los_conceptos_se_vuelven_actividad(self) -> None:
        planeadas = planear_actividades(nodos=_arbol(), precios=_PRECIOS)
        assert [p.concepto_id for p in planeadas] == ["cpt-1", "cpt-2"]

    def test_conserva_el_orden_del_arbol(self) -> None:
        planeadas = planear_actividades(nodos=_arbol(), precios=_PRECIOS)
        assert [p.orden for p in planeadas] == [0, 1]
        assert planeadas[0].descripcion == "Zapata corrida"

    def test_hereda_nivel_y_etapa_de_sus_ancestros(self) -> None:
        # El nodo concepto no los trae: los trae la rama (§7.4).
        planeada = planear_actividades(nodos=_arbol(), precios=_PRECIOS)[0]
        assert planeada.nivel_id == "niv-pb"
        assert planeada.etapa_id == "eta-cim"

    def test_el_nodo_propio_gana_sobre_el_ancestro(self) -> None:
        nodos = _arbol()
        nodos[2] = NodoPrototipo(
            id="n-c1",
            tipo=ClaseNodo.CONCEPTO,
            nombre="Zapata corrida",
            parent_id="n-nivel",
            concepto_id="cpt-1",
            cantidad=Decimal("12.5"),
            nivel_id="niv-propio",
        )
        planeada = planear_actividades(nodos=nodos, precios=_PRECIOS)[0]
        assert planeada.nivel_id == "niv-propio"

    def test_cant_base_sale_del_nodo(self) -> None:
        planeadas = planear_actividades(nodos=_arbol(), precios=_PRECIOS)
        assert planeadas[0].cant_base == Decimal("12.5")

    def test_un_padre_ausente_es_arbol_incompleto(self) -> None:
        nodos = [n for n in _arbol() if n.id != "n-nivel"]
        with pytest.raises(ErrorDeGeneracion, match="incompleto"):
            planear_actividades(nodos=nodos, precios=_PRECIOS)

    def test_un_nodo_repetido_revienta(self) -> None:
        nodos = _arbol()
        with pytest.raises(ErrorDeGeneracion, match="dos veces"):
            planear_actividades(nodos=[*nodos, nodos[2]], precios=_PRECIOS)

    def test_un_ciclo_en_el_arbol_revienta(self) -> None:
        nodos = [
            NodoPrototipo(
                id="a", tipo=ClaseNodo.ETAPA, nombre="A", parent_id="b"
            ),
            NodoPrototipo(
                id="b", tipo=ClaseNodo.NIVEL, nombre="B", parent_id="a"
            ),
            NodoPrototipo(
                id="c",
                tipo=ClaseNodo.CONCEPTO,
                nombre="C",
                parent_id="a",
                concepto_id="cpt-1",
                cantidad=Decimal(1),
            ),
        ]
        with pytest.raises(ErrorDeGeneracion, match="ciclo"):
            planear_actividades(nodos=nodos, precios=_PRECIOS)


class TestPrecios:
    def test_toma_el_cpu_vigente(self) -> None:
        planeadas = planear_actividades(nodos=_arbol(), precios=_PRECIOS)
        assert planeadas[0].precio.total == Dinero("1000")
        assert planeadas[0].precio.destajo == Dinero("400")
        assert planeadas[1].precio.total == Dinero("2500")

    def test_sin_cpu_vigente_no_se_genera(self) -> None:
        with pytest.raises(ErrorDeGeneracion, match="CPU vigente"):
            planear_actividades(nodos=_arbol(), precios={"cpt-1": _precio()})

    def test_lista_todos_los_conceptos_sin_precio_de_una_vez(self) -> None:
        with pytest.raises(ErrorDeGeneracion) as exc:
            planear_actividades(nodos=_arbol(), precios={})
        assert "cpt-1" in str(exc.value)
        assert "cpt-2" in str(exc.value)


class TestProgramaBase:
    def test_sin_programa_base_la_duracion_es_uno_y_no_hay_frente(self) -> None:
        planeada = planear_actividades(nodos=_arbol(), precios=_PRECIOS)[0]
        assert planeada.duracion_dias == Decimal(1)
        assert planeada.frente_id is None
        assert planeada.dependencias == ()

    def test_el_item_del_nodo_manda(self) -> None:
        items = [
            ItemProgramaBase(
                duracion_dias=Decimal(5),
                prototipo_nodo_id="n-c1",
                frente_id="fre-cim",
                dependencias=(Dependencia(ref="n-c2", lag_dias=1.0),),
            )
        ]
        planeadas = planear_actividades(
            nodos=_arbol(), precios=_PRECIOS, programa_base=items
        )
        assert planeadas[0].duracion_dias == Decimal(5)
        assert planeadas[0].frente_id == "fre-cim"
        assert planeadas[0].dependencias[0].ref == "n-c2"
        # El segundo concepto no tiene item propio: cae al default.
        assert planeadas[1].duracion_dias == Decimal(1)

    def test_cae_al_item_de_la_etapa_cuando_no_hay_uno_del_nodo(self) -> None:
        items = [
            ItemProgramaBase(
                duracion_dias=Decimal(3), etapa_id="eta-cim", frente_id="fre-cim"
            )
        ]
        planeadas = planear_actividades(
            nodos=_arbol(), precios=_PRECIOS, programa_base=items
        )
        assert [p.duracion_dias for p in planeadas] == [Decimal(3), Decimal(3)]
        assert planeadas[1].frente_id == "fre-cim"

    def test_el_item_del_nodo_gana_sobre_el_de_la_etapa(self) -> None:
        items = [
            ItemProgramaBase(duracion_dias=Decimal(3), etapa_id="eta-cim"),
            ItemProgramaBase(duracion_dias=Decimal(9), prototipo_nodo_id="n-c1"),
        ]
        planeadas = planear_actividades(
            nodos=_arbol(), precios=_PRECIOS, programa_base=items
        )
        assert planeadas[0].duracion_dias == Decimal(9)
        assert planeadas[1].duracion_dias == Decimal(3)


class TestInvariantesDeSalida:
    def test_modo_pago_por_defecto_es_destajo(self) -> None:
        planeada = planear_actividades(nodos=_arbol(), precios=_PRECIOS)[0]
        assert planeada.modo_pago is ModoPago.DESTAJO

    def test_respeta_el_modo_pago_pedido(self) -> None:
        planeadas = planear_actividades(
            nodos=_arbol(), precios=_PRECIOS, modo_pago=ModoPago.CONCEPTO
        )
        assert all(p.modo_pago is ModoPago.CONCEPTO for p in planeadas)

    def test_un_arbol_sin_conceptos_no_genera_nada(self) -> None:
        solo_estructura = [n for n in _arbol() if n.tipo is not ClaseNodo.CONCEPTO]
        with pytest.raises(ErrorDeGeneracion, match="no tiene ningún nodo"):
            planear_actividades(nodos=solo_estructura, precios=_PRECIOS)

    def test_un_nodo_concepto_sin_concepto_revienta(self) -> None:
        nodos = _arbol()
        nodos[2] = NodoPrototipo(
            id="n-c1", tipo=ClaseNodo.CONCEPTO, nombre="Huérfano", parent_id="n-nivel"
        )
        with pytest.raises(ErrorDeGeneracion, match="no apunta a ningún concepto"):
            planear_actividades(nodos=nodos, precios=_PRECIOS)

    def test_cantidad_negativa_revienta(self) -> None:
        nodos = _arbol()
        nodos[2] = NodoPrototipo(
            id="n-c1",
            tipo=ClaseNodo.CONCEPTO,
            nombre="Zapata corrida",
            parent_id="n-nivel",
            concepto_id="cpt-1",
            cantidad=Decimal("-1"),
        )
        with pytest.raises(ErrorDeGeneracion, match="negativa"):
            planear_actividades(nodos=nodos, precios=_PRECIOS)
