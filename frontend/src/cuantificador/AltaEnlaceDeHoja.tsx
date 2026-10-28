/**
 * Enlace entre hojas: la zona que se marcó con dos clics lleva a otra hoja de la obra («ver plano X»).
 * Se elige la hoja de destino y se le pone una etiqueta; con eso queda guardado. Nunca produce cantidad.
 */

import { useState, type FormEvent } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { useCrearEnlaceDeHojaApiV1PlanosPlanoIdEnlacesPost } from '@/api/generado/enlaces-de-hoja/enlaces-de-hoja';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import type { Punto } from './geometria';

interface HojaDeLaObra {
  readonly id: string;
  readonly nombre: string;
  readonly version: number;
}

interface Props {
  readonly planoId: string;
  readonly puntoA: Punto;
  readonly puntoB: Punto;
  /** Las demás hojas de la obra: a cualquiera se puede saltar. */
  readonly destinos: readonly HojaDeLaObra[];
  readonly onCerrar: () => void;
  readonly onCreado: (etiqueta: string) => void;
}

export function AltaEnlaceDeHoja({ planoId, puntoA, puntoB, destinos, onCerrar, onCreado }: Props) {
  const [destinoId, setDestinoId] = useState(destinos[0]?.id ?? '');
  const [etiqueta, setEtiqueta] = useState('');
  const [error, setError] = useState<string | null>(null);
  const crear = useCrearEnlaceDeHojaApiV1PlanosPlanoIdEnlacesPost<ErrorApi>();

  const x = Math.min(puntoA[0], puntoB[0]);
  const y = Math.min(puntoA[1], puntoB[1]);
  const ancho = Math.abs(puntoA[0] - puntoB[0]);
  const alto = Math.abs(puntoA[1] - puntoB[1]);
  const valido = destinoId !== '' && etiqueta.trim() !== '' && ancho > 0 && alto > 0;

  async function alEnviar(e: FormEvent) {
    e.preventDefault();
    if (!valido) return;
    setError(null);
    try {
      await crear.mutateAsync({
        planoId,
        data: { destino_plano_id: destinoId, etiqueta: etiqueta.trim(), x, y, ancho, alto },
      });
      onCreado(etiqueta.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar el enlace.');
    }
  }

  return (
    <Sheet titulo="Enlace a otra hoja" subtitulo="Una zona del plano que lleva a otra hoja" onCerrar={onCerrar}>
      <form onSubmit={(e) => void alEnviar(e)}>
        <div className="sheet__body col gap-12">
          {error && <ErrorBanner mensaje={error} />}
          {destinos.length === 0 ? (
            <p className="text-sm">Esta obra no tiene otra hoja a la que enlazar: sube primero el plano de destino.</p>
          ) : (
            <>
              <div className="field">
                <label className="field__label" htmlFor="enlace-destino">
                  Lleva a la hoja
                </label>
                <select
                  id="enlace-destino"
                  className="select"
                  value={destinoId}
                  onChange={(e) => setDestinoId(e.target.value)}
                >
                  {destinos.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.nombre} · v{d.version}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label className="field__label" htmlFor="enlace-etiqueta">
                  Etiqueta
                </label>
                <input
                  id="enlace-etiqueta"
                  className="input"
                  autoFocus
                  placeholder="Ver corte A-A"
                  value={etiqueta}
                  onChange={(e) => setEtiqueta(e.target.value)}
                />
              </div>
            </>
          )}
        </div>
        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={!valido || crear.isPending}>
            {crear.isPending ? 'Guardando…' : 'Crear enlace'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
