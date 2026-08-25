/**
 * Cargas de datos — la bandeja del §10.3.
 *
 * Spec §10 (cargadores) · §10.8 (versionado y reversa) · §11.3 workflow G ·
 * §5.1 (Configuración → «Cargas de datos», Control de obra).
 *
 * Es lo que permite que un Control de obra suba el catálogo real de su
 * organización sin que nadie corra un script. Hasta ahora el vertical de
 * cargas llegaba a la API y se detenía ahí: los endpoints existían, el
 * contrato los publicaba y ninguna pantalla los usaba.
 *
 * La descarga de plantillas vive aquí y no en el formulario de subida, a
 * propósito: se baja una vez, se llena con calma y se sube después. Meterla
 * dentro del cajón de subir obligaría a abrir un flujo de escritura para hacer
 * una lectura.
 */

import { useState } from 'react';

import {
  descargarPlantillaApiV1CargasPlantillasTipoGet,
  useListarCargasApiV1CargasGet,
} from '@/api/generado/cargas/cargas';
import { TipoCarga, type LoteRespuesta } from '@/api/generado/modelo';
import { guardarArchivo, type ArchivoDescargado, type ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { PanelCarga } from './PanelCarga';
import { SubirCarga } from './SubirCarga';
import {
  TIPOS,
  etiquetaEstatus,
  etiquetaModo,
  etiquetaTipo,
  resumenDe,
  tonoEstatus,
} from './reglas';

export default function Cargas() {
  const [tipo, setTipo] = useState<TipoCarga | 'todos'>('todos');
  const [subiendo, setSubiendo] = useState(false);
  const [seleccionado, setSeleccionado] = useState<LoteRespuesta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bajando, setBajando] = useState<string | null>(null);
  // Con un tipo específico elegido, la lista se colapsa a la carga más
  // reciente: la mayoría de las anteriores ya no se pueden revertir solas
  // (§10.8, `CargaConDependientes`), así que verlas todas siempre es ruido.
  // En "Todas" se deja el comportamiento de siempre — agrupar tipos
  // mezclados es una pregunta distinta que no se resuelve aquí.
  const [verAnteriores, setVerAnteriores] = useState(false);

  const consulta = useListarCargasApiV1CargasGet<LoteRespuesta[], ErrorApi>(
    tipo === 'todos' ? undefined : { tipo },
  );

  const filas = consulta.data ?? [];
  // El backend ya las entrega por `fecha desc` (más nueva primero).
  const filasVisibles =
    tipo === 'todos' || verAnteriores ? filas : filas.slice(0, 1);
  const anteriores = tipo === 'todos' ? 0 : Math.max(filas.length - 1, 0);

  // El contrato publica `GET /cargas/{id}`, pero tras revertir basta con
  // recargar el historial: el cajón se recupera de la lista, igual que en
  // Evaluaciones y en Equipo.
  const abierto =
    seleccionado === null
      ? null
      : (filas.find((l) => l.id === seleccionado.id) ?? seleccionado);

  async function bajarPlantilla(deTipo: TipoCarga) {
    setBajando(deTipo);
    setError(null);
    try {
      // Sin hook de TanStack Query: una descarga no es estado del servidor que
      // haya que cachear ni recargar. `useQuery` la dispararía al montar la
      // pantalla, que es justo lo contrario de lo que se quiere.
      const archivo = (await descargarPlantillaApiV1CargasPlantillasTipoGet(
        deTipo,
      )) as unknown as ArchivoDescargado;
      guardarArchivo(archivo);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo bajar la plantilla.');
    } finally {
      setBajando(null);
    }
  }

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Configuración</div>
          <h1 className="page__title">Cargas de datos</h1>
          <div className="page__subtitle">
            Sube catálogos, presupuestos y programas desde Excel (§10). Cada
            carga se previsualiza antes de aplicarse, deja su reporte de errores
            por fila y se puede revertir como unidad.
          </div>
        </div>
        <div className="page__actions">
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => setSubiendo(true)}
          >
            Subir archivo
          </button>
        </div>
      </div>

      {error && <ErrorBanner mensaje={error} />}

      <div className="card mb-8">
        <div className="card__header">
          <h2 className="card__title">Plantillas</h2>
          <div className="text-mute text-xs">
            Cada cargador espera sus cabeceras exactas (§10.6)
          </div>
        </div>
        <div className="card__body row gap-8" style={{ flexWrap: 'wrap' }}>
          {TIPOS.map((t) => (
            <button
              key={t}
              type="button"
              className="btn btn--sm"
              disabled={bajando !== null}
              onClick={() => void bajarPlantilla(t)}
            >
              {bajando === t ? 'Bajando…' : etiquetaTipo(t)}
            </button>
          ))}
        </div>
      </div>

      <div className="filterbar">
        <div className="tabs">
          <button
            type="button"
            className={`tabs__tab ${tipo === 'todos' ? 'is-active' : ''}`}
            onClick={() => {
              setTipo('todos');
              setVerAnteriores(false);
            }}
          >
            Todas
          </button>
          {TIPOS.map((t) => (
            <button
              key={t}
              type="button"
              className={`tabs__tab ${tipo === t ? 'is-active' : ''}`}
              onClick={() => {
                setTipo(t);
                setVerAnteriores(false);
              }}
            >
              {etiquetaTipo(t)}
            </button>
          ))}
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Tipo</th>
                <th>Archivo</th>
                <th>Modo</th>
                <th>Estado</th>
                <th className="is-num">Filas</th>
                <th className="is-num">Insertados</th>
                <th className="is-num">Actualizados</th>
                <th className="is-num">Versión</th>
                <th className="cell-actions">Detalle</th>
              </tr>
            </thead>
            <tbody>
              {consulta.isLoading ? (
                <tr>
                  <td colSpan={9}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : filas.length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Todavía no hay cargas de este tipo. Baja la plantilla,
                      llénala y súbela.
                    </div>
                  </td>
                </tr>
              ) : (
                filasVisibles.map((lote) => {
                  const resumen = resumenDe(lote);
                  return (
                    <tr key={lote.id} className={lote.revertida ? 'is-muted' : ''}>
                      <td className="is-key">{etiquetaTipo(lote.tipo)}</td>
                      <td>{lote.archivo_nombre ?? '—'}</td>
                      <td>{etiquetaModo(lote.modo)}</td>
                      <td>
                        <div className="row gap-4">
                          <span className={`badge badge--${tonoEstatus(lote.estatus)}`}>
                            {etiquetaEstatus(lote.estatus)}
                          </span>
                          {lote.revertida && (
                            <span className="badge badge--warn">Revertida</span>
                          )}
                        </div>
                      </td>
                      <td className="is-num mono">{resumen.filas}</td>
                      <td className="is-num mono">{resumen.insertados}</td>
                      <td className="is-num mono">{resumen.actualizados}</td>
                      <td className="is-num mono">{lote.version_generada ?? '—'}</td>
                      <td className="cell-actions">
                        <button
                          type="button"
                          className="btn btn--sm"
                          onClick={() => setSeleccionado(lote)}
                        >
                          Abrir
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {anteriores > 0 && (
        <button
          type="button"
          className="btn btn--sm"
          style={{ marginTop: 8 }}
          onClick={() => setVerAnteriores((v) => !v)}
        >
          {verAnteriores ? 'Ocultar cargas anteriores' : `Ver ${anteriores} carga(s) anteriores`}
        </button>
      )}

      {subiendo && (
        <SubirCarga
          onCerrar={() => setSubiendo(false)}
          onAplicada={() => {
            setSubiendo(false);
            void consulta.refetch();
          }}
        />
      )}

      {abierto && (
        <PanelCarga
          lote={abierto}
          onCerrar={() => setSeleccionado(null)}
          onRevertida={() => void consulta.refetch()}
          onEliminada={() => {
            setSeleccionado(null);
            void consulta.refetch();
          }}
        />
      )}
    </div>
  );
}
