/**
 * Las correcciones propuestas al catálogo (Ola 3B): una corrección NO edita el catálogo, se registra como una nueva versión del
 * concepto. Costos la propone, Control de obra la autoriza o la rechaza y entonces nace el número de versión; la tabla muestra la
 * diferencia contra el catálogo vigente. Hoy trae una: la unidad de EST-02330 (de m2 a m), cuyo elemento aún no se construye.
 */

import type { ErrorApi } from '@/api/cliente';
import {
  getCorreccionesDeCatalogoApiV1CorreccionesDeCatalogoGetQueryKey,
  useAutorizarCorreccionApiV1CorreccionesDeCatalogoCorreccionIdAutorizarPost,
  useCorreccionesDeCatalogoApiV1CorreccionesDeCatalogoGet,
  useProponerCorreccionApiV1CorreccionesDeCatalogoPost,
  useRechazarCorreccionApiV1CorreccionesDeCatalogoCorreccionIdRechazarPost,
} from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';
import { queryClient } from '@/app/queryClient';

interface Props {
  readonly rol?: string | null;
}

const ESTADO: Record<string, string> = {
  sin_proponer: 'Sin proponer',
  pendiente: 'Pendiente de autorizar por Control de obra',
  autorizada: 'Autorizada',
  rechazada: 'Rechazada',
};
const unidad = (u: string) => (u === 'm2' ? 'm²' : u);

export function CorreccionesDelCatalogo({ rol }: Props) {
  const puedeProponer = rol === 'control_obra' || rol === 'costos';
  const puedeAutorizar = rol === 'control_obra';
  const consulta = useCorreccionesDeCatalogoApiV1CorreccionesDeCatalogoGet({ query: { enabled: puedeProponer } });
  const proponer = useProponerCorreccionApiV1CorreccionesDeCatalogoPost<ErrorApi>();
  const autorizar = useAutorizarCorreccionApiV1CorreccionesDeCatalogoCorreccionIdAutorizarPost<ErrorApi>();
  const rechazar = useRechazarCorreccionApiV1CorreccionesDeCatalogoCorreccionIdRechazarPost<ErrorApi>();
  if (!puedeProponer) return null;
  const filas = consulta.data ?? [];
  if (filas.length === 0) return null;

  const recargar = () => queryClient.invalidateQueries({ queryKey: getCorreccionesDeCatalogoApiV1CorreccionesDeCatalogoGetQueryKey() });
  const fallo = (e: unknown, texto: string) => window.alert(e instanceof Error ? e.message : texto);

  return (
    <section className="mct__bloque" aria-label="Correcciones propuestas al catálogo" data-correcciones-de-catalogo>
      <h3>Correcciones propuestas al catálogo</h3>
      <p className="text-mute text-xs">
        Una corrección no edita el catálogo: nace como nueva versión del concepto, la propone Costos y la autoriza Control de obra.
      </p>
      {filas.map((c) => (
        <div key={`${c.concepto_clave}:${c.campo}`} className="mct__bloque" data-correccion={c.concepto_clave}>
          <div>
            <b className="mono">{c.concepto_clave}</b> · {c.concepto}
          </div>
          <table className="mct__tabla" aria-label={`Diferencia de ${c.concepto_clave}`}>
            <thead>
              <tr>
                <th>Dato</th>
                <th>Catálogo vigente</th>
                <th>Versión propuesta</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Unidad</td>
                <td className="mono">{unidad(c.valor_catalogo)}</td>
                <td className="mono">{unidad(c.valor_propuesto)}</td>
                <td>
                  <span className={c.estado === 'autorizada' ? 'badge badge--ok' : c.estado === 'pendiente' ? 'badge badge--warn' : 'badge badge--outline'}>
                    {ESTADO[c.estado]}
                    {c.version_vigente ? ` · versión ${c.version_vigente}` : ''}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
          <p className="text-xs">{c.motivo}</p>
          <p className="text-mute text-xs">
            Fuente: {c.fuente} · {c.preguntas.join(', ')}. {c.nota}
          </p>
          <div className="row" style={{ gap: 6 }}>
            {c.estado === 'sin_proponer' && (
              <button
                type="button"
                className="btn btn--sm"
                onClick={() =>
                  proponer
                    .mutateAsync({ data: { concepto_clave: c.concepto_clave, campo: c.campo } })
                    .then(recargar)
                    .catch((e: unknown) => fallo(e, 'No se pudo proponer la corrección.'))
                }
              >
                Proponer versión nueva ({unidad(c.valor_catalogo)} → {unidad(c.valor_propuesto)})
              </button>
            )}
            {c.estado === 'pendiente' && c.pendiente_id && puedeAutorizar && (
              <>
                <button
                  type="button"
                  className="btn btn--sm btn--primary"
                  onClick={() =>
                    autorizar
                      .mutateAsync({ correccionId: c.pendiente_id as string })
                      .then(recargar)
                      .catch((e: unknown) => fallo(e, 'No se pudo autorizar la corrección.'))
                  }
                >
                  Autorizar
                </button>
                <button
                  type="button"
                  className="btn btn--sm"
                  onClick={() =>
                    rechazar
                      .mutateAsync({ correccionId: c.pendiente_id as string, data: {} })
                      .then(recargar)
                      .catch((e: unknown) => fallo(e, 'No se pudo rechazar la corrección.'))
                  }
                >
                  Rechazar
                </button>
              </>
            )}
          </div>
          {c.historial.length > 0 && (
            <ul className="text-xs" aria-label={`Historial de ${c.concepto_clave}`}>
              {c.historial.map((h) => (
                <li key={h.id}>
                  {h.estado === 'autorizada' ? `Versión ${h.version} autorizada` : h.estado === 'rechazada' ? 'Rechazada' : 'Pendiente'}: propuso{' '}
                  {h.propuso_nombre ?? '—'}
                  {h.decidio_nombre ? `, decidió ${h.decidio_nombre}` : ''}
                  {h.motivo_rechazo ? ` (${h.motivo_rechazo})` : ''}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </section>
  );
}
