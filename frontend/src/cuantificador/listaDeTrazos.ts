/**
 * La pestaña «Trazos»: todos los trazos del plano, agrupados por el concepto al que alimentan.
 * Puro: recibe los trazos y los nombres ya resueltos y devuelve filas listas para pintar.
 *
 * La cantidad que se escribe es la del enlace vigente que sirvió para agrupar (la que calcula el
 * servidor); un trazo sin enlace no tiene cantidad y va al grupo «Sin enlace».
 */

import type { TrazoFeature } from '@/api/generado/modelo';
import { fmtNum } from '@/lib/formato';
import { etiquetaMedida } from './reglas';

export interface FilaDeTrazo {
  readonly id: string;
  readonly titulo: string;
  readonly subtitulo: string;
  readonly cantidad: string | null;
  readonly color: string | undefined;
}

export interface GrupoDeTrazos {
  /** El nodo del concepto, o `null` en el grupo «Sin enlace». */
  readonly claveDeGrupo: string | null;
  readonly nombre: string;
  readonly trazos: readonly FilaDeTrazo[];
}

export interface OpcionesDeLista {
  /** Nombre legible del nodo de un enlace (actividad o nodo de prototipo). */
  readonly nombreDeNodo: (tipo: string, id: string) => string;
  /** Nombre de una medición por su id, o `undefined` si no se conoce. */
  readonly nombreDeMedicion: (id: string) => string | undefined;
  readonly colorDe: (trazo: TrazoFeature) => string | undefined;
  readonly busqueda?: string;
}

const NOMBRE_DE_GEOMETRIA: Readonly<Record<string, string>> = {
  Polygon: 'Área',
  MultiPolygon: 'Área',
  LineString: 'Línea',
  MultiLineString: 'Línea',
  Point: 'Punto',
  MultiPoint: 'Punto',
};

export const SIN_ENLACE = 'Sin enlace';

function tipoDeTrazo(trazo: TrazoFeature): string {
  const tipo = (trazo.geometry as { type?: string }).type ?? '';
  const base = NOMBRE_DE_GEOMETRIA[tipo] ?? 'Trazo';
  // Una línea con grosor es un muro; un punto con forma lleva el nombre de su plantilla.
  if (base === 'Línea' && trazo.properties.grosor_m != null) return 'Muro';
  return base;
}

function tituloDe(trazo: TrazoFeature): string {
  const forma = trazo.properties.forma;
  const nombreDeForma = forma && typeof forma === 'object' ? (forma as { nombre?: string | null }).nombre : null;
  return nombreDeForma ?? trazo.properties.capa ?? `${tipoDeTrazo(trazo)} ${trazo.id.slice(0, 4)}`;
}

/** El enlace vigente que sirve para agrupar: el que apunta a un concepto, no a un nodo de prototipo. */
function enlaceDeGrupo(trazo: TrazoFeature) {
  const vigentes = trazo.properties.enlaces.filter((e) => e.vigente);
  return vigentes.find((e) => e.tipo_nodo !== 'prototipo_nodo') ?? vigentes[0] ?? null;
}

export function agruparTrazos(
  trazos: readonly TrazoFeature[],
  opciones: OpcionesDeLista,
): readonly GrupoDeTrazos[] {
  const consulta = (opciones.busqueda ?? '').trim().toLowerCase();
  const grupos = new Map<string | null, { nombre: string; trazos: FilaDeTrazo[] }>();

  for (const trazo of trazos) {
    const enlace = enlaceDeGrupo(trazo);
    const concepto = enlace ? opciones.nombreDeNodo(enlace.tipo_nodo, enlace.nodo_id) : SIN_ENLACE;
    const medicionId = trazo.properties.medicion_id;
    const medicion = medicionId ? opciones.nombreDeMedicion(medicionId) : undefined;
    const tipo = tipoDeTrazo(trazo);
    const titulo = tituloDe(trazo);

    const textoBuscable = [titulo, tipo, concepto, medicion].filter(Boolean).join(' ').toLowerCase();
    if (consulta !== '' && !textoBuscable.includes(consulta)) continue;

    const nHuecos = trazo.properties.n_huecos ?? 0;
    const subtitulo = [tipo, medicion, nHuecos > 0 ? `${nHuecos} ${nHuecos === 1 ? 'hueco' : 'huecos'}` : null]
      .filter(Boolean)
      .join(' · ');

    const fila: FilaDeTrazo = {
      id: trazo.id,
      titulo,
      subtitulo,
      cantidad: enlace ? `${fmtNum(enlace.cantidad)} · ${etiquetaMedida(enlace.medida)}` : null,
      color: opciones.colorDe(trazo),
    };

    const clave = enlace ? `${enlace.tipo_nodo}:${enlace.nodo_id}` : null;
    const grupo = grupos.get(clave) ?? { nombre: concepto, trazos: [] };
    grupo.trazos.push(fila);
    grupos.set(clave, grupo);
  }

  // «Sin enlace» al final: lo que ya suma va primero.
  return [...grupos.entries()]
    .map(([claveDeGrupo, g]) => ({ claveDeGrupo, nombre: g.nombre, trazos: g.trazos }))
    .sort((a, b) => (a.claveDeGrupo === null ? 1 : 0) - (b.claveDeGrupo === null ? 1 : 0));
}
