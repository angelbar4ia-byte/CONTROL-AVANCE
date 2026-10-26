/**
 * Anotar el plano (`POST /planos/{id}/notas`, MODELO.md §1b).
 *
 * Una nota marca un lugar y dice algo; **nunca produce cantidad**. Si algún día
 * una nota necesita sumar, se convierte en trazo, no se amplía esta entidad.
 * Solo Residente y Supervisor anotan (el servidor lo impone con 403).
 */

import { useState, type FormEvent } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { useRegistrarNotaPlanoApiV1PlanosPlanoIdNotasPost } from '@/api/generado/cuantificacion/cuantificacion';
import type { ActividadRespuesta } from '@/api/generado/modelo';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import type { Punto } from './geometria';

interface Props {
  readonly planoId: string;
  readonly versionPlano: number;
  readonly punto: Punto;
  readonly actividades: readonly ActividadRespuesta[];
  readonly onCerrar: () => void;
  readonly onGuardada: () => void;
}

export function AltaNota({ planoId, versionPlano, punto, actividades, onCerrar, onGuardada }: Props) {
  const [texto, setTexto] = useState('');
  const [actividadId, setActividadId] = useState('');
  const [error, setError] = useState<string | null>(null);
  const registrar = useRegistrarNotaPlanoApiV1PlanosPlanoIdNotasPost<ErrorApi>();

  async function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    setError(null);
    try {
      await registrar.mutateAsync({
        planoId,
        data: {
          version_plano: versionPlano,
          ubicacion_wkt: `POINT(${punto[0]} ${punto[1]})`,
          texto: texto.trim(),
          actividad_id: actividadId === '' ? null : actividadId,
        },
      });
      onGuardada();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar la nota.');
    }
  }

  return (
    <Sheet titulo="Anotar el plano" subtitulo="POST /planos/{id}/notas · MODELO §1b" onCerrar={onCerrar}>
      <form onSubmit={(e) => void alEnviar(e)}>
        <div className="sheet__body col gap-12">
          {error && <ErrorBanner mensaje={error} />}
          <div className="field">
            <label className="field__label" htmlFor="nota-texto">
              Nota
            </label>
            <textarea
              id="nota-texto"
              className="input"
              rows={4}
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              required
            />
            <div className="field__hint">Una nota no suma cantidad a ninguna actividad.</div>
          </div>
          <div className="field">
            <label className="field__label" htmlFor="nota-actividad">
              Sobre la actividad <span className="text-mute">(opcional)</span>
            </label>
            <select
              id="nota-actividad"
              className="select"
              value={actividadId}
              onChange={(e) => setActividadId(e.target.value)}
            >
              <option value="">Solo un lugar del plano</option>
              {actividades.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.concepto_clave ?? a.descripcion ?? 'Actividad'}
                  {a.nivel_clave ? ` — ${a.nivel_clave}` : ''}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button
            type="submit"
            className="btn btn--primary"
            disabled={registrar.isPending || texto.trim() === ''}
          >
            {registrar.isPending ? 'Guardando…' : 'Guardar nota'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
