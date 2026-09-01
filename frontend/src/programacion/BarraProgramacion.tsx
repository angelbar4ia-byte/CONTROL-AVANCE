/**
 * Barra de herramientas de programación (§7.5).
 *
 * El "menú de herramienta" que pidió el jefe de obra: lo que se usa a cada
 * minuto mientras se arma un programa, en una sola fila y sin abrir nada.
 * Agrupada por gesto —qué se está haciendo, cómo se liga, qué se ve, dónde se
 * mira— porque un renglón de trece botones sin separar no se lee.
 *
 * No decide nada: recibe el estado y avisa. Toda la lógica está en los
 * módulos puros (`borrador.ts`, `acomodo.ts`, `grafo.ts`).
 */

import {
  ArrowRightLeft,
  Layers,
  LayoutGrid,
  Maximize2,
  MousePointer2,
  Redo2,
  Save,
  Undo2,
} from 'lucide-react';

import { TIPOS_LIGA, type TipoLiga, type Vista } from './grafo';
import { ayudaTipoDependencia, etiquetaTipoDependencia } from './reglas';

/**
 * Modo del puntero. `conectar` no cambia lo que React Flow permite —los
 * anclajes siempre tienden cables— sino lo que hace arrastrar el **cuerpo** de
 * la caja: en `seleccionar` la mueve, en `conectar` la deja quieta para no
 * desacomodar el grafo mientras se cablea a dos manos.
 */
export type ModoPuntero = 'seleccionar' | 'conectar';

interface Props {
  readonly modo: ModoPuntero;
  readonly onModo: (modo: ModoPuntero) => void;
  readonly tipoLigaPorDefecto: TipoLiga;
  readonly onTipoLiga: (tipo: TipoLiga) => void;
  readonly vista: Vista;
  readonly onVista: (vista: Vista) => void;
  readonly nombreEtapaAbierta: string | null;
  readonly onAcomodar: () => void;
  readonly onAjustar: () => void;
  readonly puedeDeshacer: boolean;
  readonly puedeRehacer: boolean;
  readonly onDeshacer: () => void;
  readonly onRehacer: () => void;
  readonly onGuardar: () => void;
  readonly guardando: boolean;
  readonly sucio: boolean;
  readonly renglones: number;
}

export function BarraProgramacion({
  modo,
  onModo,
  tipoLigaPorDefecto,
  onTipoLiga,
  vista,
  onVista,
  nombreEtapaAbierta,
  onAcomodar,
  onAjustar,
  puedeDeshacer,
  puedeRehacer,
  onDeshacer,
  onRehacer,
  onGuardar,
  guardando,
  sucio,
  renglones,
}: Props) {
  return (
    <div className="barra-prog" role="toolbar" aria-label="Herramientas de programación">
      <div className="barra-prog__grupo" role="group" aria-label="Puntero">
        <button
          type="button"
          className={`btn btn--sm${modo === 'seleccionar' ? ' btn--accent' : ''}`}
          aria-pressed={modo === 'seleccionar'}
          onClick={() => onModo('seleccionar')}
          title="Seleccionar y mover cajas"
        >
          <MousePointer2 size={13} aria-hidden /> Seleccionar
        </button>
        <button
          type="button"
          className={`btn btn--sm${modo === 'conectar' ? ' btn--accent' : ''}`}
          aria-pressed={modo === 'conectar'}
          onClick={() => onModo('conectar')}
          title="Solo tender cables: las cajas quedan fijas"
        >
          <ArrowRightLeft size={13} aria-hidden /> Conectar
        </button>
      </div>

      <div className="barra-prog__sep" aria-hidden />

      <div className="barra-prog__grupo">
        <label className="text-xs text-mute" htmlFor="liga-por-defecto">
          Liga
        </label>
        <select
          id="liga-por-defecto"
          className="select"
          style={{ width: 150 }}
          value={tipoLigaPorDefecto}
          onChange={(e) => onTipoLiga(e.target.value as TipoLiga)}
          title={ayudaTipoDependencia(tipoLigaPorDefecto)}
        >
          {TIPOS_LIGA.map((tipo) => (
            <option key={tipo} value={tipo}>
              {tipo} · {etiquetaTipoDependencia(tipo)}
            </option>
          ))}
        </select>
      </div>

      <div className="barra-prog__sep" aria-hidden />

      <div className="barra-prog__grupo" role="group" aria-label="Granularidad">
        <button
          type="button"
          className={`btn btn--sm${vista.modo === 'etapas' ? ' btn--accent' : ''}`}
          aria-pressed={vista.modo === 'etapas'}
          onClick={() => onVista({ modo: 'etapas' })}
          title="Etapas constructivas: la vista legible del programa"
        >
          <Layers size={13} aria-hidden /> Etapas
        </button>
        <button
          type="button"
          className={`btn btn--sm${vista.modo === 'conceptos' ? ' btn--accent' : ''}`}
          aria-pressed={vista.modo === 'conceptos'}
          onClick={() => onVista({ modo: 'conceptos' })}
          title="Todos los conceptos del prototipo, de todas las etapas"
        >
          <LayoutGrid size={13} aria-hidden /> Conceptos
        </button>
        {vista.modo === 'conceptos-de' && (
          <span className="badge badge--accent" title="Doble clic en una etapa para entrar">
            {nombreEtapaAbierta ?? 'Etapa'}
          </span>
        )}
      </div>

      <div className="barra-prog__sep" aria-hidden />

      <div className="barra-prog__grupo" role="group" aria-label="Vista">
        <button type="button" className="btn btn--sm" onClick={onAcomodar} title="Auto-acomodo por precedencia">
          Acomodar
        </button>
        <button
          type="button"
          className="btn btn--sm btn--icon"
          onClick={onAjustar}
          title="Ajustar a pantalla"
          aria-label="Ajustar a pantalla"
        >
          <Maximize2 size={13} aria-hidden />
        </button>
      </div>

      <div className="barra-prog__sep" aria-hidden />

      <div className="barra-prog__grupo" role="group" aria-label="Historial">
        <button
          type="button"
          className="btn btn--sm btn--icon"
          onClick={onDeshacer}
          disabled={!puedeDeshacer}
          title="Deshacer (Ctrl+Z)"
          aria-label="Deshacer"
        >
          <Undo2 size={13} aria-hidden />
        </button>
        <button
          type="button"
          className="btn btn--sm btn--icon"
          onClick={onRehacer}
          disabled={!puedeRehacer}
          title="Rehacer (Ctrl+Shift+Z)"
          aria-label="Rehacer"
        >
          <Redo2 size={13} aria-hidden />
        </button>
      </div>

      <div className="barra-prog__spacer" />

      {sucio && (
        <span className="badge badge--warn" title="Los cambios viven solo en esta pestaña">
          sin guardar
        </span>
      )}
      <button
        type="button"
        className="btn btn--sm btn--primary"
        onClick={onGuardar}
        disabled={guardando || renglones === 0}
        title="Cada guardado crea una versión nueva del programa base (§7.5)"
      >
        <Save size={13} aria-hidden />
        {guardando ? 'Guardando…' : `Guardar versión (${renglones})`}
      </button>
    </div>
  );
}
