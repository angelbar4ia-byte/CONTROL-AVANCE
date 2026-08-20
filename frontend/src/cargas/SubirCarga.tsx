/**
 * Subir un archivo de carga — `POST /cargas` (§10.2, §11.3 workflow G).
 *
 * DOS PASOS, NO UNO: VISTA PREVIA Y APLICAR
 *
 * El §10.2 pide vista previa, y aquí es literal: la primera subida va con
 * `dry_run` y no escribe nada; la segunda —el mismo archivo, ya visto el
 * reporte— aplica. El hash del archivo garantiza que sea el mismo (§10.8).
 *
 * Es más trabajo que un botón único y es el punto: una carga de catálogo
 * cambia miles de precios, y nadie debería poder hacerlo sin ver antes cuántas
 * filas van a insertarse, cuántas a actualizarse y qué renglones vienen mal.
 *
 * El reporte de errores es **por fila**: número, columna, valor y motivo
 * (§9.3). Un "el archivo tiene errores" sin decir dónde obliga a revisar diez
 * mil renglones a mano.
 */

import { useMemo, useState, type FormEvent } from 'react';

import { useSubirCargaApiV1CargasPost } from '@/api/generado/cargas/cargas';
import { ModoCarga, TipoCarga, type CargaRespuesta } from '@/api/generado/modelo';
import { claveDeIdempotencia, type ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import {
  MODOS,
  TIPOS,
  descripcionModo,
  etiquetaModo,
  etiquetaTipo,
  modoDestructivo,
} from './reglas';

interface Props {
  readonly onCerrar: () => void;
  readonly onAplicada: () => void;
}

export function SubirCarga({ onCerrar, onAplicada }: Props) {
  const [tipo, setTipo] = useState<TipoCarga>(TipoCarga.catalogo_conceptos);
  const [modo, setModo] = useState<ModoCarga>(ModoCarga.actualizar);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [previa, setPrevia] = useState<CargaRespuesta | null>(null);
  const [error, setError] = useState<string | null>(null);

  // La clave protege el **aplicar**, no la vista previa: la previa no escribe
  // nada y repetirla es inofensivo. Se genera al montar y se reusa, que es lo
  // que la vuelve útil ante un doble clic (regla 1 del ROADMAP).
  const clave = useMemo(claveDeIdempotencia, []);

  const subir = useSubirCargaApiV1CargasPost<ErrorApi>({
    mutation: {
      onError: (err) => setError(err.message),
    },
    request: { headers: { 'Idempotency-Key': clave } },
  });

  function enviar(dryRun: boolean) {
    if (archivo === null) return;
    setError(null);
    subir.mutate(
      {
        data: {
          // El contrato tipa `archivo` como `string`: FastAPI emite un
          // `UploadFile` como `type: string · contentMediaType`, y Orval lo
          // traduce literal. Lo que el `FormData` necesita es el `File`, así
          // que el cast corrige el artefacto del generador — no una decisión
          // de esta pantalla.
          archivo: archivo as unknown as string,
          tipo,
          modo,
          dry_run: dryRun,
        },
      },
      {
        onSuccess: (resultado) => {
          if (dryRun) {
            setPrevia(resultado);
          } else {
            onAplicada();
          }
        },
      },
    );
  }

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    enviar(true);
  }

  /** Cambiar de archivo o de modo invalida la previa que se veía. */
  function reiniciarPrevia() {
    setPrevia(null);
  }

  const hayErrores = (previa?.errores.length ?? 0) > 0;

  return (
    <Sheet
      titulo="Subir archivo de carga"
      subtitulo="POST /cargas · §10.2"
      onCerrar={onCerrar}
    >
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          {error && <ErrorBanner mensaje={error} />}

          <div className="field">
            <label className="field__label" htmlFor="carga-tipo">
              Tipo de carga
            </label>
            <select
              id="carga-tipo"
              className="select"
              value={tipo}
              onChange={(e) => {
                setTipo(e.target.value as TipoCarga);
                reiniciarPrevia();
              }}
            >
              {TIPOS.map((t) => (
                <option key={t} value={t}>
                  {etiquetaTipo(t)}
                </option>
              ))}
            </select>
            <div className="field__hint">
              Cada tipo espera las cabeceras de su plantilla (§10.6). Descárgala
              desde la bandeja si no la tienes.
            </div>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="carga-modo">
              Modo
            </label>
            <select
              id="carga-modo"
              className="select"
              value={modo}
              onChange={(e) => {
                setModo(e.target.value as ModoCarga);
                reiniciarPrevia();
              }}
            >
              {MODOS.map((m) => (
                <option key={m} value={m}>
                  {etiquetaModo(m)}
                </option>
              ))}
            </select>
            <div className="field__hint">{descripcionModo(modo)}</div>
            {modoDestructivo(modo) && (
              <div className="badge badge--warn" style={{ marginTop: 6 }}>
                Lo que no venga en el archivo deja de estar vigente.
              </div>
            )}
          </div>

          <div className="field">
            <label className="field__label" htmlFor="carga-archivo">
              Archivo .xlsx
            </label>
            <input
              id="carga-archivo"
              className="input"
              type="file"
              accept=".xlsx"
              onChange={(e) => {
                setArchivo(e.target.files?.[0] ?? null);
                reiniciarPrevia();
              }}
              required
            />
          </div>

          {previa && <ReportePrevia previa={previa} />}
        </div>

        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          {previa === null ? (
            <button
              type="submit"
              className="btn btn--primary"
              disabled={subir.isPending || archivo === null}
            >
              {subir.isPending ? 'Revisando…' : 'Ver qué haría'}
            </button>
          ) : (
            <button
              type="button"
              className="btn btn--primary"
              // Con errores no se aplica: el backend los rechazaría fila por
              // fila y el operador tiene que corregir el archivo primero.
              disabled={subir.isPending || hayErrores}
              onClick={() => enviar(false)}
            >
              {subir.isPending ? 'Aplicando…' : 'Aplicar'}
            </button>
          )}
        </div>
      </form>
    </Sheet>
  );
}

function ReportePrevia({ previa }: { readonly previa: CargaRespuesta }) {
  const hayErrores = previa.errores.length > 0;

  return (
    <div className="card">
      <div className="card__header">
        <h3 className="card__title">Vista previa</h3>
      </div>
      <div className="card__body col gap-8">
        <div className="row gap-12">
          <Dato etiqueta="Filas" valor={previa.filas} />
          <Dato etiqueta="Insertaría" valor={previa.insertados} />
          <Dato etiqueta="Actualizaría" valor={previa.actualizados} />
          <Dato etiqueta="Omitiría" valor={previa.omitidos} />
        </div>

        {previa.pendientes > 0 && (
          <div className="badge badge--info">
            {previa.pendientes} pendiente(s) esperarán confirmación en la bandeja
            (§10.3).
          </div>
        )}

        {previa.reutilizada && (
          <div className="badge badge--info">
            Este archivo ya se había aplicado idéntico: no se creará versión
            nueva (§10.8).
          </div>
        )}

        {hayErrores ? (
          <>
            <div className="badge badge--danger">
              {previa.errores.length} fila(s) con error. Corrige el archivo y
              vuelve a subirlo.
            </div>
            <div className="table-scroll" style={{ maxHeight: 260 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th className="is-num">Fila</th>
                    <th>Columna</th>
                    <th>Valor</th>
                    <th>Motivo</th>
                  </tr>
                </thead>
                <tbody>
                  {previa.errores.map((error, indice) => (
                    <tr key={`${error.fila}-${error.columna}-${indice}`}>
                      <td className="is-num mono">{error.fila}</td>
                      <td className="mono">{error.columna ?? '—'}</td>
                      <td className="mono">{error.valor ?? '—'}</td>
                      <td>{error.motivo}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <div className="badge badge--ok">
            Sin errores. Revisa los números y aplica.
          </div>
        )}
      </div>
    </div>
  );
}

function Dato({ etiqueta, valor }: { readonly etiqueta: string; readonly valor: number }) {
  return (
    <div className="col gap-2">
      <span className="text-xs text-mute">{etiqueta}</span>
      <span className="mono is-key">{valor}</span>
    </div>
  );
}
