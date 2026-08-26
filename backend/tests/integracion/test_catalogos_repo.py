"""Repositorios de catálogo contra Postgres real (§7.3, §12.4).

Lo que se prueba aquí y no en los tests de dominio: que el alcance de los
catálogos es el del **bloque A** de `rls_policies` —lectura para toda la
organización, escritura solo para `app.es_config()`— y que la clave única por
catálogo (§3.3) es una frontera real de la base.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from obractrl.adapters.repos.conceptos_sql import RepositorioConceptosSQL
from obractrl.adapters.repos.contratistas_sql import RepositorioContratistasSQL
from obractrl.adapters.repos.cuadrillas_sql import RepositorioCuadrillasSQL
from obractrl.adapters.repos.familias_sql import RepositorioFamiliasSQL
from obractrl.adapters.repos.insumos_sql import RepositorioInsumosSQL
from obractrl.adapters.repos.unidades_sql import RepositorioUnidadesSQL
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import Escenario


async def test_unidad_alta_lectura_y_sinonimos(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioUnidadesSQL(sesion)
        unidad_id = await repo.crear(
            {
                "clave": "PZA",
                "nombre": "Pieza",
                "sinonimos": ["PZ", "PIEZA"],
                "factor": Decimal(1),
            }
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        fila = await RepositorioUnidadesSQL(sesion).obtener(unidad_id)

    assert fila is not None
    assert fila["clave"] == "PZA"
    # Los sinónimos son lo que permite cruzar `pz` con `PZA` al homologar
    # (§10.3); viajan como `text[]`, no como JSON.
    assert list(fila["sinonimos"]) == ["PZ", "PIEZA"]


async def test_el_residente_lee_catalogos_pero_no_los_escribe(
    escenario: Escenario,
    contexto_control: ContextoSesion,
    contexto_residente: ContextoSesion,
) -> None:
    """Bloque A de `rls_policies`: lectura de organización, escritura de
    Configuración (§5.1). El Residente consulta el catálogo desde su pantalla
    de avance, pero no lo edita."""
    async with sesion_con_rls(contexto_control) as sesion:
        await RepositorioUnidadesSQL(sesion).crear({"clave": "M2", "nombre": "Metro²"})
        await sesion.commit()

    async with sesion_con_rls(contexto_residente) as sesion:
        unidades = await RepositorioUnidadesSQL(sesion).listar()
        assert [u["clave"] for u in unidades] == ["M2"]

    async with sesion_con_rls(contexto_residente) as sesion:
        with pytest.raises(DBAPIError):
            await RepositorioUnidadesSQL(sesion).crear(
                {"clave": "ML", "nombre": "Metro lineal"}
            )


async def test_otra_organizacion_no_ve_el_catalogo(
    escenario: Escenario,
    contexto_control: ContextoSesion,
    contexto_ajeno: ContextoSesion,
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        unidad_id = await RepositorioUnidadesSQL(sesion).crear(
            {"clave": "TON", "nombre": "Tonelada"}
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_ajeno) as sesion:
        repo = RepositorioUnidadesSQL(sesion)
        assert await repo.obtener(unidad_id) is None
        assert await repo.listar() == []


async def test_la_clave_es_unica_por_catalogo(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """§3.3: en todos los catálogos la clave es única. `uq_unidad_clave`."""
    async with sesion_con_rls(contexto_control) as sesion:
        await RepositorioUnidadesSQL(sesion).crear({"clave": "KG", "nombre": "Kilo"})
        with pytest.raises(IntegrityError):
            await RepositorioUnidadesSQL(sesion).crear(
                {"clave": "KG", "nombre": "Kilogramo"}
            )


async def test_familia_crear_o_existente_es_idempotente_por_clave(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """`crear_o_existente` es lo que usa el auto-alta de una carga
    (`_resolver_o_dar_de_alta`, §3.3, §8.7): dos cargas que auto-crean la
    misma familia nueva casi al mismo tiempo no deben tronar con
    `UniqueViolationError` — la segunda solo obtiene el id de la que la
    primera ya dio de alta, sin pisarla. Reproduce el `IntegrityError` real
    de producción sobre `uq_familia_clave` con `OBRA`."""
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioFamiliasSQL(sesion)
        primero = await repo.crear_o_existente({"clave": "OBRA", "nombre": "OBRA"})
        segundo = await repo.crear_o_existente({"clave": "OBRA", "nombre": "OBRA"})
        await sesion.commit()

    assert primero == segundo

    async with sesion_con_rls(contexto_control) as sesion:
        familias = await RepositorioFamiliasSQL(sesion).listar(solo_activos=False)
    assert [f["clave"] for f in familias] == ["OBRA"]


async def test_unidad_y_cuadrilla_crear_o_existente_tambien_son_idempotentes(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """Mismo mecanismo que familia, para los otros dos catálogos que
    `_resolver_o_dar_de_alta` puede auto-crear."""
    async with sesion_con_rls(contexto_control) as sesion:
        unidades = RepositorioUnidadesSQL(sesion)
        u1 = await unidades.crear_o_existente({"clave": "PZA", "nombre": "PZA"})
        u2 = await unidades.crear_o_existente({"clave": "PZA", "nombre": "Pieza"})
    assert u1 == u2

    async with sesion_con_rls(contexto_control) as sesion:
        cuadrillas = RepositorioCuadrillasSQL(sesion)
        c1 = await cuadrillas.crear_o_existente({"clave": "CUA-01", "nombre": "CUA-01"})
        c2 = await cuadrillas.crear_o_existente({"clave": "CUA-01", "nombre": "CUA-01"})
    assert c1 == c2


async def test_insumo_crear_o_existente_es_idempotente(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """El insumo que se auto-crea desde CPU/Presupuesto/Cuadrillas cuando un
    componente no cruza (§7.3, §8.7): la clave manda, dos altas de la misma
    clave nueva no deben chocar."""
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioInsumosSQL(sesion)
        i1 = await repo.crear_o_existente(
            {"tipo": "material", "clave": "MAT-99", "descripcion": "Material 99"}
        )
        i2 = await repo.crear_o_existente(
            {"tipo": "material", "clave": "MAT-99", "descripcion": "Otra descripción"}
        )
        await sesion.commit()
    assert i1 == i2

    async with sesion_con_rls(contexto_control) as sesion:
        fila = await RepositorioInsumosSQL(sesion).obtener(i1)
    assert fila is not None and fila["descripcion"] == "Material 99"


async def test_familia_con_padre_y_iva(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioFamiliasSQL(sesion)
        raiz = await repo.crear({"clave": "OBR", "nombre": "Obra negra"})
        # Pétreos nace exenta (§3.5).
        hija = await repo.crear(
            {
                "clave": "PET",
                "nombre": "Pétreos",
                "parent_id": raiz,
                "iva_aplica": False,
            }
        )
        await repo.crear(
            {"clave": "ALB", "nombre": "Albañilería", "aplica_a": "concepto"}
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioFamiliasSQL(sesion)
        fila = await repo.obtener(hija)
        assert fila is not None
        assert fila["parent_id"] == raiz
        assert fila["iva_aplica"] is False
        assert fila["aplica_a"] == "material"

        de_conceptos = await repo.listar(aplica_a="concepto")
        assert [f["clave"] for f in de_conceptos] == ["ALB"]


async def test_material_es_un_insumo_filtrado_por_tipo(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """§7.3: `Material` = `Insumo` con `tipo='material'`. `GET /materiales` es
    este mismo repositorio con el filtro puesto, no otra tabla."""
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioInsumosSQL(sesion)
        await repo.crear(
            {
                "tipo": "material",
                "clave": "MAT-CEM",
                "descripcion": "Cemento gris",
                "costo_base": Decimal("180.50"),
                "iva_aplica": None,
            }
        )
        await repo.crear(
            {"tipo": "mano_obra", "clave": "MOA-ALB", "descripcion": "Albañil"}
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioInsumosSQL(sesion)
        assert [i["clave"] for i in await repo.listar()] == ["MAT-CEM", "MOA-ALB"]
        materiales = await repo.listar(tipo="material")
        assert [i["clave"] for i in materiales] == ["MAT-CEM"]
        # Nulo en `iva_aplica` significa "hereda de la familia" (§3.5); el
        # repositorio no lo convierte en `false`.
        assert materiales[0]["iva_aplica"] is None
        assert materiales[0]["costo_base"] == Decimal("180.5000")


async def test_contratista_con_frentes(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        # El catálogo de frentes es semilla de organización (§8.3) y el
        # escenario no lo siembra: Control de obra lo puede escribir, igual
        # que el resto del bloque A.
        frentes = [
            (
                await sesion.execute(
                    text(
                        """
                        insert into frente (org_id, clave, nombre, orden)
                        values (cast(current_setting('app.org_id') as uuid),
                                :clave, :nombre, :orden)
                        returning id
                        """
                    ),
                    {"clave": clave, "nombre": nombre, "orden": orden},
                )
            ).scalar_one()
            for orden, (clave, nombre) in enumerate(
                [("ALB", "Albañilería"), ("HID", "Hidráulica")], start=1
            )
        ]

        contratista_id = await RepositorioContratistasSQL(sesion).crear(
            {
                "clave": "CTR-01",
                "razon_social": "Constructora del Bajío",
                "rfc": "CDB010203AB1",
                "frentes": [str(f) for f in frentes],
            }
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        fila = await RepositorioContratistasSQL(sesion).obtener(contratista_id)
        puente = (
            await sesion.execute(
                text(
                    "select count(*) from contratista_frente where contratista_id = :id"
                ),
                {"id": str(contratista_id)},
            )
        ).scalar_one()

    assert fila is not None
    assert fila["razon_social"] == "Constructora del Bajío"
    assert puente == 2


async def test_concepto_alta_y_filtro_por_tipo(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioConceptosSQL(sesion)
        await repo.crear(
            {"tipo": "concepto", "clave": "EST-001", "descripcion": "Muro de block"}
        )
        await repo.crear(
            {"tipo": "auxiliar", "clave": "AUX-MOR", "descripcion": "Mortero"}
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioConceptosSQL(sesion)
        assert [c["clave"] for c in await repo.listar()] == ["AUX-MOR", "EST-001"]
        assert [c["clave"] for c in await repo.listar(tipo="auxiliar")] == ["AUX-MOR"]


async def test_conceptos_sin_explosion_devuelven_composicion_vacia(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """Un `basico` sin desglose no es un error: la explosión sale vacía."""
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioConceptosSQL(sesion)
        concepto_id = await repo.crear(
            {"tipo": "basico", "clave": "BAS-1", "descripcion": "Sin desglose"}
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        assert (
            await RepositorioConceptosSQL(sesion).composicion_recursiva(concepto_id)
            == []
        )


async def test_versiones_de_cpu_y_vigencia_unica(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """`publicar_version_cpu` retira antes de insertar: `uq_cpu_vigente` es un
    índice único parcial y no es diferible (§7.3)."""
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioConceptosSQL(sesion)
        concepto_id = await repo.crear(
            {"tipo": "concepto", "clave": "EST-CPU", "descripcion": "Con CPU"}
        )
        await repo.publicar_version_cpu(
            concepto_id,
            version=1,
            precio_unitario=Decimal("100.00"),
            precio_destajo=Decimal("40.00"),
            variante=None,
            retirar=[],
        )
        await repo.publicar_version_cpu(
            concepto_id,
            version=2,
            precio_unitario=Decimal("120.00"),
            precio_destajo=Decimal("50.00"),
            variante=None,
            retirar=[1],
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        versiones = await RepositorioConceptosSQL(sesion).versiones_cpu(concepto_id)

    assert [(v["version"], v["vigente"]) for v in versiones] == [(1, False), (2, True)]
    # La v1 no se borra: el histórico es lo que permite comparar y restaurar
    # (§10.8).
    assert versiones[0]["precio_unitario"] == Decimal("100.0000")


async def test_una_variante_tiene_su_propia_vigencia(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    """`uq_cpu_vigente` es por concepto **y variante** (§2.2, recetas alternas)."""
    async with sesion_con_rls(contexto_control) as sesion:
        repo = RepositorioConceptosSQL(sesion)
        concepto_id = await repo.crear(
            {"tipo": "concepto", "clave": "EST-VAR", "descripcion": "Con variantes"}
        )
        await repo.publicar_version_cpu(
            concepto_id,
            version=1,
            precio_unitario=Decimal("100.00"),
            precio_destajo=Decimal("40.00"),
            variante=None,
            retirar=[],
        )
        await repo.publicar_version_cpu(
            concepto_id,
            version=1,
            precio_unitario=Decimal("90.00"),
            precio_destajo=Decimal("35.00"),
            variante="mortero",
            retirar=[],
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        versiones = await RepositorioConceptosSQL(sesion).versiones_cpu(concepto_id)

    assert sorted(
        ((v["variante"], v["vigente"]) for v in versiones), key=lambda p: p[0] or ""
    ) == [(None, True), ("mortero", True)]


async def test_el_id_generado_no_se_cruza_entre_organizaciones(
    escenario: Escenario, contexto_ajeno: ContextoSesion
) -> None:
    """Escribir con un contexto de otra org no debe colarse por el `org_id`
    del INSERT: `current_setting('app.org_id')` apunta a una organización que
    no existe, así que la llave foránea lo rechaza."""
    async with sesion_con_rls(contexto_ajeno) as sesion:
        with pytest.raises(IntegrityError):
            await RepositorioUnidadesSQL(sesion).crear(
                {"clave": str(uuid.uuid4())[:8], "nombre": "Fantasma"}
            )
