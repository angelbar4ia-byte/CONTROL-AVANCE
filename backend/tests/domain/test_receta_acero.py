"""La receta del acero (varillas, armex, cortes, anillos por zonas, alambre y cimbra) contra los números del mockup.

Las cifras esperadas salen de correr las funciones `corteDe` y `muestra` de `app.js` del mockup (v47) con los drivers
por defecto; el catálogo se cita donde lo contradice («diferencia conocida»: no se fuerzan los números).
"""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.receta_acero import (
    Armex,
    ConsumoDeCimbra,
    DriversDeReceta,
    EntradaRecetaAcero,
    ErrorDeRecetaAcero,
    GrupoDeVarillas,
    Varilla,
    ZonaDeAnillo,
    calcular_receta_acero,
    corte_de,
    diametro_de_varilla_m,
)

# Insumos del catálogo (CATALOGO_DE_MATERIALES.csv; pesos de la especificación del mockup).
V3 = Varilla("ACR-00001", 3, 12.0, 0.56)  # varilla 3/8
V4 = Varilla("ACR-00002", 4, 12.0, 0.994)  # varilla 1/2
V5 = Varilla("ACR-00003", 5, 12.0, 1.552)  # varilla 5/8
V6 = Varilla("ACR-00004", 6, 12.0, 2.235)  # varilla 3/4
ARMEX_10X10 = Armex("ACE-00011", 6.0)  # sin peso en el catálogo
ARMEX_10X15 = Armex("ACE-00020", 6.0)
PESO_ANILLO = 0.249  # kg/m (supuesto de la especificación)

# Tabla de cortes del mockup (alto, piezas, módulo, material cortado, alto que cubre), corteDe con los drivers por
# defecto: armex de 6 m (traslape 15 cm, puntas 50 cm) y varilla 3/8 de 12 m (traslape y puntas de 40 diámetros).
TABLA_ARMEX = [
    (2.0, 1, 3.0, 3.0, 2.5),
    (2.25, 1, 3.0, 3.0, 2.5),
    (2.5, 1, 3.0, 3.0, 2.5),
    (2.75, 1, 4.0, 4.0, 3.5),
    (3.0, 1, 4.0, 4.0, 3.5),
    (3.25, 1, 4.0, 4.0, 3.5),
    (3.5, 1, 4.0, 4.0, 3.5),
    (3.75, 1, 6.0, 6.0, 5.5),
    (4.0, 1, 6.0, 6.0, 5.5),
    (4.5, 1, 6.0, 6.0, 5.5),
    (5.0, 1, 6.0, 6.0, 5.5),
    (5.5, 1, 6.0, 6.0, 5.5),
    (5.75, 2, 4.0, 8.0, 7.35),
    (6.0, 2, 4.0, 8.0, 7.35),
]
TABLA_VARILLA_3_8 = [
    (2.0, 1, 3.0, 3.0, 2.238),
    (2.25, 1, 4.0, 4.0, 3.238),
    (2.5, 1, 4.0, 4.0, 3.238),
    (3.0, 1, 4.0, 4.0, 3.238),
    (3.25, 1, 6.0, 6.0, 5.238),
    (4.0, 1, 6.0, 6.0, 5.238),
    (5.0, 1, 6.0, 6.0, 5.238),
    (5.25, 2, 4.0, 8.0, 6.857),
    (6.0, 2, 4.0, 8.0, 6.857),
]


def _anillos(sep: float, peso: float = PESO_ANILLO, len_cm: float | None = None) -> ZonaDeAnillo:
    return ZonaDeAnillo(sep_cm=sep, peso_kg_m=peso, len_cm=len_cm)


# ---------------------------------------------------------------- regla de cortes


@pytest.mark.parametrize(("alto", "n", "modulo", "total", "cubre"), TABLA_ARMEX)
def test_tabla_de_cortes_del_armex_de_castillo(
    alto: float, n: int, modulo: float, total: float, cubre: float
) -> None:
    c = corte_de(alto, 6.0, 0.15, 0.5)
    assert (c.n, c.modulo_m) == (n, modulo)
    assert c.total_m == pytest.approx(total)
    assert c.alto_que_cubre_m == pytest.approx(cubre, abs=1e-3)
    assert c.cubre_completo and not c.excede_maximo


@pytest.mark.parametrize(("alto", "n", "modulo", "total", "cubre"), TABLA_VARILLA_3_8)
def test_tabla_de_cortes_de_la_varilla_de_3_8(
    alto: float, n: int, modulo: float, total: float, cubre: float
) -> None:
    dm = diametro_de_varilla_m(3)
    c = corte_de(alto, 12.0, 40 * dm, 80 * dm)
    assert (c.n, c.modulo_m) == (n, modulo)
    assert c.total_m == pytest.approx(total)
    assert c.alto_que_cubre_m == pytest.approx(cubre, abs=1e-3)


def test_los_modulos_se_limitan_a_los_que_caben_en_la_barra() -> None:
    # Barra de 3 m: no se puede cortar un módulo de 4 ni de 6.
    c = corte_de(2.0, 3.0, 0.15, 0.5)
    assert c.modulo_m <= 3.0


def test_el_maximo_de_piezas_se_respeta_y_solo_se_pasa_si_no_hay_solucion() -> None:
    # 17 m con barras de 6 m: 3 piezas de 6 m cubren 18 − 0.3 = 17.7 m: cabe en el máximo de 3.
    c = corte_de(17.0, 6.0, 0.15, 0.0)
    assert c.n == 3 and not c.excede_maximo
    # Con un máximo de 2 no hay solución: se pasa del máximo (3 piezas) y se avisa.
    c2 = corte_de(17.0, 6.0, 0.15, 0.0, DriversDeReceta(max_piezas_corte=2))
    assert c2.n == 3 and c2.excede_maximo and c2.cubre_completo
    # 30 m tampoco caben en 3 piezas.
    c3 = corte_de(30.0, 6.0, 0.15, 0.0)
    assert c3.n == 8 and c3.modulo_m == 4.0 and c3.excede_maximo  # gana el que gasta menos material (32 m)


def test_la_tolerancia_acepta_una_falta_sin_pasar_al_corte_siguiente() -> None:
    # Armex de castillo de 2.60 m: necesita 3.10 m con las puntas; el módulo de 3 m se queda 10 cm corto.
    assert corte_de(2.6, 6.0, 0.15, 0.5).modulo_m == 4.0
    assert corte_de(2.6, 6.0, 0.15, 0.5, DriversDeReceta(tolerancia_corte_cm=10.0)).modulo_m == 3.0
    assert corte_de(2.6, 6.0, 0.15, 0.5, DriversDeReceta(tolerancia_corte_cm=9.0)).modulo_m == 4.0


def test_ningun_modulo_cabe_en_una_barra_chica() -> None:
    with pytest.raises(ErrorDeRecetaAcero):
        corte_de(2.0, 0.5, 0.1, 0.1)


# ---------------------------------------------------------------- castillo K-1 con armex (por pieza)


def _k1(alto: float) -> dict:
    return calcular_receta_acero(
        EntradaRecetaAcero(
            forma="castillo",
            ancho_cm=15,
            peralte_cm=15,
            longitud_m=alto,
            lados_cimbra=2,
            armex=ARMEX_10X10,
            alambre_kg_ml=0.02,
            cimbra=[
                ConsumoDeCimbra("ACE-00012", por_ml=0.017021),
                ConsumoDeCimbra("ACE-00013", por_ml=0.02),
                ConsumoDeCimbra("MAD-00004", por_ml=0.01),
                ConsumoDeCimbra("ACE-00001", por_ml=0.210987),
            ],
        )
    )


def test_k1_de_2_6_m_corta_un_armex_de_4_m() -> None:
    r = _k1(2.6)
    assert r["unidad"] == "pza"
    assert r["armex"]["corte"]["modulo_m"] == 4.0 and r["armex"]["corte"]["piezas"] == 1
    assert r["armex"]["ml"] == pytest.approx(4.0)
    assert r["armex"]["piezas_comerciales"] == pytest.approx(4 / 6)
    assert r["alambre"]["kg"] == pytest.approx(0.052)
    assert r["cimbra"]["m2"] == pytest.approx(0.78)
    consumos = {c["clave"]: c["cantidad"] for c in r["cimbra"]["consumos"]}
    assert consumos["ACE-00012"] == pytest.approx(0.044255, abs=1e-6)
    assert consumos["ACE-00001"] == pytest.approx(0.548566, abs=1e-6)
    assert consumos["MAD-00004"] == pytest.approx(0.026)


def test_k1_de_4_2_m_usa_una_pieza_completa_de_armex() -> None:
    r = _k1(4.2)
    assert r["armex"]["corte"]["modulo_m"] == 6.0
    assert r["armex"]["piezas_comerciales"] == pytest.approx(1.0)
    assert r["armex"]["ml"] == pytest.approx(6.0)
    assert r["cimbra"]["m2"] == pytest.approx(1.26)


def test_el_armex_sin_peso_avisa_y_deja_los_kg_sin_dato() -> None:
    r = _k1(2.6)
    assert r["armex"]["kg"] is None
    assert r["acero_kg_completo"] is False
    assert any("peso" in a for a in r["advertencias"])


def test_k1_para_varias_piezas_redondea_las_piezas_comerciales_hacia_arriba() -> None:
    e = EntradaRecetaAcero(
        forma="castillo", ancho_cm=15, peralte_cm=15, longitud_m=2.6, lados_cimbra=2, armex=ARMEX_10X10, cantidad=10
    )
    (t,) = calcular_receta_acero(e)["totales"]
    assert t["cantidad_exacta"] == pytest.approx(10 * 4 / 6)
    assert t["cantidad_a_comprar"] == 7.0


# ---------------------------------------------------------------- castillo K-2 y columna C-1 (varillas y anillos)


def _k2(alto: float) -> dict:
    return calcular_receta_acero(
        EntradaRecetaAcero(
            forma="castillo",
            ancho_cm=15,
            peralte_cm=15,
            longitud_m=alto,
            lados_cimbra=2,
            varillas=[GrupoDeVarillas(4, V3)],
            anillos=[_anillos(20)],
        )
    )


def test_k2_de_2_6_m_varillas_anillos_y_alambre() -> None:
    r = _k2(2.6)
    (v,) = r["varillas"]
    assert v["corte"]["piezas"] == 1 and v["corte"]["modulo_m"] == 4.0
    assert v["ml"] == pytest.approx(16.0)
    assert v["kg"] == pytest.approx(8.96)
    assert v["piezas_comerciales"] == pytest.approx(16 / 12)
    a = r["anillos"]
    assert a["largo_anillo_m"] == pytest.approx(0.5)  # 2 × (10 + 10) cm + 10 cm de gancho
    assert a["pza"] == 14  # ceil(2.6 / 0.20) + 1
    assert a["kg"] == pytest.approx(1.743)
    assert r["alambre"]["kg"] == pytest.approx(0.1596)  # 4 varillas × 14 anillos × 0.3 m × 0.0095 kg/m


def test_k2_de_6_m_traslapa_dos_piezas_de_4_m() -> None:
    r = _k2(6.0)
    (v,) = r["varillas"]
    assert v["corte"]["piezas"] == 2 and v["corte"]["modulo_m"] == 4.0
    assert v["kg"] == pytest.approx(17.92)
    assert r["anillos"]["pza"] == 31
    assert r["anillos"]["kg"] == pytest.approx(3.8595)
    assert r["desperdicio"]["traslape_m"] == pytest.approx(4 * 0.381)
    assert r["desperdicio"]["puntas_m"] == pytest.approx(4 * 0.762)


def test_columna_c1_de_4_2_m() -> None:
    r = calcular_receta_acero(
        EntradaRecetaAcero(
            forma="castillo",
            ancho_cm=30,
            peralte_cm=30,
            longitud_m=4.2,
            lados_cimbra=4,
            varillas=[GrupoDeVarillas(8, V4)],
            anillos=[_anillos(15)],
            cimbra=[ConsumoDeCimbra("MAD-00004", por_ml=0.01)],
        )
    )
    (v,) = r["varillas"]
    assert v["corte"]["piezas"] == 1 and v["corte"]["modulo_m"] == 6.0
    assert v["ml"] == pytest.approx(48.0)
    assert v["kg"] == pytest.approx(47.712)
    assert v["piezas_comerciales"] == pytest.approx(4.0)
    assert r["anillos"]["largo_anillo_m"] == pytest.approx(1.1)  # 2 × (25 + 25) cm + 10 cm
    assert r["anillos"]["pza"] == 29
    assert r["anillos"]["kg"] == pytest.approx(7.9431)
    assert r["alambre"]["kg"] == pytest.approx(0.6612)
    assert r["cimbra"]["m2"] == pytest.approx(5.04)  # perímetro de 4 lados × 4.2 m
    assert r["cimbra"]["consumos"][0]["cantidad"] == pytest.approx(0.042)
    assert r["acero_kg"] == pytest.approx(47.712 + 7.9431)
    assert r["acero_kg_completo"] is True


# ---------------------------------------------------------------- trabes: por metro y por pieza con zonas


def _trabe(forma: str, anillos: list[ZonaDeAnillo], largo: float | None = None) -> dict:
    return calcular_receta_acero(
        EntradaRecetaAcero(
            forma=forma,  # type: ignore[arg-type]
            ancho_cm=15,
            peralte_cm=25,
            longitud_m=largo,
            lados_cimbra=3,
            varillas=[GrupoDeVarillas(2, V3, "arriba"), GrupoDeVarillas(2, V3, "abajo")],
            anillos=anillos,
            gancho_cm=16.5,
            factor_anillo=1.1,
            alambre_kg_ml=0.216437,
            cimbra=[ConsumoDeCimbra("MAD-00001", por_m2=1.0)],
        )
    )


def test_trabe_t1_15x25_por_ml_coincide_con_el_catalogo_en_anillos_y_alambre() -> None:
    r = _trabe("ml", [_anillos(25)])
    assert r["unidad"] == "ml"
    # Anillo 10×20 del núcleo: perímetro 60 cm × 1.10 + 16.5 cm = 0.825 m.
    assert r["anillos"]["largo_anillo_m"] == pytest.approx(0.825)
    assert r["anillos"]["pza"] == pytest.approx(4.0)
    assert r["anillos"]["kg"] == pytest.approx(0.8217)  # igual al ACE-00005 de AUX-00008 del catálogo
    assert r["alambre"]["kg"] == pytest.approx(0.216437)
    assert r["cimbra"]["m2"] == pytest.approx(0.65)  # 2 × 0.25 + 0.15
    assert r["cimbra"]["consumos"][0]["cantidad"] == pytest.approx(0.65)
    # Varillas por ml: factor L / (L − traslape) = 12 / (12 − 0.381).
    for v in r["varillas"]:
        assert v["ml"] == pytest.approx(2 * 12 / (12 - 40 * diametro_de_varilla_m(3)))
        assert v["corte"] is None
    assert r["acero_kg"] == pytest.approx(2.313452 + 0.8217, abs=1e-5)


def test_trabe_por_pieza_con_zonas_de_anillo_en_los_extremos() -> None:
    zonas = [_anillos(10, len_cm=50), _anillos(25)]
    r = _trabe("pieza", zonas, largo=4.0)
    assert r["unidad"] == "pza"
    z_ext, z_centro = r["anillos"]["zonas"]
    # Extremos: 50 cm en cada punta = 1.00 m a 10 cm → 10 + 1 anillos; centro: 4 − 1 = 3 m a 25 cm → 12.
    assert (z_ext["largo_m"], z_ext["pza"]) == (pytest.approx(1.0), 11)
    assert (z_centro["largo_m"], z_centro["pza"]) == (pytest.approx(3.0), 12)
    assert r["anillos"]["pza"] == 23
    assert r["anillos"]["kg"] == pytest.approx(4.724775)
    for v in r["varillas"]:
        assert v["corte"]["piezas"] == 1 and v["corte"]["modulo_m"] == 6.0
        assert v["ml"] == pytest.approx(2 * 6.0)
    assert r["acero_kg"] == pytest.approx(13.44 + 4.724775)
    assert r["alambre"]["kg"] == pytest.approx(0.865748)  # kg por ml × 4 m
    assert r["cimbra"]["m2"] == pytest.approx(2.6)


def test_zonas_fijas_que_rebasan_el_largo_avisan() -> None:
    r = _trabe("pieza", [_anillos(10, len_cm=150), _anillos(25)], largo=2.0)
    assert any("rebasan" in a for a in r["advertencias"])


# ---------------------------------------------------------------- armex en tramo continuo y drivers


def test_armex_en_un_ml_usa_el_traslape_de_15_cm() -> None:
    r = calcular_receta_acero(
        EntradaRecetaAcero(forma="ml", ancho_cm=15, peralte_cm=20, lados_cimbra=2, armex=ARMEX_10X15, alambre_kg_ml=0.1)
    )
    assert r["armex"]["piezas_comerciales"] == pytest.approx(1 / (6 - 0.15))  # 0.1709 pza por metro
    assert r["armex"]["corte"] is None
    assert r["alambre"]["kg"] == pytest.approx(0.1)


def test_un_driver_distinto_cambia_el_corte() -> None:
    base = calcular_receta_acero(
        EntradaRecetaAcero(forma="castillo", ancho_cm=15, peralte_cm=15, longitud_m=2.6, armex=ARMEX_10X10)
    )
    sin_puntas = calcular_receta_acero(
        EntradaRecetaAcero(
            forma="castillo",
            ancho_cm=15,
            peralte_cm=15,
            longitud_m=2.6,
            armex=ARMEX_10X10,
            drivers=DriversDeReceta(puntas_armex_cm=0),
        )
    )
    assert base["armex"]["corte"]["modulo_m"] == 4.0
    assert sin_puntas["armex"]["corte"]["modulo_m"] == 3.0
    assert sin_puntas["drivers"]["puntas_armex_cm"] == 0


def test_el_desperdicio_de_acero_multiplica_las_varillas() -> None:
    e = EntradaRecetaAcero(
        forma="castillo",
        ancho_cm=15,
        peralte_cm=15,
        longitud_m=2.6,
        varillas=[GrupoDeVarillas(4, V3)],
        drivers=DriversDeReceta(desperdicio_acero_pct=5.0),
    )
    assert calcular_receta_acero(e)["varillas"][0]["kg"] == pytest.approx(8.96 * 1.05)


@pytest.mark.parametrize(
    "campo",
    ["traslape_armex_cm", "traslape_varilla_diametros", "puntas_armex_cm", "tolerancia_corte_cm"],
)
def test_los_drivers_negativos_se_rechazan(campo: str) -> None:
    with pytest.raises(ErrorDeRecetaAcero):
        DriversDeReceta(**{campo: -1.0})  # type: ignore[arg-type]


def test_el_maximo_de_piezas_va_de_1_a_12() -> None:
    for malo in (0, 13):
        with pytest.raises(ErrorDeRecetaAcero):
            DriversDeReceta(max_piezas_corte=malo)


@pytest.mark.parametrize(
    "cambio",
    [
        {"ancho_cm": 0},
        {"longitud_m": None},
        {"longitud_m": 31},
        {"lados_cimbra": 5},
        {"cantidad": 0},
        {"recubrimiento_cm": 9},
    ],
)
def test_entradas_invalidas_se_rechazan(cambio: dict) -> None:
    base = {"forma": "castillo", "ancho_cm": 15, "peralte_cm": 15, "longitud_m": 2.6, "armex": ARMEX_10X10}
    with pytest.raises(ErrorDeRecetaAcero):
        calcular_receta_acero(EntradaRecetaAcero(**{**base, **cambio}))  # type: ignore[arg-type]


def test_armex_y_varillas_a_la_vez_se_rechazan() -> None:
    with pytest.raises(ErrorDeRecetaAcero):
        calcular_receta_acero(
            EntradaRecetaAcero(
                forma="ml", ancho_cm=15, peralte_cm=15, armex=ARMEX_10X10, varillas=[GrupoDeVarillas(4, V3)]
            )
        )


def test_los_lados_de_cimbra_de_un_castillo() -> None:
    def m2(lados: int) -> float:
        return calcular_receta_acero(
            EntradaRecetaAcero(
                forma="castillo", ancho_cm=15, peralte_cm=30, longitud_m=1.0, lados_cimbra=lados, armex=ARMEX_10X10
            )
        )["cimbra"]["m2"]

    assert m2(0) == 0
    assert m2(1) == pytest.approx(0.30)
    assert m2(2) == pytest.approx(0.60)
    assert m2(3) == pytest.approx(0.75)
    assert m2(4) == pytest.approx(0.90)


# ---------------------------------------------------------------- diferencias conocidas con el catálogo (no se fuerzan)


def test_diferencia_conocida_el_traslape_de_40_diametros_es_menos_que_el_8_por_ciento_del_catalogo() -> None:
    """El catálogo cuenta 8 % de desperdicio en lugar del traslape; los 40 diámetros dan de 3 a 7 %. No se alinean."""
    factores = {}
    for v in (V3, V4, V5, V6):
        lap = 40 * diametro_de_varilla_m(v.numero)
        factores[v.numero] = v.largo_m / (v.largo_m - lap) - 1
    assert min(factores.values()) == pytest.approx(0.0328, abs=1e-3)
    assert max(factores.values()) == pytest.approx(0.0678, abs=1e-3)
    assert all(0.03 < f < 0.08 for f in factores.values())
    # En un ml de trabe el cálculo usa el factor del traslape, no el 8 %.
    r = _trabe("ml", [_anillos(25)])
    assert r["varillas"][0]["ml"] / 2 == pytest.approx(1 + factores[3], rel=1e-4)


def test_diferencia_conocida_el_catalogo_cuenta_anillos_mas_cortos_que_el_perimetro_k3() -> None:
    """EST-10031 (K-3, 6 var. del no. 4 y anillo 10×25 @15 «hasta 6.00 m»): el catálogo da 6.51882 kg de anillo y
    3 pza de varilla de 1/2; el cálculo con el perímetro del núcleo da más. Es un dato del catálogo (pregunta
    abierta), no se corrige el cálculo."""
    r = calcular_receta_acero(
        EntradaRecetaAcero(
            forma="castillo",
            ancho_cm=15,
            peralte_cm=30,
            longitud_m=6.0,
            lados_cimbra=2,
            varillas=[GrupoDeVarillas(6, V4)],
            anillos=[_anillos(15)],
            alambre_kg_ml=0.17296,
        )
    )
    catalogo_anillo_kg = 6.51882
    assert r["anillos"]["largo_anillo_m"] == pytest.approx(0.8)  # 2 × (10 + 25) cm = 70 cm + 10 cm de gancho
    assert r["anillos"]["kg"] == pytest.approx(41 * 0.8 * PESO_ANILLO)
    assert r["anillos"]["kg"] > catalogo_anillo_kg * 1.08  # «≠»: pasa de 8 %
    # El largo que implica el catálogo (kg ÷ peso ÷ 40 anillos) es menor que el perímetro del núcleo (0.70 m).
    assert catalogo_anillo_kg / PESO_ANILLO / 40 < 0.70
    # Varilla: el catálogo da 3 pza (6 var × 6 m ÷ 12 m, sin puntas ni traslape); el cálculo corta 2 × 4 m y da 4.
    (v,) = r["varillas"]
    assert v["piezas_comerciales"] == pytest.approx(4.0)
    assert v["piezas_comerciales"] > 3.0 * 1.08
