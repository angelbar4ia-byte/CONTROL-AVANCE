/**
 * Búsqueda en catálogos con **prioridad de CLAVE** (§3.3).
 *
 * El §3.3 es tajante: "en **todos los catálogos** la **clave es única**; las
 * descripciones varían. Todo análisis, mapeo, homologación y cruce
 * **prioriza la comparación por CLAVE**; la descripción **desempata**,
 * sugiere coincidencias o se usa cuando la clave falta".
 *
 * Aquí eso se traduce a una sola cosa: al escribir en el buscador, lo que
 * coincide por clave sale **antes** que lo que solo coincide por
 * descripción, y se marca de dónde vino la coincidencia para que el usuario
 * lo vea. No es un cruce ni una homologación —esos los hace el backend
 * (§10.3)—, es el filtro de la tabla sobre lo que el servidor ya devolvió.
 *
 * Funciones puras, fuera de los componentes (§12.11).
 */

/** Lo mínimo que necesita un registro para ser buscable: su clave (§3.3). */
export interface Buscable {
  readonly clave: string;
}

/**
 * Por qué entró un registro al resultado. El orden de la unión es el orden
 * de prioridad, de la coincidencia más fuerte a la más débil.
 */
export type Coincidencia = 'clave_exacta' | 'clave_inicio' | 'clave_parcial' | 'descripcion';

const PRIORIDAD: Record<Coincidencia, number> = {
  clave_exacta: 0,
  clave_inicio: 1,
  clave_parcial: 2,
  descripcion: 3,
};

export interface Resultado<T> {
  readonly item: T;
  readonly coincidencia: Coincidencia;
}

/**
 * Normaliza para comparar: minúsculas y sin acentos.
 *
 * Las claves son ASCII en mayúsculas (`EST-…`, `NIV-…`, §10.1), pero las
 * descripciones vienen en español y nadie escribe "cimentación" con acento
 * en un buscador. Es normalización de **texto de UI**, no de datos: los
 * sinónimos y homologaciones de verdad viven en el catálogo (§10.3).
 */
function normalizar(texto: string): string {
  return texto
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/gu, '')
    .toLowerCase()
    .trim();
}

function clasificar(clave: string, descripcion: string, aguja: string): Coincidencia | null {
  const claveNorm = normalizar(clave);
  if (claveNorm === aguja) return 'clave_exacta';
  if (claveNorm.startsWith(aguja)) return 'clave_inicio';
  if (claveNorm.includes(aguja)) return 'clave_parcial';
  if (normalizar(descripcion).includes(aguja)) return 'descripcion';
  return null;
}

/**
 * Filtra y **ordena por prioridad de clave** (§3.3).
 *
 * `descripcionDe` extrae el texto secundario del registro: `descripcion` en
 * insumos y conceptos, `nombre` en unidades y familias, `razon_social` en
 * contratistas. Sin aguja no filtra ni reordena: devuelve la lista tal como
 * la mandó el servidor.
 *
 * El orden dentro de un mismo grado de coincidencia se conserva (el
 * `sort` de ES2019 es estable), así que el criterio del servidor sigue
 * mandando entre iguales.
 */
export function buscarPorClave<T extends Buscable>(
  items: readonly T[],
  texto: string,
  descripcionDe: (item: T) => string,
): readonly Resultado<T>[] {
  const aguja = normalizar(texto);

  if (aguja === '') {
    return items.map((item) => ({ item, coincidencia: 'clave_exacta' as const }));
  }

  const encontrados: Resultado<T>[] = [];
  for (const item of items) {
    const coincidencia = clasificar(item.clave, descripcionDe(item), aguja);
    if (coincidencia !== null) encontrados.push({ item, coincidencia });
  }

  return encontrados.sort(
    (a, b) => PRIORIDAD[a.coincidencia] - PRIORIDAD[b.coincidencia],
  );
}

/** Igual que {@link buscarPorClave}, cuando solo interesan los registros. */
export function filtrarPorClave<T extends Buscable>(
  items: readonly T[],
  texto: string,
  descripcionDe: (item: T) => string,
): readonly T[] {
  return buscarPorClave(items, texto, descripcionDe).map((resultado) => resultado.item);
}

/**
 * ¿Este resultado entró **solo** por su descripción? La tabla lo marca para
 * dejar claro que la clave no coincidió — el §3.3 quiere que se note.
 */
export function soloPorDescripcion(coincidencia: Coincidencia): boolean {
  return coincidencia === 'descripcion';
}
