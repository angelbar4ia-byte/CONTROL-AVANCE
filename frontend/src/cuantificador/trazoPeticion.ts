/**
 * El cuerpo de `POST /planos/{id}/trazos` de lo que se acaba de dibujar, y a qué medida se enlaza cuando el
 * concepto ya está elegido. Lo comparten el cajón «Guardar trazo» y el **guardado directo**: con un concepto o una
 * medición activos el trazo se guarda al cerrar la figura, sin botón (D-588).
 *
 * Funciones puras, sin DOM ni React.
 */

import type { TrazoPeticion } from '@/api/generado/modelo';
import type { Alineacion, Forma } from './formas';
import { aWkt, MEDIDAS_POR_HERRAMIENTA, type GeometriaBase, type MedidaDeTrazo, type Punto } from './geometria';
import type { TipoDeMedicion } from './tipos';

export interface EnlaceDeTrazo {
  readonly actividadId?: string;
  readonly prototipoNodoId?: string;
  readonly matrizId?: string;
  readonly medida: MedidaDeTrazo;
  readonly factor: string;
}

export interface DatosDelTrazo {
  readonly versionPlano: number;
  readonly fuente?: 'pdf' | 'dwg' | 'ifc';
  readonly capa?: string | null;
  readonly herramienta: GeometriaBase;
  readonly puntos: readonly Punto[];
  readonly grosorM?: number | null;
  readonly alineacion?: Alineacion | null;
  readonly pendientePct?: number | null;
  readonly forma?: Forma | null;
  readonly medicionId?: string | null;
  readonly enlaces: readonly EnlaceDeTrazo[];
}

/** Qué medidas admite lo dibujado: un muro (línea con grosor) también mide su área; una forma estampada se cuenta. */
export function medidasDeLoDibujado(herramienta: GeometriaBase, conGrosor: boolean, conForma: boolean): readonly MedidaDeTrazo[] {
  if (conGrosor) return ['area', 'longitud', 'conteo'];
  if (conForma) return ['conteo', 'area', 'perimetro'];
  return MEDIDAS_POR_HERRAMIENTA[herramienta];
}

export function trazoPeticion(d: DatosDelTrazo): TrazoPeticion {
  const conGrosor = d.herramienta === 'linea' && d.grosorM != null;
  const capa = d.capa?.trim();
  return {
    version_plano: d.versionPlano,
    fuente: d.fuente ?? 'pdf',
    capa: capa ? capa : null,
    geometria_wkt: aWkt(d.herramienta, d.puntos),
    ...(d.medicionId ? { medicion_id: d.medicionId } : {}),
    ...(conGrosor && d.alineacion != null ? { grosor_m: String(d.grosorM), alineacion: d.alineacion } : {}),
    ...(d.herramienta === 'linea' && d.pendientePct != null ? { pendiente_pct: String(d.pendientePct) } : {}),
    ...(d.forma
      ? {
          forma: {
            tipo: d.forma.tipo,
            ancho_m: String(d.forma.anchoM),
            alto_m: String(d.forma.altoM),
            rotacion_grados: String(d.forma.rotacionGrados),
            ...(d.forma.nombre ? { nombre: d.forma.nombre } : {}),
            ...(d.forma.tipo === 'libre' && d.forma.vertices
              ? { vertices: d.forma.vertices.map((v) => [v[0], v[1]] as [number, number]) }
              : {}),
          },
        }
      : {}),
    enlaces: d.enlaces.map((e) => ({
      medida: e.medida,
      factor: e.factor,
      ...(e.prototipoNodoId
        ? { prototipo_nodo_id: e.prototipoNodoId }
        : { actividad_id: e.actividadId as string, ...(e.matrizId ? { matriz_concepto_id: e.matrizId } : {}) }),
    })),
  };
}

/**
 * La medida con la que se enlaza **sin preguntar**, según cómo se mide el concepto (por su unidad) y qué se dibujó;
 * `null` si hay que preguntar: un conteo dibujado como área, un área con una polilínea, un concepto derivado (kg)…
 * El volumen se mide con un área (y un espesor en el factor, que se afina en el detalle).
 */
export function medidaDirecta(
  tipo: TipoDeMedicion | null,
  herramienta: GeometriaBase,
  conGrosor: boolean,
  conForma: boolean,
): MedidaDeTrazo | null {
  const admitidas = medidasDeLoDibujado(herramienta, conGrosor, conForma);
  const elegir = (m: MedidaDeTrazo): MedidaDeTrazo | null => (admitidas.includes(m) ? m : null);
  switch (tipo) {
    case 'area':
      // Un área se mide con un polígono; un muro con grosor, con su área; una línea sin grosor, con su largo × la
      // altura y las caras por defecto (el aplanado de un muro): `factorDeLaMedida` pone ese factor.
      return herramienta === 'poligono' ? elegir('area') : conGrosor ? elegir('area') : herramienta === 'linea' ? elegir('longitud') : null;
    case 'lineal':
      return herramienta === 'linea' ? elegir('longitud') : herramienta === 'poligono' ? elegir('perimetro') : null;
    case 'conteo':
      return herramienta === 'punto' || conForma ? elegir('conteo') : null;
    default:
      return null; // volumen (se mide con área y espesor), derivada o sin tipo: se pregunta
  }
}

/** Altura por defecto de un muro (m) para convertir su largo en área: el aplanado, la pintura. Se afina en el detalle. */
export const ALTURA_POR_DEFECTO_M = 2.6;
/** Caras por defecto de un muro: las dos. */
export const CARAS_POR_DEFECTO = 2;

/**
 * El factor del enlace directo. Casi siempre 1; una **línea sobre un concepto en m²** (sin grosor) mide su largo y lo
 * convierte en área con la altura y las caras por defecto: largo × 2.6 × 2 = largo × 5.2.
 */
export function factorDeLaMedida(
  tipo: TipoDeMedicion | null,
  herramienta: GeometriaBase,
  conGrosor: boolean,
  medida: MedidaDeTrazo,
): string {
  if (tipo === 'area' && herramienta === 'linea' && !conGrosor && medida === 'longitud') {
    return String(Number((ALTURA_POR_DEFECTO_M * CARAS_POR_DEFECTO).toFixed(6)));
  }
  return '1';
}
