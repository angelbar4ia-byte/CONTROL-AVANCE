"""Los drivers de la obra conectados con los cálculos de los elementos (Ola 4, «drivers conectados»), sin base de datos.

Tres cosas:

1. **Precedencia**: lo que manda la petición > el driver de la obra > el valor por defecto.
2. **Compatibilidad**: sin `obra_id` el resultado es idéntico al de antes (y no pide sesión ni token).
3. **Registro de consumidores**: cambiando cada driver, uno por uno, el resultado de cada consumidor cambia si y solo si
   `consumidores_de_drivers` dice que lo lee; y ningún driver del catálogo queda sin consumidor (salvo los declarados).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from obractrl.adapters.api.casos_uso import obtener_drivers_de_obra
from obractrl.adapters.api.v1.bastones import router as router_bastones
from obractrl.adapters.api.v1.biblioteca_de_elementos import router as router_biblioteca
from obractrl.adapters.api.v1.elementos_de_estructura import router as router_estructura
from obractrl.adapters.api.v1.elementos_estructurales import router as router_lineal
from obractrl.adapters.api.v1.muros_de_tabique import router as router_tabique
from obractrl.adapters.api.v1.receta_acero import router as router_receta
from obractrl.domain.cuantificacion.cambio_de_unidad import medida_para  # noqa: F401  (el plano lee la altura por aquí)
from obractrl.domain.cuantificacion.colocacion_de_plantilla import colocar_plantilla
from obractrl.domain.cuantificacion.consumidores_de_drivers import (
    CONSUMIDORES,
    SIN_CONSUMIDOR_POR_AHORA,
    consumidores_de,
)
from obractrl.domain.cuantificacion.conversion import conversion_por_defecto
from obractrl.domain.cuantificacion.elementos_lineales import claves_de_elementos_estructurales
from obractrl.domain.cuantificacion.estructura_de_catalogo import ELEMENTOS_DE_ESTRUCTURA
from obractrl.domain.cuantificacion.drivers import CATALOGO_DE_DRIVERS, ValorVigente, definicion_de, resolver
from obractrl.domain.cuantificacion.muro_cimentacion import CORONA_M, ESCARPIO_MINIMO

OBRA = uuid4()


class _DriversDeObra:
    """Hace de `DriversDeObraPerezosos`: los drivers de la obra salen de un diccionario `clave → valor de la obra`."""

    def __init__(self, de_obra: dict[str, str], globales: dict[str, str] | None = None) -> None:
        self.de_obra, self.globales, self.pedidos = de_obra, globales or {}, 0

    async def valores(self, obra_id: UUID | None) -> dict[str, ValorVigente] | None:
        if obra_id is None:
            return None
        self.pedidos += 1
        salida = {}
        for d in CATALOGO_DE_DRIVERS:
            g = self.globales.get(d.clave)
            salida[d.clave] = resolver(
                d,
                valor_global=Decimal(g) if g is not None else None,
                modo_global=None,
                valor_obra=Decimal(self.de_obra[d.clave]) if d.clave in self.de_obra else None,
            )
        return salida


def _cliente(de_obra: dict[str, str], globales: dict[str, str] | None = None) -> TestClient:
    app = FastAPI()
    for r in (router_receta, router_estructura, router_lineal, router_bastones, router_tabique, router_biblioteca):
        app.include_router(r)
    proveedor = _DriversDeObra(de_obra, globales)
    app.dependency_overrides[obtener_drivers_de_obra] = lambda: proveedor
    return TestClient(app)


def _sin_sesion() -> TestClient:
    """La aplicación tal cual, SIN reemplazar la dependencia: sin `obra_id` no debe pedir token ni base de datos."""
    app = FastAPI()
    for r in (router_receta, router_estructura, router_lineal, router_bastones, router_tabique, router_biblioteca):
        app.include_router(r)
    return TestClient(app)


def _usados(r: Any) -> dict[str, dict[str, Any]]:
    assert r.status_code == 200, r.text
    return {u["clave"]: u for u in r.json()["drivers_usados"]}


# --- 1. Precedencia: petición > obra > defecto --------------------------------------------------------------------------------

K1 = "/biblioteca-de-elementos/estructura/EST-02130/calcular"
BA = "/biblioteca-de-elementos/baston/BA-1/calcular"
TRABE = "/biblioteca-de-elementos/estructura-lineal/T-1-15x25/calcular"
RECETA = "/biblioteca-de-elementos/receta-acero/calcular"


def test_castillo_el_driver_de_la_obra_manda_sobre_el_defecto_y_la_peticion_sobre_el_driver() -> None:
    c = _cliente({"traslape_armex_cm": "25", "altura_estandar": "3.5", "desperdicio_concreto": "9"})
    r = c.post(K1, json={"obra_id": str(OBRA)})
    u = _usados(r)
    assert u["traslape_armex_cm"]["valor"] == 25 and u["traslape_armex_cm"]["fuente"] == "obra"
    assert u["altura_estandar"]["valor"] == 3.5 and u["altura_estandar"]["fuente"] == "obra"
    assert u["desperdicio_concreto"]["valor"] == 9 and u["desperdicio_concreto"]["fuente"] == "obra"
    assert u["traslape_varilla_diametros"]["fuente"] == "defecto"
    assert r.json()["alto_m"] == 3.5  # el alto sin pedir es la altura estándar de la obra
    # La petición manda sobre el driver.
    r2 = c.post(K1, json={"obra_id": str(OBRA), "alto_m": 2.8, "drivers": {"traslape_armex_cm": 30}})
    u2 = _usados(r2)
    assert u2["traslape_armex_cm"] == {**u2["traslape_armex_cm"], "valor": 30, "fuente": "peticion"}
    assert "altura_estandar" not in u2 and r2.json()["alto_m"] == 2.8


def test_un_global_editado_cuenta_como_global_y_el_valor_de_partida_como_defecto() -> None:
    c = _cliente({}, globales={"max_piezas_corte": "5"})
    u = _usados(c.post(K1, json={"obra_id": str(OBRA)}))
    assert u["max_piezas_corte"]["valor"] == 5 and u["max_piezas_corte"]["fuente"] == "global"
    assert u["tolerancia_corte_cm"]["fuente"] == "defecto"


def test_la_forjada_conserva_su_alto_fijo_aunque_la_obra_cambie_la_altura_estandar() -> None:
    c = _cliente({"altura_estandar": "3.5"})
    r = c.post("/biblioteca-de-elementos/estructura/EST-07010/calcular", json={"obra_id": str(OBRA)})
    assert r.status_code == 200 and r.json()["alto_m"] == 4.2 and "altura_estandar" not in _usados(r)


def test_baston_toma_traslape_tolerancia_y_maximo_de_la_obra_y_la_peticion_manda() -> None:
    c = _cliente({"traslape_varilla_diametros": "50", "tolerancia_corte_cm": "10", "max_piezas_corte": "4"})
    u = _usados(c.post(BA, json={"obra_id": str(OBRA), "largo_cm": 800}))
    assert (u["traslape_varilla_diametros"]["valor"], u["tolerancia_corte_cm"]["valor"], u["max_piezas_corte"]["valor"]) == (50, 10, 4)
    assert {x["fuente"] for x in u.values()} == {"obra"}
    r = c.post(BA, json={"obra_id": str(OBRA), "largo_cm": 800, "traslape_diametros": 30})
    assert _usados(r)["traslape_varilla_diametros"] == {**_usados(r)["traslape_varilla_diametros"], "valor": 30, "fuente": "peticion"}
    assert r.json()["parametros"]["traslape_diametros"] == 30 and r.json()["parametros"]["tolerancia_corte_cm"] == 10


def test_trabe_toma_el_desperdicio_de_concreto_de_la_obra_y_el_acero_de_la_receta() -> None:
    c = _cliente({"desperdicio_concreto": "12", "desperdicio_acero": "3"})
    r = c.post(TRABE, json={"obra_id": str(OBRA)})
    u = _usados(r)
    assert u["desperdicio_concreto"]["valor"] == 12 and u["desperdicio_acero"]["valor"] == 3
    assert r.json()["concreto"]["desperdicio_pct"] == 12
    r2 = c.post(TRABE, json={"obra_id": str(OBRA), "desperdicio_concreto_pct": 7})
    assert _usados(r2)["desperdicio_concreto"]["fuente"] == "peticion" and r2.json()["concreto"]["desperdicio_pct"] == 7


# --- 2. Compatibilidad: sin obra, igual que hoy -----------------------------------------------------------------------------

CUERPOS = [
    (K1, {"alto_m": 3.0}),
    (K1, {}),
    ("/biblioteca-de-elementos/estructura/EST-02140/calcular", {"alto_m": 7.0, "drivers": {"tolerancia_corte_cm": 5}}),
    (TRABE, {"desperdicio_concreto_pct": 8}),
    (BA, {"trazo_m": 10, "largo_cm": 800}),
    (RECETA, {"forma": "castillo", "ancho_cm": 15, "peralte_cm": 15, "longitud_m": 2.6, "varillas": [{"clave": "ACR-00001", "numero": 3, "peso_kg_m": 0.56, "cantidad": 4}], "anillos": [{"sep_cm": 20, "peso_kg_m": 0.249}]}),
]


@pytest.mark.parametrize(("ruta", "cuerpo"), CUERPOS)
def test_sin_obra_el_calculo_es_identico_y_no_pide_sesion_ni_token(ruta: str, cuerpo: dict[str, Any]) -> None:
    sin_sesion = _sin_sesion().post(ruta, json=cuerpo)
    con_proveedor = _cliente({"altura_estandar": "9", "desperdicio_concreto": "30", "traslape_armex_cm": "90"}).post(ruta, json=cuerpo)
    assert sin_sesion.status_code == con_proveedor.status_code
    if sin_sesion.status_code == 200:
        assert sin_sesion.json() == con_proveedor.json()  # los drivers de una obra no se cuelan si la petición no trae `obra_id`
        assert all(u["fuente"] in ("defecto", "peticion") for u in sin_sesion.json()["drivers_usados"])


def test_con_la_obra_en_valores_de_partida_el_resultado_es_el_mismo_que_sin_obra() -> None:
    c = _cliente({})
    for ruta, cuerpo in CUERPOS[:5]:
        a, b = c.post(ruta, json=cuerpo).json(), c.post(ruta, json={**cuerpo, "obra_id": str(OBRA)}).json()
        a.pop("drivers_usados"), b.pop("drivers_usados")
        assert a == b


# --- 3. El tabique de 14 cm no usa desperdicio_mamposteria (M-105) ------------------------------------------------------------


def test_el_tabique_no_aplica_el_driver_de_desperdicio_de_mamposteria() -> None:
    cuerpo = {"cantidad": 10}
    a = _cliente({}).post("/biblioteca-de-elementos/tabique/EST-02010/calcular", json=cuerpo).json()
    b = _cliente({"desperdicio_mamposteria": "40"}).post("/biblioteca-de-elementos/tabique/EST-02010/calcular", json={**cuerpo}).json()
    assert a == b and a["parametros"]["desperdicio_de_pieza_pct"] == 12 and a["parametros"]["desperdicio_de_mezcla_pct"] == 5


def test_los_cimientos_de_piedra_leen_el_escarpio_y_la_corona_como_constantes_iguales_a_los_drivers_fijos() -> None:
    assert Decimal(str(ESCARPIO_MINIMO)) == definicion_de("escarpio_minimo").inicial
    assert Decimal(str(CORONA_M * 100)) == definicion_de("corona_cimiento_cm").inicial
    assert definicion_de("escarpio_minimo").modo_inicial == definicion_de("corona_cimiento_cm").modo_inicial == "fijo"


# --- 4. El registro de consumidores es verdad en los dos sentidos ------------------------------------------------------------

_PERTURBADOS = {
    "altura_estandar": "3.5",
    "separacion_castillos": "2.0",
    "desperdicio_mamposteria": "9",
    "desperdicio_concreto": "9",
    "traslape_armex_cm": "30",
    "traslape_varilla_diametros": "60",
    "desperdicio_acero": "4",
    "puntas_inferior_diametros": "60",
    "puntas_superior_diametros": "60",
    "puntas_armex_cm": "80",
    "tolerancia_corte_cm": "40",
    "max_piezas_corte": "2",
}
"""Un valor de obra distinto del de partida y dentro de los límites del driver (los fijos no se ajustan por obra)."""

_BASES_DE_PRUEBA: dict[str, list[tuple[str, dict[str, Any]]]] = {
    # Escenarios donde cada driver del consumidor tiene efecto: varillas largas y armex, varios cortes, altura sin pedir.
    "estructura": [
        (f"/biblioteca-de-elementos/estructura/{k}/calcular", cuerpo)
        for k in ELEMENTOS_DE_ESTRUCTURA
        for cuerpo in ({}, {"alto_m": 7.0}, {"alto_m": 11.5})
    ],
    "estructura_lineal": [
        (f"/biblioteca-de-elementos/estructura-lineal/{k}/calcular", cuerpo)
        for k in claves_de_elementos_estructurales()
        for cuerpo in (
            ({"modo": "pieza"}, {"modo": "pieza", "alto_m": 11.0}) if k == "C-1"
            else ({"modo": "pieza"},) if k == "Z-1"
            else ({"modo": "pieza"}, {"modo": "pieza", "largo_m": 9.0}, {"modo": "pieza", "largo_m": 14.0})
        )
    ],
    "receta_acero": [
        (
            RECETA,
            {
                "forma": "castillo", "ancho_cm": 15, "peralte_cm": 25, "longitud_m": largo,
                "varillas": [{"clave": "ACR-00001", "numero": 4, "peso_kg_m": 0.99, "cantidad": 4, "largo_m": 12.0}],
                "anillos": [{"sep_cm": 20, "peso_kg_m": 0.22}],
            },
        )
        for largo in (3.0, 7.0, 16.0)
    ]
    + [
        (RECETA, {"forma": "castillo", "ancho_cm": 15, "peralte_cm": 25, "longitud_m": largo, "armex": {"clave": "ACE-00020", "largo_m": 6.0, "peso_kg_m": 0.7}})
        for largo in (3.0, 7.0, 16.0)
    ],
    "baston": [(BA, {"trazo_m": 10, "largo_cm": largo, "varilla_numero": 3}) for largo in (120, 400, 900, 1350, 1700)],
}


def _resultados(consumidor: str, de_obra: dict[str, str]) -> list[Any]:
    c = _cliente(de_obra)
    salida = []
    for ruta, cuerpo in _BASES_DE_PRUEBA[consumidor]:
        r = c.post(ruta, json={**cuerpo, "obra_id": str(OBRA)})
        assert r.status_code == 200, (ruta, cuerpo, r.text)
        j = r.json()
        j.pop("drivers_usados")
        salida.append(j)
    return salida


@pytest.mark.parametrize("consumidor", sorted(_BASES_DE_PRUEBA))
def test_cada_consumidor_lee_exactamente_los_drivers_que_el_registro_dice(consumidor: str) -> None:
    registrado = next(c for c in CONSUMIDORES if c.id == consumidor)
    base = _resultados(consumidor, {})
    for d in CATALOGO_DE_DRIVERS:
        if d.modo_inicial == "fijo":
            continue
        cambia = _resultados(consumidor, {d.clave: _PERTURBADOS[d.clave]}) != base
        assert cambia == (d.clave in registrado.claves), (
            f"{consumidor}: el driver {d.clave} "
            + ("cambia el cálculo pero el registro no lo declara" if cambia else "está declarado pero no cambia el cálculo")
        )


def test_la_colocacion_de_la_plantilla_lee_la_altura_y_la_separacion() -> None:
    registrado = next(c for c in CONSUMIDORES if c.id == "plantilla_colocar")
    elementos = [{"uid": "K-1", "ref": "K-1", "clase": "castillo", "modo": "ubicado", "sep_m": None, "z_m": "0"}]

    def correr(vigentes: dict[str, str]) -> Any:
        d = {x.clave: Decimal(vigentes.get(x.clave, x.inicial)) for x in CATALOGO_DE_DRIVERS}
        c = colocar_plantilla(
            elementos, largo_m=Decimal("10"), altura_m=d["altura_estandar"], anchos_m={"K-1": Decimal("0.15")},
            separacion_m=d["separacion_castillos"],
        )
        return [(i.piezas, i.alto_m, i.metros) for i in c.instancias]

    base = correr({})
    for d in CATALOGO_DE_DRIVERS:
        if d.modo_inicial == "fijo":
            continue
        assert (correr({d.clave: _PERTURBADOS[d.clave]}) != base) == (d.clave in registrado.claves), d.clave


def test_el_muro_del_plano_lee_la_altura_estandar() -> None:
    registrado = next(c for c in CONSUMIDORES if c.id == "muro_del_plano")
    assert registrado.claves == ("altura_estandar",)
    assert conversion_por_defecto("muro", "m2", 3.5)["alt"] == 3.5 != conversion_por_defecto("muro", "m2", None)["alt"]


def test_todo_driver_tiene_consumidor_o_su_motivo_y_el_registro_no_nombra_drivers_que_no_existen() -> None:
    claves = {d.clave for d in CATALOGO_DE_DRIVERS}
    for c in CONSUMIDORES:
        assert set(c.claves) <= claves and set(c.constantes) <= claves, c.id
        assert not set(c.claves) & set(c.constantes), c.id
        for k in c.constantes:
            assert definicion_de(k).modo_inicial == "fijo", f"{c.id}: «{k}» se lee como constante, así que debe ser fijo"
        for k in c.claves:
            assert definicion_de(k).modo_inicial == "ajustable", f"{c.id}: «{k}» es fijo; se lee como constante, no por obra"
    for k in claves:
        con = consumidores_de(k)
        if k in SIN_CONSUMIDOR_POR_AHORA:
            assert not con, f"«{k}» ya tiene consumidor ({[c.id for c in con]}): quítalo de SIN_CONSUMIDOR_POR_AHORA"
        else:
            assert con, f"«{k}» no lo usa ningún elemento ni artefacto: regístralo o declara por qué no (SIN_CONSUMIDOR_POR_AHORA)"
    assert set(SIN_CONSUMIDOR_POR_AHORA) <= claves


def test_los_consumidores_de_vista_previa_y_colocar_leen_los_mismos_drivers() -> None:
    por_id = {c.id: c for c in CONSUMIDORES}
    assert por_id["plantilla_vista_previa"].claves == por_id["plantilla_colocar"].claves == ("altura_estandar", "separacion_castillos")
    assert por_id["plantilla_vista_previa"].verificado_en == "frontend"
    assert {c.id for c in CONSUMIDORES if c.verificado_en == "backend" and c.claves} <= (
        set(_BASES_DE_PRUEBA) | {"plantilla_colocar", "muro_del_plano"}
    )
