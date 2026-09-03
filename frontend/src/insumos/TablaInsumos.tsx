/**
 * La matriz insumo × periodo (§7.3, §7.5).
 *
 * Componente de presentación: recibe las filas y los periodos ya calculados y
 * no decide nada salvo cómo se ven (§12.11). Así se puede probar sin red, que
 * es la convención de las pruebas de render de este repo.
 *
 * ## Por qué una tabla ancha y no dos paneles
 *
 * El editor del programa base resuelve lo ancho con un split de dos paneles y
 * scroll sincronizado, porque ahí la mitad izquierda es un árbol con jerarquía
 * y colapso. Aquí la parte fija son tres columnas planas —clave, descripción,
 * unidad— y el `<table>` de siempre alcanza: `overflow-x` en el contenedor y
 * `min-width: max-content` en la tabla. Menos maquinaria para el mismo
 * resultado, y el encabezado pegajoso ya lo trae `.table th`.
 *
 * ## El desglose
 *
 * Un insumo aparece en varios conceptos y en varias obras; el renglón enseña la
 * suma porque se compra por insumo. Cuando una cifra sorprende hay que poder
 * ver de dónde salió, así que el renglón se abre y muestra el reparto por obra
 * y concepto, de mayor a menor — que es el orden en que se contesta "¿quién
 * pide tanto?".
 */

import { ChevronDown, ChevronRight } from 'lucide-react';

import type {
  FilaDeInsumoRespuesta,
  ObractrlAdaptersApiV1InsumosPeriodoRespuesta as PeriodoRespuesta,
} from '@/api/generado/modelo';
import { fmtMXN, fmtNum } from '@/lib/formato';
import { etiquetaTipo } from './reglas';

/** Ancho fijo por columna de periodo, como la rejilla del programa base. */
const ANCHO_PERIODO = 92;

interface Props {
  readonly periodos: readonly PeriodoRespuesta[];
  readonly filas: readonly FilaDeInsumoRespuesta[];
  /** Insumos con el desglose abierto. */
  readonly abiertos: ReadonlySet<string>;
  readonly onAlternar: (insumoId: string) => void;
  /** El rol ve importes (§4). Con `false` la columna no se dibuja. */
  readonly conImportes: boolean;
  /** Hay almacén contra el cual comparar: falso en una simulación. */
  readonly conSurtido: boolean;
}

export function TablaInsumos({
  periodos,
  filas,
  abiertos,
  onAlternar,
  conImportes,
  conSurtido,
}: Props) {
  const columnasFijas = 4 + (conSurtido ? 1 : 0) + (conImportes ? 1 : 0);

  return (
    <div className="table-wrap">
      <div className="table-scroll">
        <table className="table" style={{ minWidth: 'max-content' }}>
          <thead>
            <tr>
              <th style={{ minWidth: 120 }}>Clave</th>
              <th style={{ minWidth: 240 }}>Descripción</th>
              <th style={{ minWidth: 64 }}>Unidad</th>
              {periodos.map((periodo) => (
                <th
                  key={periodo.clave}
                  className="is-num"
                  style={{ width: ANCHO_PERIODO, minWidth: ANCHO_PERIODO }}
                  title={`${periodo.desde} → ${periodo.hasta}`}
                >
                  {periodo.etiqueta}
                </th>
              ))}
              <th className="is-num" style={{ minWidth: 96 }}>
                Total
              </th>
              {conSurtido && (
                <th
                  className="is-num"
                  style={{ minWidth: 110 }}
                  title="Lo que ya salió del almacén. No es una existencia: todavía no hay inventario."
                >
                  Ya surtido
                </th>
              )}
              {conImportes && (
                <th className="is-num" style={{ minWidth: 120 }}>
                  Importe
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {filas.map((fila) => {
              const abierto = abiertos.has(fila.insumo_id);
              return (
                <FilaInsumo
                  key={fila.insumo_id}
                  fila={fila}
                  abierto={abierto}
                  columnas={periodos.length + columnasFijas}
                  onAlternar={onAlternar}
                  conImportes={conImportes}
                  conSurtido={conSurtido}
                />
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FilaInsumo({
  fila,
  abierto,
  columnas,
  onAlternar,
  conImportes,
  conSurtido,
}: {
  readonly fila: FilaDeInsumoRespuesta;
  readonly abierto: boolean;
  readonly columnas: number;
  readonly onAlternar: (insumoId: string) => void;
  readonly conImportes: boolean;
  readonly conSurtido: boolean;
}) {
  const hayDesglose = fila.desglose !== undefined && fila.desglose.length > 0;

  return (
    <>
      <tr>
        <td className="mono">
          <div className="row gap-2" style={{ alignItems: 'center' }}>
            {hayDesglose ? (
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                aria-expanded={abierto}
                aria-label={`Desglose de ${fila.clave}`}
                onClick={() => onAlternar(fila.insumo_id)}
                style={{ padding: 0, lineHeight: 1 }}
              >
                {abierto ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </button>
            ) : (
              <span style={{ width: 14 }} />
            )}
            <span>{fila.clave}</span>
          </div>
        </td>
        <td>
          <div className="col gap-2" style={{ alignItems: 'flex-start' }}>
            <span>{fila.descripcion}</span>
            <span className="text-mute text-xs">
              {etiquetaTipo(fila.tipo)}
              {/* El plazo solo se anuncia cuando alguien lo capturó: sin él
                  manda la anticipación global y decirlo aquí sería repetir el
                  mismo número en cada renglón. */}
              {fila.dias_entrega !== null && fila.dias_entrega !== undefined
                ? ` · pedir ${fila.dias_entrega} d antes`
                : ''}
            </span>
          </div>
        </td>
        <td className="mono text-xs">{fila.unidad ?? ''}</td>
        {fila.cantidades.map((cantidad, indice) => (
          <td
            // eslint-disable-next-line react/no-array-index-key
            key={indice}
            className="mono tnum is-num text-xs"
            style={{ opacity: cantidad === 0 ? 0.35 : 1 }}
          >
            {/* Cero es un dato —esa semana no se ocupa nada— y por eso se
                escribe en vez de dejarse en blanco, solo que atenuado. */}
            {fmtNum(cantidad)}
          </td>
        ))}
        <td className="mono tnum is-num is-key">{fmtNum(fila.total)}</td>
        {conSurtido && (
          <td className="mono tnum is-num text-xs">
            {fila.ya_surtido === null || fila.ya_surtido === undefined
              ? ''
              : fmtNum(fila.ya_surtido)}
          </td>
        )}
        {conImportes && (
          <td className="mono tnum is-num">
            {fila.importe === null || fila.importe === undefined
              ? ''
              : fmtMXN(fila.importe)}
          </td>
        )}
      </tr>

      {abierto && hayDesglose && (
        <tr>
          <td colSpan={columnas} style={{ background: 'var(--c-panel-2)' }}>
            <div className="col gap-2" style={{ padding: '8px 0 8px 28px' }}>
              <span className="text-mute text-xs">
                De dónde sale, en el rango consultado:
              </span>
              {fila.desglose?.map((reparto) => (
                <div
                  key={`${reparto.obra_id}-${reparto.concepto_clave}`}
                  className="row gap-8 text-xs"
                  style={{ alignItems: 'center' }}
                >
                  <span className="mono" style={{ minWidth: 140 }}>
                    {reparto.concepto_clave}
                  </span>
                  <span className="mono tnum">{fmtNum(reparto.cantidad)}</span>
                  <span className="text-mute mono" style={{ fontSize: 11 }}>
                    obra {reparto.obra_id.slice(0, 8)}
                  </span>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
