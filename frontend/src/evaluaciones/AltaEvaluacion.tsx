/**
 * Alta de evaluación — `POST /evaluaciones` (§11.2, §11.3 workflow H).
 *
 * El **nivel lo fija el rol** (auto R · control C · final SI, §11.3 H): no se
 * ofrece un selector de nivel porque un rol solo puede crear el suyo y el
 * dominio responde 422 al resto. Los sujetos que se ofrecen salen de
 * `reglas.ts`, reflejo del §6.
 *
 * El sujeto se captura por id: el contrato no publica `GET /usuarios` y las
 * obras vienen del selector compartido. Para `sujeto_tipo=contratista` se usa
 * el catálogo (`GET /contratistas`).
 */

import { useState, type FormEvent } from 'react';

import { useCrearEvaluacionApiV1EvaluacionesPost } from '@/api/generado/evaluaciones/evaluaciones';
import { useListarContratistasApiV1ContratistasGet } from '@/api/generado/catalogos/catalogos';
import type { NivelEvaluacion, SujetoEvaluacion } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import { SelectorObra } from '@/lib/SelectorObra';
import {
  evaluacionCompleta,
  formularioEvaluacionVacio,
  peticionDeEvaluacion,
  periodoActual,
  type FormularioEvaluacion,
} from './formulario';
import { descripcionNivel, etiquetaNivel, etiquetaSujeto, sujetosDelNivel } from './reglas';

interface Props {
  readonly nivel: NivelEvaluacion;
  /** Id del usuario en sesión: sujeto por defecto de la autoevaluación (§11.3 H.1). */
  readonly usuarioId: string;
  readonly onCerrar: () => void;
  readonly onCreada: () => void;
}

export function AltaEvaluacion({ nivel, usuarioId, onCerrar, onCreada }: Props) {
  const [formulario, setFormulario] = useState<FormularioEvaluacion>(() =>
    formularioEvaluacionVacio(nivel, periodoActual()),
  );
  const [error, setError] = useState<string | null>(null);

  const contratistas = useListarContratistasApiV1ContratistasGet();

  const crear = useCrearEvaluacionApiV1EvaluacionesPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        onCreada();
      },
      onError: (err) => setError(err.message),
    },
  });

  function cambiar<K extends keyof FormularioEvaluacion>(
    campo: K,
    valor: FormularioEvaluacion[K],
  ) {
    setFormulario((previo) => ({ ...previo, [campo]: valor }));
  }

  /** Al cambiar de sujeto el id anterior deja de tener sentido. */
  function cambiarSujeto(sujetoTipo: SujetoEvaluacion) {
    setFormulario((previo) => ({
      ...previo,
      sujetoTipo,
      // El Residente se autoevalúa: su propio id es el default (§11.3 H.1).
      sujetoId: nivel === 'auto' && sujetoTipo === 'residente' ? usuarioId : '',
    }));
  }

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!evaluacionCompleta(formulario)) return;
    crear.mutate({ data: peticionDeEvaluacion(formulario) });
  }

  const sujetos = sujetosDelNivel(nivel);

  return (
    <Sheet
      titulo={`Nueva evaluación · ${etiquetaNivel(nivel)}`}
      subtitulo="POST /evaluaciones · §11.3 H"
      onCerrar={onCerrar}
    >
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          {error && <ErrorBanner mensaje={error} />}

          <div className="field__hint">{descripcionNivel(nivel)}</div>

          <div className="field">
            <label className="field__label" htmlFor="evaluacion-sujeto-tipo">
              Sujeto evaluado
            </label>
            <select
              id="evaluacion-sujeto-tipo"
              className="select"
              value={formulario.sujetoTipo}
              onChange={(e) => cambiarSujeto(e.target.value as SujetoEvaluacion)}
            >
              {sujetos.map((sujeto) => (
                <option key={sujeto} value={sujeto}>
                  {etiquetaSujeto(sujeto)}
                </option>
              ))}
            </select>
          </div>

          {formulario.sujetoTipo === 'obra' ? (
            <SelectorObra
              id="evaluacion-sujeto-obra"
              etiqueta="Obra evaluada"
              valor={formulario.sujetoId}
              onCambio={(obraId) =>
                setFormulario((previo) => ({ ...previo, sujetoId: obraId, obraId }))
              }
              requerido
            />
          ) : formulario.sujetoTipo === 'contratista' ? (
            <div className="field">
              <label className="field__label" htmlFor="evaluacion-sujeto-contratista">
                Contratista evaluado
              </label>
              <select
                id="evaluacion-sujeto-contratista"
                className="select"
                required
                value={formulario.sujetoId}
                onChange={(e) => cambiar('sujetoId', e.target.value)}
              >
                <option value="">Elige un contratista…</option>
                {(contratistas.data ?? []).map((contratista) => (
                  <option key={contratista.id} value={contratista.id}>
                    {contratista.clave} · {contratista.razon_social}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div className="field">
              <label className="field__label" htmlFor="evaluacion-sujeto-residente">
                Residente evaluado (id de usuario)
              </label>
              <input
                id="evaluacion-sujeto-residente"
                className="input input--mono"
                required
                placeholder="uuid del residente"
                value={formulario.sujetoId}
                onChange={(e) => cambiar('sujetoId', e.target.value)}
              />
              <div className="field__hint">
                {nivel === 'auto'
                  ? 'La autoevaluación es sobre uno mismo: el dominio rechaza (422) otro sujeto (§11.3 H.1).'
                  : 'El contrato no expone GET /usuarios; cuando exista, este campo debe volverse un selector.'}
              </div>
            </div>
          )}

          {formulario.sujetoTipo !== 'obra' && (
            <SelectorObra
              id="evaluacion-obra"
              etiqueta="Obra a la que pertenece (opcional)"
              valor={formulario.obraId}
              onCambio={(obraId) => cambiar('obraId', obraId)}
              vacio="Sin obra"
            />
          )}

          <div className="field">
            <label className="field__label" htmlFor="evaluacion-periodo">
              Periodo
            </label>
            <input
              id="evaluacion-periodo"
              className="input input--mono"
              required
              value={formulario.periodo}
              onChange={(e) => cambiar('periodo', e.target.value)}
              placeholder="2026-08"
            />
            <div className="field__hint">
              Formato <code>WWYY</code> (semana de obra, §3.1) o <code>YYYY-MM</code> (§7.8).
            </div>
          </div>
        </div>

        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button
            type="submit"
            className="btn btn--accent"
            disabled={crear.isPending || !evaluacionCompleta(formulario)}
          >
            {crear.isPending ? 'Creando…' : 'Crear evaluación'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
