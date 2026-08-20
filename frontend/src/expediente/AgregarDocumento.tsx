/**
 * Agregar un documento al expediente (§7.9, §11.2).
 *
 * EL ARCHIVO NO VIAJA POR LA API
 *
 * Dos pasos: `POST /evidencias/presigned` devuelve una URL firmada, el
 * navegador sube **directo a R2** y solo entonces `POST /obras/{id}/expediente`
 * registra la clave. Un plano de obra pesa decenas de megas; hacerlo pasar por
 * el proceso de FastAPI lo tendría ocupado el tiempo entero de la subida y
 * gastaría el ancho de banda dos veces (§12.2, §12.5).
 *
 * La URL firmada es un HMAC con caducidad, no una credencial: el navegador
 * nunca ve las llaves de R2.
 *
 * Si algo falla **después** de subir a R2 queda un objeto sin fila que lo
 * referencie. Se prefiere a lo contrario —una fila apuntando a un archivo que
 * no existe, que rompería el expediente al abrirlo— y el objeto huérfano no le
 * estorba a nadie: nada lo lista.
 */

import { useState, type FormEvent } from 'react';

import { useFirmarEvidenciaApiV1EvidenciasPresignedPost } from '@/api/generado/evidencias/evidencias';
import { useAgregarDocumentoApiV1ObrasObraIdExpedientePost } from '@/api/generado/expediente/expediente';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import { TIPOS_DOC, etiquetaTipoDoc } from './reglas';

interface Props {
  readonly obraId: string;
  readonly onCerrar: () => void;
  readonly onAgregado: () => void;
}

export function AgregarDocumento({ obraId, onCerrar, onAgregado }: Props) {
  const [tipo, setTipo] = useState<string>('plano');
  const [nombre, setNombre] = useState('');
  const [archivo, setArchivo] = useState<File | null>(null);
  const [paso, setPaso] = useState<'inactivo' | 'subiendo' | 'registrando'>('inactivo');
  const [error, setError] = useState<string | null>(null);

  const firmar = useFirmarEvidenciaApiV1EvidenciasPresignedPost<ErrorApi>();
  const registrar = useAgregarDocumentoApiV1ObrasObraIdExpedientePost<ErrorApi>();

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
        },
      });

      // `fetch` a pelo y no `peticion`: esta petición va a R2, no a la API.
      // Mandarle el `Authorization` de Supabase rompería la firma —el HMAC
      // cubre las cabeceras— además de filtrar el token a otro dominio.
      const subida = await fetch(firma.url, {
        method: firma.metodo,
        headers: { 'Content-Type': firma.content_type },
        body: archivo,
      });
      if (!subida.ok) {
        throw new Error(
          `El almacenamiento rechazó la subida (HTTP ${subida.status}).`,
        );
      }

      setPaso('registrando');
      await registrar.mutateAsync({
        obraId,
        data: {
          tipo: tipo as never,
          nombre: nombre.trim() || archivo.name,
          url: firma.clave,
        },
      });

      onAgregado();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo agregar el documento.');
    } finally {
      setPaso('inactivo');
    }
  }

  const trabajando = paso !== 'inactivo';

  return (
    <Sheet
      titulo="Agregar documento al expediente"
      subtitulo="POST /obras/{id}/expediente · §7.9"
      onCerrar={onCerrar}
    >
      <form onSubmit={(e) => void alEnviar(e)}>
        <div className="sheet__body col gap-12">
          {error && <ErrorBanner mensaje={error} />}

          <div className="field">
            <label className="field__label" htmlFor="doc-tipo">
              Tipo
            </label>
            <select
              id="doc-tipo"
              className="select"
              value={tipo}
              onChange={(e) => setTipo(e.target.value)}
            >
              {TIPOS_DOC.map((t) => (
                <option key={t} value={t}>
                  {etiquetaTipoDoc(t)}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="doc-archivo">
              Archivo
            </label>
            <input
              id="doc-archivo"
              className="input"
              type="file"
              onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
              required
            />
            <div className="field__hint">
              Se sube directo al almacenamiento; no pasa por la API.
            </div>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="doc-nombre">
              Nombre legible <span className="text-mute">(opcional)</span>
            </label>
            <input
              id="doc-nombre"
              className="input"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder={archivo?.name ?? 'Como quieras verlo en la lista'}
            />
          </div>

          {paso === 'subiendo' && (
            <div className="badge badge--info">Subiendo el archivo…</div>
          )}
          {paso === 'registrando' && (
            <div className="badge badge--info">Registrándolo en el expediente…</div>
          )}
        </div>

        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar} disabled={trabajando}>
            Cancelar
          </button>
          <button
            type="submit"
            className="btn btn--primary"
            disabled={trabajando || archivo === null}
          >
            {trabajando ? 'Trabajando…' : 'Agregar'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
