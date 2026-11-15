/**
 * El área de trabajo de la pestaña «Elementos»: solo la tarjeta del elemento elegido en la biblioteca (que vive en el
 * panel izquierdo): los muros de piedra MCT-01010 (contención) y CIM-01010 (cimentación) y los castillos, aparentes y columnas
 * forjadas.
 */

import { useBibliotecaDeElementosApiV1BibliotecaDeElementosGet } from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';

import { TarjetaEstructura } from './TarjetaEstructura';

import { TarjetaMuroCimentacion } from './TarjetaMuroCimentacion';
import { TarjetaMuroContencion } from './TarjetaMuroContencion';

export function PantallaDeElementos({ clave }: { readonly clave: string | null }) {
  const biblioteca = useBibliotecaDeElementosApiV1BibliotecaDeElementosGet();
  // Los castillos, aparentes y columnas forjadas (3A) comparten la tarjeta de estructura.
  const esDeEstructura = (biblioteca.data ?? []).some((c) =>
    c.subcategorias.some((s) => s.elementos.some((e) => e.clave === clave && e.tipo === 'estructura_de_catalogo')),
  );
  return (
    <section className="pantalla-elementos" role="region" id="area-elementos" aria-label="Elementos">
      <div className="pantalla-elementos__tarjeta">
        {clave === 'MCT-01010' ? (
          <TarjetaMuroContencion clave={clave} />
        ) : clave && esDeEstructura ? (
          <TarjetaEstructura clave={clave} />
        ) : clave === 'CIM-01010' ? (
          <TarjetaMuroCimentacion clave={clave} />
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
