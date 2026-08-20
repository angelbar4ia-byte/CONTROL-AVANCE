/**
 * Rendimientos de una obra: concepto por concepto y cuadrilla por cuadrilla
 * (§5.1, §7.3).
 *
 * ## Las dos caras que faltan son el punto
 *
 * El comparativo incluye lo **presupuestado y no ejecutado** —trabajo que no se
 * hizo— y lo **ejecutado sin presupuestar** —los extra-catálogo (§11.2)—. Son
 * los dos que explican por qué una obra costó lo que costó, y los dos que un
 * comparativo ingenuo dejaría fuera.
 *
 * ## Las cuadrillas no tienen contraparte presupuestada
 *
 * El presupuesto es por concepto y no reparte el trabajo entre cuadrillas. Lo
 * comparable es su `rendimiento` de catálogo —lo que se espera que produzcan—
 * contra lo que produjeron, y eso es lo que se muestra.
 */

import { useState } from 'react';

import {
  useRendimientosDeObraApiV1ObrasObraIdRendimientosGet,
  useRendimientosPorCuadrillaApiV1ObrasObraIdRendimientosCuadrillasGet,
} from '@/api/generado/presupuesto/presupuesto';
import type {
  RendimientoPorConceptoRespuesta,
  RendimientoPorCuadrillaRespuesta,
  ResumenDeObraRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import { fmtMXN, fmtNum } from '@/lib/formato';
import { etiquetaClasificacion, textoPorcentaje, tonoClasificacion } from './reglas';

interface Props {
  readonly obra: ResumenDeObraRespuesta;
  readonly onCerrar: () => void;
}

export function PanelRendimientos({ obra, onCerrar }: Props) {
  const [vista, setVista] = useState<'conceptos' | 'cuadrillas'>('conceptos');

  const conceptos = useRendimientosDeObraApiV1ObrasObraIdRendimientosGet<
    RendimientoPorConceptoRespuesta[],
    ErrorApi
  >(obra.obra_id, undefined, { query: { enabled: vista === 'conceptos' } });

  const cuadrillas =
    useRendimientosPorCuadrillaApiV1ObrasObraIdRendimientosCuadrillasGet<
      RendimientoPorCuadrillaRespuesta[],
      ErrorApi
    >(obra.obra_id, { query: { enabled: vista === 'cuadrillas' } });

  return (
    <Sheet
      titulo={obra.obra_clave}
      subtitulo={`${obra.proyecto_clave} · ${obra.cluster_clave}`}
      onCerrar={onCerrar}
    >
      <div className="sheet__body col gap-12">
        {conceptos.error && <ErrorBanner mensaje={conceptos.error.message} />}
        {cuadrillas.error && <ErrorBanner mensaje={cuadrillas.error.message} />}

        <div className="row gap-12">
          <Dato etiqueta="Presupuestado" valor={fmtMXN(Number(obra.monto_presupuestado))} />
          <Dato etiqueta="Ejecutado" valor={fmtMXN(Number(obra.monto_ejecutado))} />
          <Dato
            etiqueta="Desviación"
            valor={`${fmtMXN(Number(obra.desviacion_importe))} · ${textoPorcentaje(obra.desviacion_pct)}`}
          />
        </div>

        <div className="tabs">
          <button
            type="button"
            className={`tabs__tab ${vista === 'conceptos' ? 'is-active' : ''}`}
            onClick={() => setVista('conceptos')}
          >
            Por concepto
          </button>
          <button
            type="button"
            className={`tabs__tab ${vista === 'cuadrillas' ? 'is-active' : ''}`}
            onClick={() => setVista('cuadrillas')}
          >
            Por cuadrilla
          </button>
        </div>

        <div className="table-scroll" style={{ maxHeight: 420 }}>
          {vista === 'conceptos' ? (
            <TablaConceptos consulta={conceptos} />
          ) : (
            <TablaCuadrillas consulta={cuadrillas} />
          )}
        </div>
      </div>

      <div className="sheet__footer">
        <button type="button" className="btn" onClick={onCerrar}>
          Cerrar
        </button>
      </div>
    </Sheet>
  );
}

function TablaConceptos({
  consulta,
}: {
  readonly consulta: { isLoading: boolean; data?: RendimientoPorConceptoRespuesta[] };
}) {
  const filas = consulta.data ?? [];
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Concepto</th>
          <th className="is-num">Presupuestado</th>
          <th className="is-num">Ejecutado</th>
          <th className="is-num">Desviación</th>
          <th>Estado</th>
        </tr>
      </thead>
      <tbody>
        {consulta.isLoading ? (
          <tr>
            <td colSpan={5}>
              <div className="text-mute text-sm" style={{ padding: '16px 0' }}>
                Cargando…
              </div>
            </td>
          </tr>
        ) : filas.length === 0 ? (
          <tr>
            <td colSpan={5}>
              <div className="text-mute text-sm" style={{ padding: '16px 0' }}>
                Sin presupuesto ni actividades que comparar.
              </div>
            </td>
          </tr>
        ) : (
          filas.map((fila, indice) => (
            <tr key={fila.concepto_id ?? `sin-concepto-${indice}`}>
              <td className="is-key">
                <div className="col gap-2" style={{ alignItems: 'flex-start' }}>
                  <span>
                    {fila.concepto_descripcion ??
                      (fila.extra ? 'Trabajo extra-catálogo' : 'Sin concepto')}
                  </span>
                  {fila.concepto_clave && (
                    <span className="text-xs text-mute mono">{fila.concepto_clave}</span>
                  )}
                </div>
              </td>
              <td className="is-num mono">
                {fmtMXN(Number(fila.importe_presupuestado))}
                <span className="text-xs text-mute">
                  {' '}
                  {fmtNum(Number(fila.cantidad_presupuestada))} {fila.unidad_clave ?? ''}
                </span>
              </td>
              <td className="is-num mono">
                {fmtMXN(Number(fila.importe_ejecutado))}
                <span className="text-xs text-mute">
                  {' '}
                  {fmtNum(Number(fila.cantidad_ejecutada))} {fila.unidad_clave ?? ''}
                </span>
              </td>
              <td className="is-num mono">
                {fmtMXN(Number(fila.desviacion_importe))}
                <span className="text-xs text-mute">
                  {' '}
                  {textoPorcentaje(fila.desviacion_pct)}
                </span>
              </td>
              <td>
                <span className={`badge badge--${tonoClasificacion(fila.clasificacion)}`}>
                  {etiquetaClasificacion(fila.clasificacion)}
                </span>
              </td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}

function TablaCuadrillas({
  consulta,
}: {
  readonly consulta: { isLoading: boolean; data?: RendimientoPorCuadrillaRespuesta[] };
}) {
  const filas = consulta.data ?? [];
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Cuadrilla</th>
          <th>Contratista</th>
          <th className="is-num">Actividades</th>
          <th className="is-num">Ejecutado</th>
          <th className="is-num">Rendimiento</th>
        </tr>
      </thead>
      <tbody>
        {consulta.isLoading ? (
          <tr>
            <td colSpan={5}>
              <div className="text-mute text-sm" style={{ padding: '16px 0' }}>
                Cargando…
              </div>
            </td>
          </tr>
        ) : filas.length === 0 ? (
          <tr>
            <td colSpan={5}>
              <div className="text-mute text-sm" style={{ padding: '16px 0' }}>
                Ninguna actividad de esta obra tiene cuadrilla asignada.
              </div>
            </td>
          </tr>
        ) : (
          filas.map((fila) => (
            <tr key={fila.cuadrilla_id}>
              <td className="is-key">{fila.cuadrilla_nombre}</td>
              <td className="text-sm">{fila.contratista_nombre ?? '—'}</td>
              <td className="is-num mono">
                {fila.concluidas} / {fila.actividades}
              </td>
              <td className="is-num mono">
                {fmtMXN(Number(fila.importe_ejecutado ?? 0))}
              </td>
              <td className="is-num mono">
                {/* Lo esperado por catálogo contra lo que produjo. Sin
                    `rendimiento` capturado no hay contra qué comparar, y se
                    dice en vez de mostrar un cero. */}
                {fila.rendimiento_esperado === null ||
                fila.rendimiento_esperado === undefined ? (
                  <span className="text-mute">sin base</span>
                ) : (
                  <>
                    {fmtNum(Number(fila.cantidad_ejecutada ?? 0))}
                    <span className="text-xs text-mute">
                      {' '}
                      esp. {fmtNum(Number(fila.rendimiento_esperado))}
                    </span>
                  </>
                )}
              </td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}

function Dato({ etiqueta, valor }: { readonly etiqueta: string; readonly valor: string }) {
  return (
    <div className="col gap-2">
      <span className="text-xs text-mute">{etiqueta}</span>
      <span className="mono is-key">{valor}</span>
    </div>
  );
}
