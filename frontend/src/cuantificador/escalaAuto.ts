/**
 * Escala automática (Fase 2): proponer la escala de un plano en PDF a partir del texto de su hoja
 * («ESC. 1:50», «ESCALA 1/100»…). **Solo propone:** el error de escala arrastra todas las cantidades,
 * así que nunca se aplica sola; la confirma una persona.
 *
 * El cálculo vale para un PDF a su tamaño de impresión: un punto de PDF mide 1/72 de pulgada de papel,
 * así que con escala 1:N un punto son `0.0254 / 72 × N` metros reales, y una unidad de plano
 * (1 / `ESCALA_PDF` puntos) la parte que le toca. Si el PDF se exportó «ajustado a la hoja», el cuadro
 * de título miente: por eso se muestra cuánto cubriría la hoja, para que alguien lo juzgue.
 *
 * Funciones puras, sin DOM ni React.
 */

const METROS_POR_PUNTO_DE_PAPEL = 0.0254 / 72;

export interface CandidatoDeEscala {
  readonly denominador: number;
  /** El texto de la hoja del que salió. */
  readonly texto: string;
  /** Dice «escala» expresamente: es más fiable que un 1:N suelto (una relación de aspecto, un nivel). */
  readonly rotulada: boolean;
  /** Cuántas veces aparece en la hoja. */
  readonly veces: number;
}

const ROTULADA = /esc(?:ala|\.)?\s*[:=]?\s*1\s*[:/]\s*(\d{1,4})(?!\d)/gi;
const SUELTA = /(?<![\d.,])1\s*:\s*(\d{1,4})(?![\d.,:])/g;

/** Un denominador de escala de arquitectura o ingeniería creíble (1:1 a 1:5000). */
const creible = (n: number): boolean => Number.isInteger(n) && n >= 2 && n <= 5000;

/**
 * Los candidatos que el texto de la hoja sugiere, los más fiables primero: los que dicen «escala»,
 * luego los más repetidos, luego los de denominador menor.
 */
export function candidatosDeEscala(textos: readonly string[]): CandidatoDeEscala[] {
  const unido = textos.join(' ').replace(/\s+/g, ' ');
  const acumulado = new Map<number, { texto: string; rotulada: boolean; veces: number }>();
  const sumar = (denominador: number, texto: string, rotulada: boolean) => {
    if (!creible(denominador)) return;
    const previo = acumulado.get(denominador);
    acumulado.set(denominador, {
      texto: previo && previo.rotulada && !rotulada ? previo.texto : texto,
      rotulada: (previo?.rotulada ?? false) || rotulada,
      veces: (previo?.veces ?? 0) + 1,
    });
  };
  for (const m of unido.matchAll(ROTULADA)) sumar(Number(m[1]), m[0].trim(), true);
  const sinRotuladas = unido.replace(ROTULADA, ' ');
  for (const m of sinRotuladas.matchAll(SUELTA)) sumar(Number(m[1]), m[0].trim(), false);
  return [...acumulado.entries()]
    .map(([denominador, v]) => ({ denominador, ...v }))
    .sort((a, b) => Number(b.rotulada) - Number(a.rotulada) || b.veces - a.veces || a.denominador - b.denominador);
}

/** Metros reales por unidad de plano de un PDF a su tamaño de impresión, con escala 1:`denominador`. */
export function metrosPorUnidad(denominador: number, escalaDelPdf: number): number {
  return (METROS_POR_PUNTO_DE_PAPEL * denominador) / escalaDelPdf;
}

/** Cuánto cubre en la realidad una hoja de `anchoPt` × `altoPt` puntos con esa escala, en metros. */
export function coberturaDeLaHoja(anchoPt: number, altoPt: number, denominador: number): { ancho: number; alto: number } {
  const porPunto = METROS_POR_PUNTO_DE_PAPEL * denominador;
  return { ancho: anchoPt * porPunto, alto: altoPt * porPunto };
}
