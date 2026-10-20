"""Alta directa del programa base de los 7 prototipos (§7.5, Paso 4 del plan
del rollout): "Programa base de cada prototipo. Se da de alta por la API (no
hay cargador) con PROGRAMAS-PROTOTIPOS.csv y la red mínima."

Por qué un script y no `TipoCarga.PROGRAMA_BASE` (el cargador de archivo que
sí existe, para `PROGRAMA_<PROTOTIPO>.xlsx`): ese archivo nativo de OPUS solo
trae `Vínculos` poblado en el bloque de Zafiro — los otros seis prototipos no
tienen ahí ningún vínculo (verificado fila por fila). `PROGRAMAS-PROTOTIPOS.
csv` es el que de verdad trae la red resuelta para los 7 ("red mínima": la
columna `regla` documenta cómo se infirió cada vínculo que OPUS no
programó). Cargar ESTE archivo por el pipeline genérico de `TipoCarga`
—pensado para archivos que un usuario sube una y otra vez— sería forzar una
migración histórica, de una sola vez, por un camino hecho para otra cosa; el
plan es explícito en que no lleva cargador. Este script llama directo a
`AplicadorProgramaBase.aplicar`/`CrearProgramaBase` — el mismo caso de uso
que ya resuelve `ruta`→`prototipo_nodo_id` y vínculos para el archivo nativo
— y nunca pasa por `EjecutarCarga`/`FabricaDeCargas`/la bandeja de pendientes
genérica: no queda fila en `carga_datos` ni versión que revertir con
`RevertirCarga` — revertir esto es, como con cualquier alta de programa base,
dar de alta una versión nueva (§10.8, `AplicadorProgramaBase`).

**El ancla, no el CPM puro.** `AplicadorProgramaBase.aplicar` acepta
`anclas_dias` (fila del archivo → offset en días hábiles desde el arranque
del bloque) precisamente para este archivo: cada partida se da de alta con
su propio `inicio_dias` tomado de la fecha real que trae el archivo, no
derivado de la red de vínculos. La red es deliberadamente mínima (cubre los
relevos entre oficios, no cada secuencia dentro de un mismo oficio) y por sí
sola no reconstruye el 95% de las fechas reales — ver el docstring de
`tests/domain/test_programa_base_motor_cpm_real.py`, que prueba exactamente
este mecanismo contra el archivo real (100% de los inicios, 89.3% de los
fines — el resto son interrupciones reales de obra que este archivo
consolidado no expone como tramo). El ancla reproduce la fecha histórica tal
cual; la red de vínculos queda para cuando este programa base se reprograme
a futuro (una obra que se atrasa, una réplica con otro arranque).

Uso:
    DATABASE_URL=... python scripts/cargar_programas_prototipos.py \\
        --org-id <uuid> --usuario-id <uuid> \\
        [--archivo /ruta/a/PROGRAMAS-PROTOTIPOS.csv] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from obractrl.adapters.repos.programas_sql import RepositorioProgramasSQL  # noqa: E402
from obractrl.adapters.repos.prototipo_nodo_sql import RepositorioPrototipoNodoSQL  # noqa: E402
from obractrl.adapters.repos.prototipos_sql import RepositorioPrototiposSQL  # noqa: E402
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL  # noqa: E402
from obractrl.application.casos_uso.aplicar_carga import (  # noqa: E402
    AplicadorProgramaBase,
    PrototipoDeProgramaNoEncontrado,
)
from obractrl.application.casos_uso.gestionar_programacion import CrearProgramaBase  # noqa: E402
from obractrl.domain.cargadores.cabeceras import PROGRAMA_BASE, resolver_encabezados  # noqa: E402
from obractrl.domain.cargadores.programa_base import (  # noqa: E402
    BloqueProgramaCargado,
    leer_programa_base,
)
from obractrl.domain.cargadores.reporte import LecturaCarga  # noqa: E402
from obractrl.domain.programacion.calendario import CalendarioLaboral  # noqa: E402
from obractrl.domain.shared.diccionario import ModoCarga  # noqa: E402
from obractrl.infrastructure.db.sesion import ContextoSesion, sesion_con_rls  # noqa: E402

_ARCHIVO_DEFAULT = Path(
    "/home/user/cerebro-erp-construccion/1-mundo/programas/PROGRAMAS-PROTOTIPOS.csv"
)

CALENDARIO_PROGRAMA_BASE = CalendarioLaboral.de([1, 2, 3, 4, 5])
"""Lunes a viernes — mismo calendario que ya usa `AplicadorProgramaBase` al
dar de alta el programa base desde el archivo nativo de OPUS."""


def leer_bloques(ruta: Path) -> tuple[BloqueProgramaCargado, ...]:
    with ruta.open(newline="", encoding="utf-8-sig") as f:
        todas = list(csv.reader(f))
    encabezados = todas[0]
    filas = [
        (numero, fila)
        for numero, fila in enumerate(todas[1:], start=2)
        if any(celda.strip() for celda in fila)
    ]
    mapa = resolver_encabezados(encabezados, PROGRAMA_BASE)
    bloques, errores = leer_programa_base(filas, mapa)
    if errores:
        raise SystemExit(f"{ruta}: {len(errores)} fila(s) con error, p. ej. {errores[0]}")
    return bloques


def anclas_de(bloque: BloqueProgramaCargado) -> dict[int, Decimal]:
    """`fila → inicio_dias`: el offset en días hábiles desde el arranque del
    bloque hasta la fecha real de cada partida (ver el docstring del
    módulo)."""
    partidas = bloque.partidas
    if not partidas:
        return {}
    ancla = min(p.inicio for p in partidas)
    return {
        p.fila: Decimal(CALENDARIO_PROGRAMA_BASE.dias_entre(ancla, p.inicio))
        for p in partidas
    }


async def cargar_programas_prototipos(
    sesion,
    *,
    ruta: Path = _ARCHIVO_DEFAULT,
    dry_run: bool = False,
) -> dict[str, UUID]:
    """Núcleo importable (sin CLI ni manejo de conexión): da de alta el
    programa base de cada prototipo del archivo cuya clave ya existe en el
    alcance de `sesion`. Devuelve `clave_prototipo -> prototipo_id` de los
    que sí se cargaron.

    `dry_run` se pasa tal cual a `AplicadorProgramaBase.aplicar`, que es
    quien de verdad decide no escribir nada (`CrearProgramaBase.ejecutar`
    abre y confirma su **propia** unidad de trabajo — ver su docstring —,
    así que un `sesion.rollback()` después de llamar a este núcleo con
    `dry_run=False` no deshace nada: lo ya confirmado por esa unidad de
    trabajo interna queda escrito)."""
    bloques = leer_bloques(ruta)

    prototipos_repo = RepositorioPrototiposSQL(sesion)
    aplicador = AplicadorProgramaBase(
        prototipos=prototipos_repo,
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        crear_programa_base=CrearProgramaBase(
            programas=RepositorioProgramasSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
        ),
    )

    por_clave = {str(p["clave"]): UUID(str(p["id"])) for p in await prototipos_repo.listar()}
    lectura = LecturaCarga(registros=bloques)

    cargados: dict[str, UUID] = {}
    for bloque in bloques:
        prototipo_id = por_clave.get(bloque.clave_prototipo)
        if prototipo_id is None:
            print(
                f"  {bloque.clave_prototipo}: no existe ningún prototipo con "
                "esa clave en este alcance — se omite (dalo de alta primero "
                "con el alta plana de prototipos, §7.2)."
            )
            continue

        try:
            aplicacion = await aplicador.aplicar(
                lectura,
                modo=ModoCarga.ACTUALIZAR,
                dry_run=dry_run,
                carga_id=uuid4(),
                prototipo_id=prototipo_id,
                anclas_dias=anclas_de(bloque),
            )
        except PrototipoDeProgramaNoEncontrado as exc:
            print(f"  {bloque.clave_prototipo}: {exc}")
            continue

        print(
            f"  {bloque.clave_prototipo}: {aplicacion.insertados} items, "
            f"{len(aplicacion.pendientes)} pendiente(s), "
            f"{aplicacion.detalle.get('vinculos_rechazados', 0)} vínculo(s) "
            f"rechazado(s), {aplicacion.detalle.get('vinculos_incumplidos', 0)} "
            "incumplido(s)."
        )
        cargados[bloque.clave_prototipo] = prototipo_id

    return cargados


async def _main_async(args: argparse.Namespace) -> int:
    ctx = ContextoSesion(
        org_id=UUID(args.org_id), usuario_id=UUID(args.usuario_id), rol="control_obra"
    )
    async with sesion_con_rls(ctx) as sesion:
        cargados = await cargar_programas_prototipos(
            sesion, ruta=args.archivo, dry_run=args.dry_run
        )
    if args.dry_run:
        print("(--dry-run: AplicadorProgramaBase no llamó a CrearProgramaBase; nada quedó escrito)")
    print(f"{len(cargados)} prototipo(s) con programa base dado de alta.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org-id", required=True, help="UUID de la organización destino.")
    parser.add_argument(
        "--usuario-id", required=True, help="UUID del usuario que queda como autor del alta."
    )
    parser.add_argument("--archivo", type=Path, default=_ARCHIVO_DEFAULT)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resuelve y reporta todo, pero no llama a CrearProgramaBase: no escribe nada.",
    )
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
