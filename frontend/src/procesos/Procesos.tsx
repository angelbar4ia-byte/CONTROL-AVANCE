/**
 * Mejora de procesos — el tablero del Super intendente (§7.9, §11.2, §5.1).
 *
 * La entrada «Presupuesto → Mejora de procesos» está en su sidebar desde la
 * Fase 1 y hasta ahora caía en "en construcción": la tabla `proceso` existía
 * desde la migración 0010 y no había endpoints. Era el último bloque del
 * §11.2 sin implementar.
 *
 * ## Qué es esta pantalla, en una línea
 *
 * Lo que la organización decidió cambiar en su forma de trabajar, y en qué
 * quedó. No es un gestor de tareas: no tiene responsable, ni fecha, ni
 * subtareas. El §7.9 le da a `Proceso` cuatro campos y esta pantalla no
 * inventa un quinto.
 *
 * ## Todos leen, el SI escribe
 *
 * La asimetría del §11.2 es deliberada y se ve aquí: el residente entra por la
 * URL y **ve el tablero** —tiene que poder, si se espera que siga el proceso—
 * pero no ve el formulario ni los botones de etapa.
 */

import { useState, type FormEvent } from 'react';

import {
  useCambiarEstatusProcesoApiV1ProcesosProcesoIdPatch,
  useCrearProcesoApiV1ProcesosPost,
  useListarProcesosApiV1ProcesosGet,
} from '@/api/generado/procesos/procesos';
import { EstatusProceso as EstatusApi, type ProcesoRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtFecha } from '@/lib/formato';
import {
  ESTATUS_PROCESO,
  etiquetaEstatus,
  ordenDeEstatus,
  procesoCompleto,
  puedeEditarProcesos,
  tonoEstatus,
  type FormularioProceso,
} from './reglas';

const VACIO: FormularioProceso = { nombre: '', descripcion: '' };

export default function Procesos() {
  const { sesion } = useSesion();
  const [formulario, setFormulario] = useState<FormularioProceso>(VACIO);
  const [error, setError] = useState<string | null>(null);

  const consulta = useListarProcesosApiV1ProcesosGet<ProcesoRespuesta[], ErrorApi>();

  const crear = useCrearProcesoApiV1ProcesosPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        setFormulario(VACIO);
        void consulta.refetch();
      },
      onError: (err) => setError(err.message),
    },
  });

  const mover = useCambiarEstatusProcesoApiV1ProcesosProcesoIdPatch<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        void consulta.refetch();
      },
      onError: (err) => setError(err.message),
    },
  });

  if (!sesion) return null;

  const puedeEditar = puedeEditarProcesos(sesion.rol);

  // El orden del tablero se decide aquí y no en el servidor: `listar` devuelve
  // por `updated_at desc`, que es el criterio dentro de cada etapa, y agrupar
  // por etapa es una decisión de esta pantalla.
  const procesos = [...(consulta.data ?? [])].sort(
    (a, b) => ordenDeEstatus(a.estatus) - ordenDeEstatus(b.estatus),
  );

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!procesoCompleto(formulario)) return;
    crear.mutate({
      data: {
        nombre: formulario.nombre.trim(),
        descripcion: formulario.descripcion.trim() || null,
        estatus: EstatusApi.propuesto,
      },
    });
  }

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Presupuesto</div>
          <h1 className="page__title">Mejora de procesos</h1>
          <div className="page__subtitle">
            Lo que se decidió cambiar en la forma de trabajar, y en qué quedó (§7.9).
          </div>
        </div>
      </div>

      {error && <ErrorBanner mensaje={error} />}

      {puedeEditar && (
        <form onSubmit={alEnviar} className="card mb-8">
          <div className="card__header">
            <h2 className="card__title">Proponer un proceso</h2>
          </div>
          <div className="card__body col gap-12">
            <div className="field">
              <label className="field__label" htmlFor="proceso-nombre">
                Nombre
              </label>
              <input
                id="proceso-nombre"
                className="input"
                value={formulario.nombre}
                onChange={(e) =>
                  setFormulario((previo) => ({ ...previo, nombre: e.target.value }))
                }
                placeholder="Junta de arranque por cluster"
                required
              />
            </div>

            <div className="field">
              <label className="field__label" htmlFor="proceso-descripcion">
                Qué cambia y por qué
              </label>
              <textarea
                id="proceso-descripcion"
                className="input"
                rows={3}
                value={formulario.descripcion}
                onChange={(e) =>
                  setFormulario((previo) => ({ ...previo, descripcion: e.target.value }))
                }
                placeholder="Antes de iniciar, recorrer el cluster con el residente para detectar interferencias."
              />
              <div className="field__hint">
                Opcional, pero es lo que hace útil el tablero seis meses después.
              </div>
            </div>

            <div className="row gap-8">
              <button
                type="submit"
                className="btn btn--primary"
                disabled={!procesoCompleto(formulario) || crear.isPending}
              >
                {crear.isPending ? 'Guardando…' : 'Proponer'}
              </button>
            </div>
          </div>
        </form>
      )}

      {consulta.isLoading ? (
        <div className="empty">
          <div className="empty-title">Cargando…</div>
        </div>
      ) : procesos.length === 0 ? (
        <div className="empty">
          <div className="empty-title">Todavía no hay procesos</div>
          <div className="empty-sub">
            {puedeEditar
              ? 'Anota el primero cuando algo se repita mal dos veces.'
              : 'El Super intendente los da de alta (§11.2).'}
          </div>
        </div>
      ) : (
        <div className="col gap-8">
          {procesos.map((proceso) => (
            <article key={proceso.id} className="card">
              <div className="card__header">
                <h3 className="card__title">{proceso.nombre}</h3>
                <span className={`badge ${tonoEstatus(proceso.estatus)}`}>
                  {etiquetaEstatus(proceso.estatus)}
                </span>
              </div>
              <div className="card__body col gap-8">
                {proceso.descripcion ? (
                  <p className="text-soft">{proceso.descripcion}</p>
                ) : (
                  <p className="text-mute text-sm">Sin descripción.</p>
                )}

                <div className="row gap-12 text-mute text-sm">
                  <span className="mono">{fmtFecha(proceso.updated_at)}</span>
                </div>

                {puedeEditar && (
                  <div className="row gap-8">
                    {ESTATUS_PROCESO.filter((etapa) => etapa !== proceso.estatus).map(
                      (etapa) => (
                        <button
                          key={etapa}
                          type="button"
                          className="btn btn--sm"
                          disabled={mover.isPending}
                          onClick={() =>
                            mover.mutate({
                              procesoId: proceso.id,
                              data: { estatus: etapa as EstatusApi },
                            })
                          }
                        >
                          {etiquetaEstatus(etapa)}
                        </button>
                      ),
                    )}
                  </div>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
