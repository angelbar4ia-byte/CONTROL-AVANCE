/**
 * Detalle de un ensamble: receta, costo, cohorte e instancias (skill
 * `erp-parametrico`, §11.2).
 *
 * Reúne lo que el contrato deja sobre un ensamble:
 *   - `GET /ensambles/{id}/explosion` — costo y composición, con el factor
 *     de una instancia hipotética (C, SI);
 *   - `GET /ensambles/{id}/renglones` — la receta directa, con el **origen**
 *     de cada cantidad (C, SI);
 *   - `GET /ensambles/{id}/cohorte` — los prototipos declarados (C, SI);
 *   - `GET /ensambles/{id}/instancias` — lo ya generado, para regenerarlo;
 *   - `POST /ensambles/{id}/generar` — generar o regenerar (solo C).
 *
 * ## Dos explosiones sobre el mismo documento (skill §4)
 *
 * "De costo" trae todo —da el precio—; "de contratación" agrupa solo el
 * destajo. Aquí no son dos pantallas: cada línea trae **las dos cifras**, el
 * backend las calcula y esta pantalla las muestra lado a lado sin recomponer
 * ninguna. El costo unitario de cada concepto no se repite aquí: el panel mide
 * 480px y con seis columnas el importe —lo que de verdad se lee— quedaba fuera
 * de la vista; el unitario vive en el APU de cada concepto.
 */

import { useState } from 'react';

import {
  useExplotarEnsambleApiV1EnsamblesEnsambleIdExplosionGet,
  useListarCohorteApiV1EnsamblesEnsambleIdCohorteGet,
  useListarInstanciasApiV1EnsamblesEnsambleIdInstanciasGet,
  useListarRenglonesApiV1EnsamblesEnsambleIdRenglonesGet,
} from '@/api/generado/ensambles/ensambles';
import type {
  CohorteItemRespuesta,
  EnsambleRespuesta,
  ExplosionEnsambleRespuesta,
  InstanciaEnsambleRespuesta,
  RenglonEnsambleRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import { fmtMXN, fmtNum } from '@/lib/formato';
import type { Rol } from '@/shell/navegacion';
import { GenerarEnsamble } from './GenerarEnsamble';
import { etiquetaOrigen, factorValido, puedeEscribirEnsambles, tasaPublicada } from './reglas';

interface Props {
  readonly ensamble: EnsambleRespuesta;
  readonly rol: Rol;
  readonly onCerrar: () => void;
}

export function PanelEnsamble({ ensamble, rol, onCerrar }: Props) {
  const [factor, setFactor] = useState('1');
  const [generando, setGenerando] = useState<{ instancia?: InstanciaEnsambleRespuesta } | null>(
    null,
  );

  const factorOk = factorValido(factor);
  const explosionQ = useExplotarEnsambleApiV1EnsamblesEnsambleIdExplosionGet<
    ExplosionEnsambleRespuesta,
    ErrorApi
  >(ensamble.id, { factor }, { query: { enabled: factorOk, retry: false } });
  const renglonesQ = useListarRenglonesApiV1EnsamblesEnsambleIdRenglonesGet<
    RenglonEnsambleRespuesta[],
    ErrorApi
  >(ensamble.id);
  const cohorteQ = useListarCohorteApiV1EnsamblesEnsambleIdCohorteGet<
    CohorteItemRespuesta[],
    ErrorApi
  >(ensamble.id);
  const instanciasQ = useListarInstanciasApiV1EnsamblesEnsambleIdInstanciasGet<
    InstanciaEnsambleRespuesta[],
    ErrorApi
  >(ensamble.id);

  const escribe = puedeEscribirEnsambles(rol);
  const explosion = explosionQ.data;

  return (
    <Sheet titulo={ensamble.clave} subtitulo={ensamble.nombre} onCerrar={onCerrar}>
      {/* El scroll y el flex-columna van en dos niveles: `.sheet__body` hace
          scroll y `.card` tiene `overflow: hidden`, así que como hijos
          directos de un `.col` las tarjetas se comprimen en vez de dejar
          que el panel haga scroll. */}
      <div className="sheet__body">
       <div className="col gap-16">
        {explosionQ.isError && <ErrorBanner mensaje={explosionQ.error.message} />}

        {/* ── Tasa ────────────────────────────────────────────────── */}
        <section className="card">
          <div className="card__header">
            <div>
              <h3 className="card__title">Parámetro</h3>
              <div className="card__sub">
                {ensamble.divisor_nombre
                  ? `Se normaliza contra: ${ensamble.divisor_nombre}.`
                  : 'Sin divisor declarado: todavía no se puede medir una tasa (§5.7).'}
              </div>
            </div>
          </div>
          <div className="card__body">
            {tasaPublicada(ensamble.tasa, ensamble.dispersion) ? (
              <div className="kpi-grid" style={{ marginBottom: 0 }}>
                <div className="kpi">
                  <div className="kpi__label">Tasa</div>
                  <div className="kpi__value">{fmtMXN(ensamble.tasa)}</div>
                  <div className="kpi__sub">por unidad del divisor</div>
                </div>
                <div className="kpi">
                  <div className="kpi__label">Dispersión</div>
                  <div className="kpi__value tnum">{fmtNum(ensamble.dispersion)}%</div>
                  <div className="kpi__sub">Coeficiente de variación de la cohorte</div>
                </div>
              </div>
            ) : (
              <div className="text-mute text-sm">
                Sin tasa publicada. Una tasa nunca se muestra sin su dispersión: un precio
                paramétrico sin ella es un número disfrazado de certeza (§5.7).
              </div>
            )}
          </div>
        </section>

        {/* ── Costo y composición ─────────────────────────────────── */}
        <section className="card">
          <div className="card__header">
            <div>
              <h3 className="card__title">Costo y composición</h3>
              <div className="card__sub">
                Con las dos cifras por línea: costo total y la porción de destajo (skill §4).
              </div>
            </div>
            <div style={{ width: 120 }}>
              <label className="field__label" htmlFor="ens-factor">
                Veces que entra
              </label>
              <input
                id="ens-factor"
                className="input mono"
                type="number"
                min="0"
                step="any"
                value={factor}
                onChange={(e) => setFactor(e.target.value)}
              />
            </div>
          </div>
          <div className="card__body col gap-12">
            {!factorOk ? (
              <div className="text-mute text-sm">Escribe un factor mayor que cero.</div>
            ) : explosionQ.isLoading ? (
              <div className="text-mute text-sm">Calculando…</div>
            ) : explosion ? (
              <>
                <div className="kpi-grid" style={{ marginBottom: 0 }}>
                  <div className="kpi">
                    <div className="kpi__label">Costo total</div>
                    <div className="kpi__value">{fmtMXN(explosion.precio.total)}</div>
                  </div>
                  <div className="kpi">
                    <div className="kpi__label">De ello, destajo</div>
                    <div className="kpi__value">{fmtMXN(explosion.precio.destajo)}</div>
                    <div className="kpi__sub">Lo que se contrata (skill §4)</div>
                  </div>
                </div>
                <TablaExplosion explosion={explosion} />
              </>
            ) : null}
          </div>
        </section>

        {/* ── Receta directa ──────────────────────────────────────── */}
        <section className="card">
          <div className="card__header">
            <div>
              <h3 className="card__title">Receta</h3>
              <div className="card__sub">
                Cantidad por una instancia completa y de dónde salió (skill §2).
              </div>
            </div>
          </div>
          <div className="card__body card__body--flush">
            {renglonesQ.isError && <ErrorBanner mensaje={renglonesQ.error.message} />}
            <div className="table-wrap">
              <div className="table-scroll">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Renglón</th>
                      <th>Cantidad</th>
                      <th>Origen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(renglonesQ.data ?? []).map((renglon) => (
                      <tr key={renglon.id}>
                        <td className="is-key mono">
                          {renglon.concepto_clave ?? renglon.sub_ensamble_clave}
                          {renglon.sub_ensamble_clave != null && (
                            <span className="badge badge--outline" style={{ marginLeft: 8 }}>
                              sub-ensamble
                            </span>
                          )}
                        </td>
                        <td className="is-num">{fmtNum(renglon.cantidad)}</td>
                        <td>{etiquetaOrigen(renglon.origen)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>

        {/* ── Cohorte ─────────────────────────────────────────────── */}
        <section className="card">
          <div className="card__header">
            <div>
              <h3 className="card__title">Cohorte declarada</h3>
              <div className="card__sub">
                Los prototipos sobre los que se mide la tasa; se declaran a mano (§5.7).
              </div>
            </div>
            <span className="badge badge--outline tnum">{cohorteQ.data?.length ?? 0}</span>
          </div>
          <div className="card__body">
            {(cohorteQ.data ?? []).length === 0 ? (
              <div className="text-mute text-sm">Sin cohorte declarada.</div>
            ) : (
              <div className="row gap-8" style={{ flexWrap: 'wrap' }}>
                {(cohorteQ.data ?? []).map((item) => (
                  <span key={item.prototipo_id} className="badge badge--outline mono">
                    {item.prototipo_clave}
                  </span>
                ))}
              </div>
            )}
          </div>
        </section>

        {/* ── Instancias ──────────────────────────────────────────── */}
        <section className="card">
          <div className="card__header">
            <div>
              <h3 className="card__title">Instancias generadas</h3>
              <div className="card__sub">
                Lo que este ensamble ya compuso en el árbol de un prototipo.
              </div>
            </div>
            {escribe && (
              <button type="button" className="btn btn--accent" onClick={() => setGenerando({})}>
                Generar instancia
              </button>
            )}
          </div>
          <div className="card__body card__body--flush">
            {instanciasQ.isError && <ErrorBanner mensaje={instanciasQ.error.message} />}
            {(instanciasQ.data ?? []).length === 0 ? (
              <div className="text-mute text-sm" style={{ padding: '16px 12px' }}>
                Todavía no se genera ninguna instancia.
              </div>
            ) : (
              <div className="table-wrap">
                <div className="table-scroll">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Instancia</th>
                        <th>Prototipo</th>
                        <th>Veces</th>
                        {escribe && <th />}
                      </tr>
                    </thead>
                    <tbody>
                      {(instanciasQ.data ?? []).map((instancia) => (
                        <tr key={instancia.id}>
                          <td className="is-key">{instancia.nombre}</td>
                          <td className="mono text-xs">{instancia.prototipo_clave}</td>
                          <td className="is-num">{fmtNum(instancia.factor)}</td>
                          {escribe && (
                            <td>
                              <button
                                type="button"
                                className="btn btn--sm"
                                aria-label={`Regenerar ${instancia.nombre}`}
                                onClick={() => setGenerando({ instancia })}
                              >
                                Regenerar
                              </button>
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </section>
       </div>
      </div>

      {generando !== null && (
        <GenerarEnsamble
          ensamble={ensamble}
          instancia={generando.instancia}
          onCerrar={() => setGenerando(null)}
          onGenerado={() => void instanciasQ.refetch()}
        />
      )}
    </Sheet>
  );
}

function TablaExplosion({ explosion }: { readonly explosion: ExplosionEnsambleRespuesta }) {
  return (
    <div className="table-wrap">
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Línea</th>
              <th className="is-num">Cantidad</th>
              <th className="is-num">Importe</th>
              <th className="is-num">De ello, destajo</th>
            </tr>
          </thead>
          <tbody>
            {explosion.lineas.map((linea) => (
              <tr key={`${linea.ruta.join('/')}/${linea.referencia}`}>
                <td className="is-key mono" style={{ paddingLeft: 8 + (linea.nivel - 1) * 16 }}>
                  {linea.referencia}
                  {linea.tipo_hijo === 'ensamble' && (
                    <span className="badge badge--outline" style={{ marginLeft: 8 }}>
                      sub-ensamble
                    </span>
                  )}
                </td>
                <td className="is-num">{fmtNum(linea.cantidad)}</td>
                <td className="is-num">{fmtMXN(linea.importe)}</td>
                <td className="is-num">{fmtMXN(linea.importe_destajo)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
