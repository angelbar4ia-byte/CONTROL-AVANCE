/**
 * Mitad izquierda del editor de programa base: la tabla jerárquica (§7.4, §7.5).
 *
 * Es el precedente de `ArbolPrototipo` llevado a una lista **plana y
 * virtualizada**. La diferencia no es estética: `ArbolPrototipo` anida `<div>`
 * por profundidad y monta el árbol entero, lo cual va bien para mirar un
 * prototipo pero no para programarlo — con ~155 nodos hay que poder recorrerlo
 * a 60 fps y, sobre todo, cada renglón tiene que caer a la **misma altura** que
 * su barra del Gantt, y eso sólo se garantiza con una lista de renglones de
 * altura fija (`ALTO_FILA`, en `ejePrograma.ts`). Por eso el aplanado, el
 * colapso y la numeración viven en `filasPrograma.ts` y aquí sólo se pinta.
 *
 * Componente de presentación: recibe las filas ya calculadas y no decide nada
 * salvo cómo se ven (§12.11). Lo único que produce son gestos —plegar,
 * seleccionar, capturar una duración— que despacha hacia arriba.
 *
 * ## Qué columnas hay y por qué faltan las otras
 *
 * Sólo las que tienen dato real en este sistema. "Días laborables" y "Días
 * calendario" son la distinción trabajo/span que ya vive en `tramos.ts`: la
 * primera es la suma de los tramos —los días que de verdad se trabaja— y la
 * segunda lo que la barra ocupa de punta a punta, que es mayor cuando la
 * actividad está interrumpida. Unidad, cantidad e importe salen del presupuesto
 * vigente del prototipo, unidos por `prototipo_nodo_id` igual que en
 * `ArbolPrototipo`.
 *
 * ## Cuáles se ven lo decide el menú, no esta hoja
 *
 * El catálogo, el orden, los anchos y el congelado están en
 * `columnasPrograma.ts`; aquí llega la lista ya filtrada y la plantilla de
 * `grid-template-columns` viaja como `--prog-cols`. Es lo que permite apagar
 * columnas sin que el encabezado y los renglones se descuadren: los dos leen la
 * misma plantilla de la misma variable.
 */

import { useVirtualizer } from '@tanstack/react-virtual';
import { ChevronDown, ChevronRight } from 'lucide-react';

import { fmtMXN, fmtNum } from '@/lib/formato';
import {
  plantillaDeColumnas,
  type ColumnaPrograma,
} from './columnasPrograma';
import { ALTO_ENCABEZADO, ALTO_FILA, etiquetaDeDia, type EjePrograma } from './ejePrograma';
import type { FilaPrograma } from './filasPrograma';
import { etiquetaClaseNodo } from './reglas';
import type { MagnitudesFila } from './reparto';
import type { VistaGantt } from './vistaGantt';

/**
 * Etiqueta corta de la clase para la columna Tipo.
 *
 * `etiquetaClaseNodo` da el nombre completo —"Nivel de construcción"— que es el
 * correcto en un `select` y no cabe en una columna de 74 px. Se muestra la
 * corta y la completa va en el `title`, que es donde sigue estando disponible.
 */
const TIPO_CORTO: Record<string, string> = {
  nivel: 'Nivel',
  etapa: 'Etapa',
  concepto: 'Concepto',
};

interface Props {
  readonly filas: readonly FilaPrograma[];
  readonly eje: EjePrograma;
  /** Columnas encendidas, en el orden del catálogo (`columnasPrograma.ts`). */
  readonly columnas: readonly ColumnaPrograma[];
  /** `left` de cada columna congelada; vacío con el congelado apagado. */
  readonly congelados: ReadonlyMap<string, number>;
  readonly vista: VistaGantt;
  readonly magnitudes: ReadonlyMap<string, MagnitudesFila>;
  /** Nodos de la cadena crítica del borrador (`rutaCritica.ts`). */
  readonly criticas: ReadonlySet<string>;
  readonly colapsados: ReadonlySet<string>;
  readonly seleccionado: string | null;
  /** El rol puede capturar; en lectura las celdas no se editan. */
  readonly editable: boolean;
  readonly onAlternar: (nodoId: string) => void;
  readonly onSeleccionar: (nodoId: string) => void;
  readonly onDuracion: (nodoId: string, dias: number | null) => void;
  readonly onInicio: (nodoId: string, dia: number | null) => void;
  readonly onTermino: (nodoId: string, dia: number) => void;
  /** Contenedor de scroll: lo comparte con el Gantt (`sincronia.ts`). */
  readonly contenedorRef: React.RefObject<HTMLDivElement>;
  readonly onScroll: (scrollTop: number) => void;
}

export function TablaPrograma({
  filas,
  eje,
  columnas,
  congelados,
  vista,
  magnitudes,
  criticas,
  colapsados,
  seleccionado,
  editable,
  onAlternar,
  onSeleccionar,
  onDuracion,
  onInicio,
  onTermino,
  contenedorRef,
  onScroll,
}: Props) {
  const virtualizador = useVirtualizer({
    count: filas.length,
    getScrollElement: () => contenedorRef.current,
    estimateSize: () => ALTO_FILA,
    overscan: 10,
    // El encabezado pegajoso está **dentro** del contenedor de scroll, así que
    // la lista no arranca en el píxel 0: sin decírselo, el virtualizador
    // calcularía la ventana un renglón corrido y el último no llegaría a
    // montarse al final del recorrido.
    scrollMargin: ALTO_ENCABEZADO,
  });

  const clasesTabla = [
    'prog-tabla',
    vista.rayado ? 'is-rayada' : '',
    vista.lineas ? 'is-lineada' : '',
    vista.colorPorNivel ? 'is-tenida' : '',
  ]
    .filter((clase) => clase !== '')
    .join(' ');

  return (
    <div
      className="prog-split__lado"
      ref={contenedorRef}
      onScroll={(evento) => onScroll(evento.currentTarget.scrollTop)}
      role="grid"
      aria-label="Renglones del programa base"
      aria-rowcount={filas.length}
    >
      <div
        className={clasesTabla}
        style={{ ['--prog-cols' as string]: plantillaDeColumnas(columnas) }}
      >
        <div className="prog-tabla__head" role="row" style={{ height: ALTO_ENCABEZADO }}>
          {columnas.map((columna) => (
            <div
              key={columna.clave}
              className={`prog-tabla__th${congelados.has(columna.clave) ? ' is-congelada' : ''}`}
              role="columnheader"
              title={columna.ayuda}
              style={estiloCongelado(congelados, columna.clave)}
            >
              {columna.titulo}
            </div>
          ))}
        </div>

        <div
          role="rowgroup"
          style={{ height: virtualizador.getTotalSize(), position: 'relative' }}
        >
          {virtualizador.getVirtualItems().map((item) => {
            const fila = filas[item.index];
            if (!fila) return null;
            return (
              <Renglon
                key={fila.nodoId}
                fila={fila}
                eje={eje}
                columnas={columnas}
                congelados={congelados}
                vista={vista}
                magnitudes={magnitudes.get(fila.nodoId)}
                esCritica={criticas.has(fila.nodoId)}
                indice={item.index}
                desplazamiento={item.start - ALTO_ENCABEZADO}
                colapsado={colapsados.has(fila.nodoId)}
                seleccionado={seleccionado === fila.nodoId}
                editable={editable}
                onAlternar={onAlternar}
                onSeleccionar={onSeleccionar}
                onDuracion={onDuracion}
                onInicio={onInicio}
                onTermino={onTermino}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

/**
 * `position: sticky` con su desplazamiento, o nada.
 *
 * El `z-index` mantiene el bloque congelado por encima de lo que pasa por
 * debajo al correr la tabla; el `background: inherit` lo pone la hoja, porque
 * sin fondo propio el contenido de las columnas de la derecha se vería a través
 * de las congeladas — que es el fallo clásico de una tabla con `sticky`.
 */
function estiloCongelado(
  congelados: ReadonlyMap<string, number>,
  clave: string,
): React.CSSProperties | undefined {
  const izquierda = congelados.get(clave);
  if (izquierda === undefined) return undefined;
  return { position: 'sticky', left: izquierda, zIndex: 1 };
}

/**
 * Un renglón.
 *
 * El tinte por profundidad es lo que hace legible el árbol sin contar
 * sangrías: los dos primeros escalones en gris y azul, el tercero en verde y
 * el concepto en blanco —que es, además, el único donde se captura—. La
 * sangría se aplica **dentro** de la celda de descripción y no al renglón, o
 * las columnas numéricas dejarían de alinear entre profundidades (§estilos,
 * mismo criterio que `.tree--tabla`).
 */
function Renglon({
  fila,
  eje,
  columnas,
  congelados,
  vista,
  magnitudes,
  esCritica,
  indice,
  desplazamiento,
  colapsado,
  seleccionado,
  editable,
  onAlternar,
  onSeleccionar,
  onDuracion,
  onInicio,
  onTermino,
}: {
  readonly fila: FilaPrograma;
  readonly eje: EjePrograma;
  readonly columnas: readonly ColumnaPrograma[];
  readonly congelados: ReadonlyMap<string, number>;
  readonly vista: VistaGantt;
  readonly magnitudes: MagnitudesFila | undefined;
  readonly esCritica: boolean;
  readonly indice: number;
  /** Píxeles desde el arranque de la lista; lo pone el virtualizador. */
  readonly desplazamiento: number;
  readonly colapsado: boolean;
  readonly seleccionado: boolean;
  readonly editable: boolean;
  readonly onAlternar: (nodoId: string) => void;
  readonly onSeleccionar: (nodoId: string) => void;
  readonly onDuracion: (nodoId: string, dias: number | null) => void;
  readonly onInicio: (nodoId: string, dia: number | null) => void;
  readonly onTermino: (nodoId: string, dia: number) => void;
}) {
  const tinte = `prog-tabla__fila--p${Math.min(3, fila.profundidad)}`;
  const clases = [
    'prog-tabla__fila',
    tinte,
    indice % 2 === 1 ? 'is-impar' : '',
    seleccionado ? 'is-selected' : '',
    esCritica && vista.rutaCritica ? 'is-critica' : '',
    fila.capturado || fila.esResumen ? '' : 'is-propuesta',
  ]
    .filter((clase) => clase !== '')
    .join(' ');

  return (
    <div
      className={clases}
      role="row"
      // `aria-rowindex` es 1-based y cuenta el encabezado, así que el primer
      // renglón de datos es el 2. Sin él, un lector de pantalla anunciaría
      // "fila 1 de 12" sobre lo montado y no sobre el programa completo, que es
      // el efecto secundario típico de virtualizar una tabla.
      aria-rowindex={indice + 2}
      aria-selected={seleccionado}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        height: ALTO_FILA,
        transform: `translateY(${desplazamiento}px)`,
      }}
      onClick={() => onSeleccionar(fila.nodoId)}
    >
      {columnas.map((columna) => (
        <Celda
          key={columna.clave}
          clave={columna.clave}
          estilo={estiloCongelado(congelados, columna.clave)}
          congelada={congelados.has(columna.clave)}
          fila={fila}
          eje={eje}
          magnitudes={magnitudes}
          colapsado={colapsado}
          editable={editable}
          onAlternar={onAlternar}
          onDuracion={onDuracion}
          onInicio={onInicio}
          onTermino={onTermino}
        />
      ))}
    </div>
  );
}

/**
 * Una celda, elegida por la clave de su columna.
 *
 * El `switch` sustituye a los doce `<div>` en orden fijo que había antes: con
 * las columnas apagables, la posición de una celda ya no dice cuál es, y
 * emparejarlas por índice sería el fallo que aparece la primera vez que alguien
 * apaga "Tipo" y ve la clave donde iba el tipo.
 */
function Celda({
  clave,
  estilo,
  congelada,
  fila,
  eje,
  magnitudes,
  colapsado,
  editable,
  onAlternar,
  onDuracion,
  onInicio,
  onTermino,
}: {
  readonly clave: string;
  readonly estilo: React.CSSProperties | undefined;
  readonly congelada: boolean;
  readonly fila: FilaPrograma;
  readonly eje: EjePrograma;
  readonly magnitudes: MagnitudesFila | undefined;
  readonly colapsado: boolean;
  readonly editable: boolean;
  readonly onAlternar: (nodoId: string) => void;
  readonly onDuracion: (nodoId: string, dias: number | null) => void;
  readonly onInicio: (nodoId: string, dia: number | null) => void;
  readonly onTermino: (nodoId: string, dia: number) => void;
}) {
  const base = `prog-tabla__celda${congelada ? ' is-congelada' : ''}`;

  switch (clave) {
    case 'num':
      return (
        <div className={`${base} mono tnum text-faint`} role="gridcell" style={estilo}>
          {fila.numero}
        </div>
      );

    case 'tipo':
      return (
        <div
          className={`${base} text-xs`}
          role="gridcell"
          style={estilo}
          title={etiquetaClaseNodo(fila.tipo)}
        >
          {TIPO_CORTO[fila.tipo] ?? fila.tipo}
        </div>
      );

    case 'clave':
      return (
        <div className={`${base} mono text-xs`} role="gridcell" style={estilo}>
          {fila.clave ?? ''}
        </div>
      );

    case 'descripcion':
      return (
        <div className={base} role="gridcell" style={estilo}>
          <span className="prog-tabla__nombre" style={{ paddingLeft: fila.profundidad * 14 }}>
            {fila.tieneHijos ? (
              <button
                type="button"
                className="prog-tabla__caret"
                aria-expanded={!colapsado}
                aria-label={`${colapsado ? 'Expandir' : 'Colapsar'} ${fila.descripcion}`}
                onClick={(evento) => {
                  evento.stopPropagation();
                  onAlternar(fila.nodoId);
                }}
              >
                {colapsado ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
              </button>
            ) : (
              <span aria-hidden className="prog-tabla__caret" />
            )}
            <span
              style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              title={fila.descripcion}
            >
              {fila.descripcion}
            </span>
            {fila.enCiclo && (
              <span
                className="badge badge--danger"
                title="Participa de un ciclo de precedencias (§6)"
              >
                ciclo
              </span>
            )}
          </span>
        </div>
      );

    case 'unidad':
      return (
        <div className={`${base} mono text-xs`} role="gridcell" style={estilo}>
          {fila.unidad ?? ''}
        </div>
      );

    case 'cantidad':
      return (
        <div className={`${base} mono tnum text-xs`} role="gridcell" style={estilo}>
          {fila.cantidad === null ? '' : fmtNum(fila.cantidad)}
        </div>
      );

    case 'importe':
      return (
        <div className={`${base} mono tnum text-xs`} role="gridcell" style={estilo}>
          {magnitudes?.importe === null || magnitudes?.importe === undefined
            ? ''
            : fmtMXN(magnitudes.importe)}
        </div>
      );

    case 'peso':
      return (
        <div className={`${base} mono tnum text-xs`} role="gridcell" style={estilo}>
          {magnitudes?.pesoPct === null || magnitudes?.pesoPct === undefined
            ? ''
            : `${fmtNum(magnitudes.pesoPct)} %`}
        </div>
      );

    // Días laborables es la única celda capturable: es la duración del renglón
    // (`duracion_dias`), y sin ella el nodo no entra al POST. En un resumen es
    // la suma de sus hijos y por eso es de lectura — capturarla ahí duplicaría
    // los días de los conceptos que ya la componen (§7.4).
    case 'laborables':
      return (
        <div className={`${base} mono tnum text-xs`} role="gridcell" style={estilo}>
          {!editable ? (
            fila.diasLaborables === null ? (
              ''
            ) : (
              fmtNum(fila.diasLaborables)
            )
          ) : (
            <CeldaDuracion fila={fila} onDuracion={onDuracion} />
          )}
        </div>
      );

    case 'calendario':
      return (
        <div className={`${base} mono tnum text-xs`} role="gridcell" style={estilo}>
          {fila.diasCalendario === null ? '' : fmtNum(fila.diasCalendario)}
        </div>
      );

    // El inicio se captura: es el ancla del §7.5 (`inicio_dias`, 0043), que
    // manda sobre las predecesoras. En un resumen no —la ventana la ponen sus
    // hojas— y sin colocar tampoco, porque no hay qué clavar todavía.
    case 'inicio':
      return (
        <div className={`${base} mono text-xs`} role="gridcell" style={estilo}>
          {!editable || fila.inicioDias === null ? (
            fila.inicioDias === null ? (
              ''
            ) : (
              etiquetaDeDia(eje, fila.inicioDias)
            )
          ) : (
            <CeldaInicio fila={fila} eje={eje} onInicio={onInicio} />
          )}
        </div>
      );

    // El cierre se rotula con el **último día trabajado**, no con el día en
    // que la ventana termina: una actividad que arranca el día 1 y dura tres
    // cierra el día 3, no el 4.
    // El término también se captura: se traduce a duración (`fijarTermino`), y
    // en un resumen eso hereda hacia abajo igual que capturarle los días — es
    // la misma operación dicha de otra manera.
    case 'termino':
      return (
        <div className={`${base} mono text-xs`} role="gridcell" style={estilo}>
          {!editable || fila.finDias === null ? (
            fila.finDias === null ? (
              ''
            ) : (
              etiquetaDeDia(eje, Math.max(0, fila.finDias - 1))
            )
          ) : (
            <CeldaTermino fila={fila} eje={eje} onTermino={onTermino} />
          )}
        </div>
      );

    case 'holgura':
      return (
        <div className={`${base} mono tnum text-xs`} role="gridcell" style={estilo}>
          {fila.holguraDias === null ? '' : fmtNum(fila.holguraDias)}
        </div>
      );

    case 'pred':
      return (
        <div className={`${base} mono tnum text-xs`} role="gridcell" style={estilo}>
          {fila.nPredecesoras === 0 ? '' : fila.nPredecesoras}
        </div>
      );

    default:
      return null;
  }
}

/**
 * Captura de la duración de un renglón.
 *
 * Es un campo no controlado —`defaultValue` con `key`— para que teclear no
 * dispare un despacho por pulsación: cada acción del borrador apila su propio
 * paso de deshacer (`borrador.ts`), y escribir "12" dejaría dos. Se despacha al
 * salir del campo o con Enter. La `key` fuerza a React a rehacer el campo
 * cuando el valor cambia por otra vía —deshacer, o un arrastre en el Gantt—,
 * que si no seguiría enseñando lo tecleado.
 *
 * Vaciar el campo devuelve el nodo a **propuesta**: sin duración no viaja en el
 * POST (`duracion_dias` es obligatorio y `> 0`), que es la forma de sacar del
 * programa un nodo sin borrarlo del árbol.
 */
/**
 * El día en que arranca la actividad, capturable.
 *
 * Se teclea el **número de día** (1-based, como lo rotula la columna) y no la
 * fecha simulada: el programa base es una plantilla sin fechas propias (§7.5),
 * y las que enseña el eje son una simulación contra un arranque elegido. La
 * fecha va en el `title` para quien tenga el modo encendido.
 *
 * Vaciar la celda **desclava** la actividad: vuelve a colocarla su cadena de
 * precedencias. Por eso el `placeholder` dice de dónde sale el día cuando no
 * hay ancla — si no, un campo lleno y uno vacío se verían igual de decididos.
 */
function CeldaInicio({
  fila,
  eje,
  onInicio,
}: {
  readonly fila: FilaPrograma;
  readonly eje: EjePrograma;
  readonly onInicio: (nodoId: string, dia: number | null) => void;
}) {
  const anclada = fila.anclaDias !== null;

  function confirmar(texto: string): void {
    const limpio = texto.trim();
    if (limpio === '') {
      onInicio(fila.nodoId, null);
      return;
    }
    const numero = Number(limpio);
    if (!Number.isFinite(numero)) return;
    // La columna cuenta desde el Día 1 y el modelo desde el 0.
    onInicio(fila.nodoId, Math.max(0, Math.round(numero) - 1));
  }

  return (
    <label
      className={`cell-edit${anclada ? ' is-anclada' : ''}`}
      onClick={(evento) => evento.stopPropagation()}
      title={
        anclada
          ? `Arranque fijo: ${etiquetaDeDia(eje, fila.anclaDias ?? 0)}. Vacía la celda para que vuelva a mandar su cadena de precedencias.`
          : `${etiquetaDeDia(eje, fila.inicioDias ?? 0)} — lo decide su cadena de precedencias. Teclea un día para clavarla ahí.`
      }
    >
      <input
        key={fila.anclaDias ?? 'libre'}
        type="number"
        min={1}
        step={1}
        defaultValue={anclada ? (fila.anclaDias ?? 0) + 1 : ''}
        placeholder={String((fila.inicioDias ?? 0) + 1)}
        aria-label={`Día de arranque de ${fila.descripcion}`}
        onBlur={(evento) => confirmar(evento.currentTarget.value)}
        onKeyDown={(evento) => {
          if (evento.key === 'Enter') evento.currentTarget.blur();
        }}
      />
    </label>
  );
}

/**
 * El día en que la actividad **cierra**, capturable.
 *
 * Se teclea el último día trabajado —una actividad que arranca el día 1 y dura
 * tres cierra el día 3, no el 4—, que es lo mismo que rotula la columna. El
 * gesto lo traduce a duración, porque es lo que el contrato guarda (§7.5).
 */
function CeldaTermino({
  fila,
  eje,
  onTermino,
}: {
  readonly fila: FilaPrograma;
  readonly eje: EjePrograma;
  readonly onTermino: (nodoId: string, dia: number) => void;
}) {
  const ultimo = fila.finDias === null ? null : Math.max(0, fila.finDias - 1);

  function confirmar(texto: string): void {
    const limpio = texto.trim();
    if (limpio === '') return;
    const numero = Number(limpio);
    if (!Number.isFinite(numero)) return;
    // La columna cuenta desde el Día 1 y el modelo desde el 0.
    onTermino(fila.nodoId, Math.max(0, Math.round(numero) - 1));
  }

  return (
    <label
      className="cell-edit"
      onClick={(evento) => evento.stopPropagation()}
      title={`Cierra el ${etiquetaDeDia(eje, ultimo)}. Teclea otro día para estirar o acortar la actividad.`}
    >
      <input
        key={ultimo ?? 'vacio'}
        type="number"
        min={1}
        step={1}
        defaultValue={ultimo === null ? '' : ultimo + 1}
        aria-label={`Día de término de ${fila.descripcion}`}
        onBlur={(evento) => confirmar(evento.currentTarget.value)}
        onKeyDown={(evento) => {
          if (evento.key === 'Enter') evento.currentTarget.blur();
        }}
      />
    </label>
  );
}

function CeldaDuracion({
  fila,
  onDuracion,
}: {
  readonly fila: FilaPrograma;
  readonly onDuracion: (nodoId: string, dias: number | null) => void;
}) {
  const capturado = fila.diasLaborables;

  function confirmar(texto: string): void {
    const limpio = texto.trim();
    if (limpio === '') {
      onDuracion(fila.nodoId, null);
      return;
    }
    const numero = Number(limpio);
    if (!Number.isFinite(numero)) return;
    onDuracion(fila.nodoId, numero);
  }

  // Con la actividad partida la duración es la suma de sus tramos y no se
  // captura: dejar las dos cifras editables garantiza que un día discrepen
  // (§7.6). Se muestra de lectura y se edita arrastrando el borde de la barra.
  if (fila.tramos.length > 0) {
    return (
      <span title="Actividad interrumpida: la duración es la suma de sus tramos (§7.6)">
        {fmtNum(capturado)}
      </span>
    );
  }

  return (
    <label className="cell-edit" onClick={(evento) => evento.stopPropagation()}>
      <input
        key={capturado ?? 'vacio'}
        type="number"
        min={0}
        step={0.5}
        defaultValue={capturado ?? ''}
        aria-label={`Días laborables de ${fila.descripcion}`}
        onBlur={(evento) => confirmar(evento.currentTarget.value)}
        onKeyDown={(evento) => {
          if (evento.key === 'Enter') evento.currentTarget.blur();
        }}
      />
    </label>
  );
}
