/**
 * Incidencias — bandeja por rol (§7.8, §11.2, §11.3 workflow F).
 *
 * Pantalla compartida (§5.3): los cuatro sidebars la traen —«Mis
 * incidencias» (R), «Incidencias» (S, C, SI)— y se monta **una sola vez** en
 * `/incidencias` (`shell/navegacion.ts`). Lo que cambia por rol es el
 * alcance —RLS ya devuelve solo lo visible (§12.4)— y qué botones se ofrecen
 * (`reglas.ts`).
 *
 * ## Las cuatro tarjetas y las pestañas no son el mismo filtro
 *
 * Las tarjetas KPI cuentan **preguntas** —¿cuántas requieren acción?,
 * ¿cuántas detienen la obra ahora?, ¿cuántas están vencidas?, ¿cuántas
 * esperan a Control?— y una incidencia puede contestar "sí" a varias a la
 * vez: una que detiene y además está vencida cuenta en las dos tarjetas. Las
 * pestañas, en cambio, sí particionan la bandeja: cada incidencia cae en
 * exactamente una.
 *
 * ## Frente y sub-frente
 *
 * Vienen del **nivel** y la **etapa** (§7.4, migración 0050) — el mismo eje
 * que ya usan Avances y Control de cambio, no `frente_id` (que sigue siendo
 * el tipo de contratación, otro eje).
 */

import { useMemo, useState } from 'react';

import { useListarIncidenciasApiV1IncidenciasGet } from '@/api/generado/incidencias/incidencias';
import type { IncidenciaRespuesta } from '@/api/generado/modelo';
import { useSesion } from '@/app/sesion';
import { fmtFecha } from '@/lib/formato';
import { AltaIncidencia } from './AltaIncidencia';
import { PanelIncidencia } from './PanelIncidencia';
import {
  contarPorTipo,
  detieneAhora,
  diasDeAtraso,
  etiquetaDiasDeAtraso,
  etiquetaEstatus,
  etiquetaImpacto,
  etiquetaTipo,
  incidenciaVencida,
  requiereAccion,
  tonoEstatusIncidencia,
  tonoImpacto,
} from './reglas';

type Pestana = 'activas' | 'detienen' | 'vencidas' | 'cierre_solicitado' | 'cerradas' | 'todas';

const PESTANAS: readonly { readonly clave: Pestana; readonly etiqueta: string }[] = [
  { clave: 'activas', etiqueta: 'Activas' },
  { clave: 'detienen', etiqueta: 'Detienen' },
  { clave: 'vencidas', etiqueta: 'Vencidas' },
  { clave: 'cierre_solicitado', etiqueta: 'Cierre solicitado' },
  { clave: 'cerradas', etiqueta: 'Cerradas' },
  { clave: 'todas', etiqueta: 'Todas' },
];

function enPestana(incidencia: IncidenciaRespuesta, pestana: Pestana, hoy: Date): boolean {
  switch (pestana) {
    case 'todas':
      return true;
    case 'activas':
      return requiereAccion(incidencia.estatus);
    case 'detienen':
      return detieneAhora(incidencia.impacto, incidencia.estatus);
    case 'vencidas':
      return incidenciaVencida(incidencia.fecha_limite, incidencia.estatus, hoy);
    case 'cierre_solicitado':
      return incidencia.estatus === 'cierre_solicitado';
    case 'cerradas':
      return incidencia.estatus === 'cerrada' || incidencia.estatus === 'rechazada';
  }
}

export default function Incidencias() {
  const { sesion } = useSesion();
  const [pestana, setPestana] = useState<Pestana>('activas');
  const [tipo, setTipo] = useState<string | null>(null);
  const [abriendoAlta, setAbriendoAlta] = useState(false);
  const [seleccionada, setSeleccionada] = useState<IncidenciaRespuesta | null>(null);

  // Se trae la bandeja entera (sin filtro de estatus en el servidor): las
  // tarjetas y las pestañas cruzan estatus, impacto y fecha límite a la vez,
  // y siete idas distintas al backend para siete recortes del mismo dato
  // serían peor que filtrar una sola lista aquí.
  const consulta = useListarIncidenciasApiV1IncidenciasGet();

  const hoy = useMemo(() => new Date(), []);

  if (!sesion) return null;

  const todas = consulta.data ?? [];
  const porTipo = tipo === null ? todas : todas.filter((i) => i.tipo === tipo);
  const filas = porTipo.filter((i) => enPestana(i, pestana, hoy));
  const chips = contarPorTipo(todas);

  const activas = todas.filter((i) => requiereAccion(i.estatus)).length;
  const detienen = todas.filter((i) => detieneAhora(i.impacto, i.estatus)).length;
  const vencidas = todas.filter((i) => incidenciaVencida(i.fecha_limite, i.estatus, hoy)).length;
  const enRevision = todas.filter((i) => i.estatus === 'cierre_solicitado').length;

  // El cajón se refresca desde la lista: el contrato no publica
  // `GET /incidencias/{id}`, así que tras una acción se vuelve a leer la
  // bandeja y se recupera de ahí la fila abierta.
  const abierta =
    seleccionada === null ? null : (todas.find((i) => i.id === seleccionada.id) ?? seleccionada);

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
          {activas > 0 && (
            <span className="badge badge--warn">{activas} por atender</span>
          )}
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

      <div className="kpi-grid">
        <TarjetaKpi
          etiqueta="Activas"
          valor={activas}
          ayuda="requieren acción"
          activa={pestana === 'activas'}
          onClick={() => setPestana('activas')}
        />
        <TarjetaKpi
          etiqueta="Detienen el programa"
          valor={detienen}
          ayuda="obras parcial o totalmente detenidas"
          tono="danger"
          activa={pestana === 'detienen'}
          onClick={() => setPestana('detienen')}
        />
        <TarjetaKpi
          etiqueta="Vencidas"
          valor={vencidas}
          ayuda="fuera de fecha límite"
          tono="warn"
          activa={pestana === 'vencidas'}
          onClick={() => setPestana('vencidas')}
        />
        <TarjetaKpi
          etiqueta="Cierres en revisión"
          valor={enRevision}
          ayuda="solicitados por el residente"
          activa={pestana === 'cierre_solicitado'}
          onClick={() => setPestana('cierre_solicitado')}
        />
      </div>

      {chips.length > 1 && (
        <div className="row gap-8 mb-8" style={{ flexWrap: 'wrap', alignItems: 'center' }}>
          <span className="text-mute text-xs">Por tipo</span>
          <button
            type="button"
            className={`chip${tipo === null ? ' is-active' : ''}`}
            aria-pressed={tipo === null}
            onClick={() => setTipo(null)}
          >
            Todos <span className="text-mute">{todas.length}</span>
          </button>
          {chips.map((c) => (
            <button
              key={c.tipo}
              type="button"
              className={`chip${tipo === c.tipo ? ' is-active' : ''}`}
              aria-pressed={tipo === c.tipo}
              onClick={() => setTipo(tipo === c.tipo ? null : c.tipo)}
            >
              {c.etiqueta} <span className="text-mute">{c.cantidad}</span>
            </button>
          ))}
        </div>
      )}

      <div className="filterbar">
        <div className="tabs">
          {PESTANAS.map((p) => (
            <button
              key={p.clave}
              type="button"
              className={`tabs__tab ${pestana === p.clave ? 'is-active' : ''}`}
              onClick={() => setPestana(p.clave)}
            >
              {p.etiqueta}
            </button>
          ))}
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table" style={{ minWidth: 'max-content' }}>
            <thead>
              <tr>
                <th style={{ minWidth: 90 }}>Folio</th>
                <th style={{ minWidth: 260 }}>Incidencia</th>
                <th style={{ minWidth: 90 }}>Lote</th>
                <th style={{ minWidth: 110 }}>Frente</th>
                <th style={{ minWidth: 140 }}>Tipo</th>
                <th style={{ minWidth: 100 }}>Impacto</th>
                <th style={{ minWidth: 100 }}>Programada</th>
                <th style={{ minWidth: 80 }}>Días</th>
                <th style={{ minWidth: 130 }}>Estatus</th>
                <th className="cell-actions">Detalle</th>
              </tr>
            </thead>
            <tbody>
              {consulta.isLoading ? (
                <tr>
                  <td colSpan={10}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : filas.length === 0 ? (
                <tr>
                  <td colSpan={10}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      No hay incidencias en este filtro.
                    </div>
                  </td>
                </tr>
              ) : (
                filas.map((incidencia) => {
                  const dias = diasDeAtraso(incidencia.fecha_limite, hoy);
                  return (
                    <tr key={incidencia.id}>
                      <td className="is-key" title={incidencia.id}>
                        {incidencia.id.slice(0, 8)}
                      </td>
                      <td>
                        {incidencia.titulo}
                        {incidencia.bloquea_claves && incidencia.bloquea_claves.length > 0 && (
                          <div className="text-xs text-mute">
                            🔒 bloquea {incidencia.bloquea_claves.join(', ')}
                          </div>
                        )}
                      </td>
                      <td className="mono text-xs">{incidencia.obra_clave ?? '—'}</td>
                      <td className="text-xs">{incidencia.nivel_clave ?? '—'}</td>
                      <td className="text-mute">{etiquetaTipo(incidencia.tipo)}</td>
                      <td>
                        <span className={`badge badge--${tonoImpacto(incidencia.impacto)}`}>
                          {etiquetaImpacto(incidencia.impacto)}
                        </span>
                      </td>
                      <td className="text-xs">{fmtFecha(incidencia.fecha_limite)}</td>
                      <td
                        className="text-xs"
                        style={
                          dias !== null && dias > 0
                            ? { color: 'var(--c-danger)', fontWeight: 600 }
                            : undefined
                        }
                      >
                        {dias === null || dias <= 0 ? (
                          <span className="text-mute">{etiquetaDiasDeAtraso(dias)}</span>
                        ) : (
                          etiquetaDiasDeAtraso(dias)
                        )}
                      </td>
                      <td>
                        <span className={`badge badge--${tonoEstatusIncidencia(incidencia.estatus)}`}>
                          {etiquetaEstatus(incidencia.estatus)}
                        </span>
                      </td>
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
                  );
                })
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

function TarjetaKpi({
  etiqueta,
  valor,
  ayuda,
  tono,
  activa,
  onClick,
}: {
  readonly etiqueta: string;
  readonly valor: number;
  readonly ayuda: string;
  readonly tono?: 'danger' | 'warn';
  readonly activa: boolean;
  readonly onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`kpi${valor > 0 && tono ? ' kpi--alert' : ''}`}
      aria-pressed={activa}
      style={{
        textAlign: 'left',
        cursor: 'pointer',
        outline: activa ? '2px solid var(--c-accent)' : undefined,
        outlineOffset: activa ? '-1px' : undefined,
      }}
      onClick={onClick}
    >
      <div className="kpi__label">{etiqueta}</div>
      <div
        className="kpi__value"
        style={{ color: valor > 0 && tono === 'danger' ? 'var(--c-danger)' : undefined }}
      >
        {valor}
      </div>
      <div className="kpi__sub">{ayuda}</div>
    </button>
  );
}
