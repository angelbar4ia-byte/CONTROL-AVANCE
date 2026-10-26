"""Reprogramar lo asignado (migración 0072; D-533, P-4): la cadena con salto."""

from __future__ import annotations

from datetime import date

import pytest

from obractrl.domain.programacion.reprogramacion import (
    ROLES_QUE_RECIBEN_OBSERVACIONES,
    ErrorDeReprogramacion,
    EstatusReprogramacion,
    FechasDeLoAsignado,
    Reprogramacion,
    esta_asignada,
    exigir_fechas_libres,
    roles_a_avisar_al_aplicar,
    texto_de_observacion,
)
from obractrl.domain.shared.diccionario import Rol

INICIO = date(2026, 3, 2)
TERMINO = date(2026, 3, 13)


def _proponer(rol: Rol = Rol.RESIDENTE, **cambios) -> Reprogramacion:
    datos = {
        "actividad_id": "a1",
        "usuario_id": "u1",
        "rol": rol,
        "motivo": "El contratista no tenía cuadrilla",
        "asignada": True,
        "fecha_inicio": date(2026, 3, 9),
        "fecha_termino": date(2026, 3, 20),
        "fecha_inicio_actual": INICIO,
        "fecha_termino_actual": TERMINO,
    }
    datos.update(cambios)
    return Reprogramacion.proponer(**datos)


class TestLoAsignado:
    def test_asignada_es_tener_contratista(self) -> None:
        assert esta_asignada(contratista_id="c1")
        assert not esta_asignada(contratista_id=None)

    def test_las_fechas_de_lo_asignado_no_se_editan_directo(self) -> None:
        with pytest.raises(FechasDeLoAsignado, match="reprogramación"):
            exigir_fechas_libres(asignada=True, toca_fechas=True)

    def test_lo_asignado_si_admite_editar_lo_que_no_son_fechas(self) -> None:
        exigir_fechas_libres(asignada=True, toca_fechas=False)

    def test_lo_no_asignado_se_edita_libre(self) -> None:
        exigir_fechas_libres(asignada=False, toca_fechas=True)


class TestProponer:
    def test_el_residente_propone_y_queda_pendiente_de_revision(self) -> None:
        r = _proponer(Rol.RESIDENTE)
        assert r.estatus is EstatusReprogramacion.PROPUESTA
        assert r.propuesta_rol is Rol.RESIDENTE
        assert r.revisada_por is None

    def test_el_supervisor_propone_y_se_salta_la_revision(self) -> None:
        r = _proponer(Rol.SUPERVISOR)
        assert r.estatus is EstatusReprogramacion.REVISADA
        # La revisión se salta: nadie revisó, y el rastro no finge lo contrario.
        assert r.revisada_por is None

    @pytest.mark.parametrize("rol", [Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE])
    def test_solo_residente_y_supervisor_proponen(self, rol: Rol) -> None:
        with pytest.raises(ErrorDeReprogramacion, match="residente o el supervisor"):
            _proponer(rol)

    def test_solo_se_reprograma_lo_asignado(self) -> None:
        with pytest.raises(ErrorDeReprogramacion, match="asignad"):
            _proponer(asignada=False)

    def test_pide_motivo(self) -> None:
        with pytest.raises(ErrorDeReprogramacion, match="motivo"):
            _proponer(motivo="   ")

    def test_pide_al_menos_una_fecha(self) -> None:
        with pytest.raises(ErrorDeReprogramacion, match="al menos una fecha"):
            _proponer(fecha_inicio=None, fecha_termino=None)

    def test_una_sola_fecha_basta(self) -> None:
        r = _proponer(fecha_inicio=None, fecha_termino=date(2026, 3, 20))
        assert r.fecha_inicio is None
        assert r.fecha_termino == date(2026, 3, 20)

    def test_el_termino_no_puede_ser_antes_del_inicio(self) -> None:
        with pytest.raises(ErrorDeReprogramacion, match="anterior"):
            _proponer(fecha_inicio=date(2026, 3, 20), fecha_termino=date(2026, 3, 10))

    def test_el_termino_nuevo_se_compara_con_el_inicio_que_ya_tenia(self) -> None:
        # Solo manda el término, y es anterior al inicio vigente.
        with pytest.raises(ErrorDeReprogramacion, match="anterior"):
            _proponer(fecha_inicio=None, fecha_termino=date(2026, 3, 1))

    def test_proponer_la_misma_fecha_no_es_reprogramar(self) -> None:
        with pytest.raises(ErrorDeReprogramacion, match="nada que reprogramar"):
            _proponer(fecha_inicio=INICIO, fecha_termino=TERMINO)
        with pytest.raises(ErrorDeReprogramacion, match="nada que reprogramar"):
            _proponer(fecha_inicio=INICIO, fecha_termino=None)


class TestLaCadena:
    def test_residente_supervisor_control_control(self) -> None:
        r = _proponer(Rol.RESIDENTE)
        r.revisar(usuario_id="s1", rol=Rol.SUPERVISOR)
        assert r.estatus is EstatusReprogramacion.REVISADA
        assert r.revisada_por == "s1"
        r.validar(usuario_id="c1", rol=Rol.CONTROL_OBRA)
        assert r.estatus is EstatusReprogramacion.VALIDADA
        r.aplicar(usuario_id="c2", rol=Rol.CONTROL_OBRA)
        assert r.estatus is EstatusReprogramacion.APLICADA
        assert (r.validada_por, r.aplicada_por) == ("c1", "c2")

    def test_si_propone_el_supervisor_va_directo_a_control(self) -> None:
        r = _proponer(Rol.SUPERVISOR)
        r.validar(usuario_id="c1", rol=Rol.CONTROL_OBRA)
        r.aplicar(usuario_id="c1", rol=Rol.CONTROL_OBRA)
        assert r.estatus is EstatusReprogramacion.APLICADA

    def test_no_se_valida_lo_que_nadie_reviso(self) -> None:
        r = _proponer(Rol.RESIDENTE)
        with pytest.raises(ErrorDeReprogramacion, match="No se puede pasar"):
            r.validar(usuario_id="c1", rol=Rol.CONTROL_OBRA)

    def test_no_se_aplica_lo_que_no_se_valido(self) -> None:
        r = _proponer(Rol.SUPERVISOR)
        with pytest.raises(ErrorDeReprogramacion, match="No se puede pasar"):
            r.aplicar(usuario_id="c1", rol=Rol.CONTROL_OBRA)

    def test_no_se_revisa_dos_veces(self) -> None:
        r = _proponer(Rol.RESIDENTE)
        r.revisar(usuario_id="s1", rol=Rol.SUPERVISOR)
        with pytest.raises(ErrorDeReprogramacion, match="No se puede pasar"):
            r.revisar(usuario_id="s1", rol=Rol.SUPERVISOR)

    @pytest.mark.parametrize("rol", [Rol.RESIDENTE, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE])
    def test_solo_el_supervisor_revisa(self, rol: Rol) -> None:
        with pytest.raises(ErrorDeReprogramacion, match="supervisor"):
            _proponer(Rol.RESIDENTE).revisar(usuario_id="x", rol=rol)

    @pytest.mark.parametrize("rol", [Rol.RESIDENTE, Rol.SUPERVISOR, Rol.SUPER_INTENDENTE])
    def test_solo_control_valida_y_realiza(self, rol: Rol) -> None:
        r = _proponer(Rol.SUPERVISOR)
        with pytest.raises(ErrorDeReprogramacion, match="control de obra"):
            r.validar(usuario_id="x", rol=rol)
        r.validar(usuario_id="c1", rol=Rol.CONTROL_OBRA)
        with pytest.raises(ErrorDeReprogramacion, match="control de obra"):
            r.aplicar(usuario_id="x", rol=rol)


class TestRechazar:
    def test_el_supervisor_rechaza_lo_que_revisa(self) -> None:
        r = _proponer(Rol.RESIDENTE)
        r.rechazar(usuario_id="s1", rol=Rol.SUPERVISOR, motivo="No hay sustento")
        assert r.estatus is EstatusReprogramacion.RECHAZADA
        assert r.rechazada_por == "s1"
        assert r.motivo_rechazo == "No hay sustento"

    def test_despues_de_revisar_decide_control_no_el_supervisor(self) -> None:
        r = _proponer(Rol.SUPERVISOR)
        with pytest.raises(ErrorDeReprogramacion, match="control de obra"):
            r.rechazar(usuario_id="s1", rol=Rol.SUPERVISOR, motivo="me arrepentí")
        r.rechazar(usuario_id="c1", rol=Rol.CONTROL_OBRA, motivo="Rompe el compromiso")
        assert r.estatus is EstatusReprogramacion.RECHAZADA

    def test_control_rechaza_aun_lo_validado(self) -> None:
        r = _proponer(Rol.SUPERVISOR)
        r.validar(usuario_id="c1", rol=Rol.CONTROL_OBRA)
        r.rechazar(usuario_id="c1", rol=Rol.CONTROL_OBRA, motivo="Cambió el contrato")
        assert r.estatus is EstatusReprogramacion.RECHAZADA

    def test_el_rechazo_requiere_motivo(self) -> None:
        with pytest.raises(ErrorDeReprogramacion, match="motivo"):
            _proponer().rechazar(usuario_id="s1", rol=Rol.SUPERVISOR, motivo=" ")

    def test_lo_aplicado_y_lo_rechazado_ya_no_se_mueven(self) -> None:
        aplicada = _proponer(Rol.SUPERVISOR)
        aplicada.validar(usuario_id="c1", rol=Rol.CONTROL_OBRA)
        aplicada.aplicar(usuario_id="c1", rol=Rol.CONTROL_OBRA)
        with pytest.raises(ErrorDeReprogramacion, match="No se puede pasar"):
            aplicada.rechazar(usuario_id="c1", rol=Rol.CONTROL_OBRA, motivo="tarde")

        rechazada = _proponer(Rol.RESIDENTE)
        rechazada.rechazar(usuario_id="s1", rol=Rol.SUPERVISOR, motivo="no")
        with pytest.raises(ErrorDeReprogramacion, match="No se puede pasar"):
            rechazada.revisar(usuario_id="s1", rol=Rol.SUPERVISOR)

    def test_un_rol_ajeno_no_rechaza(self) -> None:
        with pytest.raises(ErrorDeReprogramacion, match="no puede rechazar"):
            _proponer().rechazar(usuario_id="r1", rol=Rol.RESIDENTE, motivo="x")


class TestAQuienSeAvisa:
    def test_si_propuso_el_residente_se_avisa_al_supervisor_y_a_control(self) -> None:
        assert roles_a_avisar_al_aplicar(Rol.RESIDENTE) == {Rol.SUPERVISOR, Rol.CONTROL_OBRA}

    def test_si_propuso_el_supervisor_se_avisa_al_residente_y_a_control(self) -> None:
        assert roles_a_avisar_al_aplicar(Rol.SUPERVISOR) == {Rol.RESIDENTE, Rol.CONTROL_OBRA}

    def test_nunca_se_avisa_a_quien_propuso(self) -> None:
        for propone in (Rol.RESIDENTE, Rol.SUPERVISOR):
            assert propone not in roles_a_avisar_al_aplicar(propone)

    @pytest.mark.parametrize("rol", [Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE])
    def test_quien_no_propone_no_tiene_a_quien_avisar(self, rol: Rol) -> None:
        with pytest.raises(ErrorDeReprogramacion, match="residente o el supervisor"):
            roles_a_avisar_al_aplicar(rol)


class TestObservaciones:
    def test_control_observa_al_residente_y_al_supervisor(self) -> None:
        assert {Rol.RESIDENTE, Rol.SUPERVISOR} == ROLES_QUE_RECIBEN_OBSERVACIONES
        assert texto_de_observacion(rol=Rol.CONTROL_OBRA, texto="  Ojo con la cuadrilla ") == (
            "Ojo con la cuadrilla"
        )

    @pytest.mark.parametrize("rol", [Rol.RESIDENTE, Rol.SUPERVISOR, Rol.SUPER_INTENDENTE])
    def test_solo_control_observa(self, rol: Rol) -> None:
        with pytest.raises(ErrorDeReprogramacion, match="control de obra"):
            texto_de_observacion(rol=rol, texto="algo")

    def test_la_observacion_dice_algo(self) -> None:
        with pytest.raises(ErrorDeReprogramacion, match="texto"):
            texto_de_observacion(rol=Rol.CONTROL_OBRA, texto="   ")
