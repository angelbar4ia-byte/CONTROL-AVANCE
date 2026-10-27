"""Las matrices internas: lo medido ajusta el importe y manda sobre lo de adentro (D-583)."""

from decimal import Decimal

from obractrl.domain.cuantificacion.matriz import NodoDeMatriz, ajuste_por_medicion

D = Decimal
BASE = D("10")  # la actividad: 10 m² de losa


def nodo(concepto: str, ruta: tuple[str, ...], acum: str, pu: str, medida: str | None = None) -> NodoDeMatriz:
    return NodoDeMatriz(concepto, ruta, D(acum), D(pu), D(medida) if medida is not None else None)


def test_sin_nada_medido_el_importe_no_cambia() -> None:
    a = ajuste_por_medicion([nodo("nerv", ("losa", "nerv"), "0.5", "200")], cant_base=BASE)
    assert (a.importe_ajuste, a.medidas) == (0, 0)


def test_una_matriz_medida_ajusta_por_lo_que_se_alejo_del_catalogo() -> None:
    # El catálogo implicaba 0.5 × 10 = 5 ml de nervaduras; se midieron 8 a $200: +$600.
    a = ajuste_por_medicion([nodo("nerv", ("losa", "nerv"), "0.5", "200", "8")], cant_base=BASE)
    assert (a.importe_ajuste, a.medidas) == (D("600.0"), 1)
    # Y si se midió de menos, resta.
    a = ajuste_por_medicion([nodo("nerv", ("losa", "nerv"), "0.5", "200", "3")], cant_base=BASE)
    assert a.importe_ajuste == D("-400.0")


def test_una_matriz_medida_manda_sobre_las_de_adentro() -> None:
    nodos = [
        nodo("nerv", ("losa", "nerv"), "0.5", "200", "8"),
        nodo("estribo", ("losa", "nerv", "estribo"), "1.5", "10", "99"),  # ya está dentro de nerv
    ]
    a = ajuste_por_medicion(nodos, cant_base=BASE)
    assert (a.importe_ajuste, a.medidas) == (D("600.0"), 1)


def test_si_solo_se_midio_la_de_adentro_ajusta_ella() -> None:
    nodos = [
        nodo("nerv", ("losa", "nerv"), "0.5", "200"),
        nodo("estribo", ("losa", "nerv", "estribo"), "1.5", "10", "20"),
    ]
    a = ajuste_por_medicion(nodos, cant_base=BASE)
    # Implicaba 1.5 × 10 = 15; se midieron 20 a $10: +$50.
    assert (a.importe_ajuste, a.medidas) == (D("50.0"), 1)


def test_la_misma_matriz_por_dos_caminos_suma_lo_que_el_catalogo_implicaba() -> None:
    nodos = [
        nodo("estribo", ("losa", "nerv", "estribo"), "1.5", "10", "30"),
        nodo("estribo", ("losa", "trabe", "estribo"), "0.5", "10", "30"),
    ]
    a = ajuste_por_medicion(nodos, cant_base=BASE)
    # Implicaba 15 + 5 = 20; se midieron 30: +$100.
    assert a.importe_ajuste == D("100.0")
