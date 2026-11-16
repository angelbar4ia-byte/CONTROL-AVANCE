/**
 * Los drivers del Paramétrico que leyó un cálculo, con el valor que usó y de dónde salió (Ola 4, «drivers conectados»): el que
 * teclea la tarjeta, el de la OBRA (y cuál driver es), el global de la organización o el valor por defecto del cálculo. Solo pinta
 * lo que el servidor respondió (`drivers_usados`).
 */

import type { DriverUsadoRespuesta } from '@/api/generado/modelo';

export const FUENTE_DEL_VALOR: Record<string, { texto: string; clase: string }> = {
  peticion: { texto: 'tecleado aquí', clase: 'badge badge--outline' },
  obra: { texto: 'driver de la obra', clase: 'badge badge--info' },
  global: { texto: 'driver global', clase: 'badge badge--ok' },
  defecto: { texto: 'valor por defecto', clase: 'badge badge--outline' },
};

interface Props {
  readonly usados: readonly DriverUsadoRespuesta[] | undefined;
  /** La obra del cálculo: sin ella los valores no vienen de ningún driver de obra. */
  readonly obraClave?: string | null;
  readonly hayObra: boolean;
}

export function DriversUsadosDelCalculo({ usados, obraClave, hayObra }: Props) {
  if (!usados || usados.length === 0) return null;
  const deObra = usados.filter((u) => u.fuente === 'obra' || u.fuente === 'global').length;
  return (
    <section className="mct__bloque" aria-label="Drivers que usa este cálculo" data-drivers-usados>
      <h3>Drivers que usa este cálculo</h3>
      <p className="text-mute text-xs">
        {hayObra
          ? `Los valores salen de los drivers de la obra${obraClave ? ` ${obraClave}` : ''} (Paramétrico); lo que teclees aquí manda sobre ellos.${
              deObra === 0 ? ' Esta obra no ha cambiado ninguno: todos valen lo de partida.' : ''
            }`
          : 'Sin obra elegida: valen los valores por defecto del cálculo.'}
      </p>
      <div className="mct__tabla-caja">
        <table className="mct__tabla" aria-label="Drivers usados">
          <thead>
            <tr>
              <th>Driver</th>
              <th className="n">Valor</th>
              <th>De dónde sale</th>
            </tr>
          </thead>
          <tbody>
            {usados.map((u) => {
              const f = FUENTE_DEL_VALOR[u.fuente] ?? { texto: u.fuente, clase: 'badge' };
              return (
                <tr key={u.clave} data-driver-usado={u.clave} data-fuente={u.fuente}>
                  <td>
                    {u.nombre} <span className="text-mute text-xs mono">{u.clave}</span>
                  </td>
                  <td className="n">
                    {u.valor} {u.unidad}
                  </td>
                  <td>
                    <span className={f.clase}>{f.texto}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
