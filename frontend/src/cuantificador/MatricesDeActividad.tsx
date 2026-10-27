/**
 * Las matrices internas de una actividad (cerebro WORKFLOWS.md §8.9, «Las hojas del árbol»; D-565,
 * D-583). El concepto es la matriz madre y un insumo puede ser otra matriz —nervaduras, trabes,
 * bastones—, a cualquier profundidad. Lo que se mide son esas matrices; su cantidad es de esta obra
 * y ajusta el importe de la actividad sin tocar su cantidad base ni el catálogo.
 */

import type { ErrorApi } from '@/api/cliente';
import type { MatricesDeActividadRespuesta } from '@/api/generado/modelo';
import { useMatricesDeLaActividadApiV1ActividadesActividadIdMatricesGet } from '@/api/generado/cuantificacion/cuantificacion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtMXN, fmtNum } from '@/lib/formato';

export function MatricesDeActividad({ actividadId }: { readonly actividadId: string }) {
  const consulta = useMatricesDeLaActividadApiV1ActividadesActividadIdMatricesGet<
    MatricesDeActividadRespuesta,
    ErrorApi
  >(actividadId);

  if (consulta.isLoading) return <div className="text-mute text-xs">Cargando matrices…</div>;
  if (consulta.error) return <ErrorBanner mensaje={consulta.error.message} />;
  const datos = consulta.data;
  if (!datos || datos.matrices.length === 0) {
    return <div className="text-mute text-xs">Este concepto no tiene matrices internas que medir.</div>;
  }
  return (
    <div className="col gap-4" role="region" aria-label={`Matrices de ${datos.concepto_clave ?? 'la actividad'}`}>
      <table className="table">
        <thead>
          <tr>
            <th>Matriz</th>
            <th className="is-num">Catálogo</th>
            <th className="is-num">Medido</th>
            <th className="is-num">Dif.</th>
          </tr>
        </thead>
        <tbody>
          {datos.matrices.map((m, i) => (
            <tr key={`${m.concepto_id}-${i}`}>
              <td style={{ paddingLeft: 12 + (m.nivel - 1) * 16 }}>
                <span className="mono">{m.clave}</span> · {m.descripcion}
                {m.unidad ? <span className="text-xs text-mute"> ({m.unidad})</span> : null}
                {m.cantidad_medida === null || m.cantidad_medida === undefined ? (
                  <span className="badge badge--outline" style={{ marginLeft: 6 }}>
                    Sin medir
                  </span>
                ) : null}
              </td>
              <td className="is-num">{fmtNum(m.cantidad_catalogo)}</td>
              <td className="is-num">{m.cantidad_medida != null ? fmtNum(m.cantidad_medida) : '—'}</td>
              <td className="is-num">{m.diferencia != null ? fmtNum(m.diferencia) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {datos.medidas > 0 && (
        <div className="text-xs">
          Lo medido ajusta el importe: {fmtMXN(Number(datos.importe))} → <strong>{fmtMXN(Number(datos.importe_ajustado))}</strong>{' '}
          ({Number(datos.importe_ajuste) >= 0 ? '+' : ''}
          {fmtMXN(Number(datos.importe_ajuste))}). La cantidad de la actividad no cambia.
        </div>
      )}
    </div>
  );
}

/** Opciones para elegir qué se mide dentro de una actividad: ella entera o una de sus matrices. */
export function OpcionesDeMatriz({ actividadId }: { readonly actividadId: string }) {
  const consulta = useMatricesDeLaActividadApiV1ActividadesActividadIdMatricesGet<
    MatricesDeActividadRespuesta,
    ErrorApi
  >(actividadId);
  const vistas = new Set<string>();
  return (
    <>
      {(consulta.data?.matrices ?? [])
        .filter((m) => (vistas.has(m.concepto_id) ? false : (vistas.add(m.concepto_id), true)))
        .map((m) => (
          <option key={m.concepto_id} value={m.concepto_id}>
            {'— '.repeat(m.nivel - 1)}
            {m.clave} · {m.descripcion}
          </option>
        ))}
    </>
  );
}
