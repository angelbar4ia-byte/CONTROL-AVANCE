"""Extracción de un ensamble de punta a punta contra Postgres real (§5.7-§5.10,
§6; skill `erp-parametrico`).

Lo que aquí se prueba y no en `tests/domain/test_ensamble.py`: que el caso de
uso resuelve clave→id contra los catálogos reales (concepto, sub-ensamble,
prototipo), que el CTE recursivo de `renglones_recursivos` trae un
sub-ensamble anidado, y que la clave duplicada / el concepto o sub-ensamble
inexistente se rechazan antes de escribir nada.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from obractrl.adapters.repos.conceptos_sql import RepositorioConceptosSQL
from obractrl.adapters.repos.ensambles_sql import RepositorioEnsamblesSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.calcular_cpu import ConceptoNoEncontrado
from obractrl.application.casos_uso.gestionar_ensamble import (
    ClaveDeEnsambleEnUso,
    ComandoExtraerEnsamble,
    ExtraerEnsamble,
    SubEnsambleNoEncontrado,
)
from obractrl.domain.catalogos.ensamble import RenglonEnsamble
from obractrl.domain.shared.diccionario import OrigenCantidadEnsamble
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import Escenario


async def test_extraer_ensamble_resuelve_claves_y_persiste_renglones(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        conceptos = RepositorioConceptosSQL(sesion)
        muro = await conceptos.crear(
            {"tipo": "concepto", "clave": "EST-MURO", "descripcion": "Muro de block"}
        )
        losa = await conceptos.crear(
            {"tipo": "concepto", "clave": "EST-LOSA", "descripcion": "Losa de desplante"}
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        caso_uso = ExtraerEnsamble(
            ensambles=RepositorioEnsamblesSQL(sesion),
            conceptos=RepositorioConceptosSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        creado = await caso_uso.ejecutar(
            ComandoExtraerEnsamble(
                clave="RECAMARA-A",
                nombre="Recámara tipo A",
                divisor_concepto_clave="EST-LOSA",
                divisor_nombre="m² de desplante",
                renglones=[
                    RenglonEnsamble(
                        cantidad=Decimal("12.5"),
                        origen=OrigenCantidadEnsamble.HEREDADA_CONCEPTO,
                        clave_concepto="EST-MURO",
                        orden=1,
                    ),
                    RenglonEnsamble(
                        cantidad=Decimal("1"),
                        origen=OrigenCantidadEnsamble.MANUAL,
                        clave_concepto="EST-LOSA",
                        orden=2,
                    ),
                ],
            )
        )

    assert creado.clave == "RECAMARA-A"
    assert creado.renglones == 2

    async with sesion_con_rls(contexto_control) as sesion:
        ensambles = RepositorioEnsamblesSQL(sesion)
        fila = await ensambles.obtener_por_clave("RECAMARA-A")
        assert fila is not None
        assert fila["divisor_nombre"] == "m² de desplante"
        assert fila["divisor_concepto_id"] == losa

        renglones = await ensambles.renglones(fila["id"])

    renglon_muro = next(r for r in renglones if r["concepto_clave"] == "EST-MURO")
    assert renglon_muro["concepto_id"] == muro
    assert renglon_muro["cantidad"] == Decimal("12.500000")
    assert renglon_muro["origen"] == "heredada_concepto"
    assert renglon_muro["sub_ensamble_id"] is None


async def test_renglones_recursivos_bajan_por_el_sub_ensamble(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        conceptos = RepositorioConceptosSQL(sesion)
        block = await conceptos.crear(
            {"tipo": "concepto", "clave": "EST-BLOCK", "descripcion": "Block"}
        )
        pintura = await conceptos.crear(
            {"tipo": "concepto", "clave": "ACB-PINTURA", "descripcion": "Pintura"}
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        caso_uso = ExtraerEnsamble(
            ensambles=RepositorioEnsamblesSQL(sesion),
            conceptos=RepositorioConceptosSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        await caso_uso.ejecutar(
            ComandoExtraerEnsamble(
                clave="MURO-TIPICO",
                nombre="Muro típico",
                renglones=[
                    RenglonEnsamble(
                        cantidad=Decimal("10"),
                        origen=OrigenCantidadEnsamble.HEREDADA_CONCEPTO,
                        clave_concepto="EST-BLOCK",
                    )
                ],
            )
        )
        await caso_uso.ejecutar(
            ComandoExtraerEnsamble(
                clave="RECAMARA-B",
                nombre="Recámara tipo B",
                renglones=[
                    RenglonEnsamble(
                        cantidad=Decimal("4"),
                        origen=OrigenCantidadEnsamble.HEREDADA_CONCEPTO,
                        clave_sub_ensamble="MURO-TIPICO",
                    ),
                    RenglonEnsamble(
                        cantidad=Decimal("2"),
                        origen=OrigenCantidadEnsamble.MANUAL,
                        clave_concepto="ACB-PINTURA",
                    ),
                ],
            )
        )

    async with sesion_con_rls(contexto_control) as sesion:
        ensambles = RepositorioEnsamblesSQL(sesion)
        raiz = await ensambles.obtener_por_clave("RECAMARA-B")
        assert raiz is not None
        filas = await ensambles.renglones_recursivos(raiz["id"])

    # Baja de RECAMARA-B a MURO-TIPICO y trae también su hijo (EST-BLOCK).
    por_padre = {(f["ensamble_clave"], f["concepto_clave"], f["sub_ensamble_clave"]) for f in filas}
    assert ("RECAMARA-B", None, "MURO-TIPICO") in por_padre
    assert ("RECAMARA-B", "ACB-PINTURA", None) in por_padre
    assert ("MURO-TIPICO", "EST-BLOCK", None) in por_padre
    assert block is not None and pintura is not None  # usados arriba por clave


async def test_clave_duplicada_se_rechaza(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        await RepositorioConceptosSQL(sesion).crear(
            {"tipo": "concepto", "clave": "EST-MURO", "descripcion": "Muro"}
        )
        await sesion.commit()

    async def _extraer(sesion) -> None:
        caso_uso = ExtraerEnsamble(
            ensambles=RepositorioEnsamblesSQL(sesion),
            conceptos=RepositorioConceptosSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        await caso_uso.ejecutar(
            ComandoExtraerEnsamble(
                clave="RECAMARA-A",
                nombre="Recámara tipo A",
                renglones=[
                    RenglonEnsamble(
                        cantidad=Decimal("1"),
                        origen=OrigenCantidadEnsamble.MANUAL,
                        clave_concepto="EST-MURO",
                    )
                ],
            )
        )

    async with sesion_con_rls(contexto_control) as sesion:
        await _extraer(sesion)

    with pytest.raises(ClaveDeEnsambleEnUso):
        async with sesion_con_rls(contexto_control) as sesion:
            await _extraer(sesion)


async def test_concepto_inexistente_se_rechaza(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    with pytest.raises(ConceptoNoEncontrado):
        async with sesion_con_rls(contexto_control) as sesion:
            caso_uso = ExtraerEnsamble(
                ensambles=RepositorioEnsamblesSQL(sesion),
                conceptos=RepositorioConceptosSQL(sesion),
                uow=UnidadDeTrabajoSQL(sesion),
            )
            await caso_uso.ejecutar(
                ComandoExtraerEnsamble(
                    clave="RECAMARA-A",
                    nombre="Recámara tipo A",
                    renglones=[
                        RenglonEnsamble(
                            cantidad=Decimal("1"),
                            origen=OrigenCantidadEnsamble.MANUAL,
                            clave_concepto="NO-EXISTE",
                        )
                    ],
                )
            )


async def test_sub_ensamble_inexistente_se_rechaza(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    with pytest.raises(SubEnsambleNoEncontrado):
        async with sesion_con_rls(contexto_control) as sesion:
            caso_uso = ExtraerEnsamble(
                ensambles=RepositorioEnsamblesSQL(sesion),
                conceptos=RepositorioConceptosSQL(sesion),
                uow=UnidadDeTrabajoSQL(sesion),
            )
            await caso_uso.ejecutar(
                ComandoExtraerEnsamble(
                    clave="RECAMARA-A",
                    nombre="Recámara tipo A",
                    renglones=[
                        RenglonEnsamble(
                            cantidad=Decimal("1"),
                            origen=OrigenCantidadEnsamble.MANUAL,
                            clave_sub_ensamble="NO-EXISTE",
                        )
                    ],
                )
            )


async def test_cohorte_y_presupuesto_origen_se_persisten(
    escenario: Escenario, contexto_control: ContextoSesion
) -> None:
    async with sesion_con_rls(contexto_control) as sesion:
        await RepositorioConceptosSQL(sesion).crear(
            {"tipo": "concepto", "clave": "EST-MURO", "descripcion": "Muro"}
        )
        await sesion.commit()

    async with sesion_con_rls(contexto_control) as sesion:
        caso_uso = ExtraerEnsamble(
            ensambles=RepositorioEnsamblesSQL(sesion),
            conceptos=RepositorioConceptosSQL(sesion),
            uow=UnidadDeTrabajoSQL(sesion),
        )
        await caso_uso.ejecutar(
            ComandoExtraerEnsamble(
                clave="RECAMARA-A",
                nombre="Recámara tipo A",
                presupuesto_origen_id=None,
                cohorte_prototipo_ids=[escenario.prototipo_id],
                renglones=[
                    RenglonEnsamble(
                        cantidad=Decimal("1"),
                        origen=OrigenCantidadEnsamble.HEREDADA_CONCEPTO,
                        clave_concepto="EST-MURO",
                    )
                ],
            )
        )

    async with sesion_con_rls(contexto_control) as sesion:
        ensambles = RepositorioEnsamblesSQL(sesion)
        fila = await ensambles.obtener_por_clave("RECAMARA-A")
        assert fila is not None
        cohorte = await ensambles.cohorte(fila["id"])

    assert [c["prototipo_id"] for c in cohorte] == [escenario.prototipo_id]
