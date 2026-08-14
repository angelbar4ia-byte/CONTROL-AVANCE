"""Flujo de cierre de actividad (§6, §4, §11.3 C)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.cierres.reglas import (
    ErrorDeCierre,
    SolicitudCierre,
    calcular_monto_cierre,
)
from obractrl.domain.shared.diccionario import EstatusSolicitudCierre, Rol
from obractrl.domain.shared.valores import Dinero

D = Decimal

CHECKLIST = [{"item": "Nivelación", "ok": True}]
ADJUNTOS = ["r2://evidencias/foto-1.jpg"]


def _solicitud() -> SolicitudCierre:
    return SolicitudCierre.solicitar(
        actividad_id="act-1",
        residente_id="usr-res",
        rol=Rol.RESIDENTE,
        cantidad=D("10"),
        precio_unitario=Dinero("250"),
        checklist=CHECKLIST,
        adjuntos=ADJUNTOS,
    )


class TestSolicitud:
    def test_calcula_el_monto(self) -> None:
        """`monto = cantidad × precio_unitario` (§6)."""
        assert _solicitud().monto == Dinero("2500")

    def test_solo_el_residente_solicita(self) -> None:
        for rol in (Rol.SUPERVISOR, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE):
            with pytest.raises(ErrorDeCierre, match="Solo el Residente"):
                SolicitudCierre.solicitar(
                    actividad_id="act-1",
                    residente_id="x",
                    rol=rol,
                    cantidad=D("1"),
                    precio_unitario=Dinero("1"),
                    checklist=CHECKLIST,
                    adjuntos=ADJUNTOS,
                )

    def test_exige_checklist_y_evidencias(self) -> None:
        with pytest.raises(ErrorDeCierre, match="checklist"):
            SolicitudCierre.solicitar(
                actividad_id="a", residente_id="u", rol=Rol.RESIDENTE,
                cantidad=D("1"), precio_unitario=Dinero("1"),
                checklist=[], adjuntos=ADJUNTOS,
            )
        with pytest.raises(ErrorDeCierre, match="evidencias"):
            SolicitudCierre.solicitar(
                actividad_id="a", residente_id="u", rol=Rol.RESIDENTE,
                cantidad=D("1"), precio_unitario=Dinero("1"),
                checklist=CHECKLIST, adjuntos=[],
            )


class TestAutorizarVsValidar:
    """`validar` ≠ `autorizar` (§4). Es la regla de permisos más delicada."""

    def test_el_supervisor_autoriza(self) -> None:
        s = _solicitud()
        s.autorizar(usuario_id="usr-sup", rol=Rol.SUPERVISOR)
        assert s.estatus is EstatusSolicitudCierre.AUTORIZADA
        assert s.autorizada_por == "usr-sup"

    def test_control_de_obra_NO_autoriza(self) -> None:
        s = _solicitud()
        with pytest.raises(ErrorDeCierre, match="no autoriza"):
            s.autorizar(usuario_id="usr-ctrl", rol=Rol.CONTROL_OBRA)

    def test_el_super_intendente_tampoco_autoriza_actividades(self) -> None:
        s = _solicitud()
        with pytest.raises(ErrorDeCierre):
            s.autorizar(usuario_id="usr-si", rol=Rol.SUPER_INTENDENTE)

    def test_control_de_obra_valida_y_comenta(self) -> None:
        s = _solicitud()
        s.autorizar(usuario_id="usr-sup", rol=Rol.SUPERVISOR)
        s.validar(usuario_id="usr-ctrl", rol=Rol.CONTROL_OBRA, comentario="Ok")
        assert s.estatus is EstatusSolicitudCierre.VALIDADA
        assert s.validada_por == "usr-ctrl"
        assert s.comentarios == "Ok"
        assert s.esta_cerrada

    def test_el_supervisor_no_valida(self) -> None:
        s = _solicitud()
        s.autorizar(usuario_id="usr-sup", rol=Rol.SUPERVISOR)
        with pytest.raises(ErrorDeCierre, match="Solo Control de obra valida"):
            s.validar(usuario_id="usr-sup", rol=Rol.SUPERVISOR)


class TestTransiciones:
    def test_no_se_valida_lo_que_no_se_autorizo(self) -> None:
        s = _solicitud()
        with pytest.raises(ErrorDeCierre, match="No se puede pasar"):
            s.validar(usuario_id="usr-ctrl", rol=Rol.CONTROL_OBRA)

    def test_validada_es_terminal(self) -> None:
        s = _solicitud()
        s.autorizar(usuario_id="usr-sup", rol=Rol.SUPERVISOR)
        s.validar(usuario_id="usr-ctrl", rol=Rol.CONTROL_OBRA)
        with pytest.raises(ErrorDeCierre, match="ninguna"):
            s.rechazar(usuario_id="usr-sup", rol=Rol.SUPERVISOR, motivo="tarde")

    def test_el_rechazo_exige_motivo(self) -> None:
        s = _solicitud()
        with pytest.raises(ErrorDeCierre, match="motivo"):
            s.rechazar(usuario_id="usr-sup", rol=Rol.SUPERVISOR, motivo="  ")

    def test_el_residente_no_rechaza_su_propia_solicitud(self) -> None:
        s = _solicitud()
        with pytest.raises(ErrorDeCierre):
            s.rechazar(usuario_id="usr-res", rol=Rol.RESIDENTE, motivo="me arrepentí")


def test_monto_no_acepta_cantidad_negativa() -> None:
    with pytest.raises(ErrorDeCierre):
        calcular_monto_cierre(D("-1"), Dinero("100"))
