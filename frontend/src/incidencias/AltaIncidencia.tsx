/**
 * Alta de incidencia — `POST /incidencias` (§11.2, §11.3 F.1).
 *
 * *"Cualquier rol abre una incidencia"* (§11.2, contrato). El formulario
 * traduce a DTO en `formulario.ts`; la lista de actividades bloqueadas solo
 * se manda con impacto `detiene` (§6) y la UI lo dice explícitamente.
 */

import { useState, type FormEvent } from 'react';

import { useAbrirIncidenciaApiV1IncidenciasPost } from '@/api/generado/incidencias/incidencias';
import { useListarFrentesApiV1FrentesGet } from '@/api/generado/proyectos/proyectos';
import { ImpactoIncidencia, TipoIncidencia } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import { SelectorObra } from '@/lib/SelectorObra';
import {
  formularioIncidenciaVacio,
  incidenciaCompleta,
  peticionDeIncidencia,
  type FormularioIncidencia,
} from './formulario';
import { descripcionImpacto, detieneObra, etiquetaImpacto, etiquetaTipo } from './reglas';

interface Props {
  readonly obraIdInicial: string;
  readonly onCerrar: () => void;
  readonly onAbierta: () => void;
}

export function AltaIncidencia({ obraIdInicial, onCerrar, onAbierta }: Props) {
  const [formulario, setFormulario] = useState<FormularioIncidencia>(() =>
    formularioIncidenciaVacio(
      obraIdInicial,
      TipoIncidencia.falta_material,
      ImpactoIncidencia.detalle,
    ),
  );
  const [error, setError] = useState<string | null>(null);

  const frentes = useListarFrentesApiV1FrentesGet();

  const abrir = useAbrirIncidenciaApiV1IncidenciasPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        onAbierta();
      },
      onError: (err) => setError(err.message),
    },
  });

  function cambiar<K extends keyof FormularioIncidencia>(
    campo: K,
    valor: FormularioIncidencia[K],
  ) {
    setFormulario((previo) => ({ ...previo, [campo]: valor }));
  }

  const detiene = detieneObra(formulario.impacto);

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!incidenciaCompleta(formulario)) return;
    abrir.mutate({ data: peticionDeIncidencia(formulario) });
  }

  return (
    <Sheet titulo="Abrir incidencia" subtitulo="POST /incidencias · §11.3 F.1" onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          {error && <ErrorBanner mensaje={error} />}

          <SelectorObra
            id="incidencia-obra"
            etiqueta="Obra"
            valor={formulario.obraId}
            onCambio={(obraId) => cambiar('obraId', obraId)}
            requerido
          />

          <div className="field">
            <label className="field__label" htmlFor="incidencia-titulo">
              Título
            </label>
            <input
              id="incidencia-titulo"
              className="input"
              required
              value={formulario.titulo}
              onChange={(e) => cambiar('titulo', e.target.value)}
            />
          </div>

          <div className="row gap-12">
            <div className="field w-full">
              <label className="field__label" htmlFor="incidencia-tipo">
                Tipo
              </label>
              <select
                id="incidencia-tipo"
                className="select"
                value={formulario.tipo}
                onChange={(e) => cambiar('tipo', e.target.value as TipoIncidencia)}
              >
                {Object.values(TipoIncidencia).map((tipo) => (
                  <option key={tipo} value={tipo}>
                    {etiquetaTipo(tipo)}
                  </option>
                ))}
              </select>
            </div>

            <div className="field w-full">
              <label className="field__label" htmlFor="incidencia-impacto">
                Impacto
              </label>
              <select
                id="incidencia-impacto"
                className="select"
                value={formulario.impacto}
                onChange={(e) => cambiar('impacto', e.target.value as ImpactoIncidencia)}
              >
                {Object.values(ImpactoIncidencia).map((impacto) => (
                  <option key={impacto} value={impacto}>
                    {etiquetaImpacto(impacto)}
                  </option>
                ))}
              </select>
              <div className="field__hint">{descripcionImpacto(formulario.impacto)}</div>
            </div>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="incidencia-frente">
              Frente (opcional)
            </label>
            <select
              id="incidencia-frente"
              className="select"
              value={formulario.frenteId}
              onChange={(e) => cambiar('frenteId', e.target.value)}
            >
              <option value="">Sin frente</option>
              {(frentes.data ?? []).map((frente) => (
                <option key={frente.id} value={frente.id}>
                  {frente.clave} · {frente.nombre}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="incidencia-descripcion">
              Descripción (opcional)
            </label>
            <textarea
              id="incidencia-descripcion"
              className="textarea"
              value={formulario.descripcion}
              onChange={(e) => cambiar('descripcion', e.target.value)}
            />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="incidencia-limite">
              Fecha límite (opcional)
            </label>
            <input
              id="incidencia-limite"
              className="input"
              type="date"
              value={formulario.fechaLimite}
              onChange={(e) => cambiar('fechaLimite', e.target.value)}
            />
          </div>

          {detiene && (
            <div className="field">
              <label className="field__label" htmlFor="incidencia-bloquea">
                Actividades que se detienen
              </label>
              <textarea
                id="incidencia-bloquea"
                className="textarea input--mono"
                placeholder="Un id de actividad por línea"
                value={formulario.bloqueaActividades}
                onChange={(e) => cambiar('bloqueaActividades', e.target.value)}
              />
              <div className="field__hint">
                Con impacto «detiene» la incidencia <strong>frena la obra</strong>: el
                backend bloquea estas actividades y recalcula la ruta crítica
                (§6, §11.3 F.5). El contrato solo acepta esta lista con este
                impacto.
              </div>
            </div>
          )}
        </div>

        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button
            type="submit"
            className="btn btn--accent"
            disabled={abrir.isPending || !incidenciaCompleta(formulario)}
          >
            {abrir.isPending ? 'Abriendo…' : 'Abrir incidencia'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
