"""Programación jerárquica sobre el árbol WBS (§7.4, §7.5, §6).

`test_programacion.py` prueba cómo la plantilla baja a una actividad concreta;
esto prueba la otra dimensión: cómo una ventana capturada en un nodo **grueso**
—una etapa, un nivel— se reparte entre los conceptos que cuelgan de él, cómo el
cronograma de esos conceptos vuelve a subir como barra resumen, y qué pasa
cuando las dos cifras no coinciden.

El árbol de las pruebas es el del ejemplo con el que se discutió la fase:

    ESTRUCTURA PB  (etapa)
      └ PLANTA BAJA (nivel)
          ├ muro      $122 000
          ├ castillo  $ 10 000
          └ cadena    $ 30 000
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from itertools import pairwise

import pytest

from obractrl.domain.programacion.calendario import SEMANA_LABORAL, SEMANA_NATURAL
from obractrl.domain.programacion.jerarquia import (
    MINIMO_REPARTIBLE,
    ErrorDeJerarquia,
    HojaProgramable,
    NodoWBS,
    es_captura_manual,
    hojas_por_nodo,
    nodos_capturables,
    pesos_por_importe,
    repartir_secuencial,
    repartir_ventana,
    resumir_arbol,
)
from obractrl.domain.shared.diccionario import ClaseNodo

INICIO = date(2026, 3, 2)  # lunes

ETAPA, NIVEL = "n-etapa", "n-nivel"
NODO_MURO, NODO_CASTILLO, NODO_CADENA = "n-muro", "n-castillo", "n-cadena"
MURO, CASTILLO, CADENA = "act-muro", "act-castillo", "act-cadena"

IMPORTE_MURO = Decimal("122000")
IMPORTE_CASTILLO = Decimal("10000")
IMPORTE_CADENA = Decimal("30000")


def _arbol() -> list[NodoWBS]:
    """Etapa → nivel → tres conceptos, en recorrido en profundidad."""
    return [
        NodoWBS(id=ETAPA, tipo=ClaseNodo.ETAPA, nombre="ESTRUCTURA PB"),
        NodoWBS(id=NIVEL, tipo=ClaseNodo.NIVEL, nombre="PLANTA BAJA", parent_id=ETAPA),
        NodoWBS(
            id=NODO_MURO, tipo=ClaseNodo.CONCEPTO, nombre="Muro", parent_id=NIVEL
        ),
        NodoWBS(
            id=NODO_CASTILLO,
            tipo=ClaseNodo.CONCEPTO,
            nombre="Castillo",
            parent_id=NIVEL,
        ),
        NodoWBS(
            id=NODO_CADENA, tipo=ClaseNodo.CONCEPTO, nombre="Cadena", parent_id=NIVEL
        ),
    ]


def _hojas() -> list[HojaProgramable]:
    """Las tres hojas recién generadas: día por defecto y sin fechas."""
    return [
        HojaProgramable(
            actividad_id=MURO, prototipo_nodo_id=NODO_MURO, importe=IMPORTE_MURO
        ),
        HojaProgramable(
            actividad_id=CASTILLO,
            prototipo_nodo_id=NODO_CASTILLO,
            importe=IMPORTE_CASTILLO,
        ),
        HojaProgramable(
            actividad_id=CADENA, prototipo_nodo_id=NODO_CADENA, importe=IMPORTE_CADENA
        ),
    ]


def _campos(hoja: HojaProgramable) -> dict:
    return {
        "actividad_id": hoja.actividad_id,
        "prototipo_nodo_id": hoja.prototipo_nodo_id,
        "importe": hoja.importe,
        "duracion_dias": hoja.duracion_dias,
        "fecha_inicio": hoja.fecha_inicio,
        "fecha_termino": hoja.fecha_termino,
        "avance_pct": hoja.avance_pct,
    }


# --- Reparto hacia abajo (§7.5) ------------------------------------------


def test_reparto_es_proporcional_al_importe() -> None:
    """El muro de $122k se lleva más días que el castillo de $10k."""
    reparto = dict(repartir_ventana(Decimal(20), pesos_por_importe(_hojas())))

    total = IMPORTE_MURO + IMPORTE_CASTILLO + IMPORTE_CADENA
    assert reparto[MURO] > reparto[CADENA] > reparto[CASTILLO]
    # El muro vale 122/162 del total: le tocan ~15 de los 20 días.
    exacto = Decimal(20) * IMPORTE_MURO / total
    assert abs(reparto[MURO] - exacto) < Decimal("0.02")


def test_el_reparto_cuadra_exactamente_con_la_ventana() -> None:
    """La suma de las partes es la ventana capturada, sin medio día suelto.

    Es la invariante que hace que el rollup reproduzca la cifra que el usuario
    escribió en el padre: si el reparto perdiera centésimas por el redondeo, la
    barra resumen diría 19.98 donde él capturó 20 y parecería un conflicto.
    """
    reparto = repartir_ventana(Decimal(20), pesos_por_importe(_hojas()))
    assert sum(dias for _, dias in reparto) == Decimal(20)


def test_ocho_conceptos_caben_en_veinte_dias() -> None:
    """El caso del brief: la etapa con ocho conceptos abajo."""
    pesos = [(f"act-{i}", Decimal(1000 * (i + 1))) for i in range(8)]
    reparto = repartir_ventana(Decimal(20), pesos)

    assert len(reparto) == 8
    assert sum(dias for _, dias in reparto) == Decimal(20)
    assert all(dias > 0 for _, dias in reparto)


def test_sin_presupuesto_el_reparto_es_igual() -> None:
    """Importes en cero —una obra sin presupuesto cargado— reparte parejo."""
    sin_importe = [(MURO, Decimal(0)), (CASTILLO, Decimal(0)), (CADENA, Decimal(0))]
    reparto = dict(repartir_ventana(Decimal(9), sin_importe))

    assert reparto[CASTILLO] == reparto[CADENA] == Decimal(3)
    assert sum(reparto.values()) == Decimal(9)


def test_un_solo_hijo_se_lleva_toda_la_ventana() -> None:
    reparto = repartir_ventana(Decimal("12.5"), [(MURO, IMPORTE_MURO)])
    assert reparto == ((MURO, Decimal("12.50")),)


def test_una_hoja_sin_importe_entre_hojas_con_importe_no_se_queda_en_cero() -> None:
    """`duracion_dias` tiene `check (> 0)`: nadie puede salir con cero días."""
    pesos = [(MURO, IMPORTE_MURO), (CASTILLO, Decimal(0))]
    reparto = dict(repartir_ventana(Decimal(10), pesos))

    assert reparto[CASTILLO] == MINIMO_REPARTIBLE
    assert sum(reparto.values()) == Decimal(10)


def test_sin_hojas_no_hay_reparto() -> None:
    with pytest.raises(ErrorDeJerarquia, match=r"[Nn]o hay nada"):
        repartir_ventana(Decimal(20), [])


def test_ventana_no_positiva_se_rechaza() -> None:
    with pytest.raises(ErrorDeJerarquia, match="positiva"):
        repartir_ventana(Decimal(0), pesos_por_importe(_hojas()))


def test_ventana_que_no_alcanza_para_todos_se_rechaza() -> None:
    """Programar medio día repartido entre cien conceptos no cabe en la columna."""
    pesos = [(f"act-{i}", Decimal(1)) for i in range(100)]
    with pytest.raises(ErrorDeJerarquia, match="no alcanza"):
        repartir_ventana(Decimal("0.5"), pesos)


def test_reparto_secuencial_acomoda_una_tras_otra_sin_huecos() -> None:
    """Las tres quedan en fila y la última cierra donde cierra la ventana."""
    colocaciones = repartir_secuencial(
        hojas=_hojas(), ventana_dias=Decimal(20), inicio=INICIO
    )

    assert [c.actividad_id for c in colocaciones] == [MURO, CASTILLO, CADENA]
    assert colocaciones[0].offset_dias == Decimal(0)
    assert colocaciones[0].fecha_inicio == INICIO

    for anterior, siguiente in pairwise(colocaciones):
        assert siguiente.offset_dias == anterior.offset_dias + anterior.duracion_dias
        # Sin hueco ni traslape: la siguiente arranca donde cerró la anterior.
        assert siguiente.fecha_inicio == anterior.fecha_termino

    ultima = colocaciones[-1]
    assert ultima.offset_dias + ultima.duracion_dias == Decimal(20)


def test_reparto_secuencial_respeta_el_calendario_laboral() -> None:
    """Con lunes a sábado, 20 días hábiles no son 20 casillas del calendario."""
    natural = repartir_secuencial(
        hojas=_hojas(),
        ventana_dias=Decimal(20),
        inicio=INICIO,
        calendario=SEMANA_NATURAL,
    )
    laboral = repartir_secuencial(
        hojas=_hojas(),
        ventana_dias=Decimal(20),
        inicio=INICIO,
        calendario=SEMANA_LABORAL,
    )

    # Las duraciones no cambian de valor al cambiar de calendario; cambia a qué
    # fecha las traduce (`calendario.py`).
    assert [c.duracion_dias for c in natural] == [c.duracion_dias for c in laboral]
    assert laboral[-1].fecha_termino > natural[-1].fecha_termino


def test_los_pesos_se_pueden_traer_de_fuera() -> None:
    """La costura para `cantidad ÷ rendimiento`: quien pesa es el llamador.

    Con pesos invertidos —el castillo pesando más que el muro— el reparto
    cambia sin tocar el reparto mismo, que es justo lo que se necesita para que
    meter la regla del destajo sea cambiar quién calcula el peso.
    """
    invertidos = [(MURO, Decimal(1)), (CASTILLO, Decimal(9)), (CADENA, Decimal(0))]
    colocaciones = repartir_secuencial(
        hojas=_hojas(), ventana_dias=Decimal(10), inicio=INICIO, pesos=invertidos
    )

    por_id = {c.actividad_id: c.duracion_dias for c in colocaciones}
    assert por_id[CASTILLO] > por_id[MURO]


# --- Rollup hacia arriba (§6, §7.4) --------------------------------------


def test_el_resumen_reproduce_la_ventana_que_se_reparto() -> None:
    """Ida y vuelta: repartir 20 días y volverlos a subir da 20 días.

    Es la garantía de que las dos direcciones son la misma cifra vista desde
    dos lados, no dos cálculos que pueden discrepar.
    """
    colocaciones = repartir_secuencial(
        hojas=_hojas(), ventana_dias=Decimal(20), inicio=INICIO
    )
    por_id = {c.actividad_id: c for c in colocaciones}
    hojas = [
        HojaProgramable(
            **{
                **_campos(hoja),
                "duracion_dias": por_id[hoja.actividad_id].duracion_dias,
                "fecha_inicio": por_id[hoja.actividad_id].fecha_inicio,
                "fecha_termino": por_id[hoja.actividad_id].fecha_termino,
            }
        )
        for hoja in _hojas()
    ]

    resumenes = {r.nodo_id: r for r in resumir_arbol(nodos=_arbol(), hojas=hojas)}

    for nodo_id in (ETAPA, NIVEL):
        assert resumenes[nodo_id].duracion_dias == Decimal(20)
        assert resumenes[nodo_id].fecha_inicio == INICIO
        assert resumenes[nodo_id].fecha_termino == colocaciones[-1].fecha_termino


def test_el_resumen_toma_el_inicio_mas_temprano_y_el_fin_mas_tardio() -> None:
    """La barra del padre cubre a todos sus hijos, aunque se traslapen."""
    hojas = [
        HojaProgramable(
            actividad_id=MURO,
            prototipo_nodo_id=NODO_MURO,
            importe=IMPORTE_MURO,
            duracion_dias=Decimal(10),
            fecha_inicio=date(2026, 3, 9),
            fecha_termino=date(2026, 3, 19),
        ),
        HojaProgramable(
            actividad_id=CASTILLO,
            prototipo_nodo_id=NODO_CASTILLO,
            importe=IMPORTE_CASTILLO,
            duracion_dias=Decimal(5),
            fecha_inicio=date(2026, 3, 2),
            fecha_termino=date(2026, 3, 7),
        ),
    ]

    resumen = {r.nodo_id: r for r in resumir_arbol(nodos=_arbol(), hojas=hojas)}[NIVEL]

    assert resumen.fecha_inicio == date(2026, 3, 2)
    assert resumen.fecha_termino == date(2026, 3, 19)
    # Span de calendario (17 días) y no la suma de trabajo (15): se traslapan.
    assert resumen.duracion_dias == Decimal(17)
    assert resumen.duracion_hojas_dias == Decimal(15)


def test_el_avance_del_resumen_es_ponderado_por_importe() -> None:
    """El muro de $122k en 0 % y el castillo de $10k al 100 % no son 50 %."""
    hojas = [
        HojaProgramable(
            actividad_id=MURO,
            prototipo_nodo_id=NODO_MURO,
            importe=IMPORTE_MURO,
            avance_pct=Decimal(0),
        ),
        HojaProgramable(
            actividad_id=CASTILLO,
            prototipo_nodo_id=NODO_CASTILLO,
            importe=IMPORTE_CASTILLO,
            avance_pct=Decimal(100),
        ),
    ]

    resumen = {r.nodo_id: r for r in resumir_arbol(nodos=_arbol(), hojas=hojas)}[NIVEL]

    esperado = (Decimal(100) * IMPORTE_CASTILLO / (IMPORTE_MURO + IMPORTE_CASTILLO)).quantize(
        Decimal("0.01")
    )
    assert resumen.avance_pct == esperado
    assert resumen.avance_pct < Decimal(10)


def test_sin_importes_el_avance_cae_al_promedio_simple() -> None:
    hojas = [
        HojaProgramable(actividad_id=MURO, prototipo_nodo_id=NODO_MURO, avance_pct=Decimal(0)),
        HojaProgramable(
            actividad_id=CASTILLO, prototipo_nodo_id=NODO_CASTILLO, avance_pct=Decimal(100)
        ),
    ]

    resumen = {r.nodo_id: r for r in resumir_arbol(nodos=_arbol(), hojas=hojas)}[NIVEL]
    assert resumen.avance_pct == Decimal("50.00")


def test_el_resumen_sube_por_todos_los_ancestros() -> None:
    """La etapa resume lo que hay debajo de sus niveles, no sólo lo directo."""
    resumenes = {r.nodo_id: r for r in resumir_arbol(nodos=_arbol(), hojas=_hojas())}

    assert set(resumenes[ETAPA].actividades) == {MURO, CASTILLO, CADENA}
    assert set(resumenes[NIVEL].actividades) == {MURO, CASTILLO, CADENA}
    assert resumenes[ETAPA].importe == IMPORTE_MURO + IMPORTE_CASTILLO + IMPORTE_CADENA
    assert resumenes[ETAPA].profundidad == 0
    assert resumenes[NIVEL].profundidad == 1


def test_las_hojas_tambien_traen_su_propio_resumen() -> None:
    """El nodo `concepto` es su propia hoja: el Gantt necesita su renglón."""
    resumenes = {r.nodo_id: r for r in resumir_arbol(nodos=_arbol(), hojas=_hojas())}
    assert resumenes[NODO_MURO].actividades == (MURO,)
    assert resumenes[NODO_MURO].tipo is ClaseNodo.CONCEPTO


def test_un_nodo_sin_hojas_no_produce_barra() -> None:
    """Una rama vacía del árbol no estorba el Gantt con una barra de nada."""
    arbol = [
        *_arbol(),
        NodoWBS(id="n-vacio", tipo=ClaseNodo.NIVEL, nombre="PLANTA ALTA", parent_id=ETAPA),
    ]
    resumenes = {r.nodo_id for r in resumir_arbol(nodos=arbol, hojas=_hojas())}
    assert "n-vacio" not in resumenes


def test_una_actividad_extra_no_cuelga_de_ningun_nodo() -> None:
    """Un extra de catálogo (§5.1) no nació del prototipo y no rompe el resumen."""
    hojas = [
        *_hojas(),
        HojaProgramable(actividad_id="act-extra", prototipo_nodo_id=None),
    ]
    resumenes = {r.nodo_id: r for r in resumir_arbol(nodos=_arbol(), hojas=hojas)}
    assert "act-extra" not in resumenes[ETAPA].actividades


def test_hojas_por_nodo_detecta_un_arbol_repetido() -> None:
    arbol = [*_arbol(), NodoWBS(id=NIVEL, tipo=ClaseNodo.NIVEL, nombre="Repetido")]
    with pytest.raises(ErrorDeJerarquia, match="dos veces"):
        hojas_por_nodo(arbol, _hojas())


# --- El conflicto padre/hijo (§7.5) --------------------------------------


def test_el_conflicto_se_marca_pero_no_se_resuelve() -> None:
    """20 días capturados en la etapa contra 10+8+5 = 23 de los conceptos."""
    hojas = [
        HojaProgramable(
            actividad_id=MURO,
            prototipo_nodo_id=NODO_MURO,
            importe=IMPORTE_MURO,
            duracion_dias=Decimal(10),
        ),
        HojaProgramable(
            actividad_id=CASTILLO,
            prototipo_nodo_id=NODO_CASTILLO,
            importe=IMPORTE_CASTILLO,
            duracion_dias=Decimal(8),
        ),
        HojaProgramable(
            actividad_id=CADENA,
            prototipo_nodo_id=NODO_CADENA,
            importe=IMPORTE_CADENA,
            duracion_dias=Decimal(5),
        ),
    ]

    resumen = {
        r.nodo_id: r
        for r in resumir_arbol(
            nodos=_arbol(), hojas=hojas, ventanas={ETAPA: Decimal(20)}
        )
    }[ETAPA]

    assert resumen.conflicto is not None
    assert resumen.conflicto.dias_capturados == Decimal(20)
    assert resumen.conflicto.dias_derivados == Decimal(23)
    assert set(resumen.conflicto.actividades) == {MURO, CASTILLO, CADENA}
    # Ninguna de las dos cifras se corrigió: el resumen sigue diciendo lo de
    # los hijos y la ventana sigue diciendo 20. Decide el usuario.
    assert resumen.duracion_hojas_dias == Decimal(23)


def test_no_hay_conflicto_cuando_las_cifras_cuadran() -> None:
    hojas = [
        HojaProgramable(
            actividad_id=MURO, prototipo_nodo_id=NODO_MURO, duracion_dias=Decimal(12)
        ),
        HojaProgramable(
            actividad_id=CASTILLO,
            prototipo_nodo_id=NODO_CASTILLO,
            duracion_dias=Decimal(8),
        ),
    ]
    resumen = {
        r.nodo_id: r
        for r in resumir_arbol(
            nodos=_arbol(), hojas=hojas, ventanas={ETAPA: Decimal(20)}
        )
    }[ETAPA]
    assert resumen.conflicto is None


def test_una_obra_recien_generada_no_dispara_conflictos() -> None:
    """Todas las hojas en su día por defecto: nadie capturó nada todavía.

    Es el caso que hace inútil un aviso mal calibrado: tres conceptos suman 3
    días contra la ventana de 20 y, sin este guardia, cada etapa de cada obra
    nueva saldría en conflicto la primera vez que alguien abre la pantalla.
    """
    resumenes = resumir_arbol(
        nodos=_arbol(), hojas=_hojas(), ventanas={ETAPA: Decimal(20)}
    )
    assert all(r.conflicto is None for r in resumenes)


def test_el_conflicto_solo_lista_las_hojas_capturadas() -> None:
    hojas = [
        HojaProgramable(
            actividad_id=MURO, prototipo_nodo_id=NODO_MURO, duracion_dias=Decimal(10)
        ),
        HojaProgramable(actividad_id=CASTILLO, prototipo_nodo_id=NODO_CASTILLO),
    ]
    resumen = {
        r.nodo_id: r
        for r in resumir_arbol(
            nodos=_arbol(), hojas=hojas, ventanas={ETAPA: Decimal(20)}
        )
    }[ETAPA]

    assert resumen.conflicto is not None
    assert resumen.conflicto.actividades == (MURO,)


def test_con_fechas_el_conflicto_se_mide_contra_el_span() -> None:
    """Dos hojas en paralelo ocupan menos calendario que la suma de su trabajo."""
    hojas = [
        HojaProgramable(
            actividad_id=MURO,
            prototipo_nodo_id=NODO_MURO,
            duracion_dias=Decimal(10),
            fecha_inicio=INICIO,
            fecha_termino=date(2026, 3, 12),
        ),
        HojaProgramable(
            actividad_id=CASTILLO,
            prototipo_nodo_id=NODO_CASTILLO,
            duracion_dias=Decimal(8),
            fecha_inicio=INICIO,
            fecha_termino=date(2026, 3, 10),
        ),
    ]
    resumen = {
        r.nodo_id: r
        for r in resumir_arbol(
            nodos=_arbol(), hojas=hojas, ventanas={ETAPA: Decimal(20)}
        )
    }[ETAPA]

    assert resumen.conflicto is not None
    # Span de 10 días, no los 18 de trabajo.
    assert resumen.conflicto.dias_derivados == Decimal(10)


def test_un_nodo_sin_ventana_capturada_nunca_esta_en_conflicto() -> None:
    hojas = [
        HojaProgramable(
            actividad_id=MURO, prototipo_nodo_id=NODO_MURO, duracion_dias=Decimal(99)
        )
    ]
    resumenes = resumir_arbol(nodos=_arbol(), hojas=hojas)
    assert all(r.conflicto is None for r in resumenes)


def test_es_captura_manual_reconoce_la_huella_de_la_captura() -> None:
    assert not es_captura_manual(
        duracion_dias=Decimal(1), fecha_inicio=None, fecha_termino=None
    )
    assert es_captura_manual(
        duracion_dias=Decimal(5), fecha_inicio=None, fecha_termino=None
    )
    assert es_captura_manual(
        duracion_dias=Decimal(1), fecha_inicio=INICIO, fecha_termino=None
    )


# --- Profundidad de captura (§7.5, migración 0041) -----------------------


def test_los_nodos_capturables_salen_del_tipo_y_no_de_la_distancia() -> None:
    """Elegir "por etapa" da las etapas, no "todo lo que esté a un nivel"."""
    arbol = _arbol()
    assert nodos_capturables(arbol, ClaseNodo.ETAPA) == (ETAPA,)
    assert nodos_capturables(arbol, ClaseNodo.NIVEL) == (NIVEL,)
    assert nodos_capturables(arbol, ClaseNodo.CONCEPTO) == (
        NODO_MURO,
        NODO_CASTILLO,
        NODO_CADENA,
    )


def test_la_profundidad_no_es_una_jaula() -> None:
    """La sugerencia dice dónde arrancar; el árbol completo sigue disponible."""
    resumenes = resumir_arbol(nodos=_arbol(), hojas=_hojas())
    profundidades = {r.nodo_id: r.profundidad for r in resumenes}

    # Aunque la captura sugerida sea por etapa, los conceptos siguen teniendo
    # su renglón y su profundidad para que el editor pueda bajar a ellos.
    assert profundidades[NODO_MURO] == 2
    assert set(nodos_capturables(_arbol(), ClaseNodo.ETAPA)) < set(profundidades)
