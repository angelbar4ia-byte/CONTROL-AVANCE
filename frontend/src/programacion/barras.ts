/**
 * Presentación de una barra del Gantt: estilo, color y etiqueta (§7.5, §12.10).
 *
 * ## Por qué esto no vive dentro del componente
 *
 * Porque son tres decisiones con reglas, no tres `className` sueltos. Cuál
 * color le toca a una barra depende de tres criterios excluyentes que el
 * usuario elige; qué dice su etiqueta depende de seis campos combinables y de
 * dónde salen sus cifras; y el estilo tiene que poder convivir con los otros
 * dos sin que una barra crítica en modo contorno se quede sin decir que es
 * crítica. Todo eso se prueba sin montar nada (§12.11), y es lo que hace que el
 * componente se limite a pintar lo que se le diga.
 *
 * ## La criticidad no comunica sólo por color
 *
 * En paleta monocromática la barra crítica se distingue por **trama** —un rayado
 * diagonal— y no por tono. No es una concesión estética: un Gantt de obra se
 * imprime, se fotocopia y se mira en un teléfono al sol, y alrededor de un ocho
 * por ciento de los hombres no distingue rojo de verde. Una cadena crítica que
 * sólo existe en el canal del color desaparece en los tres casos. La trama
 * sobrevive a los tres, y por eso en modo mono se enciende siempre.
 *
 * ## Los frentes se colorean por posición, no por identidad
 *
 * `frente_id` es un UUID y no tiene color propio en ningún catálogo. Se les
 * reparten los seis tonos de la paleta en el orden en que aparecen en el árbol,
 * que es estable dentro de una sesión y se explica en la leyenda. Inventarle un
 * color derivado del UUID —un hash de tono— daría colores que nadie eligió y
 * que cambiarían al reasignar un frente.
 *
 * Módulo puro (§12.11).
 */

import { fmtMXN, fmtNum } from '@/lib/formato';

import { etiquetaDeDia, type EjePrograma } from './ejePrograma';
import type { FilaPrograma } from './filasPrograma';
import type { MagnitudesFila } from './reparto';
import { CAMPOS_ETIQUETA, type CampoEtiqueta, type VistaGantt } from './vistaGantt';

/** Tonos de frente que define la hoja (`--prog-frente-1` … `-6`). */
export const TONOS_DE_FRENTE = 6;

/**
 * Índice de tono de cada frente, 1-based, en el orden en que los frentes
 * aparecen en el árbol. Un frente más allá del sexto vuelve a empezar: repetir
 * un tono es preferible a inventar uno fuera de la paleta.
 */
export function tonosDeFrente(
  frentePorNodo: ReadonlyMap<string, string | null>,
  orden: readonly string[],
): ReadonlyMap<string, number> {
  const tonos = new Map<string, number>();
  for (const nodoId of orden) {
    const frenteId = frentePorNodo.get(nodoId) ?? null;
    if (frenteId === null || tonos.has(frenteId)) continue;
    tonos.set(frenteId, (tonos.size % TONOS_DE_FRENTE) + 1);
  }
  return tonos;
}

export interface EntradaClaseBarra {
  readonly vista: VistaGantt;
  readonly fila: FilaPrograma;
  readonly esCritica: boolean;
  /** Tono 1–6 del frente del renglón; `null` si no tiene frente asignado. */
  readonly tonoFrente: number | null;
  readonly seleccionada: boolean;
}

/**
 * Las clases de una barra de actividad.
 *
 * El orden importa poco en CSS pero mucho al leer el DOM en una prueba: base,
 * estilo, color, estado. La alerta de ciclo va al final porque manda sobre
 * cualquier color elegido — un renglón que el backend rechazaría no puede
 * quedar del mismo azul que el resto sólo porque el usuario coloreó por frente.
 */
export function clasesDeBarra({
  vista,
  fila,
  esCritica,
  tonoFrente,
  seleccionada,
}: EntradaClaseBarra): string {
  const clases = ['prog-gantt__barra', `prog-gantt__barra--${vista.estiloBarra}`];

  if (vista.colorBarra === 'tipo') {
    clases.push(`prog-gantt__barra--tipo-${fila.tipo}`);
  } else if (vista.colorBarra === 'frente') {
    clases.push(
      tonoFrente === null ? 'prog-gantt__barra--sin-frente' : `prog-gantt__barra--frente-${tonoFrente}`,
    );
  } else {
    clases.push(esCritica ? 'prog-gantt__barra--critica' : 'prog-gantt__barra--laxa');
  }

  // La trama es la marca de criticidad que sobrevive al blanco y negro. Se
  // enciende siempre que la ruta crítica está trazada, no sólo en mono: en
  // color redunda con el tono, y una redundancia deliberada es exactamente lo
  // que hace legible un Gantt impreso.
  if (esCritica && vista.rutaCritica) clases.push('is-critica');
  if (fila.enCiclo) clases.push('prog-gantt__barra--alerta');
  if (seleccionada) clases.push('is-selected');

  return clases.join(' ');
}

/**
 * El texto de la etiqueta de una barra, o cadena vacía si no hay ninguno
 * encendido.
 *
 * Los campos se concatenan en el orden del catálogo (`CAMPOS_ETIQUETA`) y no en
 * el que se encendieron. Un campo sin dato **se salta**: una etiqueta que dice
 * "C-101 · — · —" ocupa el mismo espacio que la buena y no informa de nada.
 */
export function etiquetaDeBarra(
  vista: VistaGantt,
  fila: FilaPrograma,
  magnitudes: MagnitudesFila | undefined,
): string {
  // Se recorre el **catálogo** y no `vista.etiquetas`. Da lo mismo mientras la
  // lista la construya `alternarEtiqueta` —que ya la deja en este orden—, pero
  // hacer que la garantía dependa del setter es exactamente cómo se pierde:
  // basta una preferencia guardada por una versión anterior, o una lista
  // armada a mano, para que la misma etiqueta se lea distinta. Aquí el orden
  // es del catálogo, venga la lista de donde venga.
  const encendidos = new Set(vista.etiquetas);
  const partes: string[] = [];
  for (const campo of CAMPOS_ETIQUETA) {
    if (!encendidos.has(campo)) continue;
    const texto = campoDeEtiqueta(campo, fila, magnitudes);
    if (texto !== null) partes.push(texto);
  }
  return partes.join(' · ');
}

function campoDeEtiqueta(
  campo: CampoEtiqueta,
  fila: FilaPrograma,
  magnitudes: MagnitudesFila | undefined,
): string | null {
  switch (campo) {
    case 'clave':
      return fila.clave;
    case 'descripcion':
      return fila.descripcion;
    case 'dias':
      return fila.diasLaborables === null ? null : `${fmtNum(fila.diasLaborables)} d`;
    case 'cantidad': {
      // La cantidad de un resumen no existe: sus hijos tienen unidades
      // distintas y sumarlas daría un total que no lo es (`reparto.ts`).
      const cantidad = magnitudes?.cantidad ?? null;
      if (cantidad === null || fila.esResumen) return null;
      return fila.unidad === null ? fmtNum(cantidad) : `${fmtNum(cantidad)} ${fila.unidad}`;
    }
    case 'importe':
      return magnitudes?.importe === null || magnitudes?.importe === undefined
        ? null
        : fmtMXN(magnitudes.importe);
    case 'porcentaje':
      return magnitudes?.pesoPct === null || magnitudes?.pesoPct === undefined
        ? null
        : `${fmtNum(magnitudes.pesoPct)} %`;
  }
}

/**
 * Texto del `title` de una barra: lo que la tabla ya dice, junto.
 *
 * Existe porque la barra es `aria-hidden` —la tabla es la mitad que se navega
 * con lector de pantalla (§12.10)— y el `title` es lo único que le queda a
 * quien mira el Gantt con el ratón encima.
 */
export function tituloDeBarra(
  fila: FilaPrograma,
  eje: EjePrograma,
  esCritica: boolean,
): string {
  const partes = [
    fila.clave === null ? fila.descripcion : `${fila.clave} · ${fila.descripcion}`,
    `${fmtNum(fila.diasLaborables)} d laborables`,
    `${fmtNum(fila.diasCalendario)} d de calendario`,
    `arranca ${etiquetaDeDia(eje, fila.inicioDias)}`,
  ];
  if (fila.holguraDias !== null && fila.holguraDias > 0) {
    partes.push(`holgura ${fmtNum(fila.holguraDias)} d`);
  }
  if (esCritica) partes.push('en la cadena crítica del borrador');
  return partes.join(' · ');
}
