/**
 * Sigue un reporte encolado hasta que se puede bajar (§11.2, §12.2).
 *
 * Los dos reportes del sistema —XLSX de estimación y PDF de expediente— son
 * **jobs**: la ruta encola y devuelve un identificador, el worker lo produce y
 * la descarga llega después. Esta tarjeta es lo que convierte ese identificador
 * en algo que un operador puede mirar.
 *
 * POR QUÉ SONDEA, INCLUSO CON TIEMPO REAL
 *
 * El canal de avisos existe desde la Fase 16 (`lib/tiempoReal.ts`) y aun así
 * esto sigue sondeando. No es una omisión: el canal transporta **hechos del
 * dominio** —una actividad cerrada, una estimación validada— y el progreso de
 * un job no es uno. Anunciarlo obligaría a que el worker publicara por
 * organización el avance de cada trabajo —convertir un canal de negocio en un
 * bus de infraestructura— para ahorrarle unas cuantas peticiones a la única
 * pantalla que está mirando un identificador.
 *
 * Así que `refetchInterval` de TanStack Query cada dos segundos y **solo
 * mientras el trabajo está vivo**: en cuanto queda `listo` o `fallido` el
 * intervalo se apaga solo, porque un sondeo que sigue después de terminar es
 * una petición cada dos segundos que no cambia nada.
 *
 * El estado del trabajo **caduca** (`keep_result` de arq): un identificador
 * viejo responde 404 y eso no es un error del operador. Se dice con esas
 * palabras en vez de un "error 404".
 */

import { useState } from 'react';

import {
  descargarReporteApiV1ReportesReporteIdDescargarGet,
  useEstadoDeReporteApiV1ReportesReporteIdGet,
} from '@/api/generado/reportes/reportes';
import { guardarArchivo, type ArchivoDescargado, type ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';

const SONDEO_MS = 2000;

interface Props {
  readonly reporteId: string;
  readonly titulo: string;
  readonly onCerrar: () => void;
}

export function SeguimientoDeReporte({ reporteId, titulo, onCerrar }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [bajando, setBajando] = useState(false);

  const estado = useEstadoDeReporteApiV1ReportesReporteIdGet(reporteId, {
    query: {
      refetchInterval: (consulta) => {
        const dato = consulta.state.data;
        // Sin dato todavía: se sigue preguntando. Con uno terminado, se para.
        if (!dato) return SONDEO_MS;
        return dato.estatus === 'listo' || dato.estatus === 'fallido'
          ? false
          : SONDEO_MS;
      },
      // Un 404 es el resultado caducado, no un fallo transitorio: reintentar
      // no lo va a resucitar.
      retry: false,
    },
  });

  async function bajar() {
    setBajando(true);
    setError(null);
    try {
      const archivo = (await descargarReporteApiV1ReportesReporteIdDescargarGet(
        reporteId,
      )) as unknown as ArchivoDescargado;
      guardarArchivo(archivo);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo bajar el reporte.');
    } finally {
      setBajando(false);
    }
  }

  const dato = estado.data;
  const caducado = (estado.error as ErrorApi | null)?.status === 404;

  return (
    <div className="card mb-8">
      <div className="card__header">
        <div className="col gap-2" style={{ alignItems: 'flex-start' }}>
          <h2 className="card__title">{titulo}</h2>
          <span className="text-xs text-mute mono">{reporteId}</span>
        </div>
        <button type="button" className="btn btn--sm btn--ghost" onClick={onCerrar}>
          Ocultar
        </button>
      </div>
      <div className="card__body col gap-8">
        {error && <ErrorBanner mensaje={error} />}

        {caducado ? (
          <div className="text-sm text-mute">
            El resultado de este reporte ya caducó. Vuelve a generarlo — no se
            perdió nada, solo el archivo temporal.
          </div>
        ) : dato === undefined ? (
          <div className="text-mute text-sm">Consultando…</div>
        ) : (
          <>
            <div className="row gap-8" style={{ alignItems: 'center' }}>
              <span className={`badge badge--${tonoEstado(dato.estatus)}`}>
                {etiquetaEstado(dato.estatus)}
              </span>
              {dato.nombre_archivo && (
                <span className="mono text-xs text-mute">{dato.nombre_archivo}</span>
              )}
            </div>

            {dato.estatus === 'fallido' && (
              <div className="text-sm">
                El worker no pudo generarlo
                {dato.error ? ` (${dato.error})` : ''}. El detalle queda en el log
                del servidor, no aquí (§12.4).
              </div>
            )}

            {dato.listo && (
              <button
                type="button"
                className="btn btn--primary btn--sm"
                style={{ alignSelf: 'flex-start' }}
                disabled={bajando}
                onClick={() => void bajar()}
              >
                {bajando ? 'Bajando…' : 'Descargar'}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function etiquetaEstado(estatus: string): string {
  const etiquetas: Record<string, string> = {
    en_cola: 'En cola',
    en_proceso: 'Generándose',
    listo: 'Listo',
    fallido: 'Falló',
  };
  return etiquetas[estatus] ?? estatus;
}

function tonoEstado(estatus: string): string {
  if (estatus === 'listo') return 'ok';
  if (estatus === 'fallido') return 'danger';
  return 'info';
}
