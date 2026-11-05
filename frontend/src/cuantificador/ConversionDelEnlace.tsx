/**
 * «Edición · cómo cuenta para el concepto» (cerebro D-633): lo que el mockup llama el detalle del trazo. Un trazo no cuenta
 * igual para todos los conceptos: un muro se cuenta por largo, área (por el eje, una cara o dos, con altura única o por
 * partes), volumen o piezas; un área, por área, volumen, piezas o perímetro. Cada cambio se calcula en el servidor (la
 * misma cuenta que se guarda) y se ve con su fórmula y si coincide la unidad del concepto; **Aplicar** crea un enlace
 * nuevo y el anterior queda como evidencia y deja de sumar.
 */

import { useEffect, useMemo, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getVerConversionApiV1EnlacesEnlaceIdConversionGetQueryKey,
  useAplicarConversionApiV1EnlacesEnlaceIdConversionPost,
  useCalcularConversionApiV1EnlacesEnlaceIdConversionCalcularPost,
  useVerConversionApiV1EnlacesEnlaceIdConversionGet,
} from '@/api/generado/cuantificacion/cuantificacion';
import type { CalculoDeConversionRespuesta, ConversionPeticion } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';

interface Parte {
  nombre: string;
  desde_m: number;
  hasta_m: number;
  suma: boolean;
}

/** La conversión como se edita: los números como texto, para poder teclearlos. */
export interface BorradorDeConversion {
  modo: string;
  mide: 'eje' | 'cara1' | 'cara2';
  cara: 'int' | 'ext';
  lado: 'izq' | 'der';
  partes: Parte[];
  [campo: string]: unknown;
}

const NUMEROS = ['alt', 'gro', 'esp', 'desc', 'pw', 'ph', 'merma', 'sep'] as const;
const PIEZAS_DE_MUESTRA: Readonly<Record<string, readonly [number, number]>> = {
  'Loseta 60×60': [0.6, 0.6],
  'Block 40×20': [0.4, 0.2],
  'Ladrillo 24×11': [0.24, 0.11],
  'Tablero 1.22×2.44': [1.22, 2.44],
};

const esMuroOLinea = (tipo: string) => tipo === 'muro' || tipo === 'linea';

const num = (t: unknown) => Number(String(t ?? '').replace(',', '.'));

/** El borrador listo para mandar al servidor (los números ya como números). */
export function aPeticion(b: BorradorDeConversion): ConversionPeticion {
  const p: Record<string, unknown> = { modo: b.modo, mide: b.mide, cara: b.cara, lado: b.lado, partes: b.partes };
  for (const k of NUMEROS) {
    const v = b[k];
    if (v !== undefined && v !== null && String(v).trim() !== '' && Number.isFinite(num(v))) p[k] = num(v);
  }
  return p as unknown as ConversionPeticion;
}

/** ¿Hay cambios sin aplicar? Compara lo editado con lo vigente, sin importar cómo se escribió cada número. */
export function hayCambios(a: BorradorDeConversion | null, b: BorradorDeConversion | null): boolean {
  if (!a || !b) return false;
  return JSON.stringify(aPeticion(a)) !== JSON.stringify(aPeticion(b));
}

interface Props {
  readonly enlaceId: string;
  readonly nombreDelConcepto: string;
  /** El grosor y la alineación del trazo, para el resumen de arriba. */
  readonly grosorM?: number | null;
  readonly alineacion?: string | null;
  /** Cuántos otros trazos del mismo tipo alimentan este concepto (para «aplicar también a…»). */
  readonly hermanos: number;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

export function ConversionDelEnlace({ enlaceId, nombreDelConcepto, grosorM, alineacion, hermanos, onCambio, onError }: Props) {
  const info = useVerConversionApiV1EnlacesEnlaceIdConversionGet(enlaceId);
  const calcular = useCalcularConversionApiV1EnlacesEnlaceIdConversionCalcularPost<ErrorApi>();
  const aplicar = useAplicarConversionApiV1EnlacesEnlaceIdConversionPost<ErrorApi>();
  const [borrador, setBorrador] = useState<BorradorDeConversion | null>(null);
  const [vigente, setVigente] = useState<BorradorDeConversion | null>(null);
  const [resultado, setResultado] = useState<CalculoDeConversionRespuesta | null>(null);
  const [aTodos, setATodos] = useState(false);

  const alCargar = (c: Record<string, unknown>): BorradorDeConversion => ({
    ...c,
    modo: String(c.modo),
    mide: (c.mide as BorradorDeConversion['mide']) ?? 'cara2',
    cara: (c.cara as BorradorDeConversion['cara']) ?? 'int',
    lado: (c.lado as BorradorDeConversion['lado']) ?? 'der',
    partes: ((c.partes as Parte[] | undefined) ?? []).map((p) => ({ ...p })),
  });

  useEffect(() => {
    const c = info.data?.conversion;
    if (!c) return;
    const b = alCargar(c);
    setBorrador(b);
    setVigente(b);
  }, [info.data]);

  // La vista previa: el servidor calcula con lo que está escrito (sin guardar nada).
  useEffect(() => {
    if (!borrador) return;
    const espera = setTimeout(() => {
      calcular.mutate(
        { enlaceId, data: aPeticion(borrador) },
        { onSuccess: setResultado, onError: () => setResultado(null) },
      );
    }, 250);
    return () => clearTimeout(espera);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [borrador, enlaceId]);

  const campos = useMemo(() => (borrador ? (info.data?.campos[borrador.modo] ?? []) : []), [borrador, info.data]);
  if (!info.data || !info.data.conversion || !borrador) return null;

  const tipo = info.data.tipo;
  const esMuro = tipo === 'muro' || tipo === 'linea';
  const sinAplicar = hayCambios(borrador, vigente);
  const cambiar = (c: Partial<BorradorDeConversion>) => setBorrador({ ...borrador, ...c });
  const partes = borrador.partes;
  const mide = borrador.mide;

  async function ponerAplicar() {
    if (!borrador) return;
    try {
      const r = await aplicar.mutateAsync({ enlaceId, data: { conversion: aPeticion(borrador), a_todos: aTodos } });
      void queryClient.invalidateQueries({ queryKey: getVerConversionApiV1EnlacesEnlaceIdConversionGetQueryKey(enlaceId) });
      onCambio(
        `Enlace nuevo: ${nombreDelConcepto} suma ${resultado ? `${resultado.valor.toFixed(2)} ${resultado.unidad}` : 'la nueva cantidad'}` +
          (r.aplicados > 1 ? ` · aplicado a ${r.aplicados} trazos` : '') +
          '.',
      );
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo aplicar la conversión.');
    }
  }

  const chip = (activo: boolean, texto: string, onClick: () => void, clave: string) => (
    <button key={clave} type="button" className={activo ? 'btn btn--sm btn--primary' : 'btn btn--sm'} aria-pressed={activo} onClick={onClick}>
      {texto}
    </button>
  );

  return (
    <div role="group" aria-label={`Cómo cuenta para ${nombreDelConcepto}`} style={{ display: 'grid', gap: 6 }} data-enlace={enlaceId}>
      <dl style={{ margin: 0, display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '2px 12px' }} aria-label="Resumen del trazo">
        {[
          ['Concepto', nombreDelConcepto],
          ['Tipo', { muro: 'Muro', linea: 'Línea', area: 'Área', forma: 'Forma', punto: 'Punto' }[info.data.tipo] ?? info.data.tipo],
          ...(resultado && esMuroOLinea(info.data.tipo) ? [['Largo', `${Number(resultado.componentes.largo).toFixed(2)} m`]] : []),
          ...(grosorM != null ? [['Grosor', `${grosorM} m`], ['Alineación', alineacion ?? 'centro']] : []),
          ...(resultado && info.data.tipo === 'area'
            ? [['Área', `${Number(resultado.componentes.area).toFixed(2)} m²`], ['Perímetro', `${Number(resultado.componentes.perimetro).toFixed(2)} m`]]
            : []),
          ...(resultado && info.data.tipo === 'forma' ? [['Área', `${Number(resultado.componentes.area).toFixed(4)} m²`]] : []),
          ...(resultado && Number(resultado.componentes.huecos) > 0 ? [['Huecos', String(resultado.componentes.huecos)]] : []),
          ...(resultado && Number(resultado.componentes.pendiente_pct) > 0 ? [['Pendiente', `${Number(resultado.componentes.pendiente_pct)} %`]] : []),
          ...(resultado && Number(resultado.componentes.vanos_m2) > 0 ? [['Vanos', `− ${Number(resultado.componentes.vanos_m2).toFixed(2)} m²`]] : []),
        ].map(([a, b]) => (
          <div key={a} style={{ display: 'contents' }}>
            <dt className="text-mute text-xs">{a}</dt>
            <dd className="mono text-xs" style={{ margin: 0, textAlign: 'right' }}>{b}</dd>
          </div>
        ))}
      </dl>
      <div className="text-xs text-mute">Edición · cómo cuenta para el concepto</div>
      <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
        {info.data.modos.map((m) => chip(borrador.modo === m.clave, m.nombre, () => cambiar({ modo: m.clave }), m.clave))}
      </div>

      {campos
        .filter((c) => !(c.clave === 'alt' && esMuro && partes.length > 0))
        .map((c) => (
          <label key={c.clave} className="text-xs" style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'space-between' }}>
            <span>
              {c.etiqueta} ({c.unidad})
            </span>
            <input
              aria-label={c.etiqueta}
              inputMode="decimal"
              style={{ width: 80, textAlign: 'right' }}
              value={String(borrador[c.clave] ?? '')}
              onChange={(e) => cambiar({ [c.clave]: e.target.value })}
            />
          </label>
        ))}

      {tipo === 'area' && borrador.modo === 'pza' && (
        <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
          {Object.entries(PIEZAS_DE_MUESTRA).map(([nombre, [pw, ph]]) => (
            <button key={nombre} type="button" className="btn btn--sm" onClick={() => cambiar({ pw, ph })}>
              {nombre}
            </button>
          ))}
        </div>
      )}

      {esMuro && borrador.modo === 'area' && (
        <>
          <div className="text-xs text-mute">Medir por</div>
          <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
            {chip(mide === 'eje', 'Eje', () => cambiar({ mide: 'eje' }), 'eje')}
            {chip(mide === 'cara1', '1 cara', () => cambiar({ mide: 'cara1' }), 'cara1')}
            {chip(mide === 'cara2', '2 caras', () => cambiar({ mide: 'cara2' }), 'cara2')}
          </div>
          {mide === 'cara1' && (
            <div className="row" style={{ gap: 4 }}>
              {chip(borrador.cara === 'int', 'Interior', () => cambiar({ cara: 'int' }), 'int')}
              {chip(borrador.cara === 'ext', 'Exterior', () => cambiar({ cara: 'ext' }), 'ext')}
            </div>
          )}
          {mide !== 'eje' && (
            <>
              <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
                {chip(borrador.lado === 'izq', 'Interior a la izquierda', () => cambiar({ lado: 'izq' }), 'izq')}
                {chip(borrador.lado === 'der', 'Interior a la derecha', () => cambiar({ lado: 'der' }), 'der')}
              </div>
              <div className="text-xs text-mute">Izquierda o derecha respecto al sentido en que dibujaste el muro.</div>
            </>
          )}
        </>
      )}

      {esMuro && ['area', 'vol'].includes(borrador.modo) && (
        <>
          <div className="text-xs text-mute">Altura por partes</div>
          <div className="row" style={{ gap: 4 }}>
            {chip(partes.length === 0, 'Altura única', () => cambiar({ partes: [] }), 'unica')}
            {chip(
              partes.length > 0,
              'Por partes',
              () => cambiar({ partes: [{ nombre: 'Muro', desde_m: 0, hasta_m: num(borrador.alt) || 2.6, suma: true }] }),
              'partes',
            )}
          </div>
          {partes.map((p, i) => (
            <div key={i} className="row" style={{ gap: 4 }}>
              <input aria-label={`Nombre de la parte ${i + 1}`} style={{ width: 80 }} value={p.nombre} onChange={(e) => cambiar({ partes: partes.map((x, j) => (j === i ? { ...x, nombre: e.target.value } : x)) })} />
              <input aria-label={`Desde (m) de la parte ${i + 1}`} inputMode="decimal" style={{ width: 48 }} value={String(p.desde_m)} onChange={(e) => cambiar({ partes: partes.map((x, j) => (j === i ? { ...x, desde_m: num(e.target.value) } : x)) })} />
              <input aria-label={`Hasta (m) de la parte ${i + 1}`} inputMode="decimal" style={{ width: 48 }} value={String(p.hasta_m)} onChange={(e) => cambiar({ partes: partes.map((x, j) => (j === i ? { ...x, hasta_m: num(e.target.value) } : x)) })} />
              <label className="text-xs" title="Suma a la cantidad">
                <input type="checkbox" checked={p.suma} onChange={(e) => cambiar({ partes: partes.map((x, j) => (j === i ? { ...x, suma: e.target.checked } : x)) })} /> suma
              </label>
              <button type="button" className="btn btn--ghost btn--sm" aria-label={`Quitar la parte ${i + 1}`} onClick={() => cambiar({ partes: partes.filter((_, j) => j !== i) })}>
                ×
              </button>
            </div>
          ))}
          {partes.length > 0 && (
            <button type="button" className="btn btn--sm" onClick={() => cambiar({ partes: [...partes, { nombre: '', desde_m: partes[partes.length - 1]!.hasta_m, hasta_m: partes[partes.length - 1]!.hasta_m + 0.5, suma: true }] })}>
              + Parte
            </button>
          )}
        </>
      )}

      <div style={{ border: '1px solid var(--line, #2a2f3a)', borderRadius: 8, padding: '8px 10px' }} data-resultado>
        <div className="mono text-xs text-mute">{resultado?.formula ?? '…'}</div>
        <div className="mono" style={{ fontSize: 18, fontWeight: 700 }}>
          {resultado ? `${resultado.unidad === 'pza' ? Math.round(resultado.valor) : resultado.valor.toFixed(2)} ${resultado.unidad}` : '—'}
        </div>
      </div>
      <div className="row" style={{ justifyContent: 'space-between', gap: 6 }}>
        <span className="text-xs">
          {nombreDelConcepto} se mide en <b>{info.data.unidad_del_concepto ?? '—'}</b>
        </span>
        {resultado && (
          <span className={resultado.coincide ? 'badge badge--ok' : 'badge badge--warn'}>
            {resultado.coincide ? '✓ coincide' : '⚠ distinta unidad'}
          </span>
        )}
      </div>

      {hermanos > 0 && (
        <label className="text-xs">
          <input type="checkbox" checked={aTodos} onChange={(e) => setATodos(e.target.checked)} /> Aplicar también a los {hermanos} trazos del mismo tipo de este concepto
        </label>
      )}
      <div className="row" style={{ justifyContent: 'flex-end', gap: 6, alignItems: 'center' }}>
        <span className="text-xs text-mute">{sinAplicar ? 'Cambios sin aplicar' : info.data.es_la_de_hoy ? 'Aplicado' : 'Sin aplicar'}</span>
        <button type="button" className="btn btn--sm" disabled={!sinAplicar} onClick={() => setBorrador(vigente)}>
          Restablecer
        </button>
        <button type="button" className="btn btn--sm btn--primary" disabled={aplicar.isPending || (!sinAplicar && info.data.es_la_de_hoy)} onClick={() => void ponerAplicar()}>
          Aplicar
        </button>
      </div>
      <div className="text-xs text-mute">Aplicar crea un enlace nuevo con estos parámetros; el anterior queda como evidencia y deja de sumar.</div>
    </div>
  );
}
