/**
 * «Confirmar cálculo → actualizar APU» y la conciliación en las dos direcciones (plan de elementos de muro, fase I; M-131).
 *
 * El **APU manda**: las compras y la estimación se pagan con él. El cálculo del elemento (su receta puesta en los insumos) es la
 * salida de material que justifica la estimación; la tolerancia de ±3 % es solo un aviso visual. Confirmar el cálculo lleva sus
 * coeficientes al APU del concepto y crea una versión nueva; lo que Costos confirma queda como propuesta y rige el APU vigente
 * hasta que Control de obra la autorice. Un concepto nuevo no tiene APU: se autoriza primero.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getAutorizacionDelElementoApiV1ElementosParametricosElementoIdAutorizacionGetQueryKey as claveDeAutorizacion,
  getConciliacionDelConceptoApiV1ElementosParametricosElementoIdConceptosPorContextoFilaIdConciliacionGetQueryKey as claveDeConciliacion,
  getPlanDeApuApiV1ElementosParametricosElementoIdConceptosPorContextoFilaIdApuGetQueryKey as claveDelPlan,
  useConciliacionDelConceptoApiV1ElementosParametricosElementoIdConceptosPorContextoFilaIdConciliacionGet as useConciliacion,
  useConfirmarCalculoApiV1ElementosParametricosElementoIdConceptosPorContextoFilaIdApuConfirmarPost as useConfirmarCalculo,
  usePlanDeApuApiV1ElementosParametricosElementoIdConceptosPorContextoFilaIdApuGet as usePlanDeApu,
} from '@/api/generado/elementos-parametricos/elementos-parametricos';
import { queryClient } from '@/app/queryClient';

interface Props {
  readonly elementoId: string;
  readonly filaId: string;
  readonly concepto: string;
  readonly puedeAutorizar: boolean;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

const ACCION: Record<string, string> = {
  sin_cambio: 'Coincide',
  actualizar: 'Se actualiza',
  agregar: 'Se agrega al APU',
  en_auxiliar: 'En un auxiliar: no se toca',
  solo_apu: 'Solo el APU: manda el APU',
  sin_insumo: 'No existe en la base',
};
const SENTIDO: Record<string, string> = {
  se_justifican: 'Se justifican',
  difieren: 'Difieren',
  estimado_sin_salida: 'Estimado sin salida del cálculo',
  salida_sin_estimado: 'Salida sin estimado',
};

const num = (n: number | null | undefined) => (n === null || n === undefined ? '—' : Math.abs(n) >= 1 ? n.toFixed(2) : n.toFixed(4));
const pesos = (n: number | null | undefined) => (n === null || n === undefined ? '—' : `$${n.toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
const pct = (n: number | null | undefined) => (n === null || n === undefined ? '—' : `${n > 0 ? '+' : ''}${n.toFixed(1)} %`);

export function ApuDelConcepto({ elementoId, filaId, concepto, puedeAutorizar, onCambio, onError }: Props) {
  const [cantidad, setCantidad] = useState('1');
  const plan = usePlanDeApu(elementoId, filaId);
  const n = Number(cantidad);
  const conciliacion = useConciliacion(elementoId, filaId, { cantidad: Number.isFinite(n) && n > 0 ? n : 1 });
  const confirmar = useConfirmarCalculo<ErrorApi>();
  const p = plan.data;
  if (!p) return null;

  const recargar = () => {
    void queryClient.invalidateQueries({ queryKey: claveDelPlan(elementoId, filaId) });
    void queryClient.invalidateQueries({ queryKey: claveDeConciliacion(elementoId, filaId) });
    void queryClient.invalidateQueries({ queryKey: claveDeAutorizacion(elementoId) });
  };
  async function confirmarCalculo() {
    try {
      const r = await confirmar.mutateAsync({ elementoId, filaId });
      recargar();
      onCambio(
        r.aplicado
          ? `${concepto}: APU actualizado, versión ${r.version ?? ''}.`.replace(' ,', ',')
          : `${concepto}: la actualización del APU quedó propuesta; rige el APU vigente hasta que Control de obra la autorice.`,
      );
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo actualizar el APU.');
    }
  }

  const c = conciliacion.data;
  return (
    <div role="group" aria-label={`APU de ${concepto}`} data-apu-del-concepto={concepto} style={{ display: 'grid', gap: 4 }}>
      <div className="text-xs text-mute">Confirmar cálculo → actualizar APU (el APU manda; ±3 % es solo un aviso)</div>
      {p.sin_catalogo ? (
        <p className="text-xs text-mute">Concepto nuevo: aún no tiene APU en el catálogo. Autorízalo antes de actualizar su APU.</p>
      ) : (
        <>
          <table className="text-xs" aria-label={`Actualización del APU de ${concepto}`}>
            <thead>
              <tr><th>Clave</th><th>Insumo</th><th>APU vigente</th><th>Con el cálculo</th><th>Dif.</th><th /></tr>
            </thead>
            <tbody>
              {p.filas.map((f) => (
                <tr key={f.clave} data-insumo-del-apu={f.clave} data-accion={f.accion}>
                  <td className="mono">{f.clave}</td>
                  <td>{f.descripcion}</td>
                  <td>{num(f.apu)}</td>
                  <td>{num(f.calculo)}</td>
                  <td>{pct(f.diferencia_pct)}</td>
                  <td><span className="badge" title={f.motivo}>{ACCION[f.accion] ?? f.accion}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="row text-xs" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <span data-pu-del-apu>
              Precio unitario: {pesos(p.pu_vigente)} → {pesos(p.pu_con_el_calculo)}
            </span>
            {p.avisos.map((a) => (
              <span key={a} role="note" className="text-mute">{a}</span>
            ))}
          </div>
          <div className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
            <button
              type="button"
              className="btn btn--primary"
              data-confirmar-calculo={concepto}
              disabled={!p.hay_cambios || p.propuesta_pendiente !== null || confirmar.isPending}
              onClick={() => void confirmarCalculo()}
            >
              Confirmar cálculo → actualizar APU
            </button>
            {p.propuesta_pendiente !== null ? (
              <span className="badge badge--warn">Propuesta pendiente de autorización: rige el APU vigente</span>
            ) : !p.hay_cambios ? (
              <span className="text-xs text-mute">El cálculo ya coincide con el APU.</span>
            ) : !puedeAutorizar ? (
              <span className="text-xs text-mute">Propone una versión nueva del APU; pasa por la autorización de Control de obra y mientras tanto rige el APU vigente.</span>
            ) : null}
          </div>
          <details>
            <summary className="text-xs">Conciliación en las dos direcciones: estimado por APU ↔ salida del cálculo</summary>
            <label className="text-xs text-mute" style={{ display: 'inline-grid', gap: 2 }}>
              Cantidad del concepto ({p.unidad})
              <input type="number" min={0} step="any" aria-label={`Cantidad de ${concepto} a conciliar`} value={cantidad} onChange={(e) => setCantidad(e.target.value)} />
            </label>
            {c && (
              <>
                <table className="text-xs" aria-label={`Conciliación de ${concepto}`}>
                  <thead>
                    <tr><th>Clave</th><th>Insumo</th><th>Estimado por APU</th><th>Salida del cálculo</th><th>Dif.</th><th>Dif. $</th><th /></tr>
                  </thead>
                  <tbody>
                    {c.filas.map((f) => (
                      <tr key={f.clave} data-conciliado={f.clave} data-sentido={f.sentido}>
                        <td className="mono">{f.clave}</td>
                        <td>{f.descripcion}</td>
                        <td>{num(f.estimado)}</td>
                        <td>{num(f.salida)}</td>
                        <td>{pct(f.diferencia_pct)}</td>
                        <td>{pesos(f.diferencia_importe)}</td>
                        <td><span className={f.avisa ? 'badge badge--warn' : 'badge'}>{SENTIDO[f.sentido] ?? f.sentido}</span></td>
                      </tr>
                    ))}
                    <tr>
                      <td colSpan={5}><strong>Importe</strong></td>
                      <td colSpan={2}>{pesos(c.importe_apu)} APU · {pesos(c.importe_salida)} salida</td>
                    </tr>
                  </tbody>
                </table>
                {c.sin_precio && <p className="text-xs text-mute">Algún insumo no tiene precio: su importe queda vacío (no se inventa).</p>}
                <p className="text-xs text-mute">
                  Lo pagado y estimado es concepto × APU. La estimación se justifica con las salidas de material y las salidas de material se
                  justifican con lo estimado. Para compras y estimación manda el APU; ±3 % es solo un aviso visual.
                </p>
              </>
            )}
          </details>
        </>
      )}
    </div>
  );
}
