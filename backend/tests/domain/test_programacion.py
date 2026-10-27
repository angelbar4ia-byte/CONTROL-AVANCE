"""Reglas del contexto Programación (§7.5, §11.2).

`test_cpm.py` prueba el motor puro sobre `NodoCPM`; esto prueba lo que hay
alrededor: cómo la plantilla del prototipo baja al cronograma de una obra
(`instanciar_programa`), cómo se ajusta una actividad a mano
(`editar_programacion`) y que el grafo que se le entrega al motor
(`nodos_cpm`) sea el correcto —incluidos el ciclo, la holgura y la
criticidad medidas de punta a punta desde una `ActividadProgramable`.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from obractrl.domain.programacion.cpm import (
    CicloEnGrafoError,
    Dependencia,
    TipoDependencia,
    Tramo,
    calcular_cpm,
)
from obractrl.domain.programacion.reglas import (
    CAMPOS_DE_ESTRUCTURA,
    CAMPOS_DE_FECHAS,
    ActividadProgramable,
    EdicionDeProgramaNoPermitida,
    ErrorDeProgramacion,
    ItemProgramaBase,
    editar_programacion,
    exigir_permiso_de_edicion,
    instanciar_programa,
    item_aplicable,
    nodos_cpm,
    validar_item_base,
)
from obractrl.domain.shared.diccionario import Rol

INICIO = date(2026, 3, 2)  # lunes

# El muro del jefe de obra: dos semanas, pausa para la losa, y los pretiles.
# 14 días de trabajo en 19 de calendario.
MURO = (Tramo(duracion_dias=10), Tramo(duracion_dias=4, offset_dias=15))

# El programa base habla en nodos del prototipo; el cronograma, en ids de
# actividad. Los dos juegos de ids se nombran distinto a propósito: si la
# traducción no ocurriera, las pruebas lo notarían.
NODO_A, NODO_B, NODO_C = "nodo-a", "nodo-b", "nodo-c"
ACT_A, ACT_B, ACT_C = "act-a", "act-b", "act-c"
ETAPA = "etapa-cimentacion"


def _actividades() -> list[ActividadProgramable]:
    """Tres actividades generadas desde tres nodos del prototipo (§11.3 A.2)."""
    return [
        ActividadProgramable(id=ACT_A, prototipo_nodo_id=NODO_A, etapa_id=ETAPA),
        ActividadProgramable(id=ACT_B, prototipo_nodo_id=NODO_B, etapa_id=ETAPA),
        ActividadProgramable(id=ACT_C, prototipo_nodo_id=NODO_C, etapa_id=ETAPA),
    ]


def _plantilla() -> list[ItemProgramaBase]:
    """A(5) -> B(6) -> nada; C(2) cuelga de A. La rama C queda holgada."""
    return [
        ItemProgramaBase(duracion_dias=Decimal(5), prototipo_nodo_id=NODO_A, orden=0),
        ItemProgramaBase(
            duracion_dias=Decimal(6),
            prototipo_nodo_id=NODO_B,
            dependencias=(Dependencia(NODO_A),),
            orden=1,
        ),
        ItemProgramaBase(
            duracion_dias=Decimal(2),
            prototipo_nodo_id=NODO_C,
            dependencias=(Dependencia(NODO_A),),
            orden=2,
        ),
    ]


class TestValidarItemBase:
    def test_duracion_no_positiva_se_rechaza(self) -> None:
        with pytest.raises(ErrorDeProgramacion, match="positiva"):
            validar_item_base(
                ItemProgramaBase(duracion_dias=Decimal(0), prototipo_nodo_id=NODO_A)
            )

    def test_item_sin_destino_se_rechaza(self) -> None:
        with pytest.raises(ErrorDeProgramacion, match="nodo del prototipo"):
            validar_item_base(ItemProgramaBase(duracion_dias=Decimal(3)))

    def test_item_que_depende_de_si_mismo_se_rechaza(self) -> None:
        with pytest.raises(ErrorDeProgramacion, match="sí mismo"):
            validar_item_base(
                ItemProgramaBase(
                    duracion_dias=Decimal(3),
                    prototipo_nodo_id=NODO_A,
                    dependencias=(Dependencia(NODO_A),),
                )
            )


class TestValidarTramos:
    """Invariantes de la interrupción de una actividad (§7.6)."""

    def _item(self, tramos: tuple[Tramo, ...], duracion: int = 14) -> ItemProgramaBase:
        return ItemProgramaBase(
            duracion_dias=Decimal(duracion),
            prototipo_nodo_id=NODO_A,
            tramos=tramos,
        )

    def test_el_muro_partido_es_valido(self) -> None:
        item = validar_item_base(self._item(MURO))
        assert item.tramos == MURO
        assert item.duracion_dias == Decimal(14)

    def test_tramos_traslapados_se_rechazan(self) -> None:
        traslapados = (
            Tramo(duracion_dias=10),
            Tramo(duracion_dias=4, offset_dias=8),  # el primero cierra en el 10
        )
        with pytest.raises(ErrorDeProgramacion, match="traslapan"):
            validar_item_base(self._item(traslapados))

    def test_tramos_desordenados_se_rechazan(self) -> None:
        """Desordenar es un caso particular de traslape hacia atrás: el
        dominio no reordena, porque un orden que el cliente no capturó no es
        algo que se deba adivinar."""
        al_reves = (
            Tramo(duracion_dias=4),
            Tramo(duracion_dias=10, offset_dias=0),
        )
        with pytest.raises(ErrorDeProgramacion, match="traslapan"):
            validar_item_base(self._item(al_reves))

    @pytest.mark.parametrize("duracion", [0, -3])
    def test_tramo_de_duracion_no_positiva_se_rechaza(self, duracion: float) -> None:
        tramos = (
            Tramo(duracion_dias=10),
            Tramo(duracion_dias=duracion, offset_dias=15),
        )
        with pytest.raises(ErrorDeProgramacion, match="duración de un tramo"):
            validar_item_base(self._item(tramos, duracion=10 + int(duracion)))

    def test_offset_negativo_se_rechaza(self) -> None:
        tramos = (Tramo(duracion_dias=10), Tramo(duracion_dias=4, offset_dias=-1))
        with pytest.raises(ErrorDeProgramacion, match="no puede ser negativo"):
            validar_item_base(self._item(tramos))

    def test_el_primer_tramo_arranca_en_cero(self) -> None:
        """Un hueco por delante no es interrupción: es empezar más tarde, y
        eso se dice con el lag de la dependencia."""
        tramos = (
            Tramo(duracion_dias=10, offset_dias=3),
            Tramo(duracion_dias=4, offset_dias=18),
        )
        with pytest.raises(ErrorDeProgramacion, match="no es una interrupción"):
            validar_item_base(self._item(tramos))

    def test_la_duracion_debe_ser_la_suma_de_los_tramos(self) -> None:
        """El span (19) no es la duración: los días de trabajo son 14."""
        with pytest.raises(ErrorDeProgramacion, match="suman 14"):
            validar_item_base(self._item(MURO, duracion=19))

    def test_un_solo_tramo_colapsa_a_ninguno(self) -> None:
        item = validar_item_base(
            self._item((Tramo(duracion_dias=14),), duracion=14)
        )
        assert item.tramos == ()

    def test_sin_tramos_nada_cambia(self) -> None:
        item = ItemProgramaBase(duracion_dias=Decimal(5), prototipo_nodo_id=NODO_A)
        assert validar_item_base(item) is item


class TestItemAplicable:
    def test_gana_el_item_del_nodo_exacto(self) -> None:
        por_etapa = ItemProgramaBase(duracion_dias=Decimal(9), etapa_id=ETAPA)
        items = [por_etapa, *_plantilla()]
        elegido = item_aplicable(NODO_A, ETAPA, items)
        assert elegido is not None
        assert elegido.duracion_dias == Decimal(5)

    def test_cae_al_item_de_la_etapa(self) -> None:
        por_etapa = ItemProgramaBase(duracion_dias=Decimal(9), etapa_id=ETAPA)
        elegido = item_aplicable("nodo-sin-plantilla", ETAPA, [por_etapa])
        assert elegido is por_etapa

    def test_sin_coincidencia_no_hay_item(self) -> None:
        assert item_aplicable("nodo-x", "otra-etapa", _plantilla()) is None


class TestInstanciarPrograma:
    def test_baja_las_duraciones_de_la_plantilla(self) -> None:
        resultado = instanciar_programa(
            actividades=_actividades(), items=_plantilla()
        )
        por_id = {p.actividad_id: p for p in resultado.actividades}
        assert por_id[ACT_A].duracion_dias == Decimal(5)
        assert por_id[ACT_B].duracion_dias == Decimal(6)
        assert por_id[ACT_C].duracion_dias == Decimal(2)

    def test_traduce_los_refs_del_prototipo_a_ids_de_actividad(self) -> None:
        """Es lo que el workflow A dejó pendiente: sin esto el motor ignora
        todas las dependencias y el cronograma sale plano (§11.3 A.2)."""
        resultado = instanciar_programa(
            actividades=_actividades(), items=_plantilla()
        )
        por_id = {p.actividad_id: p for p in resultado.actividades}
        assert [d.ref for d in por_id[ACT_B].dependencias] == [ACT_A]
        assert [d.ref for d in por_id[ACT_C].dependencias] == [ACT_A]
        assert resultado.refs_no_resueltas == ()

    def test_conserva_tipo_y_lag_al_traducir(self) -> None:
        items = [
            ItemProgramaBase(duracion_dias=Decimal(5), prototipo_nodo_id=NODO_A),
            ItemProgramaBase(
                duracion_dias=Decimal(3),
                prototipo_nodo_id=NODO_B,
                dependencias=(
                    Dependencia(
                        NODO_A, tipo=TipoDependencia.INICIO_INICIO, lag_dias=2
                    ),
                ),
            ),
        ]
        resultado = instanciar_programa(actividades=_actividades(), items=items)
        dep = next(
            p for p in resultado.actividades if p.actividad_id == ACT_B
        ).dependencias[0]
        assert dep.ref == ACT_A
        assert dep.tipo == TipoDependencia.INICIO_INICIO
        assert dep.lag_dias == 2

    def test_actividad_sin_item_conserva_su_programacion(self) -> None:
        """Reinstanciar no debe borrar los ajustes manuales de lo que la
        plantilla no cubre (§11.2 `PATCH`)."""
        actividades = [
            *_actividades(),
            ActividadProgramable(
                id="act-extra",
                prototipo_nodo_id="nodo-extra",
                etapa_id="etapa-ajena",
                duracion_dias=Decimal(7),
            ),
        ]
        resultado = instanciar_programa(actividades=actividades, items=_plantilla())
        extra = next(
            p for p in resultado.actividades if p.actividad_id == "act-extra"
        )
        assert extra.duracion_dias == Decimal(7)
        assert resultado.sin_item == ("act-extra",)

    def test_ref_que_no_es_actividad_de_la_obra_se_reporta(self) -> None:
        items = [
            ItemProgramaBase(
                duracion_dias=Decimal(4),
                prototipo_nodo_id=NODO_A,
                dependencias=(Dependencia("nodo-fantasma"),),
            )
        ]
        resultado = instanciar_programa(actividades=_actividades(), items=items)
        assert resultado.refs_no_resueltas == ("nodo-fantasma",)

    def test_frente_de_la_plantilla_no_borra_el_de_la_actividad(self) -> None:
        actividades = [
            ActividadProgramable(
                id=ACT_A, prototipo_nodo_id=NODO_A, frente_id="frente-albanileria"
            )
        ]
        items = [ItemProgramaBase(duracion_dias=Decimal(4), prototipo_nodo_id=NODO_A)]
        resultado = instanciar_programa(actividades=actividades, items=items)
        assert resultado.actividades[0].frente_id == "frente-albanileria"

    def test_autodependencia_se_rechaza(self) -> None:
        items = [
            ItemProgramaBase(
                duracion_dias=Decimal(4),
                prototipo_nodo_id=NODO_A,
                dependencias=(Dependencia(NODO_A),),
            )
        ]
        with pytest.raises(ErrorDeProgramacion, match="sí mism"):
            instanciar_programa(actividades=_actividades(), items=items)

    def test_sin_actividades_no_hay_nada_que_programar(self) -> None:
        with pytest.raises(ErrorDeProgramacion, match="genérala desde su prototipo"):
            instanciar_programa(actividades=[], items=_plantilla())

    def test_sin_plantilla_vigente_se_rechaza(self) -> None:
        with pytest.raises(ErrorDeProgramacion, match="programa base vigente"):
            instanciar_programa(actividades=_actividades(), items=[])


class TestTramosEnLaInstanciacion:
    """La interrupción viaja del prototipo a la obra (§7.5 → §7.6)."""

    def _plantilla_con_muro(self) -> list[ItemProgramaBase]:
        """MURO(14 de trabajo, 19 de span) -> APLANADO; LOSA en el hueco."""
        return [
            ItemProgramaBase(
                duracion_dias=Decimal(14),
                prototipo_nodo_id=NODO_A,
                tramos=MURO,
                orden=0,
            ),
            ItemProgramaBase(
                duracion_dias=Decimal(5),
                prototipo_nodo_id=NODO_B,
                dependencias=(
                    Dependencia(
                        NODO_A, tipo=TipoDependencia.INICIO_INICIO, lag_dias=10
                    ),
                ),
                orden=1,
            ),
            ItemProgramaBase(
                duracion_dias=Decimal(3),
                prototipo_nodo_id=NODO_C,
                dependencias=(Dependencia(NODO_A),),
                orden=2,
            ),
        ]

    def test_los_tramos_bajan_a_la_actividad(self) -> None:
        resultado = instanciar_programa(
            actividades=_actividades(), items=self._plantilla_con_muro()
        )
        por_id = {p.actividad_id: p for p in resultado.actividades}
        assert por_id[ACT_A].tramos == MURO
        assert por_id[ACT_A].duracion_dias == Decimal(14)
        assert por_id[ACT_B].tramos == ()

    def test_la_actividad_sin_item_conserva_sus_tramos(self) -> None:
        actividades = [
            *_actividades(),
            ActividadProgramable(
                id="act-extra",
                prototipo_nodo_id="nodo-extra",
                etapa_id="etapa-ajena",
                duracion_dias=Decimal(14),
                tramos=MURO,
            ),
        ]
        resultado = instanciar_programa(
            actividades=actividades, items=self._plantilla_con_muro()
        )
        extra = next(
            p for p in resultado.actividades if p.actividad_id == "act-extra"
        )
        assert extra.tramos == MURO

    def test_el_caso_del_jefe_de_obra_de_punta_a_punta(self) -> None:
        """Muro (2 semanas) → pausa para la losa → pretiles, instanciado.

        El muro es UNA actividad: 317 m² de tabique, 14 días de trabajo, un
        avance. La losa se cuela en la pausa y el aplanado —que sí depende del
        muro terminado— espera al ÚLTIMO tramo, no al primero.
        """
        instanciado = instanciar_programa(
            actividades=_actividades(), items=self._plantilla_con_muro()
        )
        por_id = {p.actividad_id: p for p in instanciado.actividades}
        r = calcular_cpm(
            nodos_cpm(_actividades(), por_id), INICIO, fecha_corte=INICIO
        )

        assert r[ACT_A].fin_temprano == date(2026, 3, 21)   # 2 de marzo + 19
        assert r[ACT_B].inicio_temprano == date(2026, 3, 12)  # +10, en el hueco
        assert r[ACT_B].fin_temprano == date(2026, 3, 17)   # cierra antes del 21
        assert r[ACT_C].inicio_temprano == date(2026, 3, 21)  # el último tramo
        # La losa cabe entera en la pausa, así que no es ella la que manda.
        assert r[ACT_A].es_critica
        assert not r[ACT_B].es_critica

    def test_los_tramos_no_cambian_los_dias_de_trabajo(self) -> None:
        """Lo que factura el destajo y consume recursos son los 14, no los 19."""
        resultado = instanciar_programa(
            actividades=_actividades(), items=self._plantilla_con_muro()
        )
        por_id = {p.actividad_id: p for p in resultado.actividades}
        assert por_id[ACT_A].duracion_dias == Decimal(14)
        assert nodos_cpm(_actividades(), por_id)[0].duracion_dias == 14.0
        assert nodos_cpm(_actividades(), por_id)[0].span == 19.0


class TestArranqueFijoEnLaInstanciacion:
    """El ancla viaja del prototipo a la obra, igual que los tramos (0043)."""

    def _con_ancla(self) -> list[ItemProgramaBase]:
        items = _plantilla()
        items[2] = replace(items[2], inicio_dias=Decimal(30))
        return items

    def test_el_ancla_del_item_baja_a_la_actividad(self) -> None:
        resultado = instanciar_programa(actividades=_actividades(), items=self._con_ancla())
        por_id = {p.actividad_id: p for p in resultado.actividades}
        assert por_id[ACT_C].inicio_dias == Decimal(30)
        assert por_id[ACT_A].inicio_dias is None

    def test_el_ancla_llega_al_motor(self) -> None:
        resultado = instanciar_programa(actividades=_actividades(), items=self._con_ancla())
        por_id = {p.actividad_id: p for p in resultado.actividades}
        nodos = {n.ref: n for n in nodos_cpm(_actividades(), por_id)}
        assert nodos[ACT_C].inicio_dias == 30.0
        assert nodos[ACT_A].inicio_dias is None

    def test_una_plantilla_sin_ancla_no_desclava_lo_que_la_obra_tenia(self) -> None:
        # Mismo criterio que `frente_id`: lo que la plantilla no trae, no
        # borra. Alguien clavó esta actividad en ESTA obra a propósito.
        actividades = _actividades()
        actividades[0] = replace(actividades[0], inicio_dias=Decimal(12))
        resultado = instanciar_programa(actividades=actividades, items=_plantilla())
        por_id = {p.actividad_id: p for p in resultado.actividades}
        assert por_id[ACT_A].inicio_dias == Decimal(12)

    def test_el_ancla_de_la_plantilla_pisa_a_la_de_la_obra(self) -> None:
        actividades = _actividades()
        actividades[2] = replace(actividades[2], inicio_dias=Decimal(12))
        resultado = instanciar_programa(actividades=actividades, items=self._con_ancla())
        por_id = {p.actividad_id: p for p in resultado.actividades}
        assert por_id[ACT_C].inicio_dias == Decimal(30)


class TestCicloEnDependencias:
    def test_el_cronograma_instanciado_ciclico_revienta_en_el_motor(self) -> None:
        """El ciclo se detecta sobre el grafo ya traducido: es la garantía de
        que `POST /obras/{id}/programa` aborta antes de escribir (§6)."""
        items = [
            ItemProgramaBase(
                duracion_dias=Decimal(3),
                prototipo_nodo_id=NODO_A,
                dependencias=(Dependencia(NODO_B),),
            ),
            ItemProgramaBase(
                duracion_dias=Decimal(3),
                prototipo_nodo_id=NODO_B,
                dependencias=(Dependencia(NODO_A),),
            ),
        ]
        resultado = instanciar_programa(actividades=_actividades(), items=items)
        por_id = {p.actividad_id: p for p in resultado.actividades}

        with pytest.raises(CicloEnGrafoError) as exc:
            calcular_cpm(nodos_cpm(_actividades(), por_id), INICIO)

        assert {ACT_A, ACT_B} <= set(exc.value.involucradas)


class TestHolguraYCriticidad:
    def _resultados(self) -> dict:
        instanciado = instanciar_programa(
            actividades=_actividades(), items=_plantilla()
        )
        por_id = {p.actividad_id: p for p in instanciado.actividades}
        return calcular_cpm(
            nodos_cpm(_actividades(), por_id), INICIO, fecha_corte=INICIO
        )

    def test_la_rama_larga_es_la_ruta_critica(self) -> None:
        resultados = self._resultados()
        criticas = {ref for ref, r in resultados.items() if r.es_critica}
        assert criticas == {ACT_A, ACT_B}

    def test_la_rama_corta_tiene_holgura(self) -> None:
        resultados = self._resultados()
        # C dura 2 y su rama compite contra B, que dura 6: 4 días de holgura.
        assert resultados[ACT_C].holgura == 4
        assert not resultados[ACT_C].es_critica

    def test_las_fechas_salen_de_la_duracion_instanciada(self) -> None:
        resultados = self._resultados()
        assert resultados[ACT_A].fin_temprano == date(2026, 3, 7)  # +5
        assert resultados[ACT_B].fin_temprano == date(2026, 3, 13)  # +5+6


class TestNodosCPM:
    def test_sin_programacion_propuesta_usa_lo_que_trae_la_actividad(self) -> None:
        actividades = [
            ActividadProgramable(
                id=ACT_A,
                duracion_dias=Decimal(8),
                dependencias=(Dependencia(ACT_B),),
            )
        ]
        nodo = nodos_cpm(actividades)[0]
        assert nodo.duracion_dias == 8.0
        assert nodo.dependencias[0].ref == ACT_B

    def test_la_fecha_real_solo_cuenta_si_la_actividad_esta_concluida(self) -> None:
        """Antes del 100% `fecha_termino` es la planeada, y usarla como real
        invalidaría el desfase (§6)."""
        en_curso = ActividadProgramable(
            id=ACT_A,
            avance_pct=Decimal(50),
            fecha_termino=date(2026, 3, 20),
        )
        concluida = ActividadProgramable(
            id=ACT_B,
            avance_pct=Decimal(100),
            fecha_termino=date(2026, 3, 20),
        )
        nodos = nodos_cpm([en_curso, concluida])
        assert nodos[0].fecha_real_termino is None
        assert nodos[1].fecha_real_termino == date(2026, 3, 20)


class TestEditarProgramacion:
    def _actual(self) -> ActividadProgramable:
        return ActividadProgramable(
            id=ACT_B,
            duracion_dias=Decimal(6),
            dependencias=(Dependencia(ACT_A),),
            frente_id="frente-1",
            fecha_inicio=date(2026, 3, 9),
        )

    def test_solo_cambia_lo_que_llega(self) -> None:
        nueva = editar_programacion(self._actual(), duracion_dias=Decimal(4))
        assert nueva.duracion_dias == Decimal(4)
        assert [d.ref for d in nueva.dependencias] == [ACT_A]
        assert nueva.frente_id == "frente-1"
        assert nueva.fecha_inicio == date(2026, 3, 9)

    def test_lista_vacia_deja_la_actividad_sin_predecesoras(self) -> None:
        nueva = editar_programacion(self._actual(), dependencias=[])
        assert nueva.dependencias == ()

    def test_duracion_no_positiva_se_rechaza(self) -> None:
        with pytest.raises(ErrorDeProgramacion, match="positiva"):
            editar_programacion(self._actual(), duracion_dias=Decimal(0))

    def test_autodependencia_se_rechaza(self) -> None:
        with pytest.raises(ErrorDeProgramacion, match="sí misma"):
            editar_programacion(
                self._actual(),
                dependencias=[Dependencia(ACT_B)],
                refs_de_la_obra=frozenset({ACT_A, ACT_B}),
            )

    def test_dependencia_fuera_de_la_obra_se_rechaza(self) -> None:
        with pytest.raises(ErrorDeProgramacion, match="no es una actividad de esta"):
            editar_programacion(
                self._actual(),
                dependencias=[Dependencia("act-de-otra-obra")],
                refs_de_la_obra=frozenset({ACT_A, ACT_B}),
            )

    def test_dependencia_repetida_se_rechaza(self) -> None:
        with pytest.raises(ErrorDeProgramacion, match="repetida"):
            editar_programacion(
                self._actual(),
                dependencias=[Dependencia(ACT_A), Dependencia(ACT_A)],
                refs_de_la_obra=frozenset({ACT_A, ACT_B}),
            )

    def test_fechas_invertidas_se_rechazan(self) -> None:
        with pytest.raises(ErrorDeProgramacion, match="anterior a la de inicio"):
            editar_programacion(
                self._actual(),
                fecha_inicio=date(2026, 3, 10),
                fecha_termino=date(2026, 3, 5),
            )

    def test_partir_una_actividad_deriva_su_duracion_de_los_tramos(self) -> None:
        """El gesto del editor gráfico: se arrastran los pedazos y la duración
        sale de la suma, sin que el cliente la tenga que recalcular."""
        nueva = editar_programacion(self._actual(), tramos=MURO)
        assert nueva.tramos == MURO
        assert nueva.duracion_dias == Decimal(14)

    def test_duracion_en_desacuerdo_con_los_tramos_se_rechaza(self) -> None:
        with pytest.raises(ErrorDeProgramacion, match="suman 14"):
            editar_programacion(
                self._actual(), duracion_dias=Decimal(19), tramos=MURO
            )

    def test_lista_vacia_de_tramos_quita_la_interrupcion(self) -> None:
        partida = ActividadProgramable(
            id=ACT_B, duracion_dias=Decimal(14), tramos=MURO
        )
        nueva = editar_programacion(partida, tramos=[], duracion_dias=Decimal(14))
        assert nueva.tramos == ()
        assert nueva.duracion_dias == Decimal(14)

    def test_sin_mandar_tramos_los_conserva(self) -> None:
        partida = ActividadProgramable(
            id=ACT_B, duracion_dias=Decimal(14), tramos=MURO
        )
        nueva = editar_programacion(partida, frente_id="frente-2")
        assert nueva.tramos == MURO

    def test_cambiar_la_duracion_de_una_actividad_partida_exige_los_tramos(
        self,
    ) -> None:
        """Los 14 días son la suma de los tramos: moverlos a 20 sin decir cómo
        se reparten dejaría la actividad contradiciéndose."""
        partida = ActividadProgramable(
            id=ACT_B, duracion_dias=Decimal(14), tramos=MURO
        )
        with pytest.raises(ErrorDeProgramacion, match="suman 14"):
            editar_programacion(partida, duracion_dias=Decimal(20))

    def test_tramos_traslapados_se_rechazan(self) -> None:
        with pytest.raises(ErrorDeProgramacion, match="traslapan"):
            editar_programacion(
                self._actual(),
                tramos=[
                    Tramo(duracion_dias=10),
                    Tramo(duracion_dias=4, offset_dias=8),
                ],
            )

    def test_una_actividad_sin_tramos_se_edita_igual_que_antes(self) -> None:
        """Regresión: nada de lo anterior cambia para el caso normal."""
        nueva = editar_programacion(self._actual(), duracion_dias=Decimal(4))
        assert nueva.tramos == ()
        assert nueva.duracion_dias == Decimal(4)

    def test_el_ciclo_lo_detecta_el_motor_sobre_el_grafo_completo(self) -> None:
        """Una arista sola no dice nada: hace falta el cronograma entero (§6)."""
        actividades = [
            ActividadProgramable(
                id=ACT_A, duracion_dias=Decimal(3), dependencias=(Dependencia(ACT_B),)
            ),
            ActividadProgramable(id=ACT_B, duracion_dias=Decimal(3)),
        ]
        nueva = editar_programacion(
            actividades[1],
            dependencias=[Dependencia(ACT_A)],
            refs_de_la_obra=frozenset({ACT_A, ACT_B}),
        )
        with pytest.raises(CicloEnGrafoError):
            calcular_cpm(nodos_cpm(actividades, {nueva.actividad_id: nueva}), INICIO)


class TestPermisoDeEdicion:
    """Quién edita qué del programa (MODELO.md §5b): Control la estructura, el
    Residente las fechas."""

    def test_control_y_supervisor_editan_todo(self) -> None:
        for rol in (Rol.CONTROL_OBRA, Rol.SUPERVISOR):
            assert exigir_permiso_de_edicion(rol, ["duracion_dias"]) == "estructura"
            assert exigir_permiso_de_edicion(rol, ["fecha_inicio"]) == "fechas"
            assert (
                exigir_permiso_de_edicion(rol, ["duracion_dias", "fecha_termino"]) == "mixta"
            )

    def test_el_residente_solo_edita_fechas(self) -> None:
        assert (
            exigir_permiso_de_edicion(Rol.RESIDENTE, ["fecha_inicio", "fecha_termino"])
            == "fechas"
        )
        for campo in CAMPOS_DE_ESTRUCTURA:
            with pytest.raises(EdicionDeProgramaNoPermitida, match="solo puede editar las fechas"):
                exigir_permiso_de_edicion(Rol.RESIDENTE, [campo])

    def test_el_residente_no_se_cuela_con_fechas_y_estructura_juntas(self) -> None:
        with pytest.raises(EdicionDeProgramaNoPermitida):
            exigir_permiso_de_edicion(Rol.RESIDENTE, ["fecha_inicio", "duracion_dias"])

    def test_el_super_intendente_no_edita_el_programa(self) -> None:
        with pytest.raises(EdicionDeProgramaNoPermitida):
            exigir_permiso_de_edicion(Rol.SUPER_INTENDENTE, ["fecha_inicio"])

    def test_los_campos_de_estructura_y_de_fechas_no_se_traslapan(self) -> None:
        assert not set(CAMPOS_DE_ESTRUCTURA) & set(CAMPOS_DE_FECHAS)
