/**
 * La fachada del plano por BANDAS de altura (F1): los m² de cara exterior de los muros REALES, en la banda baja (0 a 3.00), la media («+3.00»,
 * de 3.00 a 4.20) y el resto. Cada m² cae en una sola banda. Sale de las zonas de losa, los puntos de nivel exterior, las partes con caras, la
 * ubicación y las puertas y ventanas de cada muro (los castillos colocados NO se restan como vanos): no hay selector ni cantidad capturada aparte. Solo muestra lo que calcula el servidor; no cobra nada.
 */

import { useEffect } from 'react';

import { useFachadaPorBandasApiV1PlanosPlanoIdFachadaPorBandasGet } from '@/api/generado/fachada/fachada';
import { fmtNum } from '@/lib/formato';


const ORIGEN: Record<string, string> = { partes_del_muro: 'partes del muro', zona_de_losa: 'zona de losa', ubicacion: 'ubicación' };

export function PanelDeFachadaPorBandas({ planoId, huella }: { readonly planoId: string; readonly huella?: unknown }) {
  const consulta = useFachadaPorBandasApiV1PlanosPlanoIdFachadaPorBandasGet(planoId, { query: { enabled: planoId !== '' } });
  const { refetch } = consulta;
  // Sigue a los muros reales: cuando los trazos o los vanos del plano se vuelven a leer (cualquier cambio de altura, ubicación, largo o vano), se
  // vuelve a pedir. `huella` es lo que la pantalla ya sabe que cambió (la hora de lectura de los trazos y de los vanos).
  useEffect(() => {
    if (planoId !== '') void refetch();
  }, [planoId, huella, refetch]);
  const f = consulta.data;
  return (
    <section className="zonas-losa" aria-label="Fachada por bandas" data-fachada-por-bandas>
      <div className="estacion__subencabezado">
        <span className="estacion__subtitulo">Fachada por bandas de altura</span>
      </div>
      {!f ? (
        <div className="text-mute text-sm">{consulta.isError ? 'No se pudo calcular la fachada.' : 'Calculando la fachada…'}</div>
      ) : f.muros.length === 0 ? (
        <div className="text-mute text-sm">Sin muros con cara exterior. Pon la ubicación del muro, sus caras por parte o dibuja su zona de losa.</div>
      ) : (
        <table className="mct__tabla" aria-label="Fachada por banda de altura">
          <thead>
            <tr>
              <th>Banda</th>
              <th className="n">Bruto m²</th>
              <th className="n">Vanos m²</th>
              <th className="n">Neto m²</th>
            </tr>
          </thead>
          <tbody>
            {f.bandas.map((b) => (
              <tr key={b.banda} data-fachada-banda={b.banda}>
                <td>{b.nombre}</td>
                <td className="n">{fmtNum(b.bruto_m2)}</td>
                <td className="n">{fmtNum(b.vanos_m2)}</td>
                <td className="n" data-neto>
                  {fmtNum(b.neto_m2)}
                </td>
              </tr>
            ))}
            <tr data-fachada-total>
              <th>Total</th>
              <td className="n">{fmtNum(f.bruto_m2)}</td>
              <td className="n">{fmtNum(f.vanos_m2)}</td>
              <td className="n" data-neto>
                {fmtNum(f.neto_m2)}
              </td>
            </tr>
          </tbody>
        </table>
      )}
      {f && f.muros.length > 0 && (
        <p className="text-mute text-xs" data-fachada-nota-vanos>
          Vanos: solo puertas y ventanas; los castillos colocados no se restan.
        </p>
      )}
      {f && f.muros.length > 0 && (
        <p className="text-mute text-xs">
          {f.muros.length} muro{f.muros.length === 1 ? '' : 's'}: la cara exterior sale de {[...new Set(f.muros.map((m) => ORIGEN[m.origen_de_caras] ?? m.origen_de_caras))].join(', ')}.
        </p>
      )}
      {f && f.muros_sin_cara_exterior.length > 0 && (
        <p className="text-xs mct__aviso" role="status" data-fachada-sin-cara>
          {f.muros_sin_cara_exterior.length} muro{f.muros_sin_cara_exterior.length === 1 ? '' : 's'} sin cara exterior definida no se cuenta
          {f.muros_sin_cara_exterior.length === 1 ? '' : 'n'}: pon su ubicación, sus caras por parte o dibuja su zona de losa.
        </p>
      )}
    </section>
  );
}
