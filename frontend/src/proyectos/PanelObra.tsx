/**
 * Cajón de detalle de una obra (drill-down del §12.10).
 *
 * Reúne las tres acciones que el contrato deja sobre una obra:
 *   - lectura del detalle — `GET /obras/{id}` (todos, por alcance §4);
 *   - edición — `PATCH /obras/{id}` (solo Control de obra, §11.2);
 *   - generación de actividades desde el prototipo — `POST
 *     /obras/{id}/generar`, Workflow A (§11.3 A.2).
 *
 * El componente monta el formulario a partir de la obra recibida; se espera
 * que el padre lo remonte con `key={obra.id}` al cambiar de obra.
 */

import { useState, type FormEvent } from 'react';

import {
  useActualizarObraApiV1ObrasObraIdPatch,
  useGenerarObraApiV1ObrasObraIdGenerarPost,
} from '@/api/generado/obras/obras';
import { ModoPago } from '@/api/generado/modelo';
import type {
  ClusterRespuesta,
  ObraGeneradaRespuesta,
  ObraRespuesta,
  PrototipoRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { colorAvance, fmtFecha, fmtNum, fmtPct } from '@/lib/formato';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import type { Rol } from '@/shell/navegacion';
import { CampoTexto } from './Campos';
import { cambiosDeObra, formularioDeObra, hayCambios } from './formulario';
import {
  etiquetaEstatusObra,
  impedimentoParaGenerar,
  motivoImpedimento,
  puedeEditarObra,
  tonoEstatusObra,
} from './reglas';

interface Props {
  readonly obra: ObraRespuesta;
  readonly rol: Rol;
  readonly cluster?: ClusterRespuesta;
  readonly prototipo?: PrototipoRespuesta;
  readonly onCerrar: () => void;
  /** El padre revalida la lista tras una edición o una generación. */
  readonly onCambiada: () => void;
}

export function PanelObra({ obra, rol, cluster, prototipo, onCerrar, onCambiada }: Props) {
  const [formulario, setFormulario] = useState(() => formularioDeObra(obra));
  const [modoPago, setModoPago] = useState<ModoPago>(ModoPago.destajo);
  const [generada, setGenerada] = useState<ObraGeneradaRespuesta | null>(null);
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  const editar = useActualizarObraApiV1ObrasObraIdPatch<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        onCambiada();
      },
      onError: (err) => setError({ mensaje: err.message, campo: err.campo }),
    },
  });

  const generar = useGenerarObraApiV1ObrasObraIdGenerarPost<ErrorApi>({
    mutation: {
      onSuccess: (respuesta) => {
        setError(null);
        setGenerada(respuesta);
        onCambiada();
      },
      onError: (err) => setError({ mensaje: err.message, campo: err.campo }),
    },
  });

  const editable = puedeEditarObra(rol, obra);
  const impedimento = impedimentoParaGenerar(rol, obra);
  const cambios = cambiosDeObra(obra, formulario);
  const avance = Number(obra.avance_pct);

  function alGuardar(evento: FormEvent) {
    evento.preventDefault();
    if (!editable || !hayCambios(cambios) || editar.isPending) return;
    editar.mutate({ obraId: obra.id, data: cambios });
  }

  return (
    <Sheet titulo={obra.clave} subtitulo={obra.id} onCerrar={onCerrar}>
      <div className="sheet__body col gap-16">
        <div className="row gap-4" style={{ flexWrap: 'wrap' }}>
          <span className={`badge badge--${tonoEstatusObra(obra.estatus)}`}>
            {etiquetaEstatusObra(obra.estatus)}
          </span>
          {obra.es_urba && <span className="badge badge--outline">Urbanización</span>}
        </div>

        <div>
          <div className={`bar ${colorAvance(avance) !== 'accent' ? `bar--${colorAvance(avance)}` : ''}`}>
            <div
              className="bar__fill"
              style={{ width: `${Math.min(100, Math.max(0, avance))}%` }}
            />
          </div>
          <div className="text-mute text-xs mono tnum mt-8">
            Avance {fmtPct(obra.avance_pct)}
          </div>
        </div>

        <dl className="col gap-4" style={{ margin: 0 }}>
          <Dato etiqueta="Cluster" valor={cluster ? `${cluster.clave} — ${cluster.nombre}` : obra.cluster_id} mono={!cluster} />
          <Dato
            etiqueta="Prototipo"
            valor={
              obra.prototipo_id === null
                ? '—'
                : prototipo
                  ? `${prototipo.clave} · ${prototipo.nombre}`
                  : obra.prototipo_id
            }
            mono={obra.prototipo_id !== null && !prototipo}
          />
          <Dato etiqueta="Residente" valor={obra.residente_id ?? 'Sin asignar'} mono={obra.residente_id !== null} />
          <Dato etiqueta="Inicio" valor={fmtFecha(obra.fecha_inicio)} />
          <Dato etiqueta="Fin" valor={fmtFecha(obra.fecha_fin)} />
          <Dato etiqueta="m²" valor={fmtNum(obra.m2)} />
        </dl>

        {error && <ErrorBanner mensaje={error.mensaje} campo={error.campo} />}

        {editable && (
          <form onSubmit={alGuardar} className="card">
            <div className="card__header">
              <div>
                <h3 className="card__title">Editar obra</h3>
                <div className="card__sub">
                  El estatus lo deriva el avance y el cierre de obra final (§6, §11.3 D).
                </div>
              </div>
            </div>
            <div className="card__body col gap-12">
              <CampoTexto
                id="editar-clave"
                etiqueta="Clave"
                valor={formulario.clave}
                onCambio={(clave) => setFormulario((f) => ({ ...f, clave }))}
                mono
              />
              <CampoTexto
                id="editar-residente"
                etiqueta="Residente (uuid)"
                valor={formulario.residenteId}
                onCambio={(residenteId) => setFormulario((f) => ({ ...f, residenteId }))}
                mono
                pista="Vacío libera la obra."
              />
              <div className="row gap-12">
                <div style={{ flex: 1 }}>
                  <CampoTexto
                    id="editar-fecha-inicio"
                    etiqueta="Inicio"
                    valor={formulario.fechaInicio}
                    onCambio={(fechaInicio) => setFormulario((f) => ({ ...f, fechaInicio }))}
                    tipo="date"
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <CampoTexto
                    id="editar-fecha-fin"
                    etiqueta="Fin"
                    valor={formulario.fechaFin}
                    onCambio={(fechaFin) => setFormulario((f) => ({ ...f, fechaFin }))}
                    tipo="date"
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <CampoTexto
                    id="editar-m2"
                    etiqueta="m²"
                    valor={formulario.m2}
                    onCambio={(m2) => setFormulario((f) => ({ ...f, m2 }))}
                    tipo="number"
                    mono
                    paso="any"
                    minimo="0"
                  />
                </div>
              </div>
              <div className="row">
                <button
                  type="submit"
                  className="btn btn--primary"
                  disabled={!hayCambios(cambios) || editar.isPending}
                >
                  {editar.isPending ? 'Guardando…' : 'Guardar cambios'}
                </button>
              </div>
            </div>
          </form>
        )}

        {/* La generación es del creador de obra (§11.2): a los demás roles
            ni siquiera se les muestra la tarjeta. */}
        {impedimento !== 'rol' && (
          <div className="card">
            <div className="card__header">
              <div>
                <h3 className="card__title">Generar desde prototipo</h3>
                <div className="card__sub">
                  Workflow A: crea las actividades con su CPU vigente e instancia el
                  programa de obra (§11.3 A.2).
                </div>
              </div>
            </div>
            <div className="card__body col gap-12">
              {impedimento !== null ? (
                <div className="text-mute text-sm">{motivoImpedimento(impedimento)}</div>
              ) : (
                <>
                  <div className="field">
                    <label className="field__label" htmlFor="generar-modo">
                      Modo de pago de las actividades
                    </label>
                    <select
                      id="generar-modo"
                      className="select"
                      value={modoPago}
                      onChange={(e) => setModoPago(e.target.value as ModoPago)}
                    >
                      <option value={ModoPago.destajo}>Destajo</option>
                      <option value={ModoPago.concepto}>Concepto</option>
                      <option value={ModoPago.subcontrato}>Subcontrato</option>
                    </select>
                  </div>
                  <div className="row">
                    <button
                      type="button"
                      className="btn btn--accent"
                      disabled={generar.isPending}
                      onClick={() =>
                        generar.mutate({ obraId: obra.id, data: { modo_pago: modoPago } })
                      }
                    >
                      {generar.isPending ? 'Generando…' : 'Generar actividades'}
                    </button>
                  </div>
                </>
              )}

              {generada && (
                <div className="text-sm" role="status">
                  <span className="badge badge--ok">Generada</span>{' '}
                  <span className="mono tnum">{generada.n_actividades}</span> actividades ·
                  programa <span className="mono">{generada.programa_obra_id.slice(0, 8)}</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </Sheet>
  );
}

function Dato({
  etiqueta,
  valor,
  mono = false,
}: {
  readonly etiqueta: string;
  readonly valor: string;
  readonly mono?: boolean;
}) {
  return (
    <div className="row" style={{ justifyContent: 'space-between', gap: 12 }}>
      <dt className="text-mute text-sm">{etiqueta}</dt>
      <dd className={mono ? 'text-sm mono' : 'text-sm'} style={{ margin: 0, textAlign: 'right' }}>
        {valor}
      </dd>
    </div>
  );
}
