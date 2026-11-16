/**
 * El área de trabajo de la pestaña «Paramétrico» (Ola 4B): los drivers de la obra (global, por obra o mixto) y el enlace de las
 * ranuras de elementos y plantillas con las partidas del árbol de la obra. Todo lo calcula y valida el servidor.
 */

import { EnlacesDeRanuras } from './EnlacesDeRanuras';
import { TablaDeDrivers } from './TablaDeDrivers';

interface Props {
  readonly obraId: string;
  readonly obraClave?: string | null;
  readonly rol?: string | null;
}

/** Q3: Costos y Control de obra editan los drivers y los enlaces; el servidor lo vuelve a exigir. */
export const puedeEditarElParametrico = (rol: string | null | undefined) => rol === 'costos' || rol === 'control_obra';

export function PantallaParametrica({ obraId, obraClave, rol }: Props) {
  const puedeEditar = puedeEditarElParametrico(rol);
  return (
    <section className="pantalla-elementos" role="region" id="area-parametrico" aria-label="Paramétrico">
      <div className="pantalla-elementos__tarjeta">
        <div className="mct mct--ancha">
          <header className="mct__cabecera">
            <div>
              <h2 className="mct__titulo">Paramétrico</h2>
              <p className="text-mute text-sm">
                Aquí viven los drivers y el enlace con el Presupuesto. No inventa conceptos: enlaza lo que los elementos y las plantillas necesitan
                con los conceptos que ya existen en el catálogo y en el árbol de la obra.
              </p>
            </div>
          </header>
          {obraId === '' ? (
            <div className="empty">
              <div className="empty-title">Elige una obra</div>
            </div>
          ) : (
            <>
              <TablaDeDrivers obraId={obraId} obraClave={obraClave} puedeEditar={puedeEditar} />
              <EnlacesDeRanuras obraId={obraId} puedeEditar={puedeEditar} />
            </>
          )}
        </div>
      </div>
    </section>
  );
}
