"""El cierre de un frente (migración 0071; D-515/D-522/D-261)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.cierres.frente import (
    UMBRAL_CIERRE_DE_FRENTE,
    CierreDeFrente,
    EstatusCierreFrente,
    frente_listo_para_cierre,
)
from obractrl.domain.cierres.reglas import ErrorDeCierre
from obractrl.domain.shared.diccionario import Rol

D = Decimal


def _solicitado(avance: str = "92") -> CierreDeFrente:
    return CierreDeFrente.solicitar(
        nivel_id="n1", residente_id="r1", rol=Rol.RESIDENTE, avance_pct=D(avance)
    )


class TestSolicitar:
    def test_el_residente_solicita_al_90_por_ciento(self) -> None:
        assert UMBRAL_CIERRE_DE_FRENTE == 90
        c = _solicitado("90")
        assert c.estatus is EstatusCierreFrente.SOLICITADO
        assert c.avance_pct == 90  # la constancia de cuánto llevaba

    def test_por_debajo_del_umbral_no_se_solicita(self) -> None:
        with pytest.raises(ErrorDeCierre, match="90"):
            _solicitado("89.99")

    @pytest.mark.parametrize("rol", [Rol.SUPERVISOR, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE])
    def test_solo_el_residente_solicita(self, rol: Rol) -> None:
        with pytest.raises(ErrorDeCierre, match="residente"):
            CierreDeFrente.solicitar(nivel_id="n1", residente_id="x", rol=rol, avance_pct=D(95))


class TestLaCadena:
    def test_solicita_aprueba_valida(self) -> None:
        c = _solicitado()
        c.aprobar(usuario_id="s1", rol=Rol.SUPERVISOR)
        assert c.estatus is EstatusCierreFrente.APROBADO
        assert c.aprobado_por == "s1"
        assert not c.esta_cerrado

        c.validar(usuario_id="c1", rol=Rol.CONTROL_OBRA, comentario="Recorrido hecho")
        assert c.estatus is EstatusCierreFrente.VALIDADO
        assert c.validado_por == "c1"
        assert c.comentarios == "Recorrido hecho"
        assert c.esta_cerrado

    def test_no_se_valida_lo_que_no_se_aprobo(self) -> None:
        with pytest.raises(ErrorDeCierre, match="No se puede pasar"):
            _solicitado().validar(usuario_id="c1", rol=Rol.CONTROL_OBRA)

    def test_cada_paso_es_de_su_rol(self) -> None:
        with pytest.raises(ErrorDeCierre, match="supervisor"):
            _solicitado().aprobar(usuario_id="c1", rol=Rol.CONTROL_OBRA)
        c = _solicitado()
        c.aprobar(usuario_id="s1", rol=Rol.SUPERVISOR)
        with pytest.raises(ErrorDeCierre, match="control de obra"):
            c.validar(usuario_id="s1", rol=Rol.SUPERVISOR)

    def test_rechaza_el_supervisor_o_control_con_motivo(self) -> None:
        for rol in (Rol.SUPERVISOR, Rol.CONTROL_OBRA):
            c = _solicitado()
            c.rechazar(usuario_id="u", rol=rol, motivo="Falta la losa")
            assert c.estatus is EstatusCierreFrente.RECHAZADO
            assert c.comentarios == "Falta la losa"
        with pytest.raises(ErrorDeCierre, match="motivo"):
            _solicitado().rechazar(usuario_id="u", rol=Rol.SUPERVISOR, motivo="  ")
        with pytest.raises(ErrorDeCierre, match="no puede rechazar"):
            _solicitado().rechazar(usuario_id="r", rol=Rol.RESIDENTE, motivo="x")

    def test_lo_validado_y_lo_rechazado_son_terminales(self) -> None:
        c = _solicitado()
        c.aprobar(usuario_id="s1", rol=Rol.SUPERVISOR)
        c.validar(usuario_id="c1", rol=Rol.CONTROL_OBRA)
        with pytest.raises(ErrorDeCierre, match="ninguna"):
            c.rechazar(usuario_id="c1", rol=Rol.CONTROL_OBRA, motivo="tarde")

        r = _solicitado()
        r.rechazar(usuario_id="s1", rol=Rol.SUPERVISOR, motivo="no")
        with pytest.raises(ErrorDeCierre, match="ninguna"):
            r.aprobar(usuario_id="s1", rol=Rol.SUPERVISOR)

    def test_un_rechazo_tambien_cabe_tras_la_aprobacion(self) -> None:
        c = _solicitado()
        c.aprobar(usuario_id="s1", rol=Rol.SUPERVISOR)
        c.rechazar(usuario_id="c1", rol=Rol.CONTROL_OBRA, motivo="Calidad")
        assert c.estatus is EstatusCierreFrente.RECHAZADO


class TestFrenteListoParaCierre:
    def test_avisa_al_llegar_al_umbral_si_no_se_ha_solicitado(self) -> None:
        assert frente_listo_para_cierre(D(90), estatus_vivo=None)
        assert not frente_listo_para_cierre(D("89.9"), estatus_vivo=None)

    def test_ya_solicitado_ya_no_avisa(self) -> None:
        for vivo in ("solicitado", "aprobado", "validado"):
            assert not frente_listo_para_cierre(D(95), estatus_vivo=vivo)
