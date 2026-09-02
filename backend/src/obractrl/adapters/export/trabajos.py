"""Trabajos de Arq que producen los reportes.

Spec §11.2 (`GET /estimaciones/{id}/export` (xlsx, **job**), `GET
/obras/{id}/expediente/pdf` (job), `GET /reportes/{id}` estado/descarga) ·
§12.2 (Arq + Redis) · §12.11 (el borde ensambla).

Vive en `adapters/` y no en `infrastructure/` a propósito: una función de aquí
hace lo mismo que un endpoint —arma un caso de uso con repositorios concretos
y mapea el resultado—, solo que su disparador es la cola en vez de HTTP. La
plomería de la cola (encolar, consultar, traducir la caída de Redis) sí es
infraestructura y vive en `infrastructure/jobs/cola.py`, que **no importa este
módulo**: así la dependencia no se invierte (§12.11).

**El contexto RLS viaja en el payload.** El worker corre fuera de la petición:
no hay JWT que leer, así que `org_id`, `usuario_id` y `rol` llegan como
argumentos y con ellos se abre `sesion_con_rls`, igual que lo haría el borde
HTTP. Eso es seguro **porque el único productor es la API**, que ya validó el
token y sacó esos tres valores de ahí (`adapters/api/dependencias.py`); Redis
no está expuesto a los clientes. El worker no amplía el alcance: con ese
contexto puesto, RLS filtra el reporte exactamente igual que filtraría la
consulta equivalente por HTTP (§12.4). Un usuario no puede pedir el
expediente de una obra que no ve, ni encolándolo.

El resultado vuelve como `bytes` dentro del resultado del trabajo, que Arq
guarda en Redis: el archivo **no** se sube a R2. A la escala del §12.1 un
`.xlsx` de estimación es de kilobytes y esto ahorra depender de que R2 esté
configurado para poder exportar; si algún reporte llegara a pesar, el cambio
es subirlo y devolver la clave, sin tocar ni el router ni el caso de uso.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Final
from uuid import UUID

from obractrl.adapters.export.pdf import (
    CONTENT_TYPE_PDF,
    expediente_a_pdf,
    nombre_de_archivo_expediente,
)
from obractrl.adapters.export.xlsx import (
    CONTENT_TYPE_XLSX,
    estimacion_a_xlsx,
    nombre_de_archivo_estimacion,
)
from obractrl.adapters.export.xlsx_avance import (
    avance_a_xlsx,
    nombre_de_archivo_avance,
)
from obractrl.adapters.export.xlsx_insumos import (
    insumos_a_xlsx,
    nombre_de_archivo_insumos,
)
from obractrl.adapters.repos.actividades_sql import RepositorioActividadesSQL
from obractrl.adapters.repos.calendario_sql import RepositorioCalendarioSQL
from obractrl.adapters.repos.cierres_sql import RepositorioCierresSQL
from obractrl.adapters.repos.conceptos_sql import RepositorioConceptosSQL
from obractrl.adapters.repos.estimaciones_sql import RepositorioEstimacionesSQL
from obractrl.adapters.repos.expediente_sql import RepositorioExpedienteSQL
from obractrl.adapters.repos.incidencias_sql import RepositorioIncidenciasSQL
from obractrl.adapters.repos.insumos_sql import RepositorioInsumosSQL
from obractrl.adapters.repos.materiales_sql import RepositorioMaterialesSQL
from obractrl.adapters.repos.obras_sql import RepositorioObrasSQL
from obractrl.adapters.repos.presupuestos_sql import RepositorioPresupuestosSQL
from obractrl.adapters.repos.prototipo_nodo_sql import RepositorioPrototipoNodoSQL
from obractrl.adapters.repos.revisiones_sql import RepositorioRevisionesSQL
from obractrl.adapters.repos.torre_sql import RepositorioTorreSQL
from obractrl.adapters.repos.unidades_sql import RepositorioUnidadesSQL
from obractrl.application.casos_uso.armar_reporte_de_avance import (
    ArmarReporteDeAvance,
)
from obractrl.application.casos_uso.consultar_insumos_programados import (
    ComandoInsumosProgramados,
    ConsultarInsumosProgramados,
)
from obractrl.application.casos_uso.exportar_estimacion import (
    ArmarReporteDeEstimacion,
)
from obractrl.application.casos_uso.gestionar_expediente import ArmarExpediente
from obractrl.domain.shared.diccionario import Rol
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls

__all__ = [
    "EXPEDIENTE_PDF",
    "EXPORTAR_ESTIMACION_XLSX",
    "FUNCIONES",
    "REPORTE_DE_AVANCE_XLSX",
    "exportar_estimacion_xlsx",
    "generar_expediente_pdf",
    "reporte_de_avance_xlsx",
]

_log = logging.getLogger(__name__)

EXPORTAR_ESTIMACION_XLSX: Final = "exportar_estimacion_xlsx"
EXPEDIENTE_PDF: Final = "generar_expediente_pdf"
REPORTE_DE_AVANCE_XLSX: Final = "reporte_de_avance_xlsx"
INSUMOS_PROGRAMADOS_XLSX: Final = "insumos_programados_xlsx"
"""Nombres con los que se encola y con los que el worker resuelve la función.
Son constantes y no literales sueltos porque los comparten dos procesos: un
typo aquí es un trabajo que se encola y nunca corre."""


def _contexto(*, org_id: str, usuario_id: str, rol: str) -> ContextoSesion:
    return ContextoSesion(
        org_id=UUID(org_id), usuario_id=UUID(usuario_id), rol=rol
    )


def _archivo(*, contenido: bytes, nombre: str, content_type: str) -> dict[str, Any]:
    """Forma única del resultado de un reporte. La lee `GET /reportes/{id}`."""
    return {"contenido": contenido, "nombre": nombre, "content_type": content_type}


async def exportar_estimacion_xlsx(
    _ctx: dict[str, Any],
    *,
    org_id: str,
    usuario_id: str,
    rol: str,
    estimacion_id: str,
) -> dict[str, Any]:
    """§11.2 `GET /estimaciones/{id}/export` — genera el `.xlsx`.

    Los identificadores llegan como texto: Arq serializa el payload a Redis y
    un `UUID` obliga a pickle en ambos extremos sin ganar nada.
    """
    ctx = _contexto(org_id=org_id, usuario_id=usuario_id, rol=rol)
    async with sesion_con_rls(ctx) as sesion:
        caso_uso = ArmarReporteDeEstimacion(
            estimaciones=RepositorioEstimacionesSQL(sesion),
            obras=RepositorioObrasSQL(sesion),
        )
        reporte = await caso_uso.ejecutar(UUID(estimacion_id))

    _log.info(
        "Estimación %s exportada a xlsx (%d renglones).",
        estimacion_id,
        len(reporte.conceptos),
    )
    return _archivo(
        contenido=estimacion_a_xlsx(reporte),
        nombre=nombre_de_archivo_estimacion(reporte),
        content_type=CONTENT_TYPE_XLSX,
    )


async def generar_expediente_pdf(
    _ctx: dict[str, Any],
    *,
    org_id: str,
    usuario_id: str,
    rol: str,
    obra_id: str,
) -> dict[str, Any]:
    """§11.2 `GET /obras/{id}/expediente/pdf` — genera el PDF del expediente."""
    ctx = _contexto(org_id=org_id, usuario_id=usuario_id, rol=rol)
    async with sesion_con_rls(ctx) as sesion:
        caso_uso = ArmarExpediente(
            expediente=RepositorioExpedienteSQL(sesion),
            obras=RepositorioObrasSQL(sesion),
            cierres=RepositorioCierresSQL(sesion),
            estimaciones=RepositorioEstimacionesSQL(sesion),
            revisiones=RepositorioRevisionesSQL(sesion),
            incidencias=RepositorioIncidenciasSQL(sesion),
        )
        expediente = await caso_uso.ejecutar(UUID(obra_id))

    _log.info(
        "Expediente de la obra %s: %d documentos, %d evidencias.",
        obra_id,
        len(expediente.documentos),
        expediente.n_evidencias,
    )
    return _archivo(
        contenido=expediente_a_pdf(expediente),
        nombre=nombre_de_archivo_expediente(expediente),
        content_type=CONTENT_TYPE_PDF,
    )


async def reporte_de_avance_xlsx(
    _ctx: dict[str, Any],
    *,
    org_id: str,
    usuario_id: str,
    rol: str,
    proyecto_id: str | None = None,
    cluster_id: str | None = None,
) -> dict[str, Any]:
    """§11.2 `POST /reportes/avance` — el estado de las obras **del alcance**.

    Es el primer reporte que no cuelga de una entidad: no recibe el id de
    nada, y lo que sale depende de quién lo pidió. Eso funciona porque el
    contexto RLS viaja en el payload y se vuelve a fijar aquí (ver el
    encabezado del módulo): el worker ve exactamente las obras que vería ese
    usuario por HTTP, ni una más.

    `proyecto_id` y `cluster_id` son **foco**, no permiso: acotan dentro de lo
    que ya se puede ver. Pasar el proyecto de otra organización no amplía
    nada — devuelve vacío, que es lo correcto.
    """
    ctx = _contexto(org_id=org_id, usuario_id=usuario_id, rol=rol)
    async with sesion_con_rls(ctx) as sesion:
        caso_uso = ArmarReporteDeAvance(torre=RepositorioTorreSQL(sesion))
        reporte = await caso_uso.ejecutar(
            proyecto_id=UUID(proyecto_id) if proyecto_id else None,
            cluster_id=UUID(cluster_id) if cluster_id else None,
        )

    _log.info(
        "Reporte de avance para el rol %s: %d obras, %d requieren atención.",
        rol,
        reporte.total_obras,
        reporte.obras_que_requieren_atencion,
    )
    return _archivo(
        contenido=avance_a_xlsx(reporte),
        nombre=nombre_de_archivo_avance(reporte),
        content_type=CONTENT_TYPE_XLSX,
    )


async def insumos_programados_xlsx(
    _ctx: dict[str, Any],
    *,
    org_id: str,
    usuario_id: str,
    rol: str,
    desde: str,
    hasta: str,
    granularidad: str = "semana",
    obra_id: str | None = None,
    residente_id: str | None = None,
    supervisor_id: str | None = None,
    prototipo_id: str | None = None,
    n_casas: int = 1,
    dias_anticipacion: int = 0,
) -> dict[str, Any]:
    """§11.2 `POST /reportes/insumos-programados` — qué comprar y cuándo.

    La hoja que se manda al proveedor. Como el de avance, no cuelga de una
    entidad: lo que sale depende de quién lo pidió, y funciona porque el
    contexto RLS viaja en el payload y se vuelve a fijar aquí.

    **El rol decide si el archivo trae dinero**, con el mismo criterio que el
    endpoint: cantidades para los cuatro, importes solo para Control de obra y
    el Super intendente. Un residente que baja su hoja obtiene exactamente lo
    que ve en pantalla — si aquí fuera distinto, el reporte sería el rodeo para
    saltarse la guarda de la ruta.
    """
    ctx = _contexto(org_id=org_id, usuario_id=usuario_id, rol=rol)
    con_importe = rol in {Rol.CONTROL_OBRA.value, Rol.SUPER_INTENDENTE.value}

    async with sesion_con_rls(ctx) as sesion:
        caso_uso = ConsultarInsumosProgramados(
            actividades=RepositorioActividadesSQL(sesion),
            conceptos=RepositorioConceptosSQL(sesion),
            insumos=RepositorioInsumosSQL(sesion),
            unidades=RepositorioUnidadesSQL(sesion),
            calendario=RepositorioCalendarioSQL(sesion),
            obras=RepositorioObrasSQL(sesion),
            presupuestos=RepositorioPresupuestosSQL(sesion),
            materiales=RepositorioMaterialesSQL(sesion),
            nodos=RepositorioPrototipoNodoSQL(sesion),
        )
        resultado = await caso_uso.ejecutar(
            ComandoInsumosProgramados(
                desde=date.fromisoformat(desde),
                hasta=date.fromisoformat(hasta),
                granularidad=granularidad,
                obra_id=UUID(obra_id) if obra_id else None,
                residente_id=UUID(residente_id) if residente_id else None,
                supervisor_id=UUID(supervisor_id) if supervisor_id else None,
                prototipo_id=UUID(prototipo_id) if prototipo_id else None,
                n_casas=n_casas,
                dias_anticipacion=dias_anticipacion,
                con_importe=con_importe,
            )
        )

    hoy = date.today()
    _log.info(
        "Insumos programados para el rol %s: %d insumos en %d periodos.",
        rol,
        len(resultado.matriz.filas),
        len(resultado.matriz.periodos),
    )
    return _archivo(
        contenido=insumos_a_xlsx(
            resultado, con_importe=con_importe, generado_en=hoy
        ),
        nombre=nombre_de_archivo_insumos(hoy),
        content_type=CONTENT_TYPE_XLSX,
    )


FUNCIONES = (
    exportar_estimacion_xlsx,
    generar_expediente_pdf,
    reporte_de_avance_xlsx,
    insumos_programados_xlsx,
)
"""Lo que el worker registra (`obractrl/trabajador.py`). Arq resuelve cada
trabajo por el `__name__` de la función, que es lo que
`EXPORTAR_ESTIMACION_XLSX` y `EXPEDIENTE_PDF` deletrean."""
