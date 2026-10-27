/**
 * Geometría del visor de planos — funciones puras, sin DOM ni React.
 *
 * Las coordenadas son **de plano** (SRID 0, MODELO.md §1b "Coordenadas de plano,
 * no geográficas"): unidades locales del archivo —píxeles, si el plano es una
 * imagen—, con el eje Y hacia abajo como en SVG. No hay conversión a lon/lat en
 * ninguna parte: el servidor mide con `ST_Area`/`ST_Length` sobre estas mismas
 * coordenadas y el visor solo las dibuja y las captura.
 *
 * Entra GeoJSON (lo que el servidor manda para pintar) y sale WKT (lo que el
 * visor manda al capturar un trazo nuevo), el par de decisiones 2 y 3 de
 * MODELO.md §1b.
 */

export type Punto = readonly [number, number];

export type Herramienta =
  | 'seleccionar'
  | 'mano'
  | 'zoom'
  | 'poligono'
  | 'rectangulo'
  | 'circulo'
  | 'elipse'
  | 'arco'
  | 'linea'
  | 'polilinea'
  | 'punto'
  | 'copiar'
  | 'hueco'
  | 'borrar'
  | 'nota'
  | 'escala';

/**
 * Herramientas que dibujan una geometría que alimenta cantidades. No lo son: `seleccionar`,
 * `mano` y `zoom` (mueven o eligen), `hueco` (resta de un área ya trazada), `borrar` (quita un
 * trazo), `nota` ni `escala`
 * (marca dos puntos de referencia, no un trazo).
 */
export type HerramientaDeTrazo = Exclude<
  Herramienta,
  'seleccionar' | 'mano' | 'zoom' | 'copiar' | 'hueco' | 'borrar' | 'nota' | 'escala'
>;

/** La geometría que se guarda: lo que el servidor mide. Las herramientas de dibujo desembocan en una de estas. */
export type GeometriaBase = 'poligono' | 'linea' | 'punto';

export type MedidaDeTrazo = 'area' | 'perimetro' | 'longitud' | 'conteo';

export interface Caja {
  readonly minX: number;
  readonly minY: number;
  readonly maxX: number;
  readonly maxY: number;
}

/** Lo que se ve del plano: la caja del `viewBox` de SVG. */
export interface Vista {
  readonly x: number;
  readonly y: number;
  readonly ancho: number;
  readonly alto: number;
}

/** Geometría GeoJSON tal como la manda el servidor (`TrazoFeature.geometry`). */
export interface GeometriaGeoJson {
  readonly type?: unknown;
  readonly coordinates?: unknown;
}

/** Cuántos puntos hacen falta para que la herramienta pueda cerrar el trazo. */
export const PUNTOS_MINIMOS: Record<GeometriaBase, number> = {
  poligono: 3,
  linea: 2,
  punto: 1,
};

/**
 * Qué medidas tienen sentido sobre cada forma.
 *
 * PostGIS no se queja de pedir el área de una línea: devuelve 0. Un enlace así
 * sumaría cero en silencio, que es peor que no poder elegirlo — por eso el
 * formulario solo ofrece las que miden algo (`ST_Area`/`ST_Perimeter` miden
 * polígonos, `ST_Length` mide líneas, el conteo vale para cualquier forma).
 */
export const MEDIDAS_POR_HERRAMIENTA: Record<GeometriaBase, readonly MedidaDeTrazo[]> = {
  poligono: ['area', 'perimetro', 'conteo'],
  linea: ['longitud', 'conteo'],
  punto: ['conteo'],
};

export function trazoCompleto(herramienta: GeometriaBase, puntos: readonly Punto[]): boolean {
  return puntos.length >= PUNTOS_MINIMOS[herramienta];
}

function par(p: Punto): string {
  // `toString` y no `toFixed`: un plano en milímetros no debe perder precisión
  // y uno en píxeles no necesita decimales de relleno.
  return `${p[0]} ${p[1]}`;
}

/** Un hueco es un anillo interior del polígono: necesita tres vértices, como el exterior. */
export const PUNTOS_MINIMOS_DE_HUECO = 3;

/**
 * WKT del trazo capturado. Lanza si faltan puntos: nunca emite un WKT inválido.
 *
 * `huecos` son los anillos interiores de un polígono —lo que se **descuenta**: la
 * ventana de un muro, el cubo de una escalera—. WKT los pone tras el exterior, cada
 * uno cerrado. El servidor mide el área ya descontada (`ST_Area` resta los huecos) y
 * suma su borde al perímetro; si un hueco queda fuera del polígono o se cruza con
 * otro, la geometría es inválida y el trazo se rechaza con su motivo.
 */
export function aWkt(
  herramienta: GeometriaBase,
  puntos: readonly Punto[],
  huecos: readonly (readonly Punto[])[] = [],
): string {
  if (!trazoCompleto(herramienta, puntos)) {
    throw new Error(
      `Faltan puntos: ${herramienta} necesita al menos ${PUNTOS_MINIMOS[herramienta]}.`,
    );
  }
  if (huecos.length > 0 && herramienta !== 'poligono') {
    throw new Error('Solo un polígono tiene huecos.');
  }
  for (const hueco of huecos) {
    if (hueco.length < PUNTOS_MINIMOS_DE_HUECO) {
      throw new Error(`Faltan puntos: un hueco necesita al menos ${PUNTOS_MINIMOS_DE_HUECO}.`);
    }
  }
  switch (herramienta) {
    case 'punto':
      return `POINT(${par(puntos[0] as Punto)})`;
    case 'linea':
      return `LINESTRING(${puntos.map(par).join(', ')})`;
    case 'poligono': {
      // WKT exige cada anillo cerrado: el primer punto se repite al final.
      const cerrado = (anillo: readonly Punto[]) =>
        `(${[...anillo, anillo[0] as Punto].map(par).join(', ')})`;
      return `POLYGON(${[puntos, ...huecos].map(cerrado).join(', ')})`;
    }
  }
}

/**
 * Cuánto más mide una línea inclinada que su proyección en planta: √(1 + (p/100)²), con `p` la
 * pendiente en % (desnivel / recorrido × 100). Sin pendiente (o `null`), 1. Es la misma fórmula
 * con que el servidor mide (migración 0087).
 */
export function factorDePendiente(pendientePct: number | string | null | undefined): number {
  const p = Number(pendientePct ?? 0);
  return p > 0 ? Math.sqrt(1 + (p / 100) ** 2) : 1;
}

export function longitudLocal(puntos: readonly Punto[]): number {
  let total = 0;
  for (let i = 1; i < puntos.length; i += 1) {
    const a = puntos[i - 1] as Punto;
    const b = puntos[i] as Punto;
    total += Math.hypot(b[0] - a[0], b[1] - a[1]);
  }
  return total;
}

/** Área de un anillo por la fórmula del topógrafo (shoelace), siempre positiva. */
export function areaLocal(puntos: readonly Punto[]): number {
  if (puntos.length < 3) return 0;
  let suma = 0;
  for (let i = 0; i < puntos.length; i += 1) {
    const a = puntos[i] as Punto;
    const b = puntos[(i + 1) % puntos.length] as Punto;
    suma += a[0] * b[1] - b[0] * a[1];
  }
  return Math.abs(suma) / 2;
}

export function perimetroLocal(puntos: readonly Punto[]): number {
  if (puntos.length < 2) return 0;
  return longitudLocal([...puntos, puntos[0] as Punto]);
}

/**
 * Medida en unidades de plano mientras se dibuja, para que quien traza vea el
 * orden de magnitud antes de guardar. **No es la cantidad**: la cantidad la
 * calcula el servidor con PostGIS al registrar el trazo, y es la que cuenta.
 */
export function medidaLocal(
  herramienta: GeometriaBase,
  medida: MedidaDeTrazo,
  puntos: readonly Punto[],
  huecos: readonly (readonly Punto[])[] = [],
): number {
  if (medida === 'conteo') return 1;
  if (herramienta === 'poligono') {
    // El área descuenta los huecos; el perímetro suma su borde (`ST_Perimeter`
    // recorre todos los anillos).
    return medida === 'area'
      ? areaLocal(puntos) - huecos.reduce((s, h) => s + areaLocal(h), 0)
      : perimetroLocal(puntos) + huecos.reduce((s, h) => s + perimetroLocal(h), 0);
  }
  if (herramienta === 'linea' && medida === 'longitud') return longitudLocal(puntos);
  return 0;
}

// ── GeoJSON → dibujo ──────────────────────────────────────────────────────

function esPunto(valor: unknown): valor is Punto {
  return (
    Array.isArray(valor) &&
    valor.length >= 2 &&
    typeof valor[0] === 'number' &&
    typeof valor[1] === 'number'
  );
}

function aPuntos(valor: unknown): Punto[] {
  return Array.isArray(valor) ? valor.filter(esPunto).map((p) => [p[0], p[1]] as Punto) : [];
}

export interface Parte {
  readonly tipo: 'punto' | 'linea' | 'anillo';
  readonly puntos: Punto[];
  /** Solo en anillos: a qué polígono pertenece, para saber qué es exterior y qué hueco. */
  readonly poligono?: number;
  /** Solo en anillos: `true` si es un anillo interior (lo que se descuenta). */
  readonly hueco?: boolean;
}

/** Los anillos de un polígono GeoJSON: el primero es el exterior, el resto son huecos. */
function anillosDe(poligono: unknown, indice: number): Parte[] {
  return Array.isArray(poligono)
    ? poligono.map((a, i) => ({
        tipo: 'anillo' as const,
        puntos: aPuntos(a),
        poligono: indice,
        hueco: i > 0,
      }))
    : [];
}

/** Los anillos/líneas de una geometría, aplanados. Lo desconocido se ignora. */
function partes(geometria: GeometriaGeoJson): Parte[] {
  const c = geometria.coordinates;
  switch (geometria.type) {
    case 'Point':
      return esPunto(c) ? [{ tipo: 'punto', puntos: [[c[0], c[1]]] }] : [];
    case 'MultiPoint':
      return aPuntos(c).map((p) => ({ tipo: 'punto' as const, puntos: [p] }));
    case 'LineString':
      return [{ tipo: 'linea', puntos: aPuntos(c) }];
    case 'MultiLineString':
      return Array.isArray(c) ? c.map((l) => ({ tipo: 'linea' as const, puntos: aPuntos(l) })) : [];
    case 'Polygon':
      return anillosDe(c, 0);
    case 'MultiPolygon':
      return Array.isArray(c) ? c.flatMap((poligono, i) => anillosDe(poligono, i)) : [];
    default:
      return [];
  }
}

/** Los anillos, líneas y puntos de una geometría, aplanados (para etiquetas, cotas y resúmenes). */
export function partesDe(geometria: GeometriaGeoJson): Parte[] {
  return partes(geometria);
}

/** Todos los vértices de la geometría. */
export function puntosDe(geometria: GeometriaGeoJson): Punto[] {
  return partes(geometria).flatMap((p) => p.puntos);
}

/** Trazo SVG (`d`) de una geometría; los puntos no tienen trazo, se dibujan aparte. */
export function rutaSvg(geometria: GeometriaGeoJson): string {
  return partes(geometria)
    .filter((p) => p.tipo !== 'punto' && p.puntos.length > 1)
    .map((p) => {
      const [primero, ...resto] = p.puntos as [Punto, ...Punto[]];
      const cuerpo = resto.map((q) => `L${q[0]} ${q[1]}`).join('');
      return `M${primero[0]} ${primero[1]}${cuerpo}${p.tipo === 'anillo' ? 'Z' : ''}`;
    })
    .join('');
}

/** Los puntos sueltos de la geometría (centros de marcador). */
export function marcadoresDe(geometria: GeometriaGeoJson): Punto[] {
  return partes(geometria)
    .filter((p) => p.tipo === 'punto')
    .flatMap((p) => p.puntos);
}

// ── Cajas y vista ─────────────────────────────────────────────────────────

export function cajaDePuntos(puntos: readonly Punto[]): Caja | null {
  if (puntos.length === 0) return null;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const [x, y] of puntos) {
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  }
  return { minX, minY, maxX, maxY };
}

/**
 * Vista que encuadra la caja con un margen proporcional. Una caja degenerada
 * (un solo punto, una línea recta) se ensancha: un `viewBox` de ancho 0 no
 * pinta nada.
 */
export function vistaQueEncuadra(caja: Caja, margen = 0.08): Vista {
  const ancho = Math.max(caja.maxX - caja.minX, 1);
  const alto = Math.max(caja.maxY - caja.minY, 1);
  const mx = ancho * margen;
  const my = alto * margen;
  return { x: caja.minX - mx, y: caja.minY - my, ancho: ancho + 2 * mx, alto: alto + 2 * my };
}

export const VISTA_VACIA: Vista = { x: 0, y: 0, ancho: 1000, alto: 700 };

/** Acerca (`factor` < 1) o aleja (> 1) manteniendo fijo el punto `centro`. */
export function zoomEn(vista: Vista, factor: number, centro: Punto): Vista {
  const ancho = vista.ancho * factor;
  const alto = vista.alto * factor;
  // El punto bajo el cursor conserva su posición relativa dentro de la vista.
  const fx = (centro[0] - vista.x) / vista.ancho;
  const fy = (centro[1] - vista.y) / vista.alto;
  return { x: centro[0] - fx * ancho, y: centro[1] - fy * alto, ancho, alto };
}

export function desplazar(vista: Vista, dx: number, dy: number): Vista {
  return { ...vista, x: vista.x - dx, y: vista.y - dy };
}

// ── Elegir un trazo con el clic ───────────────────────────────────────────

function distanciaASegmento(p: Punto, a: Punto, b: Punto): number {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const largo2 = dx * dx + dy * dy;
  if (largo2 === 0) return Math.hypot(p[0] - a[0], p[1] - a[1]);
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / largo2));
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

function dentroDeAnillo(p: Punto, anillo: readonly Punto[]): boolean {
  let dentro = false;
  for (let i = 0, j = anillo.length - 1; i < anillo.length; j = i, i += 1) {
    const a = anillo[i] as Punto;
    const b = anillo[j] as Punto;
    if (a[1] > p[1] !== b[1] > p[1] && p[0] < ((b[0] - a[0]) * (p[1] - a[1])) / (b[1] - a[1]) + a[0]) {
      dentro = !dentro;
    }
  }
  return dentro;
}

/**
 * Distancia del punto a la geometría; 0 si cae dentro de un polígono.
 * `Infinity` si la geometría no tiene nada que medir.
 */
export function distanciaA(p: Punto, geometria: GeometriaGeoJson): number {
  let mejor = Infinity;
  const todas = partes(geometria);
  // Un clic dentro de un hueco **no** está dentro del polígono: la ventana de un
  // muro no es muro. Cae a la distancia a su borde, que es el del polígono.
  const enHueco = new Set(
    todas
      .filter((q) => q.tipo === 'anillo' && q.hueco && dentroDeAnillo(p, q.puntos))
      .map((q) => q.poligono),
  );
  for (const parte of todas) {
    if (parte.tipo === 'punto') {
      const q = parte.puntos[0];
      if (q) mejor = Math.min(mejor, Math.hypot(p[0] - q[0], p[1] - q[1]));
      continue;
    }
    if (
      parte.tipo === 'anillo' &&
      !parte.hueco &&
      !enHueco.has(parte.poligono) &&
      dentroDeAnillo(p, parte.puntos)
    ) {
      return 0;
    }
    const pts = parte.tipo === 'anillo' ? [...parte.puntos, parte.puntos[0] as Punto] : parte.puntos;
    for (let i = 1; i < pts.length; i += 1) {
      mejor = Math.min(mejor, distanciaASegmento(p, pts[i - 1] as Punto, pts[i] as Punto));
    }
  }
  return mejor;
}

/**
 * Id del trazo más cercano al clic, dentro de `tolerancia` (en unidades de
 * plano; el llamador la deriva del zoom para que sean ~8 px de pantalla).
 * Si hay varios, gana el más cercano; a igual distancia —polígonos apilados,
 * ambos con el clic adentro— gana el de menor área, que es el que está
 * "encima" a la vista.
 */
export function trazoEnPunto(
  trazos: readonly { readonly id: string; readonly geometry: GeometriaGeoJson }[],
  p: Punto,
  tolerancia: number,
): string | null {
  let elegido: string | null = null;
  let mejorDistancia = Infinity;
  let mejorArea = Infinity;
  for (const trazo of trazos) {
    const d = distanciaA(p, trazo.geometry);
    if (d > tolerancia) continue;
    const area = partes(trazo.geometry)
      .filter((q) => q.tipo === 'anillo')
      .reduce((s, q) => s + (q.hueco ? -areaLocal(q.puntos) : areaLocal(q.puntos)), 0);
    if (d < mejorDistancia || (d === mejorDistancia && area < mejorArea)) {
      elegido = trazo.id;
      mejorDistancia = d;
      mejorArea = area;
    }
  }
  return elegido;
}

/**
 * La herramienta con la que se habría dibujado una geometría del servidor, para
 * saber qué medidas tienen sentido sobre ella al enlazarla. `null` si no es una
 * de las tres formas que el visor sabe capturar.
 */
export function herramientaDeGeometria(geometria: GeometriaGeoJson): GeometriaBase | null {
  switch (geometria.type) {
    case 'Polygon':
    case 'MultiPolygon':
      return 'poligono';
    case 'LineString':
    case 'MultiLineString':
      return 'linea';
    case 'Point':
    case 'MultiPoint':
      return 'punto';
    default:
      return null;
  }
}

/**
 * Id de la nota más cercana al clic, dentro de `tolerancia`. Las notas son
 * puntos, así que solo cuenta la distancia; a igual distancia gana la última
 * (la más reciente, que es la que quedó dibujada encima).
 */
export function notaEnPunto(
  notas: readonly { readonly id: string; readonly punto: Punto; readonly destino?: Punto | null }[],
  p: Punto,
  tolerancia: number,
): string | null {
  let elegida: string | null = null;
  let mejor = Infinity;
  for (const nota of notas) {
    // Una flecha o una llamada se elige también por su cuerpo, no solo por donde nace.
    const d = nota.destino
      ? distanciaASegmento(p, nota.punto, nota.destino)
      : Math.hypot(p[0] - nota.punto[0], p[1] - nota.punto[1]);
    if (d <= tolerancia && d <= mejor) {
      elegida = nota.id;
      mejor = d;
    }
  }
  return elegida;
}


/** Distancia entre dos puntos, en unidades de plano. */
export function distanciaEntre(a: Punto, b: Punto): number {
  return Math.hypot(b[0] - a[0], b[1] - a[1]);
}

/**
 * Metros por unidad de plano que saldrían de dos puntos y una distancia real.
 * Es **solo una vista previa** para quien calibra: la escala que cuenta la calcula
 * el servidor (`domain/cuantificacion/escala.py`). `null` si no se puede calcular.
 */
export function escalaPrevista(a: Punto, b: Punto, metros: number): number | null {
  const enPlano = distanciaEntre(a, b);
  if (!Number.isFinite(metros) || metros <= 0 || enPlano === 0) return null;
  return metros / enPlano;
}

// ── Medidas de un trazo ya guardado ───────────────────────────────────────

/**
 * Área de una geometría de polígono en unidades de plano², descontando los huecos.
 * 0 si no hay polígono. Vista previa para el cálculo de volúmenes: la cantidad que
 * cuenta sigue siendo la del servidor.
 */
export function areaDeGeometria(geometria: GeometriaGeoJson): number {
  return partes(geometria)
    .filter((p) => p.tipo === 'anillo')
    .reduce((suma, p) => {
      const area = areaLocal(p.puntos);
      return p.hueco ? suma - area : suma + area;
    }, 0);
}

/** Longitud de una geometría de línea en unidades de plano. 0 si no hay línea. */
export function longitudDeGeometria(geometria: GeometriaGeoJson): number {
  return partes(geometria)
    .filter((p) => p.tipo === 'linea')
    .reduce((suma, p) => suma + longitudLocal(p.puntos), 0);
}

// ── GeoJSON → WKT ─────────────────────────────────────────────────────────

/**
 * El WKT de una geometría GeoJSON del servidor, para volver a registrarla (rehacer un trazo que se
 * borró). Cubre lo que el cuantificador guarda: puntos, líneas y polígonos con huecos, y los
 * multipolígonos que salen de un hueco que parte un área. `null` si no la reconoce.
 */
export function geojsonAWkt(geometria: GeometriaGeoJson): string | null {
  const par = (p: unknown): string | null =>
    Array.isArray(p) && typeof p[0] === 'number' && typeof p[1] === 'number' ? `${p[0]} ${p[1]}` : null;
  const lista = (ps: unknown): string | null => {
    if (!Array.isArray(ps)) return null;
    const partes = ps.map(par);
    return partes.every((x) => x !== null) ? `(${partes.join(', ')})` : null;
  };
  const poligono = (anillos: unknown): string | null => {
    if (!Array.isArray(anillos)) return null;
    const partes = anillos.map(lista);
    return partes.every((x) => x !== null) ? `(${partes.join(', ')})` : null;
  };
  const c = geometria.coordinates;
  switch (geometria.type) {
    case 'Point': {
      const p = par(c);
      return p === null ? null : `POINT(${p})`;
    }
    case 'LineString': {
      const l = lista(c);
      return l === null ? null : `LINESTRING${l}`;
    }
    case 'Polygon': {
      const pg = poligono(c);
      return pg === null ? null : `POLYGON${pg}`;
    }
    case 'MultiPolygon': {
      if (!Array.isArray(c)) return null;
      const partes = c.map(poligono);
      return partes.every((x) => x !== null) ? `MULTIPOLYGON(${partes.join(', ')})` : null;
    }
    default:
      return null;
  }
}
