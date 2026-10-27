/**
 * El cuadro de datos: un resumen de las medidas de lo que se ve en pantalla (los trazos visibles,
 * es decir, ya con el filtro de conceptos aplicado). Arriba, lo que miden los trazos con su
 * geometría y la escala del plano; abajo, las cantidades por concepto que calculó el servidor.
 */

import { X } from 'lucide-react';

import { fmtNum } from '@/lib/formato';
import { fmtMedida } from './etiquetas';
import type { Resumen } from './resumen';
import { etiquetaMedida } from './reglas';

interface Props {
  readonly resumen: Resumen;
  readonly nombreDeNodo: (tipo: string, id: string) => string;
  readonly calibrada: boolean;
  readonly onCerrar: () => void;
}

export function CuadroDeDatos({ resumen, nombreDeNodo, calibrada, onCerrar }: Props) {
  const { lineal, superficie } = resumen.unidades;
  const filas: readonly [string, string][] = [
    ['Trazos en pantalla', String(resumen.trazos)],
    [`Áreas (${resumen.areas.n})`, `${fmtMedida(resumen.areas.total)} ${superficie}`],
    [`Huecos (${resumen.huecos.n})`, resumen.huecos.n === 0 ? `0.00 ${superficie}` : `−${fmtMedida(resumen.huecos.total)} ${superficie}`],
    ['Área de las formas estampadas', `${fmtMedida(resumen.formas.total)} ${superficie}`],
    [`Líneas (${resumen.lineas.n})`, `${fmtMedida(resumen.lineas.longitud)} ${lineal}`],
    ['Área de muros (largo × grosor)', `${fmtMedida(resumen.lineas.areaMuros)} ${superficie}`],
    ['Puntos contados', String(resumen.puntos)],
  ];
  return (
    <section className="datos" aria-label="Cuadro de datos">
      <header className="datos__cabecera">
        <strong>Cuadro de datos</strong>
        <button type="button" className="btn-icono" aria-label="Cerrar el cuadro de datos" onClick={onCerrar}>
          <X size={15} aria-hidden />
        </button>
      </header>
      <div className="datos__cuerpo">
        <div className="datos__subtitulo">Por concepto</div>
        {resumen.porNodo.length === 0 ? (
          <p className="text-mute text-xs">Ningún trazo en pantalla alimenta un concepto.</p>
        ) : (
          <table className="table datos__tabla datos__tabla--conceptos" aria-label="Cantidades por concepto">
            <thead>
              <tr>
                <th>Concepto</th>
                <th className="is-num">Trazos</th>
                <th className="is-num">Cantidad</th>
              </tr>
            </thead>
            <tbody>
              {resumen.porNodo.map((n) => (
                <tr key={n.clave}>
                  <td title={nombreDeNodo(n.tipoNodo, n.nodoId)} className="datos__concepto">
                    {nombreDeNodo(n.tipoNodo, n.nodoId)}
                  </td>
                  <td className="is-num">{n.trazos}</td>
                  <td className="is-num mono">
                    {Object.entries(n.medidas)
                      .map(([m, c]) => `${fmtNum(c)} ${etiquetaMedida(m).toLowerCase()}`)
                      .join(' · ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className="datos__subtitulo datos__subtitulo--menor">En pantalla</div>
        <table className="table datos__tabla datos__tabla--totales" aria-label="Medidas de la pantalla">
          <tbody>
            {filas.map(([k, v]) => (
              <tr key={k}>
                <th scope="row">{k}</th>
                <td className="is-num mono" data-testid={`dato-${k.split(' (')[0]}`}>
                  {v}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!calibrada && (
          <p className="text-mute text-xs">
            El plano no está calibrado: las medidas están en unidades de plano, no en metros.
          </p>
        )}
      </div>
    </section>
  );
}
