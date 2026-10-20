"""El cuantificador de punta a punta, contra Postgres real con PostGIS
(cerebro MODELO.md §1b).

Tres pruebas:

- Camino `actividad`: un trazo real (rectángulo 4×3 -> área 12) enlazado a
  una actividad real con `cant_base` conocido. Confirma que `ST_Area`
  calcula el área correcta, que se genera una `Desviacion` cuando la
  medida difiere de `cant_base`, y que `cant_base` JAMÁS se modifica.
- Camino `prototipo_nodo` ("diseño_nuevo"): mismo fixture sintético que
  `test_ingenieria_lote_endtoend.py::TestCaminoDisenoNuevo` (nivel ->
  etapa -> concepto), enlazado directo contra el `prototipo_nodo` del
  concepto. Confirma que ahí SÍ se escribe `cantidad`+`modo_cantidad=
  'medida'` directo.
- `ReemplazarEnlace`: el enlace viejo pasa a `vigente=false`, el nuevo
  queda vigente, y la suma de vigentes cambia en consecuencia.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from obractrl.adapters.repos.actividades_sql import RepositorioActividadesSQL
from obractrl.adapters.repos.cuantificacion_sql import (
    RepositorioEnlacesCuantificacionSQL,
    RepositorioPlanosSQL,
    RepositorioTrazosSQL,
)
from obractrl.adapters.repos.desviaciones_sql import RepositorioDesviacionesSQL
from obractrl.adapters.repos.prototipo_nodo_sql import RepositorioPrototipoNodoSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.application.casos_uso.cuantificar import (
    ComandoReemplazarEnlace,
    ComandoRegistrarTrazo,
    IntencionEnlace,
    NuevoEnlace,
    ReemplazarEnlace,
    RegistrarTrazoConEnlaces,
)
from obractrl.domain.shared.diccionario import (
    FuenteTrazo,
    MedidaCuantificacion,
    Rol,
    TipoCarga,
)
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls
from tests.integracion.conftest import DATABASE_URL_ADMIN, Escenario
from tests.integracion.test_cargas_endtoend import (
    _archivo_presupuesto,
    _archivo_prototipos,
    _cargar,
    _prototipos,
)

_RECTANGULO_4X3 = "POLYGON((0 0, 4 0, 4 3, 0 3, 0 0))"
"""Área 12 — el caso que el encargo pide verificar explícito."""


def _caso_uso_registrar_trazo(sesion) -> RegistrarTrazoConEnlaces:
    return RegistrarTrazoConEnlaces(
        trazos=RepositorioTrazosSQL(sesion),
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        desviaciones=RepositorioDesviacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def _caso_uso_reemplazar_enlace(sesion) -> ReemplazarEnlace:
    return ReemplazarEnlace(
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        desviaciones=RepositorioDesviacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


async def _crear_plano(contexto: ContextoSesion, *, obra_id: uuid.UUID) -> uuid.UUID:
    async with sesion_con_rls(contexto) as sesion:
        plano_id = await RepositorioPlanosSQL(sesion).crear(
            obra_id=obra_id,
            nombre="Planta baja",
            archivo_url="org/planos/planta-baja.pdf",
            version=1,
            capas=None,
            subido_por=contexto.usuario_id,
        )
        await sesion.commit()
    return plano_id


async def _preparar_actividad_con_concepto(
    *, org_id: uuid.UUID, actividad_id: uuid.UUID, precio_unitario: Decimal
) -> uuid.UUID:
    """Le da a la actividad del fixture un `concepto_id` y un
    `precio_unitario` reales — sin esto no se puede construir una
    `Desviacion` válida (exige `concepto_id`, §3.3). Engine admin, mismo
    criterio que `test_ingenieria_lote_endtoend._asignar_prototipo_a_obra`:
    aquí se prepara el fixture, no se prueba aislamiento."""
    engine = create_async_engine(DATABASE_URL_ADMIN)
    concepto_id = uuid.uuid4()
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "insert into concepto (id, org_id, clave, descripcion) "
                    "values (:id, :org, 'EST-CUANT-1', 'Concepto de prueba')"
                ),
                {"id": str(concepto_id), "org": str(org_id)},
            )
            await conn.execute(
                text(
                    "update actividad set concepto_id = :concepto, "
                    "precio_unitario = :precio where id = :id"
                ),
                {
                    "concepto": str(concepto_id),
                    "precio": str(precio_unitario),
                    "id": str(actividad_id),
                },
            )
    finally:
        await engine.dispose()
    return concepto_id


async def _leer_actividad(actividad_id: uuid.UUID) -> dict:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with engine.begin() as conn:
            fila = (
                await conn.execute(
                    text("select cant_base from actividad where id = :id"),
                    {"id": str(actividad_id)},
                )
            ).mappings().first()
    finally:
        await engine.dispose()
    assert fila is not None
    return dict(fila)


async def _desviaciones_de_obra(obra_id: uuid.UUID) -> list[dict]:
    engine = create_async_engine(DATABASE_URL_ADMIN)
    try:
        async with engine.begin() as conn:
            filas = (
                await conn.execute(
                    text("select * from desviacion where obra_id = :obra"),
                    {"obra": str(obra_id)},
                )
            ).mappings().all()
    finally:
        await engine.dispose()
    return [dict(f) for f in filas]


class TestCaminoActividad:
    async def test_area_real_genera_desviacion_sin_tocar_cant_base(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        # El fixture `escenario` ya trae una actividad con cant_base=100
        # (tests/integracion/conftest.py) — le damos concepto y precio
        # para poder construir la Desviacion.
        await _preparar_actividad_con_concepto(
            org_id=escenario.org_id,
            actividad_id=escenario.actividad_id,
            precio_unitario=Decimal("1000"),
        )
        plano_id = await _crear_plano(contexto_control, obra_id=escenario.obra_id)

        async with sesion_con_rls(contexto_control) as sesion:
            resultado = await _caso_uso_registrar_trazo(sesion).ejecutar(
                ComandoRegistrarTrazo(
                    plano_id=plano_id,
                    version_plano=1,
                    capa="ARQ-MUROS",
                    fuente=str(FuenteTrazo.PDF),
                    geometria_wkt=_RECTANGULO_4X3,
                    autor_id=contexto_control.usuario_id,
                    rol=Rol.CONTROL_OBRA,
                    enlaces=(
                        IntencionEnlace(
                            medida=MedidaCuantificacion.AREA,
                            factor=Decimal("1"),
                            actividad_id=escenario.actividad_id,
                        ),
                    ),
                ),
                detectada_en=datetime.now(UTC),
            )

        assert len(resultado.enlace_ids) == 1
        assert len(resultado.recalculos) == 1
        recalculo = resultado.recalculos[0]

        # ST_Area del rectángulo 4x3 = 12 (el caso que el encargo pide).
        assert recalculo.cantidad_total == Decimal("12")

        # cant_base=100 vs medido=12, precio=1000: se desvía mucho más
        # allá del umbral -> SÍ genera Desviacion.
        assert recalculo.desviacion_id is not None
        assert recalculo.prototipo_nodo_actualizado is None

        desviaciones = await _desviaciones_de_obra(escenario.obra_id)
        assert len(desviaciones) == 1
        d = desviaciones[0]
        assert d["tipo"] == "consumo"
        assert d["causa"] is None  # nunca se decide aquí (MODELO.md §5g)
        assert Decimal(str(d["cantidad_plan"])) == Decimal("100")
        assert Decimal(str(d["cantidad_real"])) == Decimal("12")

        # cant_base JAMÁS se toca (adapters/repos/actividades_sql.py ~373).
        actividad = await _leer_actividad(escenario.actividad_id)
        assert Decimal(str(actividad["cant_base"])) == Decimal("100")

    async def test_medida_igual_a_cant_base_no_genera_desviacion(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        await _preparar_actividad_con_concepto(
            org_id=escenario.org_id,
            actividad_id=escenario.actividad_id,
            precio_unitario=Decimal("1000"),
        )
        plano_id = await _crear_plano(contexto_control, obra_id=escenario.obra_id)

        # Un cuadrado de 10x10 = área 100, igual a cant_base del fixture:
        # no hay nada que reportar (§3.6, "dentro_de_rango").
        async with sesion_con_rls(contexto_control) as sesion:
            resultado = await _caso_uso_registrar_trazo(sesion).ejecutar(
                ComandoRegistrarTrazo(
                    plano_id=plano_id,
                    version_plano=1,
                    capa=None,
                    fuente=str(FuenteTrazo.PDF),
                    geometria_wkt="POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))",
                    autor_id=contexto_control.usuario_id,
                    rol=Rol.CONTROL_OBRA,
                    enlaces=(
                        IntencionEnlace(
                            medida=MedidaCuantificacion.AREA,
                            factor=Decimal("1"),
                            actividad_id=escenario.actividad_id,
                        ),
                    ),
                ),
                detectada_en=datetime.now(UTC),
            )

        assert resultado.recalculos[0].cantidad_total == Decimal("100")
        assert resultado.recalculos[0].desviacion_id is None
        assert await _desviaciones_de_obra(escenario.obra_id) == []


class TestCaminoPrototipoNodoDisenoNuevo:
    """Mismo fixture sintético que
    `test_ingenieria_lote_endtoend.TestCaminoDisenoNuevo` (nivel -> etapa
    -> concepto): aquí el enlace escribe `prototipo_nodo.cantidad` directo,
    nunca compara contra nada."""

    async def _prototipo_sintetico(self, contexto_control: ContextoSesion) -> uuid.UUID:
        resultado = await _cargar(
            contexto_control,
            TipoCarga.PROTOTIPOS,
            _archivo_prototipos(
                # "PROY" es la clave de proyecto que ya siembra el fixture
                # `escenario` (tests/integracion/conftest.py).
                [["PROY", "CAS-CUANT", "Prototipo cuantificador", "", "", ""]]
            ),
        )
        assert resultado.resumen.errores == 0

        resultado_presupuesto = await _cargar(
            contexto_control,
            TipoCarga.PRESUPUESTO,
            _archivo_presupuesto(
                [
                    [1, None, "CAS-CUANT", "Prototipo", None, None, None, None, "PROTOTIPO"],
                    [1, "CAS-CUANT", "NIV-1", "Nivel", None, None, None, None, "NIVEL DE CONSTRUCCION"],
                    [1, "NIV-1", "ECO-1", "Etapa", None, None, None, None, "ETAPA DE CONSTRUCCION"],
                    [1, "ECO-1", "EST-1", "Concepto", "M2", 1, 0, 0, "CONCEPTO"],
                ]
            ),
        )
        assert resultado_presupuesto.resumen.errores == 0

        prototipos = await _prototipos(contexto_control)
        return uuid.UUID(str(prototipos["CAS-CUANT"]["id"]))

    async def test_escribe_cantidad_y_modo_medida_directo(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        prototipo_id = await self._prototipo_sintetico(contexto_control)

        async with sesion_con_rls(contexto_control) as sesion:
            nodos = await RepositorioPrototipoNodoSQL(sesion).por_prototipo(prototipo_id)
        nodo_concepto = next(n for n in nodos if n["clave"] == "EST-1")
        assert nodo_concepto["modo_cantidad"] == "capturada"
        assert nodo_concepto["cantidad"] == Decimal("1")

        plano_id = await _crear_plano(contexto_control, obra_id=escenario.obra_id)

        # Rectángulo 4x3 = área 12 otra vez, esta vez contra el
        # prototipo_nodo del concepto EST-1.
        async with sesion_con_rls(contexto_control) as sesion:
            resultado = await _caso_uso_registrar_trazo(sesion).ejecutar(
                ComandoRegistrarTrazo(
                    plano_id=plano_id,
                    version_plano=1,
                    capa=None,
                    fuente=str(FuenteTrazo.DWG),
                    geometria_wkt=_RECTANGULO_4X3,
                    autor_id=contexto_control.usuario_id,
                    rol=Rol.CONTROL_OBRA,
                    enlaces=(
                        IntencionEnlace(
                            medida=MedidaCuantificacion.AREA,
                            factor=Decimal("1"),
                            prototipo_nodo_id=uuid.UUID(str(nodo_concepto["id"])),
                        ),
                    ),
                ),
                detectada_en=datetime.now(UTC),
            )

        recalculo = resultado.recalculos[0]
        assert recalculo.cantidad_total == Decimal("12")
        assert recalculo.desviacion_id is None  # nunca se audita contra sí mismo
        assert recalculo.prototipo_nodo_actualizado == uuid.UUID(str(nodo_concepto["id"]))

        async with sesion_con_rls(contexto_control) as sesion:
            nodos_despues = await RepositorioPrototipoNodoSQL(sesion).por_prototipo(
                prototipo_id
            )
        nodo_despues = next(n for n in nodos_despues if n["clave"] == "EST-1")
        assert nodo_despues["cantidad"] == Decimal("12")
        assert nodo_despues["modo_cantidad"] == "medida"

        # Nunca generó Desviacion: el prototipo "diseño_nuevo" no se
        # audita contra sí mismo.
        assert await _desviaciones_de_obra(escenario.obra_id) == []


class TestReemplazarEnlace:
    async def test_el_viejo_pasa_a_no_vigente_y_la_suma_cambia(
        self, escenario: Escenario, contexto_control: ContextoSesion
    ) -> None:
        await _preparar_actividad_con_concepto(
            org_id=escenario.org_id,
            actividad_id=escenario.actividad_id,
            precio_unitario=Decimal("1000"),
        )
        plano_id = await _crear_plano(contexto_control, obra_id=escenario.obra_id)

        # Primer trazo: cuadrado de 10x10 = área 100 (coincide con
        # cant_base, no genera Desviacion, pero sí deja un enlace vigente).
        async with sesion_con_rls(contexto_control) as sesion:
            primero = await _caso_uso_registrar_trazo(sesion).ejecutar(
                ComandoRegistrarTrazo(
                    plano_id=plano_id,
                    version_plano=1,
                    capa=None,
                    fuente=str(FuenteTrazo.PDF),
                    geometria_wkt="POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))",
                    autor_id=contexto_control.usuario_id,
                    rol=Rol.CONTROL_OBRA,
                    enlaces=(
                        IntencionEnlace(
                            medida=MedidaCuantificacion.AREA,
                            factor=Decimal("1"),
                            actividad_id=escenario.actividad_id,
                        ),
                    ),
                ),
                detectada_en=datetime.now(UTC),
            )
        enlace_viejo_id = primero.enlace_ids[0]
        assert primero.recalculos[0].cantidad_total == Decimal("100")

        # Un DWG (mayor precedencia) mide distinto: rectángulo 4x3 = 12,
        # sobre un trazo nuevo ya registrado aparte.
        async with sesion_con_rls(contexto_control) as sesion:
            segundo_trazo_id = await RepositorioTrazosSQL(sesion).crear(
                plano_id=plano_id,
                version_plano=1,
                capa=None,
                geometria_wkt=_RECTANGULO_4X3,
                fuente=str(FuenteTrazo.DWG),
                autor_id=contexto_control.usuario_id,
            )
            await sesion.commit()

        async with sesion_con_rls(contexto_control) as sesion:
            resultado = await _caso_uso_reemplazar_enlace(sesion).ejecutar(
                ComandoReemplazarEnlace(
                    enlace_id=enlace_viejo_id,
                    rol=Rol.CONTROL_OBRA,
                    nuevo=NuevoEnlace(
                        trazo_id=segundo_trazo_id,
                        medida=MedidaCuantificacion.AREA,
                        factor=Decimal("1"),
                    ),
                ),
                detectada_en=datetime.now(UTC),
            )

        # La suma de vigentes ahora es solo la del reemplazo: 12, no 112.
        assert resultado.cantidad_total == Decimal("12")

        async with sesion_con_rls(contexto_control) as sesion:
            enlaces_repo = RepositorioEnlacesCuantificacionSQL(sesion)
            viejo = await enlaces_repo.obtener(enlace_viejo_id)
            filas_nodo = await enlaces_repo.enlaces_de_nodo(
                tipo_nodo="actividad",
                actividad_id=escenario.actividad_id,
                prototipo_nodo_id=None,
            )
        assert viejo is not None
        assert viejo["vigente"] is False

        vigentes = [f for f in filas_nodo if f["vigente"]]
        assert len(vigentes) == 1
        assert Decimal(str(vigentes[0]["medida_valor"])) == Decimal("12")
