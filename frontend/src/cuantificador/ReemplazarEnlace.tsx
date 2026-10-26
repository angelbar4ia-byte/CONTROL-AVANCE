/**
 * Reemplazar un enlace (`POST /enlaces-cuantificacion/{id}/reemplazar`,
 * MODELO.md §1b).
 *
 * El enlace anterior pasa a `vigente = false`: queda como evidencia, nunca se
 * borra ni se vuelve a sumar. Es una acción **explícita**: el sistema no
 * empareja medidas por cercanía, así que quien traza decide cuál medida
 * sustituye a cuál (típico: llega un DWG que mide mejor que el PDF).
 *
 * Dos salidas: dejar el enlace sin efecto, o sustituirlo por otro trazo del
 * mismo plano. El nodo (actividad) lo hereda el reemplazo; no se vuelve a elegir.
 */

import { useState, type FormEvent } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { useReemplazarEnlaceApiV1EnlacesCuantificacionEnlaceIdReemplazarPost } from '@/api/generado/cuantificacion/cuantificacion';
import type { EnlaceDeTrazoRespuesta, TrazoFeature } from '@/api/generado/modelo';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import { MEDIDAS_POR_HERRAMIENTA, herramientaDeGeometria, type MedidaDeTrazo } from './geometria';
import { etiquetaMedida } from './reglas';

const NOMBRE_FORMA = { poligono: 'Polígono', linea: 'Línea', punto: 'Punto' } as const;

interface Props {
  readonly enlace: EnlaceDeTrazoRespuesta;
  /** Los demás trazos del plano: candidatos a sustituir a este enlace. */
  readonly candidatos: readonly TrazoFeature[];
  readonly nombreDelNodo: string;
  readonly onCerrar: () => void;
  readonly onReemplazado: () => void;
}

export function ReemplazarEnlace({
  enlace,
  candidatos,
  nombreDelNodo,
  onCerrar,
  onReemplazado,
}: Props) {
  const [trazoId, setTrazoId] = useState('');
  const [medida, setMedida] = useState<MedidaDeTrazo | ''>('');
  const [factor, setFactor] = useState('1');
  const [error, setError] = useState<string | null>(null);
  const reemplazar = useReemplazarEnlaceApiV1EnlacesCuantificacionEnlaceIdReemplazarPost<ErrorApi>();

  const elegido = candidatos.find((t) => t.id === trazoId);
  const forma = elegido ? herramientaDeGeometria(elegido.geometry) : null;
  const medidas = forma ? MEDIDAS_POR_HERRAMIENTA[forma] : [];

  async function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    setError(null);
    if (trazoId !== '') {
      const n = Number(factor);
      if (medida === '' || !(n > 0)) {
        setError('Elige la medida y un factor mayor que cero.');
        return;
      }
      if (medida === 'conteo' && !Number.isInteger(n)) {
        setError('Un enlace de conteo lleva un factor entero: ya cuenta instancias.');
        return;
      }
    }
    try {
      await reemplazar.mutateAsync({
        enlaceId: enlace.enlace_id,
        data: trazoId === '' ? {} : { nuevo: { trazo_id: trazoId, medida: medida as MedidaDeTrazo, factor } },
      });
      onReemplazado();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo reemplazar el enlace.');
    }
  }

  return (
    <Sheet
      titulo="Reemplazar enlace"
      subtitulo="POST /enlaces-cuantificacion/{id}/reemplazar · MODELO §1b"
      onCerrar={onCerrar}
    >
      <form onSubmit={(e) => void alEnviar(e)}>
        <div className="sheet__body col gap-12">
          {error && <ErrorBanner mensaje={error} />}
          <div className="text-sm">
            Hoy: <strong>{etiquetaMedida(enlace.medida)}</strong> × {enlace.factor} sobre{' '}
            <strong>{nombreDelNodo}</strong>. Pasará a no vigente: queda como evidencia y deja de
            sumar.
          </div>
          <div className="field">
            <label className="field__label" htmlFor="reemplazo-trazo">
              Sustituir por
            </label>
            <select
              id="reemplazo-trazo"
              className="select"
              value={trazoId}
              onChange={(e) => {
                setTrazoId(e.target.value);
                setMedida('');
              }}
            >
              <option value="">Nada: dejarlo sin efecto</option>
              {candidatos.map((t, i) => {
                const f = herramientaDeGeometria(t.geometry);
                return (
                  <option key={t.id} value={t.id}>
                    Trazo {i + 1} · {f ? NOMBRE_FORMA[f] : 'Forma'} · {t.properties.fuente.toUpperCase()}
                    {t.properties.capa ? ` · ${t.properties.capa}` : ''}
                  </option>
                );
              })}
            </select>
          </div>
          {trazoId !== '' && (
            <div className="row">
              <div className="field" style={{ flex: 1 }}>
                <label className="field__label" htmlFor="reemplazo-medida">
                  Medida
                </label>
                <select
                  id="reemplazo-medida"
                  className="select"
                  value={medida}
                  onChange={(e) => setMedida(e.target.value as MedidaDeTrazo)}
                >
                  <option value="">Elige…</option>
                  {medidas.map((m) => (
                    <option key={m} value={m}>
                      {etiquetaMedida(m)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label className="field__label" htmlFor="reemplazo-factor">
                  Factor
                </label>
                <input
                  id="reemplazo-factor"
                  className="input"
                  inputMode="decimal"
                  value={factor}
                  onChange={(e) => setFactor(e.target.value)}
                />
              </div>
            </div>
          )}
        </div>
        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={reemplazar.isPending}>
            {reemplazar.isPending ? 'Reemplazando…' : trazoId === '' ? 'Dejar sin efecto' : 'Reemplazar'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
