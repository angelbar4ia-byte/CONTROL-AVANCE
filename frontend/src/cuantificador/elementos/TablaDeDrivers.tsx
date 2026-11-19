/**
 * Los drivers del Paramétrico (Ola 4B): parámetros que comparten los elementos y las plantillas, con tres niveles: el valor global y
 * su modo (fijo o ajustable), el ajuste de ESTA obra (solo en los ajustables) y el valor vigente que usan los cálculos.
 *
 * Costos y Control de obra PROPONEN (Q3) y solo Control de obra AUTORIZA (F3): lo que propone Control de obra se aplica; lo de Costos queda
 * «pendiente» y no cambia nada hasta que Control de obra lo autorice (queda quién y cuándo). El escarpio y la corona siguen fijos (F4):
 * no se cambian. Los demás roles ven la tabla en solo lectura. Cambiar un driver no recalcula nada guardado
 * (Q1): los trazos que ya traen su altura la conservan; el driver da la altura de lo que nace sin ella. El servidor decide el valor
 * vigente y valida; aquí solo se manda lo tecleado y se pinta lo que responde.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getDriversDeObraApiV1ObrasObraIdDriversGetQueryKey,
  useDriversDeObraApiV1ObrasObraIdDriversGet,
  useFijarDriverDeObraApiV1ObrasObraIdDriversClavePut,
  getPropuestasDeDriversApiV1DriversPropuestasGetQueryKey,
  useAutorizarPropuestaDeDriverApiV1DriversPropuestasPropuestaIdAutorizarPost,
  useFijarDriverGlobalApiV1DriversClavePut,
  usePropuestasDeDriversApiV1DriversPropuestasGet,
  useQuitarDriverDeObraApiV1ObrasObraIdDriversClaveDelete,
  useRechazarPropuestaDeDriverApiV1DriversPropuestasPropuestaIdRechazarPost,
} from '@/api/generado/parametrico/parametrico';
import type { DriverRespuesta, PropuestaDeDriver } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';

interface Props {
  readonly obraId: string;
  readonly obraClave?: string | null;
  readonly puedeEditar: boolean;
  /** F3: solo Control de obra autoriza (el servidor lo vuelve a exigir). */
  readonly puedeAutorizar?: boolean;
}

const ESTADO_DE_PROPUESTA: Record<string, string> = { pendiente: 'pendiente', autorizada: 'autorizada', rechazada: 'rechazada' };

function resumenDeLaPropuesta(p: PropuestaDeDriver): string {
  const partes: string[] = [];
  if (p.accion === 'quitar') partes.push('quitar el ajuste de la obra');
  if (p.valor != null) partes.push(`valor ${p.valor}${p.valor_anterior != null ? ` (antes ${p.valor_anterior})` : ''}`);
  if (p.modo != null) partes.push(`modo ${p.modo}${p.modo_anterior != null ? ` (antes ${p.modo_anterior})` : ''}`);
  return partes.join(' · ');
}

function fechaCorta(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short' });
}

const TIPO_DE_CONSUMIDOR: Record<string, string> = { elemento: 'elemento', artefacto: 'artefacto', plano: 'plano' };
const ORIGEN: Record<string, string> = { obra: 'obra', global: 'global', inicial: 'de partida' };

/** Un número que se teclea: guarda el texto y solo manda el valor al salir del campo (o con Enter) si cambió. */
function CampoDeDriver({
  etiqueta,
  valor,
  vacioPermitido,
  deshabilitado,
  marcador,
  onConfirmar,
}: {
  readonly etiqueta: string;
  readonly valor: string;
  readonly vacioPermitido?: boolean;
  readonly deshabilitado: boolean;
  readonly marcador?: string;
  readonly onConfirmar: (texto: string) => void;
}) {
  const [texto, setTexto] = useState<string | null>(null);
  const visto = texto ?? valor;
  function confirmar() {
    const limpio = (texto ?? valor).trim().replace(',', '.');
    setTexto(null);
    if (limpio === valor) return;
    if (limpio === '' && !vacioPermitido) return;
    onConfirmar(limpio);
  }
  return (
    <input
      className="input mct__driver-campo"
      aria-label={etiqueta}
      inputMode="decimal"
      disabled={deshabilitado}
      placeholder={marcador}
      value={visto}
      onChange={(e) => {
        if (/^[0-9]*[.,]?[0-9]*$/.test(e.target.value)) setTexto(e.target.value);
      }}
      onBlur={confirmar}
      onKeyDown={(e) => {
        if (e.key === 'Enter') e.currentTarget.blur();
        if (e.key === 'Escape') setTexto(null);
      }}
    />
  );
}

export function TablaDeDrivers({ obraId, obraClave, puedeEditar, puedeAutorizar = false }: Props) {
  const consulta = useDriversDeObraApiV1ObrasObraIdDriversGet(obraId, { query: { enabled: obraId !== '' } });
  const fijarGlobal = useFijarDriverGlobalApiV1DriversClavePut<ErrorApi>();
  const fijarDeObra = useFijarDriverDeObraApiV1ObrasObraIdDriversClavePut<ErrorApi>();
  const quitarDeObra = useQuitarDriverDeObraApiV1ObrasObraIdDriversClaveDelete<ErrorApi>();
  const autorizar = useAutorizarPropuestaDeDriverApiV1DriversPropuestasPropuestaIdAutorizarPost<ErrorApi>();
  const rechazar = useRechazarPropuestaDeDriverApiV1DriversPropuestasPropuestaIdRechazarPost<ErrorApi>();
  const bitacora = usePropuestasDeDriversApiV1DriversPropuestasGet({ obra_id: obraId }, { query: { enabled: obraId !== '' } });
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const recargar = async () => {
    await queryClient.invalidateQueries({ queryKey: getDriversDeObraApiV1ObrasObraIdDriversGetQueryKey(obraId) });
    await queryClient.invalidateQueries({ queryKey: getPropuestasDeDriversApiV1DriversPropuestasGetQueryKey({ obra_id: obraId }) });
  };
  async function intentar(accion: () => Promise<unknown>) {
    setError(null);
    setAviso(null);
    try {
      const r = (await accion()) as DriverRespuesta | undefined;
      // F3: lo de Costos queda pendiente (el servidor contesta 202 y el driver no cambió); lo de Control de obra ya está aplicado.
      if (r?.propuesta?.estado === 'pendiente') setAviso('Cambio propuesto: queda pendiente hasta que Control de obra lo autorice. El valor vigente no cambió.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar el driver.');
    }
    await recargar();
  }

  const drivers = consulta.data ?? [];
  return (
    <section className="mct__bloque" aria-label="Drivers" data-drivers>
      <h3>Drivers</h3>
      <p className="text-mute text-xs">
        {puedeEditar
          ? 'Costos y Control de obra proponen el valor global y si cada driver es fijo o ajustable; solo Control de obra autoriza (lo suyo se aplica al instante). En los ajustables, esta obra puede tener su propio valor.'
          : 'Solo Costos y Control de obra editan los drivers: aquí los ves en solo lectura.'}{' '}
        El valor vigente es el de la obra si el driver es ajustable y la obra lo cambió; si no, el global. Cambiar un driver no recalcula lo ya
        guardado: un trazo que ya trae su altura la conserva, y el driver da la altura de lo que nace sin ella. Las medidas de castillos y
        cadenas no son drivers: son del elemento.
      </p>
      {error && (
        <p className="mct__error" role="alert">
          {error}
        </p>
      )}
      {aviso && (
        <p className="text-xs mct__aviso" role="status" data-aviso-propuesta>
          {aviso}
        </p>
      )}
      {consulta.isLoading ? (
        <p className="text-mute text-sm">Cargando los drivers…</p>
      ) : (
        <div className="mct__tabla-caja">
          <table className="mct__tabla" aria-label="Drivers del Paramétrico">
            <thead>
              <tr>
                <th>Driver</th>
                <th>Unidad</th>
                <th>Global</th>
                <th>Modo</th>
                <th>{obraClave ? `Obra ${obraClave}` : 'Esta obra'}</th>
                <th className="n">Vigente</th>
                <th>Origen</th>
                <th>Lo usan</th>
              </tr>
            </thead>
            <tbody>
              {drivers.map((d: DriverRespuesta) => {
                const ajustable = d.modo === 'ajustable';
                const inmutable = d.inmutable === true;
                const pendientes = d.propuestas_pendientes ?? [];
                return (
                  <tr key={d.clave} data-driver={d.clave}>
                    <td>
                      {d.nombre}
                      {d.por_confirmar && (
                        <>
                          {' '}
                          <span className="badge badge--warn">por confirmar</span>
                        </>
                      )}
                      {inmutable && (
                        <>
                          {' '}
                          <span className="badge badge--outline" data-inmutable>
                            fijo: no se cambia
                          </span>
                        </>
                      )}
                      <div className="text-mute text-xs">{d.nota}</div>
                      {pendientes.length > 0 && (
                        <ul className="text-xs" style={{ listStyle: 'none', margin: 0, padding: 0 }} aria-label={`Cambios pendientes de ${d.nombre}`}>
                          {pendientes.map((p) => (
                            <li key={p.id} data-propuesta={p.id} className="mct__aviso">
                              <span className="badge badge--warn">pendiente</span> {resumenDeLaPropuesta(p)} · propuso {p.propuso_nombre ?? p.propuso_rol} el {fechaCorta(p.propuesto_en)}
                              {puedeAutorizar && (
                                <>
                                  {' '}
                                  <button
                                    type="button"
                                    className="btn btn--sm"
                                    aria-label={`Autorizar el cambio de ${d.nombre}`}
                                    onClick={() => void intentar(() => autorizar.mutateAsync({ propuestaId: p.id }))}
                                  >
                                    Autorizar
                                  </button>{' '}
                                  <button
                                    type="button"
                                    className="btn btn--ghost btn--sm"
                                    aria-label={`Rechazar el cambio de ${d.nombre}`}
                                    onClick={() => void intentar(() => rechazar.mutateAsync({ propuestaId: p.id, data: {} }))}
                                  >
                                    Rechazar
                                  </button>
                                </>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                    <td>{d.unidad}</td>
                    <td>
                      <CampoDeDriver
                        etiqueta={`Valor global de ${d.nombre}`}
                        valor={d.valor_global}
                        deshabilitado={!puedeEditar || inmutable}
                        onConfirmar={(t) => void intentar(() => fijarGlobal.mutateAsync({ clave: d.clave, data: { valor: t } }))}
                      />
                    </td>
                    <td>
                      <select
                        className="input"
                        aria-label={`Modo de ${d.nombre}`}
                        disabled={!puedeEditar || inmutable}
                        value={d.modo}
                        onChange={(e) =>
                          void intentar(() => fijarGlobal.mutateAsync({ clave: d.clave, data: { modo: e.target.value as 'fijo' | 'ajustable' } }))
                        }
                      >
                        <option value="fijo">Fijo</option>
                        <option value="ajustable">Ajustable por obra</option>
                      </select>
                    </td>
                    <td>
                      <CampoDeDriver
                        etiqueta={`Valor de la obra para ${d.nombre}`}
                        valor={d.valor_obra ?? ''}
                        vacioPermitido
                        deshabilitado={!puedeEditar || !ajustable || inmutable}
                        marcador={ajustable ? 'igual al global' : '—'}
                        onConfirmar={(t) =>
                          void intentar(() =>
                            t === ''
                              ? quitarDeObra.mutateAsync({ obraId, clave: d.clave })
                              : fijarDeObra.mutateAsync({ obraId, clave: d.clave, data: { valor: t } }),
                          )
                        }
                      />
                      {d.ajuste_ignorado && <div className="text-xs mct__aviso">El driver es fijo: el ajuste de la obra no vale.</div>}
                    </td>
                    <td className="n" data-vigente>
                      {d.valor_vigente}
                    </td>
                    <td>
                      <span className={d.origen === 'obra' ? 'badge badge--info' : 'badge badge--ok'}>{ORIGEN[d.origen] ?? d.origen}</span>
                    </td>
                    <td data-lo-usan={d.clave}>
                      {(d.lo_usan ?? []).length === 0 ? (
                        <span className="text-mute text-xs">{d.sin_consumidor ?? 'Ningún cálculo lo lee todavía.'}</span>
                      ) : (
                        <ul style={{ listStyle: 'none', margin: 0, padding: 0 }} aria-label={`Lo usan: ${d.nombre}`}>
                          {(d.lo_usan ?? []).map((c) => (
                            <li key={c.id} className="text-xs" data-consumidor={c.id}>
                              <span className="badge badge--outline">{TIPO_DE_CONSUMIDOR[c.tipo] ?? c.tipo}</span> {c.nombre}
                              {c.lectura === 'constante' && <span className="text-mute"> (fijo: lo lee como constante)</span>}
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <details className="mct__bloque" data-bitacora-de-drivers>
        <summary>Bitácora de cambios de drivers (quién y cuándo)</summary>
        {(bitacora.data ?? []).length === 0 ? (
          <p className="text-mute text-xs">Aún no hay cambios propuestos.</p>
        ) : (
          <table className="mct__tabla" aria-label="Bitácora de cambios de drivers">
            <thead>
              <tr>
                <th>Driver</th>
                <th>Cambio</th>
                <th>Estado</th>
                <th>Propuso</th>
                <th>Decidió</th>
              </tr>
            </thead>
            <tbody>
              {(bitacora.data ?? []).map((p) => (
                <tr key={p.id} data-bitacora-propuesta={p.id}>
                  <td className="mono">{p.clave}</td>
                  <td>
                    {p.alcance === 'obra' ? 'obra · ' : ''}
                    {resumenDeLaPropuesta(p)}
                  </td>
                  <td>{ESTADO_DE_PROPUESTA[p.estado] ?? p.estado}</td>
                  <td>
                    {p.propuso_nombre ?? p.propuso_rol} · {fechaCorta(p.propuesto_en)}
                  </td>
                  <td>{p.decidio_rol ? `${p.decidio_nombre ?? p.decidio_rol} · ${fechaCorta(p.decidido_en)}${p.motivo ? ` · ${p.motivo}` : ''}` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </details>
    </section>
  );
}
