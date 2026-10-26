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
  notaEnPunto,
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
  /** Aprobado por Control de obra: se dibuja en verde. */
  readonly aprobado: boolean;
}

export interface NotaVisible {
  readonly id: string;
  readonly punto: Punto;
  readonly texto: string;
  readonly porRevisar: boolean;
}

/** Lo elegido en el plano: un trazo o una nota, nunca los dos. */
export interface Seleccion {
  readonly tipo: 'trazo' | 'nota';
  readonly id: string;
}

interface Props {
  /** URL de la imagen de fondo, o `null` si no hay (o no es una imagen). */
  readonly fondoUrl: string | null;
  readonly trazos: readonly TrazoVisible[];
  readonly notas: readonly NotaVisible[];
  readonly seleccion: Seleccion | null;
  readonly herramienta: Herramienta;
  /** Vértices del trazo en curso. */
  readonly borrador: readonly Punto[];
  readonly onPunto: (p: Punto) => void;
  readonly onSeleccionar: (seleccion: Seleccion | null) => void;
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
  notas,
  seleccion,
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

  // Re-encuadrar al cambiar de plano y cuando llega lo que define el encuadre
  // (la imagen, o los primeros trazos: al abrir un plano los trazos llegan *después*
  // de montar el visor, y sin esto quedarían fuera de cuadro). No se re-encuadra
  // si quien trazaba ya movió la vista: saltarle bajo las manos al guardar el
  // primer trazo sería peor que no encuadrar.
  const encuadreActual = useRef(encuadre);
  encuadreActual.current = encuadre;
  const vistaTocada = useRef(false);
  const hayTrazos = trazos.length > 0;
  useEffect(() => {
    vistaTocada.current = false;
  }, [claveDePlano]);
  useEffect(() => {
    if (!vistaTocada.current) setVista(encuadreActual.current);
  }, [claveDePlano, imagen, hayTrazos]);

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
    vistaTocada.current = true;
    const escala = g.vista.ancho / anchoPantalla;
    setVista(desplazar(g.vista, dx * escala, dy * escala));
  }

  function alSoltar(e: React.PointerEvent<SVGSVGElement>) {
    const g = gesto.current;
    gesto.current = null;
    if (!g || g.movido) return;
    const p = aPlano(e.clientX, e.clientY);
    if (herramienta === 'seleccionar') {
      const tolerancia = TOLERANCIA_PX * porPixel;
      // Una nota es un punto diminuto sobre trazos que suelen ser polígonos
      // grandes: si se probara el trazo primero, dentro de un polígono siempre
      // ganaría el trazo y la nota nunca se podría elegir.
      const nota = notaEnPunto(notas, p, tolerancia);
      const trazo = nota === null ? trazoEnPunto(trazos, p, tolerancia) : null;
      onSeleccionar(
        nota !== null
          ? { tipo: 'nota', id: nota }
          : trazo !== null
            ? { tipo: 'trazo', id: trazo }
            : null,
      );
    } else {
      onPunto(p);
    }
  }

  function alRodar(e: React.WheelEvent<SVGSVGElement>) {
    // Sin `preventDefault` aquí: React registra `wheel` como pasivo. El scroll
    // de la página se evita con `touch-action`/`overscroll` en el CSS del lienzo.
    vistaTocada.current = true;
    const factor = e.deltaY > 0 ? 1.15 : 1 / 1.15;
    setVista((v) => zoomEn(v, factor, aPlano(e.clientX, e.clientY)));
  }

  const radio = 5 * porPixel;
  const dibujando = herramienta !== 'seleccionar'; // incluye la nota: también es un clic de captura

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
        const elegido = seleccion?.tipo === 'trazo' && t.id === seleccion.id;
        const clase = [
          'visor__trazo',
          elegido && 'is-selected',
          t.porRevisar && 'is-por-revisar',
          t.aprobado && 'is-aprobado',
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

      {notas.map((n) => {
        const clase = [
          'visor__nota',
          seleccion?.tipo === 'nota' && n.id === seleccion.id && 'is-selected',
          n.porRevisar && 'is-por-revisar',
        ]
          .filter(Boolean)
          .join(' ');
        const r = radio * 1.6;
        return (
          <g key={n.id} className={clase} data-nota-id={n.id}>
            <title>{n.texto}</title>
            {/* Rombo: se distingue de los marcadores redondos de los puntos. */}
            <path
              d={`M${n.punto[0]} ${n.punto[1] - r}L${n.punto[0] + r} ${n.punto[1]}L${n.punto[0]} ${n.punto[1] + r}L${n.punto[0] - r} ${n.punto[1]}Z`}
            />
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
