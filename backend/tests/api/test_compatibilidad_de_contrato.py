"""El contrato no rompe a los clientes publicados (§12.12).

`test_contrato.py` —vía `scripts/verificar_contrato.py`— comprueba que el
contrato del repo coincida con el código. Esto comprueba la otra mitad, que
ninguna prueba hacía: que el cambio sea **aditivo**. Se puede regenerar el
contrato correctamente y, con eso, romper a todos los clientes viejos a la vez.

Importa desde la Fase 15: la app de Play no se actualiza a voluntad, y entre
publicar una versión e instalarla el último residente pasan semanas (§12.13).

Se prueba el comparador con documentos mínimos escritos a mano —no con el
contrato real— porque lo que hay que verificar es **qué considera romper**, y
eso se ve mejor en cinco líneas que en un OpenAPI de ochenta rutas. La última
prueba sí usa el contrato real: la línea base tiene que estar al día.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

RAIZ = Path(__file__).resolve().parents[3]
"""La raíz del repo: `openapi/` es de todos, no del backend."""


def _cargar_script() -> Any:
    """Importa `scripts/verificar_compatibilidad.py`.

    El script vive fuera del paquete a propósito —se corre igual en local que
    en CI, como `verificar_contrato.py`—, así que se carga por ruta en vez de
    volverlo un módulo importable solo para probarlo.
    """
    ruta = RAIZ / "backend" / "scripts" / "verificar_compatibilidad.py"
    spec = importlib.util.spec_from_file_location("verificar_compatibilidad", ruta)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


vc = _cargar_script()


def _doc(
    *,
    operaciones: dict[str, dict[str, Any]] | None = None,
    esquemas: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {"paths": operaciones or {}, "components": {"schemas": esquemas or {}}}


UNA_RUTA = {"/api/v1/obras": {"get": {"responses": {}}}}


class TestLoQueRompe:
    def test_quitar_una_operación_sin_deprecar(self) -> None:
        fallos = vc.comparar(_doc(operaciones=UNA_RUTA), _doc())

        assert len(fallos) == 1
        assert "se quitó sin deprecar" in fallos[0]

    def test_volver_obligatorio_un_parámetro(self) -> None:
        antes = _doc(
            operaciones={
                "/x": {"get": {"parameters": [{"in": "query", "name": "page"}]}}
            }
        )
        despues = _doc(
            operaciones={
                "/x": {
                    "get": {
                        "parameters": [
                            {"in": "query", "name": "page", "required": True}
                        ]
                    }
                }
            }
        )

        fallos = vc.comparar(antes, despues)
        assert any("query:page" in f and "obligatorio" in f for f in fallos)

    def test_agregar_un_campo_obligatorio_al_cuerpo(self) -> None:
        def documento(requeridos: list[str]) -> dict[str, Any]:
            return _doc(
                operaciones={
                    "/x": {
                        "post": {
                            "requestBody": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Alta"}
                                    }
                                }
                            }
                        }
                    }
                },
                esquemas={"Alta": {"required": requeridos, "properties": {}}},
            )

        fallos = vc.comparar(documento(["nombre"]), documento(["nombre", "clave"]))
        assert any("'clave' del cuerpo pasó a obligatorio" in f for f in fallos)

    def test_quitar_un_campo_de_una_respuesta(self) -> None:
        antes = _doc(esquemas={"Obra": {"properties": {"clave": {}, "avance": {}}}})
        despues = _doc(esquemas={"Obra": {"properties": {"clave": {}}}})

        fallos = vc.comparar(antes, despues)
        assert fallos == [
            "Obra.avance: se quitó del esquema; un cliente viejo puede estar leyéndolo."
        ]

    def test_cambiar_el_tipo_de_un_campo(self) -> None:
        antes = _doc(esquemas={"Obra": {"properties": {"avance": {"type": "string"}}}})
        despues = _doc(esquemas={"Obra": {"properties": {"avance": {"type": "number"}}}})

        assert vc.comparar(antes, despues) == ["Obra.avance: cambió de string a number."]

    def test_quitar_un_valor_de_un_enum(self) -> None:
        # Un cliente viejo puede tener un `switch` con ese valor, pero lo que
        # de verdad rompe es al revés: el servidor deja de aceptarlo y el
        # cliente lo sigue mandando.
        antes = _doc(esquemas={"Rol": {"enum": ["residente", "supervisor"]}})
        despues = _doc(esquemas={"Rol": {"enum": ["residente"]}})

        assert vc.comparar(antes, despues) == [
            "Rol: se quitó el valor 'supervisor' del enum."
        ]


class TestLoQueNoRompe:
    def test_agregar_una_operación(self) -> None:
        despues = _doc(operaciones={**UNA_RUTA, "/api/v1/procesos": {"get": {}}})
        assert vc.comparar(_doc(operaciones=UNA_RUTA), despues) == []

    def test_agregar_un_campo_opcional_a_una_respuesta(self) -> None:
        antes = _doc(esquemas={"Obra": {"properties": {"clave": {}}}})
        despues = _doc(esquemas={"Obra": {"properties": {"clave": {}, "nuevo": {}}}})

        assert vc.comparar(antes, despues) == []

    def test_agregar_un_valor_a_un_enum(self) -> None:
        antes = _doc(esquemas={"Estatus": {"enum": ["propuesto"]}})
        despues = _doc(esquemas={"Estatus": {"enum": ["propuesto", "adoptado"]}})

        assert vc.comparar(antes, despues) == []

    def test_quitar_un_parámetro_opcional(self) -> None:
        # El cliente que lo mandaba sigue funcionando: el servidor lo ignora.
        antes = _doc(
            operaciones={"/x": {"get": {"parameters": [{"in": "query", "name": "q"}]}}}
        )
        assert vc.comparar(antes, _doc(operaciones={"/x": {"get": {}}})) == []


class TestVentanaDeDeprecacion:
    def _deprecada(self, sunset: date | None) -> dict[str, Any]:
        operacion: dict[str, Any] = {"deprecated": True}
        if sunset is not None:
            operacion["x-sunset"] = sunset.isoformat()
        return _doc(operaciones={"/viejo": {"get": operacion}})

    def test_quitar_algo_deprecado_cuya_ventana_venció(self) -> None:
        ayer = date.today() - timedelta(days=1)
        assert vc.comparar(self._deprecada(ayer), _doc()) == []

    def test_no_se_puede_quitar_antes_de_que_venza(self) -> None:
        # La ventana existe para cumplirse: si se pudiera acortar, no sería
        # una ventana sino un comentario.
        manana = date.today() + timedelta(days=1)
        fallos = vc.comparar(self._deprecada(manana), _doc())

        assert len(fallos) == 1
        assert "Todavía no se puede quitar" in fallos[0]

    def test_una_deprecación_sin_fecha_es_un_error(self) -> None:
        # Sin fecha, la ventana nunca empieza a correr y la ruta se queda
        # deprecada para siempre.
        fallos = vc.comparar(_doc(), self._deprecada(None))

        assert len(fallos) == 1
        assert "sin `x-sunset`" in fallos[0]

    def test_quitar_algo_deprecado_sin_fecha_tampoco_pasa(self) -> None:
        fallos = vc.comparar(self._deprecada(None), _doc())
        assert any("nunca empezó a correr" in f for f in fallos)


class TestElContratoReal:
    def test_la_línea_base_existe_y_el_contrato_de_hoy_es_compatible(self) -> None:
        """La prueba que se pone roja el día que alguien rompe la API.

        Duplica lo que hace el paso de CI a propósito: quien corre `pytest` en
        local se entera antes de abrir el PR, que es cuando el cambio todavía
        es barato.
        """
        publicado = json.loads((RAIZ / "openapi" / "publicado.json").read_text("utf-8"))
        actual = json.loads((RAIZ / "openapi" / "openapi.json").read_text("utf-8"))

        assert vc.comparar(publicado, actual) == []

    def test_ninguna_ruta_está_deprecada_sin_fecha(self) -> None:
        actual = json.loads((RAIZ / "openapi" / "openapi.json").read_text("utf-8"))

        sin_fecha = [
            clave
            for clave, operacion in vc._operaciones(actual).items()
            if operacion.get("deprecated") and not operacion.get("x-sunset")
        ]
        assert sin_fecha == []


class TestElAyudanteDeDeprecacion:
    """`adapters/api/deprecacion.py`. Hoy no hay rutas deprecadas —la Fase 16
    agrega, no quita— así que se prueba el mecanismo, que es lo que tiene que
    estar listo antes de que haga falta."""

    def test_arma_la_ventana_y_la_extensión_del_contrato(self) -> None:
        from obractrl.adapters.api.deprecacion import deprecar

        kwargs = deprecar(desde="2026-01-01", meses=6, en_favor_de="GET /nuevo")

        assert kwargs["deprecated"] is True
        # La misma fecha que `verificar_compatibilidad.py` va a leer.
        assert kwargs["openapi_extra"]["x-sunset"] == "2026-06-30"
        assert "GET /nuevo" in kwargs["description"]

    def test_la_fecha_http_no_depende_del_locale(self) -> None:
        # `strftime('%a')` en un servidor con locale español escribiría "mié"
        # donde el RFC 9110 exige "Wed" — y el cliente descartaría la cabecera.
        from obractrl.adapters.api.deprecacion import _http_date

        assert _http_date(date(2026, 6, 30)) == "Tue, 30 Jun 2026 00:00:00 GMT"

    @pytest.mark.asyncio
    async def test_pone_las_cabeceras_del_rfc_8594(self) -> None:
        from fastapi import Response

        from obractrl.adapters.api.deprecacion import deprecar

        kwargs = deprecar(desde="2026-01-01", meses=6, en_favor_de="GET /nuevo")
        dependencia = kwargs["dependencies"][0].dependency

        respuesta = Response()
        await dependencia(respuesta)

        assert respuesta.headers["Deprecation"] == "Thu, 01 Jan 2026 00:00:00 GMT"
        assert respuesta.headers["Sunset"] == "Tue, 30 Jun 2026 00:00:00 GMT"
        assert 'rel="successor-version"' in respuesta.headers["Link"]
