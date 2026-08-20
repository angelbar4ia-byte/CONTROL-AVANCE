"""Reglas de identidad: quién da de alta a quién (§4, §5.1).

Lo que se fija aquí es la parte del §4 que ninguna pantalla debe poder saltarse
—y que la base vuelve a imponer con el trigger de la migración 0025—: que
Control de obra pueda armar su equipo sin poder fabricarse un cómplice con más
privilegios, y que nadie se promueva a sí mismo.
"""

from __future__ import annotations

import pytest

from obractrl.domain.identidad.reglas import (
    LARGO_MINIMO_CONTRASENA,
    ContrasenaTemporal,
    ErrorDeIdentidad,
    Usuario,
    puede_asignar_alcance_de,
    puede_dar_de_alta,
)
from obractrl.domain.shared.diccionario import Rol


class TestQuienDaDeAlta:
    @pytest.mark.parametrize(
        "rol_nuevo",
        [Rol.RESIDENTE, Rol.SUPERVISOR, Rol.CONTROL_OBRA],
    )
    def test_control_de_obra_arma_su_equipo(self, rol_nuevo: Rol) -> None:
        """Es lo que promete la pantalla de Login (§5.1)."""
        assert puede_dar_de_alta(Rol.CONTROL_OBRA, rol_nuevo)

    def test_control_de_obra_no_fabrica_un_super_intendente(self) -> None:
        """Sería darse a sí mismo un cómplice con más privilegios que él."""
        assert not puede_dar_de_alta(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE)

    def test_el_super_intendente_si(self) -> None:
        assert puede_dar_de_alta(Rol.SUPER_INTENDENTE, Rol.SUPER_INTENDENTE)

    @pytest.mark.parametrize("quien", [Rol.RESIDENTE, Rol.SUPERVISOR])
    def test_quien_no_configura_no_da_de_alta(self, quien: Rol) -> None:
        assert not puede_dar_de_alta(quien, Rol.RESIDENTE)

    def test_el_alta_rechaza_el_rol_que_no_le_toca(self) -> None:
        with pytest.raises(ErrorDeIdentidad, match="no puede dar de alta"):
            Usuario.crear(
                nombre="Quien Sea",
                email="quien@obra.mx",
                rol=Rol.SUPER_INTENDENTE,
                creado_por=Rol.CONTROL_OBRA,
            )


class TestAlcance:
    def test_control_reparte_clusters_entre_supervisores(self) -> None:
        """Operación diaria: es la política `supervisor_cluster_*` de la 0012."""
        assert puede_asignar_alcance_de(Rol.CONTROL_OBRA, Rol.SUPERVISOR)

    def test_control_no_toca_los_proyectos_de_otro_control(self) -> None:
        """Ese puente decide el alcance de quien administra: si Control pudiera
        editarlo, se ampliaría el suyo."""
        assert not puede_asignar_alcance_de(Rol.CONTROL_OBRA, Rol.CONTROL_OBRA)
        assert puede_asignar_alcance_de(Rol.SUPER_INTENDENTE, Rol.CONTROL_OBRA)

    def test_el_residente_no_lleva_puente(self) -> None:
        """Llega a su obra por `obra.residente_id`, no por una tabla de alcance."""
        assert not puede_asignar_alcance_de(Rol.SUPER_INTENDENTE, Rol.RESIDENTE)


class TestAltaDeUsuario:
    def test_normaliza_nombre_y_correo(self) -> None:
        usuario = Usuario.crear(
            nombre="  Ana   Ruiz  ",
            email="  ANA@Obra.MX ",
            rol=Rol.RESIDENTE,
            creado_por=Rol.CONTROL_OBRA,
        )
        assert usuario.nombre == "Ana Ruiz"
        # En minúsculas porque `uq_usuario_email_org` distingue mayúsculas: sin
        # normalizar, "Ana@obra.mx" y "ana@obra.mx" serían dos personas.
        assert usuario.email == "ana@obra.mx"

    @pytest.mark.parametrize("correo", ["sin-arroba", "a@b", "@obra.mx", "a b@obra.mx"])
    def test_rechaza_un_correo_mal_formado(self, correo: str) -> None:
        with pytest.raises(ErrorDeIdentidad, match="forma válida"):
            Usuario.crear(
                nombre="Ana",
                email=correo,
                rol=Rol.RESIDENTE,
                creado_por=Rol.CONTROL_OBRA,
            )

    def test_los_opcionales_vacios_quedan_nulos(self) -> None:
        """Una cédula en blanco no es una cédula: guardarla como `""` haría
        que un filtro por "sin cédula" no la encontrara."""
        usuario = Usuario.crear(
            nombre="Ana",
            email="ana@obra.mx",
            rol=Rol.RESIDENTE,
            creado_por=Rol.CONTROL_OBRA,
            cedula="   ",
            telefono="",
        )
        assert usuario.cedula is None
        assert usuario.telefono is None


class TestCambioDeRol:
    def _alguien(self, rol: Rol = Rol.RESIDENTE) -> Usuario:
        return Usuario(nombre="Ana", email="ana@obra.mx", rol=rol)

    def test_nadie_se_promueve_a_si_mismo(self) -> None:
        usuario = self._alguien(Rol.CONTROL_OBRA)
        with pytest.raises(ErrorDeIdentidad, match="su propio rol"):
            usuario.cambiar_rol(
                Rol.SUPER_INTENDENTE, por=Rol.CONTROL_OBRA, es_uno_mismo=True
            )

    def test_control_no_promueve_a_super_intendente(self) -> None:
        usuario = self._alguien()
        with pytest.raises(ErrorDeIdentidad, match="super intendente"):
            usuario.cambiar_rol(
                Rol.SUPER_INTENDENTE, por=Rol.CONTROL_OBRA, es_uno_mismo=False
            )

    def test_control_tampoco_degrada_a_un_super_intendente(self) -> None:
        """La otra mitad del mismo problema: quitar el rol al único SI dejaría
        a la organización sin quien pueda otorgarlo."""
        usuario = self._alguien(Rol.SUPER_INTENDENTE)
        with pytest.raises(ErrorDeIdentidad, match="super intendente"):
            usuario.cambiar_rol(
                Rol.RESIDENTE, por=Rol.CONTROL_OBRA, es_uno_mismo=False
            )

    def test_control_si_mueve_los_demas_roles(self) -> None:
        usuario = self._alguien()
        usuario.cambiar_rol(Rol.SUPERVISOR, por=Rol.CONTROL_OBRA, es_uno_mismo=False)
        assert usuario.rol is Rol.SUPERVISOR

    def test_un_supervisor_no_cambia_roles(self) -> None:
        usuario = self._alguien()
        with pytest.raises(ErrorDeIdentidad, match="no puede cambiar roles"):
            usuario.cambiar_rol(
                Rol.SUPERVISOR, por=Rol.SUPERVISOR, es_uno_mismo=False
            )


class TestBaja:
    def test_desactiva_en_vez_de_borrar(self) -> None:
        """Sus capturas y cierres siguen apuntando a esta persona (§11.3)."""
        usuario = Usuario(nombre="Ana", email="ana@obra.mx", rol=Rol.RESIDENTE)
        usuario.desactivar(por=Rol.CONTROL_OBRA, es_uno_mismo=False)
        assert usuario.activo is False

    def test_nadie_se_da_de_baja_a_si_mismo(self) -> None:
        usuario = Usuario(nombre="Ana", email="ana@obra.mx", rol=Rol.CONTROL_OBRA)
        with pytest.raises(ErrorDeIdentidad, match="a sí mismo"):
            usuario.desactivar(por=Rol.CONTROL_OBRA, es_uno_mismo=True)

    def test_control_no_da_de_baja_a_un_super_intendente(self) -> None:
        usuario = Usuario(nombre="Ana", email="ana@obra.mx", rol=Rol.SUPER_INTENDENTE)
        with pytest.raises(ErrorDeIdentidad, match="super intendente"):
            usuario.desactivar(por=Rol.CONTROL_OBRA, es_uno_mismo=False)


class TestContrasenaTemporal:
    def test_exige_largo_minimo(self) -> None:
        with pytest.raises(ErrorDeIdentidad, match="al menos"):
            ContrasenaTemporal("corta")

    def test_acepta_una_de_largo_suficiente(self) -> None:
        valor = "x" * LARGO_MINIMO_CONTRASENA
        assert ContrasenaTemporal(valor).valor == valor

    def test_rechaza_espacios_en_los_bordes(self) -> None:
        """Se pierden al copiar y pegar, y la persona no puede entrar con una
        contraseña que sí le dictaron bien."""
        with pytest.raises(ErrorDeIdentidad, match="espacios"):
            ContrasenaTemporal(" " + "x" * LARGO_MINIMO_CONTRASENA)

    def test_no_se_filtra_al_representarla(self) -> None:
        """Un `repr()` accidental en una traza de Sentry la publicaría."""
        secreta = "contrasena-larga-de-prueba"
        temporal = ContrasenaTemporal(secreta)
        assert secreta not in repr(temporal)
        assert secreta not in str(temporal)
        assert secreta not in f"{temporal}"
