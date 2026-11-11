/**
 * Lo que se le puede hacer a un vano ya colocado desde el plano o desde su panel: correrlo por el muro, cambiarle el
 * ancho (la versión del catálogo sigue al ancho), las piezas, la hoja de una puerta, o quitarlo. Todo se puede
 * deshacer y rehacer; al deshacer un «quitar» el vano nace con id nuevo y `vigente` lleva del viejo al nuevo.
 */

import { useRef } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useCambiarAnchoDelVanoApiV1VanosVanoIdAnchoPatch,
  useCambiarPiezasDelVanoApiV1VanosVanoIdPiezasPatch,
  useColocarVanoApiV1TrazosTrazoIdVanosPost,
  useFijarHojaDelVanoApiV1VanosVanoIdHojaPut,
  useMoverVanoApiV1VanosVanoIdPosicionPatch,
  useQuitarVanoApiV1VanosVanoIdDelete,
} from '@/api/generado/cuantificacion/cuantificacion';
import type { VanoEnPlanoRespuesta } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';

import type { Historial } from './historial';

export type CambioDeHoja = Partial<{ bisagra: number; lado_hoja: number; apertura_grados: number }>;

interface Entradas {
  readonly historial: Historial;
  readonly alCambiarHistorial: () => void;
  readonly avisar: (mensaje: string) => void;
  /** Cambió lo que miden los trazos: volver a leerlos. */
  readonly alCambiarMedidas: () => void;
  readonly vanos: readonly VanoEnPlanoRespuesta[];
}

const num = (x: unknown): number => Number(x);
const redondear = (x: number) => Number(x.toFixed(3));

export function useAccionesDeVano({ historial, alCambiarHistorial, avisar, alCambiarMedidas, vanos }: Entradas) {
  const mover = useMoverVanoApiV1VanosVanoIdPosicionPatch<ErrorApi>();
  const ancho = useCambiarAnchoDelVanoApiV1VanosVanoIdAnchoPatch<ErrorApi>();
  const piezas = useCambiarPiezasDelVanoApiV1VanosVanoIdPiezasPatch<ErrorApi>();
  const hoja = useFijarHojaDelVanoApiV1VanosVanoIdHojaPut<ErrorApi>();
  const quitarMut = useQuitarVanoApiV1VanosVanoIdDelete<ErrorApi>();
  const colocar = useColocarVanoApiV1TrazosTrazoIdVanosPost<ErrorApi>();
  const alias = useRef(new Map<string, string>());

  const vigente = (id: string): string => {
    let actual = id;
    while (alias.current.has(actual)) actual = alias.current.get(actual) as string;
    return actual;
  };
  const refrescar = () => {
    void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/vanos') });
    alCambiarMedidas();
  };
  const falla = (que: string, err: unknown) => avisar(`No se pudo ${que}: ${err instanceof Error ? err.message : 'error'}`);

  const posicionDe = (v: VanoEnPlanoRespuesta) => num(v.posicion_m ?? 0);
  const hojaDe = (v: VanoEnPlanoRespuesta) => ({
    bisagra: (v.bisagra ?? 1) === -1 ? -1 : 1,
    lado_hoja: (v.lado_hoja ?? 1) === -1 ? -1 : 1,
    apertura_grados: v.apertura_grados ?? 90,
  });

  async function fijarPosicion(id: string, metros: number) {
    await mover.mutateAsync({ vanoId: vigente(id), data: { posicion_m: redondear(Math.max(0, metros)) } });
  }
  async function fijarAncho(id: string, metros: number) {
    return ancho.mutateAsync({ vanoId: vigente(id), data: { ancho_m: redondear(Math.max(0.1, metros)) } });
  }

  /** Correrlo por su muro: `metros` desde el inicio de la línea. No cambia lo que mide. */
  async function moverA(v: VanoEnPlanoRespuesta, metros: number) {
    const antes = posicionDe(v);
    const despues = redondear(Math.max(0, metros));
    if (Math.abs(despues - antes) < 1e-6) return;
    try {
      await fijarPosicion(v.id, despues);
      historial.registrar({
        etiqueta: 'vano movido',
        deshacer: () => fijarPosicion(v.id, antes).then(refrescar),
        rehacer: () => fijarPosicion(v.id, despues).then(refrescar),
      });
      alCambiarHistorial();
      refrescar();
      avisar(`${v.clave} movido sobre el muro: ${despues.toFixed(2)} m desde el inicio.`);
    } catch (err) {
      falla('mover el vano', err);
    }
  }

  /** Cambiarle el ancho. La versión sigue al ancho; `corrimientoM` desplaza el centro (el extremo contrario queda fijo). */
  async function cambiarAncho(v: VanoEnPlanoRespuesta, metros: number, corrimientoM = 0) {
    const antesAncho = num(v.ancho_m);
    const antesPos = posicionDe(v);
    const despuesAncho = redondear(Math.max(0.1, metros));
    const despuesPos = redondear(Math.max(0, antesPos + corrimientoM));
    if (Math.abs(despuesAncho - antesAncho) < 1e-6) return;
    try {
      const r = await fijarAncho(v.id, despuesAncho);
      if (Math.abs(despuesPos - antesPos) > 1e-6) await fijarPosicion(v.id, despuesPos);
      historial.registrar({
        etiqueta: 'vano redimensionado',
        deshacer: async () => {
          await fijarAncho(v.id, antesAncho);
          await fijarPosicion(v.id, antesPos);
          refrescar();
        },
        rehacer: async () => {
          await fijarAncho(v.id, despuesAncho);
          await fijarPosicion(v.id, despuesPos);
          refrescar();
        },
      });
      alCambiarHistorial();
      refrescar();
      const cambioDeVersion =
        r.clave && r.clave !== v.clave ? (r.version_nueva ? ` Versión nueva ${r.clave} en el catálogo.` : ` Corresponde a la versión ${r.clave}.`) : '';
      avisar(`${r.clave ?? v.clave}: ahora de ${despuesAncho} m de ancho.${cambioDeVersion}`);
    } catch (err) {
      falla('cambiar el ancho', err);
    }
  }

  async function cambiarPiezas(v: VanoEnPlanoRespuesta, cuantas: number) {
    const antes = v.piezas;
    if (!Number.isInteger(cuantas) || cuantas < 1 || cuantas === antes) return;
    const poner = (n: number) => piezas.mutateAsync({ vanoId: vigente(v.id), data: { piezas: n } }).then(refrescar);
    try {
      await poner(cuantas);
      historial.registrar({ etiqueta: 'piezas del vano', deshacer: () => poner(antes), rehacer: () => poner(cuantas) });
      alCambiarHistorial();
      avisar(`${v.clave}: ${cuantas} ${cuantas === 1 ? 'pieza' : 'piezas idénticas'}; lo que descuenta se recalculó.`);
    } catch (err) {
      falla('cambiar las piezas', err);
    }
  }

  /** La hoja de una puerta: bisagra, lado y apertura. Es dibujo: no cambia lo que descuenta. */
  async function cambiarHoja(v: VanoEnPlanoRespuesta, cambio: CambioDeHoja, etiqueta = 'hoja de la puerta') {
    const antes = hojaDe(v);
    const despues = { ...antes, ...cambio };
    const poner = (h: typeof antes) =>
      hoja
        .mutateAsync({
          vanoId: vigente(v.id),
          data: { bisagra: h.bisagra === -1 ? -1 : 1, lado_hoja: h.lado_hoja === -1 ? -1 : 1, apertura_grados: h.apertura_grados },
        })
        .then(refrescar);
    try {
      await poner(despues);
      historial.registrar({ etiqueta, deshacer: () => poner(antes), rehacer: () => poner(despues) });
      alCambiarHistorial();
      avisar(`${v.clave}: hoja actualizada.`);
    } catch (err) {
      falla('cambiar la hoja', err);
    }
  }

  async function quitar(v: VanoEnPlanoRespuesta) {
    const datos = {
      clave: v.clave,
      tipo: v.tipo as 'puerta' | 'ventana' | 'cancel' | 'arco' | 'paso' | 'castillo',
      ancho_m: num(v.ancho_m),
      alto_m: num(v.alto_m),
      antepecho_m: num(v.antepecho_m ?? 0),
      piezas: v.piezas,
      posicion_m: posicionDe(v),
      lado_muro: (v.lado_muro ?? 0) as -1 | 0 | 1,
    };
    const hojaAntes = hojaDe(v);
    const recrear = async () => {
      const r = await colocar.mutateAsync({ trazoId: v.trazo_id, data: datos });
      alias.current.set(v.id, r.vano_id);
      if (v.tipo === 'puerta') {
        await hoja.mutateAsync({ vanoId: r.vano_id, data: hojaAntes as { bisagra: -1 | 1; lado_hoja: -1 | 1; apertura_grados: number } });
      }
      refrescar();
    };
    try {
      await quitarMut.mutateAsync({ vanoId: vigente(v.id) });
      historial.registrar({
        etiqueta: 'vano quitado',
        deshacer: recrear,
        rehacer: async () => {
          await quitarMut.mutateAsync({ vanoId: vigente(v.id) });
          refrescar();
        },
      });
      alCambiarHistorial();
      refrescar();
      avisar(`${v.clave} quitado: el muro vuelve a medir ese descuento. Se puede deshacer.`);
    } catch (err) {
      falla('quitar el vano', err);
    }
  }

  const buscar = (id: string) => vanos.find((x) => x.id === id);
  return { moverA, cambiarAncho, cambiarPiezas, cambiarHoja, quitar, buscar, vigente };
}
