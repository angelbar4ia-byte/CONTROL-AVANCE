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
 * actividad está interrumpida. Unidad y cantidad salen del presupuesto vigente
 * del prototipo, unidas por `prototipo_nodo_id` igual que en `ArbolPrototipo`.
 */

import { useVirtualizer } from '@tanstack/react-virtual';
import { ChevronDown, ChevronRight } from 'lucide-react';

import { fmtNum } from '@/lib/formato';
import { ALTO_ENCABEZADO, ALTO_FILA, etiquetaDeDia, type EjePrograma } from './ejePrograma';
import type { FilaPrograma } from './filasPrograma';
import { etiquetaClaseNodo } from './reglas';

/** Las doce columnas, en el orden del `grid-template-columns` de la hoja. */
const COLUMNAS: readonly { readonly clave: string; readonly titulo: string }[] = [
  { clave: 'num', titulo: '#' },
  { clave: 'tipo', titulo: 'Tipo' },
  { clave: 'clave', titulo: 'Clave' },
  { clave: 'descripcion', titulo: 'Descripción' },
  { clave: 'unidad', titulo: 'Unidad' },
  { clave: 'cantidad', titulo: 'Cantidad' },
  { clave: 'laborables', titulo: 'Días lab.' },
  { clave: 'calendario', titulo: 'Días cal.' },
  { clave: 'inicio', titulo: 'Inicio' },
  { clave: 'termino', titulo: 'Término' },
  { clave: 'holgura', titulo: 'Holgura' },
  { clave: 'pred', titulo: 'Pred.' },
];

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
  readonly colapsados: ReadonlySet<string>;
  readonly seleccionado: string | null;
  /** El rol puede capturar; en lectura las celdas no se editan. */
  readonly editable: boolean;
  readonly onAlternar: (nodoId: string) => void;
  readonly onSeleccionar: (nodoId: string) => void;
  readonly onDuracion: (nodoId: string, dias: number | null) => void;
  /** Contenedor de scroll: lo comparte con el Gantt (`sincronia.ts`). */
  readonly contenedorRef: React.RefObject<HTMLDivElement>;
  readonly onScroll: (scrollTop: number) => void;
}

export function TablaPrograma({
  filas,
  eje,
  colapsados,
  seleccionado,
  editable,
  onAlternar,
  onSeleccionar,
  onDuracion,
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

  return (
    <div
      className="prog-split__lado"
      ref={contenedorRef}
      onScroll={(evento) => onScroll(evento.currentTarget.scrollTop)}
      role="grid"
      aria-label="Renglones del programa base"
      aria-rowcount={filas.length}
    >
      <div className="prog-tabla">
        <div className="prog-tabla__head" role="row" style={{ height: ALTO_ENCABEZADO }}>
          {COLUMNAS.map((columna) => (
            <div key={columna.clave} className="prog-tabla__th" role="columnheader">
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
                indice={item.index}
                desplazamiento={item.start - ALTO_ENCABEZADO}
                colapsado={colapsados.has(fila.nodoId)}
                seleccionado={seleccionado === fila.nodoId}
                editable={editable}
                onAlternar={onAlternar}
                onSeleccionar={onSeleccionar}
                onDuracion={onDuracion}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
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
  indice,
  desplazamiento,
  colapsado,
  seleccionado,
  editable,
  onAlternar,
  onSeleccionar,
  onDuracion,
}: {
  readonly fila: FilaPrograma;
  readonly eje: EjePrograma;
  readonly indice: number;
  /** Píxeles desde el arranque de la lista; lo pone el virtualizador. */
  readonly desplazamiento: number;
  readonly colapsado: boolean;
  readonly seleccionado: boolean;
  readonly editable: boolean;
  readonly onAlternar: (nodoId: string) => void;
  readonly onSeleccionar: (nodoId: string) => void;
  readonly onDuracion: (nodoId: string, dias: number | null) => void;
}) {
  const tinte = `prog-tabla__fila--p${Math.min(3, fila.profundidad)}`;
  const clases = [
    'prog-tabla__fila',
    tinte,
    seleccionado ? 'is-selected' : '',
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
      <div className="prog-tabla__celda mono tnum text-faint" role="gridcell">
        {fila.numero}
      </div>
      <div
        className="prog-tabla__celda text-xs"
        role="gridcell"
        title={etiquetaClaseNodo(fila.tipo)}
      >
        {TIPO_CORTO[fila.tipo] ?? fila.tipo}
      </div>
      <div className="prog-tabla__celda mono text-xs" role="gridcell">
        {fila.clave ?? ''}
      </div>

      <div className="prog-tabla__celda" role="gridcell">
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
          {fila.conflicto && (
            <span
              className="badge badge--warn"
              title={
                'El nodo declara días propios y sus conceptos programados ocupan otros. ' +
                'La barra dibuja el resumen; decide cuál conservar (§7.5).'
              }
            >
              conflicto
            </span>
          )}
          {fila.enCiclo && (
            <span className="badge badge--danger" title="Participa de un ciclo de precedencias (§6)">
              ciclo
            </span>
          )}
        </span>
      </div>

      <div className="prog-tabla__celda mono text-xs" role="gridcell">
        {fila.unidad ?? ''}
      </div>
      <div className="prog-tabla__celda mono tnum text-xs" role="gridcell">
        {fila.cantidad === null ? '' : fmtNum(fila.cantidad)}
      </div>

      {/* Días laborables es la única celda capturable: es la duración del
          renglón (`duracion_dias`), y sin ella el nodo no entra al POST. En un
          resumen es la suma de sus hijos y por eso es de lectura — capturarla
          ahí duplicaría los días de los conceptos que ya la componen (§7.4). */}
      <div className="prog-tabla__celda mono tnum text-xs" role="gridcell">
        {fila.esResumen || !editable ? (
          fila.diasLaborables === null ? (
            ''
          ) : (
            fmtNum(fila.diasLaborables)
          )
        ) : (
          <CeldaDuracion fila={fila} onDuracion={onDuracion} />
        )}
      </div>

      <div className="prog-tabla__celda mono tnum text-xs" role="gridcell">
        {fila.diasCalendario === null ? '' : fmtNum(fila.diasCalendario)}
      </div>
      <div className="prog-tabla__celda mono text-xs" role="gridcell">
        {fila.inicioDias === null ? '' : etiquetaDeDia(eje, fila.inicioDias)}
      </div>
      {/* El cierre se rotula con el **último día trabajado**, no con el día en
          que la ventana termina: una actividad que arranca el día 1 y dura tres
          cierra el día 3, no el 4. */}
      <div className="prog-tabla__celda mono text-xs" role="gridcell">
        {fila.finDias === null ? '' : etiquetaDeDia(eje, Math.max(0, fila.finDias - 1))}
      </div>
      <div className="prog-tabla__celda mono tnum text-xs" role="gridcell">
        {fila.holguraDias === null ? '' : fmtNum(fila.holguraDias)}
      </div>
      <div className="prog-tabla__celda mono tnum text-xs" role="gridcell">
        {fila.nPredecesoras === 0 ? '' : fila.nPredecesoras}
      </div>
    </div>
  );
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
