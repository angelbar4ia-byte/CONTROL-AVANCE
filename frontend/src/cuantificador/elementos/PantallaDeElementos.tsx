/**
 * El área de trabajo de la pestaña «Elementos»: la biblioteca plegable por categoría y subcategoría a la izquierda y
 * la tarjeta del elemento elegido a la derecha. Hoy la biblioteca trae un solo elemento paramétrico: el muro de
 * contención de piedra MCT-01010.
 */

import { useState } from 'react';

import { useBibliotecaDeElementosApiV1BibliotecaDeElementosGet } from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';

import { BibliotecaDeElementos } from './BibliotecaDeElementos';
import { TarjetaMuroContencion } from './TarjetaMuroContencion';

export function PantallaDeElementos() {
  const consulta = useBibliotecaDeElementosApiV1BibliotecaDeElementosGet();
  const categorias = consulta.data ?? [];
  const [elegida, setElegida] = useState<string | null>('MCT-01010');

  return (
    <section
      className="pantalla-elementos"
      role="tabpanel"
      id="area-elementos"
      aria-label="Elementos"
    >
      <aside className="pantalla-elementos__biblioteca">
        <div className="estacion__titulo">Biblioteca</div>
        {consulta.isLoading ? (
          <p className="text-mute text-sm" style={{ padding: 10 }}>
            Cargando la biblioteca…
          </p>
        ) : consulta.isError ? (
          <p className="text-sm" style={{ padding: 10 }} role="alert">
            No se pudo cargar la biblioteca de elementos.
          </p>
        ) : (
          <BibliotecaDeElementos categorias={categorias} elegida={elegida} onElegir={setElegida} />
        )}
      </aside>
      <div className="pantalla-elementos__tarjeta">
        {elegida === 'MCT-01010' ? (
          <TarjetaMuroContencion clave={elegida} />
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
