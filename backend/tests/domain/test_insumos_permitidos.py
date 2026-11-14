"""Qué insumos admite cada tipo de elemento (fase D; M-25, M-28, M-55, M-134): familias del catálogo real, clases y alta provisional."""

from __future__ import annotations

import pytest

from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
)
from obractrl.domain.cuantificacion.insumos_permitidos import (
    CLASES_DE_INSUMO,
    SUGERENCIAS_DE_HERRAMIENTA,
    Insumo,
    InsumoNoPermitido,
    clase_de_insumo,
    describir_familias,
    es_permitido,
    familias_de_clase,
    normalizar_insumo_nuevo,
    validar_permitido,
)


def _mat(clave: str, familia: str, sub: str | None = None) -> Insumo:
    return Insumo(clave=clave, descripcion=clave, clase="material", familia=familia, subfamilia=sub)


# Insumos reales de CATALOGO_DE_MATERIALES.csv (familia · subfamilia).
ARMEX = _mat("ACE-00011", "Aceros", "Prefabricado")
ALAMBRE = _mat("ACE-00001", "Aceros", "Consumible")
CLAVO = _mat("ACE-00012", "Aceros", "Consumible")
VARILLA = _mat("ACR-00001", "Acero De Refuerzo", "Habilitable")
CONCRETO = _mat("MEZ-01020", "Mezclas", "Concretos")
CONCRETO_PREFAB = _mat("PRE-00001", "Prefabricados", "Concretos")
CIMBRA = _mat("MAD-00001", "Cimbra", "Cimbra")
CIMBRA_RECIEN_CARGADA = _mat("MAD-00002", "Maderas", "Cimbra")
DURMIENTE = _mat("MAD-00007", "Maderas", "Ornamental")
PIEDRA = _mat("PET-00004", "Pétreos", "Piedras")
MORTERO = _mat("MEZ-07010", "Mezclas", "Morteros")
TUBO = _mat("INS-D001", "Tuberías", "PVC")
INODORO = _mat("EQU-00001", "Equipamiento", "Muebles de Baño")


@pytest.mark.parametrize("tipo", ["castillo", "lineal", "zapata"])
@pytest.mark.parametrize("ins", [ARMEX, ALAMBRE, CLAVO, VARILLA, CONCRETO, CONCRETO_PREFAB, CIMBRA, CIMBRA_RECIEN_CARGADA])
def test_castillo_cadena_y_zapata_admiten_acero_concreto_y_cimbra(tipo: str, ins: Insumo) -> None:
    assert es_permitido(tipo, ins)
    validar_permitido(tipo, ins)


@pytest.mark.parametrize("tipo", ["castillo", "lineal", "zapata"])
@pytest.mark.parametrize("ins", [DURMIENTE, PIEDRA, MORTERO, TUBO, INODORO])
def test_un_insumo_de_otra_familia_se_rechaza_con_un_error_que_dice_que_si_admite_el_tipo(tipo: str, ins: Insumo) -> None:
    assert not es_permitido(tipo, ins)
    with pytest.raises(InsumoNoPermitido) as e:
        validar_permitido(tipo, ins)
    m = str(e.value)
    assert ins.clave in m and tipo in m
    assert "Aceros" in m and "Acero De Refuerzo" in m and "Mezclas · Concretos" in m and "Cimbra" in m


def test_el_concreto_es_de_mezclas_o_de_prefabricados_pero_no_todo_lo_de_esas_familias() -> None:
    assert not es_permitido("castillo", _mat("MEZ-07010", "Mezclas", "Morteros"))
    assert not es_permitido("castillo", _mat("PRE-00099", "Prefabricados", "Canteras"))
    assert not es_permitido("castillo", _mat("PRE-00100", "Prefabricados", "Losa Nervada"))


def test_la_losa_aun_no_tiene_lista_y_lo_dice() -> None:
    with pytest.raises(InsumoNoPermitido, match="aún no tiene lista"):
        validar_permitido("losa", VARILLA)
    assert describir_familias("losa", "material") == "ninguna todavía"


def test_los_muros_y_el_volumen_tienen_sus_propias_familias() -> None:
    assert es_permitido("muro", PIEDRA) and es_permitido("muro", MORTERO)
    assert not es_permitido("muro", VARILLA) and not es_permitido("muro", CONCRETO)
    assert es_permitido("volumen", TUBO) and es_permitido("volumen", CONCRETO) and es_permitido("volumen", PIEDRA)
    assert not es_permitido("volumen", ARMEX)


def test_tipo_desconocido() -> None:
    with pytest.raises(ErrorDeElementoParametrico, match="Tipo de elemento desconocido"):
        es_permitido("escalera", ARMEX)


def test_la_mano_de_obra_es_de_albanileria_y_estructura() -> None:
    cuadrilla = Insumo("CUAD-001", "Cuadrilla", "mano_obra", "Cuadrillas", "Albañilería y Estructura")
    peon = Insumo("MOCA-001", "Peón", "mano_obra", "Peones", "Albañilería y Estructura")
    carpintero = Insumo("CUAD-050", "Cuadrilla", "mano_obra", "Cuadrillas", "Carpintería")
    operador = Insumo("OPE-001", "Operador", "mano_obra", "Operadores", "Equipo y Maquinaria")
    assert es_permitido("castillo", cuadrilla) and es_permitido("lineal", peon)
    assert not es_permitido("castillo", carpintero) and not es_permitido("zapata", operador)
    with pytest.raises(InsumoNoPermitido, match="Mano de obra admitidos: Mano de obra · Albañilería y Estructura"):
        validar_permitido("castillo", carpintero)


def test_el_destajo_es_de_la_subfamilia_de_su_tipo() -> None:
    def destajo(clave: str, fam: str, sub: str | None) -> Insumo:
        return Insumo(clave, clave, "trabajo", fam, sub)

    k1, cadena, zapata = destajo("MOE-02020", "Obra Civil", "Castillo"), destajo("MOE-02050", "Obra Civil", "Cadena"), destajo("MOE-05010", "Obra Civil", "Zapata")
    assert es_permitido("castillo", k1) and not es_permitido("lineal", k1) and not es_permitido("zapata", k1)
    assert es_permitido("lineal", cadena) and es_permitido("zapata", zapata)
    assert es_permitido("muro", destajo("MOE-02010", "Obra Civil", "Muro")) and es_permitido("volumen", destajo("MOP-00303", "Obra Exterior", "Muro"))
    # Un destajo de Albañilería (repellado) o de Pinturas no es de la estructura.
    assert not es_permitido("muro", destajo("MOA-00001", "Albañilería", "Muro"))
    assert not es_permitido("muro", destajo("MOA-00010", "Pinturas", "Muro"))
    # Si la base no trae la subfamilia del destajo, decide la familia (los trabajos se cargan hoy sin subfamilia).
    assert es_permitido("castillo", destajo("MOE-02020", "Obra Civil", None))
    # La losa no tiene lista.
    assert not es_permitido("losa", k1)


def test_herramienta_y_equipo_es_opcional_y_libre() -> None:
    andamio = Insumo("INS-A001", "Andamio", "herramienta", "Herramienta y equipo", "Andamios", provisional=True)
    for tipo in ("castillo", "lineal", "zapata", "muro", "volumen", "losa"):
        assert es_permitido(tipo, andamio), tipo
    assert describir_familias("castillo", "herramienta").startswith("cualquiera")
    assert [f.familia for f in familias_de_clase("castillo", "herramienta")] == ["Herramienta y equipo"]


def test_la_clase_de_un_insumo_sale_de_su_tipo_y_su_familia() -> None:
    assert clase_de_insumo("material", "Aceros") == "material"
    assert clase_de_insumo("herramienta", None) == "herramienta" and clase_de_insumo("equipo", None) == "herramienta"
    assert clase_de_insumo("mano_obra", "Cuadrillas") == "mano_obra"
    assert clase_de_insumo("mano_obra", "Obra Civil") == "trabajo"  # un destajo se guarda como mano de obra
    assert clase_de_insumo("subcontrato", "Obra Civil") is None and clase_de_insumo("acarreo", None) is None
    assert list(CLASES_DE_INSUMO) == ["material", "trabajo", "mano_obra", "herramienta"]


def test_un_insumo_de_una_clase_que_no_se_agrega_no_se_acepta() -> None:
    flete = Insumo("FLE-001", "Flete", None, "Fletes", None)
    with pytest.raises(InsumoNoPermitido, match="no se agrega a un elemento"):
        validar_permitido("castillo", flete)


def test_un_insumo_nuevo_nace_en_una_familia_del_tipo_y_sin_precio() -> None:
    n = normalizar_insumo_nuevo("castillo", clase="material", clave=" ins-9001 ", descripcion="  ARMEX   15X30  ", unidad="pza", familia="Aceros", subfamilia="Prefabricado")
    assert (n.clave, n.descripcion, n.familia, n.subfamilia, n.clase) == ("INS-9001", "ARMEX 15X30", "Aceros", "Prefabricado", "material")
    with pytest.raises(InsumoNoPermitido, match="no es de las familias"):
        normalizar_insumo_nuevo("castillo", clase="material", clave="INS-9002", descripcion="Piedra", unidad="m3", familia="Pétreos")
    with pytest.raises(ErrorDeElementoParametrico, match="Elige la familia"):
        normalizar_insumo_nuevo("castillo", clase="material", clave="INS-9003", descripcion="x", unidad="kg", familia=None)


def test_la_herramienta_nueva_va_en_su_familia_y_el_andamio_es_la_sugerencia() -> None:
    n = normalizar_insumo_nuevo("lineal", clase="herramienta", clave="INS-A001", descripcion="ANDAMIO (renta por jornada)", unidad="jornal", familia=None, subfamilia="Andamios")
    assert n.familia == "Herramienta y equipo" and n.subfamilia == "Andamios"
    (s,) = SUGERENCIAS_DE_HERRAMIENTA
    assert s["clave"] == "INS-A001" and "ANDAMIO" in s["descripcion"]


def test_el_destajo_y_la_mano_de_obra_nuevos_toman_su_subfamilia() -> None:
    d = normalizar_insumo_nuevo("zapata", clase="trabajo", clave="MOE-9001", descripcion="MO ZAPATA CORRIDA", unidad="ml", familia="Obra Civil")
    assert d.subfamilia == "Zapata"
    mo = normalizar_insumo_nuevo("castillo", clase="mano_obra", clave="MOCA-9001", descripcion="Ayudante", unidad="jornal", familia="Ayudantes")
    assert mo.subfamilia == "Albañilería y Estructura"
    with pytest.raises(InsumoNoPermitido, match="La mano de obra se crea en una de estas familias"):
        normalizar_insumo_nuevo("castillo", clase="mano_obra", clave="MOCA-9002", descripcion="x", unidad="jornal", familia="Pétreos")
    with pytest.raises(InsumoNoPermitido):
        normalizar_insumo_nuevo("castillo", clase="trabajo", clave="MOA-9001", descripcion="x", unidad="m2", familia="Pinturas")


@pytest.mark.parametrize(
    ("campo", "valor"), [("clave", "a"), ("clave", "con espacio raro!"), ("descripcion", "  "), ("unidad", "")]
)
def test_un_alta_con_datos_que_no_valen_se_rechaza(campo: str, valor: str) -> None:
    datos = {"clase": "material", "clave": "INS-9100", "descripcion": "algo", "unidad": "kg", "familia": "Aceros"}
    datos[campo] = valor
    with pytest.raises(ErrorDeElementoParametrico):
        normalizar_insumo_nuevo("castillo", **datos)  # type: ignore[arg-type]
