/**
 * Catálogo de columnas de la tabla del programa base: cuáles hay, cuáles se
 * pueden apagar y cuáles se congelan (§7.4, §12.10).
 *
 * ## Por qué las columnas dejan de estar en la hoja de estilo
 *
 * El `grid-template-columns` de `.prog-tabla__fila` era una constante de doce
 * pistas en el CSS. Con "Columnas visibles" en el menú deja de poder serlo: la
 * plantilla depende de qué encendió el usuario, y una hoja de estilo no lo
 * sabe. Así que la plantilla se calcula aquí y viaja como `--prog-cols`; la
 * hoja conserva el valor por defecto en el `var()` para que la tabla siga
 * dibujándose aunque nadie le pase nada.
 *
 * ## Qué no se puede apagar
 *
 * El número de renglón y la descripción. Un renglón sin número no se puede
 * nombrar en voz alta —que es para lo que se numera el árbol completo y no lo
 * visible (`filasPrograma.ts`)— y uno sin descripción no se puede reconocer.
 * Todo lo demás es opcional, incluida la clave.
 *
 * ## El congelado
 *
 * "Fijar columnas" congela **hasta Descripción**: es el bloque que dice en qué
 * renglón se está, y es lo que hace utilizable correr la tabla a la derecha
 * para ver Holgura sin perder de vista qué actividad se está mirando. Se
 * resuelve con `position: sticky` y un `left` por columna, y ese `left` es la
 * suma de los anchos de las que la preceden **entre las visibles**: apagar Tipo
 * mueve a Clave, y calcularlo con el catálogo completo la dejaría flotando
 * setenta y cuatro píxeles a la derecha de donde está.
 *
 * La columna elástica —Descripción— cierra el bloque congelado a propósito: es
 * la única sin ancho fijo, y si algo tuviera que congelarse después de ella no
 * habría desplazamiento que calcular.
 *
 * Módulo puro (§12.11).
 */

export interface ColumnaPrograma {
  readonly clave: string;
  readonly titulo: string;
  /** Texto largo del `title` del encabezado y de la casilla del menú. */
  readonly ayuda: string;
  /** Pista de `grid-template-columns`. */
  readonly pista: string;
  /** Ancho en px para calcular el congelado; `null` en la elástica. */
  readonly anchoPx: number | null;
}

/**
 * Las columnas, en el único orden en que se dibujan.
 *
 * El orden no es configurable a propósito: una tabla cuyas columnas cambian de
 * sitio deja de poder leerse de memoria, que es como se lee una tabla de ciento
 * cincuenta renglones que se revisa todos los días.
 */
export const COLUMNAS_PROGRAMA: readonly ColumnaPrograma[] = [
  { clave: 'num', titulo: '#', ayuda: 'Número de renglón en el árbol completo', pista: '44px', anchoPx: 44 },
  { clave: 'tipo', titulo: 'Tipo', ayuda: 'Clase del nodo: nivel, etapa o concepto', pista: '74px', anchoPx: 74 },
  { clave: 'clave', titulo: 'Clave', ayuda: 'Clave del nodo en el árbol WBS', pista: '104px', anchoPx: 104 },
  {
    clave: 'descripcion',
    titulo: 'Descripción',
    ayuda: 'Nombre del nodo, con su sangría de árbol',
    pista: 'minmax(240px, 1fr)',
    anchoPx: null,
  },
  { clave: 'unidad', titulo: 'Unidad', ayuda: 'Unidad del presupuesto vigente', pista: '58px', anchoPx: 58 },
  { clave: 'cantidad', titulo: 'Cantidad', ayuda: 'Cantidad de la partida; no se agrega hacia arriba', pista: '92px', anchoPx: 92 },
  { clave: 'importe', titulo: 'Importe', ayuda: 'Importe de la partida; en resumen, la suma de sus hijos', pista: '112px', anchoPx: 112 },
  { clave: 'peso', titulo: '% del total', ayuda: 'Peso del renglón sobre el importe del programa', pista: '82px', anchoPx: 82 },
  { clave: 'laborables', titulo: 'Días lab.', ayuda: 'Días de trabajo efectivo: la suma de los tramos (§7.6)', pista: '96px', anchoPx: 96 },
  { clave: 'calendario', titulo: 'Días cal.', ayuda: 'Días que la barra ocupa de punta a punta, pausas incluidas', pista: '96px', anchoPx: 96 },
  { clave: 'inicio', titulo: 'Inicio', ayuda: 'Día en que arranca la barra', pista: '92px', anchoPx: 92 },
  { clave: 'termino', titulo: 'Término', ayuda: 'Último día trabajado', pista: '92px', anchoPx: 92 },
  { clave: 'holgura', titulo: 'Holgura', ayuda: 'Días que puede correrse sin empujar el cierre del borrador', pista: '82px', anchoPx: 82 },
  { clave: 'pred', titulo: 'Pred.', ayuda: 'Cuántas precedencias entran al renglón', pista: '64px', anchoPx: 64 },
];

/** Las que no se pueden apagar: sin ellas el renglón no se puede nombrar. */
export const COLUMNAS_FIJAS: ReadonlySet<string> = new Set(['num', 'descripcion']);

/** Última columna del bloque congelado; ver el docstring del módulo. */
const CIERRA_CONGELADO = 'descripcion';

export const CLAVES_COLUMNAS: readonly string[] = COLUMNAS_PROGRAMA.map((c) => c.clave);

/**
 * Las columnas encendidas, en el orden del catálogo.
 *
 * Se filtra el catálogo y no se recorre lo guardado: una preferencia vieja
 * puede traer una clave que ya no existe, y así se cae sola.
 */
export function columnasVisibles(claves: readonly string[]): readonly ColumnaPrograma[] {
  const encendidas = new Set(claves);
  const visibles = COLUMNAS_PROGRAMA.filter(
    (columna) => encendidas.has(columna.clave) || COLUMNAS_FIJAS.has(columna.clave),
  );
  return visibles;
}

/** El `grid-template-columns` de la tabla, para `--prog-cols`. */
export function plantillaDeColumnas(columnas: readonly ColumnaPrograma[]): string {
  return columnas.map((columna) => columna.pista).join(' ');
}

/**
 * Desplazamiento `left` de cada columna congelada, en px, indexado por clave.
 *
 * Sólo devuelve entrada para las que se congelan; el resto no lleva `sticky` y
 * pasa por debajo. Con el congelado apagado devuelve vacío, que es lo que deja
 * la tabla exactamente como estaba antes del menú.
 */
export function desplazamientosCongelados(
  columnas: readonly ColumnaPrograma[],
  congelar: boolean,
): ReadonlyMap<string, number> {
  const salida = new Map<string, number>();
  if (!congelar) return salida;

  let acumulado = 0;
  for (const columna of columnas) {
    salida.set(columna.clave, acumulado);
    if (columna.clave === CIERRA_CONGELADO) break;
    // La elástica no puede aportar un ancho conocido; si apareciera antes de
    // Descripción el congelado dejaría de poder calcularse y se corta ahí.
    if (columna.anchoPx === null) break;
    acumulado += columna.anchoPx;
  }
  return salida;
}
