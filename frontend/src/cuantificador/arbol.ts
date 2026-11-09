/**
 * El árbol del cuantificador es el del presupuesto: nivel → etapa → concepto (cerebro
 * WORKFLOWS.md §8.9, escenario «Nuevo», D-565).
 *
 * Antes la cuantificación era una lista de lo ya enlazado: no decía qué faltaba. El árbol trae
 * **todas** las actividades de la obra, medidas o no, con la misma forma con que se revisa el
 * presupuesto, y cuenta cuántos conceptos van medidos en cada rama. Las hojas son conceptos.
 */

import type { ActividadRespuesta, NodoCuantificadoRespuesta } from '@/api/generado/modelo';

export interface HojaDelArbol {
  readonly id: string;
  readonly etiqueta: string;
  /** Clave y descripción corta, para mostrar en una fila; la completa va en `etiqueta` (búsqueda y ayuda). */
  readonly corta: string;
  readonly base: string;
  readonly medida: string | null;
  readonly diferencia: string | null;
  /** Tiene al menos un enlace vigente: alguien ya lo midió. */
  readonly medido: boolean;
  readonly porRevisar: number;
}

export interface EtapaDelArbol {
  readonly clave: string;
  readonly etiqueta: string;
  readonly hojas: readonly HojaDelArbol[];
  readonly medidas: number;
}

export interface NivelDelArbol {
  readonly clave: string;
  readonly etiqueta: string;
  readonly etapas: readonly EtapaDelArbol[];
  readonly medidas: number;
  readonly total: number;
}

const SIN_NIVEL = '~sin-nivel';
const SIN_ETAPA = '~sin-etapa';

function porClave(a: string, b: string): number {
  // Lo suelto (sin nivel o sin etapa) va al final.
  if (a.startsWith('~') !== b.startsWith('~')) return a.startsWith('~') ? 1 : -1;
  return a.localeCompare(b, 'es', { numeric: true });
}

export function arbolDeCuantificacion(
  actividades: readonly ActividadRespuesta[],
  estado: readonly NodoCuantificadoRespuesta[],
): readonly NivelDelArbol[] {
  const medidoPorActividad = new Map(
    estado.filter((n) => n.tipo_nodo === 'actividad').map((n) => [n.nodo_id, n]),
  );

  const niveles = new Map<
    string,
    { etiqueta: string; etapas: Map<string, { etiqueta: string; hojas: HojaDelArbol[] }> }
  >();
  for (const a of actividades) {
    const nivelClave = a.nivel_clave ?? SIN_NIVEL;
    const etapaClave = a.etapa_clave ?? SIN_ETAPA;
    const nivel = niveles.get(nivelClave) ?? {
      etiqueta: a.nivel_clave
        ? [a.nivel_clave, a.nivel_descripcion].filter(Boolean).join(' · ')
        : 'Sin nivel',
      etapas: new Map(),
    };
    niveles.set(nivelClave, nivel);
    const etapa = nivel.etapas.get(etapaClave) ?? {
      etiqueta: a.etapa_clave
        ? [a.etapa_clave, a.etapa_descripcion].filter(Boolean).join(' · ')
        : 'Sin etapa',
      hojas: [],
    };
    nivel.etapas.set(etapaClave, etapa);

    const nodo = medidoPorActividad.get(a.id);
    etapa.hojas.push({
      id: a.id,
      etiqueta: [a.concepto_clave, a.descripcion].filter(Boolean).join(' · ') || 'Actividad',
      // El nombre breve del catálogo (columna «Descripción corta»); sin él, la descripción completa recortada.
      corta:
        [a.concepto_clave, a.concepto_descripcion_corta?.trim() || descripcionCorta(a.descripcion)].filter(Boolean).join(' · ') ||
        'Actividad',
      base: a.cant_base,
      medida: nodo ? nodo.cantidad_medida : null,
      diferencia: nodo ? (nodo.diferencia ?? null) : null,
      medido: (nodo?.enlaces_vigentes ?? 0) > 0,
      porRevisar: nodo?.trazos_por_revisar ?? 0,
    });
  }

  return [...niveles.entries()]
    .sort(([a], [b]) => porClave(a, b))
    .map(([clave, nivel]) => {
      const etapas = [...nivel.etapas.entries()]
        .sort(([a], [b]) => porClave(a, b))
        .map(([c, e]) => ({
          clave: c,
          etiqueta: e.etiqueta,
          hojas: [...e.hojas].sort((x, y) => x.etiqueta.localeCompare(y.etiqueta, 'es', { numeric: true })),
          medidas: e.hojas.filter((h) => h.medido).length,
        }));
      return {
        clave,
        etiqueta: nivel.etiqueta,
        etapas,
        medidas: etapas.reduce((s, e) => s + e.medidas, 0),
        total: etapas.reduce((s, e) => s + e.hojas.length, 0),
      };
    });
}

/** Lo mínimo que se necesita de un trazo para saber a qué conceptos alimenta. */
export interface TrazoConEnlaces {
  readonly id: string;
  readonly properties: {
    readonly enlaces: readonly {
      readonly tipo_nodo: string;
      readonly nodo_id: string;
      readonly vigente: boolean;
    }[];
  };
}

/**
 * Los trazos que alimentan alguno de los conceptos elegidos (herramienta «Solo
 * trazos de los conceptos elegidos»). Cuenta solo el enlace **vigente** a una
 * actividad: un enlace reemplazado queda como evidencia y ya no suma.
 */
export function trazosDeConceptos<T extends TrazoConEnlaces>(
  trazos: readonly T[],
  conceptos: ReadonlySet<string>,
): readonly T[] {
  return trazos.filter((t) =>
    t.properties.enlaces.some(
      (e) => e.vigente && e.tipo_nodo === 'actividad' && conceptos.has(e.nodo_id),
    ),
  );
}

/** Los ids de todas las hojas bajo una rama, para elegir una carpeta completa. */
export function idsDeNivel(nivel: NivelDelArbol): readonly string[] {
  return nivel.etapas.flatMap((e) => e.hojas.map((h) => h.id));
}

export function idsDeEtapa(etapa: EtapaDelArbol): readonly string[] {
  return etapa.hojas.map((h) => h.id);
}

/**
 * La descripción de un concepto de OPUS puede ocupar tres renglones; en una fila del árbol se muestra corta. Se
 * corta en el último espacio antes de `maximo` y se le pone «…»; la completa queda en la ayuda de la fila.
 */
export function descripcionCorta(texto: string | null | undefined, maximo = 48): string {
  const limpio = (texto ?? '').replace(/\s+/g, ' ').trim();
  if (limpio.length <= maximo) return limpio;
  const corte = limpio.lastIndexOf(' ', maximo);
  return `${limpio.slice(0, corte > maximo * 0.5 ? corte : maximo).trimEnd()}…`;
}

/**
 * Cambia de lugar un elemento entre sus hermanos: devuelve el `orden` (1, 2, 3…) que le toca a cada uno **solo si
 * algo cambia**. `dir`: `up` lo sube un lugar, `down` lo baja. `null` si ya está en el extremo.
 */
export function reordenar(ids: readonly string[], id: string, dir: 'up' | 'down'): ReadonlyMap<string, number> | null {
  const i = ids.indexOf(id);
  const j = dir === 'up' ? i - 1 : i + 1;
  if (i === -1 || j < 0 || j >= ids.length) return null;
  const nuevo = [...ids];
  [nuevo[i], nuevo[j]] = [nuevo[j] as string, nuevo[i] as string];
  return new Map(nuevo.map((x, k) => [x, k + 1]));
}
