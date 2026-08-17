"""Revisión física en campo (§7.8, §11.2 "Revisión física · Control de obra")."""

from __future__ import annotations

from datetime import date

import pytest

from obractrl.domain.revisiones.reglas import ErrorDeRevision, RevisionFisica
from obractrl.domain.shared.diccionario import Rol

FECHA = date(2026, 8, 14)


def _registrar(
    rol: Rol = Rol.CONTROL_OBRA,
    calidad: int | None = None,
    comentario: str | None = None,
    fotos: list[str] | None = None,
) -> RevisionFisica:
    return RevisionFisica.registrar(
        obra_id="obra-1",
        usuario_id="usr-ctrl",
        rol=rol,
        fecha=FECHA,
        fotos=fotos,
        comentario=comentario,
        calidad=calidad,
    )


class TestQuienRegistra:
    def test_control_de_obra_registra(self) -> None:
        revision = _registrar()
        assert revision.obra_id == "obra-1"
        assert revision.fecha == FECHA

    @pytest.mark.parametrize(
        "rol", [Rol.RESIDENTE, Rol.SUPERVISOR, Rol.SUPER_INTENDENTE]
    )
    def test_ningun_otro_rol_registra(self, rol: Rol) -> None:
        """§11.2 marca la `(C)` sobre el alta; §2 la llama "captura en campo
        de Control de obra"."""
        with pytest.raises(ErrorDeRevision, match="Solo Control de obra"):
            _registrar(rol=rol)


class TestCalidad:
    @pytest.mark.parametrize("calidad", [1, 3, 5])
    def test_acepta_la_escala_del_spec(self, calidad: int) -> None:
        assert _registrar(calidad=calidad).calidad == calidad

    @pytest.mark.parametrize("calidad", [0, 6, -1, 10])
    def test_rechaza_fuera_de_escala(self, calidad: int) -> None:
        """Misma regla que el `CHECK (calidad between 1 and 5)` de la
        migración 0009: se define en el dominio y la BD la espeja."""
        with pytest.raises(ErrorDeRevision, match="calidad"):
            _registrar(calidad=calidad)

    def test_es_opcional(self) -> None:
        # El §7.8 la declara nullable: una revisión puede ser solo fotos.
        assert _registrar(fotos=["org/foto.jpg"]).calidad is None


class TestContenido:
    def test_una_revision_puede_no_traer_nada_mas_que_la_fecha(self) -> None:
        """El §7.8 no exige fotos ni comentario, y el dominio no inventa la
        regla: la sola visita ya es un hecho que se registra."""
        revision = _registrar()
        assert revision.fotos == []
        assert revision.comentario is None

    def test_el_comentario_en_blanco_no_se_guarda_como_texto_vacio(self) -> None:
        assert _registrar(comentario="   ").comentario is None

    def test_las_fotos_se_copian_y_no_comparten_lista_con_quien_llama(self) -> None:
        fotos = ["org/a.jpg"]
        revision = _registrar(fotos=fotos)
        fotos.append("org/b.jpg")
        assert revision.fotos == ["org/a.jpg"]

    def test_los_vinculos_a_actividad_e_incidencia_conviven(self) -> None:
        """§7.8: "entidad propia que además puede vincularse a un avance o a
        una incidencia" — sin condición de exclusividad."""
        revision = RevisionFisica.registrar(
            obra_id="obra-1",
            usuario_id="usr-ctrl",
            rol=Rol.CONTROL_OBRA,
            fecha=FECHA,
            actividad_id="act-1",
            incidencia_id="inc-1",
        )
        assert revision.actividad_id == "act-1"
        assert revision.incidencia_id == "inc-1"
