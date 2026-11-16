/**
 * La plantilla de muro (Artefacto) como borrador editable: pasa de la respuesta del servidor a lo que se teclea y de vuelta a la
 * petición. Funciones puras (sin React) para probarlas. El servidor valida y deriva lo demás (la clase y el modo de cada elemento,
 * la ubicación «personalizada»); aquí solo se arma y se dibuja lo que responde.
 */

import type { PlantillaDeMuro, PlantillaDeMuroPeticion } from '@/api/generado/modelo';

import { numeroTecleado } from '../volumen';

export type TipoDeMuro = 'confinado' | 'con_cadena' | 'tabique';
export type Cara = 'exterior' | 'interior';
export type RolDeParte = 'cuerpo' | 'enrase' | 'pretil' | 'cadena';
export type Posicion = 'desplante' | 'cerramiento' | 'remate';

export interface ParteBorrador {
  readonly nombre: string;
  readonly desde: string;
  readonly hasta: string;
  readonly rol: RolDeParte | '';
  readonly caraA: Cara | '';
  readonly caraB: Cara | '';
}

export interface ElementoBorrador {
  readonly uid: string;
  readonly ref: string;
  readonly clase: 'castillo' | 'cadena' | 'muro' | '';
  readonly sep: string;
  readonly posicion: Posicion | '';
  readonly z: string;
}

export interface Borrador {
  readonly nombre: string;
  readonly tipo: TipoDeMuro;
  readonly material: string;
  readonly ubicacion: string;
  readonly altura: string;
  readonly partes: readonly ParteBorrador[];
  readonly elementos: readonly ElementoBorrador[];
}

/** La altura estándar de partida (driver `altura_estandar`): solo vale mientras la obra no responde sus drivers. */
export const ALTURA_DE_VISTA_M = 3;
/** El tramo de muro que dibuja la vista previa. */
export const LARGO_DE_VISTA_M = 6;
/** Separación de partida (driver `separacion_castillos`): solo vale mientras la obra no responde sus drivers. */
export const SEPARACION_DE_VISTA_M = 3;

/** Los drivers de la obra que lee la vista previa: la altura estándar y la separación de castillos. */
export interface DriversDeVista {
  readonly altura_m: number;
  readonly separacion_m: number;
}
export const DRIVERS_DE_VISTA_DE_PARTIDA: DriversDeVista = { altura_m: ALTURA_DE_VISTA_M, separacion_m: SEPARACION_DE_VISTA_M };
export const DRIVER_SEPARACION_CASTILLOS = 'separacion_castillos';

interface DriverVigente {
  readonly clave: string;
  readonly valor_vigente: string | number;
}

/** Los drivers de la vista previa sacados de la lista de la obra; lo que falta o no vale queda en su valor de partida. */
export function driversDeVistaDe(drivers: readonly DriverVigente[] | null | undefined): DriversDeVista {
  const de = (clave: string, partida: number) => {
    const d = drivers?.find((x) => x.clave === clave);
    const n = d ? Number(String(d.valor_vigente).replace(',', '.')) : NaN;
    return Number.isFinite(n) && n > 0 ? n : partida;
  };
  return { altura_m: de('altura_estandar', ALTURA_DE_VISTA_M), separacion_m: de(DRIVER_SEPARACION_CASTILLOS, SEPARACION_DE_VISTA_M) };
}

export function borradorVacio(): Borrador {
  return { nombre: '', tipo: 'con_cadena', material: 'tabique_rojo', ubicacion: 'fachada_a', altura: '', partes: [], elementos: [] };
}

export function borradorDe(p: PlantillaDeMuro): Borrador {
  return {
    nombre: p.nombre,
    tipo: p.tipo as TipoDeMuro,
    material: p.material,
    ubicacion: p.ubicacion,
    altura: p.altura_m ? String(Number(p.altura_m)) : '',
    partes: p.partes.map((x) => ({
      nombre: x.nombre ?? '',
      desde: String(Number(x.desde_m)),
      hasta: String(Number(x.hasta_m)),
      rol: (x.rol ?? '') as RolDeParte | '',
      caraA: (x.cara_a ?? '') as Cara | '',
      caraB: (x.cara_b ?? '') as Cara | '',
    })),
    elementos: p.elementos.map((e) => ({
      uid: e.uid ?? e.ref,
      ref: e.ref,
      clase: (e.clase ?? '') as ElementoBorrador['clase'],
      sep: e.sep_m ? String(Number(e.sep_m)) : '',
      posicion: (e.posicion ?? '') as Posicion | '',
      z: e.z_m ? String(Number(e.z_m)) : '',
    })),
  };
}

/** La petición al servidor, o el motivo por el que aún no se puede guardar. */
export function peticionDe(b: Borrador): { peticion: PlantillaDeMuroPeticion } | { motivo: string } {
  if (!b.nombre.trim()) return { motivo: 'Ponle un nombre a la plantilla.' };
  const partes = [];
  for (const [i, p] of b.partes.entries()) {
    const desde = numeroTecleado(p.desde);
    const hasta = numeroTecleado(p.hasta);
    if (!(hasta > desde) || desde < 0) return { motivo: `La parte ${i + 1} debe ir de un «desde» a un «hasta» mayor.` };
    partes.push({
      nombre: p.nombre,
      desde_m: desde,
      hasta_m: hasta,
      rol: p.rol || null,
      cara_a: p.caraA || null,
      cara_b: p.caraB || null,
    });
  }
  const altura = numeroTecleado(b.altura);
  return {
    peticion: {
      nombre: b.nombre.trim(),
      tipo: b.tipo,
      material: b.material,
      ubicacion: b.ubicacion as PlantillaDeMuroPeticion['ubicacion'],
      altura_m: altura > 0 ? altura : null,
      partes,
      elementos: b.elementos.map((e) => ({
        uid: e.uid,
        ref: e.ref,
        sep_m: e.clase === 'castillo' && numeroTecleado(e.sep) > 0 ? numeroTecleado(e.sep) : null,
        posicion: e.clase === 'cadena' && e.posicion ? e.posicion : null,
        z_m: numeroTecleado(e.z) > 0 ? numeroTecleado(e.z) : null,
      })),
    },
  };
}

/** ¿El borrador es distinto de lo guardado? Compara lo que se manda, no el texto tecleado. */
export function cambio(b: Borrador, guardado: PlantillaDeMuro | null): boolean {
  if (guardado === null) return true;
  return JSON.stringify(peticionDe(b)) !== JSON.stringify(peticionDe(borradorDe(guardado)));
}

export interface MedidaDeElemento {
  readonly ancho_m: number;
  readonly alto_m: number;
}

export interface CastilloDibujado {
  readonly uid: string;
  readonly x_m: number;
  readonly ancho_m: number;
  readonly estimado: boolean;
}
export interface CadenaDibujada {
  readonly uid: string;
  readonly ref: string;
  readonly desde_m: number;
  readonly alto_m: number;
}
export interface ParteDibujada {
  readonly nombre: string;
  readonly desde_m: number;
  readonly hasta_m: number;
  readonly caraA: string;
  readonly caraB: string;
}
export interface Geometria {
  readonly altura_m: number;
  readonly largo_m: number;
  readonly partes: readonly ParteDibujada[];
  readonly castillos: readonly CastilloDibujado[];
  readonly cadenas: readonly CadenaDibujada[];
}

/** Dónde queda cada pieza en el tramo de vista previa: las partes de altura, los castillos (cada «sep» y en los extremos) y las
 *  cadenas según su posición (desplante al pie, remate al tope, cerramiento donde arranca el enrase). */
export function geometriaDeVista(
  b: Borrador,
  medidas: Readonly<Record<string, MedidaDeElemento>>,
  drivers: DriversDeVista = DRIVERS_DE_VISTA_DE_PARTIDA,
): Geometria {
  const partes = b.partes
    .map((p) => ({ nombre: p.nombre, desde_m: numeroTecleado(p.desde), hasta_m: numeroTecleado(p.hasta), caraA: p.caraA, caraB: p.caraB }))
    .filter((p) => p.hasta_m > p.desde_m);
  const tope = partes.reduce((m, p) => Math.max(m, p.hasta_m), 0);
  const altura = tope > 0 ? tope : numeroTecleado(b.altura) > 0 ? numeroTecleado(b.altura) : drivers.altura_m;
  const largo = LARGO_DE_VISTA_M;
  const castillos: CastilloDibujado[] = [];
  const cadenas: CadenaDibujada[] = [];
  for (const e of b.elementos) {
    const m = medidas[e.ref];
    if (e.clase === 'castillo') {
      const ancho = m?.ancho_m ?? 0.15;
      // Igual que al colocar: sin separación propia, un castillo estimado (muro confinado) se reparte por el driver de la obra y uno
      // ubicado (muro con cadena) va en los extremos.
      const propia = numeroTecleado(e.sep) > 0 ? numeroTecleado(e.sep) : null;
      const sep = propia ?? (b.tipo === 'confinado' ? drivers.separacion_m : null);
      const xs = new Set<number>([0, largo]);
      if (sep !== null) for (let x = sep; x < largo - 1e-9; x += sep) xs.add(Number(x.toFixed(4)));
      for (const x of [...xs].sort((a, c) => a - c)) {
        castillos.push({ uid: e.uid, x_m: Math.min(Math.max(x - ancho / 2, 0), largo - ancho), ancho_m: ancho, estimado: b.tipo === 'confinado' });
      }
    } else if (e.clase === 'cadena') {
      const alto = m?.alto_m ?? 0.2;
      const z = numeroTecleado(e.z);
      const cuerpo = partes.filter((p) => p.nombre.toLowerCase().includes('cuerpo') || p.hasta_m < altura).reduce((t, p) => Math.max(t, p.hasta_m), 0);
      const desde =
        e.posicion === 'desplante' ? 0 : e.posicion === 'remate' ? altura - alto : z > 0 ? z : cuerpo > 0 ? cuerpo : altura - alto;
      cadenas.push({ uid: e.uid, ref: e.ref, desde_m: Math.max(0, Math.min(desde, altura - alto)), alto_m: alto });
    }
  }
  return { altura_m: altura, largo_m: largo, partes, castillos, cadenas };
}
