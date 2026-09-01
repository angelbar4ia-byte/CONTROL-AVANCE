/**
 * Estado del menú de herramientas del programa base: **lo que se ve**, no lo
 * que se guarda (§7.4, §7.5, §7.6).
 *
 * ## La línea que este módulo existe para trazar
 *
 * El editor tiene dos clases de herramienta y confundirlas es el fallo más
 * caro que puede tener una pantalla así. Unas **cambian el programa** —partir
 * una actividad, tender un vínculo, aplazar— y son gestos deshacibles que
 * acaban en el `POST` (`gestos.ts` las traduce a acciones de `borrador.ts`).
 * Las otras **cambian la mirada** —la escala del eje, el estilo de la barra,
 * el tema— y no tocan el borrador ni una vez: encender la ruta crítica no
 * puede dejar la pantalla en "sin guardar", porque no hay nada que guardar.
 *
 * Todo lo que vive en este módulo es de la segunda clase. Por eso está aparte
 * del borrador, por eso se persiste en `localStorage` y no en el servidor —el
 * contrato de `ProgramaBase` no tiene dónde poner "el usuario prefiere barras
 * delgadas", y fingir que sí obligaría a versionar el programa cada vez que
 * alguien cambia de tema—, y por eso ninguna de sus funciones recibe un
 * `Borrador`.
 *
 * ## La preferencia es del usuario, no del programa
 *
 * Dos personas abren la misma versión del mismo programa base y la ven
 * distinto: una en oscuro y compacto porque programa de noche, otra en claro y
 * cómodo porque proyecta en junta. Es exactamente lo que `localStorage`
 * resuelve y lo que un campo del contrato no resolvería sin volverse un
 * ajuste compartido que nadie pidió.
 *
 * La densidad **no** está aquí: ya existe `body[data-density]` con su propio
 * almacén (`shell/SelectorDensidad.tsx`), es de toda la app y duplicarla en
 * este módulo dejaría dos interruptores contando cosas distintas de lo mismo.
 * El menú la ofrece, pero escribiendo en el de siempre.
 *
 * Módulo puro (§12.11).
 */

import type { ModoEje } from './ejePrograma';
import type { TipoLiga } from './grafo';

/**
 * Cómo se rotula el eje. Son las cuatro de Opus/Project, y las dos que
 * nombran meses sólo dicen meses de verdad en modo fechas: en días relativos
 * un programa base no tiene calendario al que pertenecer, así que la banda de
 * arriba agrupa cuatro semanas y se rotula como el tramo de semanas que es
 * (`bandasPrograma.ts`).
 */
export type EscalaEje = 'dias' | 'semanas' | 'meses-dias' | 'meses-semanas';

export type EstiloBarra = 'solida' | 'contorno' | 'delgada';

/**
 * Qué puede decir la etiqueta de una barra. Son combinables —clave y días es
 * la combinación de todos los días— y se dibujan en el orden de esta lista,
 * no en el orden en que se encendieron: una etiqueta que cambia de orden
 * según en qué orden se pulsaron los botones se lee distinto cada tarde.
 */
export type CampoEtiqueta =
  | 'clave'
  | 'descripcion'
  | 'dias'
  | 'cantidad'
  | 'importe'
  | 'porcentaje';

export const CAMPOS_ETIQUETA: readonly CampoEtiqueta[] = [
  'clave',
  'descripcion',
  'dias',
  'cantidad',
  'importe',
  'porcentaje',
];

export type PosicionEtiqueta = 'izquierda' | 'dentro' | 'derecha';

export type ColorBarra = 'tipo' | 'frente' | 'criticidad';

/** Gantt o la rejilla volumétrica de cantidades por periodo (`reparto.ts`). */
export type Modalidad = 'gantt' | 'cantidades';

/** Qué magnitud reparte la rejilla y qué mide el porcentaje de la etiqueta. */
export type Magnitud = 'cantidad' | 'importe' | 'porcentaje';

export type Tema = 'claro' | 'oscuro' | 'sistema';

/**
 * `color` es la paleta de siempre; `mono` deja neutros más un acento y pasa la
 * criticidad a **trama** en vez de a color. Es la que sobrevive a una
 * impresión en blanco y negro y a un daltonismo rojo-verde, que es el caso en
 * que un Gantt de obra deja de comunicar justo lo que existe para comunicar.
 */
export type Paleta = 'color' | 'mono';

export type FondoGantt = 'liso' | 'cuadricula' | 'inhabiles';

export interface VistaGantt {
  // --- Escalas ---
  readonly escala: EscalaEje;
  readonly zoom: number;
  readonly modoEje: ModoEje;

  // --- Ruta crítica ---
  readonly rutaCritica: boolean;
  /** Días de holgura que todavía cuentan como crítico (`rutaCritica.ts`). */
  readonly toleranciaHolguraDias: number;

  // --- Barras ---
  readonly estiloBarra: EstiloBarra;
  readonly verResumen: boolean;
  readonly verPausas: boolean;
  readonly verHolgura: boolean;
  readonly verVinculos: boolean;
  readonly etiquetas: readonly CampoEtiqueta[];
  readonly posicionEtiqueta: PosicionEtiqueta;
  readonly colorBarra: ColorBarra;

  // --- Área de trabajo ---
  readonly modalidad: Modalidad;
  readonly magnitud: Magnitud;
  readonly fijarColumnas: boolean;
  /** Claves de `columnasPrograma.ts` visibles, en el orden del catálogo. */
  readonly columnas: readonly string[];
  readonly anchoTabla: number;

  // --- Vínculos ---
  readonly tipoLigaPorDefecto: TipoLiga;

  // --- Apariencia ---
  readonly tema: Tema;
  readonly paleta: Paleta;
  readonly rayado: boolean;
  readonly lineas: boolean;
  readonly colorPorNivel: boolean;
  readonly fondoGantt: FondoGantt;
}

/** Columnas encendidas al abrir: las doce con las que nació la tabla. */
export const COLUMNAS_POR_DEFECTO: readonly string[] = [
  'num',
  'tipo',
  'clave',
  'descripcion',
  'unidad',
  'cantidad',
  'laborables',
  'calendario',
  'inicio',
  'termino',
  'holgura',
  'pred',
];

/**
 * Reparto inicial y topes del panel dividido, en px.
 *
 * El mínimo deja ver número, tipo, clave y descripción —lo que hace falta para
 * saber en qué renglón se está—; el máximo impide dejar el Gantt en una franja
 * donde una barra ya no dice nada.
 */
export const ANCHO_TABLA_POR_DEFECTO = 620;
export const ANCHO_TABLA_MINIMO = 240;
export const ANCHO_TABLA_MAXIMO = 1100;

export function recortarAnchoTabla(px: number): number {
  return Math.round(Math.min(ANCHO_TABLA_MAXIMO, Math.max(ANCHO_TABLA_MINIMO, px)));
}

/**
 * Con qué abre el módulo. Es deliberadamente lo que ya había antes del menú
 * —días relativos, barra sólida, resumen y vínculos encendidos, sin etiqueta—
 * para que estrenar la barra de herramientas no le cambie la pantalla a quien
 * no le pidió nada.
 */
export const VISTA_GANTT_INICIAL: VistaGantt = {
  escala: 'semanas',
  zoom: 16,
  modoEje: 'relativo',

  rutaCritica: false,
  toleranciaHolguraDias: 0,

  estiloBarra: 'solida',
  verResumen: true,
  verPausas: true,
  verHolgura: true,
  verVinculos: true,
  etiquetas: [],
  posicionEtiqueta: 'derecha',
  colorBarra: 'tipo',

  modalidad: 'gantt',
  magnitud: 'cantidad',
  fijarColumnas: false,
  columnas: COLUMNAS_POR_DEFECTO,
  anchoTabla: ANCHO_TABLA_POR_DEFECTO,

  tipoLigaPorDefecto: 'FS',

  tema: 'claro',
  paleta: 'color',
  rayado: true,
  lineas: true,
  colorPorNivel: true,
  fondoGantt: 'cuadricula',
};

/**
 * Enciende o apaga un campo de la etiqueta, conservando el orden del catálogo.
 *
 * No se apila en el orden en que se pulsó: `CAMPOS_ETIQUETA` manda siempre, y
 * por eso una etiqueta con clave y días se lee igual la haya armado quien la
 * haya armado.
 */
export function alternarEtiqueta(
  vista: VistaGantt,
  campo: CampoEtiqueta,
): VistaGantt {
  const encendidos = new Set(vista.etiquetas);
  if (!encendidos.delete(campo)) encendidos.add(campo);
  return { ...vista, etiquetas: CAMPOS_ETIQUETA.filter((c) => encendidos.has(c)) };
}

/**
 * Enciende o apaga una columna, conservando el orden del catálogo por lo
 * mismo que las etiquetas: la tabla no puede reordenarse sola.
 *
 * `columnasFijas` son las que no se pueden apagar —número y descripción—: sin
 * ellas el renglón deja de poder nombrarse, que es para lo que sirve.
 */
export function alternarColumna(
  vista: VistaGantt,
  clave: string,
  catalogo: readonly string[],
  columnasFijas: ReadonlySet<string>,
): VistaGantt {
  if (columnasFijas.has(clave)) return vista;
  const encendidas = new Set(vista.columnas);
  if (!encendidas.delete(clave)) encendidas.add(clave);
  return { ...vista, columnas: catalogo.filter((c) => encendidas.has(c)) };
}

/**
 * El tema que de verdad se pinta.
 *
 * "Sistema" se resuelve **aquí**, en el cliente, y no con un `@media` en la
 * hoja: el módulo lleva el tema en un atributo propio (`data-tema`), así que
 * la hoja sólo necesita el juego de tokens oscuro una vez y no duplicado
 * dentro de una media query. Es además lo que hace que el resto de la app —que
 * hoy es sólo clara— no se vuelva oscura por debajo (ver el docstring de la
 * hoja, sección "Tema oscuro del módulo").
 */
export function temaEfectivo(tema: Tema, prefiereOscuro: boolean): 'claro' | 'oscuro' {
  if (tema === 'sistema') return prefiereOscuro ? 'oscuro' : 'claro';
  return tema;
}

/** Dónde vive la preferencia. Una sola clave: se guarda el objeto entero. */
export const CLAVE_PREFERENCIAS = 'obractrl.programa-gantt.vista';

/**
 * Reconstruye la vista desde lo guardado, **campo por campo y con el default
 * de al lado**.
 *
 * No es paranoia: el objeto guardado sobrevive a los despliegues, así que lo
 * que hay en `localStorage` es la forma que tenía este módulo el día que el
 * usuario tocó el último interruptor, no la de hoy. Un `{ ...inicial,
 * ...guardado }` a secas metería en el estado una `escala` que ya no existe o
 * un `zoom` en `null`, y el fallo aparecería como una pantalla en blanco tres
 * pantallas después. Aquí un valor que no reconoce se cambia por el default y
 * no se propaga.
 */
export function deserializarVista(crudo: string | null): VistaGantt {
  if (crudo === null || crudo === '') return VISTA_GANTT_INICIAL;

  let leido: unknown;
  try {
    leido = JSON.parse(crudo);
  } catch {
    return VISTA_GANTT_INICIAL;
  }
  if (typeof leido !== 'object' || leido === null) return VISTA_GANTT_INICIAL;

  const g = leido as Record<string, unknown>;
  const base = VISTA_GANTT_INICIAL;

  return {
    escala: entre(g.escala, ['dias', 'semanas', 'meses-dias', 'meses-semanas'], base.escala),
    zoom: numeroEntre(g.zoom, 3, 96, base.zoom),
    modoEje: entre(g.modoEje, ['relativo', 'fechas'], base.modoEje),

    rutaCritica: booleano(g.rutaCritica, base.rutaCritica),
    toleranciaHolguraDias: numeroEntre(g.toleranciaHolguraDias, 0, 60, base.toleranciaHolguraDias),

    estiloBarra: entre(g.estiloBarra, ['solida', 'contorno', 'delgada'], base.estiloBarra),
    verResumen: booleano(g.verResumen, base.verResumen),
    verPausas: booleano(g.verPausas, base.verPausas),
    verHolgura: booleano(g.verHolgura, base.verHolgura),
    verVinculos: booleano(g.verVinculos, base.verVinculos),
    etiquetas: CAMPOS_ETIQUETA.filter((campo) => lista(g.etiquetas).includes(campo)),
    posicionEtiqueta: entre(
      g.posicionEtiqueta,
      ['izquierda', 'dentro', 'derecha'],
      base.posicionEtiqueta,
    ),
    colorBarra: entre(g.colorBarra, ['tipo', 'frente', 'criticidad'], base.colorBarra),

    modalidad: entre(g.modalidad, ['gantt', 'cantidades'], base.modalidad),
    magnitud: entre(g.magnitud, ['cantidad', 'importe', 'porcentaje'], base.magnitud),
    fijarColumnas: booleano(g.fijarColumnas, base.fijarColumnas),
    // Una lista de columnas vacía dejaría la tabla sin nada; se cae al default.
    columnas: columnasLeidas(g.columnas, base.columnas),
    anchoTabla: recortarAnchoTabla(numeroEntre(g.anchoTabla, 0, 4000, base.anchoTabla)),

    tipoLigaPorDefecto: entre(
      g.tipoLigaPorDefecto,
      ['FS', 'SS', 'FF', 'SF'],
      base.tipoLigaPorDefecto,
    ),

    tema: entre(g.tema, ['claro', 'oscuro', 'sistema'], base.tema),
    paleta: entre(g.paleta, ['color', 'mono'], base.paleta),
    rayado: booleano(g.rayado, base.rayado),
    lineas: booleano(g.lineas, base.lineas),
    colorPorNivel: booleano(g.colorPorNivel, base.colorPorNivel),
    fondoGantt: entre(g.fondoGantt, ['liso', 'cuadricula', 'inhabiles'], base.fondoGantt),
  };
}

export function serializarVista(vista: VistaGantt): string {
  return JSON.stringify(vista);
}

function entre<T extends string>(
  valor: unknown,
  admitidos: readonly T[],
  porDefecto: T,
): T {
  return typeof valor === 'string' && (admitidos as readonly string[]).includes(valor)
    ? (valor as T)
    : porDefecto;
}

function numeroEntre(valor: unknown, minimo: number, maximo: number, porDefecto: number): number {
  if (typeof valor !== 'number' || !Number.isFinite(valor)) return porDefecto;
  return Math.min(maximo, Math.max(minimo, valor));
}

function booleano(valor: unknown, porDefecto: boolean): boolean {
  return typeof valor === 'boolean' ? valor : porDefecto;
}

function lista(valor: unknown): readonly string[] {
  return Array.isArray(valor) ? valor.filter((v): v is string => typeof v === 'string') : [];
}

function columnasLeidas(valor: unknown, porDefecto: readonly string[]): readonly string[] {
  const leidas = lista(valor);
  return leidas.length === 0 ? porDefecto : leidas;
}
