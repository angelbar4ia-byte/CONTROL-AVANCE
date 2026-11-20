/**
 * La capa «espacio» (0143): el cuarto o área donde se asignan zonas de losa, muros y elementos. Helpers puros de la pantalla: los nombres de los tipos,
 * cómo se lee el reparto de un muro compartido y cómo se valida lo que se teclea. El servidor es quien reparte y suma (nunca cuenta un muro dos veces):
 * aquí solo se pinta y se valida la captura.
 */

export const TIPOS_DE_ESPACIO = [
  'recamara', 'bano', 'cocina', 'sala', 'comedor', 'estancia', 'cochera', 'pasillo', 'escalera', 'patio', 'azotea', 'bodega', 'otro',
] as const;
export type TipoDeEspacio = (typeof TIPOS_DE_ESPACIO)[number];

export const NOMBRE_DE_TIPO_DE_ESPACIO: Record<TipoDeEspacio, string> = {
  recamara: 'Recámara',
  bano: 'Baño',
  cocina: 'Cocina',
  sala: 'Sala',
  comedor: 'Comedor',
  estancia: 'Estancia',
  cochera: 'Cochera',
  pasillo: 'Pasillo',
  escalera: 'Escalera',
  patio: 'Patio',
  azotea: 'Azotea',
  bodega: 'Bodega',
  otro: 'Otro',
};

/** Lo que dice la matriz de la losa de un concepto por espacio: si cuenta en una partida o por qué no. */
export const NOMBRE_DEL_ESTADO_DE_PARTIDA: Record<string, string> = {
  cuenta: 'cuenta en su partida',
  sin_espacio: 'sin espacio: no se escribe',
  propuesto: 'concepto propuesto: no cuenta',
  sin_concepto: 'no está en el catálogo',
  falta_partida: 'falta la partida en el árbol',
  sin_cantidad: 'sin cantidad',
};

export interface EspacioCorto {
  readonly id: string;
  readonly nombre: string;
}

/** El nombre de un espacio por su id; «sin espacio» si no hay o ya no existe. */
export function nombreDelEspacio(espacios: readonly EspacioCorto[], id: string | null | undefined): string {
  if (!id) return 'sin espacio';
  return espacios.find((e) => e.id === id)?.nombre ?? 'espacio borrado';
}

/** Un reparto tecleado en %: un número de más de 0 a menos de 100 (coma o punto); `null` si no vale. Vacío = mitad y mitad (no es un error). */
export function repartoTecleado(texto: string): number | null {
  const limpio = texto.trim().replace(',', '.');
  if (limpio === '') return null;
  const n = Number(limpio);
  return Number.isFinite(n) && n > 0 && n < 100 ? n : null;
}

/** Cómo se lee el reparto de un muro: «Recámara 1 50 % · Baño 50 %». Un solo espacio se lleva todo; sin espacio, «sin espacio». */
export function textoDelReparto(
  espacios: readonly EspacioCorto[],
  reparto: readonly { readonly espacio_id: string; readonly fraccion: string | number }[],
): string {
  if (reparto.length === 0) return 'sin espacio';
  return reparto
    .map((p) => {
      const pct = Number(p.fraccion) * 100;
      const texto = Number.isInteger(pct) ? String(pct) : pct.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
      return `${nombreDelEspacio(espacios, p.espacio_id)} ${texto} %`;
    })
    .join(' · ');
}
