"""Explosión recursiva, CPU y versionado (§7.3, §10.8).

El caso que manda es el del §7.3: un concepto que anida un **auxiliar**, para
comprobar las dos cosas a la vez —que el CPU suma el costo del auxiliar y que
el destajo arrastra la mano de obra que vive **dentro** de él—.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

import pytest

from obractrl.domain.catalogos.apu import (
    CicloEnExplosion,
    Componente,
    ErrorDeAPU,
    ProfundidadExcedida,
    VersionCPU,
    calcular_cpu,
    explotar,
    publicar_version,
    siguiente_version,
    vigente_de,
)
from obractrl.domain.shared.diccionario import CategoriaExplosion, TipoHijoExplosion
from obractrl.domain.shared.valores import Dinero, PrecioUnitario


def material(clave: str, cantidad: str, costo: str, orden: int = 0) -> Componente:
    return Componente(
        categoria=CategoriaExplosion.MATERIAL,
        cantidad=Decimal(cantidad),
        clave_insumo=clave,
        costo_unitario=Decimal(costo),
        orden=orden,
    )


def mano_obra(clave: str, cantidad: str, costo: str, orden: int = 0) -> Componente:
    return Componente(
        categoria=CategoriaExplosion.MANO_OBRA,
        cantidad=Decimal(cantidad),
        clave_insumo=clave,
        costo_unitario=Decimal(costo),
        orden=orden,
    )


def auxiliar(clave: str, cantidad: str, orden: int = 0) -> Componente:
    return Componente(
        categoria=CategoriaExplosion.AUXILIAR,
        cantidad=Decimal(cantidad),
        clave_concepto=clave,
        orden=orden,
    )


class TestComponente:
    def test_apunta_a_un_insumo_o_a_un_concepto_pero_no_a_ambos(self) -> None:
        with pytest.raises(ErrorDeAPU, match="nunca a los dos"):
            Componente(
                categoria=CategoriaExplosion.MATERIAL,
                cantidad=Decimal(1),
                clave_insumo="MAT-1",
                clave_concepto="AUX-1",
            )

    def test_tiene_que_apuntar_a_algo(self) -> None:
        with pytest.raises(ErrorDeAPU, match="nunca a los dos"):
            Componente(categoria=CategoriaExplosion.MATERIAL, cantidad=Decimal(1))

    def test_la_cantidad_acepta_negativos_para_deducciones(self) -> None:
        """Un componente de deducción (material recuperado, ajuste) resta del
        importe del concepto en vez de sumar — no es un dato inválido."""
        componente = Componente(
            categoria=CategoriaExplosion.MATERIAL,
            cantidad=Decimal(-1),
            clave_insumo="MAT-1",
        )
        assert componente.cantidad == Decimal("-1.0000")

    def test_el_costo_no_puede_ser_negativo(self) -> None:
        with pytest.raises(ErrorDeAPU, match="costo unitario"):
            Componente(
                categoria=CategoriaExplosion.MATERIAL,
                cantidad=Decimal(1),
                clave_insumo="MAT-1",
                costo_unitario=Decimal("-0.01"),
            )

    def test_las_tres_categorias_de_cuadrilla_son_destajo(self) -> None:
        # §7.3: "destajo = mano de obra o subcontrato".
        for categoria in (
            CategoriaExplosion.MANO_OBRA,
            CategoriaExplosion.DESTAJO,
            CategoriaExplosion.SUBCONTRATO,
        ):
            componente = Componente(
                categoria=categoria, cantidad=Decimal(1), clave_insumo="X"
            )
            assert componente.es_destajo

    def test_material_y_equipo_no_son_destajo(self) -> None:
        for categoria in (CategoriaExplosion.MATERIAL, CategoriaExplosion.EQUIPO):
            componente = Componente(
                categoria=categoria, cantidad=Decimal(1), clave_insumo="X"
            )
            assert not componente.es_destajo


class TestExplosionPlana:
    """Un concepto con solo insumos: el caso base del §7.3."""

    composicion: Mapping[str, Sequence[Componente]] = {
        "EST-001": [
            material("MAT-BLK", "12.5", "18.00", orden=1),
            mano_obra("MOA-ALB", "0.8", "450.00", orden=2),
        ]
    }

    def test_el_cpu_es_la_suma_de_todo(self) -> None:
        precio = calcular_cpu("EST-001", composiciones=self.composicion)
        # 12.5 × 18 = 225 · 0.8 × 450 = 360 → total 585
        assert precio.total == Dinero("585.00")

    def test_el_destajo_es_solo_lo_que_cobra_la_cuadrilla(self) -> None:
        precio = calcular_cpu("EST-001", composiciones=self.composicion)
        assert precio.destajo == Dinero("360.00")
        # Lo que no es destajo lo surte el almacén (§7.3).
        assert precio.materiales == Dinero("225.00")

    def test_las_lineas_traen_su_importe(self) -> None:
        calculada = explotar("EST-001", composiciones=self.composicion)
        assert [(linea.referencia, linea.importe) for linea in calculada.lineas] == [
            ("MAT-BLK", Decimal("225.0000")),
            ("MOA-ALB", Decimal("360.0000")),
        ]

    def test_un_concepto_sin_composicion_cuesta_cero(self) -> None:
        # Un `basico` puede no tener explosión; no es un error.
        calculada = explotar("EST-VACIO", composiciones={})
        assert calculada.lineas == ()
        assert calculada.precio.total == Dinero(0)


class TestExplosionRecursiva:
    """Concepto → auxiliar → insumos (§7.3: "anidar auxiliares y matrices")."""

    composicion: Mapping[str, Sequence[Componente]] = {
        "EST-010": [
            material("MAT-BLK", "10", "20.00", orden=1),
            auxiliar("AUX-MOR", "0.5", orden=2),
            mano_obra("MOA-ALB", "1", "100.00", orden=3),
        ],
        "AUX-MOR": [
            material("MAT-CEM", "4", "50.00", orden=1),
            mano_obra("MOA-AYU", "2", "30.00", orden=2),
        ],
    }

    def test_el_cpu_incluye_el_costo_del_auxiliar(self) -> None:
        # AUX-MOR = 4×50 + 2×30 = 260 por unidad.
        # EST-010 = 10×20 + 0.5×260 + 1×100 = 200 + 130 + 100 = 430.
        assert calcular_cpu("EST-010", composiciones=self.composicion).total == Dinero(
            "430.00"
        )

    def test_el_destajo_arrastra_la_mano_de_obra_del_auxiliar(self) -> None:
        # Destajo = 0.5 × 60 (MO dentro del auxiliar) + 100 (MO directa) = 130.
        # Si la recursión no propagara el destajo del hijo, daría 100.
        precio = calcular_cpu("EST-010", composiciones=self.composicion)
        assert precio.destajo == Dinero("130.00")
        assert precio.materiales == Dinero("300.00")

    def test_las_lineas_van_en_recorrido_padre_antes_que_hijos(self) -> None:
        calculada = explotar("EST-010", composiciones=self.composicion)
        assert [(linea.nivel, linea.referencia) for linea in calculada.lineas] == [
            (1, "MAT-BLK"),
            (1, "AUX-MOR"),
            (2, "MAT-CEM"),
            (2, "MOA-AYU"),
            (1, "MOA-ALB"),
        ]

    def test_la_cantidad_del_nieto_se_acumula_por_el_camino(self) -> None:
        calculada = explotar("EST-010", composiciones=self.composicion)
        cemento = next(linea for linea in calculada.lineas if linea.referencia == "MAT-CEM")
        # 4 por unidad de auxiliar × 0.5 de auxiliar por unidad de concepto.
        assert cemento.cantidad_unitaria == Decimal("4.000000")
        assert cemento.cantidad == Decimal("2.000000")
        assert cemento.ruta == ("EST-010", "AUX-MOR")

    def test_la_linea_del_auxiliar_trae_su_costo_explotado(self) -> None:
        calculada = explotar("EST-010", composiciones=self.composicion)
        aux = next(linea for linea in calculada.lineas if linea.referencia == "AUX-MOR")
        assert aux.tipo_hijo is TipoHijoExplosion.CONCEPTO
        assert aux.costo_unitario == Decimal("260.0000")
        assert aux.importe == Decimal("130.0000")

    def test_un_auxiliar_repetido_en_dos_ramas_no_es_ciclo(self) -> None:
        # El mismo auxiliar colgando de dos padres distintos es un DAG
        # legítimo; solo el camino de vuelta al mismo concepto es ciclo.
        composicion = {
            "EST-A": [auxiliar("AUX-X", "1", orden=1), auxiliar("AUX-Y", "1", orden=2)],
            "AUX-X": [auxiliar("AUX-Z", "1")],
            "AUX-Y": [auxiliar("AUX-Z", "1")],
            "AUX-Z": [material("MAT-1", "1", "10.00")],
        }
        assert calcular_cpu("EST-A", composiciones=composicion).total == Dinero("20.00")


class TestCostoDelCatalogo:
    """Fila sin PU propio: el costo lo pone el catálogo (§10.1, §10.6)."""

    def test_usa_el_costo_vigente_del_insumo(self) -> None:
        composicion = {
            "EST-020": [
                Componente(
                    categoria=CategoriaExplosion.MATERIAL,
                    cantidad=Decimal(3),
                    clave_insumo="MAT-CEM",
                )
            ]
        }
        precio = calcular_cpu(
            "EST-020",
            composiciones=composicion,
            costos_insumo={"MAT-CEM": Decimal("15.50")},
        )
        assert precio.total == Dinero("46.50")

    def test_el_pu_de_la_fila_gana_sobre_el_catalogo(self) -> None:
        composicion = {"EST-021": [material("MAT-CEM", "3", "10.00")]}
        precio = calcular_cpu(
            "EST-021",
            composiciones=composicion,
            costos_insumo={"MAT-CEM": Decimal("15.50")},
        )
        assert precio.total == Dinero("30.00")

    def test_un_insumo_sin_costo_conocido_aporta_cero(self) -> None:
        composicion = {
            "EST-022": [
                Componente(
                    categoria=CategoriaExplosion.MATERIAL,
                    cantidad=Decimal(3),
                    clave_insumo="MAT-DESCONOCIDO",
                )
            ]
        }
        assert calcular_cpu("EST-022", composiciones=composicion).total == Dinero(0)


class TestCiclos:
    def test_el_ciclo_directo_falla_con_error_de_dominio(self) -> None:
        # La base ya lo impide (`ck_explosion_no_ciclo_directo`), pero el
        # dominio no depende de la base para no colgarse.
        composicion = {"EST-A": [auxiliar("EST-A", "1")]}
        with pytest.raises(CicloEnExplosion) as exc:
            calcular_cpu("EST-A", composiciones=composicion)
        assert exc.value.camino == ["EST-A", "EST-A"]

    def test_el_ciclo_indirecto_tambien(self) -> None:
        # A→B→A pasa el CHECK de la base: solo se ve recorriendo el árbol.
        composicion = {
            "EST-A": [auxiliar("AUX-B", "1")],
            "AUX-B": [auxiliar("EST-A", "1")],
        }
        with pytest.raises(CicloEnExplosion) as exc:
            calcular_cpu("EST-A", composiciones=composicion)
        assert exc.value.camino == ["EST-A", "AUX-B", "EST-A"]
        assert "ciclo" in str(exc.value)

    def test_el_ciclo_profundo_no_cuelga(self) -> None:
        composicion = {
            "C1": [auxiliar("C2", "1")],
            "C2": [auxiliar("C3", "1")],
            "C3": [auxiliar("C2", "1")],
        }
        with pytest.raises(CicloEnExplosion) as exc:
            calcular_cpu("C1", composiciones=composicion)
        assert exc.value.camino == ["C1", "C2", "C3", "C2"]

    def test_es_un_error_de_apu(self) -> None:
        # El borde traduce `ErrorDeAPU` a problem+json; el ciclo hereda de él.
        assert issubclass(CicloEnExplosion, ErrorDeAPU)

    def test_una_cadena_absurda_corta_antes_de_agotar_la_pila(self) -> None:
        # Sin ciclo, pero con 60 niveles de anidamiento: el tope es un
        # cinturón de seguridad, no una regla de negocio.
        composicion = {f"C{i}": [auxiliar(f"C{i + 1}", "1")] for i in range(60)}
        with pytest.raises(ProfundidadExcedida):
            calcular_cpu("C0", composiciones=composicion)


class TestVersionado:
    def _version(self, numero: int, *, vigente: bool, variante: str | None = None):
        return VersionCPU(
            version=numero,
            precio=PrecioUnitario(
                total=Dinero(numero * 100), destajo=Dinero(numero * 10)
            ),
            vigente=vigente,
            variante=variante,
        )

    def test_la_primera_version_es_la_uno(self) -> None:
        assert siguiente_version([]) == 1

    def test_la_version_empieza_en_uno(self) -> None:
        with pytest.raises(ErrorDeAPU, match="empieza en 1"):
            VersionCPU(version=0, precio=PrecioUnitario(Dinero(1), Dinero(0)))

    def test_sin_versiones_no_hay_vigente(self) -> None:
        assert vigente_de([]) is None

    def test_solo_una_version_vigente_por_concepto(self) -> None:
        versiones = [self._version(1, vigente=True), self._version(2, vigente=True)]
        with pytest.raises(ErrorDeAPU, match="vigentes"):
            vigente_de(versiones)

    def test_publicar_retira_la_vigente_anterior(self) -> None:
        versiones = [self._version(1, vigente=False), self._version(2, vigente=True)]
        nueva, retiradas = publicar_version(
            versiones, PrecioUnitario(Dinero("500.00"), Dinero("120.00"))
        )
        assert (nueva.version, nueva.vigente) == (3, True)
        assert retiradas == (2,)

    def test_publicar_la_primera_no_retira_nada(self) -> None:
        nueva, retiradas = publicar_version(
            [], PrecioUnitario(Dinero("500.00"), Dinero("120.00"))
        )
        assert (nueva.version, retiradas) == (1, ())

    def test_la_vigencia_es_por_variante(self) -> None:
        # `uq_cpu_vigente` permite un vigente por concepto **y variante**
        # (§2.2, recetas alternas).
        versiones = [
            self._version(1, vigente=True),
            self._version(1, vigente=True, variante="mortero"),
        ]
        assert vigente_de(versiones).version == 1
        assert vigente_de(versiones, variante="mortero").variante == "mortero"

    def test_el_consecutivo_es_independiente_por_variante(self) -> None:
        versiones = [
            self._version(1, vigente=False),
            self._version(2, vigente=True),
            self._version(1, vigente=True, variante="mortero"),
        ]
        assert siguiente_version(versiones) == 3
        assert siguiente_version(versiones, variante="mortero") == 2

    def test_publicar_una_variante_no_toca_la_receta_base(self) -> None:
        versiones = [self._version(1, vigente=True)]
        nueva, retiradas = publicar_version(
            versiones,
            PrecioUnitario(Dinero("100.00"), Dinero("10.00")),
            variante="mortero",
        )
        assert (nueva.version, nueva.variante, retiradas) == (1, "mortero", ())


class TestRedondeo:
    def test_un_concepto_100_por_ciento_subcontratado_no_rompe_el_invariante(
        self,
    ) -> None:
        # Todo el costo es subcontrato: destajo == total. Redondear cada
        # cifra por separado podría empujar el destajo por encima del total y
        # `PrecioUnitario` lo rechazaría (§7.3).
        composicion = {
            "SUB-001": [
                Componente(
                    categoria=CategoriaExplosion.SUBCONTRATO,
                    cantidad=Decimal("3.333333"),
                    clave_insumo="SUB-MO",
                    costo_unitario=Decimal("101.0101"),
                )
            ]
        }
        precio = calcular_cpu("SUB-001", composiciones=composicion)
        assert precio.destajo == precio.total
        assert precio.materiales == Dinero(0)
