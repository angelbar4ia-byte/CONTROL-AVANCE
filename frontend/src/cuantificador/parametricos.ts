/**
 * Elementos paramétricos (D-602, D-604): etiquetas y orden de los parámetros de cada tipo, y cómo se lee la receta.
 * Las cuentas viven en el servidor (`domain/cuantificacion/elementos_parametricos.py`); aquí solo se muestran.
 */

export type TipoParametrico = 'castillo' | 'lineal' | 'zapata' | 'losa';

export const NOMBRE_DEL_TIPO: Readonly<Record<TipoParametrico, string>> = {
  castillo: 'Castillo (pieza)',
  lineal: 'Trabe o cadena (metro)',
  zapata: 'Zapata aislada (pieza)',
  losa: 'Losa maciza (m²)',
};

export interface CampoParametrico {
  readonly clave: string;
  readonly etiqueta: string;
  readonly unidad: string;
}

const AMARRE: readonly CampoParametrico[] = [
  { clave: 'am_l', etiqueta: 'Largo del amarre', unidad: 'm' },
  { clave: 'am_cal', etiqueta: 'Calibre del alambre', unidad: '' },
];

/** Los parámetros de cada tipo, en el orden en que se editan. */
export const CAMPOS_POR_TIPO: Readonly<Record<TipoParametrico, readonly CampoParametrico[]>> = {
  castillo: [
    { clave: 'largo', etiqueta: 'Largo', unidad: 'm' },
    { clave: 'ancho', etiqueta: 'Ancho', unidad: 'm' },
    { clave: 'alto', etiqueta: 'Alto', unidad: 'm' },
    { clave: 'n_var', etiqueta: 'Varillas', unidad: 'pzas' },
    { clave: 'no_var', etiqueta: 'No. de varilla', unidad: '' },
    { clave: 'sep', etiqueta: 'Separación de estribos', unidad: 'm' },
    { clave: 'no_est', etiqueta: 'No. del estribo', unidad: '' },
    { clave: 'rec', etiqueta: 'Recubrimiento', unidad: 'm' },
    { clave: 'gancho', etiqueta: 'Ganchos', unidad: 'm' },
    { clave: 'desp', etiqueta: 'Desperdicio', unidad: '%' },
    ...AMARRE,
  ],
  lineal: [
    { clave: 'ancho', etiqueta: 'Ancho', unidad: 'm' },
    { clave: 'alto', etiqueta: 'Peralte', unidad: 'm' },
    { clave: 'n_sup', etiqueta: 'Varillas arriba', unidad: 'pzas' },
    { clave: 'no_sup', etiqueta: 'No. arriba', unidad: '' },
    { clave: 'n_inf', etiqueta: 'Varillas abajo', unidad: 'pzas' },
    { clave: 'no_inf', etiqueta: 'No. abajo', unidad: '' },
    { clave: 'sep', etiqueta: 'Separación de estribos', unidad: 'm' },
    { clave: 'no_est', etiqueta: 'No. del estribo', unidad: '' },
    { clave: 'rec', etiqueta: 'Recubrimiento', unidad: 'm' },
    { clave: 'gancho', etiqueta: 'Ganchos', unidad: 'm' },
    { clave: 'desp', etiqueta: 'Desperdicio', unidad: '%' },
    { clave: 'lados', etiqueta: 'Lados de cimbra', unidad: '' },
    ...AMARRE,
  ],
  zapata: [
    { clave: 'largo', etiqueta: 'Largo', unidad: 'm' },
    { clave: 'ancho', etiqueta: 'Ancho', unidad: 'm' },
    { clave: 'alto', etiqueta: 'Peralte', unidad: 'm' },
    { clave: 'sep_l', etiqueta: 'Separación a lo largo', unidad: 'm' },
    { clave: 'sep_a', etiqueta: 'Separación a lo ancho', unidad: 'm' },
    { clave: 'no_par', etiqueta: 'No. de varilla', unidad: '' },
    { clave: 'rec', etiqueta: 'Recubrimiento', unidad: 'm' },
    { clave: 'gancho', etiqueta: 'Ganchos', unidad: 'm' },
    { clave: 'desp', etiqueta: 'Desperdicio', unidad: '%' },
    ...AMARRE,
  ],
  losa: [
    { clave: 'alto', etiqueta: 'Espesor', unidad: 'm' },
    { clave: 'sep_x', etiqueta: 'Separación en X', unidad: 'm' },
    { clave: 'sep_y', etiqueta: 'Separación en Y', unidad: 'm' },
    { clave: 'no_par', etiqueta: 'No. de varilla', unidad: '' },
    { clave: 'lechos', etiqueta: 'Lechos', unidad: '' },
    { clave: 'desp', etiqueta: 'Desperdicio', unidad: '%' },
    ...AMARRE,
  ],
};

/** Un número de receta con los decimales que pide su magnitud, sin ceros de sobra. */
export function formatoDeReceta(valor: number, decimales = 3): string {
  return Number(valor.toFixed(decimales)).toLocaleString('es-MX', { maximumFractionDigits: decimales });
}

/** Las líneas de la receta de una muestra, listas para mostrar («Concreto 0.0585 m³ por pza»). */
export function lineasDeReceta(
  receta: {
    readonly unidad: string;
    readonly concreto: number;
    readonly acero_kg: number;
    readonly estribos_kg: number;
    readonly n_estribos: number;
    readonly long_estribo_m: number;
    readonly n_amarres: number;
    readonly alambre_kg: number;
    readonly varas: number;
    readonly cimbra_m2: Readonly<Record<string, number>>;
  },
): readonly (readonly [string, string])[] {
  const por = ` por ${receta.unidad}`;
  const lados = Object.entries(receta.cimbra_m2)
    .sort(([a], [b]) => Number(b) - Number(a))
    .map(([l, m2]) => `${formatoDeReceta(m2, 2)} m² (${l} ${Number(l) === 1 ? 'cara' : 'lados'})`)
    .join(' · ');
  const filas: (readonly [string, string])[] = [
    ['Concreto', `${formatoDeReceta(receta.concreto, 4)} m³${por}`],
    ['Acero', `${formatoDeReceta(receta.acero_kg, 2)} kg${por} · ${formatoDeReceta(receta.varas, 2)} varas de 12 m`],
  ];
  if (receta.n_estribos > 0) {
    filas.push([
      'Estribos',
      `${formatoDeReceta(receta.n_estribos, 1)} de ${formatoDeReceta(receta.long_estribo_m, 2)} m · ${formatoDeReceta(receta.estribos_kg, 2)} kg${por}`,
    ]);
  }
  filas.push(
    ['Alambre de amarre', `${formatoDeReceta(receta.n_amarres, 1)} amarres · ${formatoDeReceta(receta.alambre_kg, 3)} kg${por}`],
    ['Cimbra', `${lados}${por}`],
  );
  return filas;
}

/** Qué elementos se pueden colocar en un trazo según su geometría: un punto es una pieza, una línea son metros, un área son m². */
export function tiposParaGeometria(geometria: string): readonly TipoParametrico[] {
  if (geometria === 'Point') return ['castillo', 'zapata'];
  if (geometria === 'LineString') return ['lineal'];
  if (geometria === 'Polygon') return ['losa'];
  return [];
}

/** Los lados de cimbra que ofrece cada tipo (una pieza fija el suyo a mano). */
export function ladosDeCimbra(tipo: TipoParametrico): readonly number[] {
  if (tipo === 'castillo') return [4, 3, 2];
  if (tipo === 'lineal') return [3, 2];
  return [];
}
