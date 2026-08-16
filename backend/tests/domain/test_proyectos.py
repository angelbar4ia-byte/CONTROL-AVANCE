"""Estructura de proyecto (§7.2, §3.3)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from obractrl.domain.proyectos.reglas import (
    Cluster,
    ErrorDeProyecto,
    Prototipo,
    Proyecto,
)


class TestProyecto:
    def test_crea_con_clave_normalizada(self) -> None:
        proyecto = Proyecto.crear(clave="  magnolia  norte ", nombre="Magnolia")
        assert str(proyecto.clave) == "MAGNOLIA NORTE"
        assert proyecto.activo

    def test_exige_clave(self) -> None:
        with pytest.raises(ErrorDeProyecto, match="clave"):
            Proyecto.crear(clave="   ", nombre="Magnolia")

    def test_exige_nombre(self) -> None:
        with pytest.raises(ErrorDeProyecto, match="nombre"):
            Proyecto.crear(clave="MAGNOLIA", nombre="  ")

    def test_el_fin_estimado_no_precede_al_inicio(self) -> None:
        with pytest.raises(ErrorDeProyecto, match="fin estimado"):
            Proyecto.crear(
                clave="MAGNOLIA",
                nombre="Magnolia",
                inicio=date(2026, 3, 1),
                fin_estimado=date(2026, 2, 1),
            )

    def test_mismo_dia_de_inicio_y_fin_es_valido(self) -> None:
        proyecto = Proyecto.crear(
            clave="MAGNOLIA",
            nombre="Magnolia",
            inicio=date(2026, 3, 1),
            fin_estimado=date(2026, 3, 1),
        )
        assert proyecto.fin_estimado == date(2026, 3, 1)

    def test_normaliza_el_nombre_y_la_ubicacion(self) -> None:
        proyecto = Proyecto.crear(
            clave="MAGNOLIA", nombre="  Magnolia   Norte ", ubicacion=" Querétaro  QRO "
        )
        assert proyecto.nombre == "Magnolia Norte"
        assert proyecto.ubicacion == "Querétaro QRO"


class TestCluster:
    def test_crea_bajo_su_proyecto(self) -> None:
        cluster = Cluster.crear(proyecto_id="proy-1", clave="fresno", nombre="Fresno")
        assert cluster.proyecto_id == "proy-1"
        assert str(cluster.clave) == "FRESNO"

    def test_exige_proyecto(self) -> None:
        with pytest.raises(ErrorDeProyecto, match="proyecto_id"):
            Cluster.crear(proyecto_id="  ", clave="FRESNO", nombre="Fresno")

    def test_exige_nombre(self) -> None:
        with pytest.raises(ErrorDeProyecto, match="nombre"):
            Cluster.crear(proyecto_id="proy-1", clave="FRESNO", nombre="")


class TestPrototipo:
    def _prototipo(self, **extra: object) -> Prototipo:
        datos: dict = {
            "proyecto_id": "proy-1",
            "clave": "cas-01",
            "nombre": "Modelo Ámbar",
        }
        datos.update(extra)
        return Prototipo.crear(**datos)  # type: ignore[arg-type]

    def test_normaliza_la_clave_y_expone_su_prefijo(self) -> None:
        prototipo = self._prototipo()
        assert str(prototipo.clave) == "CAS-01"
        # El prefijo es semilla editable (§8.7): el dominio lo lee, no lo exige.
        assert prototipo.clave.prefijo == "CAS"

    def test_acepta_una_clave_sin_prefijo(self) -> None:
        prototipo = self._prototipo(clave="AMBAR")
        assert prototipo.clave.prefijo is None

    def test_m2_debe_ser_positivo(self) -> None:
        with pytest.raises(ErrorDeProyecto, match="m2"):
            self._prototipo(m2=Decimal(0))

    def test_al_menos_un_nivel(self) -> None:
        with pytest.raises(ErrorDeProyecto, match="nivel"):
            self._prototipo(niveles=0)

    def test_recamaras_no_negativas(self) -> None:
        with pytest.raises(ErrorDeProyecto, match="ecámaras"):
            self._prototipo(recamaras=-1)

    def test_cero_recamaras_es_valido(self) -> None:
        # Un prototipo puede ser de urbanización o un local sin recámaras.
        assert self._prototipo(recamaras=0).recamaras == 0

    def test_las_medidas_son_opcionales(self) -> None:
        prototipo = self._prototipo()
        assert (prototipo.m2, prototipo.niveles, prototipo.recamaras) == (
            None,
            None,
            None,
        )
