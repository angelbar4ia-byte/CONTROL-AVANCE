/**
 * Marca el trazo elegido como un elemento paramétrico (D-604 §7): un punto es una pieza (castillo, zapata), una línea
 * son sus metros (trabe, cadena) y un área son sus m² (losa). El plano suma lo que llevan. En un castillo se pueden
 * fijar a mano los lados de cimbra (aislado 4, junto a un vano 3, en muro continuo 2). Sin botón de guardar.
 */

import type { ErrorApi } from '@/api/cliente';
import {
  getElementosDelPlanoApiV1PlanosPlanoIdElementosParametricosGetQueryKey,
  usePonerElementoEnTrazoApiV1TrazosTrazoIdElementoParametricoPut,
  useListarElementosParametricosApiV1ElementosParametricosGet,
  useElementosDelPlanoApiV1PlanosPlanoIdElementosParametricosGet,
} from '@/api/generado/elementos-parametricos/elementos-parametricos';
import { queryClient } from '@/app/queryClient';

import { ladosDeCimbra, tiposParaGeometria, type TipoParametrico } from './parametricos';

interface Props {
  readonly planoId: string;
  readonly trazoId: string;
  readonly geometria: string;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

export function ElementoDelTrazo({ planoId, trazoId, geometria, onCambio, onError }: Props) {
  const tipos = tiposParaGeometria(geometria);
  const catalogo = useListarElementosParametricosApiV1ElementosParametricosGet({ query: { enabled: tipos.length > 0 } });
  const delPlano = useElementosDelPlanoApiV1PlanosPlanoIdElementosParametricosGet(planoId, { query: { enabled: tipos.length > 0 } });
  const poner = usePonerElementoEnTrazoApiV1TrazosTrazoIdElementoParametricoPut<ErrorApi>();

  const posibles = (catalogo.data ?? []).filter((e) => tipos.includes(e.tipo as TipoParametrico));
  const actual = delPlano.data?.trazos.find((t) => t.trazo_id === trazoId);
  const elegido = posibles.find((e) => e.id === actual?.elemento_id);
  if (tipos.length === 0 || (posibles.length === 0 && !actual)) return null;

  async function cambiar(elementoId: string | null, lados: number | null) {
    try {
      await poner.mutateAsync({ trazoId, data: { elemento_id: elementoId, lados_cimbra: lados } });
      void queryClient.invalidateQueries({
        queryKey: getElementosDelPlanoApiV1PlanosPlanoIdElementosParametricosGetQueryKey(planoId),
      });
      onCambio(elementoId ? 'Trazo marcado como elemento: el plano suma su receta.' : 'Trazo sin elemento.');
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo marcar el trazo.');
    }
  }

  const lados = elegido ? ladosDeCimbra(elegido.tipo as TipoParametrico) : [];
  return (
    <div className="row" role="group" aria-label="Elemento paramétrico del trazo">
      <select
        aria-label="Elemento paramétrico"
        value={actual?.elemento_id ?? ''}
        disabled={poner.isPending}
        onChange={(e) => void cambiar(e.target.value || null, null)}
      >
        <option value="">Sin elemento</option>
        {posibles.map((e) => (
          <option key={e.id} value={e.id}>
            {e.clave} · {e.nombre}
          </option>
        ))}
      </select>
      {lados.length > 1 && elegido && (
        <select
          aria-label="Lados de cimbra"
          value={actual?.lados_cimbra ?? ''}
          disabled={poner.isPending}
          onChange={(e) => void cambiar(elegido.id, e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">Cimbra: la del elemento</option>
          {lados.map((l) => (
            <option key={l} value={l}>
              {l} lados
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
