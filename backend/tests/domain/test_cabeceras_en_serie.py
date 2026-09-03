"""Columnas repetidas y numeradas en los archivos reales (§10.6, §3.3).

Los catálogos de la constructora no escriben una lista separada por comas: los
reparten en columnas. `ESPECIALIDAD 1 … ESPECIALIDAD 5` para los oficios de un
contratista, `TIPO 1` y `TIPO 2` para sus frentes. Y el catálogo de etapas trae
**dos columnas llamadas igual**, `TIPO`, donde solo la última es el frente.

Antes de las series, `resolver_encabezados` rechazaba los tres archivos: su
regla es que dos columnas hacia el mismo campo es ambigüedad, y adivinar cuál
vale es justo lo que el §3.3 prohíbe. Esa regla sigue siendo correcta para una
columna que **compite**; lo que faltaba era distinguirla de cinco huecos del
mismo dato, que no compiten entre sí.

Lo que estas pruebas fijan:

 1. **Una serie colecciona, no compite.** Cinco columnas de especialidad dan
    cinco valores, no un `ErrorDeCabecera`.
 2. **El corte por sufijo es exacto.** Un prefijo `tipo` no se puede tragar
    `TIPO DE CAMBIO`: cargaría un dato en la columna equivocada sin que nadie
    lo note.
 3. **Los huecos y las repeticiones se descartan al leer la fila**, porque son
    la forma normal del archivo: quien tiene dos oficios deja tres columnas en
    blanco.
 4. **El tipo de renglón del exportador no es un frente.** `Nivel 2` se
    descarta por vocabulario nombrado, no por posición: así una etapa con el
    frente mal escrito sale como error en vez de perderse en silencio.

Módulo puro (§12.11).
"""

from __future__ import annotations

import pytest

from obractrl.domain.cargadores.cabeceras import (
    CONTRATISTAS,
    ETAPAS_CONSTRUCTIVAS,
    ErrorDeCabecera,
    EspecificacionArchivo,
    resolver_encabezados,
)
from obractrl.domain.cargadores.contratistas import validar_contratista
from obractrl.domain.cargadores.etapas_constructivas import (
    es_tipo_de_renglon,
    validar_etapa_constructiva,
)
from obractrl.domain.cargadores.reporte import ErrorEnFila

# Los encabezados literales de los dos archivos reales.
CAB_CONTRATISTAS = [
    "CLAVE",
    "CONTRATISTA",
    "TIPO 1",
    "TIPO 2",
    "ESPECIALIDAD 1",
    "ESPECIALIDAD 2",
    "ESPECIALIDAD 3",
    "ESPECIALIDAD 4",
    "ESPECIALIDAD 5",
]
CAB_ETAPAS = ["TIPO", "CLAVE", "DESCRIPCIÓN", "DESCRIPCIÓN CORTA", "TIPO "]


class TestSerieDeColumnas:
    def test_cinco_columnas_del_mismo_dato_no_son_ambiguedad(self) -> None:
        # Sin esto el archivo entero se rechazaba: la regla de ambigüedad veía
        # cinco candidatas a una casilla donde hay cinco huecos.
        mapa = resolver_encabezados(CAB_CONTRATISTAS, CONTRATISTAS)
        assert mapa.series["especialidades"] == (4, 5, 6, 7, 8)
        assert mapa.series["frentes"] == (2, 3)

    def test_la_serie_conserva_el_orden_del_archivo(self) -> None:
        # `ESPECIALIDAD 1` es la principal; invertirlas cambiaría cuál se lee
        # primero cuando alguien las presente en ese orden.
        mapa = resolver_encabezados(CAB_CONTRATISTAS, CONTRATISTAS)
        assert list(mapa.series["especialidades"]) == sorted(
            mapa.series["especialidades"]
        )

    def test_una_cabecera_que_solo_empieza_igual_no_entra(self) -> None:
        # `TIPO DE CAMBIO` no es un `TIPO n`. Sin el corte por sufijo, su valor
        # se cargaría como frente y nadie lo notaría.
        espec = EspecificacionArchivo(
            tipo="prueba",
            archivo="X.xlsx",
            obligatorias=("clave",),
            hoja=None,
            series={"tipo": "frentes"},
        )
        mapa = resolver_encabezados(["CLAVE", "TIPO 1", "TIPO DE CAMBIO"], espec)
        assert mapa.series["frentes"] == (1,)
        assert "TIPO DE CAMBIO" in mapa.ignoradas

    def test_una_serie_puede_cubrir_una_obligatoria(self) -> None:
        espec = EspecificacionArchivo(
            tipo="prueba",
            archivo="X.xlsx",
            obligatorias=("frentes",),
            hoja=None,
            series={"tipo": "frentes"},
        )
        assert resolver_encabezados(["TIPO 1"], espec).series["frentes"] == (0,)

    def test_sigue_habiendo_ambiguedad_fuera_de_las_series(self) -> None:
        # La regla del §3.3 no se relajó: dos columnas que compiten por el mismo
        # campo siguen tumbando el archivo.
        espec = EspecificacionArchivo(
            tipo="prueba",
            archivo="X.xlsx",
            obligatorias=("clave",),
            hoja=None,
            alias={"codigo": "clave", "clave": "clave"},
        )
        with pytest.raises(ErrorDeCabecera):
            resolver_encabezados(["CLAVE", "CODIGO"], espec)


class TestLeerLosValoresDeUnaSerie:
    def _fila(self, *valores: object):
        mapa = resolver_encabezados(CAB_CONTRATISTAS, CONTRATISTAS)
        return mapa, ["C-1", "Antonio García", *valores]

    def test_los_huecos_se_descartan(self) -> None:
        # Quien tiene dos oficios deja tres columnas en blanco. Es la forma
        # normal del archivo, no un dato faltante que haya que reportar.
        mapa, fila = self._fila("OBRA", None, "OBRA CIVIL", "ACABADOS", "", None, None)
        contratista = validar_contratista(fila, mapa)
        assert [str(e) for e in contratista.especialidades] == [
            "OBRA CIVIL",
            "ACABADOS",
        ]
        assert [str(f) for f in contratista.frentes] == ["OBRA"]

    def test_una_referencia_repetida_no_se_duplica(self) -> None:
        # Duplicar un puente no dice nada nuevo y la única de la tabla lo
        # rechazaría de todos modos.
        mapa, fila = self._fila("OBRA", "OBRA", "ACABADOS", "acabados", None, None, None)
        contratista = validar_contratista(fila, mapa)
        assert len(contratista.frentes) == 1
        assert len(contratista.especialidades) == 1

    def test_un_valor_con_espacios_se_lee_igual(self) -> None:
        # El archivo real trae `SUBCONTRATO ` y `ELECTRICAS ` con espacio final.
        mapa, fila = self._fila("OBRA", "SUBCONTRATO ", "ELECTRICAS ", None, None, None, None)
        contratista = validar_contratista(fila, mapa)
        assert [str(f) for f in contratista.frentes] == ["OBRA", "SUBCONTRATO"]
        assert [str(e) for e in contratista.especialidades] == ["ELECTRICAS"]

    def test_una_celda_con_lista_separada_por_coma_sigue_funcionando(self) -> None:
        # La plantilla que este repo genera escribe `EST, INS` en una sola
        # celda. Las dos formas conviven: el archivo decide, no el cargador.
        espec = EspecificacionArchivo(
            tipo="prueba",
            archivo="X.xlsx",
            obligatorias=("clave", "razon_social"),
            opcionales=("frentes",),
            hoja=None,
            alias={"frentes": "frentes", "contratista": "razon_social"},
        )
        mapa = resolver_encabezados(["CLAVE", "CONTRATISTA", "FRENTES"], espec)
        contratista = validar_contratista(["C-1", "Antonio García", "EST, INS"], mapa)
        assert [str(f) for f in contratista.frentes] == ["EST", "INS"]


class TestLasDosColumnasTipoDeLasEtapas:
    def test_el_tipo_de_renglon_del_exportador_se_reconoce(self) -> None:
        assert es_tipo_de_renglon("Nivel 2")
        assert es_tipo_de_renglon("SUBCAPÍTULO")
        assert not es_tipo_de_renglon("OBRA")
        # Un frente mal escrito NO cae aquí: sale como dato y se reporta.
        assert not es_tipo_de_renglon("OBRAA")

    def test_de_dos_columnas_tipo_se_queda_con_el_frente(self) -> None:
        # Normalizadas las dos son "tipo": por nombre no se pueden separar y
        # por posición sería frágil. La serie las junta y el vocabulario cerrado
        # descarta la del exportador.
        mapa = resolver_encabezados(CAB_ETAPAS, ETAPAS_CONSTRUCTIVAS)
        etapa = validar_etapa_constructiva(
            ["Nivel 2", "ECO-00001", "ESTRUCTURA CIM", "ESTRUCTURA CIM", "OBRA"], mapa
        )
        assert etapa.frente == "OBRA"
        assert str(etapa.clave) == "ECO-00001"

    def test_sin_frente_la_etapa_sigue_siendo_valida(self) -> None:
        # Una etapa sin frente es el estado normal mientras se captura (0045).
        mapa = resolver_encabezados(CAB_ETAPAS, ETAPAS_CONSTRUCTIVAS)
        etapa = validar_etapa_constructiva(
            ["Nivel 2", "ECO-00029", "ILUMINACIÓN", "ILUMINACIÓN", None], mapa
        )
        assert etapa.frente is None

    def test_dos_frentes_para_la_misma_etapa_son_un_error_de_fila(self) -> None:
        # Una etapa en dos frentes contaría su trabajo dos veces al planear
        # cuántas cuadrillas hacen falta — justo lo que la 0045 evita usando una
        # columna en vez de un puente.
        mapa = resolver_encabezados(CAB_ETAPAS, ETAPAS_CONSTRUCTIVAS)
        with pytest.raises(ErrorEnFila, match="solo puede pertenecer a uno"):
            validar_etapa_constructiva(
                ["OBRA", "ECO-00001", "ESTRUCTURA CIM", "ESTRUCTURA CIM", "PINTURA"],
                mapa,
            )
