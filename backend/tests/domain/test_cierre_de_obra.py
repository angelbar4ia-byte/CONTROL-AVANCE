"""Cierre de obra final — workflow D (§11.3 D).

Lo que se fija aquí es la distinción que hace útil esta ruta: **qué pendiente
bloquea la entrega y cuál solo se informa**. Confundirlos la rompe por los dos
lados — si todo bloquea, el cierre es imposible y la gente aprende a saltárselo;
si nada bloquea, se firma una entrega con dinero sin resolver.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.cierres.obra import (
    ROLES_QUE_PARTICIPAN,
    CierreDeObra,
    ErrorDeCierreDeObra,
    evaluar_pendientes,
    puede_abrir_cierre_de_obra,
)
from obractrl.domain.shared.diccionario import Rol

OBRA = "11111111-1111-1111-1111-111111111111"


def estado(**cambios: object) -> dict[str, object]:
    """Una obra lista para entregar: todo en cero y avance completo."""
    base: dict[str, object] = {
        "avance_pct": Decimal(100),
        "actividades_sin_concluir": 0,
        "cierres_pendientes": 0,
        "estimaciones_sin_validar": 0,
        "incidencias_abiertas": 0,
        "incidencias_detienen": 0,
        "documentos_expediente": 3,
        "evaluaciones_finales": 1,
    }
    base.update(cambios)
    return base


def claves(pendientes: list) -> set[str]:
    return {p.clave for p in pendientes}


def bloqueantes(pendientes: list) -> set[str]:
    return {p.clave for p in pendientes if p.bloquea}


class TestQuienAbre:
    def test_solo_el_super_intendente(self) -> None:
        assert puede_abrir_cierre_de_obra(Rol.SUPER_INTENDENTE)

    @pytest.mark.parametrize(
        "rol", [Rol.RESIDENTE, Rol.SUPERVISOR, Rol.CONTROL_OBRA]
    )
    def test_los_demas_no(self, rol: Rol) -> None:
        """Abrir convoca a firmar una entrega. Que lo dispare quien responde por
        la organización impide darla por entregada desde dentro."""
        assert not puede_abrir_cierre_de_obra(rol)


class TestPendientesQueBloquean:
    def test_una_obra_lista_no_tiene_pendientes(self) -> None:
        assert evaluar_pendientes(estado()) == []

    def test_avance_incompleto(self) -> None:
        pendientes = evaluar_pendientes(estado(avance_pct=Decimal("87.5")))
        assert "avance_incompleto" in bloqueantes(pendientes)

    def test_actividades_sin_concluir(self) -> None:
        pendientes = evaluar_pendientes(estado(actividades_sin_concluir=3))
        assert "actividades_sin_concluir" in bloqueantes(pendientes)

    def test_cierres_de_actividad_esperando(self) -> None:
        pendientes = evaluar_pendientes(estado(cierres_pendientes=2))
        assert "cierres_pendientes" in bloqueantes(pendientes)

    def test_estimaciones_sin_validar(self) -> None:
        """Hay dinero sin resolver: firmar la entrega lo daría por bueno sin que
        nadie lo haya mirado (§11.3 E)."""
        pendientes = evaluar_pendientes(estado(estimaciones_sin_validar=1))
        assert "estimaciones_sin_validar" in bloqueantes(pendientes)

    def test_una_incidencia_que_detiene(self) -> None:
        """No es un detalle de calidad: es la obra parada."""
        pendientes = evaluar_pendientes(
            estado(incidencias_abiertas=1, incidencias_detienen=1)
        )
        assert "incidencias_detienen" in bloqueantes(pendientes)


class TestPendientesQueSoloSeInforman:
    def test_incidencias_abiertas_que_no_detienen(self) -> None:
        pendientes = evaluar_pendientes(estado(incidencias_abiertas=2))
        assert "incidencias_abiertas" in claves(pendientes)
        assert "incidencias_abiertas" not in bloqueantes(pendientes)

    def test_no_cuenta_dos_veces_las_que_detienen(self) -> None:
        # Tres abiertas de las cuales una detiene: dos entradas distintas, no
        # tres incidencias inventadas.
        pendientes = evaluar_pendientes(
            estado(incidencias_abiertas=3, incidencias_detienen=1)
        )
        abiertas = next(p for p in pendientes if p.clave == "incidencias_abiertas")
        detienen = next(p for p in pendientes if p.clave == "incidencias_detienen")
        assert abiertas.cuantos == 2
        assert detienen.cuantos == 1

    def test_expediente_vacio(self) -> None:
        pendientes = evaluar_pendientes(estado(documentos_expediente=0))
        assert "expediente_vacio" in claves(pendientes)
        assert "expediente_vacio" not in bloqueantes(pendientes)

    def test_sin_evaluacion_final(self) -> None:
        pendientes = evaluar_pendientes(estado(evaluaciones_finales=0))
        assert "sin_evaluacion_final" in claves(pendientes)
        assert "sin_evaluacion_final" not in bloqueantes(pendientes)

    def test_un_estado_incompleto_no_revienta(self) -> None:
        """El repositorio junta siete contextos: si uno viniera vacío, la
        pantalla tiene que seguir diciendo algo en vez de tronar."""
        pendientes = evaluar_pendientes({})
        assert "avance_incompleto" in bloqueantes(pendientes)


class TestParticipacion:
    def test_los_cuatro_roles_de_la_cadena_de_mando_participan_y_costos_no(self) -> None:
        # Costos cuantifica y forma el presupuesto (D-575): no entrega ni firma la obra.
        assert set(ROLES_QUE_PARTICIPAN) == set(Rol) - {Rol.COSTOS}

    def test_registrar_no_muta_el_original(self) -> None:
        """Devuelve un cierre nuevo para que el caso de uso pueda comprobar si
        con esta firma ya se cierra, sin haber tocado nada."""
        cierre = CierreDeObra(obra_id=OBRA)
        despues = cierre.registrar_participacion(Rol.RESIDENTE)
        assert cierre.participantes == frozenset()
        assert despues.participantes == frozenset({Rol.RESIDENTE})

    def test_el_mismo_rol_no_participa_dos_veces(self) -> None:
        cierre = CierreDeObra(obra_id=OBRA, participantes=frozenset({Rol.RESIDENTE}))
        with pytest.raises(ErrorDeCierreDeObra, match="ya registró"):
            cierre.registrar_participacion(Rol.RESIDENTE)

    def test_no_se_participa_en_una_obra_ya_cerrada(self) -> None:
        cierre = CierreDeObra(obra_id=OBRA, cerrada=True)
        with pytest.raises(ErrorDeCierreDeObra, match="ya está cerrada"):
            cierre.registrar_participacion(Rol.RESIDENTE)

    def test_faltan_dice_quienes(self) -> None:
        cierre = CierreDeObra(
            obra_id=OBRA, participantes=frozenset({Rol.RESIDENTE, Rol.SUPERVISOR})
        )
        assert set(cierre.faltan_por_participar) == {
            Rol.CONTROL_OBRA,
            Rol.SUPER_INTENDENTE,
        }
        assert not cierre.participaron_todos


class TestCerrar:
    def _completo(self) -> CierreDeObra:
        return CierreDeObra(obra_id=OBRA, participantes=frozenset(ROLES_QUE_PARTICIPAN))

    def test_con_todos_y_sin_bloqueantes_se_cierra(self) -> None:
        self._completo().exigir_que_se_pueda_cerrar(evaluar_pendientes(estado()))

    def test_si_falta_alguien_lo_dice(self) -> None:
        cierre = CierreDeObra(obra_id=OBRA, participantes=frozenset({Rol.RESIDENTE}))
        with pytest.raises(ErrorDeCierreDeObra, match="Faltan por participar"):
            cierre.exigir_que_se_pueda_cerrar([])

    def test_si_falta_resolver_lo_dice_distinto(self) -> None:
        """Quien lee el error necesita saber si le falta convocar o resolver:
        son dos acciones distintas y no se pueden confundir en un mensaje."""
        pendientes = evaluar_pendientes(estado(estimaciones_sin_validar=1))
        with pytest.raises(ErrorDeCierreDeObra, match="no se puede entregar"):
            self._completo().exigir_que_se_pueda_cerrar(pendientes)

    def test_los_que_no_bloquean_dejan_cerrar(self) -> None:
        """Un expediente vacío hay que verlo, pero no describe trabajo sin
        terminar: bloquear con él haría el cierre un trámite imposible."""
        pendientes = evaluar_pendientes(
            estado(documentos_expediente=0, evaluaciones_finales=0, incidencias_abiertas=2)
        )
        assert pendientes, "el escenario debe tener pendientes informativos"
        self._completo().exigir_que_se_pueda_cerrar(pendientes)
