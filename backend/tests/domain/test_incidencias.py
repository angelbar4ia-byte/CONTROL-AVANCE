"""Flujo de incidencias (§6, §7.8, §11.3 F)."""

from __future__ import annotations

import pytest

from obractrl.domain.incidencias.reglas import ErrorDeIncidencia, Incidencia
from obractrl.domain.shared.diccionario import (
    EstatusIncidencia,
    ImpactoIncidencia,
    Rol,
    TipoIncidencia,
)


def _incidencia(
    impacto: ImpactoIncidencia = ImpactoIncidencia.DETALLE,
    bloquea_actividades: list[str] | None = None,
) -> Incidencia:
    return Incidencia.abrir(
        obra_id="obra-1",
        creada_por="usr-res",
        tipo=TipoIncidencia.FALTA_MATERIAL,
        impacto=impacto,
        titulo="Falta cemento",
        descripcion="No llegó el pedido de la semana",
        bloquea_actividades=bloquea_actividades,
    )


class TestAbrir:
    def test_cualquier_rol_abre(self) -> None:
        # No hay chequeo de rol en `abrir`: cualquiera puede (§11.3 F.1).
        incidencia = _incidencia()
        assert incidencia.estatus is EstatusIncidencia.ABIERTA
        assert incidencia.creada_por == "usr-res"

    def test_exige_titulo(self) -> None:
        with pytest.raises(ErrorDeIncidencia, match="título"):
            Incidencia.abrir(
                obra_id="obra-1",
                creada_por="usr-res",
                tipo=TipoIncidencia.FALTA_MATERIAL,
                impacto=ImpactoIncidencia.DETALLE,
                titulo="   ",
            )

    def test_bloquea_actividades_solo_si_el_impacto_detiene(self) -> None:
        with pytest.raises(ErrorDeIncidencia, match="detiene"):
            _incidencia(
                impacto=ImpactoIncidencia.RETRASO,
                bloquea_actividades=["act-1"],
            )

    def test_impacto_detiene_puede_bloquear_actividades(self) -> None:
        incidencia = _incidencia(
            impacto=ImpactoIncidencia.DETIENE,
            bloquea_actividades=["act-1", "act-2"],
        )
        assert incidencia.bloquea_actividades == ["act-1", "act-2"]
        assert incidencia.bloquea_actividades_activo

    def test_impacto_detalle_no_bloquea_nada_por_defecto(self) -> None:
        incidencia = _incidencia()
        assert incidencia.bloquea_actividades == []
        assert not incidencia.bloquea_actividades_activo


class TestProgramar:
    def test_supervisor_programa(self) -> None:
        incidencia = _incidencia()
        incidencia.programar(rol=Rol.SUPERVISOR, asignada_a="usr-sup")
        assert incidencia.estatus is EstatusIncidencia.PROGRAMADA
        assert incidencia.asignada_a == "usr-sup"

    def test_control_de_obra_programa(self) -> None:
        incidencia = _incidencia()
        incidencia.programar(rol=Rol.CONTROL_OBRA, asignada_a="usr-ctrl")
        assert incidencia.estatus is EstatusIncidencia.PROGRAMADA

    def test_residente_no_programa(self) -> None:
        incidencia = _incidencia()
        with pytest.raises(ErrorDeIncidencia, match="Solo Supervisor o Control"):
            incidencia.programar(rol=Rol.RESIDENTE, asignada_a="usr-res")

    def test_super_intendente_no_programa(self) -> None:
        incidencia = _incidencia()
        with pytest.raises(ErrorDeIncidencia):
            incidencia.programar(rol=Rol.SUPER_INTENDENTE, asignada_a="usr-si")


class TestFlujoDeAtencion:
    def _programada(self) -> Incidencia:
        incidencia = _incidencia()
        incidencia.programar(rol=Rol.SUPERVISOR, asignada_a="usr-sup")
        return incidencia

    def test_atender_pasa_a_en_atencion(self) -> None:
        incidencia = self._programada()
        incidencia.atender()
        assert incidencia.estatus is EstatusIncidencia.EN_ATENCION

    def test_no_se_atiende_sin_programar(self) -> None:
        incidencia = _incidencia()
        with pytest.raises(ErrorDeIncidencia, match="No se puede pasar"):
            incidencia.atender()

    def test_solicitar_cierre_tras_atender(self) -> None:
        incidencia = self._programada()
        incidencia.atender()
        incidencia.solicitar_cierre()
        assert incidencia.estatus is EstatusIncidencia.CIERRE_SOLICITADO

    def test_no_se_solicita_cierre_sin_atender(self) -> None:
        incidencia = self._programada()
        with pytest.raises(ErrorDeIncidencia, match="No se puede pasar"):
            incidencia.solicitar_cierre()


class TestCerrarYRechazar:
    def _lista_para_cerrar(self) -> Incidencia:
        incidencia = _incidencia(
            impacto=ImpactoIncidencia.DETIENE, bloquea_actividades=["act-1"]
        )
        incidencia.programar(rol=Rol.SUPERVISOR, asignada_a="usr-sup")
        incidencia.atender()
        incidencia.solicitar_cierre()
        return incidencia

    def test_supervisor_cierra(self) -> None:
        incidencia = self._lista_para_cerrar()
        incidencia.cerrar(rol=Rol.SUPERVISOR)
        assert incidencia.estatus is EstatusIncidencia.CERRADA

    def test_control_de_obra_cierra(self) -> None:
        incidencia = self._lista_para_cerrar()
        incidencia.cerrar(rol=Rol.CONTROL_OBRA)
        assert incidencia.estatus is EstatusIncidencia.CERRADA

    def test_residente_no_cierra(self) -> None:
        incidencia = self._lista_para_cerrar()
        with pytest.raises(ErrorDeIncidencia, match="Solo Supervisor o Control"):
            incidencia.cerrar(rol=Rol.RESIDENTE)

    def test_no_se_cierra_sin_cierre_solicitado(self) -> None:
        incidencia = _incidencia()
        with pytest.raises(ErrorDeIncidencia, match="No se puede pasar"):
            incidencia.cerrar(rol=Rol.SUPERVISOR)

    def test_rechazar_exige_motivo(self) -> None:
        incidencia = self._lista_para_cerrar()
        with pytest.raises(ErrorDeIncidencia, match="motivo"):
            incidencia.rechazar(rol=Rol.SUPERVISOR, motivo="  ")

    def test_supervisor_rechaza(self) -> None:
        incidencia = self._lista_para_cerrar()
        incidencia.rechazar(rol=Rol.SUPERVISOR, motivo="Ya no aplica")
        assert incidencia.estatus is EstatusIncidencia.RECHAZADA

    def test_residente_no_rechaza(self) -> None:
        incidencia = self._lista_para_cerrar()
        with pytest.raises(ErrorDeIncidencia, match="Solo Supervisor o Control"):
            incidencia.rechazar(rol=Rol.RESIDENTE, motivo="motivo")


class TestTransicionesTerminales:
    def test_cerrada_es_terminal(self) -> None:
        incidencia = _incidencia()
        incidencia.programar(rol=Rol.SUPERVISOR, asignada_a="usr-sup")
        incidencia.atender()
        incidencia.solicitar_cierre()
        incidencia.cerrar(rol=Rol.SUPERVISOR)
        with pytest.raises(ErrorDeIncidencia, match="ninguna"):
            incidencia.atender()

    def test_rechazada_es_terminal(self) -> None:
        incidencia = _incidencia()
        incidencia.programar(rol=Rol.SUPERVISOR, asignada_a="usr-sup")
        incidencia.atender()
        incidencia.solicitar_cierre()
        incidencia.rechazar(rol=Rol.SUPERVISOR, motivo="No procede")
        with pytest.raises(ErrorDeIncidencia, match="ninguna"):
            incidencia.cerrar(rol=Rol.SUPERVISOR)
