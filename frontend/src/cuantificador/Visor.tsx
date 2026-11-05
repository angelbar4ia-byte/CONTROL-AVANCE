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
 *
 * ## Mover la vista
 *
 * La rueda acerca y aleja (centrada en el cursor), y arrastrar con el botón derecho o el del
 * medio mueve el plano con cualquier herramienta, y con la herramienta Mano también el izquierdo.
 * Con Seleccionar, arrastrar con el izquierdo (ratón o lápiz) dibuja una ventana de selección: hacia abajo
 * elige lo que cubre por completo; hacia arriba, lo que toca. En una pantalla táctil, un dedo arrastra el plano y dos dedos
 * lo acercan o alejan (pellizco) con el punto medio como centro. Con la herramienta Zoom un clic acerca y Mayús/Alt + clic aleja.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { Cota, EtiquetaDeMedida } from './etiquetas';
import type { Forma as FormaPrevia } from './dibujo';
import { NOMBRE_DE_REFERENCIA, type Referencia } from './referencias';
import { cajaTransformada, transformacionDeVista, VISTA_NORMAL, vistaDeCaja, type VistaDelPlano } from './vista';

import {
  VISTA_VACIA,
  cajaDePuntos,
  desplazar,
  marcadoresDe,
  puntosDe,
  rutaSvg,
  notaEnPunto,
  partesDe,
  trazoEnPunto,
  trazosEnVentana,
  vistaQueEncuadra,
  zoomEn,
  type GeometriaGeoJson,
  type Herramienta,
  type Punto,
  type TrazoParaVentana,
  type Vista,
} from './geometria';

const UMBRAL_ARRASTRE = 4;
/** Cuánto zoom da cada píxel de rueda: una muesca (100) ≈ 6 %. Antes era un 15 % fijo por evento. */
const SENSIBILIDAD_RUEDA = 0.0006;
const SENSIBILIDAD_PELLIZCO = 0.01;
const MAXIMO_POR_EVENTO = 250;
/** Radio de captura del clic, en píxeles de pantalla. */
const TOLERANCIA_PX = 8;

/** Un vano (puerta, ventana…) sobre un muro: dónde va, hacia dónde corre el muro ahí y cuánto mide de ancho (unidades de plano). */
export interface VanoVisible {
  readonly id: string;
  readonly x: number;
  readonly y: number;
  readonly angulo: number;
  readonly anchoPlano: number;
  readonly clave: string;
  readonly tipo: string;
  readonly piezas: number;
  /** La hoja de una puerta (D-632): extremo de las bisagras (1 inicial, -1 el otro), lado hacia donde abre y grados abierta. */
  readonly bisagra?: number;
  readonly ladoHoja?: number;
  readonly aperturaGrados?: number;
  /** De qué cara del muro se colocó (-1, 0, 1) y su grosor en unidades de plano, para dibujarlo con su cuerpo. */
  readonly ladoMuro?: number;
  readonly grosorPlano?: number;
}

export interface TrazoVisible {
  readonly id: string;
  readonly geometry: GeometriaGeoJson;
  /** Hecho sobre una versión anterior del plano: se dibuja distinto. */
  readonly porRevisar: boolean;
  /** Aprobado por Control de obra: se dibuja en verde. */
  readonly aprobado: boolean;
  /** El color de su medición; sin medición se dibuja con el color de acento. */
  readonly color?: string;
  /** Es de la medición activa (la capa sombra): se dibuja con un halo. */
  readonly resaltado?: boolean;
  /** El cuerpo de una línea con grosor (un muro), ya como anillo en coordenadas de plano. */
  readonly banda?: readonly Punto[];
}

/** Un trazo de la versión anterior del plano, dibujado como fantasma (empalme de versiones). */
export interface TrazoFantasma {
  readonly id: string;
  readonly geometry: GeometriaGeoJson;
}

/** Una propuesta por revisar (conteo o takeoff automático): se ve en naranja y no suma nada. */
export interface PropuestaVisible {
  readonly id: string;
  readonly geometry: GeometriaGeoJson;
  /** Está elegida para aceptarse o rechazarse; una descartada se ve atenuada. */
  readonly elegida: boolean;
}

/** Una zona de la hoja que lleva a otra hoja (enlace entre hojas). */
export interface EnlaceVisible {
  readonly id: string;
  readonly x: number;
  readonly y: number;
  readonly ancho: number;
  readonly alto: number;
  readonly etiqueta: string;
  readonly destinoId: string;
}

export interface NotaVisible {
  readonly id: string;
  readonly punto: Punto;
  readonly texto: string;
  readonly porRevisar: boolean;
  /** `nota` es el rombo; `texto` un rótulo; `flecha` y `llamada` apuntan a `destino`. */
  readonly tipo?: 'nota' | 'texto' | 'flecha' | 'llamada';
  readonly destino?: Punto | null;
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
  /** Huecos ya cerrados del polígono en curso: lo que se descuenta. */
  readonly huecos?: readonly (readonly Punto[])[];
  /** El hueco que se está dibujando ahora. */
  readonly huecoEnCurso?: readonly Punto[];
  /** Un clic de dibujo; `tolerancia` es el radio de captura (8 px de pantalla) en unidades de plano. */
  readonly onPunto: (p: Punto, tolerancia: number) => void;
  /** `agregar`: con Mayús o Ctrl, suma o quita el trazo de la selección en vez de reemplazarla. */
  readonly onSeleccionar: (seleccion: Seleccion | null, agregar?: boolean) => void;
  /** Los demás trazos elegidos (multiselección), además de `seleccion`. */
  readonly seleccionados?: ReadonlySet<string>;
  /** Selección por ventana: los trazos que cubre (arrastrando hacia abajo) o toca (hacia arriba). `agregar`: con Mayús o Ctrl. */
  readonly onSeleccionarVarios?: (ids: readonly string[], agregar: boolean) => void;
  /** El cuerpo de la línea que se está dibujando, si lleva grosor. */
  readonly bandaEnCurso?: readonly Punto[];
  /** La forma que se estamparía bajo el cursor (punto con forma). */
  readonly fantasma?: readonly Punto[];
  /** Puntos numerados, áreas y huecos («Mostrar medidas»). */
  readonly etiquetas?: readonly EtiquetaDeMedida[];
  /** Cotas de cada tramo («Cota»). */
  readonly cotas?: readonly Cota[];
  /** Dónde está el cursor sobre el plano (ya asistido); `null` al salir. Solo si alguien lo pide. */
  readonly onMover?: (p: Punto | null) => void;
  /** Los vanos del plano, dibujados sobre sus muros. */
  readonly vanos?: readonly VanoVisible[];
  /** El vano elegido (Seleccionar): lleva asas para correrlo por su muro y para cambiarle el ancho. */
  readonly vanoElegidoId?: string | null;
  readonly onElegirVano?: (id: string | null) => void;
  /** Se soltó un asa: `desplazamiento` (unidades de plano, a lo largo del muro) o el nuevo `anchoPlano`. */
  readonly onAjustarVano?: (id: string, cambio: { desplazamiento?: number; anchoPlano?: number }) => void;
  /** Dónde está el cursor (plano, sin asistir) para mostrar sus coordenadas; no vuelve a pintar nada por sí mismo. */
  readonly onCoordenadas?: (p: Punto | null) => void;
  /**
   * Clic derecho **sin arrastre** (el arrastre con el derecho mueve el plano): el trazo bajo el cursor, o `null`, y dónde
   * está el cursor en pantalla, para abrir el menú del trazo.
   */
  readonly onMenu?: (trazoId: string | null, x: number, y: number) => void;
  /**
   * La ayuda de dibujo: recibe el punto bajo el cursor y cuánto vale un píxel en el plano, y devuelve
   * el punto al que se pega (ortogonal, referencia a objetos) y a qué referencia. Con ella el visor
   * dibuja la marca de la referencia y pone vértices en el punto ya asistido.
   */
  readonly asistir?: (p: Punto, porPixel: number) => { punto: Punto; referencia: Referencia | null };
  /** La forma que resultaría del trazo en curso (círculo, rectángulo, arco…): vista previa. */
  readonly previa?: FormaPrevia | null;
  /** Los clics del trazo en curso, como marcas sueltas (sin unirlos con una línea). */
  readonly marcas?: readonly Punto[];
  /** Cambia cuando hay que volver a encuadrar (otro plano). */
  readonly claveDePlano: string;
  /** Cómo se ve el plano: girado y/o en espejo. Solo presentación. */
  readonly vistaDelPlano?: VistaDelPlano;
  /** La versión anterior del plano, como fantasma bajo los trazos (empalme de versiones). */
  readonly empalme?: readonly TrazoFantasma[];
  /** Cuánto se corre el fantasma para alinearlo con la versión nueva (unidades de plano). */
  readonly empalmeDesfase?: Punto;
  readonly empalmeElegidoId?: string | null;
  /** Opacidad del fantasma, de 0 a 1. */
  readonly empalmeOpacidad?: number;
  /** Clic en un fantasma con Seleccionar: es el que se va a traer. */
  readonly onElegirFantasma?: (id: string | null) => void;
  /** Zonas que llevan a otra hoja. Con Seleccionar un clic salta; con Borrar, lo quita. */
  readonly enlaces?: readonly EnlaceVisible[];
  readonly onUsarEnlace?: (enlace: EnlaceVisible, accion: 'abrir' | 'quitar') => void;
  /** Trazos propuestos por una herramienta automática. Un clic (con Seleccionar) los descarta o los elige. */
  readonly propuestas?: readonly PropuestaVisible[];
  readonly onAlternarPropuesta?: (id: string) => void;
}

/** El trazo de una flecha de `desde` a `hasta`: el cuerpo y la cabeza (de `cabeza` unidades de largo). */
function flechaHacia(desde: Punto, hasta: Punto, cabeza: number): string {
  const ang = Math.atan2(hasta[1] - desde[1], hasta[0] - desde[0]);
  const lado = (delta: number): string =>
    `L${hasta[0] - cabeza * Math.cos(ang + delta)} ${hasta[1] - cabeza * Math.sin(ang + delta)}`;
  return `M${desde[0]} ${desde[1]}L${hasta[0]} ${hasta[1]}${lado(0.45)}M${hasta[0]} ${hasta[1]}${lado(-0.45)}`;
}

interface Gesto {
  readonly pantallaX: number;
  readonly pantallaY: number;
  readonly vista: Vista;
  movido: boolean;
  /** Botón derecho o del medio: solo mueve la vista, nunca pone un punto. */
  soloMueve: boolean;
  /** El arrastre con Seleccionar dibuja una ventana de selección en vez de mover el plano. */
  ventana?: boolean;
}

export function Visor({
  empalme = [],
  empalmeDesfase = [0, 0],
  empalmeElegidoId = null,
  empalmeOpacidad = 0.55,
  onElegirFantasma,
  enlaces = [],
  onUsarEnlace,
  propuestas = [],
  onAlternarPropuesta,
  fondoUrl,
  trazos,
  notas,
  seleccion,
  seleccionados,
  onSeleccionarVarios,
  herramienta,
  borrador,
  huecos = [],
  huecoEnCurso = [],
  onPunto,
  onSeleccionar,
  bandaEnCurso = [],
  fantasma = [],
  etiquetas = [],
  cotas = [],
  onMover,
  vanos = [],
  vanoElegidoId = null,
  onElegirVano,
  onAjustarVano,
  onCoordenadas,
  onMenu,
  asistir,
  previa = null,
  marcas = [],
  claveDePlano,
  vistaDelPlano = VISTA_NORMAL,
}: Props) {
  const svg = useRef<SVGSVGElement>(null);
  const gesto = useRef<Gesto | null>(null);
  /** La ventana de selección en curso, en coordenadas de vista (las del SVG). */
  const [ventana, setVentana] = useState<{ x0: number; y0: number; x1: number; y1: number; abajo: boolean } | null>(null);
  // Dedos sobre la pantalla (o el ratón): con dos, el gesto es un pellizco que acerca y aleja.
  const punteros = useRef(new Map<number, { x: number; y: number }>());
  const pinza = useRef<{ d0: number; v0: Vista; p0: Punto; m0: { x: number; y: number } } | null>(null);
  const [vista, setVista] = useState<Vista>(VISTA_VACIA);
  const [imagen, setImagen] = useState<{ ancho: number; alto: number } | null>(null);
  const [fondoRoto, setFondoRoto] = useState(false);
  const [anchoPantalla, setAnchoPantalla] = useState(1000);
  const [referencia, setReferencia] = useState<Referencia | null>(null);
  const cuadro = useRef<number | null>(null);

  // El fondo manda en el encuadre: si hay imagen, el plano *es* la imagen. Sin
  // ella (PDF, o R2 sin configurar) se encuadran los trazos.
  const { rotacionGrados, volteoH, volteoV } = vistaDelPlano;
  const T = useMemo(
    () => transformacionDeVista({ rotacionGrados, volteoH, volteoV }),
    [rotacionGrados, volteoH, volteoV],
  );
  const encuadre = useMemo<Vista>(() => {
    if (imagen) {
      return vistaDeCaja(cajaTransformada({ minX: 0, minY: 0, maxX: imagen.ancho, maxY: imagen.alto }, T));
    }
    const caja = cajaDePuntos(trazos.flatMap((t) => puntosDe(t.geometry)));
    if (!caja) return VISTA_VACIA;
    const v = vistaQueEncuadra(caja);
    return vistaDeCaja(
      cajaTransformada({ minX: v.x, minY: v.y, maxX: v.x + v.ancho, maxY: v.y + v.alto }, T),
    );
  }, [imagen, trazos, T]);

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
  }, [claveDePlano, rotacionGrados, volteoH, volteoV]);
  useEffect(() => {
    if (!vistaTocada.current) setVista(encuadreActual.current);
  }, [claveDePlano, imagen, hayTrazos, rotacionGrados, volteoH, volteoV]);

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

  /** Pantalla → coordenadas del `viewBox` (la vista, ya girada si el plano lo está). */
  const aVista = useCallback((clientX: number, clientY: number): Punto => {
    const el = svg.current;
    const matriz = el?.getScreenCTM();
    if (!el || !matriz) return [0, 0];
    const punto = el.createSVGPoint();
    punto.x = clientX;
    punto.y = clientY;
    const p = punto.matrixTransform(matriz.inverse());
    return [p.x, p.y];
  }, []);
  /** Pantalla → coordenadas de plano: la vista, deshecho el giro y el espejo. */
  const aPlano = useCallback(
    (clientX: number, clientY: number): Punto => T.invertir(aVista(clientX, clientY)),
    [aVista, T],
  );

  // Unidades de plano por píxel de pantalla: lo que mantiene los marcadores y la
  // tolerancia del clic del mismo tamaño visual a cualquier zoom.
  const porPixel = vista.ancho / anchoPantalla;

  // Las asas de un vano: lo que se arrastra se ve al instante y se manda al soltar.
  const [arrastreVano, setArrastreVano] = useState<{ id: string; modo: 'mover' | 'ini' | 'fin'; d: number } | null>(null);
  function empezarArrastreVano(e: React.PointerEvent, v: VanoVisible, modo: 'mover' | 'ini' | 'fin') {
    if (e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    const rad = (v.angulo * Math.PI) / 180;
    const [ux, uy] = [Math.cos(rad), Math.sin(rad)];
    const origen = aPlano(e.clientX, e.clientY);
    const minimo = 4 * porPixel;
    let d = 0;
    const limitar = (x: number) => (modo === 'mover' ? x : Math.max(x, -(v.anchoPlano - minimo) / 2));
    const alMover = (ev: PointerEvent) => {
      const q = aPlano(ev.clientX, ev.clientY);
      const bruto = (q[0] - origen[0]) * ux + (q[1] - origen[1]) * uy;
      d = limitar(modo === 'ini' ? -bruto : bruto);
      setArrastreVano({ id: v.id, modo, d });
    };
    const alSoltar = () => {
      window.removeEventListener('pointermove', alMover);
      window.removeEventListener('pointerup', alSoltar);
      setArrastreVano(null);
      if (Math.abs(d) < 1e-9) return;
      onAjustarVano?.(v.id, modo === 'mover' ? { desplazamiento: d } : { anchoPlano: v.anchoPlano + 2 * d });
    };
    window.addEventListener('pointermove', alMover);
    window.addEventListener('pointerup', alSoltar);
  }

  function alPresionar(e: React.PointerEvent<SVGSVGElement>) {
    if (e.button > 2) return;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    punteros.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (punteros.current.size === 2) {
      // El segundo dedo convierte el gesto en pellizco: lo que había empezado ya no es un clic.
      const [a, b] = [...punteros.current.values()] as [{ x: number; y: number }, { x: number; y: number }];
      const m0 = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
      pinza.current = {
        d0: Math.max(1, Math.hypot(a.x - b.x, a.y - b.y)),
        v0: vista,
        p0: aVista(m0.x, m0.y),
        m0,
      };
      if (gesto.current) gesto.current.movido = true;
      return;
    }
    gesto.current = {
      pantallaX: e.clientX,
      pantallaY: e.clientY,
      vista,
      movido: false,
      soloMueve: e.button !== 0,
    };
  }

  function alMover(e: React.PointerEvent<SVGSVGElement>) {
    if (punteros.current.has(e.pointerId)) {
      punteros.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    }
    const pz = pinza.current;
    if (pz && punteros.current.size >= 2) {
      const [a, b] = [...punteros.current.values()] as [{ x: number; y: number }, { x: number; y: number }];
      const d = Math.max(1, Math.hypot(a.x - b.x, a.y - b.y));
      const m = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
      vistaTocada.current = true;
      // Separar los dedos acerca (la vista se hace más chica); el punto que estaba bajo los
      // dedos al empezar sigue bajo ellos aunque se muevan.
      const acercada = zoomEn(pz.v0, pz.d0 / d, pz.p0);
      const k = acercada.ancho / anchoPantalla;
      setVista(desplazar(acercada, (m.x - pz.m0.x) * k, (m.y - pz.m0.y) * k));
      return;
    }
    const g = gesto.current;
    if (!g) {
      // Una sola actualización por cuadro: el cursor manda decenas de eventos por segundo.
      const x = e.clientX;
      const y = e.clientY;
      if (cuadro.current === null) {
        cuadro.current = requestAnimationFrame(() => {
          cuadro.current = null;
          const bruto = aPlano(x, y);
          const asistido = asistir?.(bruto, porPixel);
          setReferencia(asistido?.referencia ?? null);
          onMover?.(asistido ? asistido.punto : bruto);
          onCoordenadas?.(bruto);
        });
      }
      return;
    }
    const dx = e.clientX - g.pantallaX;
    const dy = e.clientY - g.pantallaY;
    if (!g.movido && Math.hypot(dx, dy) < UMBRAL_ARRASTRE) return;
    g.movido = true;
    // Con Seleccionar, el arrastre del botón izquierdo (ratón o lápiz) dibuja una ventana; el plano se mueve con el
    // botón derecho o el del medio, con la herramienta Mano o con un dedo.
    if (onSeleccionarVarios && herramienta === 'seleccionar' && !g.soloMueve && e.pointerType !== 'touch') {
      g.ventana = true;
      const a = aVista(g.pantallaX, g.pantallaY);
      const b = aVista(e.clientX, e.clientY);
      setVentana({ x0: a[0], y0: a[1], x1: b[0], y1: b[1], abajo: e.clientY > g.pantallaY });
      return;
    }
    vistaTocada.current = true;
    const escala = g.vista.ancho / anchoPantalla;
    setVista(desplazar(g.vista, dx * escala, dy * escala));
  }

  function alSoltarPuntero(e: React.PointerEvent<SVGSVGElement>) {
    punteros.current.delete(e.pointerId);
    if (pinza.current) {
      if (punteros.current.size < 2) pinza.current = null;
      gesto.current = null; // el dedo que queda no pone un vértice al levantarse
      return true;
    }
    return false;
  }

  function alSoltar(e: React.PointerEvent<SVGSVGElement>) {
    if (alSoltarPuntero(e)) return;
    const g = gesto.current;
    gesto.current = null;
    if (g && !g.movido && g.soloMueve && e.button === 2 && onMenu) {
      const sobre = trazoEnPunto(trazos, aPlano(e.clientX, e.clientY), TOLERANCIA_PX * porPixel);
      onMenu(sobre, e.clientX, e.clientY);
      return;
    }
    if (g?.ventana && onSeleccionarVarios) {
      const a = aVista(g.pantallaX, g.pantallaY);
      const b = aVista(e.clientX, e.clientY);
      const caja = { minX: Math.min(a[0], b[0]), minY: Math.min(a[1], b[1]), maxX: Math.max(a[0], b[0]), maxY: Math.max(a[1], b[1]) };
      // Los puntos de cada trazo, en coordenadas de vista (con el giro y el espejo aplicados).
      const candidatos: TrazoParaVentana[] = trazos.flatMap((t) =>
        partesDe(t.geometry)
          .filter((parte) => !parte.hueco)
          .map((parte) => ({ id: t.id, puntos: parte.puntos.map((q) => T.aplicar(q)), cerrada: parte.tipo === 'anillo' })),
      );
      const ids = [...new Set(trazosEnVentana(candidatos, caja, e.clientY > g.pantallaY))];
      setVentana(null);
      onSeleccionarVarios(ids, e.shiftKey || e.ctrlKey || e.metaKey);
      return;
    }
    if (!g || g.movido || g.soloMueve) return;
    const bruto = aPlano(e.clientX, e.clientY);
    const p = asistir && !['seleccionar', 'borrar', 'mano', 'zoom'].includes(herramienta) ? asistir(bruto, porPixel).punto : bruto;
    if (herramienta === 'mano') return;
    if (herramienta === 'zoom') {
      vistaTocada.current = true;
      const factor = e.shiftKey || e.altKey ? 1.5 : 1 / 1.5;
      setVista((v) => zoomEn(v, factor, T.aplicar(p)));
      return;
    }
    if (herramienta === 'seleccionar' || herramienta === 'borrar') {
      const tolerancia = TOLERANCIA_PX * porPixel;
      // Una nota es un punto diminuto sobre trazos que suelen ser polígonos
      // grandes: si se probara el trazo primero, dentro de un polígono siempre
      // ganaría el trazo y la nota nunca se podría elegir.
      if (herramienta === 'seleccionar') onElegirVano?.(null);
      const nota = notaEnPunto(notas, p, tolerancia);
      const trazo = nota === null ? trazoEnPunto(trazos, p, tolerancia) : null;
      onSeleccionar(
        nota !== null
          ? { tipo: 'nota', id: nota }
          : trazo !== null
            ? { tipo: 'trazo', id: trazo }
            : null,
        herramienta === 'seleccionar' && (e.shiftKey || e.ctrlKey || e.metaKey),
      );
    } else {
      onPunto(p, TOLERANCIA_PX * 1.75 * porPixel);
    }
  }

  // La rueda acerca o aleja con el cursor como centro. Se registra a mano, no con `onWheel` de
  // React: React la registra como pasiva y entonces `preventDefault` no frena el desplazamiento
  // de la página, que es lo que haría saltar el plano al hacer zoom.
  useEffect(() => {
    const el = svg.current;
    if (!el) return;
    function alRodar(e: WheelEvent) {
      e.preventDefault();
      vistaTocada.current = true;
      // El zoom sigue a lo que se rueda, no a cuántos eventos llegan: una muesca del ratón
      // (deltaY ≈ 100) acerca o aleja ~6 %, y un trackpad, que manda muchos eventos chicos,
      // se siente continuo. El pellizco del trackpad llega como Ctrl + rueda, con deltas más
      // chicos todavía, y se amplifica.
      const pixeles = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaMode === 2 ? e.deltaY * 400 : e.deltaY;
      const sensibilidad = e.ctrlKey ? SENSIBILIDAD_PELLIZCO : SENSIBILIDAD_RUEDA;
      const factor = Math.exp(Math.max(-MAXIMO_POR_EVENTO, Math.min(MAXIMO_POR_EVENTO, pixeles)) * sensibilidad);
      setVista((v) => zoomEn(v, factor, aVista(e.clientX, e.clientY)));
    }
    el.addEventListener('wheel', alRodar, { passive: false });
    return () => el.removeEventListener('wheel', alRodar);
  }, [aVista]);

  const radio = 5 * porPixel;
  const cursor =
    herramienta === 'seleccionar' || herramienta === 'mano'
      ? 'grab'
      : herramienta === 'zoom'
        ? 'zoom-in'
        : herramienta === 'borrar'
          ? 'pointer'
          : 'crosshair'; // el resto captura un punto con el clic (incluida la nota)
  const px = porPixel;

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
      onPointerCancel={(e) => {
        alSoltarPuntero(e);
        gesto.current = null;
        setVentana(null);
      }}
      onPointerLeave={() => {
        setReferencia(null);
        onMover?.(null);
        onCoordenadas?.(null);
      }}
      onContextMenu={(e) => e.preventDefault()}
      style={{ cursor }}
    >
      <g transform={T.svg} data-testid="plano-girado" data-rotacion={rotacionGrados} data-volteo={`${volteoH ? 'h' : ''}${volteoV ? 'v' : ''}`}>
      {fondoUrl && imagen && !fondoRoto && (
        <image href={fondoUrl} x={0} y={0} width={imagen.ancho} height={imagen.alto} />
      )}

      {empalme.length > 0 && (
        <g
          className="visor__empalme"
          transform={`translate(${empalmeDesfase[0]} ${empalmeDesfase[1]})`}
          data-testid="empalme"
          style={{ opacity: empalmeOpacidad }}
        >
          {empalme.map((f) => (
            <g
              key={f.id}
              className={f.id === empalmeElegidoId ? 'visor__fantasma is-elegido' : 'visor__fantasma'}
              data-fantasma-id={f.id}
              onPointerDown={(e) => {
                // El visor captura el puntero al presionar y el clic ya no llega al fantasma: se elige aquí.
                if (herramienta !== 'seleccionar' || e.button !== 0) return;
                e.stopPropagation();
                onElegirFantasma?.(f.id === empalmeElegidoId ? null : f.id);
              }}
            >
              <path className="visor__fantasma-zona" d={rutaSvg(f.geometry)} vectorEffect="non-scaling-stroke" />
              <path d={rutaSvg(f.geometry)} vectorEffect="non-scaling-stroke" />
              {marcadoresDe(f.geometry).map((m, i) => (
                <circle key={i} cx={m[0]} cy={m[1]} r={radio} />
              ))}
            </g>
          ))}
        </g>
      )}

      {propuestas.map((pr) => (
        <g
          key={pr.id}
          className={pr.elegida ? 'visor__propuesta' : 'visor__propuesta is-descartada'}
          data-propuesta-id={pr.id}
          onPointerDown={(ev) => {
            if (ev.button !== 0 || herramienta !== 'seleccionar') return;
            ev.stopPropagation();
            onAlternarPropuesta?.(pr.id);
          }}
        >
          <path className="visor__propuesta-zona" d={rutaSvg(pr.geometry)} vectorEffect="non-scaling-stroke" />
          <path d={rutaSvg(pr.geometry)} vectorEffect="non-scaling-stroke" />
          {marcadoresDe(pr.geometry).map((m, i) => (
            <circle key={i} cx={m[0]} cy={m[1]} r={radio * 1.2} />
          ))}
        </g>
      ))}

      {enlaces.map((e) => (
        <g
          key={e.id}
          className="visor__enlace"
          data-enlace-id={e.id}
          onPointerDown={(ev) => {
            // Un clic en la zona salta a la otra hoja (Seleccionar) o la quita (Borrar).
            if (ev.button !== 0 || (herramienta !== 'seleccionar' && herramienta !== 'borrar')) return;
            ev.stopPropagation();
            onUsarEnlace?.(e, herramienta === 'borrar' ? 'quitar' : 'abrir');
          }}
        >
          <title>{e.etiqueta}</title>
          <rect x={e.x} y={e.y} width={e.ancho} height={e.alto} vectorEffect="non-scaling-stroke" />
          <text x={e.x + 4 * px} y={e.y + 14 * px} fontSize={12 * px} transform={T.contragiro(e.x + 4 * px, e.y + 14 * px)}>
            {e.etiqueta} ↗
          </text>
        </g>
      ))}

      {trazos.map((t) => {
        const elegido = (seleccion?.tipo === 'trazo' && t.id === seleccion.id) || (seleccionados?.has(t.id) ?? false);
        const clase = [
          'visor__trazo',
          elegido && 'is-selected',
          t.porRevisar && 'is-por-revisar',
          t.aprobado && 'is-aprobado',
          t.resaltado && 'is-medicion',
        ]
          .filter(Boolean)
          .join(' ');
        return (
          <g key={t.id} className={clase} data-trazo-id={t.id} style={t.color ? { ['--c-trazo' as string]: t.color } : undefined}>
            {t.banda && t.banda.length > 2 && (
              <polygon
                className="visor__banda"
                points={t.banda.map((q) => `${q[0]},${q[1]}`).join(' ')}
                vectorEffect="non-scaling-stroke"
              />
            )}
            <path d={rutaSvg(t.geometry)} vectorEffect="non-scaling-stroke" />
            {marcadoresDe(t.geometry).map((m, i) => (
              <circle key={i} cx={m[0]} cy={m[1]} r={radio} />
            ))}
          </g>
        );
      })}

      <g className="visor__vanos" data-testid="vanos">
        {vanos.map((v) => {
          const alto = Math.max(10 * px, v.grosorPlano ?? 0);
          // Con el ancla transversal el vano se corre hacia la cara donde cayó el clic (el eje local y sigue al muro).
          const direccion = Math.cos((v.angulo * Math.PI) / 180);
          const haciaDerecha = direccion > 1e-9 || (Math.abs(direccion) <= 1e-9 && Math.sin((v.angulo * Math.PI) / 180) > 0);
          const corrimiento = (v.ladoMuro ?? 0) * ((v.grosorPlano ?? 0) / 2) * (haciaDerecha ? 1 : -1);
          const elegido = vanoElegidoId === v.id;
          const enArrastre = arrastreVano?.id === v.id ? arrastreVano : null;
          // Mientras se arrastra, el vano ya se ve en su lugar nuevo (a lo largo del muro) o con el ancho nuevo.
          const desvio = enArrastre?.modo === 'mover' ? enArrastre.d : 0;
          const ancho = enArrastre && enArrastre.modo !== 'mover' ? v.anchoPlano + 2 * enArrastre.d : v.anchoPlano;
          return (
            <g
              key={v.id}
              data-vano-id={v.id}
              data-tipo={v.tipo}
              className={elegido ? 'visor__vano-grupo is-elegido' : 'visor__vano-grupo'}
              onPointerDown={(e) => {
                if (herramienta !== 'seleccionar' || e.button !== 0) return;
                e.stopPropagation();
                onElegirVano?.(v.id);
              }}
            >
              <g transform={`translate(${v.x} ${v.y}) rotate(${v.angulo}) translate(${desvio} ${corrimiento})`}>
                <rect className="visor__vano-zona" x={-ancho / 2} y={-alto / 2} width={ancho} height={alto} />
                <rect
                  className={v.tipo === 'ventana' ? 'visor__vano visor__vano--ventana' : 'visor__vano'}
                  x={-ancho / 2}
                  y={-alto / 2}
                  width={ancho}
                  height={alto}
                  vectorEffect="non-scaling-stroke"
                />
                {v.tipo === 'puerta' && (v.aperturaGrados ?? 90) > 0 && (() => {
                  // La hoja: del eje de las bisagras gira `apertura` hacia el lado en que abre, con el arco que barre.
                  const w = ancho;
                  const sentido = (v.bisagra ?? 1) === 1 ? 1 : -1;
                  const lado = (v.ladoHoja ?? 1) === 1 ? 1 : -1;
                  const rad = ((v.aperturaGrados ?? 90) * Math.PI) / 180;
                  const bx = -sentido * (w / 2);
                  const fx = bx + sentido * w * Math.cos(rad);
                  const fy = lado * w * Math.sin(rad);
                  const cerrada = bx + sentido * w;
                  const barrido = sentido * lado > 0 ? 1 : 0;
                  return (
                    <g data-hoja={v.id} fill="none">
                      <line className="visor__vano" x1={bx} y1={0} x2={fx} y2={fy} vectorEffect="non-scaling-stroke" />
                      <path className="visor__vano" d={`M ${cerrada} 0 A ${w} ${w} 0 0 ${barrido} ${fx} ${fy}`} vectorEffect="non-scaling-stroke" strokeDasharray="3 3" />
                    </g>
                  );
                })()}
                {elegido && herramienta === 'seleccionar' && (
                  <g className="visor__asas">
                    <circle className="visor__asa" data-asa="ini" cx={-ancho / 2} cy={0} r={5 * px} vectorEffect="non-scaling-stroke" onPointerDown={(e) => empezarArrastreVano(e, v, 'ini')} />
                    <circle className="visor__asa" data-asa="fin" cx={ancho / 2} cy={0} r={5 * px} vectorEffect="non-scaling-stroke" onPointerDown={(e) => empezarArrastreVano(e, v, 'fin')} />
                    <circle className="visor__asa visor__asa--centro" data-asa="mover" cx={0} cy={0} r={5 * px} vectorEffect="non-scaling-stroke" onPointerDown={(e) => empezarArrastreVano(e, v, 'mover')} />
                  </g>
                )}
              </g>
              <text
                className="visor__rotulo"
                x={v.x}
                y={v.y - 9 * px}
                textAnchor="middle"
                fontSize={10 * px}
                transform={T.contragiro(v.x, v.y - 9 * px)}
              >
                {v.piezas > 1 ? `${v.piezas}× ` : ''}
                {v.clave}
              </text>
            </g>
          );
        })}
      </g>

      {notas.map((n) => {
        const clase = [
          'visor__nota',
          seleccion?.tipo === 'nota' && n.id === seleccion.id && 'is-selected',
          n.porRevisar && 'is-por-revisar',
        ]
          .filter(Boolean)
          .join(' ');
        const r = radio * 1.6;
        const tipo = n.tipo ?? 'nota';
        if (tipo !== 'nota') {
          const cuerpo = n.destino ? flechaHacia(n.punto, n.destino, 11 * px) : null;
          return (
            <g key={n.id} className={`${clase} visor__anotacion`} data-nota-id={n.id} data-tipo={tipo}>
              <title>{n.texto || 'Flecha'}</title>
              {cuerpo && <path d={cuerpo} className="visor__flecha" />}
              {tipo !== 'flecha' && n.texto && (
                <text x={n.punto[0]} y={n.punto[1]} fontSize={13 * px} className="visor__rotulo" transform={T.contragiro(n.punto[0], n.punto[1])}>
                  {n.texto}
                </text>
              )}
            </g>
          );
        }
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

      {(huecos.length > 0 || huecoEnCurso.length > 0) && (
        <g className="visor__hueco" data-testid="huecos">
          {huecos.map((h, i) => (
            <polygon
              key={i}
              points={h.map((p) => `${p[0]},${p[1]}`).join(' ')}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {huecoEnCurso.length > 0 && (
            <polyline
              points={huecoEnCurso.map((p) => `${p[0]},${p[1]}`).join(' ')}
              vectorEffect="non-scaling-stroke"
            />
          )}
          {[...huecos.flat(), ...huecoEnCurso].map((p, i) => (
            <circle key={i} cx={p[0]} cy={p[1]} r={radio} />
          ))}
        </g>
      )}

      {bandaEnCurso.length > 2 && (
        <polygon
          className="visor__banda is-borrador"
          points={bandaEnCurso.map((q) => `${q[0]},${q[1]}`).join(' ')}
          vectorEffect="non-scaling-stroke"
        />
      )}

      {fantasma.length > 2 && (
        <polygon
          className="visor__fantasma"
          data-testid="fantasma"
          points={fantasma.map((q) => `${q[0]},${q[1]}`).join(' ')}
          vectorEffect="non-scaling-stroke"
        />
      )}

      {cotas.length > 0 && (
        <g className="visor__cotas" data-testid="cotas" fontSize={11 * px}>
          {cotas.map((c, i) => {
            const dx = c.b[0] - c.a[0];
            const dy = c.b[1] - c.a[1];
            const largo = Math.hypot(dx, dy) || 1;
            // La cota va desplazada del trazo para no taparlo: 12 px hacia la izquierda del tramo.
            const nx = (dy / largo) * 12 * px;
            const ny = (-dx / largo) * 12 * px;
            const a = [c.a[0] + nx, c.a[1] + ny];
            const b = [c.b[0] + nx, c.b[1] + ny];
            const mx = (a[0]! + b[0]!) / 2;
            const my = (a[1]! + b[1]!) / 2;
            const ang = T.anguloEnPantalla(c.a, c.b);
            const demasiadoCorta = largo < 28 * px;
            return (
              <g key={i}>
                <line x1={c.a[0]} y1={c.a[1]} x2={a[0]} y2={a[1]} vectorEffect="non-scaling-stroke" />
                <line x1={c.b[0]} y1={c.b[1]} x2={b[0]} y2={b[1]} vectorEffect="non-scaling-stroke" />
                <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} vectorEffect="non-scaling-stroke" />
                {!demasiadoCorta && (
                  <text x={mx} y={my} textAnchor="middle" dy={-3 * px} transform={T.contragiro(mx!, my!, ang)}>
                    {c.texto}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      )}

      {etiquetas.length > 0 && (
        <g className="visor__etiquetas" data-testid="etiquetas" fontSize={11 * px}>
          {etiquetas.map((e, i) =>
            e.tipo === 'punto' ? (
              <g key={i} className="visor__vertice" data-testid="punto-numerado">
                <circle cx={e.punto[0]} cy={e.punto[1]} r={7 * px} />
                <text x={e.punto[0]} y={e.punto[1]} textAnchor="middle" dominantBaseline="central" fontSize={9 * px} transform={T.contragiro(e.punto[0], e.punto[1])}>
                  {e.texto}
                </text>
              </g>
            ) : e.titulo ? (
              <RotuloDeMedida key={i} e={e} px={px} contragiro={T.contragiro(e.punto[0], e.punto[1])} />
            ) : (
              <text
                key={i}
                className={`visor__etiqueta visor__etiqueta--${e.tipo}`}
                x={e.punto[0]}
                y={e.punto[1]}
                textAnchor="middle"
                dominantBaseline="central"
                style={{ strokeWidth: 3 * px }}
                transform={T.contragiro(e.punto[0], e.punto[1])}
              >
                {e.texto}
              </text>
            ),
          )}
        </g>
      )}

      {previa && previa.puntos.length > 1 && (
        <g className="visor__previa" data-testid="previa">
          {previa.tipo === 'poligono' ? (
            <polygon points={previa.puntos.map((q) => `${q[0]},${q[1]}`).join(' ')} vectorEffect="non-scaling-stroke" />
          ) : (
            <polyline points={previa.puntos.map((q) => `${q[0]},${q[1]}`).join(' ')} vectorEffect="non-scaling-stroke" />
          )}
        </g>
      )}

      {marcas.length > 0 && (
        <g className="visor__borrador" data-testid="marcas">
          {marcas.map((p, i) => (
            <circle key={i} cx={p[0]} cy={p[1]} r={radio * (i === 0 ? 1.4 : 1)} />
          ))}
        </g>
      )}

      {referencia && (
        <g className="visor__referencia" data-testid="referencia" data-tipo={referencia.tipo}>
          {marcaDeReferencia(referencia, 7 * porPixel)}
          <text x={referencia.punto[0] + 10 * porPixel} y={referencia.punto[1] - 10 * porPixel} fontSize={11 * porPixel} style={{ strokeWidth: 3 * porPixel }} transform={T.contragiro(referencia.punto[0] + 10 * porPixel, referencia.punto[1] - 10 * porPixel)}>
            {NOMBRE_DE_REFERENCIA[referencia.tipo]}
          </text>
        </g>
      )}

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
      </g>
      {ventana && (
        <rect
          className={ventana.abajo ? 'visor__ventana' : 'visor__ventana visor__ventana--toca'}
          data-testid="ventana-de-seleccion"
          x={Math.min(ventana.x0, ventana.x1)}
          y={Math.min(ventana.y0, ventana.y1)}
          width={Math.abs(ventana.x1 - ventana.x0)}
          height={Math.abs(ventana.y1 - ventana.y0)}
          vectorEffect="non-scaling-stroke"
        />
      )}
    </svg>
  );
}

/** El símbolo de cada referencia, como en un programa de dibujo: cuadro, triángulo, círculo, equis… */
function marcaDeReferencia(r: Referencia, t: number) {
  const [x, y] = r.punto;
  switch (r.tipo) {
    case 'extremo':
      return <rect x={x - t} y={y - t} width={2 * t} height={2 * t} vectorEffect="non-scaling-stroke" />;
    case 'medio':
      return <polygon points={`${x},${y - t} ${x + t},${y + t} ${x - t},${y + t}`} vectorEffect="non-scaling-stroke" />;
    case 'centro':
      return <circle cx={x} cy={y} r={t} vectorEffect="non-scaling-stroke" />;
    case 'interseccion':
      return <path d={`M${x - t} ${y - t}L${x + t} ${y + t}M${x - t} ${y + t}L${x + t} ${y - t}`} vectorEffect="non-scaling-stroke" />;
    case 'perpendicular':
      return <path d={`M${x - t} ${y + t}L${x - t} ${y - t}L${x + t} ${y - t}M${x - t} ${y}L${x} ${y}L${x} ${y - t}`} vectorEffect="non-scaling-stroke" />;
    case 'cercano':
      return <path d={`M${x - t} ${y - t}L${x + t} ${y - t}L${x - t} ${y + t}L${x + t} ${y + t}Z`} vectorEffect="non-scaling-stroke" />;
  }
}

/**
 * La etiqueta de una medida con lo que se mide: arriba, en chico, «clave y concepto · matriz · medición»; debajo,
 * la medida. Una píldora con el color de la medición a la izquierda, para leerla sin abrir nada.
 */
function RotuloDeMedida({ e, px, contragiro }: { readonly e: EtiquetaDeMedida; readonly px: number; readonly contragiro: string | undefined }) {
  const titulo = e.titulo ?? '';
  const ancho = (Math.max(titulo.length * 0.92, e.texto.length * 1.25) * 6.2 + 22) * px;
  const alto = 33 * px;
  const x = e.punto[0] - ancho / 2;
  const y = e.punto[1] - alto / 2;
  return (
    <g className="visor__rotulo-medida" data-testid="rotulo-de-medida" transform={contragiro} style={e.color ? { ['--c-rotulo' as string]: e.color } : undefined}>
      <rect className="visor__rotulo-caja" x={x} y={y} width={ancho} height={alto} rx={7 * px} ry={7 * px} style={{ strokeWidth: 1.2 * px }} />
      <rect className="visor__rotulo-barra" x={x} y={y} width={5 * px} height={alto} rx={2.5 * px} />
      <text className="visor__rotulo-titulo" x={x + 13 * px} y={y + 12 * px} fontSize={8.6 * px}>
        {titulo}
      </text>
      <text className={`visor__rotulo-valor visor__etiqueta--${e.tipo}`} x={x + 13 * px} y={y + 26 * px} fontSize={12.5 * px}>
        {e.texto}
      </text>
    </g>
  );
}
