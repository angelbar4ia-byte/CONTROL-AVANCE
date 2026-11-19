/**
 * Las versiones propuestas del catálogo para una trabe (D7, Q56): lo que el catálogo trae mal no se edita; se propone como **nueva
 * versión del concepto** y solo Control de obra la autoriza. El catálogo vigente sigue activo y la conciliación de la tarjeta muestra la
 * diferencia. Mismo ciclo que el de los castillos (`/biblioteca-de-elementos/estructura/{clave}/propuestas…`). Sin precios ni destajos.
 */

import type { ErrorApi } from '@/api/cliente';
import {
  useAutorizarPropuestaApiV1PropuestasDeEstructuraPropuestaIdAutorizarPost as useAutorizarPropuesta,
  useProponerCorreccionesApiV1BibliotecaDeElementosEstructuraClavePropuestasCorreccionesPost as useProponerCorrecciones,
  useRechazarPropuestaApiV1PropuestasDeEstructuraPropuestaIdRechazarPost as useRechazarPropuesta,
} from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';
import type { CorreccionDeFabrica, PropuestaDeEstructura } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';

export const ESTADO_DE_LA_PROPUESTA: Record<string, string> = { pendiente: 'Pendiente', autorizada: 'Autorizada', rechazada: 'Rechazada' };
const ROL: Record<string, string> = { costos: 'Costos', control_obra: 'Control de obra' };

function num(n: number, dec = 4): string {
  return n.toLocaleString('es-MX', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

interface Props {
  readonly clave: string;
  readonly rol?: string | null;
  readonly deFabrica: readonly CorreccionDeFabrica[];
  readonly lista: readonly PropuestaDeEstructura[];
}

export function VersionesPropuestasDelElemento({ clave, rol, deFabrica, lista }: Props) {
  const puedeProponer = rol === 'control_obra' || rol === 'costos';
  const puedeAutorizar = rol === 'control_obra';
  const proponer = useProponerCorrecciones<ErrorApi>();
  const autorizar = useAutorizarPropuesta<ErrorApi>();
  const rechazar = useRechazarPropuesta<ErrorApi>();

  const recargar = () => queryClient.invalidateQueries();
  const fallo = (e: unknown, texto: string) => window.alert(e instanceof Error ? e.message : texto);
  const vigentes = new Set(lista.filter((p) => p.estado !== 'rechazada').map((p) => p.concepto_clave));
  const sinProponer = deFabrica.filter((c) => !vigentes.has(c.concepto_clave));

  return (
    <section className="mct__bloque" aria-label="Versiones propuestas" data-versiones-propuestas={clave}>
      <h3>Versiones propuestas del catálogo</h3>
      <p className="text-mute text-xs">
        El catálogo vigente sigue activo y no se edita. Costos propone y solo Control de obra autoriza; cada autorización crea la versión
        siguiente del concepto. La propuesta lleva los kg de anillo que calcula el elemento (perímetro del núcleo más gancho).
      </p>
      {sinProponer.map((c) => (
        <div key={c.concepto_clave} className="text-sm" data-sin-proponer={c.concepto_clave}>
          <span className="mono">{c.concepto_clave}</span> <span className="badge badge--outline">Sin proponer</span> {c.resumen}
        </div>
      ))}
      {lista.map((p) => (
        <div key={p.id} data-propuesta={p.concepto_clave} style={{ display: 'grid', gap: 3, padding: '4px 0', borderBottom: '1px solid var(--c-line-soft)' }}>
          <div className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
            <span className="mono">{p.concepto_clave}</span>
            <span className={p.estado === 'autorizada' ? 'badge badge--ok' : p.estado === 'rechazada' ? 'badge badge--danger' : 'badge badge--warn'}>
              {ESTADO_DE_LA_PROPUESTA[p.estado]}
              {p.version ? ` · versión ${p.version}` : ''}
            </span>
            <span className="text-mute text-xs">
              Nueva versión · propuso {p.propuso_nombre ?? '—'} ({ROL[p.propuso_rol ?? ''] ?? '—'})
            </span>
          </div>
          <div className="text-sm">{p.resumen}</div>
          {p.cambios.map((c) => (
            <div className="text-xs" key={c.insumo}>
              <span className="mono">{c.insumo}</span>: {num(c.antes)} → {num(c.despues)} {c.unidad}
            </div>
          ))}
          {p.motivo && <div className="text-xs">Motivo del rechazo: {p.motivo}</div>}
          {p.estado === 'pendiente' && puedeAutorizar && (
            <div className="row" style={{ gap: 6 }}>
              <button
                type="button"
                className="btn btn--sm"
                onClick={() =>
                  void autorizar.mutateAsync({ propuestaId: p.id }).then(recargar, (e: unknown) => fallo(e, 'No se pudo autorizar la propuesta.'))
                }
              >
                Autorizar
              </button>
              <button
                type="button"
                className="btn btn--sm"
                onClick={() => {
                  const motivo = window.prompt('¿Por qué se rechaza? (opcional)') ?? undefined;
                  void rechazar
                    .mutateAsync({ propuestaId: p.id, data: { motivo: motivo === '' ? null : motivo } })
                    .then(recargar, (e: unknown) => fallo(e, 'No se pudo rechazar la propuesta.'));
                }}
              >
                Rechazar
              </button>
            </div>
          )}
        </div>
      ))}
      {puedeProponer && sinProponer.length > 0 && (
        <div className="row" style={{ gap: 6, alignItems: 'center' }}>
          <button
            type="button"
            className="btn btn--sm"
            disabled={proponer.isPending}
            onClick={() => void proponer.mutateAsync({ clave }).then(recargar, (e: unknown) => fallo(e, 'No se pudo proponer la corrección.'))}
          >
            Proponer las correcciones del catálogo
          </button>
        </div>
      )}
    </section>
  );
}
