/**
 * Editor de APU: explosión del concepto y su CPU (§7.3, §10.8, §11.2).
 *
 * Es el cajón de drill-down del §12.10 y reúne las tres cosas que el
 * contrato deja sobre un concepto:
 *   - `GET /conceptos/{id}/explosion` — el árbol recursivo (C, SI);
 *   - `GET /conceptos/{id}/cpu` — versión **vigente**, historial y el precio
 *     recalculado de hoy (C, SI);
 *   - `POST /conceptos/{id}/cpu` — publicar una versión nueva (solo C).
 *
 * ## Los dos números (§7.3)
 *
 * "El **destajo** = mano de obra o subcontrato (lo que cobra la cuadrilla);
 * el **CPU** = costo total (materiales + auxiliares + matrices + MO +
 * equipo)". No son dos sumas paralelas: el destajo es la **porción** del
 * mismo árbol, incluida la mano de obra que viene dentro de un auxiliar. El
 * backend devuelve las dos —más el resto— ya calculadas; esta pantalla las
 * muestra lado a lado y **no** las recompone.
 */

import { useMemo, useState } from 'react';

import {
  useExplotarConceptoApiV1ConceptosConceptoIdExplosionGet,
  useObtenerCpuApiV1ConceptosConceptoIdCpuGet,
} from '@/api/generado/catalogos/catalogos';
import type {
  ConceptoRespuesta,
  CPURespuesta,
  ExplosionRespuesta,
  UnidadRespuesta,
  VersionCPURespuesta,
  VersionPublicadaRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import { fmtMXN } from '@/lib/formato';
import type { Rol } from '@/shell/navegacion';
import { ArbolExplosion } from './ArbolExplosion';
import { NuevaVersionCPU } from './NuevaVersionCPU';
import {
  armarArbolExplosion,
  contarLineas,
  estadoCPU,
  notaEstadoCPU,
  variantesDelHistorial,
  type EstadoCPU,
} from './explosion';
import { etiquetaTipoConcepto, puedePublicarCPU } from './reglas';

interface Props {
  readonly concepto: ConceptoRespuesta;
  readonly rol: Rol;
  readonly unidad?: UnidadRespuesta;
  readonly onCerrar: () => void;
}

const TONO_ESTADO: Record<EstadoCPU, string> = {
  sin_vigente: 'warn',
  al_dia: 'ok',
  desfasado: 'danger',
};

const ETIQUETA_ESTADO: Record<EstadoCPU, string> = {
  sin_vigente: 'Sin CPU publicado',
  al_dia: 'Vigente al día',
  desfasado: 'Vigente desfasado',
};

export function PanelAPU({ concepto, rol, unidad, onCerrar }: Props) {
  // `variante` acota la consulta del CPU a una receta alterna (§10.1);
  // vacío = receta base. La explosión no la recibe: el contrato solo la
  // expone en `GET /conceptos/{id}/cpu`.
  const [variante, setVariante] = useState('');
  const [publicando, setPublicando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  const explosionQ = useExplotarConceptoApiV1ConceptosConceptoIdExplosionGet<
    ExplosionRespuesta,
    ErrorApi
  >(concepto.id);

  const cpuQ = useObtenerCpuApiV1ConceptosConceptoIdCpuGet<CPURespuesta, ErrorApi>(
    concepto.id,
    { variante: variante === '' ? undefined : variante },
  );

  const arbol = useMemo(
    () => armarArbolExplosion(explosionQ.data?.lineas ?? []),
    [explosionQ.data],
  );

  const cpu = cpuQ.data;
  const estado = cpu ? estadoCPU(cpu) : null;
  const variantes = cpu ? variantesDelHistorial(cpu) : [];

  return (
    <Sheet
      titulo={concepto.clave}
      subtitulo={`${etiquetaTipoConcepto(concepto.tipo)}${unidad ? ` · ${unidad.clave}` : ''}`}
      onCerrar={onCerrar}
    >
      <div className="sheet__body col gap-16">
        <div className="text-sm">{concepto.descripcion}</div>

        {aviso !== null && (
          <div role="status">
            <span className="badge badge--ok">{aviso}</span>
          </div>
        )}

        {explosionQ.isError && <ErrorBanner mensaje={explosionQ.error.message} />}
        {cpuQ.isError && <ErrorBanner mensaje={cpuQ.error.message} />}

        {/* ── CPU vigente ─────────────────────────────────────────── */}
        <section className="card">
          <div className="card__header">
            <div>
              <h3 className="card__title">CPU vigente</h3>
              <div className="card__sub">
                Destajo = lo que cobra la cuadrilla; total = costo completo (§7.3).
              </div>
            </div>
            {estado !== null && (
              <span className={`badge badge--${TONO_ESTADO[estado]}`}>
                {ETIQUETA_ESTADO[estado]}
              </span>
            )}
          </div>

          <div className="card__body col gap-12">
            {cpuQ.isLoading ? (
              <div className="text-mute text-sm">Cargando CPU…</div>
            ) : cpu === undefined ? (
              <div className="text-mute text-sm">Sin datos de CPU.</div>
            ) : (
              <>
                {variantes.length > 0 && (
                  <div className="field">
                    <label className="field__label" htmlFor="apu-variante">
                      Variante (receta)
                    </label>
                    <select
                      id="apu-variante"
                      className="select"
                      value={variante}
                      onChange={(e) => setVariante(e.target.value)}
                    >
                      <option value="">Receta base</option>
                      {variantes.map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <DesgloseCPU
                  titulo={
                    cpu.vigente
                      ? `Publicado · versión ${cpu.vigente.version}`
                      : 'Sin versión publicada'
                  }
                  precio={cpu.vigente?.precio ?? null}
                />

                <DesgloseCPU
                  titulo="Calculado desde la explosión de hoy"
                  precio={cpu.calculado}
                />

                {estado !== null && (
                  <div className="text-mute text-sm">{notaEstadoCPU(estado)}</div>
                )}

                {puedePublicarCPU(rol) && (
                  <div className="row">
                    <button
                      type="button"
                      className="btn btn--accent"
                      onClick={() => setPublicando(true)}
                    >
                      Publicar nueva versión
                    </button>
                  </div>
                )}

                <HistorialCPU versiones={cpu.historial} />
              </>
            )}
          </div>
        </section>

        {/* ── Explosión ───────────────────────────────────────────── */}
        <section className="card">
          <div className="card__header">
            <div>
              <h3 className="card__title">Explosión</h3>
              <div className="card__sub">
                Composición recursiva: insumos y conceptos anidados —auxiliares y matrices—
                con su rendimiento (§7.3).
              </div>
            </div>
            <span className="badge badge--outline tnum">{contarLineas(arbol)} líneas</span>
          </div>
          <div className="card__body card__body--flush">
            {explosionQ.isLoading ? (
              <div className="text-mute text-sm" style={{ padding: '16px 12px' }}>
                Cargando explosión…
              </div>
            ) : (
              <div style={{ padding: 12 }}>
                <ArbolExplosion nodos={arbol} clave={concepto.clave} />
              </div>
            )}
          </div>
        </section>
      </div>

      {publicando && cpu !== undefined && (
        <NuevaVersionCPU
          conceptoId={concepto.id}
          clave={concepto.clave}
          calculado={cpu.calculado}
          varianteInicial={variante}
          onCerrar={() => setPublicando(false)}
          onPublicada={(publicada: VersionPublicadaRespuesta) => {
            setPublicando(false);
            setAviso(
              publicada.retiradas.length === 0
                ? `Versión ${publicada.version.version} publicada`
                : `Versión ${publicada.version.version} publicada; retiradas: ${publicada.retiradas.join(', ')}`,
            );
            void cpuQ.refetch();
          }}
        />
      )}
    </Sheet>
  );
}

function DesgloseCPU({
  titulo,
  precio,
}: {
  readonly titulo: string;
  readonly precio: { readonly total: string; readonly destajo: string; readonly materiales: string } | null;
}) {
  return (
    <div>
      <div className="text-mute text-xs mono" style={{ textTransform: 'uppercase' }}>
        {titulo}
      </div>
      {precio === null ? (
        <div className="text-mute text-sm mt-8">—</div>
      ) : (
        <div className="kpi-grid mt-8" style={{ marginBottom: 0 }}>
          <div className="kpi">
            <div className="kpi__label">Total (CPU)</div>
            <div className="kpi__value">{fmtMXN(precio.total)}</div>
          </div>
          <div className="kpi">
            <div className="kpi__label">Destajo</div>
            <div className="kpi__value">{fmtMXN(precio.destajo)}</div>
            <div className="kpi__sub">Mano de obra y subcontrato (§7.3)</div>
          </div>
          <div className="kpi">
            <div className="kpi__label">Resto</div>
            <div className="kpi__value">{fmtMXN(precio.materiales)}</div>
            <div className="kpi__sub">Materiales, equipo, auxiliares y matrices</div>
          </div>
        </div>
      )}
    </div>
  );
}

function HistorialCPU({ versiones }: { readonly versiones: readonly VersionCPURespuesta[] }) {
  if (versiones.length === 0) {
    return (
      <div className="text-mute text-sm">
        Sin historial: este concepto todavía no tiene ninguna versión de CPU (§10.8).
      </div>
    );
  }

  return (
    <div className="table-wrap">
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Versión</th>
              <th>Variante</th>
              <th>Total</th>
              <th>Destajo</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {versiones.map((version) => (
              <tr key={`${version.version}-${version.variante ?? ''}`}>
                <td className="is-key">v{version.version}</td>
                <td className="mono text-xs">{version.variante ?? 'base'}</td>
                <td className="is-num">{fmtMXN(version.precio.total)}</td>
                <td className="is-num">{fmtMXN(version.precio.destajo)}</td>
                <td>
                  {version.vigente === true ? (
                    <span className="badge badge--ok">Vigente</span>
                  ) : (
                    <span className="badge badge--outline">Histórica</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
