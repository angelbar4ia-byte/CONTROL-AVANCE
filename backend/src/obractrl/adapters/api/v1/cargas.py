"""Endpoints de Cargas de datos (§11.2 "Cargas", workflow G §11.3).

Spec §11.2 (`POST /cargas`, `GET /cargas/{id}`, `GET /cargas/plantillas/{tipo}`) ·
§10.2 (tres modos y vista previa) · §10.3 (bandeja) · §10.8 (reversa) ·
§5.1 (Configuración es de Control de obra).

Controladores delgados: validan el DTO, delegan y mapean el resultado. La
única lógica de este archivo es **defensiva**, y ahí sí tiene que estar: el
cuerpo de `POST /cargas` es un archivo que sube un usuario, así que se lee con
un tope de bytes antes de que nada lo toque.

**Diferencia con el §11.2, explícita:** el spec parte el flujo en
`POST /cargas` → `POST /cargas/{id}/validar` → `POST /cargas/{id}/aplicar`,
apoyado en que el archivo queda guardado en R2 (§11.3 G.1). Mientras las
cargas no suban a R2, un `/aplicar` posterior no tendría de dónde releer el
archivo. Aquí la vista previa del §10.2 se conserva con el campo `dry_run` de
`POST /cargas`: el cliente sube para previsualizar y vuelve a subir para
aplicar, y el hash del archivo garantiza que sea el mismo (§10.8).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import Response
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    ConsultarCargaDep,
    EliminarCargaDep,
    FabricaDeCargasDep,
    ResolverPendienteDep,
    RevertirCargaDep,
    RevertirCargaEnCadenaDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.excel.lector import LIMITES
from obractrl.adapters.excel.plantillas import nombre_de_plantilla, plantilla_de
from obractrl.application.casos_uso.gestionar_carga import (
    ComandoEjecutarCarga,
    PendienteNoResoluble,
    ResultadoCarga,
)
from obractrl.domain.shared.diccionario import ModoCarga, Rol, TipoCarga

router = APIRouter(tags=["cargas"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ErrorDeFilaRespuesta(BaseModel):
    """Un renglón del reporte de errores por fila/columna (§9.3)."""

    fila: int
    columna: str | None = None
    valor: str | None = None
    motivo: str


class CargaRespuesta(BaseModel):
    """Resultado de una carga (§9.4 `CargaDatos.resumen`)."""

    carga_id: UUID
    estatus: str
    version_generada: int | None = None
    filas: int
    insertados: int
    actualizados: int
    omitidos: int
    errores: list[ErrorDeFilaRespuesta]
    pendientes: int
    diff: dict = Field(
        default_factory=dict,
        description="Qué cambió respecto de la versión vigente (§10.8).",
    )
    reutilizada: bool = Field(
        default=False,
        description=(
            "El archivo ya se había aplicado idéntico: no se creó versión ni "
            "se tocó el catálogo (§10.8, §12.3)."
        ),
    )

    @classmethod
    def desde(cls, resultado: ResultadoCarga) -> CargaRespuesta:
        return cls(
            carga_id=resultado.carga_id,
            estatus=str(resultado.estatus),
            version_generada=resultado.version_generada,
            filas=resultado.resumen.filas,
            insertados=resultado.resumen.insertados,
            actualizados=resultado.resumen.actualizados,
            omitidos=resultado.resumen.omitidos,
            errores=[
                ErrorDeFilaRespuesta(**error.como_dict())  # type: ignore[arg-type]
                for error in resultado.errores
            ],
            pendientes=resultado.pendientes,
            diff=resultado.diff,
            reutilizada=resultado.reutilizada,
        )


class LoteRespuesta(BaseModel):
    """Estado de un lote ya registrado (§9.4)."""

    id: UUID
    tipo: str
    modo: str
    estatus: str
    archivo_nombre: str | None
    archivo_hash: str | None
    version_generada: int | None
    revertida: bool
    resumen: dict
    errores: list[dict]

    @classmethod
    def desde_fila(cls, fila: dict) -> LoteRespuesta:
        return cls(
            id=fila["id"],
            tipo=str(fila["tipo"]),
            modo=str(fila["modo"]),
            estatus=str(fila["estatus"]),
            archivo_nombre=fila.get("archivo_nombre"),
            archivo_hash=fila.get("archivo_hash"),
            version_generada=fila.get("version_generada"),
            revertida=fila.get("revertida_en") is not None,
            resumen=fila.get("resumen") or {},
            errores=fila.get("errores") or [],
        )


class PendienteBandejaRespuesta(BaseModel):
    """Renglón de la bandeja: el sistema propone, el humano confirma (§10.3)."""

    id: UUID
    carga_id: UUID | None = None
    tipo: str
    entidad: str | None
    valor_origen: str | None
    propuesta: dict
    critico: bool
    resuelto: bool
    resolucion: dict | None = None
    origen_ref: str | None

    @classmethod
    def desde_fila(cls, fila: dict) -> PendienteBandejaRespuesta:
        return cls(
            id=fila["id"],
            carga_id=fila.get("carga_id"),
            tipo=str(fila["tipo"]),
            entidad=fila.get("entidad"),
            valor_origen=fila.get("valor_origen"),
            propuesta=fila.get("propuesta") or {},
            critico=bool(fila["critico"]),
            resuelto=bool(fila["resuelto"]),
            resolucion=fila.get("resolucion"),
            origen_ref=fila.get("origen_ref"),
        )


class ResolverPendientePeticion(BaseModel):
    """Aprobar/rechazar un renglón de la bandeja (§10.3)."""

    aprobado: bool
    nota: str | None = Field(default=None, max_length=500)


class ReversaRespuesta(BaseModel):
    carga_id: UUID
    operaciones_revertidas: int
    cargas_revertidas: list[UUID] | None = Field(
        default=None,
        description=(
            "Ids de todas las cargas revertidas, en el orden en que se "
            "deshicieron. Solo se llena cuando `en_cadena=true` (§10.8)."
        ),
    )


async def _leer_con_tope(archivo: UploadFile) -> bytes:
    """Lee el archivo en trozos, cortando en cuanto pasa el tope.

    `await archivo.read()` sin argumento traería el cuerpo completo a memoria
    antes de poder medirlo: con un archivo de varios GB eso es el ataque, no
    la defensa. Aquí se corta en el trozo que cruza el límite.
    """
    tope = LIMITES.bytes_maximos
    trozos: list[bytes] = []
    leidos = 0
    while trozo := await archivo.read(1024 * 1024):
        leidos += len(trozo)
        if leidos > tope:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"El archivo excede el máximo de "
                    f"{tope // 1024 // 1024} MB por carga."
                ),
            )
        trozos.append(trozo)
    return b"".join(trozos)


@router.post(
    "/cargas",
    response_model=CargaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Subir un archivo de carga (vista previa o commit)",
    # Costos prepara la ingeniería y también la sube (D-581), pero solo esa: lo demás es de Control.
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.COSTOS))],
    responses={
        413: {"description": "El archivo excede el máximo permitido."},
        422: {"description": "El archivo no cumple el contrato del §10.6."},
    },
)
async def subir_carga(
    fabrica: FabricaDeCargasDep,
    ctx: ContextoActual,
    archivo: Annotated[UploadFile, File(description="Archivo .xlsx del §10.6.")],
    tipo: Annotated[TipoCarga, Form(description="Tipo de carga (§8.2).")],
    modo: Annotated[ModoCarga, Form(description="Modo de carga (§10.2).")] = ModoCarga.ACTUALIZAR,
    dry_run: Annotated[
        bool, Form(description="Vista previa: valida y cuenta sin escribir (§10.2).")
    ] = False,
    obra_id: Annotated[
        UUID | None,
        Form(
            description=(
                "Solo tipo='ingenieria_lote': a qué obra pertenece el lote "
                "(§11.4). Obligatorio para ese tipo — nunca se adivina del "
                "nombre del archivo."
            )
        ),
    ] = None,
    camino_ingenieria: Annotated[
        str | None,
        Form(
            description=(
                "Solo tipo='ingenieria_lote': 'conocido' (default) o "
                "'diseno_nuevo'."
            )
        ),
    ] = None,
    prototipo_base_id: Annotated[
        UUID | None,
        Form(
            description=(
                "Solo tipo='ingenieria_lote' con camino_ingenieria="
                "'diseno_nuevo': el prototipo del que se clona la "
                "estructura. Obligatorio en ese caso."
            )
        ),
    ] = None,
    nombre_prototipo_nuevo: Annotated[
        str | None,
        Form(
            description=(
                "Solo tipo='ingenieria_lote' con camino_ingenieria="
                "'diseno_nuevo', opcional: nombre del prototipo nuevo; si "
                "no se da, se usa la clave de la obra."
            )
        ),
    ] = None,
    etapa_externa: Annotated[
        str | None,
        Form(
            description=(
                "Solo tipo='ingenieria_lote' con estructura 'suelta' "
                "(§11.8): la etapa ECO-... del archivo, porque su "
                "contenido nunca la trae. Obligatorio solo para esa "
                "estructura — se valida al procesar el archivo, no aquí, "
                "porque la estructura se detecta de su contenido."
            )
        ),
    ] = None,
    prototipo_id: Annotated[
        UUID | None,
        Form(
            description=(
                "Solo tipo='programa_base' (§7.5): a qué prototipo "
                "pertenece el cronograma. Obligatorio para ese tipo — el "
                "archivo real apila varios prototipos, uno por Capítulo, "
                "y nunca se adivina cuál cargar."
            )
        ),
    ] = None,
) -> CargaRespuesta:
    """Workflow G: mapea, valida y —si no es vista previa— aplica (§11.3 G).

    Los cuatro campos de `ingenieria_lote` son **condicionales**: ningún
    otro tipo de carga los usa (`AplicadorDeCarga` genérico no los conoce,
    ver `gestionar_carga.ComandoEjecutarCarga`), así que aquí se validan
    solo contra ESE tipo — exigirlos siempre rompería los demás formularios
    que no tienen por qué mandarlos.
    """
    if Rol(ctx.rol) is Rol.COSTOS and tipo is not TipoCarga.INGENIERIA_LOTE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Costos sube la ingeniería del lote; las demás cargas son de Control de obra.",
        )
    if tipo is TipoCarga.INGENIERIA_LOTE:
        if obra_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="obra_id es obligatorio para tipo='ingenieria_lote' (§11.4).",
            )
        if camino_ingenieria == "diseno_nuevo" and prototipo_base_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "prototipo_base_id es obligatorio cuando "
                    "camino_ingenieria='diseno_nuevo'."
                ),
            )
    if tipo is TipoCarga.PROGRAMA_BASE and prototipo_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="prototipo_id es obligatorio para tipo='programa_base' (§7.5).",
        )

    contenido = await _leer_con_tope(archivo)
    caso_uso = await fabrica.para(tipo)
    resultado = await caso_uso.ejecutar(
        ComandoEjecutarCarga(
            tipo=tipo,
            contenido=contenido,
            archivo_nombre=archivo.filename or "(sin nombre)",
            usuario_id=ctx.usuario_id,
            modo=modo,
            dry_run=dry_run,
            obra_id=obra_id,
            camino_ingenieria=camino_ingenieria,
            prototipo_base_id=prototipo_base_id,
            nombre_prototipo_nuevo=nombre_prototipo_nuevo,
            etapa_externa=etapa_externa,
            prototipo_id=prototipo_id,
        )
    )
    return CargaRespuesta.desde(resultado)


@router.get(
    "/cargas",
    response_model=list[LoteRespuesta],
    summary="Historial de cargas",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE))],
)
async def listar_cargas(
    caso_uso: ConsultarCargaDep,
    tipo: Annotated[TipoCarga | None, Query(description="Filtra por tipo.")] = None,
) -> list[LoteRespuesta]:
    """Historial de versiones por tipo (§10.8): RLS ya acota el alcance."""
    return [LoteRespuesta.desde_fila(fila) for fila in await caso_uso.listar(tipo=tipo)]


# Declarado **antes** que `/cargas/{carga_id}`: si no, FastAPI intentaría
# leer "plantillas" como un UUID y respondería 422 en vez de la plantilla.
@router.get(
    "/cargas/plantillas/{tipo}",
    summary="Plantilla Excel del cargador",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA))],
    response_class=Response,
    responses={200: {"content": {_XLSX: {}}, "description": "Plantilla .xlsx"}},
)
async def descargar_plantilla(tipo: TipoCarga) -> Response:
    """`.xlsx` con las cabeceras del §10.6 de ese cargador (§9.3)."""
    return Response(
        content=plantilla_de(tipo),
        media_type=_XLSX,
        headers={
            "Content-Disposition": f'attachment; filename="{nombre_de_plantilla(tipo)}"'
        },
    )


@router.get(
    "/cargas/{carga_id}",
    response_model=LoteRespuesta,
    summary="Resultado de una carga",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE))],
    responses={404: {"description": "La carga no existe o está fuera de tu alcance."}},
)
async def obtener_carga(carga_id: UUID, caso_uso: ConsultarCargaDep) -> LoteRespuesta:
    """Resumen, reporte de errores por fila y versión generada (§9.3, §9.4)."""
    return LoteRespuesta.desde_fila(await caso_uso.obtener(carga_id))


@router.get(
    "/cargas/{carga_id}/pendientes",
    response_model=list[PendienteBandejaRespuesta],
    summary="Bandeja de pendientes de una carga",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE))],
    responses={404: {"description": "La carga no existe o está fuera de tu alcance."}},
)
async def bandeja_de_carga(
    carga_id: UUID,
    caso_uso: ConsultarCargaDep,
    solo_abiertos: Annotated[
        bool, Query(description="Solo lo que falta confirmar.")
    ] = True,
) -> list[PendienteBandejaRespuesta]:
    """Excepciones que esperan confirmación humana (§10.3)."""
    filas = await caso_uso.pendientes(carga_id, solo_abiertos=solo_abiertos)
    return [PendienteBandejaRespuesta.desde_fila(fila) for fila in filas]


@router.get(
    "/pendientes",
    response_model=list[PendienteBandejaRespuesta],
    summary="Bandeja de pendientes por autorizar (todas las cargas)",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE))],
)
async def bandeja_global(
    caso_uso: ConsultarCargaDep,
    solo_abiertos: Annotated[
        bool, Query(description="Solo lo que falta confirmar.")
    ] = True,
) -> list[PendienteBandejaRespuesta]:
    """Igual que `/cargas/{carga_id}/pendientes`, pero de cualquier carga: la
    pantalla de pendientes por autorizar no obliga a elegir una primero (§10.3)."""
    filas = await caso_uso.pendientes_globales(solo_abiertos=solo_abiertos)
    return [PendienteBandejaRespuesta.desde_fila(fila) for fila in filas]


@router.post(
    "/pendientes/{pendiente_id}/resolver",
    response_model=PendienteBandejaRespuesta,
    summary="Aprobar o rechazar un pendiente",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA))],
    responses={
        409: {
            "description": (
                "El pendiente no existe, está fuera de tu alcance, o ya se "
                "resolvió antes (§10.3: resolver es de una sola vez)."
            )
        },
    },
)
async def resolver_pendiente(
    pendiente_id: UUID,
    peticion: ResolverPendientePeticion,
    caso_uso: ResolverPendienteDep,
    ctx: ContextoActual,
) -> PendienteBandejaRespuesta:
    """Rechazar un `cpu_nuevo` de `concepto` también da de baja ESE
    concepto —el cargador ya lo había creado, "no se omite" (§10.3)— para
    que alguien lo corrija antes de que vuelva a estar disponible."""
    try:
        fila = await caso_uso.ejecutar(
            pendiente_id,
            usuario_id=ctx.usuario_id,
            aprobado=peticion.aprobado,
            nota=peticion.nota,
        )
    except PendienteNoResoluble as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return PendienteBandejaRespuesta.desde_fila(fila)


@router.post(
    "/cargas/{carga_id}/revertir",
    response_model=ReversaRespuesta,
    summary="Revertir una carga completa",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA))],
    responses={
        404: {"description": "La carga no existe o está fuera de tu alcance."},
        409: {
            "description": (
                "La carga no se aplicó, ya se revirtió, o (sin `en_cadena`) "
                "hay cargas más nuevas que dependen de lo que tocó (§10.8)."
            )
        },
    },
)
async def revertir_carga(
    carga_id: UUID,
    ctx: ContextoActual,
    caso_uso: RevertirCargaDep,
    caso_uso_en_cadena: RevertirCargaEnCadenaDep,
    en_cadena: Annotated[
        bool,
        Query(
            description=(
                "Si hay cargas más nuevas que dependen de esta, revertirlas "
                "también, de la más nueva a la más vieja, en una sola "
                "unidad (§10.8). Sin esto, esas cargas bloquean la reversa "
                "(`carga-con-dependientes`)."
            )
        ),
    ] = False,
) -> ReversaRespuesta:
    """Deshace el lote como unidad, no registro por registro (§10.8)."""
    if en_cadena:
        resultado = await caso_uso_en_cadena.ejecutar(carga_id, usuario_id=ctx.usuario_id)
    else:
        resultado = await caso_uso.ejecutar(carga_id, usuario_id=ctx.usuario_id)
    return ReversaRespuesta(**resultado)


@router.delete(
    "/cargas/{carga_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar el registro de una carga",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA))],
    responses={
        404: {"description": "La carga no existe o está fuera de tu alcance."},
        409: {
            "description": (
                "La carga se aplicó y no se ha revertido: revertirla "
                "primero (§10.8)."
            )
        },
    },
)
async def eliminar_carga(carga_id: UUID, caso_uso: EliminarCargaDep) -> None:
    """Limpia el historial de una vista previa vieja o una carga ya
    revertida (§10.8) — no de una que sigue aplicada sin deshacer."""
    await caso_uso.ejecutar(carga_id)
