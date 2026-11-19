/**
 * Zonas de losa (Fase 1): textos y etiquetas puros para el plano y el detalle del muro. Las cuentas (altura, enrase, cara A/B)
 * las hace el servidor; aquí solo se escribe lo que respondió.
 */

import type { Punto } from './geometria';
import { centroide, type EtiquetaDeMedida } from './etiquetas';

const M = new Intl.NumberFormat('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 3 });

/** Una cota en metros con su signo: «+3.00 m», «−0.30 m». */
export function textoDeCota(valor: string | number): string {
  const n = Number(valor);
  return `${n < 0 ? '−' : '+'}${M.format(Math.abs(n))} m`;
}

export function textoDeMetros(valor: string | number): string {
  return `${M.format(Number(valor))} m`;
}

export const NOMBRE_DE_ORIGEN_DE_ALTURA: Record<string, string> = {
  trazo: 'altura del trazo',
  zona: 'zona de losa',
  driver: 'altura estándar de la obra',
};

export const NOMBRE_DE_CARA: Record<string, string> = { interior: 'interior', exterior: 'exterior' };

export const NOMBRE_DE_ORIGEN_DE_LADO: Record<string, string> = {
  losa: 'bajo losa',
  punto_de_nivel: 'punto de nivel exterior',
  sin_losa: 'sin losa de ese lado',
  sin_zona: 'fuera de toda zona',
};

interface TrazoConRol {
  readonly geometry: { readonly type?: unknown; readonly coordinates?: unknown };
  readonly properties: {
    readonly losa_zona_id?: string | null;
    readonly losa_espesor_m?: string | null;
    readonly nivel_exterior_m?: string | null;
    readonly rotulo?: string | null;
  };
}

interface ZonaParaEtiqueta {
  readonly id: string;
  readonly nombre: string;
  readonly altura_libre_m: string;
  readonly espesor_m: string;
}

/** Lo que se escribe sobre el plano: el nombre, la altura libre y el espesor de cada losa; la cota y el rótulo de cada punto de nivel. */
export function etiquetasDeZonas(trazos: readonly TrazoConRol[], zonas: readonly ZonaParaEtiqueta[]): EtiquetaDeMedida[] {
  const salida: EtiquetaDeMedida[] = [];
  for (const t of trazos) {
    const p = t.properties;
    if (p.losa_zona_id && t.geometry.type === 'Polygon') {
      const z = zonas.find((x) => x.id === p.losa_zona_id);
      const anillo = (t.geometry.coordinates as number[][][])[0] as unknown as readonly Punto[] | undefined;
      if (!z || !anillo) continue;
      salida.push({
        tipo: 'area',
        punto: centroide(anillo),
        titulo: `Losa · ${z.nombre}`,
        texto: `libre ${M.format(Number(z.altura_libre_m))} · e ${M.format(Number(p.losa_espesor_m ?? z.espesor_m))}${p.losa_espesor_m ? ' (subzona)' : ''}`,
      });
    } else if (p.nivel_exterior_m != null && t.geometry.type === 'Point') {
      const c = t.geometry.coordinates as number[];
      salida.push({
        tipo: 'longitud',
        punto: [c[0] as number, c[1] as number],
        titulo: p.rotulo ? `Nivel exterior · ${p.rotulo}` : 'Nivel exterior',
        texto: textoDeCota(p.nivel_exterior_m),
      });
    }
  }
  return salida;
}
