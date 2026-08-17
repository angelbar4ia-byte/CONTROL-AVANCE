/**
 * Filas del Gantt: **mapeo de presentación** de lo que devolvió la API.
 *
 * El contrato entrega el cronograma por dos puertas distintas (§11.2):
 *
 *   - `GET /obras/{id}/programa` → `ActividadProgramadaRespuesta`, con la
 *     programación capturada (`fecha_inicio`, `fecha_termino`), el frente, la
 *     etapa y el nivel. Es (C, S).
 *   - `GET /obras/{id}/ruta-critica` → `ActividadEnRutaRespuesta`, con lo que
 *     derivó el motor CPM: `inicio_temprano`/`fin_temprano`,
 *     `inicio_tardio`/`fin_tardio`, `holgura`, `desfase` y `es_critica`. Es
 *     de **todos los roles**.
 *
 * Las dos traen la misma actividad vista desde distinto lado, así que el
 * Gantt trabaja contra una `FilaGantt` única y aquí se normalizan. **Nada se
 * calcula**: `es_critica`, `holgura` y `desfase` llegan resueltos del motor
 * (`domain/programacion/cpm.py`, §6) y esta capa solo los cambia de forma —
 * los decimales del contrato viajan como cadena y aquí se vuelven número
 * para poder pintarlos.
 *
 * Cuando el rol puede leer las dos, las filas se **fusionan**: la base es el
 * programa (que es quien sabe de etapa y nivel) y la ruta aporta las fechas
 * calculadas de las actividades que aún no tienen programación capturada.
 */

import type {
  ActividadEnRutaRespuesta,
  ActividadProgramadaRespuesta,
  DependenciaDTO,
  FrenteRespuesta,
  ProgramaObraRespuesta,
  RutaCriticaRespuesta,
} from '@/api/generado/modelo';

export interface FilaGantt {
  readonly actividadId: string;
  readonly descripcion: string;
  readonly frenteId: string | null;
  /** Solo lo trae el programa; la ruta crítica no expone etapa. */
  readonly etapaId: string | null;
  readonly nivelId: string | null;
  /** `YYYY-MM-DD` o `null` si la actividad todavía no tiene fechas. */
  readonly inicio: string | null;
  readonly fin: string | null;
  /** De dónde salieron las fechas de la barra. */
  readonly origenFechas: 'programa' | 'cpm' | 'sin_fecha';
  readonly duracionDias: number;
  readonly holguraDias: number | null;
  readonly desfaseDias: number | null;
  readonly esCritica: boolean;
  readonly bloqueada: boolean;
  /** 0–100 como lo guarda la BD (§7.6). */
  readonly avancePct: number;
  /** `null` cuando la fila vino solo de la ruta crítica, que no trae estatus. */
  readonly estatus: string | null;
  readonly dependencias: readonly DependenciaDTO[];
  /** Fechas límite del motor; solo existen si la ruta crítica alimentó la fila. */
  readonly inicioTardio: string | null;
  readonly finTardio: string | null;
}

/** Decimal del contrato (cadena) → número; `null` si no viene o no es finito. */
function aNumero(valor: string | number | null | undefined): number | null {
  if (valor === null || valor === undefined || valor === '') return null;
  const n = typeof valor === 'string' ? Number(valor) : valor;
  return Number.isFinite(n) ? n : null;
}

function filaDePrograma(actividad: ActividadProgramadaRespuesta): FilaGantt {
  const tieneFechas = actividad.fecha_inicio !== null && actividad.fecha_termino !== null;
  return {
    actividadId: actividad.id,
    descripcion: actividad.descripcion ?? actividad.id,
    frenteId: actividad.frente_id ?? null,
    etapaId: actividad.etapa_id ?? null,
    nivelId: actividad.nivel_id ?? null,
    inicio: actividad.fecha_inicio ?? null,
    fin: actividad.fecha_termino ?? null,
    origenFechas: tieneFechas ? 'programa' : 'sin_fecha',
    duracionDias: aNumero(actividad.duracion_dias) ?? 0,
    holguraDias: aNumero(actividad.holgura),
    desfaseDias: aNumero(actividad.desfase),
    esCritica: actividad.es_critica,
    bloqueada: actividad.bloqueada,
    avancePct: aNumero(actividad.avance_pct) ?? 0,
    estatus: actividad.estatus,
    dependencias: actividad.dependencias,
    inicioTardio: null,
    finTardio: null,
  };
}

function filaDeRuta(actividad: ActividadEnRutaRespuesta): FilaGantt {
  return {
    actividadId: actividad.actividad_id,
    descripcion: actividad.descripcion ?? actividad.actividad_id,
    frenteId: actividad.frente_id ?? null,
    etapaId: null,
    nivelId: null,
    inicio: actividad.inicio_temprano,
    fin: actividad.fin_temprano,
    origenFechas: 'cpm',
    duracionDias: aNumero(actividad.duracion_dias) ?? 0,
    holguraDias: actividad.holgura,
    desfaseDias: actividad.desfase,
    esCritica: actividad.es_critica,
    bloqueada: actividad.bloqueada,
    avancePct: aNumero(actividad.avance_pct) ?? 0,
    estatus: null,
    dependencias: actividad.dependencias,
    inicioTardio: actividad.inicio_tardio,
    finTardio: actividad.fin_tardio,
  };
}

/**
 * Filas del Gantt a partir de lo que el rol pudo pedir.
 *
 * - Solo ruta (Residente, Super intendente) → las fechas tempranas del motor.
 * - Solo programa → la programación capturada.
 * - Las dos (Supervisor, Control de obra) → el programa manda, y de la ruta
 *   se toman las fechas de las actividades sin programación y siempre las
 *   fechas tardías, que el programa no expone.
 */
export function construirFilas(
  programa: ProgramaObraRespuesta | null | undefined,
  ruta: RutaCriticaRespuesta | null | undefined,
): readonly FilaGantt[] {
  const deRuta = new Map<string, FilaGantt>();
  for (const actividad of ruta?.actividades ?? []) {
    deRuta.set(actividad.actividad_id, filaDeRuta(actividad));
  }

  if (!programa) return [...deRuta.values()];

  const filas: FilaGantt[] = [];
  for (const actividad of programa.actividades) {
    const base = filaDePrograma(actividad);
    const calculada = deRuta.get(base.actividadId);
    deRuta.delete(base.actividadId);

    if (!calculada) {
      filas.push(base);
      continue;
    }

    filas.push({
      ...base,
      inicio: base.inicio ?? calculada.inicio,
      fin: base.fin ?? calculada.fin,
      origenFechas: base.origenFechas === 'programa' ? 'programa' : calculada.origenFechas,
      holguraDias: base.holguraDias ?? calculada.holguraDias,
      desfaseDias: base.desfaseDias ?? calculada.desfaseDias,
      inicioTardio: calculada.inicioTardio,
      finTardio: calculada.finTardio,
    });
  }

  // Lo que el motor conoce y el programa no devolvió no se descarta: es una
  // actividad real de la obra y esconderla dejaría un Gantt incompleto.
  filas.push(...deRuta.values());
  return filas;
}

export interface GrupoGantt {
  readonly clave: string;
  readonly titulo: string;
  readonly filas: readonly FilaGantt[];
  /** Cuántas de sus filas están en la ruta crítica (§6). */
  readonly nCriticas: number;
}

const SIN_FRENTE = '__sin_frente__';

/**
 * Agrupa por **frente**, y dentro del título se antepone la **etapa** que el
 * catálogo de frentes ya trae (`FrenteRespuesta.etapa`, §8.3).
 *
 * Se agrupa por frente y no por `etapa_id` de la actividad porque `etapa_id`
 * solo viaja en `GET /obras/{id}/programa` —que Residente y Super intendente
 * no pueden pedir (§11.2)— y el contrato no expone un catálogo de etapas con
 * el que resolver su nombre. El frente sí lo traen las dos respuestas y
 * `GET /frentes` es de todos los roles.
 *
 * El orden de los grupos es el `orden` del catálogo (§8.3); las filas dentro
 * de cada grupo conservan el orden en que llegaron del servidor.
 */
export function agruparPorFrente(
  filas: readonly FilaGantt[],
  frentes: readonly FrenteRespuesta[],
): readonly GrupoGantt[] {
  const porId = new Map(frentes.map((frente) => [frente.id, frente]));
  const agrupadas = new Map<string, FilaGantt[]>();

  for (const fila of filas) {
    const clave = fila.frenteId ?? SIN_FRENTE;
    const lista = agrupadas.get(clave);
    if (lista) lista.push(fila);
    else agrupadas.set(clave, [fila]);
  }

  const grupos: GrupoGantt[] = [];
  for (const [clave, delGrupo] of agrupadas) {
    grupos.push({
      clave,
      titulo: tituloDeGrupo(clave, porId.get(clave)),
      filas: delGrupo,
      nCriticas: delGrupo.filter((fila) => fila.esCritica).length,
    });
  }

  grupos.sort((a, b) => ordenDe(a.clave, porId) - ordenDe(b.clave, porId));
  return grupos;
}

function tituloDeGrupo(clave: string, frente: FrenteRespuesta | undefined): string {
  if (clave === SIN_FRENTE) return 'Sin frente asignado';
  if (!frente) return clave;
  const etapa = frente.etapa ?? null;
  return etapa === null ? `${frente.clave} · ${frente.nombre}` : `${etapa} · ${frente.nombre}`;
}

/** Frentes desconocidos y el cajón "sin frente" van al final, en ese orden. */
function ordenDe(clave: string, porId: ReadonlyMap<string, FrenteRespuesta>): number {
  if (clave === SIN_FRENTE) return Number.MAX_SAFE_INTEGER;
  const frente = porId.get(clave);
  if (!frente) return Number.MAX_SAFE_INTEGER - 1;
  return frente.orden ?? 0;
}

/** Filtro de UI por texto sobre la descripción, sobre lo que ya llegó. */
export function filtrarPorTexto(
  filas: readonly FilaGantt[],
  texto: string,
): readonly FilaGantt[] {
  const aguja = texto.trim().toLowerCase();
  if (aguja === '') return filas;
  return filas.filter((fila) => fila.descripcion.toLowerCase().includes(aguja));
}

/** Solo las actividades que el motor marcó como críticas (§6). */
export function soloCriticas(filas: readonly FilaGantt[]): readonly FilaGantt[] {
  return filas.filter((fila) => fila.esCritica);
}

export interface ResumenPrograma {
  readonly nActividades: number;
  readonly nCriticas: number;
  readonly nConDesfase: number;
  readonly nSinFecha: number;
}

/**
 * Conteos para el encabezado. Son cuentas de lo ya recibido, no métricas
 * derivadas: el spec no define un agregado de obra sobre la ruta crítica y
 * aquí no se inventa uno.
 */
export function resumirPrograma(filas: readonly FilaGantt[]): ResumenPrograma {
  let nCriticas = 0;
  let nConDesfase = 0;
  let nSinFecha = 0;

  for (const fila of filas) {
    if (fila.esCritica) nCriticas += 1;
    if (fila.desfaseDias !== null && fila.desfaseDias > 0) nConDesfase += 1;
    if (fila.inicio === null || fila.fin === null) nSinFecha += 1;
  }

  return { nActividades: filas.length, nCriticas, nConDesfase, nSinFecha };
}
