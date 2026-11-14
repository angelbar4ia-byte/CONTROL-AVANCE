"""La clasificación de los elementos en la biblioteca: categoría, subcategoría, firma anti-duplicados y posiciones (M-29, M-32)."""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.clasificacion_de_elementos import (
    CATEGORIAS,
    categoria_por_defecto,
    firma_de_elemento,
    posiciones_permitidas,
    validar_clasificacion,
    validar_posicion,
)
from obractrl.domain.cuantificacion.elementos_parametricos import (
    PARAMETROS_POR_TIPO,
    TIPOS_DE_ELEMENTO,
    ErrorDeElementoParametrico,
    normalizar_parametros,
)


def _firma(categoria: str, subcategoria: str, tipo: str, **parametros: float) -> str:
    return firma_de_elemento(categoria, subcategoria, tipo, normalizar_parametros(tipo, parametros))


def test_cada_tipo_tiene_su_clasificacion_por_defecto_y_es_valida() -> None:
    assert {t: categoria_por_defecto(t) for t in TIPOS_DE_ELEMENTO} == {
        "castillo": ("castillos", "muro"),
        "lineal": ("cadenas", "cerramiento"),
        "zapata": ("zapatas", "aislada"),
        "losa": ("losas", "maciza"),
    }
    for tipo in TIPOS_DE_ELEMENTO:
        cat, sub = categoria_por_defecto(tipo)
        assert validar_clasificacion(tipo, None, None) == (cat, sub)
        assert validar_clasificacion(tipo, cat, sub) == (cat, sub)


def test_la_categoria_sola_toma_su_primera_subcategoria_y_lo_que_no_existe_se_rechaza() -> None:
    assert validar_clasificacion("lineal", "dalas", None) == ("dalas", "cerramiento")
    assert validar_clasificacion("lineal", None, "desplante") == ("cadenas", "desplante")
    assert validar_clasificacion("castillo", " Castillos ", " PRETIL ") == ("castillos", "pretil")
    with pytest.raises(ErrorDeElementoParametrico, match="no existe en la biblioteca"):
        validar_clasificacion("lineal", "puentes", None)
    with pytest.raises(ErrorDeElementoParametrico, match="no existe en Cadenas"):
        validar_clasificacion("lineal", "cadenas", "azotea")
    with pytest.raises(ErrorDeElementoParametrico, match="se calcula como"):
        validar_clasificacion("castillo", "cadenas", "desplante")  # un castillo no va en Cadenas
    with pytest.raises(ErrorDeElementoParametrico, match="Tipo de elemento desconocido"):
        validar_clasificacion("muro", None, None)


def test_la_biblioteca_no_repite_claves_y_cada_categoria_usa_un_tipo_que_se_calcula() -> None:
    assert len({c["clave"] for c in CATEGORIAS}) == len(CATEGORIAS)
    for c in CATEGORIAS:
        assert c["tipo"] in PARAMETROS_POR_TIPO
        assert len({s["clave"] for s in c["subcategorias"]}) == len(c["subcategorias"])


def test_cerramiento_y_desplante_con_la_misma_geometria_no_son_duplicados() -> None:
    assert _firma("cadenas", "cerramiento", "lineal") != _firma("cadenas", "desplante", "lineal")
    assert _firma("cadenas", "cerramiento", "lineal") != _firma("dalas", "cerramiento", "lineal")


def test_dos_elementos_con_lo_mismo_son_duplicados_aunque_cambien_clave_o_nombre() -> None:
    a = _firma("cadenas", "cerramiento", "lineal", ancho=0.15, alto=0.2)
    # Lo que no se dijo toma el valor por defecto, igual que al guardar.
    assert a == _firma("cadenas", "cerramiento", "lineal", alto=0.2, ancho=0.15, n_sup=3)
    assert a == _firma("cadenas", "cerramiento", "lineal", ancho=0.150000001, alto=0.2)  # el ruido de coma flotante no cuenta


@pytest.mark.parametrize(
    "cambio",
    [{"ancho": 0.25}, {"alto": 0.25}, {"n_sup": 2}, {"no_inf": 5}, {"sep": 0.15}, {"no_est": 3}, {"lados": 2}, {"rec": 0.03}],
)
def test_cambiar_medidas_armado_o_cimbra_cambia_la_firma(cambio: dict[str, float]) -> None:
    base = {"ancho": 0.15, "alto": 0.2}
    assert _firma("cadenas", "cerramiento", "lineal", **base) != _firma("cadenas", "cerramiento", "lineal", **{**base, **cambio})


def test_la_firma_es_estable_y_en_hexadecimal() -> None:
    f = _firma("castillos", "muro", "castillo")
    assert f == _firma("castillos", "muro", "castillo")
    assert len(f) == 64 and int(f, 16) >= 0


def test_la_cadena_de_desplante_solo_va_al_pie_y_la_de_cerramiento_en_cerramiento_o_remate() -> None:
    assert posiciones_permitidas("cadenas", "desplante") == ("desplante",)
    assert posiciones_permitidas("cadenas", "desplante_aparente") == ("desplante",)
    assert posiciones_permitidas("cadenas", "cerramiento") == ("cerramiento", "remate")
    assert posiciones_permitidas("cadenas", "cerramiento_aparente") == ("cerramiento", "remate")
    assert posiciones_permitidas("dalas", "repison") == ("cerramiento",)
    assert posiciones_permitidas("castillos", "muro") is None

    validar_posicion("cadenas", "desplante", "desplante")
    validar_posicion("cadenas", "cerramiento", "cerramiento")
    validar_posicion("cadenas", "cerramiento", "remate")
    with pytest.raises(ErrorDeElementoParametrico, match="solo se coloca en desplante, no en cerramiento"):
        validar_posicion("cadenas", "desplante", "cerramiento")
    with pytest.raises(ErrorDeElementoParametrico, match="solo se coloca en cerramiento o remate, no en desplante"):
        validar_posicion("cadenas", "cerramiento", "desplante")
    with pytest.raises(ErrorDeElementoParametrico, match="no se coloca por posición"):
        validar_posicion("castillos", "muro", "desplante")
    with pytest.raises(ErrorDeElementoParametrico, match="no existe"):
        validar_posicion("cadenas", "cerramiento", "azotea")
