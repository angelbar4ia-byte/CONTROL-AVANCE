/**
 * Modalidad "Cantidades por escala": el área del Gantt sustituida por una
 * rejilla de columnas, una por periodo del eje (§7.4, §7.6).
 *
 * Es la lectura volumétrica del mismo programa. Donde el Gantt contesta
 * *"¿cuándo se hace?"*, esto contesta *"¿cuánto se hace cada semana?"*, que es
 * lo que hace falta para pedir material y para dimensionar la cuadrilla.
 *
 * ## De sólo lectura, y se dice en pantalla
 *
 * El reparto **no existe como dato**: se deriva de la cantidad del presupuesto
 * y de la colocación del borrador (`reparto.ts`, que explica el cómo y el por
 * qué). Ninguna celda es un campo, y el pie de la pantalla lo rotula. Capturar
 * un reparto a mano —"esta semana quiero colar 40 m³ y no 33"— sería un dato
 * nuevo con su tabla y su endpoint, y ofrecer aquí un campo que el `POST` va a
 * ignorar sería peor que no ofrecerlo.
 *
 * ## Comparte virtualización y sincronía con el Gantt
 *
 * Es la mitad derecha del panel dividido, así que monta el mismo virtualizador
 * con el mismo `ALTO_FILA` y el mismo `scrollMargin`, y usa el mismo
 * contenedor de scroll que el Gantt reemplaza. Cambiar de modalidad no puede
 * desalinear los renglones de su descripción, que es lo que pasaría si esta
 * vista midiera sus filas de otra manera.
 *
 * Componente de presentación (§12.11): el reparto llega calculado.
 */

import { useVirtualizer } from '@tanstack/react-virtual';

import { fmtMXN, fmtNum } from '@/lib/formato';
import type { BandaEje } from './bandasPrograma';
import { ALTO_ENCABEZADO, ALTO_FILA } from './ejePrograma';
import type { FilaPrograma } from './filasPrograma';
import type { RenglonRejilla } from './reparto';
import type { Magnitud } from './vistaGantt';

/**
 * Ancho de una columna de periodo, en px.
 *
 * Es fijo y no proporcional al zoom: lo que tiene que caber aquí es una cifra
 * con dos decimales, y a 6 px por día una columna semanal mediría cuarenta y
 * dos píxeles y no cabría ninguna. La rejilla deja de ser un calendario a
 * escala y pasa a ser una tabla — que es lo que es.
 */
const ANCHO_PERIODO = 92;

interface Props {
  readonly filas: readonly FilaPrograma[];
  readonly periodos: readonly BandaEje[];
  readonly rejilla: ReadonlyMap<string, RenglonRejilla>;
  readonly magnitud: Magnitud;
  readonly seleccionado: string | null;
  readonly onSeleccionar: (nodoId: string) => void;
  readonly contenedorRef: React.RefObject<HTMLDivElement>;
  readonly onScroll: (scrollTop: number) => void;
}

export function RejillaCantidades({
  filas,
  periodos,
  rejilla,
  magnitud,
  seleccionado,
  onSeleccionar,
  contenedorRef,
  onScroll,
}: Props) {
  const virtualizador = useVirtualizer({
    count: filas.length,
    getScrollElement: () => contenedorRef.current,
    estimateSize: () => ALTO_FILA,
    overscan: 10,
    scrollMargin: ALTO_ENCABEZADO,
  });

  const ancho = (periodos.length + 1) * ANCHO_PERIODO;

  return (
    <div
      className="prog-split__lado"
      ref={contenedorRef}
      onScroll={(evento) => onScroll(evento.currentTarget.scrollTop)}
      role="grid"
      aria-label={`Cantidades por periodo (${etiquetaMagnitud(magnitud)}), derivadas y de lectura`}
      aria-rowcount={filas.length}
    >
      <div className="prog-cant" style={{ width: ancho }}>
        <div className="prog-cant__head" role="row" style={{ height: ALTO_ENCABEZADO }}>
          {periodos.map((periodo) => (
            <div
              key={periodo.dia}
              className="prog-cant__th"
              role="columnheader"
              style={{ width: ANCHO_PERIODO }}
              title={periodo.titulo}
            >
              {periodo.etiqueta}
            </div>
          ))}
          <div
            className="prog-cant__th prog-cant__th--total"
            role="columnheader"
            style={{ width: ANCHO_PERIODO }}
            title="Suma de los periodos del renglón"
          >
            Total
          </div>
        </div>

        <div role="rowgroup" style={{ height: virtualizador.getTotalSize(), position: 'relative' }}>
          {virtualizador.getVirtualItems().map((item) => {
            const fila = filas[item.index];
            if (!fila) return null;
            const renglon = rejilla.get(fila.nodoId);
            return (
              <div
                key={fila.nodoId}
                className={`prog-cant__fila${seleccionado === fila.nodoId ? ' is-selected' : ''}`}
                role="row"
                aria-rowindex={item.index + 2}
                aria-selected={seleccionado === fila.nodoId}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  height: ALTO_FILA,
                  width: ancho,
                  transform: `translateY(${item.start - ALTO_ENCABEZADO}px)`,
                }}
                onClick={() => onSeleccionar(fila.nodoId)}
              >
                {periodos.map((periodo, indice) => {
                  const valor = renglon?.celdas[indice] ?? null;
                  return (
                    <div
                      key={periodo.dia}
                      className={`prog-cant__celda mono tnum${valor === 0 ? ' is-cero' : ''}`}
                      role="gridcell"
                      style={{ width: ANCHO_PERIODO }}
                    >
                      {formatear(valor, magnitud)}
                    </div>
                  );
                })}
                <div
                  className="prog-cant__celda prog-cant__celda--total mono tnum"
                  role="gridcell"
                  style={{ width: ANCHO_PERIODO }}
                >
                  {formatear(renglon?.total ?? null, magnitud)}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/**
 * Una celda vacía y un cero no son lo mismo y se dibujan distinto: el cero es
 * un dato —esa semana no se trabaja, porque cae en una pausa (§7.6)— y el
 * hueco es "aquí no hay cifra que repartir", que es el caso de un resumen en la
 * magnitud cantidad, cuyas unidades no se pueden sumar.
 */
function formatear(valor: number | null, magnitud: Magnitud): string {
  if (valor === null) return '';
  if (valor === 0) return '·';
  if (magnitud === 'importe') return fmtMXN(valor);
  if (magnitud === 'porcentaje') return `${fmtNum(valor)} %`;
  // La cantidad va sin unidad: es la misma en toda la fila y ya la dice la
  // columna Unidad de la tabla, a la altura del mismo renglón. Repetirla en
  // cada una de las treinta celdas no añadiría nada y las estrecharía.
  return fmtNum(valor);
}

function etiquetaMagnitud(magnitud: Magnitud): string {
  if (magnitud === 'importe') return 'importe';
  if (magnitud === 'porcentaje') return 'porcentaje del total';
  return 'cantidad';
}
