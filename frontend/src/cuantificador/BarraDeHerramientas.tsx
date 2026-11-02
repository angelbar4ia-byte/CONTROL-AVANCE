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
  CopyPlus,
  Eraser,
  Eye,
  FlipHorizontal2,
  FlipVertical2,
  Hand,
  Hash,
  Layers,
  Link2,
  MapPin,
  MousePointer,
  Pentagon,
  Redo2,
  RotateCcw,
  RotateCw,
  RectangleHorizontal,
  Ruler,
  ScanLine,
  ScanSearch,
  Spline,
  SquareMinus,
  Slash,
  StickyNote,
  Table2,
  Trash2,
  Undo2,
  Wand2,
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

function IconoContorno({ size = 24, strokeWidth = 2 }: { size?: number | string; strokeWidth?: number | string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M4 19V8l6-4h4a6 6 0 0 1 6 6v9z" />
    </svg>
  );
}

/** Un icono: los de lucide y los pocos que ahí no hay (elipse, arco). */
type Icono = LucideIcon | typeof IconoElipse | typeof IconoContorno;

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
  contorno: IconoContorno,
  rectangulo_l: RectangleHorizontal,
  circulo_l: Circle,
  elipse_l: IconoElipse,
  punto: MapPin,
  copiar: CopyPlus,
  hueco: SquareMinus,
  borrar: Eraser,
  escala: Ruler,
  nota: StickyNote,
  enlace: Link2,
  conteo_auto: ScanSearch,
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
  contorno: 'Contorno (línea y arco)',
  rectangulo_l: 'Rectángulo (recorrido)',
  circulo_l: 'Círculo (recorrido)',
  elipse_l: 'Elipse (recorrido)',
  punto: 'Punto',
  copiar: 'Copiar en lote',
  hueco: 'Hueco',
  borrar: 'Borrar',
  escala: 'Calibrar escala',
  nota: 'Nota',
  enlace: 'Enlace a otra hoja',
  conteo_auto: 'Conteo automático',
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
  contorno: 'W',
  rectangulo_l: '',
  circulo_l: '',
  elipse_l: '',
  punto: 'O',
  copiar: 'K',
  hueco: 'U',
  borrar: 'B',
  escala: 'E',
  nota: 'N',
  enlace: '',
  conteo_auto: '',
};

/**
 * Las herramientas van en bloques por el tipo de medición que hacen: **Área** (siempre cerrada: lo que
 * se cierra se vuelve área), **Lineal** (largos; el rectángulo, el círculo y la elipse son aquí
 * recorridos cerrados que miden su longitud) y **Conteo**. El resto —moverse, anotar, borrar,
 * calibrar— no mide nada y no depende del tipo.
 */
export type BloqueDeBarra = 'vista' | 'area' | 'lineal' | 'conteo' | 'otros';

const BLOQUES: readonly { readonly clave: BloqueDeBarra; readonly titulo?: string; readonly herramientas: readonly Herramienta[] }[] = [
  { clave: 'vista', herramientas: ['seleccionar', 'mano', 'zoom'] },
  { clave: 'area', titulo: 'Área', herramientas: ['poligono', 'rectangulo', 'circulo', 'elipse', 'contorno', 'hueco'] },
  { clave: 'lineal', titulo: 'Lineal', herramientas: ['linea', 'polilinea', 'arco', 'rectangulo_l', 'circulo_l', 'elipse_l'] },
  { clave: 'conteo', titulo: 'Conteo', herramientas: ['punto', 'copiar', 'conteo_auto'] },
  { clave: 'otros', herramientas: ['nota', 'enlace', 'borrar'] },
];

export interface Accion {
  readonly clave: 'deshacer' | 'rehacer' | 'eliminar';
  readonly etiqueta: string;
  readonly deshabilitado: boolean;
  readonly descripcion: string;
  readonly onClick: () => void;
}

/** Cómo se ve el plano: girar a un lado u otro y voltearlo en espejo. Solo presentación. */
export interface AccionDeVista {
  readonly clave: 'girarIzquierda' | 'girarDerecha' | 'voltearH' | 'voltearV';
  readonly etiqueta: string;
  /** Los espejos quedan encendidos mientras el plano está volteado. */
  readonly activo?: boolean;
  readonly deshabilitado?: boolean;
  readonly descripcion: string;
  readonly onClick: () => void;
}

const ICONOS_DE_VISTA: Record<AccionDeVista['clave'], Icono> = {
  girarIzquierda: RotateCcw,
  girarDerecha: RotateCw,
  voltearH: FlipHorizontal2,
  voltearV: FlipVertical2,
};

export type ClaveDeInterruptor = 'medidas' | 'cotas' | 'soloElegidos' | 'volumen' | 'datos' | 'empalme' | 'escalaAuto' | 'takeoff';

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
  empalme: { etiqueta: 'Empalmar la versión anterior', icono: Layers },
  escalaAuto: { etiqueta: 'Proponer la escala', icono: Wand2 },
  takeoff: { etiqueta: 'Takeoff automático', icono: ScanLine },
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
  /** Girar y voltear el plano al verlo. */
  readonly vista?: readonly AccionDeVista[];
  readonly onAlternar: (clave: ClaveDeInterruptor) => void;
  readonly orientacion?: 'vertical' | 'horizontal';
  /** El tipo del concepto elegido: su bloque se resalta y los otros se atenúan (siguen usables). */
  readonly bloqueActivo?: 'area' | 'lineal' | 'conteo' | null;
}

function Boton({
  etiqueta,
  Icono,
  activo,
  onClick,
  deshabilitado,
  titulo,
  recorrido = false,
}: {
  readonly etiqueta: string;
  readonly Icono: Icono;
  readonly activo: boolean;
  readonly onClick: () => void;
  readonly deshabilitado?: boolean;
  readonly titulo: string;
  /** Un recorrido cerrado (rectángulo, círculo o elipse que miden longitud): se dibuja punteado. */
  readonly recorrido?: boolean;
}) {
  return (
    <button
      type="button"
      data-recorrido={recorrido ? '' : undefined}
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

export function BarraDeTrazo({
  herramientas,
  activa,
  onElegir,
  deshabilitadas = {},
  orientacion = 'vertical',
  bloqueActivo = null,
}: Props) {
  const grupos = BLOQUES.map((b) => ({ ...b, herramientas: b.herramientas.filter((h) => herramientas.includes(h)) })).filter(
    (b) => b.herramientas.length > 0,
  );
  return (
    <div
      className={`barra-iconos barra-iconos--${orientacion}`}
      role="toolbar"
      aria-label="Herramientas de trazo"
      aria-orientation={orientacion}
    >
      {grupos.map((grupo, i) => {
        const esDeTipo = grupo.clave === 'area' || grupo.clave === 'lineal' || grupo.clave === 'conteo';
        const clase = [
          'barra-iconos__grupo',
          esDeTipo && bloqueActivo === grupo.clave && 'is-resaltado',
          esDeTipo && bloqueActivo !== null && bloqueActivo !== grupo.clave && 'is-atenuado',
        ]
          .filter(Boolean)
          .join(' ');
        return (
          <div key={grupo.clave} className={clase} role="group" aria-label={grupo.titulo} data-bloque={grupo.clave}>
            {i > 0 && <span className="barra-iconos__sep" role="separator" />}
            {grupo.titulo && (
              <span className="barra-iconos__rotulo" aria-hidden="true">
                {grupo.titulo}
              </span>
            )}
            {grupo.herramientas.map((h) => (
              <Boton
                key={h}
                etiqueta={ETIQUETAS[h]}
                Icono={ICONOS[h]}
                activo={activa === h}
                deshabilitado={deshabilitadas[h] !== undefined}
                titulo={deshabilitadas[h] ?? (ATAJOS[h] ? `${ETIQUETAS[h]} (${ATAJOS[h]})` : ETIQUETAS[h])}
                recorrido={h.endsWith('_l')}
                onClick={() => onElegir(h)}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}

/**
 * FUNCIONES: deshacer, calibrar, lo que se muestra, la vista del plano y eliminar. Va en la cabecera de la
 * pantalla, fuera del plano, para no tapar lo que se dibuja.
 */
export function BarraDeFunciones({
  herramientas,
  activa,
  onElegir,
  deshabilitadas = {},
  interruptores,
  historial = [],
  acciones = [],
  vista = [],
  onAlternar,
}: Props) {
  const ctrlEscala = herramientas.includes('escala');
  return (
    <div
      className="barra-iconos barra-iconos--en-cabecera"
      role="toolbar"
      aria-label="Funciones"
      aria-orientation="horizontal"
    >
      {historial.length > 0 && (
        <div className="barra-iconos__grupo" role="group" aria-label="Historial">
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
      {ctrlEscala && (
        <div className="barra-iconos__grupo" role="group" aria-label="Escala">
          {historial.length > 0 && <span className="barra-iconos__sep" role="separator" />}
          <Boton
            etiqueta={ETIQUETAS.escala}
            Icono={ICONOS.escala}
            activo={activa === 'escala'}
            deshabilitado={deshabilitadas.escala !== undefined}
            titulo={deshabilitadas.escala ?? `${ETIQUETAS.escala} (${ATAJOS.escala})`}
            onClick={() => onElegir('escala')}
          />
        </div>
      )}
      <div className="barra-iconos__grupo" role="group" aria-label="Mostrar">
        {(historial.length > 0 || ctrlEscala) && <span className="barra-iconos__sep" role="separator" />}
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
      {vista.length > 0 && (
        <div className="barra-iconos__grupo" role="group" aria-label="Vista del plano">
          <span className="barra-iconos__sep" role="separator" />
          {vista.map((a) => (
            <Boton
              key={a.clave}
              etiqueta={a.etiqueta}
              Icono={ICONOS_DE_VISTA[a.clave]}
              activo={a.activo ?? false}
              deshabilitado={a.deshabilitado}
              titulo={a.descripcion}
              onClick={a.onClick}
            />
          ))}
        </div>
      )}
      {acciones.length > 0 && (
        <div className="barra-iconos__grupo" role="group" aria-label="Eliminar">
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
