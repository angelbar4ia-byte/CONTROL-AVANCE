"""Reglas de la obra (§7.2, §6, §11.3 A y D)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from obractrl.domain.obras.reglas import (
    ErrorDeObra,
    Obra,
    TransicionDeObraInvalida,
)
from obractrl.domain.shared.diccionario import EstatusObra
from obractrl.domain.shared.valores import Avance


def _obra(**extra: object) -> Obra:
    datos: dict = {
        "cluster_id": "clu-1",
        "clave": "fresno 01",
        "prototipo_id": "proto-1",
    }
    datos.update(extra)
    return Obra.crear(**datos)  # type: ignore[arg-type]


class TestCrear:
    def test_nace_pendiente_y_sin_avance(self) -> None:
        obra = _obra()
        assert obra.estatus is EstatusObra.PENDIENTE
        assert obra.avance.pct == Decimal(0)

    def test_normaliza_la_clave(self) -> None:
        assert str(_obra(clave="  fresno   01 ").clave) == "FRESNO 01"

    def test_exige_cluster(self) -> None:
        with pytest.raises(ErrorDeObra, match="cluster"):
            _obra(cluster_id="  ")

    def test_exige_clave(self) -> None:
        with pytest.raises(ErrorDeObra, match="clave"):
            _obra(clave="   ")

    def test_una_obra_sin_prototipo_debe_ser_urba(self) -> None:
        # Espejo del ck_obra_urba de la migración 0004 (§7.2).
        with pytest.raises(ErrorDeObra, match="urbanización"):
            _obra(prototipo_id=None)

    def test_urba_sin_prototipo_es_valida(self) -> None:
        obra = _obra(prototipo_id=None, es_urba=True)
        assert obra.es_urba
        assert obra.prototipo_id is None

    def test_m2_debe_ser_positivo(self) -> None:
        with pytest.raises(ErrorDeObra, match="m2"):
            _obra(m2=Decimal("-1"))

    def test_el_fin_no_precede_al_inicio(self) -> None:
        with pytest.raises(ErrorDeObra, match="fin"):
            _obra(fecha_inicio=date(2026, 5, 10), fecha_fin=date(2026, 5, 1))


class TestEdicion:
    def test_renombrar_normaliza(self) -> None:
        obra = _obra()
        obra.renombrar(" fresno 02 ")
        assert str(obra.clave) == "FRESNO 02"

    def test_asignar_y_liberar_residente(self) -> None:
        obra = _obra()
        obra.asignar_residente("usr-res")
        assert obra.residente_id == "usr-res"
        obra.asignar_residente(None)
        assert obra.residente_id is None

    def test_programar_fechas_conserva_lo_no_enviado(self) -> None:
        obra = _obra(fecha_inicio=date(2026, 5, 1))
        obra.programar_fechas(fin=date(2026, 8, 1))
        assert obra.fecha_inicio == date(2026, 5, 1)
        assert obra.fecha_fin == date(2026, 8, 1)

    def test_programar_fechas_valida_contra_la_fecha_ya_guardada(self) -> None:
        obra = _obra(fecha_inicio=date(2026, 5, 1))
        with pytest.raises(ErrorDeObra, match="anterior al inicio"):
            obra.programar_fechas(fin=date(2026, 4, 1))

    def test_redimensionar_exige_positivo(self) -> None:
        obra = _obra()
        with pytest.raises(ErrorDeObra, match="m2"):
            obra.redimensionar(Decimal(0))


class TestCicloDeVida:
    def test_iniciar_fija_la_fecha(self) -> None:
        obra = _obra()
        obra.iniciar(date(2026, 5, 1))
        assert obra.estatus is EstatusObra.INICIADA
        assert obra.fecha_inicio == date(2026, 5, 1)

    def test_no_se_inicia_dos_veces(self) -> None:
        obra = _obra()
        obra.iniciar(date(2026, 5, 1))
        with pytest.raises(TransicionDeObraInvalida, match="pendiente"):
            obra.iniciar(date(2026, 5, 2))

    def test_no_se_entrega_una_obra_pendiente(self) -> None:
        with pytest.raises(TransicionDeObraInvalida, match="nunca arrancó"):
            _obra().entregar(date(2026, 9, 1))

    def test_entregar_congela_la_obra(self) -> None:
        obra = _obra()
        obra.iniciar(date(2026, 5, 1))
        obra.entregar(date(2026, 9, 1))
        assert obra.estatus is EstatusObra.ENTREGADA
        assert obra.fecha_fin == date(2026, 9, 1)
        assert obra.esta_congelada

    def test_una_obra_entregada_no_se_toca(self) -> None:
        obra = _obra()
        obra.iniciar(date(2026, 5, 1))
        obra.entregar(date(2026, 9, 1))

        for accion in (
            lambda: obra.sincronizar_avance(Avance(50)),
            lambda: obra.renombrar("FRESNO 99"),
            lambda: obra.asignar_residente("otro"),
            lambda: obra.redimensionar(Decimal(80)),
            lambda: obra.entregar(date(2026, 10, 1)),
        ):
            with pytest.raises(TransicionDeObraInvalida, match="congelada"):
                accion()


class TestAvance:
    """El estatus se deriva del avance, con la misma regla que la actividad (§6)."""

    def test_avance_parcial_pasa_a_en_proceso(self) -> None:
        obra = _obra()
        obra.sincronizar_avance(Avance("42.5"))
        assert obra.estatus is EstatusObra.EN_PROCESO
        assert obra.avance.pct == Decimal("42.50")

    def test_noventa_por_ciento_pasa_a_casi_lista(self) -> None:
        obra = _obra()
        obra.sincronizar_avance(Avance(90))
        assert obra.estatus is EstatusObra.CASI_LISTA

    def test_avance_cero_deja_la_obra_iniciada_como_estaba(self) -> None:
        obra = _obra()
        obra.iniciar(date(2026, 5, 1))
        obra.sincronizar_avance(Avance(0))
        assert obra.estatus is EstatusObra.INICIADA

    def test_avance_que_baja_a_cero_regresa_a_pendiente(self) -> None:
        obra = _obra()
        obra.sincronizar_avance(Avance(30))
        obra.sincronizar_avance(Avance(0))
        assert obra.estatus is EstatusObra.PENDIENTE


class TestGenerable:
    def test_devuelve_el_prototipo(self) -> None:
        assert _obra().exigir_generable(ya_tiene_actividades=False) == "proto-1"

    def test_una_urba_sin_prototipo_no_se_genera(self) -> None:
        obra = _obra(prototipo_id=None, es_urba=True)
        with pytest.raises(TransicionDeObraInvalida, match="no tiene prototipo"):
            obra.exigir_generable(ya_tiene_actividades=False)

    def test_no_se_regenera_una_obra_que_ya_tiene_actividades(self) -> None:
        with pytest.raises(TransicionDeObraInvalida, match="duplicaría"):
            _obra().exigir_generable(ya_tiene_actividades=True)

    def test_una_obra_entregada_no_se_genera(self) -> None:
        obra = _obra()
        obra.iniciar(date(2026, 5, 1))
        obra.entregar(date(2026, 9, 1))
        with pytest.raises(TransicionDeObraInvalida, match="congelada"):
            obra.exigir_generable(ya_tiene_actividades=False)
