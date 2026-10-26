/**
 * Cajón de detalle de una obra (drill-down del §12.10).
 *
 * Reúne las tres acciones que el contrato deja sobre una obra:
 *   - lectura del detalle — `GET /obras/{id}` (todos, por alcance §4);
 *   - edición — `PATCH /obras/{id}` (solo Control de obra, §11.2);
 *   - generación de actividades desde el prototipo — `POST
 *     /obras/{id}/generar`, Workflow A (§11.3 A.2);
 *   - la junta de arranque — `POST /obras/{id}/iniciar`: la obra pasa de
 *     `pendiente` a `iniciada` y el cronograma arranca ese día (D-537).
 *
 * El componente monta el formulario a partir de la obra recibida; se espera
 * que el padre lo remonte con `key={obra.id}` al cambiar de obra.
 */

import { useMemo, useState, type FormEvent } from 'react';

import { useClavesPorRecurso } from '@/lib/idempotencia';

import {
  useActualizarObraApiV1ObrasObraIdPatch,
  useGenerarObraApiV1ObrasObraIdGenerarPost,
  useIniciarObraApiV1ObrasObraIdIniciarPost,
  useRevertirGeneracionApiV1ObrasObraIdActividadesDelete,
} from '@/api/generado/obras/obras';
import { useListarUsuariosApiV1UsuariosGet } from '@/api/generado/usuarios/usuarios';
import { ModoPago, Rol as RolUsuario } from '@/api/generado/modelo';
import type {
  ClusterRespuesta,
  ObraGeneradaRespuesta,
  ObraRespuesta,
  PrototipoRespuesta,
  UsuarioRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { colorAvance, fmtFecha, fmtNum, fmtPct } from '@/lib/formato';
import { hoyISO } from '@/materiales/formulario';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import type { Rol } from '@/shell/navegacion';
import { useArranqueDeLaObraApiV1ObrasObraIdArranqueGet } from '@/api/generado/partes/partes';
import { InstanciarPrograma } from '@/programacion/InstanciarPrograma';
import { CampoSelect, CampoTexto } from './Campos';
import { cambiosDeObra, formularioDeObra, hayCambios } from './formulario';
import {
  etiquetaEstatusObra,
  impedimentoParaGenerar,
  motivoImpedimento,
  puedeDeclararJuntaDeArranque,
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
  const [instanciando, setInstanciando] = useState(false);
  const [fechaJunta, setFechaJunta] = useState(() => hoyISO());
  // Requisito de la junta: ¿todo validado? Avisa; lo que impide es asignar (el candado).
  const arranque = useArranqueDeLaObraApiV1ObrasObraIdArranqueGet(obra.id);
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  // Una clave por (método, ruta): generar la obra A y la obra B son
  // operaciones distintas, y reintentar la A reusa la suya (regla 1 del
  // ROADMAP). Generar dos veces la misma obra duplicaría sus actividades.
  const idempotente = useClavesPorRecurso();

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
    ...idempotente,
  });

  /**
   * Deshacer el workflow A.
   *
   * Generar escribe cientos de renglones de un botón y con un modo de pago que
   * se elige antes de ver el resultado; equivocarse ahí costaba reiniciar la
   * organización entera. El backend frena si ya hay avance capturado — ahí
   * borrar deja de ser deshacer (§11.3 A.2).
   */
  const revertir = useRevertirGeneracionApiV1ObrasObraIdActividadesDelete<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        setGenerada(null);
        onCambiada();
      },
      onError: (err) => setError({ mensaje: err.message, campo: err.campo }),
    },
  });

  // La junta de arranque es una marca manual y se da una sola vez; la clave de
  // idempotencia es por (método, ruta) así que un doble clic no la repite.
  const iniciar = useIniciarObraApiV1ObrasObraIdIniciarPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        onCambiada();
      },
      onError: (err) => setError({ mensaje: err.message, campo: err.campo }),
    },
    ...idempotente,
  });

  // Cualquier rol puede leer `GET /usuarios` (§5.1: quién es el residente de
  // una obra no es información privilegiada) — así que aquí se resuelve el
  // nombre para todos, no solo para quien puede editar.
  const usuariosQ = useListarUsuariosApiV1UsuariosGet<UsuarioRespuesta[], ErrorApi>({
    rol: RolUsuario.residente,
  });
  const residenteActual = (usuariosQ.data ?? []).find((u) => u.id === obra.residente_id);
  // El actual entra siempre a las opciones, esté activo o no: si dejó de
  // ser residente, el <select> no debe mostrar "Sin asignar" en su lugar,
  // que sería peor que ver a alguien inactivo ya asignado.
  const residentesActivos = useMemo(() => {
    const activos = (usuariosQ.data ?? []).filter((u) => u.estatus === 'activo');
    if (residenteActual && residenteActual.estatus !== 'activo') return [residenteActual, ...activos];
    return activos;
  }, [usuariosQ.data, residenteActual]);

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
          <Dato
            etiqueta="Residente"
            valor={
              obra.residente_id === null
                ? 'Sin asignar'
                : (residenteActual?.nombre ?? obra.residente_id)
            }
            mono={obra.residente_id !== null && !residenteActual}
          />
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
              <CampoSelect
                id="editar-residente"
                etiqueta="Residente"
                valor={formulario.residenteId}
                onCambio={(residenteId) => setFormulario((f) => ({ ...f, residenteId }))}
                opciones={residentesActivos.map((usuario) => ({
                  valor: usuario.id,
                  etiqueta: usuario.nombre,
                }))}
                vacio="Sin asignar"
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

        {puedeDeclararJuntaDeArranque(rol, obra) && (
          <div className="card">
            <div className="card__header">
              <div>
                <h3 className="card__title">Junta de arranque</h3>
                <div className="card__sub">
                  Marca la obra como iniciada. La fecha de la junta es el arranque del
                  cronograma: lo que cuelga de ella se recalcula (D-537).
                </div>
              </div>
            </div>
            <div className="card__body col gap-12">
              {arranque.data && (
                <div className="row gap-8" style={{ alignItems: 'center', flexWrap: 'wrap' }}>
                  <span className={`badge badge--${arranque.data.todo_validado ? 'ok' : 'warn'}`}>
                    {arranque.data.todo_validado
                      ? 'Todo validado'
                      : `Falta validar ${arranque.data.sin_autorizar.length} de ${arranque.data.total} partes`}
                  </span>
                  <span className="text-xs text-mute">
                    Requisito de la junta. {arranque.data.candado_asignar
                      ? 'El candado impide asignar lo no validado.'
                      : 'Sin candado: avisa, no impide asignar.'}
                  </span>
                </div>
              )}
              <CampoTexto
                id="junta-fecha"
                etiqueta="Fecha de la junta"
                valor={fechaJunta}
                onCambio={setFechaJunta}
                tipo="date"
              />
              <div className="row">
                <button
                  type="button"
                  className="btn btn--accent"
                  disabled={iniciar.isPending || fechaJunta === ''}
                  onClick={() =>
                    iniciar.mutate({ obraId: obra.id, data: { fecha: fechaJunta } })
                  }
                >
                  {iniciar.isPending ? 'Declarando…' : 'Declarar junta de arranque'}
                </button>
              </div>
            </div>
          </div>
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
                    {/* Solo tras generar en esta sesión: para una obra que ya
                        venía generada de antes, el panel ni siquiera se ofrece
                        —el backend responde 409— y el botón sobraría. */}
                    {generada !== null && (
                      <button
                        type="button"
                        className="btn"
                        disabled={revertir.isPending}
                        title="Borra las actividades y el programa recién creados. La obra se queda."
                        onClick={() => revertir.mutate({ obraId: obra.id })}
                      >
                        {revertir.isPending ? 'Deshaciendo…' : 'Deshacer'}
                      </button>
                    )}
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

              {/* Aplicar el programa base vivía solo dentro del Gantt de obra
                  (`/programas`), que es donde se mira el cronograma y no donde
                  se prepara la obra. Se ofrece también aquí porque es el paso
                  siguiente a generar: la generación baja las duraciones de la
                  plantilla **de ese momento**, y volver a aplicarla es lo que
                  recoge los cambios que el programa base tuvo después (§7.5). */}
              {impedimento === null && (
                <div className="col gap-2" style={{ alignItems: 'flex-start' }}>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => setInstanciando(true)}
                  >
                    Aplicar el programa base…
                  </button>
                  <span className="field__hint">
                    Baja la plantilla de duraciones del prototipo al cronograma y
                    crea una versión nueva (§7.5).
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {instanciando && (
        <InstanciarPrograma
          obra={obra}
          rol={rol}
          onCerrar={() => setInstanciando(false)}
          onInstanciado={onCambiada}
        />
      )}
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
