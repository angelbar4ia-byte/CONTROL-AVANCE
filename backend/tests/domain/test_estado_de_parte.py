"""El estado de una parte y sus transiciones (D-571 a D-579)."""

from __future__ import annotations

import pytest

from obractrl.domain.partes.estado import (
    ORDEN,
    Accion,
    ErrorDeParte,
    EstadoDeParte,
    ParteNoPermitida,
    aplicar,
)
from obractrl.domain.shared.diccionario import Rol

E = EstadoDeParte
C = Rol.CONTROL_OBRA


def test_el_camino_completo_va_en_orden() -> None:
    estado = E.CUANTIFICANDO
    for accion in (
        Accion.ENVIAR_A_PRESUPUESTO,
        Accion.AUTORIZAR,
        Accion.VALIDAR,
        Accion.ENVIAR_A_PROGRAMA,
        Accion.PROGRAMAR,
        Accion.ASIGNAR,
    ):
        estado = aplicar(accion, estado=estado, rol=C)
    assert estado is E.ASIGNADA


@pytest.mark.parametrize(
    "accion, estado",
    [
        (Accion.AUTORIZAR, E.CUANTIFICANDO),
        (Accion.VALIDAR, E.ENVIADA_PRESUPUESTO),  # no se valida lo que no se autorizó
        (Accion.ENVIAR_A_PROGRAMA, E.POR_VALIDAR),  # programar pide autorizada
        (Accion.PROGRAMAR, E.AUTORIZADA),
        (Accion.ASIGNAR, E.ENVIADA_PROGRAMA),
        (Accion.ENVIAR_A_PRESUPUESTO, E.AUTORIZADA),
    ],
)
def test_no_se_salta_ningun_paso(accion: Accion, estado: E) -> None:
    with pytest.raises(ErrorDeParte, match="hace falta"):
        aplicar(accion, estado=estado, rol=C)


@pytest.mark.parametrize("rol", [Rol.RESIDENTE, Rol.SUPER_INTENDENTE])
def test_quien_no_tiene_el_permiso_no_puede(rol: Rol) -> None:
    for accion in Accion:
        with pytest.raises(ParteNoPermitida):
            aplicar(accion, estado=E.CUANTIFICANDO, rol=rol, a=E.CUANTIFICANDO)


def test_el_supervisor_programa_pero_no_autoriza() -> None:
    assert aplicar(Accion.PROGRAMAR, estado=E.ENVIADA_PROGRAMA, rol=Rol.SUPERVISOR) is E.PROGRAMADA
    with pytest.raises(ParteNoPermitida):
        aplicar(Accion.AUTORIZAR, estado=E.ENVIADA_PRESUPUESTO, rol=Rol.SUPERVISOR)


def test_el_permiso_va_antes_que_el_estado() -> None:
    # Quien no puede no se entera de en qué estado está la parte.
    with pytest.raises(ParteNoPermitida):
        aplicar(Accion.VALIDAR, estado=E.CUANTIFICANDO, rol=Rol.RESIDENTE)


@pytest.mark.parametrize("estado", [e for e in ORDEN if e is not E.CUANTIFICANDO and e is not E.ASIGNADA])
def test_volver_es_libre_hasta_asignar(estado: E) -> None:
    for destino in ORDEN[: ORDEN.index(estado)]:
        assert aplicar(Accion.DEVOLVER, estado=estado, rol=C, a=destino) is destino


def test_una_parte_asignada_ya_no_se_devuelve() -> None:
    with pytest.raises(ErrorDeParte, match="control de cambio"):
        aplicar(Accion.DEVOLVER, estado=E.ASIGNADA, rol=C, a=E.CUANTIFICANDO)


def test_devolver_solo_a_un_paso_anterior_y_diciendo_a_cual() -> None:
    with pytest.raises(ErrorDeParte, match="paso anterior"):
        aplicar(Accion.DEVOLVER, estado=E.AUTORIZADA, rol=C, a=E.AUTORIZADA)
    with pytest.raises(ErrorDeParte, match="paso anterior"):
        aplicar(Accion.DEVOLVER, estado=E.AUTORIZADA, rol=C, a=E.PROGRAMADA)
    with pytest.raises(ErrorDeParte, match="a qué estado"):
        aplicar(Accion.DEVOLVER, estado=E.AUTORIZADA, rol=C)


def test_costos_manda_y_autoriza_pero_no_valida_ni_programa_ni_asigna() -> None:
    K = Rol.COSTOS
    assert aplicar(Accion.ENVIAR_A_PRESUPUESTO, estado=E.CUANTIFICANDO, rol=K) is E.ENVIADA_PRESUPUESTO
    assert aplicar(Accion.AUTORIZAR, estado=E.ENVIADA_PRESUPUESTO, rol=K) is E.POR_VALIDAR
    # Control valida al final (D-571): quien autoriza no se valida a sí mismo.
    for accion, estado in (
        (Accion.VALIDAR, E.POR_VALIDAR),
        (Accion.ENVIAR_A_PROGRAMA, E.AUTORIZADA),
        (Accion.PROGRAMAR, E.ENVIADA_PROGRAMA),
        (Accion.ASIGNAR, E.PROGRAMADA),
        (Accion.DEVOLVER, E.AUTORIZADA),
    ):
        with pytest.raises(ParteNoPermitida):
            aplicar(accion, estado=estado, rol=K, a=E.CUANTIFICANDO)


def test_se_avisa_a_quien_da_el_siguiente_paso() -> None:
    from obractrl.domain.partes.estado import roles_del_siguiente_paso

    assert roles_del_siguiente_paso(E.ENVIADA_PRESUPUESTO) == {Rol.COSTOS, Rol.CONTROL_OBRA}
    assert roles_del_siguiente_paso(E.POR_VALIDAR) == {Rol.CONTROL_OBRA}
    assert roles_del_siguiente_paso(E.ENVIADA_PROGRAMA) == {Rol.CONTROL_OBRA, Rol.SUPERVISOR}
    assert roles_del_siguiente_paso(E.CUANTIFICANDO) == {Rol.COSTOS, Rol.CONTROL_OBRA}
    assert roles_del_siguiente_paso(E.ASIGNADA) == frozenset()
