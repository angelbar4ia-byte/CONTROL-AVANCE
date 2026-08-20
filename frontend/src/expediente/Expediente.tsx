/**
 * Expediente técnico de una obra (§7.9, §11.2, §11.3 workflow D).
 *
 * Spec §5.1 (Reportes → «Expediente técnico», C y SI) · §5.3 (compartida).
 *
 * Reúne en una pantalla lo que sostiene el cierre de obra: documentos,
 * evidencias, cierres validados y estimaciones. Los montos que suma son los
 * **validados** —un cierre sin validar o una estimación en borrador todavía
 * pueden cambiar—, y eso lo decide el agregado de dominio, no esta pantalla.
 *
 * EL PDF ES UN JOB, NO UNA DESCARGA
 *
 * `GET /obras/{id}/expediente/pdf` **encola** y devuelve un identificador; el
 * archivo se baja después por `/reportes/{id}/descargar`. Por eso aquí no hay
 * un botón que descargue: hay uno que encola y una tarjeta que sigue el
 * trabajo. Fingir una descarga inmediata dejaría al operador mirando un
 * spinner que no termina.
 */

import { useState } from 'react';

import {
  usePdfDelExpedienteApiV1ObrasObraIdExpedientePdfGet,
  useVistaDelExpedienteApiV1ObrasObraIdExpedienteVistaGet,
} from '@/api/generado/expediente/expediente';
import type { ExpedienteRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { SelectorObra } from '@/lib/SelectorObra';
import { fmtNum } from '@/lib/formato';
import { SeguimientoDeReporte } from '@/reportes/SeguimientoDeReporte';
import { AgregarDocumento } from './AgregarDocumento';
import { etiquetaTipoDoc, puedeSubirDocumentos } from './reglas';

export default function Expediente() {
  const { sesion } = useSesion();
  const [obraId, setObraId] = useState('');
  const [subiendo, setSubiendo] = useState(false);
  const [reporteId, setReporteId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const vista = useVistaDelExpedienteApiV1ObrasObraIdExpedienteVistaGet<
    ExpedienteRespuesta,
    ErrorApi
  >(obraId, { query: { enabled: obraId !== '' } });

  // `useQuery` con `enabled: false`: encolar el PDF es una acción del operador,
  // no algo que deba pasar al abrir la pantalla. Se dispara con `refetch`.
  const pdf = usePdfDelExpedienteApiV1ObrasObraIdExpedientePdfGet(obraId, {
    query: { enabled: false },
  });

  if (!sesion) return null;

  const puedeSubir = puedeSubirDocumentos(sesion.rol);
  const expediente = vista.data;

  async function encolarPdf() {
    setError(null);
    const resultado = await pdf.refetch();
    if (resultado.error) {
      setError((resultado.error as ErrorApi).message);
      return;
    }
    if (resultado.data) setReporteId(resultado.data.id);
  }

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Reportes</div>
          <h1 className="page__title">Expediente técnico</h1>
          <div className="page__subtitle">
            El acervo de una obra: documentos, evidencias, cierres validados y
            estimaciones (§7.9). Es lo que sostiene el cierre de obra (§11.3 D).
          </div>
        </div>
        {puedeSubir && obraId !== '' && (
          <div className="page__actions">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setSubiendo(true)}
            >
              Agregar documento
            </button>
          </div>
        )}
      </div>

      {error && <ErrorBanner mensaje={error} />}

      <div className="filterbar">
        <SelectorObra
          id="expediente-obra"
          etiqueta="Obra"
          valor={obraId}
          onCambio={(id) => {
            setObraId(id);
            setReporteId(null);
          }}
        />
        {obraId !== '' && (
          <button
            type="button"
            className="btn"
            disabled={pdf.isFetching}
            onClick={() => void encolarPdf()}
          >
            {pdf.isFetching ? 'Encolando…' : 'Generar PDF'}
          </button>
        )}
      </div>

      {reporteId && (
        <SeguimientoDeReporte
          reporteId={reporteId}
          titulo="PDF del expediente"
          onCerrar={() => setReporteId(null)}
        />
      )}

      {obraId === '' ? (
        <div className="empty">
          <div className="empty-title">Elige una obra</div>
          <div className="empty-sub">
            El listado ya viene acotado a tu alcance (§4).
          </div>
        </div>
      ) : vista.isLoading ? (
        <div className="text-mute text-sm" style={{ padding: 24 }}>
          Cargando expediente…
        </div>
      ) : expediente ? (
        <>
          <div className="row gap-12 mb-8" style={{ flexWrap: 'wrap' }}>
            <Tarjeta etiqueta="Obra" valor={expediente.obra_clave} />
            <Tarjeta
              etiqueta="Avance"
              valor={`${fmtNum(Number(expediente.avance_pct))} %`}
            />
            <Tarjeta
              etiqueta="Monto cerrado"
              valor={fmtNum(Number(expediente.monto_cerrado))}
              nota="Solo cierres validados"
            />
            <Tarjeta
              etiqueta="Monto estimado"
              valor={fmtNum(Number(expediente.monto_estimado))}
              nota="Solo estimaciones validadas"
            />
            <Tarjeta etiqueta="Evidencias" valor={String(expediente.n_evidencias)} />
          </div>

          <Seccion titulo="Documentos" vacio="Sin documentos en el expediente.">
            {expediente.documentos.length > 0 && (
              <table className="table">
                <thead>
                  <tr>
                    <th>Tipo</th>
                    <th>Nombre</th>
                    <th>Ubicación</th>
                  </tr>
                </thead>
                <tbody>
                  {expediente.documentos.map((doc) => (
                    <tr key={doc.id}>
                      <td>{etiquetaTipoDoc(doc.tipo)}</td>
                      <td className="is-key">{doc.nombre}</td>
                      {/* La `url` es una clave de R2, no un enlace público: las
                          evidencias se bajan con presigned URL (§12.5) y no
                          desde un `href` que caducaría o sería abierto. */}
                      <td className="mono text-xs">{doc.url}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Seccion>

          <Seccion
            titulo="Evidencias"
            vacio="Sin fotos ni archivos referenciados desde revisiones, incidencias o cierres."
          >
            {expediente.evidencias.length > 0 && (
              <table className="table">
                <thead>
                  <tr>
                    <th>Origen</th>
                    <th>Clave en R2</th>
                  </tr>
                </thead>
                <tbody>
                  {expediente.evidencias.map((ev) => (
                    <tr key={`${ev.origen}-${ev.origen_id}-${ev.clave}`}>
                      <td>{ev.origen}</td>
                      <td className="mono text-xs">{ev.clave}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Seccion>

          <Seccion titulo="Cierres" vacio="Sin cierres de actividad.">
            {expediente.cierres.length > 0 && (
              <table className="table">
                <thead>
                  <tr>
                    <th>Actividad</th>
                    <th>Estado</th>
                    <th className="is-num">Cantidad</th>
                    <th className="is-num">Monto</th>
                  </tr>
                </thead>
                <tbody>
                  {expediente.cierres.map((cierre) => (
                    <tr key={cierre.id}>
                      <td className="is-key">{cierre.actividad_id.slice(0, 8)}</td>
                      <td>{cierre.estatus}</td>
                      <td className="is-num mono">{fmtNum(Number(cierre.cantidad))}</td>
                      <td className="is-num mono">{fmtNum(Number(cierre.monto))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Seccion>

          <Seccion titulo="Estimaciones" vacio="Sin estimaciones.">
            {expediente.estimaciones.length > 0 && (
              <table className="table">
                <thead>
                  <tr>
                    <th>Folio</th>
                    <th>Periodo</th>
                    <th>Modo</th>
                    <th>Estado</th>
                    <th className="is-num">Monto</th>
                  </tr>
                </thead>
                <tbody>
                  {expediente.estimaciones.map((est) => (
                    <tr key={est.id}>
                      <td className="is-key mono">{est.folio ?? '—'}</td>
                      <td className="mono">
                        {est.anio}-S{est.semana}
                      </td>
                      <td>{est.modo}</td>
                      <td>{est.estatus}</td>
                      <td className="is-num mono">{fmtNum(Number(est.monto))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Seccion>
        </>
      ) : null}

      {subiendo && obraId !== '' && (
        <AgregarDocumento
          obraId={obraId}
          onCerrar={() => setSubiendo(false)}
          onAgregado={() => {
            setSubiendo(false);
            void vista.refetch();
          }}
        />
      )}
    </div>
  );
}

function Tarjeta({
  etiqueta,
  valor,
  nota,
}: {
  readonly etiqueta: string;
  readonly valor: string;
  readonly nota?: string;
}) {
  return (
    <div className="card" style={{ minWidth: 160 }}>
      <div className="card__body col gap-2">
        <span className="text-xs text-mute">{etiqueta}</span>
        <span className="is-key mono" style={{ fontSize: 20 }}>
          {valor}
        </span>
        {nota && <span className="text-xs text-mute">{nota}</span>}
      </div>
    </div>
  );
}

function Seccion({
  titulo,
  vacio,
  children,
}: {
  readonly titulo: string;
  readonly vacio: string;
  readonly children: React.ReactNode;
}) {
  return (
    <div className="card mb-8">
      <div className="card__header">
        <h2 className="card__title">{titulo}</h2>
      </div>
      <div className="card__body">
        {children ?? null}
        {!children && <div className="text-mute text-sm">{vacio}</div>}
      </div>
    </div>
  );
}
