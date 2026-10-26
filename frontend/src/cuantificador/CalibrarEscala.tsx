/**
 * Calibrar la escala del plano (`PUT /planos/{id}/escala`, migración 0069).
 *
 * El visor mide en coordenadas de plano —píxeles de la imagen—, no en metros. Para
 * que la cantidad medida se pueda comparar con la del presupuesto, se marcan dos
 * puntos de una distancia que se conoce (una cota, un eje) y se dice cuántos
 * metros son. De ahí sale la escala; el servidor la aplica al leer la medida de
 * **todos** los trazos del plano y recalcula lo que alimentan. Se puede repetir:
 * la última calibración manda.
 */

import { useState, type FormEvent } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { useCalibrarEscalaApiV1PlanosPlanoIdEscalaPut } from '@/api/generado/cuantificacion/cuantificacion';
import type { EscalaRespuesta } from '@/api/generado/modelo';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtNum } from '@/lib/formato';
import { Sheet } from '@/lib/Sheet';
import { distanciaEntre, escalaPrevista, type Punto } from './geometria';

interface Props {
  readonly planoId: string;
  readonly puntoA: Punto;
  readonly puntoB: Punto;
  /** La escala que ya tenía el plano, si se está recalibrando. */
  readonly escalaActual: number | null;
  readonly onCerrar: () => void;
  readonly onCalibrada: (respuesta: EscalaRespuesta) => void;
}

export function CalibrarEscala({
  planoId,
  puntoA,
  puntoB,
  escalaActual,
  onCerrar,
  onCalibrada,
}: Props) {
  const [metros, setMetros] = useState('');
  const [error, setError] = useState<string | null>(null);
  const calibrar = useCalibrarEscalaApiV1PlanosPlanoIdEscalaPut<ErrorApi>();

  const enPlano = distanciaEntre(puntoA, puntoB);
  const previa = escalaPrevista(puntoA, puntoB, Number(metros));

  async function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (previa === null) return;
    setError(null);
    try {
      const respuesta = await calibrar.mutateAsync({
        planoId,
        data: {
          punto_a: [puntoA[0], puntoA[1]],
          punto_b: [puntoB[0], puntoB[1]],
          distancia_m: metros.trim(),
        },
      });
      onCalibrada(respuesta);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo calibrar la escala.');
    }
  }

  return (
    <Sheet
      titulo="Calibrar la escala"
      subtitulo="PUT /planos/{id}/escala · migración 0069"
      onCerrar={onCerrar}
    >
      <form onSubmit={(e) => void alEnviar(e)}>
        <div className="sheet__body col gap-12">
          {error && <ErrorBanner mensaje={error} />}
          <p className="text-sm">
            Marcaste dos puntos que están a <strong>{fmtNum(enPlano)}</strong> unidades de plano.
            ¿Cuántos metros hay entre ellos en la realidad?
          </p>
          <div className="field">
            <label className="field__label" htmlFor="escala-metros">
              Distancia real (m)
            </label>
            <input
              id="escala-metros"
              className="input input--mono"
              type="number"
              step="any"
              min="0"
              autoFocus
              value={metros}
              onChange={(e) => setMetros(e.target.value)}
            />
            <span className="field__hint">
              {previa === null
                ? 'Usa una cota o un eje del plano de distancia conocida.'
                : `Escala: 1 unidad de plano = ${previa.toPrecision(4)} m.`}
            </span>
          </div>
          {escalaActual !== null && (
            <div className="text-mute text-xs">
              Este plano ya estaba calibrado (1 unidad = {escalaActual} m). Calibrar de nuevo
              reemplaza esa escala y recalcula todas las cantidades medidas en él.
            </div>
          )}
          <div className="text-mute text-xs">
            La escala se aplica a todos los trazos del plano, los ya hechos y los que vengan: el
            área escala con el cuadrado, los largos con la escala y el conteo no cambia.
          </div>
        </div>
        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button
            type="submit"
            className="btn btn--primary"
            disabled={previa === null || calibrar.isPending}
          >
            {calibrar.isPending ? 'Calibrando…' : 'Calibrar escala'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
