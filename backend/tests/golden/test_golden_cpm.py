"""Dataset golden del motor CPM (§11.7, §7.5).

Dos cronogramas realistas de una vivienda, congelados con sus fechas, holguras
y ruta crítica:

* `_cronograma`, con `FS` y `SS`, que es el que existía antes de que el motor
  supiera de `FF`/`SF` y de tramos. Se deja **intacto** a propósito: su golden
  es la prueba de que agregar los dos tipos nuevos y la interrupción no movió
  ni un día de lo que ya se calculaba.
* `_cronograma_interrumpido`, que ejercita `FF`, `SF` y una actividad partida
  en tramos —el muro que para para que se cuele la losa (§7.6).

Los tres primeros golden corren con **semana natural**, que es el default del
motor y su comportamiento histórico. El cuarto congela el mismo cronograma
interrumpido con **semana laboral** (0040): mismos días, otras fechas.

## Por qué estos cronogramas y no uno de tres nodos

Tres nodos en cadena no ejercitan nada: cualquier implementación los ordena
bien. Lo que rompe un CPM son los caminos que convergen —dos predecesoras con
duraciones distintas—, las dependencias con lag, y las ramas que no están en la
ruta crítica pero se acercan. Estos cronogramas tienen las tres.
"""

from __future__ import annotations

from datetime import date

from obractrl.domain.programacion.calendario import SEMANA_LABORAL
from obractrl.domain.programacion.cpm import (
    Dependencia,
    NodoCPM,
    TipoDependencia,
    Tramo,
    calcular_cpm,
)

INICIO = date(2026, 3, 2)
CORTE = date(2026, 3, 30)


def _cronograma() -> list[NodoCPM]:
    """Una vivienda: de trazo a limpieza.

    Las duraciones no son redondas a propósito: con todo en múltiplos de cinco,
    un error de un día en la aritmética de fechas puede quedar escondido detrás
    de un fin de semana.
    """
    fs = TipoDependencia.FIN_INICIO
    ss = TipoDependencia.INICIO_INICIO

    return [
        NodoCPM(ref="TRAZO", duracion_dias=2, avance_pct=100.0),
        NodoCPM(
            ref="EXCAV",
            duracion_dias=3,
            dependencias=(Dependencia(ref="TRAZO", tipo=fs),),
            avance_pct=100.0,
        ),
        NodoCPM(
            ref="CIMENT",
            duracion_dias=6,
            dependencias=(Dependencia(ref="EXCAV", tipo=fs),),
            avance_pct=80.0,
        ),
        # Rama corta que converge con CIMENT: existe para que haya holgura real
        # que medir.
        NodoCPM(
            ref="INST_HIDRO",
            duracion_dias=2,
            dependencias=(Dependencia(ref="EXCAV", tipo=fs),),
            avance_pct=50.0,
        ),
        NodoCPM(
            ref="MUROS",
            duracion_dias=7,
            dependencias=(
                Dependencia(ref="CIMENT", tipo=fs),
                Dependencia(ref="INST_HIDRO", tipo=fs),
            ),
        ),
        # `SS` con lag: arranca con MUROS pero tres días después.
        NodoCPM(
            ref="INST_ELEC",
            duracion_dias=4,
            dependencias=(Dependencia(ref="MUROS", tipo=ss, lag_dias=3),),
        ),
        NodoCPM(
            ref="LOSA",
            duracion_dias=5,
            dependencias=(Dependencia(ref="MUROS", tipo=fs),),
        ),
        NodoCPM(
            ref="ACABADOS",
            duracion_dias=9,
            dependencias=(
                Dependencia(ref="LOSA", tipo=fs),
                Dependencia(ref="INST_ELEC", tipo=fs),
            ),
        ),
        NodoCPM(
            ref="PINTURA",
            duracion_dias=4,
            dependencias=(Dependencia(ref="ACABADOS", tipo=fs),),
        ),
        # Una rama que puede empezar temprano y termina holgada.
        NodoCPM(
            ref="JARDIN",
            duracion_dias=2,
            dependencias=(Dependencia(ref="CIMENT", tipo=fs),),
        ),
        NodoCPM(
            ref="LIMPIEZA",
            duracion_dias=1,
            dependencias=(
                Dependencia(ref="PINTURA", tipo=fs),
                Dependencia(ref="JARDIN", tipo=fs),
            ),
        ),
        # Sin dependencias y sin sucesoras: el caso que a veces se rompe.
        NodoCPM(ref="TRAMITES", duracion_dias=3),
    ]


def _cronograma_interrumpido() -> list[NodoCPM]:
    """La misma vivienda con las cuatro relaciones y un muro partido.

    * `MURO` son 14 días de trabajo repartidos en 19 de calendario: dos
      semanas, la pausa en la que se cuela la losa, y los pretiles (§7.6).
    * `LOSA` entra en esa pausa con un `SS` de 10 días.
    * `SUPERVISION` acompaña a los acabados de punta a punta con el par
      `SS` + `FF` sobre la MISMA predecesora, que es el caso que obliga al
      backward pass a mirar todas las aristas y no solo la primera.
    * `BOMBEO` es la provisional que solo se retira cuando arranca la
      definitiva: un `SF`, la más rara de las cuatro.
    """
    fs = TipoDependencia.FIN_INICIO
    ss = TipoDependencia.INICIO_INICIO
    ff = TipoDependencia.FIN_FIN
    sf = TipoDependencia.INICIO_FIN

    return [
        NodoCPM(ref="CIMENT", duracion_dias=6, avance_pct=100.0),
        NodoCPM(
            ref="MURO",
            duracion_dias=14,
            dependencias=(Dependencia(ref="CIMENT", tipo=fs),),
            tramos=(
                Tramo(duracion_dias=10),
                Tramo(duracion_dias=4, offset_dias=15),
            ),
            avance_pct=40.0,
        ),
        NodoCPM(
            ref="LOSA",
            duracion_dias=5,
            dependencias=(Dependencia(ref="MURO", tipo=ss, lag_dias=10),),
        ),
        NodoCPM(
            ref="ACABADOS",
            duracion_dias=9,
            dependencias=(Dependencia(ref="MURO", tipo=fs),),
        ),
        NodoCPM(
            ref="SUPERVISION",
            duracion_dias=9,
            dependencias=(
                Dependencia(ref="ACABADOS", tipo=ss),
                Dependencia(ref="ACABADOS", tipo=ff),
            ),
        ),
        # Se retira cuando arranca la cisterna definitiva, no antes.
        NodoCPM(ref="BOMBEO", duracion_dias=4),
        NodoCPM(
            ref="CISTERNA",
            duracion_dias=3,
            dependencias=(Dependencia(ref="LOSA", tipo=fs),),
        ),
        NodoCPM(
            ref="RETIRO_BOMBEO",
            duracion_dias=2,
            dependencias=(Dependencia(ref="CISTERNA", tipo=sf),),
        ),
        # `FF` con lag: la limpieza cierra dos días después que los acabados.
        NodoCPM(
            ref="LIMPIEZA",
            duracion_dias=3,
            dependencias=(Dependencia(ref="ACABADOS", tipo=ff, lag_dias=2),),
        ),
    ]


def _serializar(resultados: dict) -> dict:
    return {
        ref: {
            "inicio_temprano": r.inicio_temprano.isoformat(),
            "fin_temprano": r.fin_temprano.isoformat(),
            "inicio_tardio": r.inicio_tardio.isoformat(),
            "fin_tardio": r.fin_tardio.isoformat(),
            "holgura": r.holgura,
            "es_critica": r.es_critica,
            "desfase": r.desfase,
        }
        for ref, r in sorted(resultados.items())
    }


def test_golden_cronograma_de_vivienda(golden) -> None:
    """Las fechas, holguras y criticidad de un cronograma completo."""
    resultados = calcular_cpm(_cronograma(), INICIO, fecha_corte=CORTE)
    golden("cpm_vivienda", _serializar(resultados))


def test_golden_con_tolerancia_de_holgura(golden) -> None:
    """La misma red con `tolerancia_holgura=2`.

    Se congela aparte porque cambia **qué es crítico**, que es la salida que más
    consecuencias tiene: la Torre la muestra, el Gantt la pinta y el cierre de
    obra la cuenta. Un cambio accidental en el criterio de criticidad se vería
    aquí como un puñado de `es_critica` que pasan de `false` a `true`.
    """
    resultados = calcular_cpm(
        _cronograma(), INICIO, fecha_corte=CORTE, tolerancia_holgura=2.0
    )
    golden("cpm_vivienda_tolerancia_2", _serializar(resultados))


def test_golden_cronograma_con_ff_sf_y_tramos(golden) -> None:
    """Las cuatro relaciones y una actividad interrumpida, congeladas.

    Es el golden que protege lo nuevo: si alguien reacomoda la aritmética de
    `FF`/`SF` o cambia qué cuenta como span, aquí se ve exactamente qué día se
    movió y de cuál actividad.
    """
    resultados = calcular_cpm(_cronograma_interrumpido(), INICIO, fecha_corte=CORTE)
    golden("cpm_vivienda_interrumpida", _serializar(resultados))


def test_golden_con_calendario_laboral(golden) -> None:
    """El mismo cronograma interrumpido, con semana laboral (§7.5, 0040).

    Se congela contra el golden de semana natural, no aparte de él: el par de
    archivos es la prueba de que el calendario mueve **fechas** y nada más. Las
    holguras y la criticidad son idénticas en los dos —son aritmética de
    índices—; lo que cambia son las fechas y el desfase, que ahora cuenta días
    de trabajo (§6).

    Se usa lunes a sábado y no lunes a viernes porque es la semana real de obra
    en México y por lo tanto la que va a estar en producción: una regresión ahí
    es la que le cambia las fechas a alguien.
    """
    resultados = calcular_cpm(
        _cronograma_interrumpido(),
        INICIO,
        fecha_corte=CORTE,
        calendario=SEMANA_LABORAL,
    )
    golden("cpm_vivienda_interrumpida_laboral", _serializar(resultados))


def test_el_calendario_laboral_solo_mueve_fechas(golden) -> None:
    """Holgura y criticidad no dependen del calendario; las fechas sí.

    Acompaña al golden de arriba y dice explícitamente qué debería y qué no
    debería aparecer en su diff. Sin esto, alguien que vea moverse una fecha en
    el archivo no sabe si también debía moverse la holgura.
    """
    natural = calcular_cpm(_cronograma_interrumpido(), INICIO, fecha_corte=CORTE)
    laboral = calcular_cpm(
        _cronograma_interrumpido(),
        INICIO,
        fecha_corte=CORTE,
        calendario=SEMANA_LABORAL,
    )

    for ref, n in natural.items():
        assert laboral[ref].holgura == n.holgura, ref
        assert laboral[ref].es_critica == n.es_critica, ref
        # Con semana laboral todo cae igual o más tarde en el calendario: los
        # domingos se saltan, nunca se adelanta nada.
        assert laboral[ref].fin_temprano >= n.fin_temprano, ref

    assert laboral["ACABADOS"].fin_temprano > natural["ACABADOS"].fin_temprano


def test_el_golden_no_depende_del_orden_de_entrada(golden) -> None:
    """El mismo cronograma con los nodos al revés da el mismo resultado.

    No es una obviedad: un CPM que dependiera del orden de la lista en vez de
    del orden topológico daría fechas distintas según cómo venga la consulta —y
    `programacion_de_obra` no promete ningún orden en particular.
    """
    al_reves = list(reversed(_cronograma()))
    resultados = calcular_cpm(al_reves, INICIO, fecha_corte=CORTE)
    golden("cpm_vivienda", _serializar(resultados))
