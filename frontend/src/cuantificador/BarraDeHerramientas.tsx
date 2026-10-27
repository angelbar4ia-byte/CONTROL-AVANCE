/**
 * La barra de herramientas del cuantificador: iconos, no botones con nombre.
 *
 * Cada botón lleva el nombre como `aria-label` y como `title` (el tooltip del
 * navegador), así que un lector de pantalla y quien pasa el cursor leen lo mismo
 * que antes decía el botón. Las herramientas de trazo son una a la vez
 * (`aria-pressed`); «Solo los conceptos elegidos» y «Calcular volumen» son
 * interruptores aparte: no dibujan, así que no sustituyen a la herramienta activa.
 */

import {
  Box,
  Eye,
  MapPin,
  MousePointer,
  Pentagon,
  Ruler,
  Spline,
  StickyNote,
  type LucideIcon,
} from 'lucide-react';

import type { Herramienta } from './geometria';

const ICONOS: Record<Herramienta, LucideIcon> = {
  seleccionar: MousePointer,
  poligono: Pentagon,
  linea: Spline,
  punto: MapPin,
  escala: Ruler,
  nota: StickyNote,
};

const ETIQUETAS: Record<Herramienta, string> = {
  seleccionar: 'Seleccionar',
  poligono: 'Polígono',
  linea: 'Línea',
  punto: 'Punto',
  escala: 'Calibrar escala',
  nota: 'Nota',
};

const ATAJOS: Record<Herramienta, string> = {
  seleccionar: 'V',
  poligono: 'P',
  linea: 'L',
  punto: 'O',
  escala: 'E',
  nota: 'N',
};

interface Props {
  readonly herramientas: readonly Herramienta[];
  readonly activa: Herramienta;
  readonly onElegir: (h: Herramienta) => void;
  /** «Solo los trazos de los conceptos elegidos»; `undefined` oculta el botón. */
  readonly soloElegidos?: boolean;
  readonly onAlternarSoloElegidos?: () => void;
  /** Hay conceptos elegidos en el árbol: sin ellos el filtro no tiene nada que mostrar. */
  readonly hayElegidos?: boolean;
  readonly volumenAbierto?: boolean;
  readonly onAlternarVolumen?: () => void;
  readonly orientacion?: 'vertical' | 'horizontal';
}

function Boton({
  etiqueta,
  atajo,
  Icono,
  activo,
  onClick,
  deshabilitado,
  descripcion,
}: {
  readonly etiqueta: string;
  readonly atajo?: string;
  readonly Icono: LucideIcon;
  readonly activo: boolean;
  readonly onClick: () => void;
  readonly deshabilitado?: boolean;
  readonly descripcion?: string;
}) {
  return (
    <button
      type="button"
      className={activo ? 'btn-icono is-activo' : 'btn-icono'}
      aria-label={etiqueta}
      aria-pressed={activo}
      title={descripcion ?? (atajo ? `${etiqueta} (${atajo})` : etiqueta)}
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
  soloElegidos,
  onAlternarSoloElegidos,
  hayElegidos = false,
  volumenAbierto,
  onAlternarVolumen,
  orientacion = 'vertical',
}: Props) {
  return (
    <div
      className={`barra-iconos barra-iconos--${orientacion}`}
      role="toolbar"
      aria-label="Herramientas de trazo"
      aria-orientation={orientacion}
    >
      {herramientas.map((h) => (
        <Boton
          key={h}
          etiqueta={ETIQUETAS[h]}
          atajo={ATAJOS[h]}
          Icono={ICONOS[h]}
          activo={activa === h}
          onClick={() => onElegir(h)}
        />
      ))}
      {(onAlternarSoloElegidos || onAlternarVolumen) && <span className="barra-iconos__sep" role="separator" />}
      {onAlternarSoloElegidos && (
        <Boton
          etiqueta="Solo los trazos de los conceptos elegidos"
          Icono={Eye}
          activo={soloElegidos === true}
          deshabilitado={!hayElegidos && soloElegidos !== true}
          descripcion={
            hayElegidos || soloElegidos
              ? 'Ver solo los trazos de los conceptos elegidos en el árbol'
              : 'Elige conceptos en el árbol para ver solo sus trazos'
          }
          onClick={onAlternarSoloElegidos}
        />
      )}
      {onAlternarVolumen && (
        <Boton
          etiqueta="Calcular volumen"
          Icono={Box}
          activo={volumenAbierto === true}
          onClick={onAlternarVolumen}
        />
      )}
    </div>
  );
}

