"""Catálogos maestros (§7.3, §3.3, §3.5, §10.1)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.domain.catalogos.reglas import (
    Concepto,
    Contratista,
    ErrorDeCatalogo,
    Familia,
    Insumo,
    Unidad,
    resolver_iva,
)
from obractrl.domain.shared.diccionario import TipoConcepto, TipoInsumo


class TestUnidad:
    def test_normaliza_clave_y_sinonimos(self) -> None:
        unidad = Unidad.crear(
            clave=" pza ", nombre="Pieza", sinonimos=["pz", " PIEZA ", "pz"]
        )
        assert str(unidad.clave) == "PZA"
        # Los sinónimos se normalizan igual que la clave y se deduplican: si
        # `pz` y ` PZ ` cayeran distintos, el cruce del §10.3 fallaría.
        assert unidad.sinonimos == ("PZ", "PIEZA")

    def test_descarta_el_sinonimo_que_es_la_propia_clave(self) -> None:
        unidad = Unidad.crear(clave="M2", nombre="Metro cuadrado", sinonimos=["m2"])
        assert unidad.sinonimos == ()

    def test_exige_clave(self) -> None:
        with pytest.raises(ErrorDeCatalogo, match="clave"):
            Unidad.crear(clave="   ", nombre="Pieza")

    def test_el_factor_debe_ser_positivo(self) -> None:
        with pytest.raises(ErrorDeCatalogo, match="factor"):
            Unidad.crear(clave="PZA", nombre="Pieza", factor=Decimal(0))


class TestFamilia:
    def test_default_es_familia_de_materiales_gravada(self) -> None:
        familia = Familia.crear(clave="ACE", nombre="Aceros")
        assert (familia.aplica_a, familia.iva_aplica) == ("material", True)

    def test_acepta_familia_de_conceptos(self) -> None:
        familia = Familia.crear(clave="ALB", nombre="Albañilería", aplica_a="CONCEPTO")
        assert familia.aplica_a == "concepto"

    def test_rechaza_un_ambito_desconocido(self) -> None:
        with pytest.raises(ErrorDeCatalogo, match="Ámbito"):
            Familia.crear(clave="ACE", nombre="Aceros", aplica_a="insumo")

    def test_una_familia_puede_ser_exenta(self) -> None:
        # Pétreos / Jardinería nacen sin IVA (§3.5).
        petreos = Familia.crear(clave="PET", nombre="Pétreos", iva_aplica=False)
        assert petreos.iva_aplica is False


class TestIVA:
    """§3.5: la familia define, el insumo sobrescribe."""

    def test_sin_override_hereda_de_la_familia(self) -> None:
        assert resolver_iva(iva_familia=True, override_insumo=None) is True
        assert resolver_iva(iva_familia=False, override_insumo=None) is False

    def test_el_override_apaga_el_iva_de_una_familia_gravada(self) -> None:
        assert resolver_iva(iva_familia=True, override_insumo=False) is False

    def test_el_override_enciende_el_iva_de_una_familia_exenta(self) -> None:
        # `False` explícito y `None` NO son lo mismo: nulo es "hereda"
        # (`comment on column insumo.iva_aplica`, migración 0005).
        assert resolver_iva(iva_familia=False, override_insumo=True) is True

    def test_el_insumo_resuelve_su_propio_iva(self) -> None:
        arena = Insumo.crear(
            tipo=TipoInsumo.MATERIAL, clave="MAT-ARE", descripcion="Arena"
        )
        assert arena.iva_aplica is None
        assert arena.iva_efectivo(iva_familia=False) is False
        assert arena.iva_efectivo(iva_familia=True) is True

        gravado = Insumo.crear(
            tipo=TipoInsumo.MATERIAL,
            clave="MAT-CEM",
            descripcion="Cemento",
            iva_aplica=True,
        )
        assert gravado.iva_efectivo(iva_familia=False) is True


class TestInsumo:
    def test_material_es_un_insumo_con_tipo_material(self) -> None:
        # §7.3: no hay entidad `Material`; es la misma tabla.
        material = Insumo.crear(
            tipo="material", clave="mat-001", descripcion="  Cemento  gris "
        )
        assert material.es_material
        assert str(material.clave) == "MAT-001"
        assert material.descripcion == "Cemento gris"

    def test_la_mano_de_obra_no_es_material(self) -> None:
        assert not Insumo.crear(
            tipo=TipoInsumo.MANO_OBRA, clave="MOA-01", descripcion="Albañil"
        ).es_material

    def test_rechaza_un_tipo_fuera_del_diccionario(self) -> None:
        # Un valor fuera de los invariantes va a la bandeja (§10.3), no al
        # catálogo.
        with pytest.raises(ErrorDeCatalogo, match="Tipo de insumo"):
            Insumo.crear(tipo="consumible", clave="X-1", descripcion="X")

    def test_el_costo_base_no_puede_ser_negativo(self) -> None:
        with pytest.raises(ErrorDeCatalogo, match="costo_base"):
            Insumo.crear(
                tipo=TipoInsumo.MATERIAL,
                clave="MAT-1",
                descripcion="X",
                costo_base=Decimal("-1"),
            )

    def test_el_factor_de_conversion_debe_ser_positivo(self) -> None:
        with pytest.raises(ErrorDeCatalogo, match="factor_conversion"):
            Insumo.crear(
                tipo=TipoInsumo.MATERIAL,
                clave="MAT-1",
                descripcion="X",
                factor_conversion=Decimal(0),
            )


class TestConcepto:
    def test_default_es_un_concepto_de_obra(self) -> None:
        concepto = Concepto.crear(clave="est-001", descripcion="Muro de block")
        assert concepto.tipo is TipoConcepto.CONCEPTO
        assert str(concepto.clave) == "EST-001"
        # El prefijo es semilla editable (§8.7): se lee, no se exige.
        assert concepto.clave.prefijo == "EST"

    @pytest.mark.parametrize("tipo", [TipoConcepto.AUXILIAR, TipoConcepto.MATRIZ])
    def test_auxiliares_y_matrices_son_anidables(self, tipo: TipoConcepto) -> None:
        assert Concepto.crear(clave="AUX-1", descripcion="Mortero", tipo=tipo).es_anidable

    def test_un_concepto_normal_no_es_anidable(self) -> None:
        assert not Concepto.crear(clave="EST-1", descripcion="Muro").es_anidable

    def test_rechaza_un_tipo_fuera_del_diccionario(self) -> None:
        with pytest.raises(ErrorDeCatalogo, match="Tipo de concepto"):
            Concepto.crear(clave="EST-1", descripcion="Muro", tipo="partida")


class TestContratista:
    def test_normaliza_rfc_y_email(self) -> None:
        contratista = Contratista.crear(
            clave="ctr-01",
            razon_social="  Constructora   del Bajío  ",
            rfc=" cdb010203ab1 ",
            email="  Contacto@CDB.MX ",
        )
        assert str(contratista.clave) == "CTR-01"
        assert contratista.razon_social == "Constructora del Bajío"
        assert contratista.rfc == "CDB010203AB1"
        assert contratista.email == "contacto@cdb.mx"

    def test_los_datos_de_contacto_son_opcionales(self) -> None:
        contratista = Contratista.crear(clave="CTR-01", razon_social="X", rfc="  ")
        assert (contratista.rfc, contratista.email, contratista.telefono) == (
            None,
            None,
            None,
        )

    def test_la_calificacion_no_puede_ser_negativa(self) -> None:
        with pytest.raises(ErrorDeCatalogo, match="calificación"):
            Contratista.crear(
                clave="CTR-01", razon_social="X", calificacion=Decimal("-0.5")
            )

    def test_exige_razon_social(self) -> None:
        with pytest.raises(ErrorDeCatalogo, match="razon_social"):
            Contratista.crear(clave="CTR-01", razon_social="   ")
