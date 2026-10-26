/**
 * Visor de planos: un lienzo SVG con zoom y arrastre, sobre el que se pintan los
 * trazos ya hechos y se captura el que está en curso.
 *
 * ## Por qué SVG y no una librería de mapas
 *
 * Las coordenadas son de plano (SRID 0), no geográficas: no hay proyección, ni
 * teselas, ni CRS. Un `viewBox` de SVG *es* un sistema de coordenadas de plano,
 * y el navegador resuelve solo el zoom, el recorte y el clic. Leaflet/OpenLayers
 * traerían cientos de kB para hacer, con `CRS.Simple`, lo que aquí es un atributo.
 *
 * ## Qué es un clic y qué es un arrastre
 *
 * El mismo gesto sirve para mover el plano y para poner un vértice. Se distingue
 * por la distancia recorrida entre `pointerdown` y `pointerup`: menos de
 * `UMBRAL_ARRASTRE` px es un clic; más, un arrastre que mueve la vista. Sin esto
 * cada vez que alguien arrastrara el plano con la herramienta de polígono
 * activa dejaría un vértice suelto.
 *
 * El visor no sabe de la API: recibe los trazos ya cargados y avisa qué pasó
 * (`onPunto`, `onSeleccionar`). Quien lo usa decide qué hacer con cada cosa.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  VISTA_VACIA,
  cajaDePuntos,
  desplazar,
  marcadoresDe,
  puntosDe,
  rutaSvg,
  trazoEnPunto,
  vistaQueEncuadra,
  zoomEn,
  type GeometriaGeoJson,
  type Herramienta,
  type Punto,
  type Vista,
} from './geometria';

const UMBRAL_ARRASTRE = 4;
/** Radio de captura del clic, en píxeles de pantalla. */
const TOLERANCIA_PX = 8;

export interface TrazoVisible {
  readonly id: string;
  readonly geometry: GeometriaGeoJson;
  /** Hecho sobre una versión anterior del plano: se dibuja distinto. */
  readonly porRevisar: boolean;
}

interface Props {
  /** URL de la imagen de fondo, o `null` si no hay (o no es una imagen). */
  readonly fondoUrl: string | null;
  readonly trazos: readonly TrazoVisible[];
  readonly seleccionadoId: string | null;
  readonly herramienta: Herramienta;
  /** Vértices del trazo en curso. */
  readonly borrador: readonly Punto[];
  readonly onPunto: (p: Punto) => void;
  readonly onSeleccionar: (id: string | null) => void;
  /** Cambia cuando hay que volver a encuadrar (otro plano). */
  readonly claveDePlano: string;
}

interface Gesto {
  readonly pantallaX: number;
  readonly pantallaY: number;
  readonly vista: Vista;
  movido: boolean;
}

export function Visor({
  fondoUrl,
  trazos,
  seleccionadoId,
  herramienta,
  borrador,
  onPunto,
  onSeleccionar,
  claveDePlano,
}: Props) {
  const svg = useRef<SVGSVGElement>(null);
  const gesto = useRef<Gesto | null>(null);
  const [vista, setVista] = useState<Vista>(VISTA_VACIA);
  const [imagen, setImagen] = useState<{ ancho: number; alto: number } | null>(null);
  const [fondoRoto, setFondoRoto] = useState(false);
  const [anchoPantalla, setAnchoPantalla] = useState(1000);

  // El fondo manda en el encuadre: si hay imagen, el plano *es* la imagen. Sin
  // ella (PDF, o R2 sin configurar) se encuadran los trazos.
  const encuadre = useMemo<Vista>(() => {
    if (imagen) return { x: 0, y: 0, ancho: imagen.ancho, alto: imagen.alto };
    const caja = cajaDePuntos(trazos.flatMap((t) => puntosDe(t.geometry)));
    return caja ? vistaQueEncuadra(caja) : VISTA_VACIA;
  }, [imagen, trazos]);

  // Re-encuadrar al cambiar de plano o cuando por fin se sabe cuánto mide el
  // fondo — pero no cada vez que llegan trazos nuevos, que movería la vista
  // bajo las manos de quien está dibujando.
  const encuadreInicial = useRef(encuadre);
  encuadreInicial.current = encuadre;
  useEffect(() => {
    setVista(encuadreInicial.current);
  }, [claveDePlano, imagen]);

  useEffect(() => {
    setImagen(null);
    setFondoRoto(false);
  }, [fondoUrl]);

  useEffect(() => {
    if (!fondoUrl) return;
    const cargando = new Image();
    cargando.onload = () =>
      setImagen({ ancho: cargando.naturalWidth || 1, alto: cargando.naturalHeight || 1 });
    cargando.onerror = () => setFondoRoto(true);
    cargando.src = fondoUrl;
    return () => {
      cargando.onload = null;
      cargando.onerror = null;
    };
  }, [fondoUrl]);

  useEffect(() => {
    const el = svg.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const obs = new ResizeObserver(() => setAnchoPantalla(el.clientWidth || 1000));
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  /** Pantalla → coordenadas de plano. */
  const aPlano = useCallback((clientX: number, clientY: number): Punto => {
    const el = svg.current;
    const matriz = el?.getScreenCTM();
    if (!el || !matriz) return [0, 0];
    const punto = el.createSVGPoint();
    punto.x = clientX;
    punto.y = clientY;
    const p = punto.matrixTransform(matriz.inverse());
    return [p.x, p.y];
  }, []);

  // Unidades de plano por píxel de pantalla: lo que mantiene los marcadores y la
  // tolerancia del clic del mismo tamaño visual a cualquier zoom.
  const porPixel = vista.ancho / anchoPantalla;

  function alPresionar(e: React.PointerEvent<SVGSVGElement>) {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    gesto.current = { pantallaX: e.clientX, pantallaY: e.clientY, vista, movido: false };
  }

  function alMover(e: React.PointerEvent<SVGSVGElement>) {
    const g = gesto.current;
    if (!g) return;
    const dx = e.clientX - g.pantallaX;
    const dy = e.clientY - g.pantallaY;
    if (!g.movido && Math.hypot(dx, dy) < UMBRAL_ARRASTRE) return;
    g.movido = true;
    const escala = g.vista.ancho / anchoPantalla;
    setVista(desplazar(g.vista, dx * escala, dy * escala));
  }

  function alSoltar(e: React.PointerEvent<SVGSVGElement>) {
    const g = gesto.current;
    gesto.current = null;
    if (!g || g.movido) return;
    const p = aPlano(e.clientX, e.clientY);
    if (herramienta === 'seleccionar') {
      onSeleccionar(trazoEnPunto(trazos, p, TOLERANCIA_PX * porPixel));
    } else {
      onPunto(p);
    }
  }

  function alRodar(e: React.WheelEvent<SVGSVGElement>) {
    // Sin `preventDefault` aquí: React registra `wheel` como pasivo. El scroll
    // de la página se evita con `touch-action`/`overscroll` en el CSS del lienzo.
    const factor = e.deltaY > 0 ? 1.15 : 1 / 1.15;
    setVista((v) => zoomEn(v, factor, aPlano(e.clientX, e.clientY)));
  }

  const radio = 5 * porPixel;
  const dibujando = herramienta !== 'seleccionar';

  return (
    <svg
      ref={svg}
      className="visor"
      data-herramienta={herramienta}
      viewBox={`${vista.x} ${vista.y} ${vista.ancho} ${vista.alto}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Plano con sus trazos"
      onPointerDown={alPresionar}
      onPointerMove={alMover}
      onPointerUp={alSoltar}
      onWheel={alRodar}
      style={{ cursor: dibujando ? 'crosshair' : 'grab' }}
    >
      {fondoUrl && imagen && !fondoRoto && (
        <image href={fondoUrl} x={0} y={0} width={imagen.ancho} height={imagen.alto} />
      )}

      {trazos.map((t) => {
        const elegido = t.id === seleccionadoId;
        const clase = [
          'visor__trazo',
          elegido && 'is-selected',
          t.porRevisar && 'is-por-revisar',
        ]
          .filter(Boolean)
          .join(' ');
        return (
          <g key={t.id} className={clase} data-trazo-id={t.id}>
            <path d={rutaSvg(t.geometry)} vectorEffect="non-scaling-stroke" />
            {marcadoresDe(t.geometry).map((m, i) => (
              <circle key={i} cx={m[0]} cy={m[1]} r={radio} />
            ))}
          </g>
        );
      })}

      {borrador.length > 0 && (
        <g className="visor__borrador" data-testid="borrador">
          <polyline
            points={borrador.map((p) => `${p[0]},${p[1]}`).join(' ')}
            vectorEffect="non-scaling-stroke"
          />
          {borrador.map((p, i) => (
            <circle key={i} cx={p[0]} cy={p[1]} r={radio * (i === 0 ? 1.4 : 1)} />
          ))}
        </g>
      )}
    </svg>
  );
}
