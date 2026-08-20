/**
 * Cierres de obra — el acta de entrega (§11.3 D, §5.1).
 *
 * Era el único de los seis workflows del §11.3 sin nada de backend, y es la
 * culminación del piloto: se cierra la obra con la que se empezó.
 *
 * ## Compartida, aunque solo el SI la abra
 *
 * El §5.1 pone «Cierres de obra» en el sidebar del Super intendente porque es
 * quien **abre** el acta. Pero los cuatro roles tienen que ir a firmar la suya
 * (§11.3 D.2), así que la bandeja la ve cualquiera que vea la obra y el botón
 * de abrir aparece solo para quien puede.
 */

import { useState } from 'react';

import {
  useListarCierresDeObraApiV1CierresObraGet,
  useAbrirCierreDeObraApiV1ObrasObraIdCierreObraPost,
} from '@/api/generado/cierres-obra/cierres-obra';
import type { ResumenDeCierreRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { SelectorObra } from '@/lib/SelectorObra';
import { fmtFecha } from '@/lib/formato';
import { useClavesPorRecurso } from '@/lib/idempotencia';
import { PanelCierreDeObra } from './PanelCierreDeObra';
import { puedeAbrirCierre } from './reglas';

export default function CierresDeObra() {
  const { sesion } = useSesion();
  const [estatus, setEstatus] = useState<'todos' | 'en_proceso' | 'cerrada'>('todos');
  const [obraAAbrir, setObraAAbrir] = useState('');
  const [abierto, setAbierto] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const consulta = useListarCierresDeObraApiV1CierresObraGet<
    ResumenDeCierreRespuesta[],
    ErrorApi
  >(estatus === 'todos' ? undefined : { estatus });

  // Clave por recurso: abrir el cierre de la obra A y el de la B son
  // operaciones distintas (regla 1 del ROADMAP).
  const idempotente = useClavesPorRecurso();

  const abrir = useAbrirCierreDeObraApiV1ObrasObraIdCierreObraPost<ErrorApi>({
    mutation: {
      onSuccess: (cierre) => {
        setError(null);
        setObraAAbrir('');
        setAbierto(cierre.id);
        void consulta.refetch();
      },
      onError: (err) => setError(err.message),
    },
    ...idempotente,
  });

  if (!sesion) return null;

  const puedeAbrir = puedeAbrirCierre(sesion.rol);
  const filas = consulta.data ?? [];

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Control general</div>
          <h1 className="page__title">Cierres de obra</h1>
          <div className="page__subtitle">
            El acta de entrega (§11.3 D): el residente entrega, el supervisor da
            su visto bueno, control responde por calidad y expediente, y el super
            intendente firma. Con las cuatro partes, la obra queda entregada y se
            congela.
          </div>
        </div>
      </div>

      {error && <ErrorBanner mensaje={error} />}

      {puedeAbrir && (
        <div className="card mb-8">
          <div className="card__header">
            <h2 className="card__title">Abrir el cierre de una obra</h2>
            <div className="text-mute text-xs">
              Abrir con pendientes está bien: es lo que convoca al equipo a
              resolverlos
            </div>
          </div>
          <div className="card__body filterbar">
            <SelectorObra
              id="cierre-obra-nueva"
              etiqueta="Obra"
              valor={obraAAbrir}
              onCambio={setObraAAbrir}
            />
            <button
              type="button"
              className="btn btn--primary"
              disabled={abrir.isPending || obraAAbrir === ''}
              onClick={() => abrir.mutate({ obraId: obraAAbrir })}
            >
              {abrir.isPending ? 'Abriendo…' : 'Abrir cierre'}
            </button>
          </div>
        </div>
      )}

      <div className="filterbar">
        <div className="tabs">
          {(['todos', 'en_proceso', 'cerrada'] as const).map((valor) => (
            <button
              key={valor}
              type="button"
              className={`tabs__tab ${estatus === valor ? 'is-active' : ''}`}
              onClick={() => setEstatus(valor)}
            >
              {valor === 'todos'
                ? 'Todos'
                : valor === 'en_proceso'
                  ? 'En proceso'
                  : 'Entregadas'}
            </button>
          ))}
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Obra</th>
                <th>Estado del acta</th>
                <th>Estado de la obra</th>
                <th>Fecha de entrega</th>
                <th className="cell-actions">Detalle</th>
              </tr>
            </thead>
            <tbody>
              {consulta.isLoading ? (
                <tr>
                  <td colSpan={5}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : filas.length === 0 ? (
                <tr>
                  <td colSpan={5}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      No hay cierres de obra abiertos.
                      {puedeAbrir && ' Abre uno cuando una obra esté por entregarse.'}
                    </div>
                  </td>
                </tr>
              ) : (
                filas.map((cierre) => (
                  <tr key={cierre.id}>
                    <td className="is-key">{cierre.obra_clave}</td>
                    <td>
                      <span
                        className={`badge badge--${cierre.estatus === 'cerrada' ? 'ok' : 'warn'}`}
                      >
                        {cierre.estatus === 'cerrada' ? 'Cerrada' : 'En proceso'}
                      </span>
                    </td>
                    <td className="text-sm">{cierre.obra_estatus}</td>
                    <td className="mono">
                      {cierre.fecha ? fmtFecha(cierre.fecha) : '—'}
                    </td>
                    <td className="cell-actions">
                      <button
                        type="button"
                        className="btn btn--sm"
                        onClick={() => setAbierto(cierre.id)}
                      >
                        Abrir
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {abierto && (
        <PanelCierreDeObra
          cierreId={abierto}
          onCerrar={() => setAbierto(null)}
          onCambio={() => void consulta.refetch()}
        />
      )}
    </div>
  );
}
