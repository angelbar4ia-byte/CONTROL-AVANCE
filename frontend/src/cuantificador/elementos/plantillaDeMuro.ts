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
/** Cómo cuenta un castillo sus piezas: cada separación y extremos, solo extremos, por ml de muro o total del prototipo. */
export type ReglaDeCastillo = 'separacion' | 'extremos' | 'por_ml' | 'total';
export type Planta = 'PB' | 'PA';

/** Las reglas que admite un castillo según el tipo de muro: el que se coloca en el plano (con cadena) cuenta piezas enteras. */
export function reglasDeCastillo(tipo: TipoDeMuro): readonly ReglaDeCastillo[] {
  return tipo === 'con_cadena' ? ['separacion', 'extremos'] : ['separacion', 'extremos', 'por_ml', 'total'];
}

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
  /** Solo castillos. Vacía = la de siempre (separación propia, o extremos / la del driver según el tipo). */
  readonly regla: ReglaDeCastillo | '';
  readonly piezasPorMl: string;
  readonly totalM: string;
  readonly baseM2: string;
  /** De dónde sale el dato (fila y celda del Excel); se conserva tal cual. */
  readonly origen: string;
}

export interface Borrador {
  readonly nombre: string;
  readonly tipo: TipoDeMuro;
  readonly material: string;
  readonly ubicacion: string;
  readonly altura: string;
  readonly partes: readonly ParteBorrador[];
  readonly elementos: readonly ElementoBorrador[];
  /** Solo muro confinado: el prototipo (oro_401…) o `global_1` / `global_2`; vacío = ninguno. */
  readonly prototipo: string;
  readonly planta: Planta | '';
  readonly notas: string;
  readonly porConfirmar: boolean;
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
  return {
    nombre: '', tipo: 'con_cadena', material: 'tabique_rojo', ubicacion: 'fachada_a', altura: '', partes: [], elementos: [],
    prototipo: '', planta: '', notas: '', porConfirmar: false,
  };
}

/** Un borrador de muro confinado para un prototipo y su planta (estructura sin capturar: sin castillos todavía). */
export function borradorDePrototipo(prototipo: string, planta: Planta | '', nombre: string): Borrador {
  return { ...borradorVacio(), nombre, tipo: 'confinado', ubicacion: 'interior', prototipo, planta, porConfirmar: true };
}

/** El identificador con que el panel pide una plantilla nueva (con el prototipo y la planta, si es de un prototipo). */
export const PLANTILLA_NUEVA = 'nueva';
export function plantillaNuevaDe(prototipo?: string, planta?: Planta | null): string {
  return prototipo ? `${PLANTILLA_NUEVA}:${prototipo}:${planta ?? ''}` : PLANTILLA_NUEVA;
}
export function esPlantillaNueva(id: string | null): boolean {
  return id === PLANTILLA_NUEVA || (id?.startsWith(`${PLANTILLA_NUEVA}:`) ?? false);
}
/** El prototipo y la planta que trae el identificador de una plantilla nueva. */
export function prototipoDeNueva(id: string | null): { prototipo: string; planta: Planta | '' } {
  const [, prototipo = '', planta = ''] = (id ?? '').split(':');
  return { prototipo, planta: planta === 'PB' || planta === 'PA' ? planta : '' };
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
      regla: (e.regla ?? '') as ReglaDeCastillo | '',
      piezasPorMl: e.piezas_por_ml ? String(Number(e.piezas_por_ml)) : '',
      totalM: e.total_m ? String(Number(e.total_m)) : '',
      baseM2: e.base_m2 ? String(Number(e.base_m2)) : '',
      origen: e.origen ?? '',
    })),
    prototipo: p.prototipo ?? '',
    planta: (p.planta ?? '') as Planta | '',
    notas: p.notas ?? '',
    porConfirmar: p.por_confirmar === true,
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
  for (const e of b.elementos) {
    if (e.clase !== 'castillo') continue;
    if (e.regla === 'por_ml' && !(numeroTecleado(e.piezasPorMl) > 0)) return { motivo: `${e.uid} cuenta «por ml»: di cuántas piezas lleva cada metro lineal de muro.` };
    if (e.regla === 'total' && !(numeroTecleado(e.totalM) > 0 && numeroTecleado(e.baseM2) > 0))
      return { motivo: `${e.uid} cuenta por «total»: di los metros de castillo y los m² de muro sobre los que se reparten.` };
  }
  if (b.prototipo && !b.planta && !b.prototipo.startsWith('global_')) return { motivo: 'Di la planta del prototipo (PB o PA).' };
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
        sep_m: e.clase === 'castillo' && (e.regla === '' || e.regla === 'separacion') && numeroTecleado(e.sep) > 0 ? numeroTecleado(e.sep) : null,
        regla: e.clase === 'castillo' && e.regla ? e.regla : null,
        piezas_por_ml: e.clase === 'castillo' && e.regla === 'por_ml' ? numeroTecleado(e.piezasPorMl) : null,
        total_m: e.clase === 'castillo' && e.regla === 'total' ? numeroTecleado(e.totalM) : null,
        base_m2: e.clase === 'castillo' && e.regla === 'total' ? numeroTecleado(e.baseM2) : null,
        origen: e.origen ? e.origen : null,
        posicion: e.clase === 'cadena' && e.posicion ? e.posicion : null,
        z_m: numeroTecleado(e.z) > 0 ? numeroTecleado(e.z) : null,
      })),
      prototipo: b.prototipo ? b.prototipo : null,
      planta: b.prototipo && !b.prototipo.startsWith('global_') && b.planta ? b.planta : null,
      notas: b.notas.trim() ? b.notas.trim() : null,
      por_confirmar: b.porConfirmar,
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
  /** Cómo se contó (para el rótulo de la vista previa). */
  readonly regla: ReglaDeCastillo;
  /** Las piezas que cuenta el castillo en el tramo de muestra (con fracción en «por ml» y «total»). */
  readonly piezas: number;
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

/** La regla con que se dibuja un castillo: la suya o, si no trae, la de siempre (separación propia; si no, extremos o la del driver). */
export function reglaDeVista(e: ElementoBorrador, tipo: TipoDeMuro): ReglaDeCastillo {
  if (e.regla) return e.regla;
  if (numeroTecleado(e.sep) > 0) return 'separacion';
  return tipo === 'con_cadena' ? 'extremos' : 'separacion';
}

/** Las piezas que cuenta un castillo en un tramo de `largo` × `altura` (igual que el servidor: sin redondear en «por ml» y «total»). */
export function piezasDeVista(
  e: ElementoBorrador,
  regla: ReglaDeCastillo,
  tramo: { readonly largo: number; readonly altura: number; readonly separacion: number | null },
): number {
  if (regla === 'extremos') return 2;
  if (regla === 'por_ml') return Math.round(tramo.largo * numeroTecleado(e.piezasPorMl) * 1000) / 1000;
  if (regla === 'total') {
    const base = numeroTecleado(e.baseM2);
    const alto = Math.max(tramo.altura - numeroTecleado(e.z), 0.1);
    return base > 0 ? Math.round(((numeroTecleado(e.totalM) * tramo.largo * tramo.altura) / base / alto) * 1000) / 1000 : 0;
  }
  return tramo.separacion !== null ? Math.max(2, Math.ceil(tramo.largo / tramo.separacion - 1e-9) + 1) : 2;
}

/** Dónde caen las piezas en el tramo: «cada separación y extremos» a cada separación; las demás, repartidas parejo del inicio al final. */
function posicionesDeVista(regla: ReglaDeCastillo, piezas: number, largo: number, separacion: number | null): number[] {
  if (regla === 'extremos') return [0, largo];
  if (regla === 'separacion') {
    const xs = new Set<number>([0, largo]);
    if (separacion !== null) for (let x = separacion; x < largo - 1e-9; x += separacion) xs.add(Number(x.toFixed(4)));
    return [...xs].sort((a, c) => a - c);
  }
  if (piezas <= 1) return [largo / 2];
  return Array.from({ length: piezas }, (_, i) => (largo * i) / (piezas - 1));
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
      const regla = reglaDeVista(e, b.tipo);
      const separacion = numeroTecleado(e.sep) > 0 ? numeroTecleado(e.sep) : b.tipo === 'confinado' ? drivers.separacion_m : null;
      const exactas = piezasDeVista(e, regla, { largo, altura, separacion });
      const estimado = b.tipo === 'confinado';
      const xs = posicionesDeVista(regla, Math.max(1, Math.ceil(exactas - 1e-9)), largo, separacion);
      for (const x of xs) {
        castillos.push({ uid: e.uid, x_m: Math.min(Math.max(x - ancho / 2, 0), largo - ancho), ancho_m: ancho, estimado, regla, piezas: exactas });
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
