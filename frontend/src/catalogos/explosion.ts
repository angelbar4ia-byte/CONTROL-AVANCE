/**
 * Armado del árbol de la explosión y lectura del estado del CPU (§7.3, §10.8).
 *
 * `GET /conceptos/{id}/explosion` devuelve las líneas **aplanadas** en
 * recorrido padre-antes-que-hijos, cada una con su `ruta` (el camino de
 * claves hasta su padre) y su `nivel` (`= ruta.length`). El §7.3 dice que un
 * concepto anida insumos **y otros conceptos** (auxiliares y matrices), así
 * que para pintarlo hay que volver a anidarlo.
 *
 * Todo lo de aquí es **estructura de presentación**, no costeo: ninguna
 * función suma, multiplica ni decide qué es destajo. Los importes, el
 * `es_destajo` por línea y el `PrecioUnitario` (total · destajo ·
 * materiales) los calcula el dominio (`domain/catalogos/apu.py`) y llegan
 * ya resueltos en la respuesta. Vive fuera de los componentes por la regla
 * del §12.11 y para poder fijarlo con pruebas.
 */

import type { CPURespuesta, LineaExplosionRespuesta } from '@/api/generado/modelo';

export interface NodoExplosion {
  readonly linea: LineaExplosionRespuesta;
  /** Componentes del auxiliar/matriz; vacío en las hojas (insumos). */
  readonly hijos: readonly NodoExplosion[];
}

interface NodoMutable {
  readonly linea: LineaExplosionRespuesta;
  readonly hijos: NodoMutable[];
}

/**
 * Reconstruye el árbol a partir de las líneas planas.
 *
 * Las líneas del primer nivel traen `nivel === 1` (su `ruta` es solo la
 * clave del concepto raíz); un componente que cuelga de un auxiliar trae
 * `nivel === 2`, y así. Como el recorrido es padre-antes-que-hijos, basta
 * una pila: el padre de una línea de nivel `n` es la última línea vista de
 * nivel `n - 1`.
 *
 * Si llegara una línea con un nivel que se salta un escalón —contrato roto o
 * respuesta truncada—, se cuelga de la raíz en vez de perderse: mejor
 * mostrarla suelta que desaparecer un costo de la vista.
 */
export function armarArbolExplosion(
  lineas: readonly LineaExplosionRespuesta[],
): readonly NodoExplosion[] {
  const raices: NodoMutable[] = [];
  const pila: NodoMutable[] = [];

  for (const linea of lineas) {
    const nodo: NodoMutable = { linea, hijos: [] };
    const profundidad = Math.max(1, linea.nivel);

    pila.length = Math.min(pila.length, profundidad - 1);

    const padre = pila.length === profundidad - 1 ? pila[profundidad - 2] : undefined;
    if (padre) padre.hijos.push(nodo);
    else raices.push(nodo);

    pila[profundidad - 1] = nodo;
    pila.length = profundidad;
  }

  return raices;
}

/** Cuántas líneas tiene el árbol, contando las anidadas. */
export function contarLineas(nodos: readonly NodoExplosion[]): number {
  return nodos.reduce((total, nodo) => total + 1 + contarLineas(nodo.hijos), 0);
}

/**
 * Estado de la versión vigente del CPU frente al catálogo de hoy (§10.8).
 *
 * - `sin_vigente` — el concepto todavía no tiene ninguna versión publicada.
 * - `al_dia` — lo publicado coincide con lo que da la explosión de hoy.
 * - `desfasado` — no coinciden: el catálogo cambió después de publicar.
 *
 * No recalcula nada. El backend ya manda las dos cifras —`vigente.precio` y
 * `calculado`— y su propia documentación dice qué significa que difieran:
 * "CPU recalculado desde la explosión de hoy. Si difiere del vigente, el
 * catálogo cambió y toca publicar una versión nueva (§10.8)". Esto solo las
 * compara para poder avisarlo en la UI.
 */
export type EstadoCPU = 'sin_vigente' | 'al_dia' | 'desfasado';

export function estadoCPU(cpu: CPURespuesta): EstadoCPU {
  const vigente = cpu.vigente;
  if (vigente === null || vigente === undefined) return 'sin_vigente';

  const igualTotal = mismoImporte(vigente.precio.total, cpu.calculado.total);
  const igualDestajo = mismoImporte(vigente.precio.destajo, cpu.calculado.destajo);

  return igualTotal && igualDestajo ? 'al_dia' : 'desfasado';
}

/**
 * Compara dos importes que vienen como cadena decimal.
 *
 * Postgres serializa `numeric` con la escala de la columna, así que el mismo
 * importe puede llegar como `"120.00"` y como `"120"` según de dónde salga
 * (la versión guardada o el cálculo del dominio). Comparar las cadenas
 * marcaría un falso desfase; se comparan como números, que es lo que el
 * usuario ve en pantalla.
 */
function mismoImporte(a: string, b: string): boolean {
  const na = Number(a);
  const nb = Number(b);
  if (!Number.isFinite(na) || !Number.isFinite(nb)) return a === b;
  return na === nb;
}

const NOTA_ESTADO_CPU: Record<EstadoCPU, string> = {
  sin_vigente:
    'Este concepto no tiene CPU publicado: las actividades que lo usen no tienen precio vigente (§7.3).',
  al_dia: 'La versión vigente coincide con la explosión de hoy.',
  desfasado:
    'El catálogo cambió desde que se publicó: la explosión de hoy da otro precio. Publica una versión nueva (§10.8).',
};

export function notaEstadoCPU(estado: EstadoCPU): string {
  return NOTA_ESTADO_CPU[estado];
}

/**
 * Variantes (recetas alternas) que aparecen en el historial, sin repetir.
 *
 * El §10.1 lista "Variantes/recetas de CPU" como catálogo propio: un mismo
 * concepto puede tener composiciones distintas. `null` (receta base) queda
 * fuera de la lista; es el valor por omisión del selector.
 */
export function variantesDelHistorial(cpu: CPURespuesta): readonly string[] {
  const vistas = new Set<string>();
  for (const version of cpu.historial) {
    const variante = version.variante;
    if (variante !== null && variante !== undefined && variante !== '') {
      vistas.add(variante);
    }
  }
  return [...vistas];
}
