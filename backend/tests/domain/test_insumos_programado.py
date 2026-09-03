"""Insumos programados: el cruce cronograma × APU (§7.3, §7.5, §7.6).

Lo que se fija aquí son las cuatro decisiones que no se pueden leer del código
sin explicación, y que si cambian en silencio dejan a alguien comprando mal:

 1. **El reparto es proporcional a los días trabajados**, y una pausa no
    consume material. Repartir sobre el span le daría cemento a la semana en
    que la actividad está parada — que es exactamente la cifra con la que
    alguien pide.
 2. **La suma de las columnas es el total del renglón.** Al partir en tercios
    el redondeo deja residuo; si nadie lo recoge, el renglón dice un total
    distinto de lo que enseña y deja de ser creíble.
 3. **La anticipación corre la necesidad, no la actividad.** Se pide antes, se
    usa cuando toca; las fechas del CPM no se tocan.
 4. **Lo que no se puede calcular se reporta, no se descarta.** Una obra sin
    calendarizar y una actividad extra-catálogo son casos normales; una tabla
    corta sin explicación es un bug que nadie ve.

Módulo puro: sin BD, sin reloj (§12.11).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from obractrl.domain.catalogos.apu import Componente, explotar
from obractrl.domain.insumos.programado import (
    ActividadConVentana,
    InsumoDelCatalogo,
    Periodo,
    insumos_programados,
    intervalos_de_trabajo,
    jornadas_por_frente,
    repartir_en_periodos,
)
from obractrl.domain.programacion.cpm import Tramo

# Tres semanas corridas, de lunes a lunes. `hasta` es exclusivo.
S20 = Periodo("2026-20", date(2026, 5, 11), date(2026, 5, 18), "S20")
S21 = Periodo("2026-21", date(2026, 5, 18), date(2026, 5, 25), "S21")
S22 = Periodo("2026-22", date(2026, 5, 25), date(2026, 6, 1), "S22")
SEMANAS = (S20, S21, S22)

CEMENTO = InsumoDelCatalogo(
    insumo_id="i-cem",
    clave="CEM-01",
    descripcion="Cemento gris",
    unidad="BTO",
    tipo="material",
    costo=Decimal("250"),
)
ARENA = InsumoDelCatalogo(
    insumo_id="i-are",
    clave="ARE-01",
    descripcion="Arena",
    unidad="M3",
    tipo="material",
    costo=Decimal("400"),
)
ALBANIL = InsumoDelCatalogo(
    insumo_id="i-alb",
    clave="MO-01",
    descripcion="Albañil",
    unidad="JOR",
    tipo="mano_obra",
    costo=Decimal("600"),
)
CATALOGO = {"CEM-01": CEMENTO, "ARE-01": ARENA, "MO-01": ALBANIL}


def _explosion(*componentes: Componente):
    """Explota un concepto `MURO` con los componentes dados."""
    return explotar("MURO", composiciones={"MURO": list(componentes)})


def _actividad(
    *,
    cantidad: str = "10",
    inicio: date | None = date(2026, 5, 11),
    fin: date | None = date(2026, 5, 21),
    tramos: tuple[Tramo, ...] = (),
    concepto: str | None = "MURO",
    obra: str = "obra-1",
    frente: str | None = None,
    especialidad: str | None = None,
    actividad_id: str = "act-1",
) -> ActividadConVentana:
    return ActividadConVentana(
        actividad_id=actividad_id,
        obra_id=obra,
        concepto_clave=concepto,
        descripcion="Muro de tabique",
        cantidad=Decimal(cantidad),
        inicio=inicio,
        fin=fin,
        tramos=tramos,
        frente_id=frente,
        especialidad_id=especialidad,
    )


class TestIntervalosDeTrabajo:
    def test_sin_tramos_es_la_ventana_completa(self) -> None:
        assert intervalos_de_trabajo(date(2026, 5, 11), date(2026, 5, 21), ()) == (
            (date(2026, 5, 11), date(2026, 5, 21)),
        )

    def test_con_tramos_son_los_tramos_y_no_el_span(self) -> None:
        # El muro del §7.6: dos días, para, y sigue dos más. El hueco de en
        # medio no es trabajo.
        muro = (Tramo(duracion_dias=2), Tramo(duracion_dias=2, offset_dias=7))
        assert intervalos_de_trabajo(date(2026, 5, 11), date(2026, 5, 20), muro) == (
            (date(2026, 5, 11), date(2026, 5, 13)),
            (date(2026, 5, 18), date(2026, 5, 20)),
        )

    def test_una_ventana_degenerada_no_aporta_intervalos(self) -> None:
        assert intervalos_de_trabajo(date(2026, 5, 11), date(2026, 5, 11), ()) == ()


class TestRepartoEnPeriodos:
    def test_reparte_proporcional_a_los_dias_de_cada_periodo(self) -> None:
        # 10 días: 7 en S20 y 3 en S21 → 70/30 de 100.
        intervalos = ((date(2026, 5, 11), date(2026, 5, 21)),)
        assert repartir_en_periodos(intervalos, SEMANAS, Decimal(100)) == (
            Decimal(70),
            Decimal(30),
            Decimal(0),
        )

    def test_una_pausa_no_consume(self) -> None:
        # Trabaja S20 y S22; la semana de en medio está parada y lleva CERO,
        # no un tercio. Es la razón de ser de los tramos (§7.6).
        muro = (Tramo(duracion_dias=7), Tramo(duracion_dias=7, offset_dias=14))
        intervalos = intervalos_de_trabajo(date(2026, 5, 11), date(2026, 6, 1), muro)
        assert repartir_en_periodos(intervalos, SEMANAS, Decimal(100)) == (
            Decimal(50),
            Decimal(0),
            Decimal(50),
        )

    def test_la_suma_de_las_columnas_es_el_total(self) -> None:
        # 100 entre tres semanas iguales da 33.333333 tres veces, que no suman
        # 100. El residuo lo recoge el último periodo con trabajo.
        intervalos = ((date(2026, 5, 11), date(2026, 6, 1)),)
        partes = repartir_en_periodos(intervalos, SEMANAS, Decimal(100))
        assert sum(partes) == Decimal(100)

    def test_sin_trabajo_dentro_de_la_ventana_todo_es_cero(self) -> None:
        fuera = ((date(2026, 1, 5), date(2026, 1, 9)),)
        assert repartir_en_periodos(fuera, SEMANAS, Decimal(100)) == (
            Decimal(0),
            Decimal(0),
            Decimal(0),
        )

    def test_lo_que_cae_fuera_del_rango_no_se_empuja_al_ultimo(self) -> None:
        # La actividad sigue después de S22: lo suyo de fuera se queda fuera.
        # Cuadrar aquí inflaría la última columna con trabajo que no le toca.
        intervalos = ((date(2026, 5, 11), date(2026, 6, 15)),)
        partes = repartir_en_periodos(intervalos, SEMANAS, Decimal(100))
        assert sum(partes) < Decimal(100)


class TestMatriz:
    def test_cruza_cantidad_de_obra_con_el_apu(self) -> None:
        # 10 m² de muro × 0.5 bultos por m² = 5 bultos, repartidos 70/30.
        matriz = insumos_programados(
            actividades=[_actividad()],
            explosiones={
                "MURO": _explosion(
                    Componente(
                        categoria="material",
                        cantidad=Decimal("0.5"),
                        clave_insumo="CEM-01",
                    )
                )
            },
            catalogo=CATALOGO,
            periodos=SEMANAS,
        )
        assert len(matriz.filas) == 1
        fila = matriz.filas[0]
        assert fila.insumo.clave == "CEM-01"
        assert fila.total == Decimal(5)
        assert fila.cantidades == (Decimal("3.5"), Decimal("1.5"), Decimal(0))

    def test_el_importe_usa_el_costo_del_catalogo(self) -> None:
        matriz = insumos_programados(
            actividades=[_actividad()],
            explosiones={
                "MURO": _explosion(
                    Componente(
                        categoria="material",
                        cantidad=Decimal("0.5"),
                        clave_insumo="CEM-01",
                    )
                )
            },
            catalogo=CATALOGO,
            periodos=SEMANAS,
        )
        assert matriz.filas[0].importe == Decimal(1250)  # 5 bultos × $250

    def test_sin_permiso_de_costos_el_importe_es_nulo_y_no_cero(self) -> None:
        # Cero diría que el insumo es gratis; nulo dice que no se muestra.
        matriz = insumos_programados(
            actividades=[_actividad()],
            explosiones={
                "MURO": _explosion(
                    Componente(
                        categoria="material",
                        cantidad=Decimal("0.5"),
                        clave_insumo="CEM-01",
                    )
                )
            },
            catalogo=CATALOGO,
            periodos=SEMANAS,
            con_importe=False,
        )
        assert matriz.filas[0].importe is None

    def test_baja_por_los_auxiliares_y_no_cuenta_la_matriz_dos_veces(self) -> None:
        # MURO lleva un auxiliar MORTERO, que lleva cemento y arena. El insumo
        # tiene que aparecer una sola vez, con la cantidad acumulada del camino
        # — que es lo que la vista plana `v_consumo_vs_presupuesto` no ve.
        matriz = insumos_programados(
            actividades=[_actividad()],
            explosiones={
                "MURO": explotar(
                    "MURO",
                    composiciones={
                        "MURO": [
                            Componente(
                                categoria="auxiliar",
                                cantidad=Decimal("2"),
                                clave_concepto="MORTERO",
                            )
                        ],
                        "MORTERO": [
                            Componente(
                                categoria="material",
                                cantidad=Decimal("0.25"),
                                clave_insumo="CEM-01",
                            ),
                            Componente(
                                categoria="material",
                                cantidad=Decimal("1"),
                                clave_insumo="ARE-01",
                            ),
                        ],
                    },
                )
            },
            catalogo=CATALOGO,
            periodos=SEMANAS,
        )
        por_clave = {fila.insumo.clave: fila for fila in matriz.filas}
        assert set(por_clave) == {"CEM-01", "ARE-01"}
        # 10 de muro × 2 de mortero × 0.25 de cemento = 5
        assert por_clave["CEM-01"].total == Decimal(5)
        assert por_clave["ARE-01"].total == Decimal(20)

    def test_el_filtro_por_tipo_deja_fuera_lo_que_no_se_pidio(self) -> None:
        explosion = _explosion(
            Componente(
                categoria="material", cantidad=Decimal("0.5"), clave_insumo="CEM-01"
            ),
            Componente(
                categoria="mano_obra", cantidad=Decimal("0.2"), clave_insumo="MO-01"
            ),
        )
        matriz = insumos_programados(
            actividades=[_actividad()],
            explosiones={"MURO": explosion},
            catalogo=CATALOGO,
            periodos=SEMANAS,
            tipos=frozenset({"material"}),
        )
        assert [fila.insumo.clave for fila in matriz.filas] == ["CEM-01"]

    def test_la_anticipacion_global_corre_la_necesidad_hacia_atras(self) -> None:
        # Sin anticipación el trabajo cae 70/30 entre S20 y S21. Pidiéndolo 7
        # días antes, todo se recorre una semana.
        explosion = _explosion(
            Componente(
                categoria="material", cantidad=Decimal("1"), clave_insumo="CEM-01"
            )
        )
        sin = insumos_programados(
            actividades=[_actividad()],
            explosiones={"MURO": explosion},
            catalogo=CATALOGO,
            periodos=SEMANAS,
        )
        con = insumos_programados(
            actividades=[_actividad()],
            explosiones={"MURO": explosion},
            catalogo=CATALOGO,
            periodos=SEMANAS,
            dias_anticipacion=7,
        )
        assert sin.filas[0].cantidades == (Decimal(7), Decimal(3), Decimal(0))
        # Los 7 días que se corrieron antes de S20 se salen del rango.
        assert con.filas[0].cantidades[0] == Decimal(3)

    def test_el_plazo_del_insumo_le_gana_a_la_anticipacion_global(self) -> None:
        # El cemento llega en 0 días aunque el global pida 7: lo capturado
        # manda, que es para lo que se captura.
        cemento_inmediato = {**CATALOGO, "CEM-01": InsumoDelCatalogo(
            insumo_id="i-cem", clave="CEM-01", descripcion="Cemento",
            unidad="BTO", tipo="material", costo=Decimal("250"), dias_entrega=0,
        )}
        matriz = insumos_programados(
            actividades=[_actividad()],
            explosiones={
                "MURO": _explosion(
                    Componente(
                        categoria="material",
                        cantidad=Decimal("1"),
                        clave_insumo="CEM-01",
                    )
                )
            },
            catalogo=cemento_inmediato,
            periodos=SEMANAS,
            dias_anticipacion=7,
        )
        assert matriz.filas[0].cantidades == (Decimal(7), Decimal(3), Decimal(0))

    def test_una_actividad_sin_calendarizar_se_reporta_y_no_se_descarta(self) -> None:
        matriz = insumos_programados(
            actividades=[_actividad(inicio=None, fin=None)],
            explosiones={
                "MURO": _explosion(
                    Componente(
                        categoria="material",
                        cantidad=Decimal("1"),
                        clave_insumo="CEM-01",
                    )
                )
            },
            catalogo=CATALOGO,
            periodos=SEMANAS,
        )
        assert matriz.filas == ()
        assert matriz.sin_programar == ("act-1",)

    def test_una_actividad_extra_catalogo_no_tiene_apu_que_explotar(self) -> None:
        matriz = insumos_programados(
            actividades=[_actividad(concepto=None)],
            explosiones={},
            catalogo=CATALOGO,
            periodos=SEMANAS,
        )
        assert matriz.sin_explosion == ("act-1",)

    def test_el_desglose_dice_de_donde_salio_cada_cifra(self) -> None:
        explosion = _explosion(
            Componente(
                categoria="material", cantidad=Decimal("1"), clave_insumo="CEM-01"
            )
        )
        matriz = insumos_programados(
            actividades=[
                _actividad(obra="obra-1", cantidad="10"),
                _actividad(obra="obra-2", cantidad="30"),
            ],
            explosiones={"MURO": explosion},
            catalogo=CATALOGO,
            periodos=SEMANAS,
        )
        fila = matriz.filas[0]
        assert fila.total == Decimal(40)
        # De mayor a menor: quien pide más va arriba.
        assert [(r.obra_id, r.cantidad) for r in fila.desglose] == [
            ("obra-2", Decimal(30)),
            ("obra-1", Decimal(10)),
        ]

    def test_un_insumo_que_el_catalogo_no_conoce_se_salta(self) -> None:
        # Sin unidad ni tipo no hay con qué rotularlo; enseñarlo a medias sería
        # peor que omitirlo.
        matriz = insumos_programados(
            actividades=[_actividad()],
            explosiones={
                "MURO": _explosion(
                    Componente(
                        categoria="material",
                        cantidad=Decimal("1"),
                        clave_insumo="FANTASMA",
                    )
                )
            },
            catalogo=CATALOGO,
            periodos=SEMANAS,
        )
        assert matriz.filas == ()


class TestJornadasPorFrente:
    """Las jornadas que cada frente pide, periodo a periodo (§8.3).

    Es de dónde sale la cuenta de cuadrillas, y lo que estas pruebas protegen
    es que **agrupar por frente no cambie el reparto**: es el mismo repartidor
    que el de los materiales, filtrado a mano de obra. Si un día divergieran,
    el material y la gente dirían cosas distintas sobre el mismo programa.
    """

    _MANO_DE_OBRA = Componente(
        categoria="mano_obra", cantidad=Decimal("2"), clave_insumo="MO-01"
    )
    _MATERIAL = Componente(
        categoria="material", cantidad=Decimal("3"), clave_insumo="CEM-01"
    )

    def _jornadas(self, *actividades: ActividadConVentana):
        return jornadas_por_frente(
            actividades=list(actividades),
            explosiones={"MURO": _explosion(self._MANO_DE_OBRA, self._MATERIAL)},
            catalogo=CATALOGO,
            periodos=SEMANAS,
        )

    def test_solo_cuenta_mano_de_obra(self) -> None:
        # El cemento no se mide en cuadrillas. Colarlo inflaría la gente que
        # hace falta en la proporción del APU, que no significa nada.
        jornadas = self._jornadas(_actividad(frente="est"))
        assert sum(jornadas["est"]) == Decimal(20)

    def test_suma_las_actividades_del_mismo_frente(self) -> None:
        # Un frente son varias etapas: si cada actividad saliera por su lado,
        # la tabla pediría contratar por renglón en vez de por frente.
        jornadas = self._jornadas(
            _actividad(frente="est"),
            _actividad(frente="est", actividad_id="act-2"),
        )
        assert sum(jornadas["est"]) == Decimal(40)

    def test_separa_frentes_distintos(self) -> None:
        jornadas = self._jornadas(
            _actividad(frente="est"),
            _actividad(frente="ins", actividad_id="act-2", cantidad="5"),
        )
        assert sum(jornadas["est"]) == Decimal(20)
        assert sum(jornadas["ins"]) == Decimal(10)

    def test_lo_que_no_tiene_frente_se_agrupa_y_no_se_descarta(self) -> None:
        # Es trabajo real cuya etapa todavía no se mapeó (migración 0045).
        # Descartarlo haría que el total de la obra no cuadrara con la suma de
        # sus frentes, y nadie sabría que falta capturar algo.
        jornadas = self._jornadas(_actividad(frente=None))
        assert sum(jornadas[""]) == Decimal(20)

    def test_el_agrupador_cambia_el_eje_sin_cambiar_el_reparto(self) -> None:
        """El segundo eje (0047): el mismo cruce agrupado por oficio.

        Lo que se protege es que **la suma no cambie** al cambiar de eje. El
        frente y la especialidad son dos lecturas del mismo trabajo; si cada una
        tuviera su propio recorrido, un día el total de la obra no sería ni la
        suma de sus frentes ni la de sus oficios.
        """
        actividades = [
            _actividad(frente="est", especialidad="alb"),
            _actividad(frente="est", especialidad="aca", actividad_id="act-2"),
        ]
        por_frente = self._jornadas(*actividades)
        por_oficio = jornadas_por_frente(
            actividades=actividades,
            explosiones={"MURO": _explosion(self._MANO_DE_OBRA, self._MATERIAL)},
            catalogo=CATALOGO,
            periodos=SEMANAS,
            agrupar=lambda a: a.especialidad_id or "",
        )
        assert set(por_oficio) == {"alb", "aca"}
        assert sum(por_frente["est"]) == sum(
            sum(fila) for fila in por_oficio.values()
        )

    def test_lo_que_no_tiene_oficio_tampoco_se_descarta(self) -> None:
        # Un concepto sin especialidad capturada sigue siendo trabajo real: si
        # se cayera, la suma de los oficios no daría el frente.
        por_oficio = jornadas_por_frente(
            actividades=[_actividad(frente="est", especialidad=None)],
            explosiones={"MURO": _explosion(self._MANO_DE_OBRA)},
            catalogo=CATALOGO,
            periodos=SEMANAS,
            agrupar=lambda a: a.especialidad_id or "",
        )
        assert sum(por_oficio[""]) == Decimal(20)

    def test_reparte_sobre_los_periodos_como_los_materiales(self) -> None:
        # Mismo repartidor: la actividad va del 11 al 21 de mayo, así que cae
        # en dos semanas y no entera en la primera.
        jornadas = self._jornadas(_actividad(frente="est"))
        assert len(jornadas["est"]) == len(SEMANAS)
        assert jornadas["est"][0] > 0
        assert jornadas["est"][1] > 0
        assert jornadas["est"][2] == 0
