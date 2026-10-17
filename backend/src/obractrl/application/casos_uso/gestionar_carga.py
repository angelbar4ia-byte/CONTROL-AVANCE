"""Casos de uso de cargas de datos — workflow G (§11.3).

Spec §11.3 G (subir → validar → aplicar) · §9.2 (pipeline) · §9.4
(`CargaDatos`) · §10.2 (lote reversible, tres modos) · §10.3 (bandeja) ·
§10.8 (versionado y reversa) · §12.3 (idempotencia por clave).

Tres operaciones:

- :class:`EjecutarCarga` — sube un archivo y lo **previsualiza** o lo
  **aplica**. Los dos caminos corren exactamente el mismo pipeline; la
  diferencia es si se escribe (§9.3: "dry-run obligatorio", y por eso la vista
  previa tiene que dar los mismos números que el commit).
- :class:`RevertirCarga` — deshace el lote completo (§10.8), nunca registro
  por registro.
- :class:`ConsultarCarga` — estado del lote y su bandeja de pendientes.

**Idempotencia (§10.8, §12.3).** Antes de aplicar se busca una carga del
mismo tipo, ya aplicada y no revertida, con el mismo hash de archivo: si
existe, no se crea versión ni se toca el catálogo. Y aunque el hash difiera,
si el diff sale vacío tampoco se genera versión — "si es idéntico, no crea
versión" es sobre el **contenido**, no sobre el archivo.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.aplicar_carga import (
    AplicadorDeCarga,
    AplicadorIngenieriaLote,
    AplicadorProgramaBase,
)
from obractrl.application.puertos.cargadores import LectorDeCarga, RepositorioCargas
from obractrl.application.puertos.repositorios import (
    RepositorioConceptos,
    UnidadDeTrabajo,
)
from obractrl.domain.cargadores.reporte import ErrorDeFila, ResumenCarga, TipoPendiente
from obractrl.domain.shared.diccionario import EstatusCarga, ModoCarga, TipoCarga

__all__ = [
    "CargaConDependientes",
    "CargaNoEliminable",
    "CargaNoEncontrada",
    "CargaNoRevertible",
    "ComandoEjecutarCarga",
    "ConsultarCarga",
    "EjecutarCarga",
    "EliminarCarga",
    "PendienteNoResoluble",
    "ResolverPendiente",
    "ResultadoCarga",
    "RevertirCarga",
    "RevertirCargaEnCadena",
]


class CargaNoEncontrada(LookupError):
    """El lote no existe o está fuera del alcance del usuario (§12.4)."""


class CargaNoRevertible(RuntimeError):
    """El lote no se puede revertir: no llegó a aplicarse o ya se revirtió."""


class CargaConDependientes(RuntimeError):
    """Hay cargas más nuevas que dependen de lo que esta carga tocó (§10.8).

    Revertirla sola dejaría una referencia rota — el mismo `IntegrityError`
    que `ReversaEnConflicto` (`adapters.repos.cargas_sql`) traduce cuando se
    llega a intentarlo de todos modos. Aquí se corta antes: hay que revertir
    esas cargas primero, o revertir la cadena completa con
    `RevertirCargaEnCadena`.
    """

    def __init__(self, carga_id: UUID, dependientes: list[dict[str, Any]]) -> None:
        detalle = "; ".join(
            f"{d['tipo']} · {d['archivo_nombre']} ({d['fecha']:%d/%m/%Y})"
            for d in dependientes
        )
        super().__init__(
            f"La carga {carga_id} no se puede revertir sola: "
            f"{len(dependientes)} carga(s) más reciente(s) dependen de lo que "
            f"tocó — {detalle}. Revierte esas primero, o revierte la cadena "
            f"completa (§10.8)."
        )
        self.carga_id = carga_id
        self.dependientes = dependientes


class CargaNoEliminable(RuntimeError):
    """El lote se aplicó y no se ha revertido: borrar su registro ahora
    dejaría el catálogo modificado sin ninguna forma de deshacerlo."""


@dataclass(frozen=True, slots=True)
class ComandoEjecutarCarga:
    """Subida de un archivo (§11.3 G.1, §11.2 `POST /cargas`)."""

    tipo: TipoCarga
    contenido: bytes
    archivo_nombre: str
    usuario_id: UUID | None = None
    modo: ModoCarga = ModoCarga.ACTUALIZAR
    dry_run: bool = False
    """``True`` = vista previa (§10.2): valida, cuenta y llena la bandeja, sin
    escribir el catálogo."""

    obra_id: UUID | None = None
    """Solo `TipoCarga.INGENIERIA_LOTE` (extensión propia, Fase B): a qué
    obra pertenece el lote. Nunca se parsea del nombre del archivo —se
    declara explícito antes de subir (ver `AplicadorIngenieriaLote`). Vive
    aquí y no en `archivo_nombre` por el mismo motivo que ese campo no
    llega al lector: el lector sigue siendo puro y no necesita contexto de
    obra, pero a diferencia de `archivo_nombre` (que ningún aplicador usa
    todavía) este SÍ tiene que llegar hasta `AplicadorIngenieriaLote.
    aplicar()`."""

    camino_ingenieria: str | None = None
    """Solo `TipoCarga.INGENIERIA_LOTE`: `'conocido'` (default si se omite)
    o `'diseno_nuevo'` (`aplicar_carga.CaminoIngenieria`). Nombrado distinto
    de `modo` a propósito: ese es `ModoCarga` (actualizar/acumular/
    reemplazar, §10.2) — decide CÓMO se escribe un catálogo que ya existe.
    Este decide CONTRA QUÉ prototipo se compara y se escribe la
    ingeniería; son dos preguntas distintas que no comparten campo."""

    prototipo_base_id: UUID | None = None
    """Solo `TipoCarga.INGENIERIA_LOTE`, camino `'diseno_nuevo'`: el
    prototipo del que se clona la estructura."""

    nombre_prototipo_nuevo: str | None = None
    """Solo `TipoCarga.INGENIERIA_LOTE`, camino `'diseno_nuevo'`, opcional:
    nombre del prototipo nuevo; si no se da, se usa la propia clave de la
    obra (ver `AplicadorIngenieriaLote._aplicar_diseno_nuevo`)."""

    etapa_externa: str | None = None
    """Solo `TipoCarga.INGENIERIA_LOTE`, estructura `suelta` (§11.8): la
    etapa `ECO-...` a la que pertenece el archivo, porque su contenido
    nunca la trae (columna 0 siempre vacía). Mismo criterio que `obra_id`
    —se declara explícito antes de subir, nunca se adivina del nombre del
    archivo— y por eso vive aquí, no en `archivo_nombre`."""

    prototipo_id: UUID | None = None
    """Solo `TipoCarga.PROGRAMA_BASE` (extensión propia, §7.5): a qué
    prototipo pertenece el cronograma. El archivo real apila varios
    prototipos uno tras otro (un `Capítulo` por prototipo,
    `domain.cargadores.programa_base`); igual que `obra_id` en la
    ingeniería del lote, se declara explícito antes de subir, nunca se
    adivina del contenido del archivo."""


@dataclass(frozen=True, slots=True)
class ResultadoCarga:
    """Lo que ve quien subió el archivo (§9.3, §9.4)."""

    carga_id: UUID
    estatus: EstatusCarga
    resumen: ResumenCarga
    errores: tuple[ErrorDeFila, ...] = ()
    pendientes: int = 0
    version_generada: int | None = None
    diff: dict[str, Any] = field(default_factory=dict)
    reutilizada: bool = False
    """``True`` cuando el archivo ya se había aplicado idéntico: no se creó
    versión ni se tocó nada (§10.8, §12.3)."""


class EjecutarCarga:
    """`POST /cargas` — workflow G completo sobre un archivo (§11.3 G)."""

    def __init__(
        self,
        *,
        cargas: RepositorioCargas,
        lector: LectorDeCarga,
        aplicador: AplicadorDeCarga,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._cargas = cargas
        self._lector = lector
        self._aplicador = aplicador
        self._uow = uow

    async def ejecutar(self, cmd: ComandoEjecutarCarga) -> ResultadoCarga:
        huella = hashlib.sha256(cmd.contenido).hexdigest()

        if not cmd.dry_run:
            previa = await self._cargas.buscar_aplicada_por_hash(
                tipo=str(cmd.tipo), archivo_hash=huella
            )
            if previa is not None:
                return _resultado_reutilizado(previa)

        # Parsear **antes** de abrir el lote: si el archivo ni siquiera se
        # puede leer (`ErrorDeArchivo`), no hay nada que registrar.
        lectura = self._lector.leer(cmd.contenido)

        carga_id = await self._cargas.crear(
            tipo=str(cmd.tipo),
            modo=str(cmd.modo),
            archivo_nombre=cmd.archivo_nombre,
            archivo_hash=huella,
            usuario_id=cmd.usuario_id,
        )

        if isinstance(self._aplicador, AplicadorIngenieriaLote):
            # Único aplicador que necesita contexto fuera del archivo
            # (§11.4): el `Protocol` genérico `AplicadorDeCarga` no lo
            # declara —agregarlo ahí obligaría a los otros ~15 aplicadores
            # a aceptar parámetros que nunca usan—, así que se angosta el
            # tipo aquí mismo, en el único lugar que lo necesita.
            aplicacion = await self._aplicador.aplicar(
                lectura,
                modo=cmd.modo,
                dry_run=cmd.dry_run,
                carga_id=carga_id,
                obra_id=cmd.obra_id,
                camino=cmd.camino_ingenieria,
                prototipo_base_id=cmd.prototipo_base_id,
                nombre_prototipo_nuevo=cmd.nombre_prototipo_nuevo,
                etapa_externa=cmd.etapa_externa,
            )
        elif isinstance(self._aplicador, AplicadorProgramaBase):
            # Igual que `AplicadorIngenieriaLote`: necesita contexto fuera
            # del archivo (`prototipo_id`, §7.5) que el `Protocol` genérico
            # no declara, así que se angosta el tipo aquí mismo.
            aplicacion = await self._aplicador.aplicar(
                lectura,
                modo=cmd.modo,
                dry_run=cmd.dry_run,
                carga_id=carga_id,
                prototipo_id=cmd.prototipo_id,
            )
        else:
            aplicacion = await self._aplicador.aplicar(
                lectura, modo=cmd.modo, dry_run=cmd.dry_run, carga_id=carga_id
            )

        errores = (*lectura.errores, *aplicacion.errores)
        pendientes = (*lectura.pendientes, *aplicacion.pendientes)

        version: int | None = None
        if not cmd.dry_run and aplicacion.diff.hay_cambios:
            # "Cada carga = una versión" (§10.8) — pero solo si algo cambió:
            # un archivo que no mueve nada no genera versión.
            version = await self._cargas.siguiente_version(tipo=str(cmd.tipo))

        estatus = (
            EstatusCarga.PREVISUALIZADO if cmd.dry_run else EstatusCarga.APLICADO
        )
        resumen = ResumenCarga(
            filas=lectura.filas_leidas,
            insertados=aplicacion.insertados,
            actualizados=aplicacion.actualizados,
            omitidos=aplicacion.omitidos,
            errores=len(errores),
            pendientes=len(pendientes),
        )

        async with self._uow:
            if aplicacion.operaciones:
                await self._cargas.registrar_snapshots(
                    carga_id, list(aplicacion.operaciones)
                )
            if pendientes:
                await self._cargas.crear_pendientes(
                    carga_id, [p.como_dict() for p in pendientes]
                )
            await self._cargas.finalizar(
                carga_id,
                estatus=str(estatus),
                resumen={
                    **resumen.como_dict(),
                    "diff": aplicacion.diff.como_dict(),
                    **aplicacion.detalle,
                },
                errores=[e.como_dict() for e in errores],
                version_generada=version,
            )
            await self._uow.commit()

        return ResultadoCarga(
            carga_id=carga_id,
            estatus=estatus,
            resumen=resumen,
            errores=errores,
            pendientes=len(pendientes),
            version_generada=version,
            diff=aplicacion.diff.como_dict(),
        )


def _resultado_reutilizado(previa: dict[str, Any]) -> ResultadoCarga:
    """Respuesta cuando el archivo ya se aplicó idéntico (§10.8, §12.3)."""
    guardado = previa.get("resumen") or {}
    return ResultadoCarga(
        carga_id=previa["id"],
        estatus=EstatusCarga.APLICADO,
        resumen=ResumenCarga(
            filas=int(guardado.get("filas", 0)),
            omitidos=int(guardado.get("filas", 0)),
        ),
        version_generada=previa.get("version_generada"),
        diff=guardado.get("diff") or {},
        reutilizada=True,
    )


async def _validar_revertible(cargas: RepositorioCargas, carga_id: UUID) -> dict[str, Any]:
    """Existe, se aplicó y no se ha revertido — lo que `RevertirCarga` y
    `RevertirCargaEnCadena` exigen por igual antes de tocar nada (§10.8)."""
    carga = await cargas.obtener(carga_id)
    if carga is None:
        # RLS hace indistinguible "no existe" de "no la puedes ver" (§12.4).
        raise CargaNoEncontrada(
            f"No existe la carga {carga_id} o está fuera de tu alcance."
        )
    if str(carga["estatus"]) != str(EstatusCarga.APLICADO):
        raise CargaNoRevertible(
            f"La carga está en estatus {carga['estatus']!r}: solo se revierte "
            f"lo que se aplicó (§10.8)."
        )
    if carga.get("revertida_en") is not None:
        raise CargaNoRevertible(f"La carga ya se revirtió el {carga['revertida_en']}.")
    return carga


async def _revertir_una(
    cargas: RepositorioCargas, carga_id: UUID, *, usuario_id: UUID | None
) -> int:
    """Deshace las operaciones de una carga y la marca revertida.

    Sin transacción propia a propósito: quien llama decide el alcance —una
    sola carga (`RevertirCarga`) o una cadena completa como una sola unidad
    (`RevertirCargaEnCadena`, §10.8)."""
    operaciones = await cargas.snapshots(carga_id)
    # En orden inverso: el repositorio ya las devuelve así. Importa — el CPU
    # vigente anterior no se puede volver a marcar vigente antes de borrar
    # el nuevo (`uq_cpu_vigente`).
    for operacion in operaciones:
        await cargas.revertir_operacion(operacion)
    await cargas.marcar_revertida(carga_id, usuario_id=usuario_id)
    return len(operaciones)


class RevertirCarga:
    """Deshace un lote completo (§10.8).

    "Una carga se revierte/elimina **como unidad** (el lote completo),
    dejando los datos como estaban antes de esa carga. No se borra registro
    por registro: se revierte el lote."

    Antes de tocar nada, exige que ninguna carga más nueva dependa de lo que
    esta tocó (`CargaConDependientes`): revertirla sola dejaría una
    referencia rota. La salida para ese caso es `RevertirCargaEnCadena`.
    """

    def __init__(self, *, cargas: RepositorioCargas, uow: UnidadDeTrabajo) -> None:
        self._cargas = cargas
        self._uow = uow

    async def ejecutar(
        self, carga_id: UUID, *, usuario_id: UUID | None = None
    ) -> dict[str, Any]:
        await _validar_revertible(self._cargas, carga_id)

        dependientes = await self._cargas.dependientes_de(carga_id)
        if dependientes:
            raise CargaConDependientes(carga_id, dependientes)

        async with self._uow:
            operaciones_revertidas = await _revertir_una(
                self._cargas, carga_id, usuario_id=usuario_id
            )
            await self._uow.commit()

        return {"carga_id": carga_id, "operaciones_revertidas": operaciones_revertidas}


class RevertirCargaEnCadena:
    """Deshace una carga **y** todas las que dependen de lo que tocó, como
    una sola unidad (§10.8).

    Es la salida de `CargaConDependientes`: en vez de obligar a revertir
    cada carga posterior a mano en el orden correcto, cierra la cadena
    completa (BFS sobre `dependientes_de`, cadenas cortas en la práctica —
    un `WITH RECURSIVE` sería de más) y la revierte entera, de la más nueva
    a la más vieja, en una sola transacción: o queda revertida completa, o
    no se movió nada.
    """

    def __init__(self, *, cargas: RepositorioCargas, uow: UnidadDeTrabajo) -> None:
        self._cargas = cargas
        self._uow = uow

    async def _cerrar_cadena(self, carga_id: UUID) -> list[dict[str, Any]]:
        vistas: dict[UUID, dict[str, Any]] = {}
        frontera = [carga_id]
        while frontera:
            actual = frontera.pop()
            for dependiente in await self._cargas.dependientes_de(actual):
                if dependiente["id"] in vistas or dependiente["id"] == carga_id:
                    continue
                vistas[dependiente["id"]] = dependiente
                frontera.append(dependiente["id"])
        return list(vistas.values())

    async def ejecutar(
        self, carga_id: UUID, *, usuario_id: UUID | None = None
    ) -> dict[str, Any]:
        raiz = await _validar_revertible(self._cargas, carga_id)
        dependientes = await self._cerrar_cadena(carga_id)

        # La más nueva primero: una carga no se puede revertir mientras algo
        # que ella tocó siga con una fila viva más nueva encima (§10.8).
        orden = [*sorted(dependientes, key=lambda d: d["fecha"], reverse=True), raiz]

        async with self._uow:
            total = 0
            revertidas: list[UUID] = []
            for carga in orden:
                total += await _revertir_una(
                    self._cargas, carga["id"], usuario_id=usuario_id
                )
                revertidas.append(carga["id"])
            await self._uow.commit()

        return {
            "carga_id": carga_id,
            "cargas_revertidas": revertidas,
            "operaciones_revertidas": total,
        }


class EliminarCarga:
    """Borra el registro de una carga que no tiene nada pendiente de
    revertir: una vista previa que nunca escribió (§9.3), una que falló
    antes de aplicar, o una que ya se revirtió. `carga_snapshot` y
    `pendiente` se van en cascada (`on delete cascade` desde el diseño
    original de estas tablas, §10.8) — no hay nada más que limpiar a mano.

    Una carga aplicada y **sin** revertir no se puede eliminar directo:
    borrar su snapshot sin deshacer los cambios que hizo dejaría el
    catálogo modificado y sin ninguna forma de revertirlo. Revertir
    primero, eliminar después — son dos pasos a propósito, no uno.
    """

    def __init__(self, *, cargas: RepositorioCargas, uow: UnidadDeTrabajo) -> None:
        self._cargas = cargas
        self._uow = uow

    async def ejecutar(self, carga_id: UUID) -> None:
        carga = await self._cargas.obtener(carga_id)
        if carga is None:
            raise CargaNoEncontrada(
                f"No existe la carga {carga_id} o está fuera de tu alcance."
            )
        aplicada_sin_revertir = (
            str(carga["estatus"]) == str(EstatusCarga.APLICADO)
            and carga.get("revertida_en") is None
        )
        if aplicada_sin_revertir:
            raise CargaNoEliminable(
                "Esta carga se aplicó y no se ha revertido: revierte primero "
                "(§10.8), o se perdería la única forma de deshacer sus "
                "cambios."
            )
        async with self._uow:
            await self._cargas.eliminar(carga_id)
            await self._uow.commit()


class ConsultarCarga:
    """`GET /cargas`, `GET /cargas/{id}` y su bandeja (§11.2, §10.3)."""

    def __init__(self, *, cargas: RepositorioCargas) -> None:
        self._cargas = cargas

    async def obtener(self, carga_id: UUID) -> dict[str, Any]:
        carga = await self._cargas.obtener(carga_id)
        if carga is None:
            raise CargaNoEncontrada(
                f"No existe la carga {carga_id} o está fuera de tu alcance."
            )
        return carga

    async def listar(self, *, tipo: TipoCarga | None = None) -> list[dict[str, Any]]:
        return await self._cargas.listar(tipo=str(tipo) if tipo else None)

    async def pendientes(
        self, carga_id: UUID, *, solo_abiertos: bool = True
    ) -> list[dict[str, Any]]:
        await self.obtener(carga_id)
        return await self._cargas.listar_pendientes(
            carga_id=carga_id, solo_abiertos=solo_abiertos
        )

    async def pendientes_globales(
        self, *, solo_abiertos: bool = True
    ) -> list[dict[str, Any]]:
        """Bandeja completa, de cualquier carga (§10.3): la pantalla de
        pendientes por autorizar no obliga a elegir una carga primero."""
        return await self._cargas.listar_pendientes(
            carga_id=None, solo_abiertos=solo_abiertos
        )


class PendienteNoResoluble(LookupError):
    """El pendiente no existe, está fuera de alcance, o ya se resolvió
    antes (§10.3: resolver es de una sola vez, no se pisa)."""


class ResolverPendiente:
    """Aprobar/rechazar un renglón de la bandeja (§10.3, pantalla de
    pendientes por autorizar).

    Aprobar solo cierra el pendiente: lo que el sistema ya hizo —el alta
    automática— se queda como está. Rechazar un `CPU_NUEVO` de `concepto`
    además da de baja ESE concepto (`estatus=inactivo`): el cargador ya lo
    creó porque "no se omite" (§10.3), pero un humano decidió que la clave
    no era confiable tal cual llegó. No se borra —queda editable desde el
    catálogo— para que, corregido, alguien lo reactive a mano; rechazar no
    es lo mismo que nunca haber existido.
    """

    def __init__(
        self,
        *,
        cargas: RepositorioCargas,
        conceptos: RepositorioConceptos,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._cargas = cargas
        self._conceptos = conceptos
        self._uow = uow

    async def ejecutar(
        self,
        pendiente_id: UUID,
        *,
        usuario_id: UUID | None,
        aprobado: bool,
        nota: str | None = None,
    ) -> dict[str, Any]:
        async with self._uow:
            fila = await self._cargas.resolver_pendiente(
                pendiente_id, usuario_id=usuario_id, aprobado=aprobado, nota=nota
            )
            if fila is None:
                raise PendienteNoResoluble(
                    f"El pendiente {pendiente_id} no existe, está fuera de tu "
                    f"alcance, o ya se resolvió."
                )

            es_concepto_nuevo = (
                fila["tipo"] == str(TipoPendiente.CPU_NUEVO) and fila["entidad"] == "concepto"
            )
            if not aprobado and es_concepto_nuevo and fila["valor_origen"]:
                concepto = await self._conceptos.obtener_por_clave(fila["valor_origen"])
                if concepto is not None:
                    await self._conceptos.actualizar(concepto["id"], {"estatus": "inactivo"})

            await self._uow.commit()

        return fila
