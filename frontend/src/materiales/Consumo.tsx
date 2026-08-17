/**
 * Consumo real vs presupuesto por obra (§7.7, §10.5, §11.2 "Materiales").
 *
 * Pantalla compartida (§5.3): Control de obra y Super intendente la ven
 * completa; el Residente la ve en **lectura** (§4, §5.1 "Control de
 * materiales (lectura)"). Rutas `/materiales/consumo` (C) y `/materiales`
 * (R) en `shell/navegacion.ts`.
 *
 * Todo lo numérico de esta tabla —cantidad teórica, real, desviación en
 * cantidad y en %, y el costo de valuación con la regla del §10.5— llega
 * **ya calculado** por `v_consumo_vs_presupuesto`. Aquí no se recalcula
 * nada, ni el IVA: el backend es la autoridad de la valuación (§10.5).
 */

import { useState } from 'react';

import { useConsumoVsPresupuestoApiV1ObrasObraIdMaterialesConsumoGet } from '@/api/generado/materiales/materiales';
import { useListarMaterialesApiV1MaterialesGet } from '@/api/generado/catalogos/catalogos';
import { useSesion } from '@/app/sesion';
import { fmtMXN, fmtNum, fmtPct } from '@/lib/formato';
import { SelectorObra } from '@/lib/SelectorObra';
import {
  UMBRAL_DESVIACION_PCT,
  etiquetaOrigenValuacion,
  fueraDeUmbral,
  origenValuacion,
  tonoDesviacion,
} from './reglas';

export default function Consumo() {
  const { sesion } = useSesion();
  const [obraId, setObraId] = useState('');
  const [soloDesviados, setSoloDesviados] = useState(false);

  const consulta = useConsumoVsPresupuestoApiV1ObrasObraIdMaterialesConsumoGet(obraId, {
    query: { enabled: obraId !== '' },
  });

  // El cruce viene por `insumo_id`; el catálogo de materiales da la clave y
  // la descripción legibles (§10.6: los materiales se matchean por clave).
  const materiales = useListarMaterialesApiV1MaterialesGet();
  const porId = new Map((materiales.data ?? []).map((m) => [m.id, m]));

  if (!sesion) return null;
  const soloLectura = sesion.rol === 'residente';

  const filas = consulta.data ?? [];
  const visibles = soloDesviados ? filas.filter((f) => fueraDeUmbral(f.desviacion_pct)) : filas;
  const desviados = filas.filter((f) => fueraDeUmbral(f.desviacion_pct)).length;

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Control de materiales</div>
          <h1 className="page__title">Consumo vs presupuesto</h1>
          <div className="page__subtitle">
            Consumo real de almacén contra lo teórico de la explosión del CPU.
            La desviación se reporta primero en <strong>cantidad</strong> y
            luego en importe (§10.5); el umbral de alerta es ±
            {UMBRAL_DESVIACION_PCT}% (§3.6).
            {soloLectura && ' Tu rol lo consulta en lectura (§4).'}
          </div>
        </div>
      </div>

      <div className="filterbar">
        <div style={{ minWidth: 260 }}>
          <SelectorObra
            id="consumo-obra"
            etiqueta="Obra"
            valor={obraId}
            onCambio={setObraId}
          />
        </div>
        {obraId !== '' && (
          <div className="row gap-12">
            <button
              type="button"
              className={`chip ${soloDesviados ? 'is-active' : ''}`}
              aria-pressed={soloDesviados}
              onClick={() => setSoloDesviados((v) => !v)}
            >
              Solo fuera de umbral
              <span className="mono"> {desviados}</span>
            </button>
          </div>
        )}
      </div>

      {obraId === '' ? (
        <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
          Elige una obra para ver su consumo de materiales.
        </div>
      ) : (
        <div className="table-wrap">
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Material</th>
                  <th>Descripción</th>
                  <th className="is-num">Teórica</th>
                  <th className="is-num">Real</th>
                  <th className="is-num">Desviación</th>
                  <th className="is-num">Desv. %</th>
                  <th className="is-num">Costo valuación</th>
                  <th>Regla §10.5</th>
                </tr>
              </thead>
              <tbody>
                {consulta.isLoading ? (
                  <tr>
                    <td colSpan={8}>
                      <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                        Cargando…
                      </div>
                    </td>
                  </tr>
                ) : visibles.length === 0 ? (
                  <tr>
                    <td colSpan={8}>
                      <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                        {filas.length === 0
                          ? 'Esta obra todavía no tiene consumo ni presupuesto de materiales.'
                          : `Ningún material se salió del ±${UMBRAL_DESVIACION_PCT}%.`}
                      </div>
                    </td>
                  </tr>
                ) : (
                  visibles.map((fila) => {
                    const material = porId.get(fila.insumo_id);
                    const origen = origenValuacion(fila.cant_teorica, fila.cant_real);
                    return (
                      <tr key={fila.insumo_id}>
                        <td className="is-key" title={fila.insumo_id}>
                          {material?.clave ?? fila.insumo_id.slice(0, 8)}
                        </td>
                        <td>{material?.descripcion ?? '—'}</td>
                        <td className="is-num">{fmtNum(fila.cant_teorica)}</td>
                        <td className="is-num">{fmtNum(fila.cant_real)}</td>
                        <td className="is-num">{fmtNum(fila.desviacion_cant)}</td>
                        <td className="is-num">
                          <span className={`badge badge--${tonoDesviacion(fila.desviacion_pct)}`}>
                            {fmtPct(fila.desviacion_pct)}
                          </span>
                        </td>
                        <td className="is-num">{fmtMXN(fila.costo_valuacion)}</td>
                        <td className="text-mute text-sm">{etiquetaOrigenValuacion(origen)}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="field__hint mt-8">
        Los costos del almacén vienen <strong>sin IVA</strong> y el backend
        agrega la tasa según la clase del material (§3.5, §10.6). Esta tabla
        muestra la valuación tal como la resolvió el servidor: no la
        recalcula.
      </div>
    </div>
  );
}
