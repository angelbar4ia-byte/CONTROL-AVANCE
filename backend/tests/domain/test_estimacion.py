"""Estimación semanal (§6, §11.3 E)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.estimacion.reglas import (
    ConceptoEstimado,
    ErrorDeEstimacion,
    Estimacion,
    seleccionar_estimables,
)
from obractrl.domain.shared.diccionario import EstatusEstimacion, ModoPago, Rol
from obractrl.domain.shared.valores import Dinero, PrecioUnitario

D = Decimal


def _fila(
    actividad_id: str = "act-1",
    concepto_id: str | None = "con-1",
    cantidad_validada: str = "10",
    precio_unitario: str = "500",
    precio_destajo: str = "120",
    modo_pago: str = "destajo",
) -> dict:
    return {
        "actividad_id": actividad_id,
        "concepto_id": concepto_id,
        "cantidad_validada": D(cantidad_validada),
        "precio_unitario": D(precio_unitario),
        "precio_destajo": D(precio_destajo),
        "modo_pago": modo_pago,
    }


def _conceptos() -> list[ConceptoEstimado]:
    return seleccionar_estimables([_fila()], ModoPago.DESTAJO)


class TestSeleccionarEstimables:
    def test_calcula_el_importe_segun_el_modo(self) -> None:
        conceptos = seleccionar_estimables([_fila()], ModoPago.DESTAJO)
        assert len(conceptos) == 1
        assert conceptos[0].precio_unitario == Dinero("120")
        assert conceptos[0].importe == Dinero("1200")  # 10 * 120

    def test_modo_concepto_usa_el_cpu_completo(self) -> None:
        conceptos = seleccionar_estimables([_fila()], ModoPago.CONCEPTO)
        assert conceptos == []  # la fila es de modo destajo, no entra

    def test_filtra_filas_de_otro_modo(self) -> None:
        filas = [_fila(modo_pago="destajo"), _fila(actividad_id="act-2", modo_pago="concepto")]
        conceptos = seleccionar_estimables(filas, ModoPago.CONCEPTO)
        assert len(conceptos) == 1
        assert conceptos[0].actividad_id == "act-2"
        assert conceptos[0].precio_unitario == Dinero("500")  # CPU completo

    def test_sin_concepto_id_es_fuera_de_catalogo(self) -> None:
        conceptos = seleccionar_estimables([_fila(concepto_id=None)], ModoPago.DESTAJO)
        assert conceptos[0].fuera_catalogo


class TestGenerar:
    def test_monto_total_suma_los_conceptos(self) -> None:
        filas = [_fila(), _fila(actividad_id="act-2", cantidad_validada="5")]
        conceptos = seleccionar_estimables(filas, ModoPago.DESTAJO)
        estimacion = Estimacion.generar(
            obra_id="obra-1",
            semana=21,
            anio=2026,
            modo=ModoPago.DESTAJO,
            conceptos=conceptos,
            creada_por="usr-res",
            rol=Rol.RESIDENTE,
        )
        assert estimacion.monto_total == Dinero("1800")  # 1200 + 600
        assert estimacion.estatus is EstatusEstimacion.BORRADOR

    def test_solo_residente_o_supervisor_generan(self) -> None:
        for rol in (Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE):
            with pytest.raises(ErrorDeEstimacion, match="Residente o Supervisor"):
                Estimacion.generar(
                    obra_id="obra-1",
                    semana=21,
                    anio=2026,
                    modo=ModoPago.DESTAJO,
                    conceptos=_conceptos(),
                    creada_por="x",
                    rol=rol,
                )

    def test_sin_conceptos_no_hay_nada_que_estimar(self) -> None:
        with pytest.raises(ErrorDeEstimacion, match="No hay actividades"):
            Estimacion.generar(
                obra_id="obra-1",
                semana=21,
                anio=2026,
                modo=ModoPago.DESTAJO,
                conceptos=[],
                creada_por="usr-res",
                rol=Rol.RESIDENTE,
            )


class TestPeriodoBloqueado:
    """§11.3 E.5: validar cierra la semana de esa obra.

    Es el otro lado del evento `EstimacionValidada` ("notificar + **bloquear
    periodo**"). Sin este candado la misma semana se podría volver a estimar
    —y a cobrar—, que es exactamente lo que la migración 0020 impide en la
    base y esta regla impide en el dominio.
    """

    def _generar(self, *, periodo_bloqueado: bool) -> Estimacion:
        return Estimacion.generar(
            obra_id="obra-1",
            semana=21,
            anio=2026,
            modo=ModoPago.DESTAJO,
            conceptos=_conceptos(),
            creada_por="usr-res",
            rol=Rol.RESIDENTE,
            periodo_bloqueado=periodo_bloqueado,
        )

    def test_una_semana_ya_validada_no_admite_otra_estimacion(self) -> None:
        with pytest.raises(ErrorDeEstimacion, match="bloqueado"):
            self._generar(periodo_bloqueado=True)

    def test_el_mensaje_nombra_la_semana_y_el_anio(self) -> None:
        with pytest.raises(ErrorDeEstimacion, match=r"21/2026"):
            self._generar(periodo_bloqueado=True)

    def test_una_semana_abierta_genera_normal(self) -> None:
        assert self._generar(periodo_bloqueado=False).semana == 21

    def test_el_default_es_abierto(self) -> None:
        """Quien genera no siempre tiene por qué consultarlo: el caso de uso
        lo resuelve por el puerto y lo pasa."""
        estimacion = Estimacion.generar(
            obra_id="obra-1",
            semana=21,
            anio=2026,
            modo=ModoPago.DESTAJO,
            conceptos=_conceptos(),
            creada_por="usr-res",
            rol=Rol.RESIDENTE,
        )
        assert estimacion.estatus is EstatusEstimacion.BORRADOR

    def test_el_rol_se_valida_antes_que_el_candado(self) -> None:
        """Un Control de obra sobre una semana cerrada tiene dos problemas; el
        que se le reporta es el suyo, no el estado de la semana."""
        with pytest.raises(ErrorDeEstimacion, match="Residente o Supervisor"):
            Estimacion.generar(
                obra_id="obra-1",
                semana=21,
                anio=2026,
                modo=ModoPago.DESTAJO,
                conceptos=_conceptos(),
                creada_por="x",
                rol=Rol.CONTROL_OBRA,
                periodo_bloqueado=True,
            )


class TestFlujo:
    def _estimacion(self) -> Estimacion:
        return Estimacion.generar(
            obra_id="obra-1",
            semana=21,
            anio=2026,
            modo=ModoPago.DESTAJO,
            conceptos=_conceptos(),
            creada_por="usr-res",
            rol=Rol.RESIDENTE,
        )

    def test_enviar_y_validar(self) -> None:
        e = self._estimacion()
        e.enviar(rol=Rol.SUPERVISOR)
        assert e.estatus is EstatusEstimacion.ENVIADA

        e.validar(usuario_id="usr-ctrl", rol=Rol.CONTROL_OBRA)
        assert e.estatus is EstatusEstimacion.VALIDADA
        assert e.validada_por == "usr-ctrl"

    def test_control_no_envia(self) -> None:
        e = self._estimacion()
        with pytest.raises(ErrorDeEstimacion, match="Residente o Supervisor"):
            e.enviar(rol=Rol.CONTROL_OBRA)

    def test_supervisor_no_valida(self) -> None:
        e = self._estimacion()
        e.enviar(rol=Rol.RESIDENTE)
        with pytest.raises(ErrorDeEstimacion, match="Solo Control de obra"):
            e.validar(usuario_id="usr-sup", rol=Rol.SUPERVISOR)

    def test_no_se_valida_sin_enviar(self) -> None:
        e = self._estimacion()
        with pytest.raises(ErrorDeEstimacion, match="No se puede pasar"):
            e.validar(usuario_id="usr-ctrl", rol=Rol.CONTROL_OBRA)

    def test_validada_es_terminal(self) -> None:
        e = self._estimacion()
        e.enviar(rol=Rol.RESIDENTE)
        e.validar(usuario_id="usr-ctrl", rol=Rol.CONTROL_OBRA)
        with pytest.raises(ErrorDeEstimacion, match="ninguna"):
            e.enviar(rol=Rol.RESIDENTE)


class TestPrecioUnitarioIntegracion:
    """`PrecioUnitario.para_modo` es la fuente única del precio (§6)."""

    def test_precio_unitario_para_modo_coincide(self) -> None:
        pu = PrecioUnitario(total=Dinero("500"), destajo=Dinero("120"))
        conceptos = seleccionar_estimables([_fila()], ModoPago.DESTAJO)
        assert conceptos[0].precio_unitario == pu.para_modo("destajo")
