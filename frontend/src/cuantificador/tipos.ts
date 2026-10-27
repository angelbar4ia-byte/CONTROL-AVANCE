/**
 * El tipo de medición de un concepto, y con él qué herramientas le tocan.
 *
 * El concepto manda: su unidad (m², m, pza…) dice si se mide con un **área**, una **longitud** o un
 * **conteo**. Un m³ se mide con un área y un espesor (la calculadora de volumen); un kg o una
 * tonelada se **derivan** de otra medición (el conteo de castillos × su peso). Lo demás no se
 * deduce: la barra sigue completa y no resalta nada.
 *
 * Funciones puras, sin DOM ni React.
 */

export type TipoDeMedicion = 'area' | 'lineal' | 'conteo' | 'volumen' | 'derivada';

/** El bloque de la barra que se resalta: el volumen se mide con un área. */
export type BloqueDeMedicion = 'area' | 'lineal' | 'conteo';

export const NOMBRE_DE_TIPO: Readonly<Record<TipoDeMedicion, string>> = {
  area: 'Área',
  lineal: 'Lineal',
  conteo: 'Conteo',
  volumen: 'Volumen',
  derivada: 'Derivada',
};

const AREA = new Set(['m2', 'mt2', 'mts2', 'metro2', 'metros2', 'metrocuadrado', 'metroscuadrados']);
const LINEAL = new Set(['m', 'ml', 'mt', 'mts', 'metro', 'metros', 'metrolineal', 'metroslineales', 'mlineal']);
const VOLUMEN = new Set(['m3', 'mt3', 'mts3', 'metro3', 'metros3', 'metrocubico', 'metroscubicos']);
const CONTEO = new Set([
  'pza', 'pzas', 'pz', 'pzs', 'pieza', 'piezas', 'lote', 'lotes', 'jgo', 'jgos', 'juego', 'juegos',
  'salida', 'salidas', 'par', 'pares', 'u', 'un', 'ud', 'uds', 'unidad', 'unidades', 'punto', 'puntos',
]);
const DERIVADA = new Set([
  'kg', 'kgs', 'kilo', 'kilos', 'kilogramo', 'kilogramos', 'ton', 'tons', 't', 'tonelada', 'toneladas',
  'lt', 'lts', 'l', 'litro', 'litros', 'bulto', 'bultos', 'saco', 'sacos', 'galon', 'galones',
]);

function normalizar(unidad: string): string {
  return unidad
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/²/g, '2')
    .replace(/³/g, '3')
    .replace(/[.\s]/g, '');
}

/** El tipo de medición que pide una unidad, o `null` si no se puede deducir. */
export function tipoDeMedicion(unidad: string | null | undefined): TipoDeMedicion | null {
  if (!unidad) return null;
  const u = normalizar(unidad);
  if (AREA.has(u)) return 'area';
  if (LINEAL.has(u)) return 'lineal';
  if (VOLUMEN.has(u)) return 'volumen';
  if (CONTEO.has(u)) return 'conteo';
  if (DERIVADA.has(u)) return 'derivada';
  return null;
}

/** Qué bloque de herramientas resalta un tipo: el volumen se mide con áreas; lo derivado, con ninguno. */
export function bloqueDeTipo(tipo: TipoDeMedicion | null): BloqueDeMedicion | null {
  if (tipo === 'area' || tipo === 'volumen') return 'area';
  if (tipo === 'lineal') return 'lineal';
  if (tipo === 'conteo') return 'conteo';
  return null;
}
