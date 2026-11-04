/**
 * Qué enlace de este trazo se rehízo porque cambió la unidad de su concepto (D-623): el viejo queda como evidencia y
 * el nuevo mide con lo que cabe en la unidad nueva. Un punto no cabe en m²: queda marcado sin enlace nuevo.
 */

import { useMarcasDelTrazoApiV1TrazosTrazoIdCambiosDeUnidadGet } from '@/api/generado/cambio-de-unidad/cambio-de-unidad';

import { NOMBRE_DE_MEDIDA } from './marcasDeUnidad';

export function MarcasDeUnidadDelTrazo({ trazoId }: { readonly trazoId: string }) {
  const marcas = useMarcasDelTrazoApiV1TrazosTrazoIdCambiosDeUnidadGet(trazoId, { query: { retry: false } });
  if (!marcas.data || marcas.data.length === 0) return null;
  return (
    <div role="group" aria-label="Cambios de unidad de este trazo" style={{ display: 'grid', gap: 2 }}>
      {marcas.data.map((m) => (
        <div key={m.enlace_viejo_id} className="text-xs text-mute" data-marca-unidad>
          <span className="badge badge--outline">Cambio de unidad</span>{' '}
          {m.unidad_anterior ?? '—'} → {m.unidad_nueva}:{' '}
          {m.medida_nueva
            ? `su enlace de ${NOMBRE_DE_MEDIDA[m.medida_vieja] ?? m.medida_vieja} se rehízo como ${NOMBRE_DE_MEDIDA[m.medida_nueva] ?? m.medida_nueva} (el anterior queda como evidencia).`
            : `su enlace de ${NOMBRE_DE_MEDIDA[m.medida_vieja] ?? m.medida_vieja} ya no cabe en la unidad nueva: no mide.`}
        </div>
      ))}
    </div>
  );
}
