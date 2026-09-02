"""Motor de ruta crítica (§6, §7.5)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from obractrl.domain.programacion.cpm import (
    CicloEnGrafoError,
    Dependencia,
    NodoCPM,
    TipoDependencia,
    Tramo,
    actividades_bloqueadas_por,
    calcular_cpm,
)

INICIO = date(2026, 3, 2)  # lunes

FS = TipoDependencia.FIN_INICIO
SS = TipoDependencia.INICIO_INICIO
FF = TipoDependencia.FIN_FIN
SF = TipoDependencia.INICIO_FIN


def _dias(resultado, campo: str) -> int:
    """Días desde `INICIO` de una de las fechas calculadas."""
    return (getattr(resultado, campo) - INICIO).days


def _par(tipo: str, lag: float, *, dur_a: float = 5, dur_b: float = 3) -> dict:
    """A -> B con una sola relación, para leer ES/EF de las dos de un vistazo."""
    nodos = [
        NodoCPM(ref="A", duracion_dias=dur_a),
        NodoCPM(
            ref="B",
            duracion_dias=dur_b,
            dependencias=(Dependencia("A", tipo=tipo, lag_dias=lag),),
        ),
    ]
    return calcular_cpm(nodos, INICIO, fecha_corte=INICIO)


def _cadena() -> list[NodoCPM]:
    """A(5) -> B(3) -> C(2): todo es crítico, no hay holgura."""
    return [
        NodoCPM(ref="A", duracion_dias=5),
        NodoCPM(ref="B", duracion_dias=3, dependencias=(Dependencia("A"),)),
        NodoCPM(ref="C", duracion_dias=2, dependencias=(Dependencia("B"),)),
    ]


def _con_rama_holgada() -> list[NodoCPM]:
    """A(5) -> {B(6), D(2)} -> C. La rama D tiene 4 días de holgura."""
    return [
        NodoCPM(ref="A", duracion_dias=5),
        NodoCPM(ref="B", duracion_dias=6, dependencias=(Dependencia("A"),)),
        NodoCPM(ref="D", duracion_dias=2, dependencias=(Dependencia("A"),)),
        NodoCPM(
            ref="C",
            duracion_dias=2,
            dependencias=(Dependencia("B"), Dependencia("D")),
        ),
    ]


class TestCadenaSimple:
    def test_fechas_tempranas(self) -> None:
        r = calcular_cpm(_cadena(), INICIO, fecha_corte=INICIO)
        assert r["A"].inicio_temprano == INICIO
        assert r["A"].fin_temprano == date(2026, 3, 7)   # +5
        assert r["B"].inicio_temprano == date(2026, 3, 7)
        assert r["C"].fin_temprano == date(2026, 3, 12)  # 5+3+2

    def test_todo_es_critico_sin_ramas(self) -> None:
        r = calcular_cpm(_cadena(), INICIO, fecha_corte=INICIO)
        assert all(n.es_critica for n in r.values())
        assert all(n.holgura == 0 for n in r.values())


class TestHolgura:
    def test_la_rama_corta_tiene_holgura(self) -> None:
        r = calcular_cpm(_con_rama_holgada(), INICIO, fecha_corte=INICIO)
        assert r["D"].holgura == 4
        assert not r["D"].es_critica

    def test_la_rama_larga_es_la_ruta_critica(self) -> None:
        r = calcular_cpm(_con_rama_holgada(), INICIO, fecha_corte=INICIO)
        criticas = {ref for ref, n in r.items() if n.es_critica}
        assert criticas == {"A", "B", "C"}


class TestDependencias:
    def test_lag_empuja_la_sucesora(self) -> None:
        nodos = [
            NodoCPM(ref="A", duracion_dias=5),
            NodoCPM(
                ref="B",
                duracion_dias=3,
                dependencias=(Dependencia("A", lag_dias=2),),
            ),
        ]
        r = calcular_cpm(nodos, INICIO, fecha_corte=INICIO)
        assert r["B"].inicio_temprano == date(2026, 3, 9)  # 5 + 2 de lag

    def test_inicio_inicio_arranca_junto(self) -> None:
        nodos = [
            NodoCPM(ref="A", duracion_dias=5),
            NodoCPM(
                ref="B",
                duracion_dias=3,
                dependencias=(
                    Dependencia("A", tipo=TipoDependencia.INICIO_INICIO),
                ),
            ),
        ]
        r = calcular_cpm(nodos, INICIO, fecha_corte=INICIO)
        assert r["B"].inicio_temprano == INICIO

    def test_ignora_dependencias_a_refs_inexistentes(self) -> None:
        """Un cronograma parcial debe poder calcularse igual."""
        nodos = [NodoCPM(ref="A", duracion_dias=5, dependencias=(Dependencia("FANTASMA"),))]
        r = calcular_cpm(nodos, INICIO, fecha_corte=INICIO)
        assert r["A"].inicio_temprano == INICIO

    def test_ciclo_es_error_explicito(self) -> None:
        nodos = [
            NodoCPM(ref="A", duracion_dias=1, dependencias=(Dependencia("B"),)),
            NodoCPM(ref="B", duracion_dias=1, dependencias=(Dependencia("A"),)),
        ]
        with pytest.raises(CicloEnGrafoError) as exc:
            calcular_cpm(nodos, INICIO)
        assert set(exc.value.involucradas) == {"A", "B"}


class TestLosCuatroTiposDeDependencia:
    """Los cuatro de MS Project, cada uno con lag positivo, cero y negativo.

    Se leen en días desde el arranque (`_dias`) y no en fechas: lo que se
    prueba es la aritmética de la relación, y una fecha concreta la esconde.
    A dura 5 y B dura 3.
    """

    @pytest.mark.parametrize(
        ("lag", "es_b"),
        [(0, 5), (2, 7), (-2, 3)],
    )
    def test_fs_encadena_el_fin_de_a_con_el_inicio_de_b(
        self, lag: float, es_b: int
    ) -> None:
        r = _par(FS, lag)
        assert _dias(r["B"], "inicio_temprano") == es_b

    @pytest.mark.parametrize(
        ("lag", "es_b"),
        [(0, 0), (2, 2), (-2, 0)],  # el lag negativo se clampea al día 0
    )
    def test_ss_encadena_los_dos_inicios(self, lag: float, es_b: int) -> None:
        r = _par(SS, lag)
        assert _dias(r["B"], "inicio_temprano") == es_b

    @pytest.mark.parametrize(
        ("lag", "ef_b"),
        [(0, 5), (2, 7), (-2, 3)],
    )
    def test_ff_encadena_los_dos_fines(self, lag: float, ef_b: int) -> None:
        """`FF` restringe el FIN de la sucesora, así que su inicio retrocede
        tanto como dure ella."""
        r = _par(FF, lag)
        assert _dias(r["B"], "fin_temprano") == ef_b
        assert _dias(r["B"], "inicio_temprano") == max(0, ef_b - 3)

    @pytest.mark.parametrize(
        ("lag", "ef_b"),
        [(0, 3), (4, 4), (-2, 3)],
    )
    def test_sf_ata_el_fin_de_b_al_inicio_de_a(self, lag: float, ef_b: int) -> None:
        """`SF`: B no termina antes de que A arranque. Con A en el día 0 la
        restricción casi siempre queda floja y B arranca en 0 —salvo con lag
        positivo, que sí la aprieta."""
        r = _par(SF, lag)
        assert _dias(r["B"], "fin_temprano") == ef_b

    def test_ff_con_lag_cero_termina_las_dos_el_mismo_dia(self) -> None:
        r = _par(FF, 0)
        assert r["A"].fin_temprano == r["B"].fin_temprano

    def test_un_tipo_desconocido_se_trata_como_fs(self) -> None:
        """El jsonb es histórico y puede traer basura; el default del esquema
        es `FS` y el motor no debe reventar por un tipo que no conoce."""
        r = _par("XX", 0)
        assert _dias(r["B"], "inicio_temprano") == 5


class TestHolguraYCriticidadConFFySF:
    def test_ff_a_secas_deja_las_dos_criticas(self) -> None:
        r = _par(FF, 0)
        assert r["A"].holgura == 0
        assert r["B"].holgura == 0
        assert r["A"].es_critica and r["B"].es_critica

    def test_sf_deja_holgada_a_la_sucesora_corta(self) -> None:
        """B solo debe terminar después de que A arranque: le sobra todo el
        resto del proyecto."""
        r = _par(SF, 0)
        assert r["A"].holgura == 0
        assert r["B"].holgura == 2  # B ocupa 3 de los 5 días del proyecto
        assert not r["B"].es_critica

    def test_ff_con_lag_negativo_no_le_inventa_holgura_a_la_predecesora(self) -> None:
        """A marca el fin del proyecto (5 días contra los 3 de B).

        Un `FF` de −2 permite que A termine DESPUÉS que B, así que la
        restricción de la sucesora no acota a A: si el backward pass no
        acotara además con el fin del proyecto, A saldría con holgura 2 y
        dejaría de ser crítica siendo la que fija la fecha final.
        """
        r = _par(FF, -2)
        assert _dias(r["A"], "fin_temprano") == 5
        assert r["A"].holgura == 0
        assert r["A"].es_critica

    def test_ff_alarga_la_ruta_critica_por_la_sucesora(self) -> None:
        """B(9) con FF sobre A(5): B manda y arrastra a A a ser crítica."""
        r = _par(FF, 0, dur_a=5, dur_b=9)
        assert _dias(r["B"], "inicio_temprano") == 0
        assert _dias(r["B"], "fin_temprano") == 9
        # A puede correrse hasta terminar en el 9: cuatro días de holgura.
        assert r["A"].holgura == 4
        assert not r["A"].es_critica

    def test_par_ss_ff_amarra_a_la_sucesora_de_punta_a_punta(self) -> None:
        """Dos relaciones sobre la MISMA predecesora.

        Es como se modela la actividad que acompaña a otra: arranca con ella
        (`SS`) y termina con ella (`FF`). El backward pass tiene que mirar las
        dos aristas; quedarse con la primera le dejaría a A un LS que no
        corresponde a su ES y una holgura negativa inventada.
        """
        nodos = [
            NodoCPM(ref="A", duracion_dias=6),
            NodoCPM(
                ref="B",
                duracion_dias=6,
                dependencias=(
                    Dependencia("A", tipo=SS),
                    Dependencia("A", tipo=FF),
                ),
            ),
        ]
        r = calcular_cpm(nodos, INICIO, fecha_corte=INICIO)
        assert _dias(r["B"], "inicio_temprano") == 0
        assert _dias(r["B"], "fin_temprano") == 6
        assert r["A"].holgura == 0
        assert r["B"].holgura == 0


class TestArranqueFijo:
    """`inicio_dias`: el ancla gana sobre las predecesoras (§7.5, 0043).

    Es el "Debe comenzar el" de MS Project. La diferencia con un piso —"no
    comenzar antes del"— se ve cuando la predecesora crece: con piso empujaría
    a la sucesora, con ancla no.
    """

    def test_sin_ancla_nada_cambia(self) -> None:
        # No-regresión: el caso de siempre sigue derivando el arranque.
        r = _par(FS, 0)
        assert _dias(r["B"], "inicio_temprano") == 5

    def test_el_ancla_mueve_una_actividad_sin_predecesoras(self) -> None:
        # Lo que antes no se podía expresar: A no depende de nadie y arranca
        # el día 3 porque alguien lo decidió.
        r = calcular_cpm(
            [NodoCPM(ref="A", duracion_dias=5, inicio_dias=3)],
            INICIO,
            fecha_corte=INICIO,
        )
        assert _dias(r["A"], "inicio_temprano") == 3
        assert _dias(r["A"], "fin_temprano") == 8

    @pytest.mark.parametrize("tipo", [FS, SS, FF, SF])
    def test_el_ancla_gana_sobre_las_cuatro_ligas(self, tipo: str) -> None:
        nodos = [
            NodoCPM(ref="A", duracion_dias=5),
            NodoCPM(
                ref="B",
                duracion_dias=3,
                dependencias=(Dependencia("A", tipo=tipo),),
                inicio_dias=2,
            ),
        ]
        r = calcular_cpm(nodos, INICIO, fecha_corte=INICIO)
        assert _dias(r["B"], "inicio_temprano") == 2

    def test_alargar_la_predecesora_no_arrastra_a_la_anclada(self) -> None:
        # La prueba que separa el ancla del piso: con `max(es, ancla)` B se
        # habría ido al día 9.
        def corrida(dur_a: float) -> int:
            nodos = [
                NodoCPM(ref="A", duracion_dias=dur_a),
                NodoCPM(
                    ref="B",
                    duracion_dias=3,
                    dependencias=(Dependencia("A"),),
                    inicio_dias=6,
                ),
            ]
            return _dias(
                calcular_cpm(nodos, INICIO, fecha_corte=INICIO)["B"],
                "inicio_temprano",
            )

        assert corrida(5) == 6
        assert corrida(9) == 6

    def test_un_ancla_negativa_se_recorta_al_dia_0(self) -> None:
        # Misma cota que el clamp del forward pass y que el check de la 0043.
        r = calcular_cpm(
            [NodoCPM(ref="A", duracion_dias=5, inicio_dias=-4)],
            INICIO,
            fecha_corte=INICIO,
        )
        assert _dias(r["A"], "inicio_temprano") == 0

    def test_el_ancla_cuenta_con_los_tramos_para_el_cierre(self) -> None:
        # El span sigue siendo el de la interrupción; el ancla sólo mueve el
        # punto de partida.
        r = calcular_cpm(
            [
                NodoCPM(
                    ref="A",
                    duracion_dias=4,
                    inicio_dias=3,
                    tramos=(Tramo(duracion_dias=2), Tramo(duracion_dias=2, offset_dias=7)),
                )
            ],
            INICIO,
            fecha_corte=INICIO,
        )
        assert _dias(r["A"], "inicio_temprano") == 3
        assert _dias(r["A"], "fin_temprano") == 12


class TestTramos:
    """Interrupción de una actividad (§7.6): trabajo vs. span."""

    # El caso del usuario: el muro se levanta dos semanas, para para que se
    # cuele la losa, y regresa para los pretiles.
    MURO = (Tramo(duracion_dias=10), Tramo(duracion_dias=4, offset_dias=15))

    def test_el_span_llega_hasta_el_ultimo_tramo(self) -> None:
        nodo = NodoCPM(ref="MURO", duracion_dias=14, tramos=self.MURO)
        assert nodo.span == 19  # 15 + 4
        assert nodo.duracion_dias == 14  # los días de trabajo, sin la pausa

    def test_sin_tramos_el_span_es_la_duracion(self) -> None:
        assert NodoCPM(ref="A", duracion_dias=7).span == 7

    def test_la_barra_ocupa_el_span_no_los_dias_de_trabajo(self) -> None:
        nodos = [NodoCPM(ref="MURO", duracion_dias=14, tramos=self.MURO)]
        r = calcular_cpm(nodos, INICIO, fecha_corte=INICIO)
        assert r["MURO"].inicio_temprano == INICIO
        assert _dias(r["MURO"], "fin_temprano") == 19

    def test_la_sucesora_espera_al_ultimo_tramo_no_al_primero(self) -> None:
        """Lo que más se presta a error: si el motor usara los días de trabajo
        el aplanado arrancaría el día 14, encima de los pretiles."""
        nodos = [
            NodoCPM(ref="MURO", duracion_dias=14, tramos=self.MURO),
            NodoCPM(
                ref="APLANADO",
                duracion_dias=3,
                dependencias=(Dependencia("MURO", tipo=FS),),
            ),
        ]
        r = calcular_cpm(nodos, INICIO, fecha_corte=INICIO)
        assert _dias(r["APLANADO"], "inicio_temprano") == 19

    def test_la_losa_cabe_en_el_hueco_del_muro(self) -> None:
        """El caso del jefe de obra, tal cual (§7.6).

        "El muro de tabique se realiza las primeras 2 semanas, para para
        realizar la losa y después continúa para realizar muros de pretiles".

        El muro es UNA actividad de 317 m² con 14 días de trabajo repartidos
        en 19 de calendario; la losa (5 días) arranca cuando el primer tramo
        cierra y cabe entera en la pausa, sin que ninguna de las dos deje de
        ser crítica.
        """
        nodos = [
            NodoCPM(ref="MURO", duracion_dias=14, tramos=self.MURO),
            NodoCPM(
                ref="LOSA",
                duracion_dias=5,
                # La losa arranca con el muro pero diez días después: es el
                # primer tramo del muro el que la libera, y el CPM solo sabe
                # de inicios y fines de la actividad completa.
                dependencias=(Dependencia("MURO", tipo=SS, lag_dias=10),),
            ),
        ]
        r = calcular_cpm(nodos, INICIO, fecha_corte=INICIO)

        assert _dias(r["LOSA"], "inicio_temprano") == 10
        assert _dias(r["LOSA"], "fin_temprano") == 15
        # La losa cierra justo cuando el muro reanuda: el hueco es de 15 − 10.
        assert _dias(r["MURO"], "fin_temprano") == 19
        assert r["MURO"].es_critica

    def test_el_desfase_se_mide_contra_el_fin_del_span(self) -> None:
        """Una actividad interrumpida no está atrasada por estar en pausa."""
        nodos = [NodoCPM(ref="MURO", duracion_dias=14, tramos=self.MURO)]
        r = calcular_cpm(nodos, INICIO, fecha_corte=INICIO + timedelta(days=17))
        assert r["MURO"].desfase == 0

    def test_un_solo_tramo_se_comporta_como_no_tener_ninguno(self) -> None:
        con = NodoCPM(
            ref="A", duracion_dias=6, tramos=(Tramo(duracion_dias=6),)
        )
        assert con.span == NodoCPM(ref="A", duracion_dias=6).span

    def test_tramos_no_cambian_la_holgura_de_una_rama_sin_interrumpir(self) -> None:
        """Regresión: agregar tramos a una actividad no debe mover a las que
        no dependen de ella."""
        sin_tramos = calcular_cpm(_con_rama_holgada(), INICIO, fecha_corte=INICIO)
        con_tramos = calcular_cpm(
            [
                *_con_rama_holgada(),
                NodoCPM(
                    ref="AISLADA",
                    duracion_dias=4,
                    tramos=(
                        Tramo(duracion_dias=2),
                        Tramo(duracion_dias=2, offset_dias=5),
                    ),
                ),
            ],
            INICIO,
            fecha_corte=INICIO,
        )
        assert con_tramos["D"].holgura == sin_tramos["D"].holgura
        assert con_tramos["D"].inicio_temprano == sin_tramos["D"].inicio_temprano


class TestDesfase:
    def test_actividad_en_curso_pasada_de_fecha(self) -> None:
        r = calcular_cpm(_cadena(), INICIO, fecha_corte=date(2026, 3, 10))
        assert r["A"].desfase == 3   # debía terminar el 7, hoy es 10
        assert r["A"].esta_atrasada

    def test_sin_atraso_el_desfase_es_cero(self) -> None:
        r = calcular_cpm(_cadena(), INICIO, fecha_corte=date(2026, 3, 5))
        assert r["A"].desfase == 0

    def test_concluida_se_mide_contra_su_fecha_real(self) -> None:
        nodos = [
            NodoCPM(
                ref="A",
                duracion_dias=5,
                avance_pct=100,
                fecha_real_termino=date(2026, 3, 9),
            )
        ]
        r = calcular_cpm(nodos, INICIO, fecha_corte=date(2026, 4, 1))
        assert r["A"].desfase == 2   # terminó el 9, debía el 7

    def test_concluida_a_tiempo_no_arrastra_el_corte(self) -> None:
        nodos = [
            NodoCPM(
                ref="A",
                duracion_dias=5,
                avance_pct=100,
                fecha_real_termino=date(2026, 3, 6),
            )
        ]
        r = calcular_cpm(nodos, INICIO, fecha_corte=date(2026, 6, 1))
        assert r["A"].desfase == 0


class TestBloqueoPorIncidencia:
    def test_propaga_en_cascada(self) -> None:
        """Una incidencia `detiene` bloquea la actividad y sus sucesoras (§6)."""
        bloqueadas = actividades_bloqueadas_por(_cadena(), {"A"})
        assert bloqueadas == {"B", "C"}

    def test_no_alcanza_ramas_independientes(self) -> None:
        bloqueadas = actividades_bloqueadas_por(_con_rama_holgada(), {"D"})
        assert bloqueadas == {"C"}
        assert "B" not in bloqueadas


def test_cronograma_vacio_no_revienta() -> None:
    assert calcular_cpm([], INICIO) == {}
