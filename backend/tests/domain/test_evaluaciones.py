"""Evaluación de desempeño, 3 niveles (§6, §7.8, §11.3 H)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.evaluaciones.reglas import (
    ErrorDeEvaluacion,
    Evaluacion,
    RespuestaEvaluacion,
    calcular_puntaje,
)
from obractrl.domain.shared.diccionario import NivelEvaluacion, Rol, SujetoEvaluacion

D = Decimal


def _auto(
    *,
    rol: Rol = Rol.RESIDENTE,
    sujeto_tipo: SujetoEvaluacion = SujetoEvaluacion.RESIDENTE,
    sujeto_id: str = "usr-res",
    obra_residente_id: str | None = None,
) -> Evaluacion:
    return Evaluacion.crear(
        nivel=NivelEvaluacion.AUTO,
        evaluador_id="usr-res",
        rol=rol,
        sujeto_tipo=sujeto_tipo,
        sujeto_id=sujeto_id,
        periodo="2026-07",
        obra_id="obra-1" if sujeto_tipo is SujetoEvaluacion.OBRA else None,
        obra_residente_id=obra_residente_id,
    )


class TestNivelAuto:
    """Solo el Residente se autoevalúa, y solo a sí mismo o a su obra (§11.3 H.1)."""

    def test_el_residente_se_autoevalua(self) -> None:
        e = _auto(sujeto_tipo=SujetoEvaluacion.RESIDENTE, sujeto_id="usr-res")
        assert e.nivel is NivelEvaluacion.AUTO
        assert e.evaluador_id == "usr-res"

    def test_el_residente_evalua_su_propia_obra(self) -> None:
        e = _auto(
            sujeto_tipo=SujetoEvaluacion.OBRA,
            sujeto_id="obra-1",
            obra_residente_id="usr-res",
        )
        assert e.sujeto_tipo is SujetoEvaluacion.OBRA

    def test_ningun_otro_rol_crea_nivel_auto(self) -> None:
        for rol in (Rol.SUPERVISOR, Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE):
            with pytest.raises(ErrorDeEvaluacion, match="Solo el Residente"):
                _auto(rol=rol)

    def test_no_puede_autoevaluar_a_otro_residente(self) -> None:
        with pytest.raises(ErrorDeEvaluacion, match="no a otro residente"):
            _auto(sujeto_tipo=SujetoEvaluacion.RESIDENTE, sujeto_id="usr-otro")

    def test_no_puede_autoevaluar_una_obra_ajena(self) -> None:
        with pytest.raises(ErrorDeEvaluacion, match="propia obra"):
            _auto(
                sujeto_tipo=SujetoEvaluacion.OBRA,
                sujeto_id="obra-1",
                obra_residente_id="usr-otro-residente",
            )

    def test_nivel_auto_no_evalua_contratistas(self) -> None:
        with pytest.raises(ErrorDeEvaluacion, match="contratista"):
            _auto(sujeto_tipo=SujetoEvaluacion.CONTRATISTA, sujeto_id="contratista-1")


class TestNivelControl:
    """Control de obra evalúa obra + residente + contratista (§11.3 H.2)."""

    @pytest.mark.parametrize(
        "sujeto_tipo",
        [SujetoEvaluacion.OBRA, SujetoEvaluacion.RESIDENTE, SujetoEvaluacion.CONTRATISTA],
    )
    def test_control_de_obra_evalua_los_tres_sujetos(
        self, sujeto_tipo: SujetoEvaluacion
    ) -> None:
        e = Evaluacion.crear(
            nivel=NivelEvaluacion.CONTROL,
            evaluador_id="usr-ctrl",
            rol=Rol.CONTROL_OBRA,
            sujeto_tipo=sujeto_tipo,
            sujeto_id="sujeto-1",
            periodo="2026-07",
        )
        assert e.nivel is NivelEvaluacion.CONTROL
        assert e.sujeto_tipo is sujeto_tipo

    def test_ningun_otro_rol_crea_nivel_control(self) -> None:
        for rol in (Rol.RESIDENTE, Rol.SUPERVISOR, Rol.SUPER_INTENDENTE):
            with pytest.raises(ErrorDeEvaluacion, match="Solo Control de obra"):
                Evaluacion.crear(
                    nivel=NivelEvaluacion.CONTROL,
                    evaluador_id="usr-x",
                    rol=rol,
                    sujeto_tipo=SujetoEvaluacion.OBRA,
                    sujeto_id="obra-1",
                    periodo="2026-07",
                )


class TestNivelFinal:
    """Solo el Super intendente consolida (§11.3 H.3)."""

    def test_el_super_intendente_consolida(self) -> None:
        e = Evaluacion.crear(
            nivel=NivelEvaluacion.FINAL,
            evaluador_id="usr-si",
            rol=Rol.SUPER_INTENDENTE,
            sujeto_tipo=SujetoEvaluacion.RESIDENTE,
            sujeto_id="usr-res",
            periodo="2026-07",
        )
        assert e.nivel is NivelEvaluacion.FINAL

    def test_ningun_otro_rol_consolida(self) -> None:
        for rol in (Rol.RESIDENTE, Rol.SUPERVISOR, Rol.CONTROL_OBRA):
            with pytest.raises(ErrorDeEvaluacion, match="Solo el Super intendente"):
                Evaluacion.crear(
                    nivel=NivelEvaluacion.FINAL,
                    evaluador_id="usr-x",
                    rol=rol,
                    sujeto_tipo=SujetoEvaluacion.RESIDENTE,
                    sujeto_id="usr-res",
                    periodo="2026-07",
                )


class TestRespuestas:
    def test_agregar_respuestas_calcula_el_puntaje_ponderado(self) -> None:
        e = _auto()
        e.agregar_respuestas(
            [
                RespuestaEvaluacion(criterio_id="crit-1", valor=D("8")),
                RespuestaEvaluacion(criterio_id="crit-2", valor=D("10")),
            ],
            usuario_id="usr-res",
            pesos={"crit-1": D("1"), "crit-2": D("3")},
        )
        # (8*1 + 10*3) / (1+3) = 38/4 = 9.5
        assert e.puntaje == D("9.5")
        assert len(e.respuestas) == 2

    def test_solo_el_evaluador_agrega_respuestas(self) -> None:
        e = _auto()
        with pytest.raises(ErrorDeEvaluacion, match="Solo quien registró"):
            e.agregar_respuestas(
                [RespuestaEvaluacion(criterio_id="crit-1", valor=D("8"))],
                usuario_id="usr-otro",
                pesos={"crit-1": D("1")},
            )

    def test_no_se_responde_dos_veces_el_mismo_criterio(self) -> None:
        e = _auto()
        e.agregar_respuestas(
            [RespuestaEvaluacion(criterio_id="crit-1", valor=D("8"))],
            usuario_id="usr-res",
            pesos={"crit-1": D("1")},
        )
        with pytest.raises(ErrorDeEvaluacion, match="ya tiene respuesta"):
            e.agregar_respuestas(
                [RespuestaEvaluacion(criterio_id="crit-1", valor=D("5"))],
                usuario_id="usr-res",
                pesos={"crit-1": D("1")},
            )

    def test_exige_al_menos_una_respuesta(self) -> None:
        e = _auto()
        with pytest.raises(ErrorDeEvaluacion, match="No hay respuestas"):
            e.agregar_respuestas([], usuario_id="usr-res", pesos={})

    def test_respuesta_no_acepta_valor_negativo(self) -> None:
        with pytest.raises(ErrorDeEvaluacion):
            RespuestaEvaluacion(criterio_id="crit-1", valor=D("-1"))


class TestCalcularPuntaje:
    def test_sin_respuestas_no_hay_puntaje(self) -> None:
        assert calcular_puntaje([], {}) is None

    def test_sin_peso_conocido_no_hay_puntaje(self) -> None:
        respuestas = [RespuestaEvaluacion(criterio_id="crit-x", valor=D("8"))]
        assert calcular_puntaje(respuestas, {}) is None

    def test_promedio_ponderado(self) -> None:
        respuestas = [
            RespuestaEvaluacion(criterio_id="crit-1", valor=D("6")),
            RespuestaEvaluacion(criterio_id="crit-2", valor=D("10")),
        ]
        pesos = {"crit-1": D("1"), "crit-2": D("1")}
        assert calcular_puntaje(respuestas, pesos) == D("8")
