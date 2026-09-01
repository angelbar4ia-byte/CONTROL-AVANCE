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
  CalendarDays,
  Layers,
  LayoutGrid,
  Maximize2,
  MousePointer2,
  Redo2,
  Save,
  Undo2,
} from 'lucide-react';

import {
  SEMANA_LABORAL,
  SEMANA_NATURAL,
  descripcionDeSemana,
  inicialDeDia,
  nombreDeDia,
  tipoDeSemana,
} from './calendario';
import type { ClaseNodo } from '@/api/generado/modelo';
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
  /**
   * Días hábiles del cronograma, ISO 1 = lunes … 7 = domingo (§7.5). Es del
   * programa completo, no de un renglón: si el muro contara sábados y el
   * aplanado no, la dependencia entre los dos no querría decir nada.
   */
  readonly diasHabiles: readonly number[];
  readonly onDiasHabiles: (dias: readonly number[]) => void;
  readonly onAlternarDia: (dia: number) => void;
  /**
   * Profundidad de captura sugerida del programa (§7.4, migración 0041): a qué
   * altura del árbol WBS abre el Gantt de las obras de este prototipo.
   *
   * Vive aquí y no en un diálogo aparte por lo mismo que el calendario: es del
   * **programa completo**, se decide una vez y se guarda con la versión. Y es
   * un default, no una restricción — quien necesite bajar a un concepto puede
   * hacerlo sin reversionar la plantilla.
   */
  readonly profundidad: ClaseNodo;
  readonly onProfundidad: (profundidad: ClaseNodo) => void;
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
  diasHabiles,
  onDiasHabiles,
  onAlternarDia,
  profundidad,
  onProfundidad,
}: Props) {
  const tipoSemana = tipoDeSemana(diasHabiles);
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

      {/* Semana laboral o natural (§7.5). El interruptor de dos posiciones es
          el gesto de todos los días; los días sueltos de al lado existen
          porque "laboral" no es lunes a viernes en obra —aquí lo normal es
          lunes a sábado, y hay frentes que trabajan domingo—, así que el
          conjunto real tiene que poder ajustarse sin salir de la barra. */}
      <div
        className="barra-prog__grupo"
        role="group"
        aria-label="Calendario"
        title={descripcionDeSemana(diasHabiles)}
      >
        <CalendarDays size={13} className="barra-prog__icono" aria-hidden />
        <button
          type="button"
          className={`btn btn--sm${tipoSemana === 'natural' ? ' btn--accent' : ''}`}
          aria-pressed={tipoSemana === 'natural'}
          onClick={() => onDiasHabiles(SEMANA_NATURAL)}
          title="Días corridos: sábado y domingo cuentan como trabajo"
        >
          Natural
        </button>
        <button
          type="button"
          className={`btn btn--sm${tipoSemana === 'laboral' ? ' btn--accent' : ''}`}
          aria-pressed={tipoSemana === 'laboral'}
          onClick={() => onDiasHabiles(SEMANA_LABORAL)}
          title="Solo los días hábiles cuentan; el motor salta los demás"
        >
          Laboral
        </button>
        <span className="barra-prog__dias" role="group" aria-label="Días hábiles">
          {SEMANA_NATURAL.map((dia) => {
            const habil = diasHabiles.includes(dia);
            return (
              <button
                key={dia}
                type="button"
                className={`barra-prog__dia${habil ? ' is-habil' : ''}`}
                aria-pressed={habil}
                aria-label={nombreDeDia(dia)}
                title={`${nombreDeDia(dia)}: ${habil ? 'se trabaja' : 'no se trabaja'}`}
                onClick={() => onAlternarDia(dia)}
              >
                {inicialDeDia(dia)}
              </button>
            );
          })}
        </span>
      </div>

      <div className="barra-prog__sep" aria-hidden />

      <div className="barra-prog__grupo" role="group" aria-label="Profundidad de captura">
        <Layers size={13} className="barra-prog__icono" aria-hidden />
        <select
          className="select"
          style={{ width: 175 }}
          value={profundidad}
          aria-label="Profundidad de captura"
          title={
            'A qué altura del árbol WBS abre el Gantt de las obras de este prototipo ' +
            '(§7.4). Es un default para que el equipo vea lo mismo, no una restricción.'
          }
          onChange={(e) => onProfundidad(e.target.value as ClaseNodo)}
        >
          <option value="concepto">Captura por concepto</option>
          <option value="nivel">Captura por nivel</option>
          <option value="etapa">Captura por etapa</option>
        </select>
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
