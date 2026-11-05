/**
 * «Elemento colocado»: el detalle de un vano elegido en el plano (puerta, ventana, cancel, arco o paso). Lo que es, lo
 * que descuenta y dónde está; y lo que se puede cambiar: las piezas idénticas, la hoja de una puerta (lado, bisagra y
 * apertura), ir al muro o quitarlo. Mover y ensanchar se hace con las asas en el plano: la versión sigue al ancho.
 */

import { useEffect, useState } from 'react';

import type { VanoEnPlanoRespuesta } from '@/api/generado/modelo';

import type { CambioDeHoja } from './accionesDeVano';
import { TIPOS_DE_VANO, descuentoDelVano, type TipoDeVano } from './vanos';

/** Aperturas de la hoja que se ofrecen (D-632). */
export const APERTURAS_DE_HOJA = [0, 45, 90, 135] as const;

interface Props {
  readonly vano: VanoEnPlanoRespuesta;
  /** Cómo se llama el muro, la línea o el área donde está. */
  readonly colocadoEn: string;
  /** Por cuántas caras cuenta el muro (el descuento es ancho × alto × piezas × caras). */
  readonly caras: number;
  readonly puedeEditar: boolean;
  readonly onPiezas: (piezas: number) => void;
  readonly onHoja: (cambio: CambioDeHoja) => void;
  readonly onIrAlTrazo: () => void;
  readonly onQuitar: () => void;
}

function Fila({ etiqueta, valor }: { readonly etiqueta: string; readonly valor: string }) {
  return (
    <>
      <span className="text-mute text-sm">{etiqueta}</span>
      <span className="mono text-sm" style={{ textAlign: 'right' }}>
        {valor}
      </span>
    </>
  );
}

export function VanoElegido({ vano, colocadoEn, caras, puedeEditar, onPiezas, onHoja, onIrAlTrazo, onQuitar }: Props) {
  const tipo = (vano.tipo in TIPOS_DE_VANO ? vano.tipo : 'puerta') as TipoDeVano;
  const datos = TIPOS_DE_VANO[tipo];
  const ancho = Number(vano.ancho_m);
  const alto = Number(vano.alto_m);
  const antepecho = Number(vano.antepecho_m ?? 0);
  const posicion = vano.posicion_m == null ? null : Number(vano.posicion_m);
  const descuento = descuentoDelVano(ancho, alto, vano.piezas, caras);

  const [piezas, setPiezas] = useState(String(vano.piezas));
  useEffect(() => setPiezas(String(vano.piezas)), [vano.id, vano.piezas]);

  const bisagra = (vano.bisagra ?? 1) === -1 ? -1 : 1;
  const ladoHoja = (vano.lado_hoja ?? 1) === -1 ? -1 : 1;
  const apertura = vano.apertura_grados ?? 90;
  const chip = (activo: boolean, etiqueta: string, alPulsar: () => void) => (
    <button type="button" className={activo ? 'chip is-active' : 'chip'} aria-pressed={activo} onClick={alPulsar}>
      {etiqueta}
    </button>
  );

  return (
    <div className="col gap-8" role="group" aria-label="Elemento colocado" data-testid="vano-elegido">
      <div className="kv" style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '4px 8px' }}>
        <Fila etiqueta="Elemento" valor={vano.clave} />
        <Fila etiqueta="Tipo" valor={datos.nombre} />
        <Fila etiqueta="Ancho" valor={`${ancho} m`} />
        <Fila etiqueta="Alto" valor={`${alto} m`} />
        {tipo === 'ventana' && <Fila etiqueta="Del piso a la ventana" valor={`${antepecho} m`} />}
        <Fila etiqueta="Piezas" valor={String(vano.piezas)} />
        <Fila etiqueta="Descuento" valor={`−${descuento.toFixed(2)} m²`} />
        <Fila etiqueta="Llega al piso" valor={antepecho === 0 && datos.llegaAlPiso ? 'sí' : 'no'} />
        <Fila etiqueta="Colocado en" valor={colocadoEn} />
        <Fila etiqueta="Posición" valor={posicion === null ? '—' : `${posicion.toFixed(2)} m desde el inicio`} />
      </div>

      {puedeEditar && (
        <>
          <div className="text-xs text-mute">Edición</div>
          <label className="opciones__campo" htmlFor="vano-piezas">
            <span>Piezas idénticas</span>
            <input
              id="vano-piezas"
              className="input"
              inputMode="numeric"
              value={piezas}
              onChange={(e) => {
                setPiezas(e.target.value);
                const n = Number(e.target.value);
                if (Number.isInteger(n) && n >= 1 && n <= 999) onPiezas(n);
              }}
            />
          </label>

          {tipo === 'puerta' && (
            <>
              <div className="text-xs text-mute">Hoja</div>
              <div className="opciones__fila" role="group" aria-label="Lado de la hoja">
                {chip(ladoHoja === -1, 'Abre al otro lado', () => onHoja({ lado_hoja: -1 }))}
                {chip(ladoHoja === 1, 'Abre al lado inicial', () => onHoja({ lado_hoja: 1 }))}
              </div>
              <div className="opciones__fila" role="group" aria-label="Bisagra">
                {chip(bisagra === -1, 'Bisagra izquierda', () => onHoja({ bisagra: -1 }))}
                {chip(bisagra === 1, 'Bisagra derecha', () => onHoja({ bisagra: 1 }))}
              </div>
              <div className="opciones__fila" role="group" aria-label="Apertura de la hoja">
                {APERTURAS_DE_HOJA.map((g) => chip(apertura === g, `${g}°`, () => onHoja({ apertura_grados: g })))}
              </div>
            </>
          )}
        </>
      )}

      <div className="row" style={{ gap: 6 }}>
        <button type="button" className="btn btn--sm" onClick={onIrAlTrazo}>
          Ir al trazo
        </button>
        {puedeEditar && (
          <button type="button" className="btn btn--sm btn--danger" onClick={onQuitar}>
            Quitar el vano
          </button>
        )}
      </div>
      <div className="text-mute text-xs">
        Arrastra sus asas en el plano para moverlo o cambiar su ancho: la versión sigue al ancho.
      </div>
    </div>
  );
}
