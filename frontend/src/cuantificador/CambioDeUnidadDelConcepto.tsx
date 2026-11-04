/**
 * Cambiar la unidad de un concepto a otro tipo de medición (D-623): de pieza a m², de m² a pieza, de metros a m²…
 * Cruza de tipo, así que pide una **equivalencia** (los «48 m²» de una pieza): se propone con la del destajo del
 * concepto si se encuentra, se puede teclear para corregirla, y Control de obra o Costos la aprueba. Al aprobar nace
 * una versión del concepto con las cantidades de su matriz convertidas (los precios de los insumos no cambian). Lo
 * asignado o con avance no se toca; los trazos ya medidos se marcan.
 */

import { useEffect, useRef, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useAprobarCambioApiV1CambiosDeUnidadCambioIdAprobarPost,
  useProponerCambioApiV1ConceptosConceptoIdCambioDeUnidadPost,
  useRechazarCambioApiV1CambiosDeUnidadCambioIdRechazarPost,
  useTeclearEquivalenciaApiV1CambiosDeUnidadCambioIdEquivalenciaPut,
} from '@/api/generado/cambio-de-unidad/cambio-de-unidad';
import type { CambioDeUnidadRespuesta } from '@/api/generado/modelo';

import { numeroTecleado } from './volumen';

interface Props {
  readonly conceptoId: string;
  readonly clave: string;
  readonly unidadActual: string;
  readonly unidadId: string;
  readonly unidadNueva: string;
  /** Se aprobó (con el aviso) o se rechazó / cerró sin cambios. */
  readonly onListo: (aviso: string | null) => void;
  readonly onError: (mensaje: string) => void;
}

/** Cómo se lee la equivalencia según el sentido: «48 m² por pieza», o «48 m² por cada pieza nueva» al volver a conteo. */
export function textoDeEquivalencia(unidadActual: string, unidadNueva: string, tipoNuevo: string): string {
  return tipoNuevo === 'conteo' ? `${unidadActual} por cada ${unidadNueva}` : `${unidadNueva} por cada ${unidadActual}`;
}

export function CambioDeUnidadDelConcepto({ conceptoId, clave, unidadActual, unidadId, unidadNueva, onListo, onError }: Props) {
  const proponer = useProponerCambioApiV1ConceptosConceptoIdCambioDeUnidadPost<ErrorApi>();
  const teclear = useTeclearEquivalenciaApiV1CambiosDeUnidadCambioIdEquivalenciaPut<ErrorApi>();
  const aprobar = useAprobarCambioApiV1CambiosDeUnidadCambioIdAprobarPost<ErrorApi>();
  const rechazar = useRechazarCambioApiV1CambiosDeUnidadCambioIdRechazarPost<ErrorApi>();
  const [cambio, setCambio] = useState<CambioDeUnidadRespuesta | null>(null);
  const [texto, setTexto] = useState('');
  const pedido = useRef(false);

  useEffect(() => {
    if (pedido.current) return;
    pedido.current = true;
    proponer
      .mutateAsync({ conceptoId, data: { unidad_id: unidadId } })
      .then((c) => {
        setCambio(c);
        setTexto(c.equivalencia != null ? String(Number(c.equivalencia)) : '');
      })
      .catch((err: unknown) => {
        onError(err instanceof Error ? err.message : 'No se pudo proponer el cambio de unidad.');
        onListo(null);
      });
    // Se propone una sola vez al abrir.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (cambio === null) {
    return <div className="text-mute text-xs">Buscando la equivalencia en el destajo de {clave}…</div>;
  }

  const valor = numeroTecleado(texto);
  const valida = Number.isFinite(valor) && valor > 0;
  const ocupado = teclear.isPending || aprobar.isPending || rechazar.isPending;

  async function aprobarCambio() {
    if (cambio === null || !valida) return;
    try {
      if (valor !== Number(cambio.equivalencia ?? NaN)) {
        await teclear.mutateAsync({ cambioId: cambio.id, data: { equivalencia: valor } });
      }
      const r = await aprobar.mutateAsync({ cambioId: cambio.id });
      onListo(
        `${clave} pasa a ${unidadNueva} como ${r.clave_nueva}: ${r.partidas_movidas} partida(s) movidas` +
          (r.partidas_bloqueadas > 0 ? `, ${r.partidas_bloqueadas} asignadas o con avance se quedan como estaban` : '') +
          (r.enlaces_rehechos > 0 ? `, ${r.enlaces_rehechos} enlace(s) de trazos rehechos` : '') +
          (r.enlaces_sin_medida > 0 ? `, ${r.enlaces_sin_medida} trazo(s) no caben en la unidad nueva` : '') +
          '.',
      );
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo aprobar el cambio de unidad.');
    }
  }

  async function descartar() {
    if (cambio === null) return;
    try {
      await rechazar.mutateAsync({ cambioId: cambio.id });
    } catch {
      // Si no se pudo rechazar, el cambio queda por resolver; se vuelve a ver al intentarlo otra vez.
    }
    onListo(null);
  }

  return (
    <div className="arbol-edicion__alta" role="group" aria-label={`Cambiar la unidad de ${clave}`}>
      <span className="text-xs">
        {clave}: <strong>{unidadActual}</strong> → <strong>{unidadNueva}</strong> cruza de tipo de medición. Equivalencia:
      </span>
      <input
        aria-label="Equivalencia"
        inputMode="decimal"
        style={{ width: 64 }}
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
      />
      <span className="text-xs text-mute">{textoDeEquivalencia(unidadActual, unidadNueva, cambio.tipo_nuevo)}</span>
      <span className="text-xs text-mute" style={{ flexBasis: '100%' }}>
        {cambio.origen_equivalencia === 'destajo'
          ? 'Tomada del destajo del concepto; corrígela si no es. '
          : 'No se encontró en el destajo: escríbela. '}
        Las cantidades de su matriz se convierten y los precios de los insumos no cambian. Nace una versión del concepto
        {cambio.partidas_bloqueadas > 0
          ? `; ${cambio.partidas_bloqueadas} de ${cambio.partidas} partidas están asignadas o con avance y no se tocan.`
          : '.'}
      </span>
      <button type="button" className="btn btn--sm" disabled={!valida || ocupado} onClick={() => void aprobarCambio()}>
        Aprobar
      </button>
      <button type="button" className="btn btn--ghost btn--sm" disabled={ocupado} onClick={() => void descartar()}>
        Cancelar
      </button>
    </div>
  );
}
