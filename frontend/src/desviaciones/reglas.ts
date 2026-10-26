/**
 * Reflejo de UX de las desviaciones (cerebro MODELO.md §5g, CONOCIMIENTO.md
 * §13.6). No decide nada: qué causas caben en cada fila las dice el backend
 * (`causas_posibles`) y la validación real es la del dominio.
 */

import type { DesviacionRespuesta } from '@/api/generado/modelo';

/** El vocabulario controlado, en español legible. Lo que no esté aquí se humaniza. */
const ETIQUETA_CAUSA: Readonly<Record<string, string>> = {
  mercado: 'Mercado',
  volumen: 'Volumen',
  proveedor_distinto: 'Proveedor distinto',
  cambio_de_presentacion: 'Cambio de presentación',
  desperdicio_mayor_al_teorico: 'Desperdicio mayor al teórico',
  merma_por_dano_clima_o_robo: 'Merma por daño, clima o robo',
  sustitucion_por_equivalente: 'Sustitución por equivalente',
  renegociacion: 'Renegociación',
  urgencia: 'Urgencia',
  alza_de_tabulador: 'Alza de tabulador',
  rendimiento_real_distinto: 'Rendimiento real distinto',
  retrabajo: 'Retrabajo',
  trabajo_fuera_de_alcance: 'Trabajo fuera de alcance',
  tarifa_distinta: 'Tarifa distinta',
  dias_reales_de_renta: 'Días reales de renta',
  equipo_parado: 'Equipo parado',
  tarifa: 'Tarifa',
  combustible: 'Combustible',
  horas_efectivas_contra_facturadas: 'Horas efectivas contra facturadas',
  volumen_realmente_ejecutado: 'Volumen realmente ejecutado',
};

export function etiquetaCausa(causa: string): string {
  if (ETIQUETA_CAUSA[causa]) return ETIQUETA_CAUSA[causa];
  const texto = causa.replace(/_/g, ' ');
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

export function etiquetaFactor(tipo: string): string {
  return tipo === 'precio' ? 'Precio' : tipo === 'consumo' ? 'Consumo' : tipo;
}

/**
 * Cuántas desviaciones están «sin causa» y qué porcentaje es. «Sin causa» es un
 * estado válido con su propio porcentaje (regla de captura 3): se muestra, no
 * se penaliza ni se persigue.
 */
export function resumenDeCausas(filas: readonly Pick<DesviacionRespuesta, 'causa'>[]): {
  readonly total: number;
  readonly sinCausa: number;
  readonly pctSinCausa: number;
} {
  const total = filas.length;
  const sinCausa = filas.filter((f) => f.causa === null || f.causa === undefined).length;
  return { total, sinCausa, pctSinCausa: total === 0 ? 0 : (sinCausa / total) * 100 };
}
