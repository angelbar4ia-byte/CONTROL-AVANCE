/**
 * Cambiar el muro de una plantilla a otra sin perder lo medido: de la plantilla 1 (muro confinado, que propone los castillos) a la 2
 * («muros y cadena», donde los castillos reales se siembran uno por uno en el plano, cada uno de su tipo K) y viceversa.
 *
 * Antes de cambiar se dice qué cambia: el tipo, el material y la ubicación; los castillos estimados y las cadenas que dejan de contarse,
 * empiezan o siguen; los castillos ya sembrados; y lo que se conserva (la medición del muro y sus vanos). Los castillos sembrados solo se
 * quitan si se pide. Todo lo calcula el servidor: aquí solo se pinta.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useCambiarDePlantillaApiV1TrazosTrazoIdMuroPlantillaCambioPost,
  useVerCambioDePlantillaApiV1TrazosTrazoIdMuroPlantillaCambioGet,
} from '@/api/generado/artefacto-de-muros/artefacto-de-muros';
import { queryClient } from '@/app/queryClient';
import { fmtNum } from '@/lib/formato';

const NOMBRE_DEL_CAMPO: Readonly<Record<string, string>> = { tipo: 'Tipo de muro', material: 'Material', ubicacion: 'Ubicación' };
const NOMBRE_DEL_EFECTO: Readonly<Record<string, string>> = {
  deja: 'deja de contarse',
  nuevo: 'empieza a contarse',
  sigue: 'sigue igual',
};

interface Props {
  readonly trazoId: string;
  /** La plantilla a la que se quiere cambiar. */
  readonly haciaId: string;
  readonly onCancelar: () => void;
  readonly onCambiado: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

export function CambioDePlantilla({ trazoId, haciaId, onCancelar, onCambiado, onError }: Props) {
  const consulta = useVerCambioDePlantillaApiV1TrazosTrazoIdMuroPlantillaCambioGet<unknown>(
    trazoId,
    { hacia: haciaId },
    { query: { retry: false } },
  );
  const cambiar = useCambiarDePlantillaApiV1TrazosTrazoIdMuroPlantillaCambioPost<ErrorApi>();
  const [retirar, setRetirar] = useState(false);
  const d = consulta.data as import('@/api/generado/modelo').CambioDePlantillaRespuesta | undefined;
  if (consulta.isLoading) return <p className="text-mute text-xs">Revisando qué cambia…</p>;
  if (!d) {
    return (
      <p className="text-xs mct__error" role="alert">
        No se pudo ver qué cambia con esa plantilla.
      </p>
    );
  }

  async function confirmar() {
    try {
      const r = await cambiar.mutateAsync({ trazoId, data: { plantilla_id: haciaId, retirar_castillos: retirar } });
      void queryClient.invalidateQueries({
        predicate: (q) => /vanos|trazos|cuantificacion|elementos-parametricos|muro/.test(JSON.stringify(q.queryKey)),
      });
      onCambiado(
        `Plantilla cambiada a «${r.despues.nombre}»${r.retirados > 0 ? `: se retiraron ${r.retirados} castillo${r.retirados === 1 ? '' : 's'}` : ''}. Lo medido se conservó.`,
      );
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo cambiar la plantilla.');
    }
  }

  return (
    <div className="colocacion-plantilla" role="region" aria-label="Cambiar de plantilla" data-testid="cambio-de-plantilla">
      <div className="opciones__titulo">
        Cambiar de plantilla{d.de ? `: «${d.de.nombre}» → «${d.hacia.nombre}»` : `: «${d.hacia.nombre}»`}
      </div>
      {d.cambia.length > 0 && (
        <ul className="colocacion-plantilla__lista" aria-label="Lo que cambia del muro">
          {d.cambia.map((c) => (
            <li key={c.campo} data-cambia={c.campo}>
              {NOMBRE_DEL_CAMPO[c.campo] ?? c.campo}: <b>{c.de ?? 'sin definir'}</b> → <b>{c.a}</b>
            </li>
          ))}
        </ul>
      )}
      {d.efectos.length > 0 && (
        <ul className="colocacion-plantilla__lista" aria-label="Castillos estimados y cadenas">
          {d.efectos.map((e) => (
            <li key={e.uid} data-efecto={e.efecto} data-elemento={e.ref}>
              <b className="mono">{e.ref}</b> · {NOMBRE_DEL_EFECTO[e.efecto]}
              {e.clase === 'castillo' ? ` (${fmtNum(e.piezas)} pza estimadas)` : ` (${fmtNum(e.metros)} ml)`}
            </li>
          ))}
        </ul>
      )}
      {d.castillos_sembrados > 0 && (
        <p className="text-xs" data-testid="castillos-sembrados">
          {d.castillos_sembrados} castillo{d.castillos_sembrados === 1 ? '' : 's'} ya sembrado{d.castillos_sembrados === 1 ? '' : 's'} en el plano.
        </p>
      )}
      {d.avisos.map((a) => (
        <p key={a} className="text-xs mct__aviso" role="status">
          {a}
        </p>
      ))}
      <p className="text-mute text-xs">Se conserva: {d.conserva.join(' ')}</p>
      {d.castillos_sembrados > 0 && (
        <label className="mct__manual">
          <input type="checkbox" checked={retirar} onChange={(e) => setRetirar(e.target.checked)} />
          Retirar los castillos sembrados al cambiar
        </label>
      )}
      <div className="opciones__fila">
        <button type="button" className="btn btn--sm btn--primary" disabled={cambiar.isPending} onClick={() => void confirmar()}>
          Cambiar de plantilla
        </button>
        <button type="button" className="btn btn--ghost btn--sm" disabled={cambiar.isPending} onClick={onCancelar}>
          Cancelar
        </button>
      </div>
    </div>
  );
}
