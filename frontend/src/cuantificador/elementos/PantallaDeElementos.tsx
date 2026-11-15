/**
 * El área de trabajo de la pestaña «Elementos»: solo la tarjeta del elemento elegido en la biblioteca (que vive en el
 * panel izquierdo). La biblioteca trae los muros de piedra MCT-01010 (contención) y CIM-01010 (cimentación) y los elementos
 * estructurales (trabes, contratrabes, nervaduras, zapata Z-1 y columna C-1).
 */

import { useBibliotecaDeElementosApiV1BibliotecaDeElementosGet } from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';

import { TarjetaElementoEstructural } from './TarjetaElementoEstructural';
import { TarjetaMuroCimentacion } from './TarjetaMuroCimentacion';
import { TarjetaMuroContencion } from './TarjetaMuroContencion';

const TIPOS_DE_ESTRUCTURA = new Set(['lineal_estructural', 'zapata_aislada', 'columna_de_concreto']);

export function PantallaDeElementos({ clave, rol }: { readonly clave: string | null; readonly rol?: string | null }) {
  const biblioteca = useBibliotecaDeElementosApiV1BibliotecaDeElementosGet();
  const tipo = biblioteca.data
    ?.flatMap((c) => c.subcategorias.flatMap((s) => s.elementos))
    .find((e) => e.clave === clave)?.tipo;
  return (
    <section className="pantalla-elementos" role="region" id="area-elementos" aria-label="Elementos">
      <div className="pantalla-elementos__tarjeta">
        {clave === 'MCT-01010' ? (
          <TarjetaMuroContencion clave={clave} />
        ) : clave && tipo && TIPOS_DE_ESTRUCTURA.has(tipo) ? (
          <TarjetaElementoEstructural key={clave} clave={clave} rol={rol} />
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
