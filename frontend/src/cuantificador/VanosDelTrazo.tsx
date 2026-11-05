/**
 * Los vanos de una línea (un muro): puertas, ventanas, cancel, arcos y pasos. Cada vano descuenta de lo que
 * mide la línea —ancho × alto × piezas × caras en m², o su ancho en metros si llega al piso— y el servidor
 * recalcula las cantidades al colocarlo o quitarlo. Sin botón de guardar en las medidas: «Colocar» crea el vano.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getListarVanosApiV1TrazosTrazoIdVanosGetQueryKey,
  useColocarVanoApiV1TrazosTrazoIdVanosPost,
  useFijarHojaDelVanoApiV1VanosVanoIdHojaPut,
  useListarVanosApiV1TrazosTrazoIdVanosGet,
  useQuitarVanoApiV1VanosVanoIdDelete,
  useVerMuroApiV1TrazosTrazoIdMuroGet,
} from '@/api/generado/cuantificacion/cuantificacion';
import { queryClient } from '@/app/queryClient';

import { CARAS_POR_DEFECTO } from './trazoPeticion';
import { TIPOS_DE_VANO, claveSiguiente, descuentoDelVano, type DatosDeVano, type TipoDeVano } from './vanos';

interface Props {
  readonly trazoId: string;
  readonly puedeEditar: boolean;
  /** Pide elegir en el plano dónde va, con los datos que están escritos. */
  readonly onColocarEnPlano?: (datos: DatosDeVano) => void;
  /** Cambió lo que mide la línea: hay que volver a leer trazos y cantidades. */
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

export function VanosDelTrazo({ trazoId, puedeEditar, onColocarEnPlano, onCambio, onError }: Props) {
  const vanos = useListarVanosApiV1TrazosTrazoIdVanosGet(trazoId);
  const colocar = useColocarVanoApiV1TrazosTrazoIdVanosPost<ErrorApi>();
  const quitar = useQuitarVanoApiV1VanosVanoIdDelete<ErrorApi>();
  const hoja = useFijarHojaDelVanoApiV1VanosVanoIdHojaPut<ErrorApi>();
  // Los vanos descuentan por las caras que suma el muro (D-627).
  const caras = useVerMuroApiV1TrazosTrazoIdMuroGet(trazoId).data?.caras ?? CARAS_POR_DEFECTO;
  const [tipo, setTipo] = useState<TipoDeVano>('puerta');
  const [ancho, setAncho] = useState(String(TIPOS_DE_VANO.puerta.ancho));
  const [alto, setAlto] = useState(String(TIPOS_DE_VANO.puerta.alto));
  const [antepecho, setAntepecho] = useState('0');
  const [piezas, setPiezas] = useState('1');

  const lista = vanos.data ?? [];
  const recargar = () => {
    void queryClient.invalidateQueries({ queryKey: getListarVanosApiV1TrazosTrazoIdVanosGetQueryKey(trazoId) });
    // Los vanos que se dibujan sobre el plano también cambian.
    void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/vanos') });
  };

  function elegirTipo(nuevo: TipoDeVano) {
    setTipo(nuevo);
    setAncho(String(TIPOS_DE_VANO[nuevo].ancho));
    setAlto(String(TIPOS_DE_VANO[nuevo].alto));
    setAntepecho(String(TIPOS_DE_VANO[nuevo].antepecho));
  }

  const n = (texto: string) => Number(texto.replace(',', '.'));
  const valido = n(ancho) > 0 && n(alto) > 0 && n(antepecho) >= 0 && Number.isInteger(n(piezas)) && n(piezas) >= 1;

  async function ponerVano() {
    if (!valido) return;
    try {
      await colocar.mutateAsync({
        trazoId,
        data: {
          clave: claveSiguiente(tipo, lista.map((v) => v.clave)),
          tipo,
          ancho_m: n(ancho),
          alto_m: n(alto),
          antepecho_m: n(antepecho),
          piezas: n(piezas),
        },
      });
      recargar();
      onCambio(`${TIPOS_DE_VANO[tipo].nombre} colocada: descuenta de lo que mide el muro.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo colocar el vano.');
    }
  }

  /** La hoja de una puerta (D-632): bisagra, lado y apertura. Es dibujo: no cambia lo que descuenta. */
  async function cambiarHoja(v: { id: string; clave: string; bisagra?: number; lado_hoja?: number; apertura_grados?: number }, cambio: Partial<{ bisagra: number; lado_hoja: number; apertura_grados: number }>) {
    const siguiente = { bisagra: v.bisagra ?? 1, lado_hoja: v.lado_hoja ?? 1, apertura_grados: v.apertura_grados ?? 90, ...cambio };
    try {
      await hoja.mutateAsync({
        vanoId: v.id,
        data: {
          bisagra: siguiente.bisagra === -1 ? -1 : 1,
          lado_hoja: siguiente.lado_hoja === -1 ? -1 : 1,
          apertura_grados: siguiente.apertura_grados,
        },
      });
      recargar();
      void queryClient.invalidateQueries({ queryKey: getListarVanosApiV1TrazosTrazoIdVanosGetQueryKey(trazoId) });
      onCambio(`${v.clave}: hoja actualizada.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo cambiar la hoja.');
    }
  }

  async function quitarVano(id: string, clave: string) {
    try {
      await quitar.mutateAsync({ vanoId: id });
      recargar();
      onCambio(`${clave} quitado: el muro vuelve a medir ese descuento.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo quitar el vano.');
    }
  }

  return (
    <div role="group" aria-label="Vanos del muro" style={{ display: 'grid', gap: 4 }}>
      <div className="text-xs text-mute">Vanos · descuentan lo que mide el muro</div>
      {lista.length === 0 && <div className="text-mute text-xs">Sin vanos.</div>}
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 2 }}>
        {lista.map((v) => (
          <li key={v.id} className="row" data-vano={v.clave}>
            <span className="mono text-xs">
              {Number(v.piezas) > 1 ? `${v.piezas} × ` : ''}
              {v.clave}
            </span>
            <span className="text-mute text-xs">
              {Number(v.ancho_m)} × {Number(v.alto_m)} m · −
              {descuentoDelVano(Number(v.ancho_m), Number(v.alto_m), v.piezas, caras).toFixed(2)} m²
            </span>
            {puedeEditar && v.tipo === 'puerta' && (
              <span className="row" style={{ gap: 2 }} role="group" aria-label={`Hoja de ${v.clave}`}>
                <button type="button" className="btn btn--ghost btn--sm" title="La bisagra pasa al otro extremo" aria-label={`Bisagra de ${v.clave} al otro extremo`} disabled={hoja.isPending} onClick={() => void cambiarHoja(v, { bisagra: -(v.bisagra ?? 1) })}>
                  ⇄
                </button>
                <button type="button" className="btn btn--ghost btn--sm" title="Abre hacia el otro lado del muro" aria-label={`Hoja de ${v.clave} abre al otro lado`} disabled={hoja.isPending} onClick={() => void cambiarHoja(v, { lado_hoja: -(v.lado_hoja ?? 1) })}>
                  ⇅
                </button>
                {[0, 45, 90, 135].map((g) => (
                  <button
                    key={g}
                    type="button"
                    className={(v.apertura_grados ?? 90) === g ? 'btn btn--sm btn--primary' : 'btn btn--ghost btn--sm'}
                    aria-pressed={(v.apertura_grados ?? 90) === g}
                    aria-label={`Hoja de ${v.clave} abierta ${g} grados`}
                    disabled={hoja.isPending}
                    onClick={() => void cambiarHoja(v, { apertura_grados: g })}
                  >
                    {g}°
                  </button>
                ))}
              </span>
            )}
            {puedeEditar && (
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                aria-label={`Quitar ${v.clave}`}
                disabled={quitar.isPending}
                onClick={() => void quitarVano(v.id, v.clave)}
              >
                Quitar
              </button>
            )}
          </li>
        ))}
      </ul>
      {puedeEditar && (
        <div className="arbol-edicion__alta" role="group" aria-label="Colocar un vano">
          <select aria-label="Tipo de vano" value={tipo} onChange={(e) => elegirTipo(e.target.value as TipoDeVano)}>
            {(Object.keys(TIPOS_DE_VANO) as TipoDeVano[]).map((k) => (
              <option key={k} value={k}>
                {TIPOS_DE_VANO[k].nombre}
              </option>
            ))}
          </select>
          <input aria-label="Ancho del vano (m)" inputMode="decimal" style={{ width: 48 }} value={ancho} onChange={(e) => setAncho(e.target.value)} />
          <input aria-label="Alto del vano (m)" inputMode="decimal" style={{ width: 48 }} value={alto} onChange={(e) => setAlto(e.target.value)} />
          {tipo === 'ventana' && (
            <input aria-label="Del piso a la ventana (m)" inputMode="decimal" style={{ width: 48 }} value={antepecho} onChange={(e) => setAntepecho(e.target.value)} />
          )}
          <input aria-label="Piezas idénticas" inputMode="numeric" style={{ width: 36 }} value={piezas} onChange={(e) => setPiezas(e.target.value)} />
          <button type="button" className="btn btn--sm" disabled={!valido || colocar.isPending} onClick={() => void ponerVano()}>
            Colocar
          </button>
          {onColocarEnPlano && (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              disabled={!valido}
              title="Eliges en el plano el punto del muro donde va"
              onClick={() => onColocarEnPlano({ tipo, ancho: n(ancho), alto: n(alto), antepecho: n(antepecho), piezas: n(piezas) })}
            >
              En el plano
            </button>
          )}
        </div>
      )}
    </div>
  );
}
