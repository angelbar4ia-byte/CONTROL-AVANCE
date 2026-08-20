/**
 * Revisión física — fotos, comentario y calidad (§7.8, §11.2).
 *
 * El endpoint existe desde la Fase 4 y **ninguna pantalla lo usaba**. El §11.2
 * la marca como «móvil · Control de obra», y el móvil es la Fase 15: mientras
 * tanto, esta es la única manera de registrar una revisión, y sin ella el
 * expediente técnico llega al cierre de obra sin evidencia de calidad (§11.3 D).
 *
 * ## Las fotos no viajan por la API
 *
 * Mismo camino que el expediente: presigned URL, subida directa a R2 y solo
 * entonces se manda la clave (§12.2). Aquí importa más que en ningún otro lado
 * —una revisión trae varias fotos de obra, de varios megas cada una— y por eso
 * se suben **en paralelo**: hacerlo en serie multiplicaría la espera por el
 * número de fotos.
 */

import { useState, type FormEvent } from 'react';

import { useFirmarEvidenciaApiV1EvidenciasPresignedPost } from '@/api/generado/evidencias/evidencias';
import {
  useListarRevisionesApiV1RevisionesGet,
  useRegistrarRevisionApiV1ObrasObraIdRevisionesPost,
} from '@/api/generado/revisiones/revisiones';
import type { RevisionRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { SelectorObra } from '@/lib/SelectorObra';
import { fmtFecha } from '@/lib/formato';
import {
  CALIDAD_MAXIMA,
  CALIDAD_MINIMA,
  etiquetaCalidad,
  puedeRegistrarRevision,
  tonoCalidad,
} from './reglas';

export default function Revisiones() {
  const { sesion } = useSesion();
  const [obraId, setObraId] = useState('');
  const [comentario, setComentario] = useState('');
  const [calidad, setCalidad] = useState<string>('');
  const [fotos, setFotos] = useState<File[]>([]);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const consulta = useListarRevisionesApiV1RevisionesGet<RevisionRespuesta[], ErrorApi>(
    obraId === '' ? undefined : { obra_id: obraId },
  );

  const firmar = useFirmarEvidenciaApiV1EvidenciasPresignedPost<ErrorApi>();
  const registrar = useRegistrarRevisionApiV1ObrasObraIdRevisionesPost<ErrorApi>();

  if (!sesion) return null;

  const puedeRegistrar = puedeRegistrarRevision(sesion.rol);

  async function subirFoto(foto: File): Promise<string> {
    const firma = await firmar.mutateAsync({
      data: {
        nombre_archivo: foto.name,
        content_type: foto.type || 'application/octet-stream',
      },
    });
    // `fetch` a pelo: va a R2, no a la API. Mandarle el Bearer de Supabase
    // rompería la firma —el HMAC cubre las cabeceras— y filtraría el token.
    const subida = await fetch(firma.url, {
      method: firma.metodo,
      headers: { 'Content-Type': firma.content_type },
      body: foto,
    });
    if (!subida.ok) {
      throw new Error(`El almacenamiento rechazó "${foto.name}" (HTTP ${subida.status}).`);
    }
    return firma.clave;
  }

  async function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (obraId === '') return;
    setError(null);
    setSubiendo(true);
    try {
      // En paralelo: una revisión trae varias fotos y en serie la espera se
      // multiplica por su número.
      const claves = await Promise.all(fotos.map(subirFoto));

      await registrar.mutateAsync({
        obraId,
        data: {
          fotos: claves,
          comentario: comentario.trim() || null,
          calidad: calidad === '' ? null : Number(calidad),
        },
      });

      setComentario('');
      setCalidad('');
      setFotos([]);
      void consulta.refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo registrar la revisión.');
    } finally {
      setSubiendo(false);
    }
  }

  const revisiones = consulta.data ?? [];

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Control de obra</div>
          <h1 className="page__title">Revisión física</h1>
          <div className="page__subtitle">
            Fotos, comentario y calidad de lo ejecutado (§7.8). Es la evidencia
            que sostiene el cierre de obra (§11.3 D).
          </div>
        </div>
      </div>

      {error && <ErrorBanner mensaje={error} />}

      <div className="filterbar">
        <SelectorObra
          id="revision-obra"
          etiqueta="Obra"
          valor={obraId}
          onCambio={setObraId}
          vacio="Todas las obras"
        />
      </div>

      {puedeRegistrar && obraId !== '' && (
        <form onSubmit={(e) => void alEnviar(e)} className="card mb-8">
          <div className="card__header">
            <h2 className="card__title">Registrar una revisión</h2>
          </div>
          <div className="card__body col gap-12">
            <div className="field">
              <label className="field__label" htmlFor="revision-fotos">
                Fotos
              </label>
              <input
                id="revision-fotos"
                className="input"
                type="file"
                accept="image/*"
                multiple
                onChange={(e) => setFotos(Array.from(e.target.files ?? []))}
              />
              <div className="field__hint">
                Se suben directo al almacenamiento; no pasan por la API.
                {fotos.length > 0 && ` ${fotos.length} seleccionada(s).`}
              </div>
            </div>

            <div className="field">
              <label className="field__label" htmlFor="revision-comentario">
                Comentario
              </label>
              <textarea
                id="revision-comentario"
                className="input"
                rows={3}
                value={comentario}
                onChange={(e) => setComentario(e.target.value)}
                placeholder="Qué se revisó y qué se encontró"
              />
            </div>

            <div className="field" style={{ maxWidth: 220 }}>
              <label className="field__label" htmlFor="revision-calidad">
                Calidad <span className="text-mute">(opcional)</span>
              </label>
              <select
                id="revision-calidad"
                className="select"
                value={calidad}
                onChange={(e) => setCalidad(e.target.value)}
              >
                <option value="">Sin calificar</option>
                {Array.from(
                  { length: CALIDAD_MAXIMA - CALIDAD_MINIMA + 1 },
                  (_, i) => CALIDAD_MINIMA + i,
                ).map((valor) => (
                  <option key={valor} value={valor}>
                    {valor} · {etiquetaCalidad(valor)}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="card__body" style={{ paddingTop: 0 }}>
            <button
              type="submit"
              className="btn btn--primary"
              disabled={subiendo || (fotos.length === 0 && comentario.trim() === '')}
            >
              {subiendo ? 'Registrando…' : 'Registrar revisión'}
            </button>
            <div className="field__hint" style={{ marginTop: 6 }}>
              Una revisión sin foto ni comentario no documenta nada.
            </div>
          </div>
        </form>
      )}

      {!puedeRegistrar && (
        <div className="field__hint mb-8">
          La revisión física la registra Control de obra (§11.2). Aquí puedes ver
          las que ya se hicieron en tus obras.
        </div>
      )}

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Obra</th>
                <th>Calidad</th>
                <th className="is-num">Fotos</th>
                <th>Comentario</th>
              </tr>
            </thead>
            <tbody>
              {consulta.isLoading ? (
                <tr>
                  <td colSpan={5}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : revisiones.length === 0 ? (
                <tr>
                  <td colSpan={5}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Sin revisiones registradas.
                    </div>
                  </td>
                </tr>
              ) : (
                revisiones.map((revision) => (
                  <tr key={revision.id}>
                    <td className="mono">{fmtFecha(revision.fecha)}</td>
                    <td className="is-key">{revision.obra_id.slice(0, 8)}</td>
                    <td>
                      {revision.calidad === null || revision.calidad === undefined ? (
                        <span className="text-mute">—</span>
                      ) : (
                        <span className={`badge badge--${tonoCalidad(revision.calidad)}`}>
                          {revision.calidad} · {etiquetaCalidad(revision.calidad)}
                        </span>
                      )}
                    </td>
                    <td className="is-num mono">{revision.fotos.length}</td>
                    <td className="text-sm">{revision.comentario ?? '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
