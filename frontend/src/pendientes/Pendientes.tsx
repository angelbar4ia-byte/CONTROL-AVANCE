/**
 * Pendientes por autorizar — bandeja global (§10.3).
 *
 * A diferencia de la bandeja por lote (`cargas/PanelCarga.tsx`, solo
 * lectura), esta pantalla junta los pendientes de **cualquier carga** y
 * los deja aprobar/rechazar aquí mismo. Hasta ahora el contrato no
 * publicaba la ruta que los cierra; el hint en `PanelCarga.tsx` lo decía
 * explícito.
 *
 * Rechazar un `cpu_nuevo` de concepto también da de baja ESE concepto: el
 * cargador ya lo dio de alta (§10.3, "no se omite"), pero un humano decidió
 * que la clave no era confiable tal cual llegó. Queda inactivo y editable
 * desde Catálogos, no borrado.
 */

import { useEffect, useRef, useState } from 'react';

import {
  useAprobarPendientesEnLoteApiV1PendientesAprobarLotePost,
  useBandejaGlobalApiV1PendientesGet,
  useResolverPendienteApiV1PendientesPendienteIdResolverPost,
} from '@/api/generado/cargas/cargas';
import type { PendienteBandejaRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { etiquetaTipoPendiente } from '@/cargas/reglas';

export default function Pendientes() {
  const [soloAbiertos, setSoloAbiertos] = useState(true);
  const [rechazando, setRechazando] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [marcados, setMarcados] = useState<ReadonlySet<string>>(new Set());
  const [confirmando, setConfirmando] = useState<'marcados' | 'no_criticos' | null>(null);

  const bandejaQ = useBandejaGlobalApiV1PendientesGet<PendienteBandejaRespuesta[], ErrorApi>({
    solo_abiertos: soloAbiertos,
  });
  const resolver = useResolverPendienteApiV1PendientesPendienteIdResolverPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setRechazando(null);
        void bandejaQ.refetch();
      },
    },
  });

  const lote = useAprobarPendientesEnLoteApiV1PendientesAprobarLotePost<ErrorApi>({
    mutation: {
      onSuccess: (r) => {
        setConfirmando(null);
        setMarcados(new Set());
        setAviso(
          r.omitidos > 0
            ? `${r.aprobados} aprobados; ${r.omitidos} ya estaban resueltos.`
            : `${r.aprobados} ${r.aprobados === 1 ? 'pendiente aprobado' : 'pendientes aprobados'}.`,
        );
        void bandejaQ.refetch();
      },
    },
  });

  const pendientes = bandejaQ.data ?? [];
  // Solo se marca lo que sigue abierto: lo resuelto no se vuelve a resolver (§10.3).
  const abiertos = pendientes.filter((p) => !p.resuelto);
  const marcadosVisibles = abiertos.filter((p) => marcados.has(p.id));
  const criticosMarcados = marcadosVisibles.filter((p) => p.critico).length;
  const noCriticosAbiertos = abiertos.filter((p) => !p.critico).length;
  const todosMarcados = abiertos.length > 0 && marcadosVisibles.length === abiertos.length;
  const casillaTodos = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (casillaTodos.current) {
      casillaTodos.current.indeterminate = marcadosVisibles.length > 0 && !todosMarcados;
    }
  });

  function marcar(id: string, valor: boolean) {
    setConfirmando(null);
    setMarcados((actual) => {
      const siguiente = new Set(actual);
      if (valor) siguiente.add(id);
      else siguiente.delete(id);
      return siguiente;
    });
  }

  function marcarTodos(valor: boolean) {
    setConfirmando(null);
    setMarcados(valor ? new Set(abiertos.map((p) => p.id)) : new Set());
  }

  function aprobarLote() {
    setAviso(null);
    if (confirmando === 'marcados') {
      lote.mutate({ data: { ids: marcadosVisibles.map((p) => p.id) } });
    } else if (confirmando === 'no_criticos') {
      lote.mutate({ data: { solo_no_criticos: true } });
    }
  }

  function aprobar(id: string) {
    setAviso(null);
    resolver.mutate(
      { pendienteId: id, data: { aprobado: true } },
      { onSuccess: () => setAviso('Pendiente aprobado.') },
    );
  }

  function rechazar(id: string) {
    setAviso(null);
    resolver.mutate(
      { pendienteId: id, data: { aprobado: false } },
      { onSuccess: () => setAviso('Pendiente rechazado.') },
    );
  }

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Configuración</div>
          <h1 className="page__title">Pendientes por autorizar</h1>
          <div className="page__subtitle">
            Lo que un cargador propuso y todavía espera confirmación humana
            (§10.3), de cualquier carga.
          </div>
        </div>
      </div>

      {aviso !== null && (
        <div className="mb-8" role="status">
          <span className="badge badge--ok">{aviso}</span>
        </div>
      )}
      {bandejaQ.error && (
        <div className="mb-8">
          <ErrorBanner mensaje={bandejaQ.error.message} />
        </div>
      )}
      {resolver.error && (
        <div className="mb-8">
          <ErrorBanner mensaje={resolver.error.message} />
        </div>
      )}
      {lote.error && (
        <div className="mb-8">
          <ErrorBanner mensaje={lote.error.message} />
        </div>
      )}

      <div className="filterbar">
        <label className="row gap-4" style={{ alignItems: 'center' }}>
          <input
            type="checkbox"
            checked={soloAbiertos}
            onChange={(e) => setSoloAbiertos(e.target.checked)}
          />
          <span className="text-sm text-mute">Solo lo que falta confirmar</span>
        </label>
        <div className="row gap-8" style={{ marginLeft: 'auto', alignItems: 'center' }}>
          {confirmando === null ? (
            <>
              <button
                type="button"
                className="btn btn--sm btn--primary"
                disabled={marcadosVisibles.length === 0 || lote.isPending}
                onClick={() => setConfirmando('marcados')}
              >
                Aprobar seleccionados ({marcadosVisibles.length})
              </button>
              <button
                type="button"
                className="btn btn--sm"
                disabled={noCriticosAbiertos === 0 || lote.isPending}
                onClick={() => setConfirmando('no_criticos')}
              >
                Aprobar no críticos ({noCriticosAbiertos})
              </button>
            </>
          ) : (
            <div className="row gap-8" role="alertdialog" aria-label="Confirmar aprobación en lote" style={{ alignItems: 'center' }}>
              <span className="text-sm">
                {confirmando === 'marcados'
                  ? `¿Aprobar ${marcadosVisibles.length} ${marcadosVisibles.length === 1 ? 'pendiente' : 'pendientes'}?${
                      criticosMarcados > 0
                        ? ` ${criticosMarcados} ${criticosMarcados === 1 ? 'es crítico' : 'son críticos'}.`
                        : ''
                    }`
                  : `¿Aprobar los ${noCriticosAbiertos} pendientes no críticos? Los críticos se quedan abiertos.`}
              </span>
              <button
                type="button"
                className="btn btn--sm btn--primary"
                disabled={lote.isPending}
                onClick={aprobarLote}
              >
                {lote.isPending ? 'Aprobando…' : 'Sí, aprobar'}
              </button>
              <button
                type="button"
                className="btn btn--sm"
                disabled={lote.isPending}
                onClick={() => setConfirmando(null)}
              >
                Cancelar
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: 32 }}>
                  <input
                    ref={casillaTodos}
                    type="checkbox"
                    aria-label="Seleccionar todos los pendientes abiertos"
                    checked={todosMarcados}
                    disabled={abiertos.length === 0}
                    onChange={(e) => marcarTodos(e.target.checked)}
                  />
                </th>
                <th>Tipo</th>
                <th>Entidad</th>
                <th>Valor del archivo</th>
                <th>Propuesta del sistema</th>
                <th>Crítico</th>
                <th>Estado</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {bandejaQ.isLoading ? (
                <tr>
                  <td colSpan={8}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : pendientes.length === 0 ? (
                <tr>
                  <td colSpan={8}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Nada esperando confirmación.
                    </div>
                  </td>
                </tr>
              ) : (
                pendientes.map((pendiente) => (
                  <tr key={pendiente.id}>
                    <td>
                      {!pendiente.resuelto && (
                        <input
                          type="checkbox"
                          aria-label={`Seleccionar ${pendiente.valor_origen ?? pendiente.id}`}
                          checked={marcados.has(pendiente.id)}
                          onChange={(e) => marcar(pendiente.id, e.target.checked)}
                        />
                      )}
                    </td>
                    <td>{etiquetaTipoPendiente(pendiente.tipo)}</td>
                    <td className="text-mute text-sm">{pendiente.entidad ?? '—'}</td>
                    <td className="mono">{pendiente.valor_origen ?? '—'}</td>
                    <td className="mono text-xs">{JSON.stringify(pendiente.propuesta)}</td>
                    <td>
                      {pendiente.critico ? (
                        <span className="badge badge--danger">Sí</span>
                      ) : (
                        <span className="text-mute">No</span>
                      )}
                    </td>
                    <td>
                      {pendiente.resuelto ? (
                        <span
                          className={`badge badge--${
                            pendiente.resolucion?.accion === 'rechazado' ? 'danger' : 'ok'
                          }`}
                        >
                          {pendiente.resolucion?.accion === 'rechazado'
                            ? 'Rechazado'
                            : 'Aprobado'}
                        </span>
                      ) : (
                        <span className="text-mute">Abierto</span>
                      )}
                    </td>
                    <td className="cell-actions">
                      {!pendiente.resuelto &&
                        (rechazando === pendiente.id ? (
                          <div className="row gap-8">
                            <button
                              type="button"
                              className="btn btn--sm btn--danger"
                              disabled={resolver.isPending}
                              onClick={() => rechazar(pendiente.id)}
                            >
                              {resolver.isPending ? 'Rechazando…' : 'Sí, rechazar'}
                            </button>
                            <button
                              type="button"
                              className="btn btn--sm"
                              onClick={() => setRechazando(null)}
                            >
                              Cancelar
                            </button>
                          </div>
                        ) : (
                          <div className="row gap-8">
                            <button
                              type="button"
                              className="btn btn--sm btn--primary"
                              disabled={resolver.isPending}
                              onClick={() => aprobar(pendiente.id)}
                            >
                              Aprobar
                            </button>
                            <button
                              type="button"
                              className="btn btn--sm"
                              disabled={resolver.isPending}
                              onClick={() => setRechazando(pendiente.id)}
                            >
                              Rechazar
                            </button>
                          </div>
                        ))}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
