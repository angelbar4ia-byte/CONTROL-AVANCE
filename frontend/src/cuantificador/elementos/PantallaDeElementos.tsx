/**
 * El área de trabajo de la pestaña «Elementos»: solo la tarjeta del elemento elegido en la biblioteca (que vive en el
 * panel izquierdo). Hoy la biblioteca trae un solo elemento paramétrico: el muro de contención de piedra MCT-01010.
 */

import { TarjetaMuroContencion } from './TarjetaMuroContencion';

export function PantallaDeElementos({ clave }: { readonly clave: string | null }) {
  return (
    <section className="pantalla-elementos" role="region" id="area-elementos" aria-label="Elementos">
      <div className="pantalla-elementos__tarjeta">
        {clave === 'MCT-01010' ? (
          <TarjetaMuroContencion clave={clave} />
        ) : (
          <div className="empty">
            <div className="empty-title">Elige un elemento de la biblioteca</div>
            <div className="empty-sub">Su tarjeta aparece aquí.</div>
          </div>
        )}
      </div>
    </section>
  );
}
