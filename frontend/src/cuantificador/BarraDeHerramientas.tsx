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
  Eye,
  Hand,
  Hash,
  MapPin,
  MousePointer,
  Pentagon,
  Ruler,
  Spline,
  SquareMinus,
  StickyNote,
  Table2,
  ZoomIn,
  type LucideIcon,
} from 'lucide-react';

import type { Herramienta } from './geometria';

const ICONOS: Record<Herramienta, LucideIcon> = {
  seleccionar: MousePointer,
  mano: Hand,
  zoom: ZoomIn,
  poligono: Pentagon,
  linea: Spline,
  punto: MapPin,
  hueco: SquareMinus,
  escala: Ruler,
  nota: StickyNote,
};

export const ETIQUETAS: Record<Herramienta, string> = {
  seleccionar: 'Seleccionar',
  mano: 'Mano',
  zoom: 'Zoom',
  poligono: 'Polígono',
  linea: 'Línea',
  punto: 'Punto',
  hueco: 'Hueco',
  escala: 'Calibrar escala',
  nota: 'Nota',
};

export const ATAJOS: Record<Herramienta, string> = {
  seleccionar: 'V',
  mano: 'H',
  zoom: 'Z',
  poligono: 'P',
  linea: 'L',
  punto: 'O',
  hueco: 'U',
  escala: 'E',
  nota: 'N',
};

const GRUPOS: readonly (readonly Herramienta[])[] = [
  ['seleccionar', 'mano', 'zoom'],
  ['poligono', 'linea', 'punto', 'hueco', 'nota'],
  ['escala'],
];

export type ClaveDeInterruptor = 'medidas' | 'cotas' | 'soloElegidos' | 'volumen' | 'datos';

export interface Interruptor {
  readonly clave: ClaveDeInterruptor;
  readonly activo: boolean;
  readonly deshabilitado?: boolean;
  readonly atajo?: string;
  /** Qué hace, o por qué no se puede ahora (es lo que dice el tooltip). */
  readonly descripcion?: string;
}

const INTERRUPTORES: Record<ClaveDeInterruptor, { etiqueta: string; icono: LucideIcon }> = {
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
  readonly Icono: LucideIcon;
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
      {grupos.map((grupo, i) => (
        <div key={i} className="barra-iconos__grupo" role="group">
          {i > 0 && <span className="barra-iconos__sep" role="separator" />}
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
    </div>
  );
}
