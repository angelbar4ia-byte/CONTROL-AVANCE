/**
 * Dar de alta un plano (`POST /obras/{id}/planos`).
 *
 * Mismo camino que el expediente: firma → `PUT` directo a R2 → registro de la
 * clave. El archivo no pasa por la API (§12.2). Ver `AgregarDocumento` para el
 * razonamiento de cada paso; aquí solo cambia el destino del registro.
 *
 * Solo las **imágenes** (PNG, JPG, WebP) se ven de fondo en el visor. Un PDF se
 * puede registrar, pero el visor aún no sabe pintarlo: se traza sobre una
 * rejilla en blanco y el aviso lo dice, en vez de fingir que el plano cargó.
 */

import { useState, type FormEvent } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { useRegistrarPlanoApiV1ObrasObraIdPlanosPost } from '@/api/generado/cuantificacion/cuantificacion';
import { useFirmarEvidenciaApiV1EvidenciasPresignedPost } from '@/api/generado/evidencias/evidencias';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';

interface Props {
  readonly obraId: string;
  readonly onCerrar: () => void;
  readonly onRegistrado: (planoId: string) => void;
}

export function AltaPlano({ obraId, onCerrar, onRegistrado }: Props) {
  const [nombre, setNombre] = useState('');
  const [archivo, setArchivo] = useState<File | null>(null);
  const [paso, setPaso] = useState<'inactivo' | 'subiendo' | 'registrando'>('inactivo');
  const [error, setError] = useState<string | null>(null);

  const firmar = useFirmarEvidenciaApiV1EvidenciasPresignedPost<ErrorApi>();
  const registrar = useRegistrarPlanoApiV1ObrasObraIdPlanosPost<ErrorApi>();

  async function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (archivo === null) return;
    setError(null);

    try {
      setPaso('subiendo');
      const firma = await firmar.mutateAsync({
        data: {
          nombre_archivo: archivo.name,
          content_type: archivo.type || 'application/octet-stream',
          obra_id: obraId,
        },
      });
      // `fetch` a pelo: va a R2, no a la API; el `Authorization` de Supabase
      // rompería la firma y filtraría el token.
      const subida = await fetch(firma.url, {
        method: firma.metodo,
        headers: { 'Content-Type': firma.content_type },
        body: archivo,
      });
      if (!subida.ok) {
        throw new Error(`El almacenamiento rechazó la subida (HTTP ${subida.status}).`);
      }

      setPaso('registrando');
      const plano = await registrar.mutateAsync({
        obraId,
        data: { nombre: nombre.trim() || archivo.name, archivo_url: firma.clave },
      });
      onRegistrado(plano.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo registrar el plano.');
    } finally {
      setPaso('inactivo');
    }
  }

  const esPdf = archivo !== null && /pdf/i.test(archivo.type || archivo.name);

  return (
    <Sheet titulo="Subir un plano" subtitulo="POST /obras/{id}/planos · MODELO §1b" onCerrar={onCerrar}>
      <form onSubmit={(e) => void alEnviar(e)}>
        <div className="sheet__body col gap-12">
          {error && <ErrorBanner mensaje={error} />}

          <div className="field">
            <label className="field__label" htmlFor="plano-archivo">
              Archivo
            </label>
            <input
              id="plano-archivo"
              className="input"
              type="file"
              accept="image/png,image/jpeg,image/webp,application/pdf"
              onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
              required
            />
            <div className="field__hint">
              Se sube directo al almacenamiento; no pasa por la API. Las coordenadas del plano
              son las de la imagen, en píxeles.
            </div>
            {esPdf && (
              <div className="field__hint">
                El visor todavía no pinta PDF: podrás trazar, pero sobre una rejilla en blanco.
              </div>
            )}
          </div>

          <div className="field">
            <label className="field__label" htmlFor="plano-nombre">
              Nombre <span className="text-mute">(opcional)</span>
            </label>
            <input
              id="plano-nombre"
              className="input"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder={archivo?.name ?? 'Planta baja'}
            />
          </div>
        </div>
        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button
            type="submit"
            className="btn btn--primary"
            disabled={paso !== 'inactivo' || archivo === null}
          >
            {paso === 'subiendo' ? 'Subiendo…' : paso === 'registrando' ? 'Registrando…' : 'Subir plano'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
