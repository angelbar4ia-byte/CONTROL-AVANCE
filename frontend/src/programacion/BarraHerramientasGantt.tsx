/**
 * El menú de herramientas del programa base, en cinta (§7.4, §7.5, §7.6).
 *
 * ## Por qué en pestañas y no en una fila
 *
 * `BarraProgramacion.tsx` —la del canvas— cabe en un renglón porque son cinco
 * grupos de dos o tres controles. Aquí son siete grupos y cerca de cincuenta
 * controles: programar, vínculos, ruta crítica, escalas, barras, área de
 * trabajo y apariencia. Puestos en fila darían una barra de tres metros con
 * scroll horizontal, que es la forma más segura de que nadie encuentre nada; y
 * puestos en un menú desplegable obligarían a abrir y cerrar para cada ajuste
 * de una tarea —programar— que consiste precisamente en repetir el mismo ajuste
 * cincuenta veces.
 *
 * La cinta con pestañas de Opus/Project resuelve las dos cosas: el grupo entero
 * está a la vista mientras se trabaja en él, y cambiar de grupo cuesta un clic.
 * La pestaña activa se recuerda mientras dura la pantalla, no entre sesiones:
 * es dónde estaba la mano hace un minuto, no una preferencia.
 *
 * ## Herramientas que cambian el programa y herramientas que cambian la mirada
 *
 * Las dos primeras pestañas —Programar y Vínculos— producen **gestos
 * deshacibles**: despachan acciones al borrador y dejan la pantalla en "sin
 * guardar". Las cinco restantes no tocan el borrador ni una vez; viven en
 * `vistaGantt.ts` y se persisten en `localStorage`. La separación es del
 * modelo, no de esta pantalla, y aquí sólo se respeta: ningún control de las
 * cinco últimas llama a `onGesto`.
 *
 * Componente de presentación (§12.11): no decide nada. La traducción de cada
 * botón a acciones del borrador está en `gestos.ts`, la del zoom y las bandas
 * en `bandasPrograma.ts`, y aquí sólo se recogen parámetros y se avisa.
 */

import { useState } from 'react';
import {
  AlignLeft,
  ArrowLeftRight,
  CalendarDays,
  Columns3,
  Link2,
  Link2Off,
  Maximize2,
  Palette,
  Redo2,
  RotateCcw,
  Ruler,
  Scissors,
  Undo2,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';

import { acercarZoom, alejarZoom } from './bandasPrograma';
import {
  SEMANA_LABORAL,
  SEMANA_NATURAL,
  descripcionDeSemana,
  inicialDeDia,
  nombreDeDia,
  tipoDeSemana,
} from './calendario';
import { CLAVES_COLUMNAS, COLUMNAS_FIJAS, COLUMNAS_PROGRAMA } from './columnasPrograma';
import { TIPOS_LIGA, type TipoLiga } from './grafo';
import { ayudaTipoDependencia, etiquetaTipoDependencia } from './reglas';
import type { RutaCritica } from './rutaCritica';
import type { Densidad } from '@/shell/SelectorDensidad';
import {
  CAMPOS_ETIQUETA,
  alternarColumna,
  alternarEtiqueta,
  type CampoEtiqueta,
  type ColorBarra,
  type EscalaEje,
  type EstiloBarra,
  type FondoGantt,
  type Magnitud,
  type Modalidad,
  type Paleta,
  type PosicionEtiqueta,
  type Tema,
  type VistaGantt,
} from './vistaGantt';

/** Las siete pestañas, en el orden en que se trabaja con ellas. */
const PESTANAS = [
  { clave: 'programar', titulo: 'Programar' },
  { clave: 'vinculos', titulo: 'Vínculos' },
  { clave: 'ruta', titulo: 'Ruta crítica' },
  { clave: 'escalas', titulo: 'Escalas' },
  { clave: 'barras', titulo: 'Barras' },
  { clave: 'area', titulo: 'Área de trabajo' },
  { clave: 'apariencia', titulo: 'Apariencia' },
] as const;

type ClavePestana = (typeof PESTANAS)[number]['clave'];

/** Un vínculo que entra a la actividad seleccionada, listo para el menú. */
export interface VinculoDeSeleccion {
  readonly desde: string;
  readonly etiqueta: string;
  readonly tipo: TipoLiga;
  readonly lagDias: number;
}

/**
 * Lo que el menú necesita saber de la actividad seleccionada.
 *
 * Es un resumen y no la `FilaPrograma`: la cinta no tiene por qué conocer el
 * modelo de renglón, y con esto se prueba y se lee sin arrastrar el aplanado.
 */
export interface SeleccionHerramientas {
  readonly nodoId: string;
  readonly etiqueta: string;
  /** Barra derivada de sus hijos: no se programa sobre ella (§7.4). */
  readonly esResumen: boolean;
  readonly capturado: boolean;
  /** Día de arranque, 0-based; `null` si no está colocada. */
  readonly inicioDias: number | null;
  /** Último día trabajado, 0-based; `null` si no está colocada. */
  readonly terminoDias: number | null;
  readonly diasLaborables: number | null;
  readonly nTramos: number;
  readonly predecesoras: readonly VinculoDeSeleccion[];
  /** Nodos que pueden ser predecesora sin cerrar un ciclo (`gestos.ts`). */
  readonly candidatas: readonly { readonly id: string; readonly etiqueta: string }[];
}

/** Las herramientas que cambian el programa; cada una es un gesto deshacible. */
export interface AccionesHerramientas {
  readonly aplazar: (dias: number) => void;
  readonly noIniciarAntesDe: (dia: number) => void;
  readonly fijarDuracion: (dias: number) => void;
  readonly fijarInicio: (dia: number) => void;
  readonly fijarTermino: (dia: number) => void;
  readonly dividir: () => void;
  readonly interrumpir: (indice: number, dias: number) => void;
  readonly unirTramos: (indice: number) => void;
  readonly reiniciarActividad: () => void;
  readonly reiniciarPrograma: () => void;
  readonly vincular: (desde: string, tipo: TipoLiga, lagDias: number) => void;
  readonly desvincular: (desde: string) => void;
  readonly invertir: (desde: string) => void;
  readonly retipar: (desde: string, tipo: TipoLiga) => void;
  readonly retrasar: (desde: string, lagDias: number) => void;
}

interface Props {
  readonly vista: VistaGantt;
  readonly onVista: (vista: VistaGantt) => void;
  readonly acciones: AccionesHerramientas;
  readonly seleccion: SeleccionHerramientas | null;
  /** Cómo se rotula un día del programa; viene del eje (relativo o fecha). */
  readonly rotularDia: (dia: number) => string;
  readonly ruta: RutaCritica;
  readonly diasHabiles: readonly number[];
  readonly onDiasHabiles: (dias: readonly number[]) => void;
  readonly onAlternarDia: (dia: number) => void;
  readonly inicioSimulado: string;
  readonly onInicioSimulado: (iso: string) => void;
  readonly onAjustarZoom: () => void;
  readonly profundidadMaxima: number;
  readonly onColapsarANivel: (nivel: number) => void;
  readonly densidad: Densidad;
  readonly onDensidad: (densidad: Densidad) => void;
  readonly puedeDeshacer: boolean;
  readonly puedeRehacer: boolean;
  readonly onDeshacer: () => void;
  readonly onRehacer: () => void;
  readonly editable: boolean;
}

export function BarraHerramientasGantt(props: Props) {
  const [pestana, setPestana] = useState<ClavePestana>('programar');

  return (
    <div className="cinta">
      <div className="cinta__pestanas" role="tablist" aria-label="Menú de herramientas del programa">
        {PESTANAS.map((entrada) => (
          <button
            key={entrada.clave}
            type="button"
            role="tab"
            id={`cinta-tab-${entrada.clave}`}
            aria-selected={pestana === entrada.clave}
            aria-controls={`cinta-panel-${entrada.clave}`}
            className={`cinta__pestana${pestana === entrada.clave ? ' is-activa' : ''}`}
            onClick={() => setPestana(entrada.clave)}
          >
            {entrada.titulo}
          </button>
        ))}

        <span className="cinta__spacer" />

        {/* Deshacer y rehacer viven fuera de las pestañas: son de todas, y
            esconderlos detrás de una obligaría a volver a Programar para
            deshacer un vínculo. */}
        <button
          type="button"
          className="btn btn--sm btn--icon"
          disabled={!props.puedeDeshacer}
          title="Deshacer (Ctrl+Z)"
          aria-label="Deshacer"
          onClick={props.onDeshacer}
        >
          <Undo2 size={13} aria-hidden />
        </button>
        <button
          type="button"
          className="btn btn--sm btn--icon"
          disabled={!props.puedeRehacer}
          title="Rehacer (Ctrl+Shift+Z)"
          aria-label="Rehacer"
          onClick={props.onRehacer}
        >
          <Redo2 size={13} aria-hidden />
        </button>
      </div>

      <div
        className="cinta__panel"
        role="tabpanel"
        id={`cinta-panel-${pestana}`}
        aria-labelledby={`cinta-tab-${pestana}`}
      >
        {pestana === 'programar' && <PanelProgramar {...props} />}
        {pestana === 'vinculos' && <PanelVinculos {...props} />}
        {pestana === 'ruta' && <PanelRuta {...props} />}
        {pestana === 'escalas' && <PanelEscalas {...props} />}
        {pestana === 'barras' && <PanelBarras {...props} />}
        {pestana === 'area' && <PanelArea {...props} />}
        {pestana === 'apariencia' && <PanelApariencia {...props} />}
      </div>
    </div>
  );
}

/* ================================================================== *
 * Programar
 * ================================================================== */

function PanelProgramar({ acciones, seleccion, rotularDia, editable }: Props) {
  const [dias, setDias] = useState(1);
  const [desde, setDesde] = useState(1);
  const [pausa, setPausa] = useState(1);
  const [tramo, setTramo] = useState(1);

  // Un resumen **sí** se programa: capturarle días reparte su ventana hacia
  // abajo y capturarle el arranque mueve el bloque (`gestos.fijarDuracion`,
  // `desplazarBloque`). Excluirlo era de cuando el padre no heredaba nada, y
  // dejaba la cinta entera muerta con un nivel seleccionado.
  const activa = seleccion !== null && editable;
  const partida = seleccion !== null && seleccion.nTramos > 1;

  return (
    <>
      <Grupo titulo="Actividad">
        {seleccion === null ? (
          <span className="cinta__nota">
            Elige un renglón de la tabla para programarlo.
          </span>
        ) : (
          <span className="cinta__nota" title={seleccion.etiqueta}>
            {seleccion.esResumen
              ? `${seleccion.etiqueta} — es un resumen: lo que le captures baja a sus conceptos (§7.4)`
              : seleccion.etiqueta}
          </span>
        )}
      </Grupo>

      <Sep />

      <Grupo titulo="Ventana">
        <Numero
          etiqueta="Duración"
          sufijo="d"
          valor={seleccion?.diasLaborables ?? null}
          ancho={70}
          deshabilitado={!activa || partida}
          ayuda={
            partida
              ? 'La actividad está interrumpida: su duración es la suma de sus tramos (§7.6).'
              : 'Días de trabajo efectivo del renglón. Es lo que viaja en el POST.'
          }
          onConfirmar={acciones.fijarDuracion}
        />
        <Numero
          etiqueta="Inicio"
          sufijo="día"
          valor={seleccion === null || seleccion.inicioDias === null ? null : seleccion.inicioDias + 1}
          ancho={70}
          deshabilitado={!activa}
          ayuda={
            'Día en que arranca. Se guarda como el lag de la precedencia que la detiene: ' +
            'un renglón de programa base no tiene fecha propia (§7.5).'
          }
          onConfirmar={(valor) => acciones.fijarInicio(valor - 1)}
        />
        <Numero
          etiqueta="Término"
          sufijo="día"
          valor={seleccion === null || seleccion.terminoDias === null ? null : seleccion.terminoDias + 1}
          ancho={70}
          deshabilitado={!activa || partida}
          ayuda="Último día trabajado. Se traduce a duración, que es lo que el contrato guarda."
          onConfirmar={(valor) => acciones.fijarTermino(valor - 1)}
        />
      </Grupo>

      <Sep />

      <Grupo titulo="Desplazar">
        <label className="cinta__campo">
          <span className="field__label">Aplazar</span>
          <input
            className="input"
            type="number"
            step={1}
            style={{ width: 62 }}
            value={dias}
            aria-label="Días a aplazar"
            onChange={(evento) => setDias(Number(evento.target.value))}
          />
        </label>
        <button
          type="button"
          className="btn btn--sm"
          disabled={!activa}
          title="Corre la actividad cambiando el lag de la precedencia que la detiene (§7.5)"
          onClick={() => acciones.aplazar(dias)}
        >
          Aplazar
        </button>

        <label className="cinta__campo">
          <span className="field__label">No iniciar antes del día</span>
          <input
            className="input"
            type="number"
            min={1}
            step={1}
            style={{ width: 62 }}
            value={desde}
            aria-label="Día antes del cual no debe iniciar"
            onChange={(evento) => setDesde(Number(evento.target.value))}
          />
        </label>
        <button
          type="button"
          className="btn btn--sm"
          disabled={!activa}
          title={
            'Lleva el arranque a ese día. OJO: no es una restricción con fecha propia — el ' +
            'contrato no tiene dónde guardarla —, se resuelve como lag, así que si la ' +
            'predecesora se mueve, la actividad se mueve con ella (§7.5).'
          }
          onClick={() => acciones.noIniciarAntesDe(desde - 1)}
        >
          Aplicar
        </button>
        <span className="cinta__nota mono">
          {seleccion?.inicioDias === null || seleccion === null
            ? ''
            : `hoy arranca ${rotularDia(seleccion.inicioDias)}`}
        </span>
      </Grupo>

      <Sep />

      <Grupo titulo="Interrupción">
        <button
          type="button"
          className="btn btn--sm"
          disabled={!activa}
          title="Parte la actividad a la mitad y deja una pausa; el concepto sigue siendo uno (§7.6)"
          onClick={acciones.dividir}
        >
          <Scissors size={13} aria-hidden /> Dividir
        </button>

        <label className="cinta__campo">
          <span className="field__label">Tramo</span>
          <input
            className="input"
            type="number"
            min={2}
            step={1}
            style={{ width: 52 }}
            value={tramo}
            aria-label="Número de tramo sobre el que se opera"
            onChange={(evento) => setTramo(Number(evento.target.value))}
          />
        </label>
        <label className="cinta__campo">
          <span className="field__label">Pausa</span>
          <input
            className="input"
            type="number"
            step={1}
            style={{ width: 56 }}
            value={pausa}
            aria-label="Días que se alarga la pausa"
            onChange={(evento) => setPausa(Number(evento.target.value))}
          />
        </label>
        <button
          type="button"
          className="btn btn--sm"
          disabled={!activa || !partida}
          title="Alarga la pausa que hay delante de ese tramo, corriendo lo que le sigue (§7.6)"
          onClick={() => acciones.interrumpir(tramo - 1, pausa)}
        >
          Interrumpir
        </button>
        <button
          type="button"
          className="btn btn--sm"
          disabled={!activa || !partida}
          title="Cierra la pausa y vuelve a juntar los dos tramos (§7.6)"
          onClick={() => acciones.unirTramos(tramo - 2)}
        >
          Unir tramos
        </button>
        <span className="cinta__nota mono">
          {partida ? `${seleccion?.nTramos} tramos` : 'continua'}
        </span>
      </Grupo>

      <Sep />

      <Grupo titulo="Reiniciar">
        <button
          type="button"
          className="btn btn--sm"
          disabled={!activa}
          title="Quita las pausas y devuelve la actividad a su arranque natural. No borra su duración."
          onClick={acciones.reiniciarActividad}
        >
          <RotateCcw size={13} aria-hidden /> Actividad
        </button>
        <button
          type="button"
          className="btn btn--sm"
          disabled={!editable}
          title="Lo mismo sobre todo el programa, como un solo paso de deshacer"
          onClick={acciones.reiniciarPrograma}
        >
          <RotateCcw size={13} aria-hidden /> Programa
        </button>
      </Grupo>
    </>
  );
}

/* ================================================================== *
 * Vínculos
 * ================================================================== */

function PanelVinculos({ acciones, seleccion, vista, onVista, editable }: Props) {
  const [candidata, setCandidata] = useState('');
  const [lag, setLag] = useState(0);
  const [elegido, setElegido] = useState('');

  const activa = seleccion !== null && editable;
  const vinculo =
    seleccion?.predecesoras.find((p) => p.desde === elegido) ?? seleccion?.predecesoras[0] ?? null;

  return (
    <>
      <Grupo titulo="Tender">
        <label className="cinta__campo">
          <span className="field__label">Predecesora</span>
          <select
            className="select"
            style={{ width: 260 }}
            value={candidata}
            disabled={!activa}
            aria-label="Actividad predecesora"
            onChange={(evento) => setCandidata(evento.target.value)}
          >
            <option value="">— elegir —</option>
            {(seleccion?.candidatas ?? []).map((opcion) => (
              <option key={opcion.id} value={opcion.id}>
                {opcion.etiqueta}
              </option>
            ))}
          </select>
        </label>
        <label className="cinta__campo">
          <span className="field__label">Retraso</span>
          <input
            className="input"
            type="number"
            step={1}
            style={{ width: 62 }}
            value={lag}
            aria-label="Retraso del vínculo en días"
            onChange={(evento) => setLag(Number(evento.target.value))}
          />
        </label>
        <button
          type="button"
          className="btn btn--sm btn--accent"
          disabled={!activa || candidata === ''}
          title="Tiende la precedencia con el tipo por defecto. Un ciclo se rechaza antes de guardar (§6)."
          onClick={() => acciones.vincular(candidata, vista.tipoLigaPorDefecto, lag)}
        >
          <Link2 size={13} aria-hidden /> Vincular
        </button>
      </Grupo>

      <Sep />

      <Grupo titulo="Vínculo existente">
        <label className="cinta__campo">
          <span className="field__label">Entra desde</span>
          <select
            className="select"
            style={{ width: 240 }}
            value={vinculo?.desde ?? ''}
            disabled={!activa || (seleccion?.predecesoras.length ?? 0) === 0}
            aria-label="Vínculo sobre el que se opera"
            onChange={(evento) => setElegido(evento.target.value)}
          >
            {(seleccion?.predecesoras ?? []).length === 0 && (
              <option value="">— la actividad no tiene predecesoras —</option>
            )}
            {(seleccion?.predecesoras ?? []).map((p) => (
              <option key={p.desde} value={p.desde}>
                {p.tipo} {p.lagDias === 0 ? '' : `${p.lagDias > 0 ? '+' : ''}${p.lagDias}d`} ·{' '}
                {p.etiqueta}
              </option>
            ))}
          </select>
        </label>

        <label className="cinta__campo">
          <span className="field__label">Tipo</span>
          <select
            className="select"
            style={{ width: 150 }}
            value={vinculo?.tipo ?? 'FS'}
            disabled={vinculo === null || !activa}
            aria-label="Tipo del vínculo"
            title={ayudaTipoDependencia(vinculo?.tipo)}
            onChange={(evento) =>
              vinculo && acciones.retipar(vinculo.desde, evento.target.value as TipoLiga)
            }
          >
            {TIPOS_LIGA.map((tipo) => (
              <option key={tipo} value={tipo}>
                {tipo} · {etiquetaTipoDependencia(tipo)}
              </option>
            ))}
          </select>
        </label>

        <Numero
          etiqueta="Retraso"
          sufijo="d"
          valor={vinculo?.lagDias ?? null}
          ancho={62}
          deshabilitado={vinculo === null || !activa}
          ayuda="Admite negativo: un −2 en una FS es entrar dos días antes de que la predecesora acabe."
          onConfirmar={(valor) => vinculo && acciones.retrasar(vinculo.desde, valor)}
        />

        <button
          type="button"
          className="btn btn--sm"
          disabled={vinculo === null || !activa}
          title="Le da la vuelta al vínculo conservando tipo y retraso"
          onClick={() => vinculo && acciones.invertir(vinculo.desde)}
        >
          <ArrowLeftRight size={13} aria-hidden /> Invertir
        </button>
        <button
          type="button"
          className="btn btn--sm"
          disabled={vinculo === null || !activa}
          title="Quita el vínculo"
          onClick={() => vinculo && acciones.desvincular(vinculo.desde)}
        >
          <Link2Off size={13} aria-hidden /> Desvincular
        </button>
      </Grupo>

      <Sep />

      <Grupo titulo="Configurar vínculos">
        <label className="cinta__campo">
          <span className="field__label">Tipo por defecto</span>
          <select
            className="select"
            style={{ width: 170 }}
            value={vista.tipoLigaPorDefecto}
            aria-label="Tipo de vínculo por defecto"
            title={
              'El tipo con el que se tiende un vínculo nuevo desde esta barra. Arrastrar una ' +
              'barra del Gantt mueve la actividad, no tiende vínculos: eso se hace aquí o en el canvas.'
            }
            onChange={(evento) =>
              onVista({ ...vista, tipoLigaPorDefecto: evento.target.value as TipoLiga })
            }
          >
            {TIPOS_LIGA.map((tipo) => (
              <option key={tipo} value={tipo}>
                {tipo} · {etiquetaTipoDependencia(tipo)}
              </option>
            ))}
          </select>
        </label>
      </Grupo>
    </>
  );
}

/* ================================================================== *
 * Ruta crítica
 * ================================================================== */

function PanelRuta({ vista, onVista, ruta }: Props) {
  return (
    <>
      <Grupo titulo="Trazado">
        <Interruptor
          activo={vista.rutaCritica}
          etiqueta="Trazar ruta crítica"
          ayuda={
            'Resalta la cadena sin holgura del borrador. No es la del motor (§6): aquélla se ' +
            'calcula contra el calendario laboral de la obra y llega resuelta por la API.'
          }
          onClick={() => onVista({ ...vista, rutaCritica: !vista.rutaCritica })}
        />
        <Interruptor
          activo={vista.verHolgura}
          etiqueta="Mostrar holgura"
          ayuda="La cola fantasma detrás de la barra: cuánto puede correrse sin empujar el cierre."
          onClick={() => onVista({ ...vista, verHolgura: !vista.verHolgura })}
        />
      </Grupo>

      <Sep />

      <Grupo titulo="Tolerancia">
        <label className="cinta__campo">
          <span className="field__label">Hasta</span>
          <input
            className="input"
            type="number"
            min={0}
            step={0.5}
            style={{ width: 64 }}
            value={vista.toleranciaHolguraDias}
            aria-label="Días de holgura que cuentan como crítico"
            title="Con 0 es la definición estricta: crítico es holgura cero."
            onChange={(evento) =>
              onVista({
                ...vista,
                toleranciaHolguraDias: Math.max(0, Number(evento.target.value) || 0),
              })
            }
          />
          <span className="field__label">d de holgura cuentan como crítico</span>
        </label>
      </Grupo>

      <Sep />

      <Grupo titulo="En la cadena">
        <span className="cinta__nota mono">
          {ruta.nActividades} actividad{ruta.nActividades === 1 ? '' : 'es'} ·{' '}
          {ruta.diasCriticos} d de trabajo ·{' '}
          {ruta.holguraMinima === null
            ? 'sin holgura calculada'
            : `holgura mínima ${ruta.holguraMinima} d`}
        </span>
      </Grupo>
    </>
  );
}

/* ================================================================== *
 * Escalas
 * ================================================================== */

const ESCALAS: readonly { readonly clave: EscalaEje; readonly titulo: string }[] = [
  { clave: 'dias', titulo: 'Días' },
  { clave: 'semanas', titulo: 'Semanas' },
  { clave: 'meses-dias', titulo: 'Meses / Días' },
  { clave: 'meses-semanas', titulo: 'Meses / Sem.' },
];

function PanelEscalas({
  vista,
  onVista,
  inicioSimulado,
  onInicioSimulado,
  onAjustarZoom,
  diasHabiles,
  onDiasHabiles,
  onAlternarDia,
}: Props) {
  const tipoSemana = tipoDeSemana(diasHabiles);

  return (
    <>
      <Grupo titulo="Escala">
        <Ruler size={13} className="cinta__icono" aria-hidden />
        {ESCALAS.map((escala) => (
          <button
            key={escala.clave}
            type="button"
            className={`btn btn--sm${vista.escala === escala.clave ? ' btn--accent' : ''}`}
            aria-pressed={vista.escala === escala.clave}
            title={
              escala.clave.startsWith('meses')
                ? 'Los meses son de calendario sólo con fechas simuladas; en días relativos la ' +
                  'banda de arriba agrupa cuatro semanas y se rotula como tal (§7.5).'
                : 'Periodo grande arriba, chico abajo, como en Opus.'
            }
            onClick={() => onVista({ ...vista, escala: escala.clave })}
          >
            {escala.titulo}
          </button>
        ))}
      </Grupo>

      <Sep />

      <Grupo titulo="Eje">
        <button
          type="button"
          className={`btn btn--sm${vista.modoEje === 'relativo' ? ' btn--accent' : ''}`}
          aria-pressed={vista.modoEje === 'relativo'}
          title="Un programa base es una plantilla: no tiene fechas propias (§7.5)"
          onClick={() => onVista({ ...vista, modoEje: 'relativo' })}
        >
          Días relativos
        </button>
        <button
          type="button"
          className={`btn btn--sm${vista.modoEje === 'fechas' ? ' btn--accent' : ''}`}
          aria-pressed={vista.modoEje === 'fechas'}
          title="Simulación: si esto arrancara tal día, ¿qué días caerían?"
          onClick={() => onVista({ ...vista, modoEje: 'fechas' })}
        >
          Fechas simuladas
        </button>
        {vista.modoEje === 'fechas' && (
          <label className="cinta__campo">
            <span className="field__label">Arranque</span>
            <input
              className="input"
              type="date"
              style={{ width: 150 }}
              value={inicioSimulado}
              aria-label="Arranque de la simulación"
              onChange={(evento) => onInicioSimulado(evento.target.value)}
            />
          </label>
        )}
      </Grupo>

      <Sep />

      <Grupo titulo="Zoom">
        <button
          type="button"
          className="btn btn--sm btn--icon"
          aria-label="Alejar"
          title="Alejar"
          onClick={() => onVista({ ...vista, zoom: alejarZoom(vista.zoom) })}
        >
          <ZoomOut size={13} aria-hidden />
        </button>
        <span className="cinta__nota mono">{vista.zoom} px/día</span>
        <button
          type="button"
          className="btn btn--sm btn--icon"
          aria-label="Acercar"
          title="Acercar"
          onClick={() => onVista({ ...vista, zoom: acercarZoom(vista.zoom) })}
        >
          <ZoomIn size={13} aria-hidden />
        </button>
        <button
          type="button"
          className="btn btn--sm"
          title="Ajusta el zoom para que el programa completo quepa en el ancho del Gantt"
          onClick={onAjustarZoom}
        >
          <Maximize2 size={13} aria-hidden /> Ajustar
        </button>
      </Grupo>

      <Sep />

      {/* El calendario no es de vista: viaja en el POST con la versión (§7.5).
          Está en esta pestaña porque es lo que decide qué días cuenta el eje,
          y es donde el usuario lo busca. */}
      <Grupo titulo="Días hábiles (se guarda)">
        <CalendarDays size={13} className="cinta__icono" aria-hidden />
        <button
          type="button"
          className={`btn btn--sm${tipoSemana === 'natural' ? ' btn--accent' : ''}`}
          aria-pressed={tipoSemana === 'natural'}
          title="Días corridos: sábado y domingo cuentan como trabajo"
          onClick={() => onDiasHabiles(SEMANA_NATURAL)}
        >
          Natural
        </button>
        <button
          type="button"
          className={`btn btn--sm${tipoSemana === 'laboral' ? ' btn--accent' : ''}`}
          aria-pressed={tipoSemana === 'laboral'}
          title="Sólo los días hábiles cuentan; el motor salta los demás"
          onClick={() => onDiasHabiles(SEMANA_LABORAL)}
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
        <span className="cinta__nota">{descripcionDeSemana(diasHabiles)}</span>
      </Grupo>
    </>
  );
}

/* ================================================================== *
 * Barras
 * ================================================================== */

const ESTILOS: readonly { readonly clave: EstiloBarra; readonly titulo: string }[] = [
  { clave: 'solida', titulo: 'Sólida' },
  { clave: 'contorno', titulo: 'Contorno' },
  { clave: 'delgada', titulo: 'Delgada' },
];

const ETIQUETAS_CAMPO: Record<CampoEtiqueta, string> = {
  clave: 'Clave',
  descripcion: 'Descripción',
  dias: 'Días',
  cantidad: 'Cantidad',
  importe: 'Importe',
  porcentaje: 'Porcentaje',
};

const POSICIONES: readonly { readonly clave: PosicionEtiqueta; readonly titulo: string }[] = [
  { clave: 'izquierda', titulo: 'Izquierda' },
  { clave: 'dentro', titulo: 'Dentro' },
  { clave: 'derecha', titulo: 'Derecha' },
];

const COLORES: readonly { readonly clave: ColorBarra; readonly titulo: string; readonly ayuda: string }[] = [
  { clave: 'tipo', titulo: 'Tipo', ayuda: 'Nivel, etapa y concepto en tonos distintos' },
  { clave: 'frente', titulo: 'Frente', ayuda: 'Un tono por frente de trabajo, en el orden del árbol' },
  {
    clave: 'criticidad',
    titulo: 'Criticidad',
    ayuda: 'Crítica contra holgada; en paleta monocromática la crítica se distingue por trama',
  },
];

function PanelBarras({ vista, onVista }: Props) {
  return (
    <>
      <Grupo titulo="Estilo">
        {ESTILOS.map((estilo) => (
          <button
            key={estilo.clave}
            type="button"
            className={`btn btn--sm${vista.estiloBarra === estilo.clave ? ' btn--accent' : ''}`}
            aria-pressed={vista.estiloBarra === estilo.clave}
            onClick={() => onVista({ ...vista, estiloBarra: estilo.clave })}
          >
            {estilo.titulo}
          </button>
        ))}
      </Grupo>

      <Sep />

      <Grupo titulo="Mostrar">
        <Interruptor
          activo={vista.verResumen}
          etiqueta="Resumen"
          ayuda="El corchete de nivel y etapa, derivado de sus hijos (§7.4)"
          onClick={() => onVista({ ...vista, verResumen: !vista.verResumen })}
        />
        <Interruptor
          activo={vista.verPausas}
          etiqueta="Pausas"
          ayuda="La línea que une los tramos de una actividad interrumpida (§7.6)"
          onClick={() => onVista({ ...vista, verPausas: !vista.verPausas })}
        />
        <Interruptor
          activo={vista.verHolgura}
          etiqueta="Holgura"
          ayuda="La cola detrás de la barra"
          onClick={() => onVista({ ...vista, verHolgura: !vista.verHolgura })}
        />
        <Interruptor
          activo={vista.verVinculos}
          etiqueta="Vínculos"
          ayuda="Las flechas de precedencia entre barras dibujadas"
          onClick={() => onVista({ ...vista, verVinculos: !vista.verVinculos })}
        />
      </Grupo>

      <Sep />

      <Grupo titulo="Etiqueta">
        <AlignLeft size={13} className="cinta__icono" aria-hidden />
        {CAMPOS_ETIQUETA.map((campo) => (
          <Interruptor
            key={campo}
            activo={vista.etiquetas.includes(campo)}
            etiqueta={ETIQUETAS_CAMPO[campo]}
            ayuda="Se combinan; se dibujan siempre en este orden"
            onClick={() => onVista(alternarEtiqueta(vista, campo))}
          />
        ))}
        <label className="cinta__campo">
          <span className="field__label">Posición</span>
          <select
            className="select"
            style={{ width: 120 }}
            value={vista.posicionEtiqueta}
            aria-label="Posición de la etiqueta"
            onChange={(evento) =>
              onVista({ ...vista, posicionEtiqueta: evento.target.value as PosicionEtiqueta })
            }
          >
            {POSICIONES.map((posicion) => (
              <option key={posicion.clave} value={posicion.clave}>
                {posicion.titulo}
              </option>
            ))}
          </select>
        </label>
      </Grupo>

      <Sep />

      <Grupo titulo="Color por">
        {COLORES.map((color) => (
          <button
            key={color.clave}
            type="button"
            className={`btn btn--sm${vista.colorBarra === color.clave ? ' btn--accent' : ''}`}
            aria-pressed={vista.colorBarra === color.clave}
            title={color.ayuda}
            onClick={() => onVista({ ...vista, colorBarra: color.clave })}
          >
            {color.titulo}
          </button>
        ))}
      </Grupo>
    </>
  );
}

/* ================================================================== *
 * Área de trabajo
 * ================================================================== */

const MAGNITUDES: readonly { readonly clave: Magnitud; readonly titulo: string }[] = [
  { clave: 'cantidad', titulo: 'Cantidad' },
  { clave: 'importe', titulo: 'Importe' },
  { clave: 'porcentaje', titulo: 'Porcentaje' },
];

const MODALIDADES: readonly { readonly clave: Modalidad; readonly titulo: string; readonly ayuda: string }[] = [
  { clave: 'gantt', titulo: 'Gantt', ayuda: 'Las barras sobre el eje de tiempo' },
  {
    clave: 'cantidades',
    titulo: 'Cantidades por escala',
    ayuda:
      'Sustituye el Gantt por una rejilla con una columna por periodo. El reparto es DERIVADO ' +
      'y de sólo lectura: no existe como dato en el contrato (`reparto.ts`).',
  },
];

function PanelArea({ vista, onVista, profundidadMaxima, onColapsarANivel }: Props) {
  const niveles = Array.from({ length: profundidadMaxima + 1 }, (_, i) => i);

  return (
    <>
      <Grupo titulo="Modalidad">
        {MODALIDADES.map((modalidad) => (
          <button
            key={modalidad.clave}
            type="button"
            className={`btn btn--sm${vista.modalidad === modalidad.clave ? ' btn--accent' : ''}`}
            aria-pressed={vista.modalidad === modalidad.clave}
            title={modalidad.ayuda}
            onClick={() => onVista({ ...vista, modalidad: modalidad.clave })}
          >
            {modalidad.titulo}
          </button>
        ))}
      </Grupo>

      <Sep />

      <Grupo titulo="Ver">
        {MAGNITUDES.map((magnitud) => (
          <button
            key={magnitud.clave}
            type="button"
            className={`btn btn--sm${vista.magnitud === magnitud.clave ? ' btn--accent' : ''}`}
            aria-pressed={vista.magnitud === magnitud.clave}
            title={
              magnitud.clave === 'cantidad'
                ? 'La cantidad no se agrega hacia arriba: las unidades de los hijos difieren (§6)'
                : 'El importe y su porcentaje sí se agregan, como todo lo ponderado del sistema (§6)'
            }
            onClick={() => onVista({ ...vista, magnitud: magnitud.clave })}
          >
            {magnitud.titulo}
          </button>
        ))}
      </Grupo>

      <Sep />

      <Grupo titulo="Tabla">
        <Interruptor
          activo={vista.fijarColumnas}
          etiqueta="Fijar columnas"
          ayuda="Congela el bloque hasta Descripción al correr la tabla a los lados"
          onClick={() => onVista({ ...vista, fijarColumnas: !vista.fijarColumnas })}
        />
        <Columns3 size={13} className="cinta__icono" aria-hidden />
        {COLUMNAS_PROGRAMA.map((columna) => (
          <Interruptor
            key={columna.clave}
            activo={vista.columnas.includes(columna.clave) || COLUMNAS_FIJAS.has(columna.clave)}
            etiqueta={columna.titulo}
            deshabilitado={COLUMNAS_FIJAS.has(columna.clave)}
            ayuda={
              COLUMNAS_FIJAS.has(columna.clave)
                ? `${columna.ayuda}. No se puede apagar: sin ella el renglón no se puede nombrar.`
                : columna.ayuda
            }
            onClick={() =>
              onVista(alternarColumna(vista, columna.clave, CLAVES_COLUMNAS, COLUMNAS_FIJAS))
            }
          />
        ))}
      </Grupo>

      <Sep />

      <Grupo titulo="Árbol">
        <span className="field__label">Colapsar a</span>
        {niveles.map((nivel) => (
          <button
            key={nivel}
            type="button"
            className="btn btn--sm"
            title={`Deja abiertos ${nivel + 1} escalón(es) del árbol`}
            onClick={() => onColapsarANivel(nivel)}
          >
            {nivel + 1}
          </button>
        ))}
        <button
          type="button"
          className="btn btn--sm"
          title="Abre el árbol completo"
          onClick={() => onColapsarANivel(profundidadMaxima + 1)}
        >
          Todo
        </button>
      </Grupo>
    </>
  );
}

/* ================================================================== *
 * Apariencia
 * ================================================================== */

const TEMAS: readonly { readonly clave: Tema; readonly titulo: string }[] = [
  { clave: 'claro', titulo: 'Claro' },
  { clave: 'oscuro', titulo: 'Oscuro' },
  { clave: 'sistema', titulo: 'Sistema' },
];

const PALETAS: readonly { readonly clave: Paleta; readonly titulo: string; readonly ayuda: string }[] = [
  { clave: 'color', titulo: 'Color', ayuda: 'La paleta operacional de siempre' },
  {
    clave: 'mono',
    titulo: 'Monocromática',
    ayuda:
      'Neutros más un acento. La criticidad pasa a distinguirse por trama, para que sobreviva ' +
      'a una impresión en blanco y negro y al daltonismo rojo-verde.',
  },
];

const FONDOS: readonly { readonly clave: FondoGantt; readonly titulo: string; readonly ayuda: string }[] = [
  { clave: 'liso', titulo: 'Liso', ayuda: 'Sin rejilla' },
  { clave: 'cuadricula', titulo: 'Cuadrícula', ayuda: 'Una línea por periodo de la banda inferior' },
  {
    clave: 'inhabiles',
    titulo: 'Bandas inhábiles',
    ayuda:
      'Sombrea los días que el calendario no trabaja. Sólo dice algo con fechas simuladas: en ' +
      'días relativos todos los días del eje son hábiles por construcción (§7.5).',
  },
];

function PanelApariencia({ vista, onVista, densidad, onDensidad }: Props) {
  return (
    <>
      <Grupo titulo="Tema">
        <Palette size={13} className="cinta__icono" aria-hidden />
        {TEMAS.map((tema) => (
          <button
            key={tema.clave}
            type="button"
            className={`btn btn--sm${vista.tema === tema.clave ? ' btn--accent' : ''}`}
            aria-pressed={vista.tema === tema.clave}
            title={
              tema.clave === 'sistema'
                ? 'Sigue la preferencia del sistema operativo'
                : `Tema ${tema.titulo.toLowerCase()} para este módulo`
            }
            onClick={() => onVista({ ...vista, tema: tema.clave })}
          >
            {tema.titulo}
          </button>
        ))}
      </Grupo>

      <Sep />

      <Grupo titulo="Paleta">
        {PALETAS.map((paleta) => (
          <button
            key={paleta.clave}
            type="button"
            className={`btn btn--sm${vista.paleta === paleta.clave ? ' btn--accent' : ''}`}
            aria-pressed={vista.paleta === paleta.clave}
            title={paleta.ayuda}
            onClick={() => onVista({ ...vista, paleta: paleta.clave })}
          >
            {paleta.titulo}
          </button>
        ))}
      </Grupo>

      <Sep />

      {/* La densidad no vive en `vistaGantt`: ya existe `body[data-density]`
          con su propio almacén y es de toda la app (§12.10). */}
      <Grupo titulo="Densidad">
        <button
          type="button"
          className={`btn btn--sm${densidad === 'compact' ? ' btn--accent' : ''}`}
          aria-pressed={densidad === 'compact'}
          title="Renglones más bajos; es la densidad de las vistas operativas"
          onClick={() => onDensidad('compact')}
        >
          Compacta
        </button>
        <button
          type="button"
          className={`btn btn--sm${densidad === 'comfy' ? ' btn--accent' : ''}`}
          aria-pressed={densidad === 'comfy'}
          title="Renglones más altos; es la densidad de las vistas guiadas"
          onClick={() => onDensidad('comfy')}
        >
          Cómoda
        </button>
      </Grupo>

      <Sep />

      <Grupo titulo="Tabla">
        <Interruptor
          activo={vista.rayado}
          etiqueta="Rayado"
          ayuda="Alterna el fondo de los renglones"
          onClick={() => onVista({ ...vista, rayado: !vista.rayado })}
        />
        <Interruptor
          activo={vista.lineas}
          etiqueta="Líneas"
          ayuda="Separadores entre renglones"
          onClick={() => onVista({ ...vista, lineas: !vista.lineas })}
        />
        <Interruptor
          activo={vista.colorPorNivel}
          etiqueta="Color por nivel"
          ayuda="El tinte por profundidad que deja leer el árbol sin contar sangrías"
          onClick={() => onVista({ ...vista, colorPorNivel: !vista.colorPorNivel })}
        />
      </Grupo>

      <Sep />

      <Grupo titulo="Fondo del Gantt">
        {FONDOS.map((fondo) => (
          <button
            key={fondo.clave}
            type="button"
            className={`btn btn--sm${vista.fondoGantt === fondo.clave ? ' btn--accent' : ''}`}
            aria-pressed={vista.fondoGantt === fondo.clave}
            title={fondo.ayuda}
            onClick={() => onVista({ ...vista, fondoGantt: fondo.clave })}
          >
            {fondo.titulo}
          </button>
        ))}
      </Grupo>

      <Sep />

      <Grupo titulo="">
        <span className="cinta__nota">
          La apariencia se recuerda en este navegador y es sólo de este módulo: no viaja al
          servidor ni cambia lo que ven los demás.
        </span>
      </Grupo>
    </>
  );
}

/* ================================================================== *
 * Piezas compartidas
 * ================================================================== */

function Grupo({
  titulo,
  children,
}: {
  readonly titulo: string;
  readonly children: React.ReactNode;
}) {
  return (
    <div className="cinta__grupo" role="group" aria-label={titulo === '' ? undefined : titulo}>
      {titulo !== '' && <span className="cinta__titulo">{titulo}</span>}
      <div className="cinta__fila">{children}</div>
    </div>
  );
}

function Sep() {
  return <span className="cinta__sep" aria-hidden />;
}

function Interruptor({
  activo,
  etiqueta,
  ayuda,
  deshabilitado = false,
  onClick,
}: {
  readonly activo: boolean;
  readonly etiqueta: string;
  readonly ayuda: string;
  readonly deshabilitado?: boolean;
  readonly onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`btn btn--sm${activo ? ' btn--accent' : ''}`}
      aria-pressed={activo}
      disabled={deshabilitado}
      title={ayuda}
      onClick={onClick}
    >
      {etiqueta}
    </button>
  );
}

/**
 * Campo numérico que despacha **al confirmar**, no al teclear.
 *
 * Es el mismo criterio que la celda de duración de la tabla y por el mismo
 * motivo: cada acción del borrador apila su propio paso de deshacer, así que
 * escribir "12" dejaría dos. La `key` fuerza a rehacer el campo cuando el valor
 * cambia por otra vía —deshacer, o un arrastre en el Gantt—, que si no seguiría
 * enseñando lo tecleado.
 */
function Numero({
  etiqueta,
  sufijo,
  valor,
  ancho,
  deshabilitado,
  ayuda,
  onConfirmar,
}: {
  readonly etiqueta: string;
  readonly sufijo: string;
  readonly valor: number | null;
  readonly ancho: number;
  readonly deshabilitado: boolean;
  readonly ayuda: string;
  readonly onConfirmar: (valor: number) => void;
}) {
  function confirmar(texto: string): void {
    const numero = Number(texto.trim());
    if (texto.trim() === '' || !Number.isFinite(numero)) return;
    onConfirmar(numero);
  }

  return (
    <label className="cinta__campo" title={ayuda}>
      <span className="field__label">{etiqueta}</span>
      <input
        key={valor ?? 'vacio'}
        className="input"
        type="number"
        step={0.5}
        style={{ width: ancho }}
        defaultValue={valor ?? ''}
        disabled={deshabilitado}
        aria-label={etiqueta}
        onBlur={(evento) => confirmar(evento.currentTarget.value)}
        onKeyDown={(evento) => {
          if (evento.key === 'Enter') evento.currentTarget.blur();
        }}
      />
      <span className="field__label">{sufijo}</span>
    </label>
  );
}

