/**
 * Incidencias — bandeja por rol (§7.8, §11.2, §11.3 workflow F).
 *
 * Pantalla compartida (§5.3): los cuatro sidebars la traen —«Mis
 * incidencias» (R), «Incidencias» (S, C, SI)— y se monta **una sola vez** en
 * `/incidencias` (`shell/navegacion.ts`). Lo que cambia por rol es el
 * alcance —RLS ya devuelve solo lo visible (§12.4)— y qué botones se ofrecen
 * (`reglas.ts`).
 *
 * Las incidencias con impacto `detiene` se marcan aparte: bloquean
 * actividades y disparan el recálculo de la ruta crítica (§6, §11.3 F.5).
 */

import { useState } from 'react';

import { useListarIncidenciasApiV1IncidenciasGet } from '@/api/generado/incidencias/incidencias';
import { EstatusIncidencia, type IncidenciaRespuesta } from '@/api/generado/modelo';
import { useSesion } from '@/app/sesion';
import { fmtFecha } from '@/lib/formato';
import { AltaIncidencia } from './AltaIncidencia';
import { PanelIncidencia } from './PanelIncidencia';
import {
  detieneObra,
  etiquetaEstatus,
  etiquetaImpacto,
  etiquetaTipo,
  tonoEstatusIncidencia,
  tonoImpacto,
} from './reglas';

const TABS: readonly { readonly valor: EstatusIncidencia | 'todas'; readonly etiqueta: string }[] = [
  { valor: 'todas', etiqueta: 'Todas' },
  ...Object.values(EstatusIncidencia).map((estatus) => ({
    valor: estatus,
    etiqueta: etiquetaEstatus(estatus),
  })),
];

export default function Incidencias() {
  const { sesion } = useSesion();
  const [tab, setTab] = useState<EstatusIncidencia | 'todas'>('todas');
  const [abriendoAlta, setAbriendoAlta] = useState(false);
  const [seleccionada, setSeleccionada] = useState<IncidenciaRespuesta | null>(null);

  const consulta = useListarIncidenciasApiV1IncidenciasGet({
    estatus: tab === 'todas' ? undefined : tab,
  });

  if (!sesion) return null;

  const filas = consulta.data ?? [];
  const detienen = filas.filter((i) => detieneObra(i.impacto)).length;

  // El cajón se refresca desde la lista: el contrato no publica
  // `GET /incidencias/{id}`, así que tras una acción se vuelve a leer la
  // bandeja y se recupera de ahí la fila abierta.
  const abierta =
    seleccionada === null ? null : (filas.find((i) => i.id === seleccionada.id) ?? seleccionada);

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">
            {sesion.rol === 'residente' ? 'Mi trabajo' : 'Control'}
          </div>
          <h1 className="page__title">
            {sesion.rol === 'residente' ? 'Mis incidencias' : 'Incidencias'}
          </h1>
          <div className="page__subtitle">
            Ciclo: abierta → programada → en atención → cierre solicitado →
            cerrada / rechazada (§6). Cualquier rol abre una incidencia;
            Supervisor y Control de obra programan, cierran y rechazan (§11.2).
          </div>
        </div>
        <div className="page__actions">
          <button type="button" className="btn btn--primary" onClick={() => setAbriendoAlta(true)}>
            Abrir incidencia
          </button>
        </div>
      </div>

      {detienen > 0 && (
        <div
          className="text-sm mb-8"
          role="alert"
          style={{
            color: 'var(--c-danger)',
            background: 'var(--c-danger-soft)',
            border: '1px solid var(--c-danger)',
            borderRadius: 'var(--r-md)',
            padding: '8px 12px',
          }}
        >
          <strong>{detienen}</strong> incidencia(s) con impacto «detiene»: frenan la
          obra, bloquean actividades y fuerzan el recálculo de la ruta crítica
          (§6, §11.3 F.5).
        </div>
      )}

      <div className="filterbar">
        <div className="tabs">
          {TABS.map((t) => (
            <button
              key={t.valor}
              type="button"
              className={`tabs__tab ${tab === t.valor ? 'is-active' : ''}`}
              onClick={() => setTab(t.valor)}
            >
              {t.etiqueta}
            </button>
          ))}
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Incidencia</th>
                <th>Título</th>
                <th>Tipo</th>
                <th>Impacto</th>
                <th>Estatus</th>
                <th>Obra</th>
                <th>Límite</th>
                <th className="cell-actions">Detalle</th>
              </tr>
            </thead>
            <tbody>
              {consulta.isLoading ? (
                <tr>
                  <td colSpan={8}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : filas.length === 0 ? (
                <tr>
                  <td colSpan={8}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      No hay incidencias en este filtro.
                    </div>
                  </td>
                </tr>
              ) : (
                filas.map((incidencia) => (
                  <tr key={incidencia.id}>
                    <td className="is-key" title={incidencia.id}>
                      {incidencia.id.slice(0, 8)}
                    </td>
                    <td>{incidencia.titulo}</td>
                    <td className="text-mute">{etiquetaTipo(incidencia.tipo)}</td>
                    <td>
                      <span className={`badge badge--${tonoImpacto(incidencia.impacto)}`}>
                        {etiquetaImpacto(incidencia.impacto)}
                      </span>
                    </td>
                    <td>
                      <span className={`badge badge--${tonoEstatusIncidencia(incidencia.estatus)}`}>
                        {etiquetaEstatus(incidencia.estatus)}
                      </span>
                    </td>
                    <td className="is-key">{incidencia.obra_id.slice(0, 8)}</td>
                    <td>{fmtFecha(incidencia.fecha_limite)}</td>
                    <td className="cell-actions">
                      <button
                        type="button"
                        className="btn btn--sm"
                        onClick={() => setSeleccionada(incidencia)}
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

      {abriendoAlta && (
        <AltaIncidencia
          obraIdInicial=""
          onCerrar={() => setAbriendoAlta(false)}
          onAbierta={() => {
            setAbriendoAlta(false);
            void consulta.refetch();
          }}
        />
      )}

      {abierta && (
        <PanelIncidencia
          incidencia={abierta}
          onCerrar={() => setSeleccionada(null)}
          onCambio={() => void consulta.refetch()}
        />
      )}
    </div>
  );
}
