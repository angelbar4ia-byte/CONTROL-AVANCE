/**
 * La barra de herramientas del cuantificador: iconos, no botones con nombre.
 *
 * Cada botón lleva el nombre como `aria-label` y como `title` (el tooltip del navegador), así que
 * un lector de pantalla y quien pasa el cursor leen lo mismo que antes decía el botón. Las
 * herramientas son una a la vez (`aria-pressed`) y van en grupos: moverse y elegir, dibujar, y
 * medir. Lo que no dibuja ni mueve —mostrar medidas, cotas, filtrar, calcular volumen, el cuadro
 * de datos— son interruptores aparte: se encienden sin cambiar la herramienta activa.
 */

import {
  ArrowLeftRight,
  Box,
  Circle,
  Eraser,
  Eye,
  Hand,
  Hash,
  MapPin,
  MousePointer,
  Pentagon,
  Redo2,
  RectangleHorizontal,
  Ruler,
  Spline,
  SquareMinus,
  Slash,
  StickyNote,
  Table2,
  Trash2,
  Undo2,
  ZoomIn,
  type LucideIcon,
} from 'lucide-react';

import type { Herramienta } from './geometria';

function IconoElipse({ size = 24, strokeWidth = 2 }: { size?: number | string; strokeWidth?: number | string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <ellipse cx="12" cy="12" rx="10" ry="6" transform="rotate(-25 12 12)" />
    </svg>
  );
}

function IconoArco({ size = 24, strokeWidth = 2 }: { size?: number | string; strokeWidth?: number | string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M4 19a9 9 0 0 1 16 0" />
      <circle cx="4" cy="19" r="1.4" />
      <circle cx="20" cy="19" r="1.4" />
    </svg>
  );
}

/** Un icono: los de lucide y los pocos que ahí no hay (elipse, arco). */
type Icono = LucideIcon | typeof IconoElipse;

const ICONOS: Record<Herramienta, Icono> = {
  seleccionar: MousePointer,
  mano: Hand,
  zoom: ZoomIn,
  poligono: Pentagon,
  linea: Slash,
  polilinea: Spline,
  arco: IconoArco,
  rectangulo: RectangleHorizontal,
  circulo: Circle,
  elipse: IconoElipse,
  punto: MapPin,
  hueco: SquareMinus,
  borrar: Eraser,
  escala: Ruler,
  nota: StickyNote,
};

export const ETIQUETAS: Record<Herramienta, string> = {
  seleccionar: 'Seleccionar',
  mano: 'Mano',
  zoom: 'Zoom',
  poligono: 'Polígono',
  linea: 'Línea',
  polilinea: 'Polilínea',
  arco: 'Arco',
  rectangulo: 'Rectángulo',
  circulo: 'Círculo',
  elipse: 'Elipse',
  punto: 'Punto',
  hueco: 'Hueco',
  borrar: 'Borrar',
  escala: 'Calibrar escala',
  nota: 'Nota',
};

export const ATAJOS: Record<Herramienta, string> = {
  seleccionar: 'V',
  mano: 'H',
  zoom: 'Z',
  poligono: 'P',
  linea: 'L',
  polilinea: 'Y',
  arco: 'A',
  rectangulo: 'R',
  circulo: 'I',
  elipse: 'J',
  punto: 'O',
  hueco: 'U',
  borrar: 'B',
  escala: 'E',
  nota: 'N',
};

const GRUPOS: readonly (readonly Herramienta[])[] = [
  ['seleccionar', 'mano', 'zoom'],
  ['linea', 'polilinea', 'arco', 'poligono', 'rectangulo', 'circulo', 'elipse'],
  ['punto', 'hueco', 'nota', 'borrar'],
  ['escala'],
];

export interface Accion {
  readonly clave: 'deshacer' | 'rehacer' | 'eliminar';
  readonly etiqueta: string;
  readonly deshabilitado: boolean;
  readonly descripcion: string;
  readonly onClick: () => void;
}

export type ClaveDeInterruptor = 'medidas' | 'cotas' | 'soloElegidos' | 'volumen' | 'datos';

export interface Interruptor {
  readonly clave: ClaveDeInterruptor;
  readonly activo: boolean;
  readonly deshabilitado?: boolean;
  readonly atajo?: string;
  /** Qué hace, o por qué no se puede ahora (es lo que dice el tooltip). */
  readonly descripcion?: string;
}

const INTERRUPTORES: Record<ClaveDeInterruptor, { etiqueta: string; icono: Icono }> = {
  medidas: { etiqueta: 'Mostrar medidas', icono: Hash },
  cotas: { etiqueta: 'Cota', icono: ArrowLeftRight },
  soloElegidos: { etiqueta: 'Solo los trazos de los conceptos elegidos', icono: Eye },
  volumen: { etiqueta: 'Calcular volumen', icono: Box },
  datos: { etiqueta: 'Cuadro de datos', icono: Table2 },
};

interface Props {
  readonly herramientas: readonly Herramienta[];
  readonly activa: Herramienta;
  readonly onElegir: (h: Herramienta) => void;
  /** Herramientas que ahora no se pueden usar, con la razón (el tooltip). */
  readonly deshabilitadas?: Readonly<Partial<Record<Herramienta, string>>>;
  readonly interruptores: readonly Interruptor[];
  /** Deshacer y rehacer: van arriba de todo. */
  readonly historial?: readonly Accion[];
  /** Acciones que se disparan una vez (no se quedan encendidas): eliminar lo elegido. */
  readonly acciones?: readonly Accion[];
  readonly onAlternar: (clave: ClaveDeInterruptor) => void;
  readonly orientacion?: 'vertical' | 'horizontal';
}

function Boton({
  etiqueta,
  Icono,
  activo,
  onClick,
  deshabilitado,
  titulo,
}: {
  readonly etiqueta: string;
  readonly Icono: Icono;
  readonly activo: boolean;
  readonly onClick: () => void;
  readonly deshabilitado?: boolean;
  readonly titulo: string;
}) {
  return (
    <button
      type="button"
      className={activo ? 'btn-icono is-activo' : 'btn-icono'}
      aria-label={etiqueta}
      aria-pressed={activo}
      title={titulo}
      disabled={deshabilitado}
      onClick={onClick}
    >
      <Icono size={17} strokeWidth={1.7} aria-hidden />
    </button>
  );
}

export function BarraDeHerramientas({
  herramientas,
  activa,
  onElegir,
  deshabilitadas = {},
  interruptores,
  historial = [],
  acciones = [],
  onAlternar,
  orientacion = 'vertical',
}: Props) {
  const grupos = GRUPOS.map((g) => g.filter((h) => herramientas.includes(h))).filter((g) => g.length > 0);
  return (
    <div
      className={`barra-iconos barra-iconos--${orientacion}`}
      role="toolbar"
      aria-label="Herramientas de trazo"
      aria-orientation={orientacion}
    >
      {historial.length > 0 && (
        <div className="barra-iconos__grupo" role="group">
          {historial.map((a) => (
            <button
              key={a.clave}
              type="button"
              className="btn-icono"
              aria-label={a.etiqueta}
              title={a.descripcion}
              disabled={a.deshabilitado}
              onClick={a.onClick}
            >
              {a.clave === 'deshacer' ? <Undo2 size={17} strokeWidth={1.7} aria-hidden /> : <Redo2 size={17} strokeWidth={1.7} aria-hidden />}
            </button>
          ))}
        </div>
      )}
      {grupos.map((grupo, i) => (
        <div key={i} className="barra-iconos__grupo" role="group">
          {(i > 0 || historial.length > 0) && <span className="barra-iconos__sep" role="separator" />}
          {grupo.map((h) => (
            <Boton
              key={h}
              etiqueta={ETIQUETAS[h]}
              Icono={ICONOS[h]}
              activo={activa === h}
              deshabilitado={deshabilitadas[h] !== undefined}
              titulo={deshabilitadas[h] ?? `${ETIQUETAS[h]} (${ATAJOS[h]})`}
              onClick={() => onElegir(h)}
            />
          ))}
        </div>
      ))}
      <div className="barra-iconos__grupo" role="group">
        <span className="barra-iconos__sep" role="separator" />
        {interruptores.map((i) => {
          const { etiqueta, icono } = INTERRUPTORES[i.clave];
          return (
            <Boton
              key={i.clave}
              etiqueta={etiqueta}
              Icono={icono}
              activo={i.activo}
              deshabilitado={i.deshabilitado}
              titulo={i.descripcion ?? (i.atajo ? `${etiqueta} (${i.atajo})` : etiqueta)}
              onClick={() => onAlternar(i.clave)}
            />
          );
        })}
      </div>
      {acciones.length > 0 && (
        <div className="barra-iconos__grupo" role="group">
          <span className="barra-iconos__sep" role="separator" />
          {acciones.map((a) => (
            <button
              key={a.clave}
              type="button"
              className="btn-icono btn-icono--peligro"
              aria-label={a.etiqueta}
              title={a.descripcion}
              disabled={a.deshabilitado}
              onClick={a.onClick}
            >
              <Trash2 size={17} strokeWidth={1.7} aria-hidden />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
