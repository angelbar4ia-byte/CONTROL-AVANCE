/**
 * «Cómo se coloca» el vano (cerebro D-635): por **punto** (un clic y cae donde dice la rejilla de nueve puntos) o por
 * **línea** (dos clics y una altura); el **tipo** (puerta, ventana, cancel, arco, paso) y su **versión** del catálogo
 * (P-01 0.9 × 2.1…), que se edita y se guarda al escribir —cambia el catálogo para todas las obras; los vanos ya puestos
 * conservan sus medidas—. Se coloca sobre cualquier muro, línea o área, sin elegirlo antes.
 */

import { useEffect, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getListarVersionesApiV1VanosVersionGetQueryKey,
  useCambiarVersionApiV1VanosVersionVersionIdPatch,
  useCrearVersionApiV1VanosVersionPost,
  useListarVersionesApiV1VanosVersionGet,
  useQuitarVersionApiV1VanosVersionVersionIdDelete,
} from '@/api/generado/vanos-catalogo/vanos-catalogo';
import type { VersionDeVanoRespuesta } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';

import { numeroTecleado } from './volumen';
import { TIPOS_DE_VANO, type TipoDeVano } from './vanos';

/** Dónde del vano cae el clic: a lo largo del muro (i/c/d) y a lo ancho (i = una cara, c = centro, d = la otra). */
export interface AnclaDeVano {
  readonly h: 'i' | 'c' | 'd';
  readonly v: 'i' | 'c' | 'd';
}

export interface OpcionesDelVano {
  readonly modo: 'punto' | 'linea';
  readonly tipo: TipoDeVano;
  readonly versionId: string | null;
  readonly ancla: AnclaDeVano;
  /** Por línea: la altura (y el antepecho de una ventana). */
  readonly alturaLinea: number;
  readonly antepechoLinea: number;
  readonly piezas: number;
}

export const OPCIONES_DE_VANO_INICIALES: OpcionesDelVano = {
  modo: 'punto',
  tipo: 'puerta',
  versionId: null,
  ancla: { h: 'c', v: 'c' },
  alturaLinea: 2.1,
  antepechoLinea: 0.9,
  piezas: 1,
};

const NOMBRE_DEL_EJE: Readonly<Record<'i' | 'c' | 'd', string>> = { i: 'izquierda', c: 'centro', d: 'derecha' };
const TIPOS = Object.keys(TIPOS_DE_VANO) as TipoDeVano[];

interface Props {
  readonly opciones: OpcionesDelVano;
  readonly onCambiar: (cambio: Partial<OpcionesDelVano>) => void;
  readonly puedeDefinir: boolean;
  readonly hayObjetivo: boolean;
  readonly onAviso: (texto: string) => void;
  readonly onError: (texto: string) => void;
}

/** La versión que se coloca: la elegida o, si no, la primera de su tipo. */
export function versionDelVano(versiones: readonly VersionDeVanoRespuesta[], opciones: OpcionesDelVano): VersionDeVanoRespuesta | undefined {
  const delTipo = versiones.filter((v) => v.tipo === opciones.tipo);
  return delTipo.find((v) => v.id === opciones.versionId) ?? delTipo[0];
}

export function OpcionesDeVano({ opciones, onCambiar, puedeDefinir, hayObjetivo, onAviso, onError }: Props) {
  const lista = useListarVersionesApiV1VanosVersionGet();
  const crear = useCrearVersionApiV1VanosVersionPost<ErrorApi>();
  const cambiar = useCambiarVersionApiV1VanosVersionVersionIdPatch<ErrorApi>();
  const quitar = useQuitarVersionApiV1VanosVersionVersionIdDelete<ErrorApi>();
  const versiones = lista.data ?? [];
  const delTipo = versiones.filter((v) => v.tipo === opciones.tipo);
  const version = versionDelVano(versiones, opciones);
  const esVentana = opciones.tipo === 'ventana';

  const [clave, setClave] = useState('');
  const [ancho, setAncho] = useState('');
  const [alto, setAlto] = useState('');
  const [antepecho, setAntepecho] = useState('');
  useEffect(() => {
    if (!version) return;
    setClave(version.clave);
    setAncho(String(Number(version.ancho_m)));
    setAlto(String(Number(version.alto_m)));
    setAntepecho(String(Number(version.antepecho_m)));
  }, [version?.id, version?.clave, version?.ancho_m, version?.alto_m, version?.antepecho_m]); // eslint-disable-line react-hooks/exhaustive-deps

  const recargar = () => void queryClient.invalidateQueries({ queryKey: getListarVersionesApiV1VanosVersionGetQueryKey() });

  async function guardar(campo: 'clave' | 'ancho_m' | 'alto_m' | 'antepecho_m') {
    if (!version || !puedeDefinir) return;
    const cambios: Record<string, unknown> = {};
    if (campo === 'clave') {
      const c = clave.trim().toUpperCase();
      if (c === '') {
        onError('La clave no puede quedar vacía.');
        setClave(version.clave);
        return;
      }
      if (c === version.clave) return;
      cambios.clave = c;
    } else {
      const texto = campo === 'ancho_m' ? ancho : campo === 'alto_m' ? alto : antepecho;
      const n = numeroTecleado(texto);
      const actual = Number(version[campo]);
      if (campo !== 'antepecho_m' && !(n > 0)) {
        onError('El ancho y el alto del vano deben ser mayores que cero.');
        return;
      }
      if (n === actual) return;
      cambios[campo] = n;
    }
    try {
      await cambiar.mutateAsync({ versionId: version.id, data: cambios });
      recargar();
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo guardar la versión.');
      recargar();
    }
  }

  async function nueva() {
    try {
      const v = await crear.mutateAsync({ data: { tipo: opciones.tipo, copiar_de: version?.id ?? null } });
      recargar();
      onCambiar({ versionId: v.id });
      onAviso(`Versión ${v.clave} creada: ${TIPOS_DE_VANO[opciones.tipo].nombre} ${Number(v.ancho_m)} × ${Number(v.alto_m)} m. Queda en el catálogo para todas las obras.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo crear la versión.');
    }
  }

  async function eliminar() {
    if (!version) return;
    try {
      await quitar.mutateAsync({ versionId: version.id });
      recargar();
      onCambiar({ versionId: null });
      onAviso(`Versión ${version.clave} eliminada del catálogo.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo quitar la versión.');
    }
  }

  const enEnter = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') e.currentTarget.blur();
  };
  const chip = (activo: boolean, texto: React.ReactNode, onClick: () => void, clave: string, titulo?: string) => (
    <button key={clave} type="button" className={activo ? 'btn btn--sm btn--primary' : 'btn btn--sm'} aria-pressed={activo} title={titulo} onClick={onClick}>
      {texto}
    </button>
  );

  return (
    <section className="opciones" aria-label="Opciones del vano" style={{ display: 'grid', gap: 8, minWidth: 240 }}>
      <div className="text-xs text-mute">Cómo se coloca</div>
      <div className="row" style={{ gap: 4 }}>
        {chip(opciones.modo === 'punto', 'Por punto', () => onCambiar({ modo: 'punto' }), 'punto')}
        {chip(opciones.modo === 'linea', 'Por línea', () => onCambiar({ modo: 'linea' }), 'linea')}
      </div>

      <div className="text-xs text-mute">Tipo</div>
      <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
        {TIPOS.map((t) =>
          chip(opciones.tipo === t, TIPOS_DE_VANO[t].nombre, () => onCambiar({ tipo: t, versionId: null }), t, t === 'paso' ? 'vano sin puerta' : undefined),
        )}
      </div>

      {opciones.modo === 'punto' && (
        <div className="row" style={{ gap: 10, alignItems: 'center' }}>
          <div
            role="group"
            aria-label="Punto de partida del vano"
            style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 22px)', gridTemplateRows: 'repeat(3, 22px)', gap: 3, padding: 5, border: '1px solid var(--line, #2a2f3a)', borderRadius: 7 }}
          >
            {(['i', 'c', 'd'] as const).flatMap((v) =>
              (['i', 'c', 'd'] as const).map((h) => {
                const activo = opciones.ancla.h === h && opciones.ancla.v === v;
                return (
                  <button
                    key={`${h}${v}`}
                    type="button"
                    className={activo ? 'ancla is-activa' : 'ancla'}
                    aria-pressed={activo}
                    aria-label={`Punto de partida: ${NOMBRE_DEL_EJE[h]} · cara ${NOMBRE_DEL_EJE[v]}`}
                    title={h === 'c' && v === 'c' ? 'Centro' : `A lo largo: ${NOMBRE_DEL_EJE[h]} · A lo ancho: ${NOMBRE_DEL_EJE[v]}`}
                    style={{ width: 22, height: 22, padding: 0, borderRadius: 4, border: '1px solid var(--line, #2a2f3a)', background: activo ? 'var(--accent, #3b82f6)' : 'transparent' }}
                    onClick={() => onCambiar({ ancla: { h, v } })}
                  />
                );
              }),
            )}
          </div>
          <span className="text-xs text-mute">Punto que cae en tu clic</span>
        </div>
      )}

      {opciones.modo === 'punto' ? (
        <>
          <div className="text-xs text-mute">Versión</div>
          <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
            {delTipo.map((v) =>
              chip(
                version?.id === v.id,
                <>
                  {v.clave} <span className="text-mute">{Number(v.ancho_m)}×{Number(v.alto_m)}{Number(v.antepecho_m) > 0 ? ` ↑${Number(v.antepecho_m)}` : ''}</span>
                </>,
                () => onCambiar({ versionId: v.id }),
                v.id,
                `${v.clave} · ${Number(v.ancho_m)} × ${Number(v.alto_m)} m`,
              ),
            )}
            {puedeDefinir && (
              <button type="button" className="btn btn--sm" title="Nueva versión copiando la elegida" disabled={crear.isPending} onClick={() => void nueva()}>
                + Nueva
              </button>
            )}
            {puedeDefinir && delTipo.length > 1 && version && (
              <button type="button" className="btn btn--sm" aria-label={`Eliminar la versión ${version.clave}`} title={`Eliminar la versión ${version.clave} del catálogo`} onClick={() => void eliminar()}>
                🗑
              </button>
            )}
          </div>
          <div className="text-xs text-mute">Versión · se guarda al escribir</div>
          <div className="row" style={{ gap: 6 }}>
            <label className="text-xs">
              Clave
              <input aria-label="Clave de la versión" style={{ width: 60 }} value={clave} disabled={!puedeDefinir} onChange={(e) => setClave(e.target.value)} onBlur={() => void guardar('clave')} onKeyDown={enEnter} />
            </label>
            <label className="text-xs">
              Ancho
              <input aria-label="Ancho de la versión (m)" inputMode="decimal" style={{ width: 52 }} value={ancho} disabled={!puedeDefinir} onChange={(e) => setAncho(e.target.value)} onBlur={() => void guardar('ancho_m')} onKeyDown={enEnter} />
            </label>
            <label className="text-xs">
              Alto
              <input aria-label="Alto de la versión (m)" inputMode="decimal" style={{ width: 52 }} value={alto} disabled={!puedeDefinir} onChange={(e) => setAlto(e.target.value)} onBlur={() => void guardar('alto_m')} onKeyDown={enEnter} />
            </label>
            {esVentana && (
              <label className="text-xs" title="Altura del piso al borde inferior de la ventana">
                Antep.
                <input aria-label="Antepecho de la versión (m)" inputMode="decimal" style={{ width: 52 }} value={antepecho} disabled={!puedeDefinir} onChange={(e) => setAntepecho(e.target.value)} onBlur={() => void guardar('antepecho_m')} onKeyDown={enEnter} />
              </label>
            )}
            <label className="text-xs" title="Cantidad idéntica">
              Cant.
              <input
                aria-label="Cantidad idéntica"
                inputMode="numeric"
                style={{ width: 40 }}
                value={String(opciones.piezas)}
                onChange={(e) => onCambiar({ piezas: Math.max(1, Math.round(numeroTecleado(e.target.value)) || 1) })}
              />
            </label>
          </div>
        </>
      ) : (
        <div className="row" style={{ gap: 8 }}>
          <label className="text-xs">
            Altura (m)
            <input aria-label="Altura del vano por línea (m)" inputMode="decimal" style={{ width: 60 }} value={String(opciones.alturaLinea)} onChange={(e) => onCambiar({ alturaLinea: numeroTecleado(e.target.value) })} />
          </label>
          {esVentana && (
            <label className="text-xs">
              Del piso a la ventana (m)
              <input aria-label="Del piso a la ventana (m)" inputMode="decimal" style={{ width: 60 }} value={String(opciones.antepechoLinea)} onChange={(e) => onCambiar({ antepechoLinea: numeroTecleado(e.target.value) })} />
            </label>
          )}
        </div>
      )}
      <div
        className="text-xs text-mute"
        title={`Descuenta ancho × alto de cada cara. ${TIPOS_DE_VANO[opciones.tipo].llegaAlPiso ? 'Parte del piso: también resta del largo.' : 'Se mide del antepecho hasta antepecho + alto; no resta del largo.'} Editar la versión cambia el catálogo; los vanos ya puestos conservan sus medidas.`}
      >
        {!hayObjetivo ? 'Elige un muro, línea o área.' : opciones.modo === 'punto' ? 'Clic en el plano para colocar.' : 'Fija la altura y marca inicio y fin con 2 clics.'}
      </div>
    </section>
  );
}
