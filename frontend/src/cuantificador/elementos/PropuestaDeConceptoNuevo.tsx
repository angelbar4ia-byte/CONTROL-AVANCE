/**
 * El estado de un concepto NUEVO propuesto (clave provisional) y lo que cada rol puede hacer con él: Costos o Control de obra lo proponen, solo
 * Control de obra lo autoriza o lo rechaza. Lo usan la tarjeta de la losa (su concepto por m², regla F7) y la de una trabe (su colado y cimbra por
 * ml con el destajo por ml sin importe, D8). Sin precios ni destajos con importe: la propuesta solo nombra el concepto. El catálogo no se edita.
 */

import type { ErrorApi } from '@/api/cliente';
import {
  useAutorizarPropuestaApiV1PropuestasDeEstructuraPropuestaIdAutorizarPost as useAutorizarPropuesta,
  useRechazarPropuestaApiV1PropuestasDeEstructuraPropuestaIdRechazarPost as useRechazarPropuesta,
} from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';
import type { PropuestaDeEstructura } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';

import { ESTADO_DE_LA_PROPUESTA } from './VersionesPropuestasDelElemento';

const ROL: Record<string, string> = { costos: 'Costos', control_obra: 'Control de obra' };

interface Props {
  /** La clave provisional del concepto nuevo (EJ-800, EJ-701…). */
  readonly conceptoClave: string;
  /** Todas las propuestas del elemento (la lista que devuelve el servidor). */
  readonly lista: readonly PropuestaDeEstructura[];
  readonly rol?: string | null;
  readonly textoDelBoton: string;
  readonly proponiendo: boolean;
  readonly onProponer: () => void;
}

/** La propuesta vigente (pendiente o autorizada) del concepto nuevo, si la hay. */
export function propuestaVigenteDe(lista: readonly PropuestaDeEstructura[], conceptoClave: string): PropuestaDeEstructura | undefined {
  return lista.find((p) => p.clase === 'concepto_nuevo' && p.concepto_clave === conceptoClave && p.estado !== 'rechazada');
}

export function PropuestaDeConceptoNuevo({ conceptoClave, lista, rol, textoDelBoton, proponiendo, onProponer }: Props) {
  const puedeProponer = rol === 'control_obra' || rol === 'costos';
  const puedeAutorizar = rol === 'control_obra';
  const autorizar = useAutorizarPropuesta<ErrorApi>();
  const rechazar = useRechazarPropuesta<ErrorApi>();
  const recargar = () => queryClient.invalidateQueries();
  const fallo = (e: unknown, texto: string) => window.alert(e instanceof Error ? e.message : texto);
  const vigente = propuestaVigenteDe(lista, conceptoClave);
  const rechazada = lista.find((p) => p.clase === 'concepto_nuevo' && p.concepto_clave === conceptoClave && p.estado === 'rechazada');

  return (
    <div className="text-sm" data-concepto-propuesto={conceptoClave} data-estado-propuesta={vigente?.estado ?? 'sin_proponer'}>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        <span className="mono">{conceptoClave}</span>
        <span className="badge badge--outline" title="Clave provisional: Control de obra la confirma al autorizar">
          provisional
        </span>
        {vigente ? (
          <span className={vigente.estado === 'autorizada' ? 'badge badge--ok' : 'badge badge--warn'}>
            {ESTADO_DE_LA_PROPUESTA[vigente.estado]}
            {vigente.version ? ` · versión ${vigente.version}` : ''}
          </span>
        ) : (
          <span className="badge badge--warn">Sin proponer</span>
        )}
        {vigente && (
          <span className="text-mute text-xs">
            propuso {vigente.propuso_nombre ?? '—'} ({ROL[vigente.propuso_rol ?? ''] ?? '—'})
          </span>
        )}
      </div>
      {!vigente && rechazada?.motivo && <div className="text-xs">Se rechazó la anterior: {rechazada.motivo}</div>}
      {vigente?.estado === 'pendiente' && puedeAutorizar && (
        <div className="row" style={{ gap: 6 }}>
          <button
            type="button"
            className="btn btn--sm"
            onClick={() => void autorizar.mutateAsync({ propuestaId: vigente.id }).then(recargar, (e: unknown) => fallo(e, 'No se pudo autorizar la propuesta.'))}
          >
            Autorizar
          </button>
          <button
            type="button"
            className="btn btn--sm"
            onClick={() => {
              const motivo = window.prompt('¿Por qué se rechaza? (opcional)') ?? undefined;
              void rechazar
                .mutateAsync({ propuestaId: vigente.id, data: { motivo: motivo === '' ? null : motivo } })
                .then(recargar, (e: unknown) => fallo(e, 'No se pudo rechazar la propuesta.'));
            }}
          >
            Rechazar
          </button>
        </div>
      )}
      {!vigente && puedeProponer && (
        <button type="button" className="btn btn--sm" disabled={proponiendo} onClick={onProponer}>
          {textoDelBoton}
        </button>
      )}
      {!vigente && !puedeProponer && <div className="text-mute text-xs">Lo propone Costos o Control de obra.</div>}
    </div>
  );
}
