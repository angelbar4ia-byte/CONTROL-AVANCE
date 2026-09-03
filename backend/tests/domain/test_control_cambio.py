"""Control de cambio: lo que mueve el costo final de una obra (§11.3, §6, §4).

El jefe de obra lo unificó: *"pueden pedir más cantidad, dar de alta trabajo
fuera de catálogo, cambiar una actividad por otra, o pedir una que existe en el
catálogo y no estaba; todo esto al final se clasifica como control de cambio
que recae al costo de la obra final"*.

Lo que estas pruebas fijan:

 1. **Quien pide no autoriza.** El residente afirma que hace falta —está parado
    ahí— y Control decide. Autorizar lo propio convierte el control en trámite.
 2. **Pasar el umbral no es un error de captura**, es la señal de que hace falta
    un control de cambio. La diferencia importa: un error lo corrige el
    residente solo; esto necesita a Control.
 3. **Una cantidad ya autorizada manda sobre el margen.** Una vez que Control
    firmó "súbele a 45", el porcentaje deja de decidir.
 4. **Cada tipo pide lo suyo.** Una sustitución sin decir a qué reemplaza es un
    alta disfrazada, y el costo se contaría dos veces.

Módulo puro: sin BD, sin reloj (§12.11).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.obras.control_cambio import (
    ErrorDeControlDeCambio,
    LineaDeCambio,
    SolicitudDeCambio,
    TipoControlCambio,
    excede_el_umbral,
    puede_autorizar,
    puede_solicitar,
    techo_de,
)
from obractrl.domain.shared.diccionario import Rol

OBRA = "11111111-1111-1111-1111-111111111111"
ACT = "22222222-2222-2222-2222-222222222222"


class TestQuienPideYQuienAutoriza:
    def test_pide_el_residente(self) -> None:
        assert puede_solicitar(Rol.RESIDENTE)

    def test_no_pide_control_ni_el_supervisor(self) -> None:
        # Pedir es afirmar que en la obra hace falta algo que el proyecto no
        # traía, y el único que puede afirmarlo es quien está ahí.
        assert not puede_solicitar(Rol.CONTROL_OBRA)
        assert not puede_solicitar(Rol.SUPERVISOR)

    def test_autoriza_control_y_el_super_intendente(self) -> None:
        assert puede_autorizar(Rol.CONTROL_OBRA)
        assert puede_autorizar(Rol.SUPER_INTENDENTE)

    def test_el_residente_no_autoriza_ni_lo_suyo(self) -> None:
        # Autorizar lo que uno mismo pidió convierte el control en un trámite.
        # Misma separación que el cierre de actividad.
        assert not puede_autorizar(Rol.RESIDENTE)


class TestElUmbral:
    def test_el_techo_es_la_base_mas_la_tolerancia(self) -> None:
        assert techo_de(
            cant_base=Decimal(100), tolerancia_pct=Decimal(20)
        ) == Decimal(120)

    def test_una_tolerancia_por_obra_distinta_cambia_el_techo(self) -> None:
        # Una manzana de remodelación no tolera lo mismo que una casa nueva.
        assert techo_de(
            cant_base=Decimal(100), tolerancia_pct=Decimal(5)
        ) == Decimal(105)

    def test_una_cantidad_autorizada_manda_sobre_el_margen(self) -> None:
        # Control firmó "súbele a 200": el 20% ya no decide, ni para arriba ni
        # para abajo.
        assert techo_de(
            cant_base=Decimal(100),
            tolerancia_pct=Decimal(20),
            cant_autorizada=Decimal(200),
        ) == Decimal(200)

    def test_dentro_del_umbral_no_hace_falta_autorizacion(self) -> None:
        assert not excede_el_umbral(
            cant_programada=Decimal(115),
            cant_base=Decimal(100),
            tolerancia_pct=Decimal(20),
        )

    def test_pasarlo_es_la_señal_de_que_hace_falta_control_de_cambio(self) -> None:
        assert excede_el_umbral(
            cant_programada=Decimal(130),
            cant_base=Decimal(100),
            tolerancia_pct=Decimal(20),
        )

    def test_justo_en_el_techo_todavia_cabe(self) -> None:
        # El §6 dice `≤`, no `<`: 120 sobre una base de 100 con 20% es
        # exactamente lo permitido, y rechazarlo mandaría a Control una
        # solicitud que no hace falta.
        assert not excede_el_umbral(
            cant_programada=Decimal(120),
            cant_base=Decimal(100),
            tolerancia_pct=Decimal(20),
        )


def _solicitud(
    *,
    tipo: TipoControlCambio = TipoControlCambio.EXTRA_CATALOGO,
    lineas: tuple[LineaDeCambio, ...] | None = None,
    motivo: str = "Se agotó la cantidad y falta el eje 3",
    rol: Rol = Rol.RESIDENTE,
) -> SolicitudDeCambio:
    return SolicitudDeCambio.crear(
        obra_id=OBRA,
        tipo=tipo,
        motivo=motivo,
        # `is None` y no `or`: una tupla vacía es un caso a probar —una
        # solicitud sin renglones— y `or` la sustituiría por el default.
        lineas=(
            (LineaDeCambio(cantidad=Decimal(10), actividad_id=ACT),)
            if lineas is None
            else lineas
        ),
        rol=rol,
    )


class TestLaSolicitud:
    def test_un_residente_la_crea(self) -> None:
        assert _solicitud().tipo is TipoControlCambio.EXTRA_CATALOGO

    def test_otro_rol_no(self) -> None:
        with pytest.raises(ErrorDeControlDeCambio, match="residente"):
            _solicitud(rol=Rol.CONTROL_OBRA)

    def test_sin_motivo_no(self) -> None:
        # Quien autoriza no estuvo en la obra: el motivo es todo lo que va a
        # tener para decidir.
        with pytest.raises(ErrorDeControlDeCambio, match="por qué"):
            _solicitud(motivo="   ")

    def test_sin_renglones_no_pide_nada(self) -> None:
        with pytest.raises(ErrorDeControlDeCambio, match="no pide nada"):
            _solicitud(lineas=())

    def test_varios_renglones_en_una_sola_solicitud(self) -> None:
        # El residente pide por sub-frente: si se le agotó el cemento en tres
        # actividades manda una solicitud con tres renglones.
        solicitud = _solicitud(
            lineas=(
                LineaDeCambio(cantidad=Decimal(10), actividad_id=ACT),
                LineaDeCambio(cantidad=Decimal(5), actividad_id="act-2"),
                LineaDeCambio(cantidad=Decimal(3), actividad_id="act-3"),
            )
        )
        assert len(solicitud.lineas) == 3

    def test_el_importe_es_lo_que_le_mueve_al_costo_de_la_obra(self) -> None:
        # Es la cifra con la que Control decide: tres actividades de mil se
        # autorizan distinto que una de tres mil, pero el total es el mismo y
        # tiene que estar a la vista.
        solicitud = _solicitud(
            lineas=(
                LineaDeCambio(
                    cantidad=Decimal(10),
                    actividad_id=ACT,
                    precio_unitario=Decimal(250),
                ),
                LineaDeCambio(
                    cantidad=Decimal(4),
                    actividad_id="act-2",
                    precio_unitario=Decimal(125),
                ),
            )
        )
        assert solicitud.importe == Decimal(3000)

    def test_una_cantidad_en_cero_no_es_una_solicitud(self) -> None:
        with pytest.raises(ErrorDeControlDeCambio, match="mayor que cero"):
            _solicitud(lineas=(LineaDeCambio(cantidad=Decimal(0), actividad_id=ACT),))


class TestCadaTipoPideLoSuyo:
    def test_mas_cantidad_es_sobre_una_actividad_que_ya_existe(self) -> None:
        with pytest.raises(ErrorDeControlDeCambio, match="di cuál"):
            _solicitud(lineas=(LineaDeCambio(cantidad=Decimal(10)),))

    def test_una_sustitucion_dice_a_que_reemplaza(self) -> None:
        # Sin eso es un alta disfrazada y el costo se cuenta dos veces.
        with pytest.raises(ErrorDeControlDeCambio, match="reemplaza"):
            _solicitud(
                tipo=TipoControlCambio.SUSTITUCION,
                lineas=(LineaDeCambio(cantidad=Decimal(10), actividad_id=ACT),),
            )

    def test_un_alta_de_catalogo_pide_su_concepto(self) -> None:
        # De ahí salen su precio y su APU.
        with pytest.raises(ErrorDeControlDeCambio, match="concepto"):
            _solicitud(
                tipo=TipoControlCambio.ALTA_CATALOGO,
                lineas=(LineaDeCambio(cantidad=Decimal(10)),),
            )

    def test_fuera_de_catalogo_pide_descripcion_y_precio(self) -> None:
        # No hay concepto del cual tomar ninguno de los dos.
        with pytest.raises(ErrorDeControlDeCambio, match="descripción"):
            _solicitud(
                tipo=TipoControlCambio.FUERA_CATALOGO,
                lineas=(
                    LineaDeCambio(cantidad=Decimal(10), precio_unitario=Decimal(100)),
                ),
            )
        with pytest.raises(ErrorDeControlDeCambio, match="precio armado"):
            _solicitud(
                tipo=TipoControlCambio.FUERA_CATALOGO,
                lineas=(
                    LineaDeCambio(cantidad=Decimal(10), descripcion="Demoler muro"),
                ),
            )

    def test_fuera_de_catalogo_completa_pasa(self) -> None:
        solicitud = _solicitud(
            tipo=TipoControlCambio.FUERA_CATALOGO,
            lineas=(
                LineaDeCambio(
                    cantidad=Decimal(42),
                    descripcion="Demolición de bardas preexistentes",
                    precio_unitario=Decimal("383.33"),
                ),
            ),
        )
        assert solicitud.importe == Decimal("16099.86")


class TestLaSustitucion:
    def test_lo_ejecutado_se_estima_por_defecto(self) -> None:
        """El jefe de obra: *"la primera, pero también se puede descontar si se
        necesita"*.

        El trabajo se hizo y alguien lo pagó; descontarlo es la excepción que
        Control decide al autorizar, no la regla.
        """
        solicitud = _solicitud(
            tipo=TipoControlCambio.SUSTITUCION,
            lineas=(
                LineaDeCambio(
                    cantidad=Decimal(10), actividad_id=ACT, sustituye_a="act-vieja"
                ),
            ),
        )
        assert solicitud.descuenta_ejecutado is False
