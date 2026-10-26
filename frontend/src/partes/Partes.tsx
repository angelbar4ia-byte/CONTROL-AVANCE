/**
 * Las partes de una obra — enviar, autorizar y programar por partes (migración 0075;
 * cerebro D-571 a D-579).
 *
 * Una **parte** es una etapa de construcción o un concepto independiente (losas, pisos). Cada
 * una recorre su camino a su paso: puede estar programada mientras otra sigue cuantificándose.
 * Se manda a presupuesto, se autoriza (la realiza Costos o Control, Control la valida), se envía
 * a programar y se asigna; **«total o por partes»**: se eligen las partes, o se pide el total.
 * Volver a un paso anterior es libre hasta asignar; una parte asignada ya no se devuelve.
 *
 * Todos los roles ven; los pasos los da quien el servidor autoriza (`reglas.ts` los refleja).
 */

import { useRef, useState } from 'react';

import { claveDeIdempotencia, type ErrorApi } from '@/api/cliente';
import {
  getAlertasDePartesApiV1ObrasObraIdPartesAlertasGetQueryKey,
  getArranqueDeLaObraApiV1ObrasObraIdArranqueGetQueryKey,
  getBitacoraDePartesApiV1ObrasObraIdPartesBitacoraGetQueryKey,
  getPartesDeLaObraApiV1ObrasObraIdPartesGetQueryKey,
  useBitacoraDePartesApiV1ObrasObraIdPartesBitacoraGet,
  useCargaDePartesApiV1ObrasObraIdPartesCargaGet,
  useCambiarEstadoDePartesApiV1ObrasObraIdPartesTransicionPost,
  usePartesDeLaObraApiV1ObrasObraIdPartesGet,
} from '@/api/generado/partes/partes';
import type { ParteRespuesta } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { colorAvance, fmtFecha, fmtNum, fmtPct } from '@/lib/formato';
import { Modal } from '@/lib/Modal';
import { SelectorObra } from '@/lib/SelectorObra';
import {
  ETIQUETA_ACCION,
  accionSiguiente,
  estadosAnteriores,
  etiquetaDeEstado,
  etiquetaDeTipoDeParte,
  puedeAccion,
  tonoDeEstado,
  type AccionDeParte,
  type EstadoDeParte,
} from './reglas';
import ArranqueYAlertas from './ArranqueYAlertas';
import Modificaciones from './Modificaciones';

export default function Partes() {
  const { sesion } = useSesion();
  const [obraId, setObraId] = useState('');
  const [elegidas, setElegidas] = useState<ReadonlySet<string>>(new Set());
  const [devolviendo, setDevolviendo] = useState(false);
  const [destino, setDestino] = useState<EstadoDeParte | ''>('');
  const [nota, setNota] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  // Una clave por intención: la misma ruta lleva pasos distintos (enviar, autorizar…), así que
  // no vale una clave por ruta. Se renueva en cada clic; un reintento reusa la suya.
  const clave = useRef(claveDeIdempotencia());

  const consulta = usePartesDeLaObraApiV1ObrasObraIdPartesGet<
    { partes: ParteRespuesta[]; plantas?: number | null },
    ErrorApi
  >(obraId, { query: { enabled: obraId !== '' } });
  const bitacora = useBitacoraDePartesApiV1ObrasObraIdPartesBitacoraGet(obraId, {
    query: { enabled: obraId !== '' },
  });

  const carga = useCargaDePartesApiV1ObrasObraIdPartesCargaGet(obraId, {
    query: { enabled: obraId !== '' },
  });
  const cargaDe = new Map((carga.data?.partes ?? []).map((c) => [c.clave, c]));

  const mutacion = useCambiarEstadoDePartesApiV1ObrasObraIdPartesTransicionPost<ErrorApi>({
    mutation: {
      onSuccess: (pasos) => {
        setError(null);
        setElegidas(new Set());
        setDevolviendo(false);
        setNota('');
        setAviso(`${pasos.length} ${pasos.length === 1 ? 'parte cambió' : 'partes cambiaron'} de paso.`);
        void queryClient.invalidateQueries({
          queryKey: getPartesDeLaObraApiV1ObrasObraIdPartesGetQueryKey(obraId),
        });
        void queryClient.invalidateQueries({
          queryKey: getBitacoraDePartesApiV1ObrasObraIdPartesBitacoraGetQueryKey(obraId),
        });
        // Autorizar o devolver cambia lo que alerta y lo que la junta ve.
        void queryClient.invalidateQueries({
          queryKey: getAlertasDePartesApiV1ObrasObraIdPartesAlertasGetQueryKey(obraId),
        });
        void queryClient.invalidateQueries({
          queryKey: getArranqueDeLaObraApiV1ObrasObraIdArranqueGetQueryKey(obraId),
        });
      },
      onError: (e) => setError(e.message),
    },
    request: { headers: () => ({ 'Idempotency-Key': clave.current }) },
  });

  if (!sesion) return null;
  const rol = sesion.rol;
  const partes = consulta.data?.partes ?? [];
  const marcadas = partes.filter((p) => elegidas.has(p.clave));

  const dar = (accion: AccionDeParte, extra: { todas?: boolean; a?: EstadoDeParte } = {}) => {
    clave.current = claveDeIdempotencia();
    setAviso(null);
    mutacion.mutate({
      obraId,
      data: {
        accion,
        claves: extra.todas ? [] : marcadas.map((p) => p.clave),
        todas: extra.todas ?? false,
        a: extra.a ?? null,
        nota: nota.trim() || null,
      },
    });
  };

  // Una sola acción a la vez: la de las partes marcadas, si todas están en el mismo paso.
  const estadosMarcados = new Set(marcadas.map((p) => p.estado));
  const comun = estadosMarcados.size === 1 ? [...estadosMarcados][0]! : null;
  const accionComun = comun ? accionSiguiente(comun) : null;
  const sePuedeDevolver = comun !== null && estadosAnteriores(comun).length > 0 && puedeAccion(rol, 'devolver');

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Obra</div>
          <h1 className="page__title">Partes</h1>
          <div className="page__subtitle">
            Cada <strong>parte</strong> —una etapa o un concepto independiente— avanza a su paso:
            se manda a presupuesto, se autoriza, se envía a programar y se asigna. Se puede{' '}
            <strong>total o por partes</strong>, y volver atrás es libre hasta asignar.
          </div>
        </div>
      </div>

      {error && <ErrorBanner mensaje={error} />}
      {(carga.data?.incompletas ?? 0) > 0 && (
        <div className="text-sm mb-8" role="status">
          La ingeniería de {carga.data!.incompletas}{' '}
          {carga.data!.incompletas === 1 ? 'parte está incompleta' : 'partes está incompleta'}: avisa, no
          impide mandarlas a programar.
        </div>
      )}
      {consulta.error && <ErrorBanner mensaje={consulta.error.message} />}
      {aviso && (
        <div className="text-sm mb-8" role="status">
          {aviso}
        </div>
      )}

      <div className="filterbar">
        <div style={{ minWidth: 260 }}>
          <SelectorObra
            id="partes-obra"
            etiqueta="Obra"
            valor={obraId}
            onCambio={(id) => {
              setObraId(id);
              setElegidas(new Set());
              setAviso(null);
            }}
          />
        </div>
        {consulta.data?.plantas != null && (
          <div className="text-sm" style={{ alignSelf: 'flex-end' }}>
            <span className="badge badge--outline">
              {consulta.data.plantas} {consulta.data.plantas === 1 ? 'planta' : 'plantas'}
            </span>
          </div>
        )}
      </div>

      {obraId === '' ? (
        <div className="empty">
          <div className="empty-title">Elige una obra</div>
          <div className="empty-sub">Las partes son las etapas y los conceptos independientes de una obra.</div>
        </div>
      ) : consulta.isLoading ? (
        <div className="text-mute text-sm" style={{ padding: 24 }}>
          Cargando…
        </div>
      ) : partes.length === 0 ? (
        <div className="empty">
          <div className="empty-title">Sin partes</div>
          <div className="empty-sub">La obra todavía no tiene actividades: falta generarla.</div>
        </div>
      ) : (
        <>
          <ArranqueYAlertas obraId={obraId} rol={rol} />
          <div className="row gap-8 mb-8" style={{ flexWrap: 'wrap', alignItems: 'flex-end' }} role="toolbar" aria-label="Pasos">
            <div className="field" style={{ minWidth: 220 }}>
              <label className="field__label" htmlFor="partes-anotacion">
                Anotación (al validar o devolver)
              </label>
              <input
                id="partes-anotacion"
                className="input"
                value={nota}
                onChange={(e) => setNota(e.target.value)}
              />
            </div>
            {accionComun && puedeAccion(rol, accionComun) && (
              <button
                type="button"
                className="btn btn--primary btn--sm"
                disabled={mutacion.isPending}
                onClick={() => dar(accionComun)}
              >
                {ETIQUETA_ACCION[accionComun]} ({marcadas.length})
              </button>
            )}
            {sePuedeDevolver && (
              <button type="button" className="btn btn--sm" onClick={() => setDevolviendo(true)}>
                Devolver ({marcadas.length})
              </button>
            )}
            {(['enviar_a_presupuesto', 'autorizar', 'validar', 'enviar_a_programa', 'programar', 'asignar'] as const)
              .filter((a) => puedeAccion(rol, a) && partes.some((p) => accionSiguiente(p.estado) === a))
              .map((a) => (
                <button
                  key={a}
                  type="button"
                  className="btn btn--sm"
                  disabled={mutacion.isPending}
                  onClick={() => dar(a, { todas: true })}
                >
                  {ETIQUETA_ACCION[a]}: todas las que toquen
                </button>
              ))}
          </div>

          <div className="table-wrap">
            <div className="table-scroll">
              <table className="table" style={{ minWidth: 'max-content' }}>
                <thead>
                  <tr>
                    <th style={{ width: 32 }} />
                    <th style={{ minWidth: 260 }}>Parte</th>
                    <th style={{ minWidth: 160 }}>Tipo</th>
                    <th style={{ minWidth: 150 }}>Avance</th>
                    <th className="is-num">Importe</th>
                    <th style={{ minWidth: 150 }}>Ingeniería cargada</th>
                    <th style={{ minWidth: 160 }}>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {partes.map((p) => {
                    const pct = Number(p.avance_pct);
                    return (
                      <tr key={p.clave}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`Elegir ${p.nombre}`}
                            checked={elegidas.has(p.clave)}
                            onChange={(e) => {
                              const siguiente = new Set(elegidas);
                              if (e.target.checked) siguiente.add(p.clave);
                              else siguiente.delete(p.clave);
                              setElegidas(siguiente);
                            }}
                          />
                        </td>
                        <td>{p.nombre}</td>
                        <td className="text-xs">{etiquetaDeTipoDeParte(p.tipo)}</td>
                        <td>
                          <div className="row gap-4" style={{ alignItems: 'center' }}>
                            <div
                              className={`bar ${colorAvance(pct) !== 'accent' ? `bar--${colorAvance(pct)}` : ''}`}
                              style={{ flex: 1, minWidth: 60 }}
                            >
                              <div className="bar__fill" style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
                            </div>
                            <span className="text-xs tnum">{fmtPct(p.avance_pct)}</span>
                          </div>
                        </td>
                        <td className="is-num tnum">{fmtNum(p.importe)}</td>
                        <td className="text-xs">
                          {cargaDe.get(p.clave) ? (
                            <span
                              className={`badge badge--${cargaDe.get(p.clave)!.estado === 'completo' ? 'ok' : 'warn'}`}
                              title={`Faltan ${fmtNum(cargaDe.get(p.clave)!.importe_pendiente)} por cargar`}
                            >
                              {cargaDe.get(p.clave)!.estado === 'completo'
                                ? 'Completa'
                                : `Incompleta · ${fmtPct(cargaDe.get(p.clave)!.porcentaje_cargado)}`}
                            </span>
                          ) : (
                            <span className="text-mute">—</span>
                          )}
                        </td>
                        <td>
                          <span className={`badge badge--${tonoDeEstado(p.estado)}`}>{etiquetaDeEstado(p.estado)}</span>
                          {p.programa_por_revisar && (
                            <span className="badge badge--warn" style={{ marginLeft: 4 }}>
                              Programa por revisar
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <Modificaciones
            obraId={obraId}
            rol={rol}
            etapas={partes.filter((p) => p.tipo === 'etapa' && p.id).map((p) => ({ id: p.id as string, nombre: p.nombre }))}
          />

          <section aria-label="Bitácora de las partes" className="mt-16">
            <h2 className="text-sm" style={{ margin: '16px 0 8px' }}>Bitácora</h2>
            {(bitacora.data ?? []).length === 0 ? (
              <div className="text-mute text-sm">Todavía no se ha movido ninguna parte.</div>
            ) : (
              <ul className="text-xs" style={{ margin: 0, padding: 0, listStyle: 'none' }}>
                {(bitacora.data ?? []).map((t) => (
                  <li key={t.id}>
                    <strong>{t.usuario_nombre ?? t.rol}</strong> · {ETIQUETA_ACCION[t.accion as AccionDeParte] ?? t.accion}:{' '}
                    {etiquetaDeEstado(t.de)} → {etiquetaDeEstado(t.a)}
                    <span className="text-mute"> · {fmtFecha(t.creada_en)}</span>
                    {t.nota ? <span> — {t.nota}</span> : null}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}

      {devolviendo && comun && (
        <Modal titulo="Devolver las partes a un paso anterior" onCerrar={() => setDevolviendo(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (destino !== '') dar('devolver', { a: destino });
            }}
          >
            <div className="sheet__body col gap-12">
              <p className="text-mute text-sm">
                Replantear lo hecho es libre hasta asignar. Lo que venga después de ese paso se
                revisa de nuevo.
              </p>
              <div className="field">
                <label className="field__label" htmlFor="partes-destino">
                  Volver a
                </label>
                <select
                  id="partes-destino"
                  className="select"
                  value={destino}
                  onChange={(e) => setDestino(e.target.value as EstadoDeParte)}
                >
                  <option value="">Elige un paso…</option>
                  {estadosAnteriores(comun).map((e) => (
                    <option key={e} value={e}>
                      {etiquetaDeEstado(e)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label className="field__label" htmlFor="partes-nota">
                  Nota
                </label>
                <textarea
                  id="partes-nota"
                  className="input"
                  rows={2}
                  value={nota}
                  onChange={(e) => setNota(e.target.value)}
                />
              </div>
            </div>
            <div className="sheet__footer">
              <button type="button" className="btn" onClick={() => setDevolviendo(false)}>
                Cancelar
              </button>
              <button type="submit" className="btn btn--primary" disabled={destino === '' || mutacion.isPending}>
                Devolver
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
