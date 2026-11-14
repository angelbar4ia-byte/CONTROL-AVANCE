/**
 * Materiales, insumos permitidos y comparación con el catálogo en la tarjeta del elemento (plan de elementos de muro, fase D).
 *
 * - **Materiales**: con qué insumo se paga el concreto, el alambre, la varilla y el anillo; solo ofrece los de las familias
 *   de la parte (el servidor rechaza los demás). Entran a la firma anti-duplicados.
 * - **Insumos del elemento** y una ventana sencilla para agregar: clase → familia → búsqueda, multiselección. Los insumos de
 *   otra familia salen marcados «fuera de lo usual» y no se pueden marcar. «Herramienta y equipo» es opcional y trae el
 *   andamio como sugerencia: se crea como insumo provisional, sin precio.
 * - **Comparación** con el concepto del catálogo, insumo por insumo: = hasta 3 %, ≈ hasta 8 %, ≠ más.
 *
 * Pendiente (deliberado): crear insumos nuevos con formulario completo y cantidades editables en la ventana.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getCompararConElCatalogoApiV1ElementosParametricosElementoIdComparacionGetQueryKey,
  getInsumosDelElementoApiV1ElementosParametricosElementoIdInsumosGetQueryKey,
  getListarElementosParametricosApiV1ElementosParametricosGetQueryKey,
  useActualizarElementoParametricoApiV1ElementosParametricosElementoIdPatch,
  useAgregarInsumosApiV1ElementosParametricosElementoIdInsumosPost,
  useBuscarInsumosApiV1ElementosParametricosElementoIdInsumosDisponiblesGet,
  useCompararConElCatalogoApiV1ElementosParametricosElementoIdComparacionGet,
  useCrearInsumoProvisionalApiV1ElementosParametricosElementoIdInsumosNuevosPost,
  useFamiliasDeInsumosApiV1ElementosParametricosFamiliasDeInsumosGet,
  useInsumosDelElementoApiV1ElementosParametricosElementoIdInsumosGet,
  useQuitarInsumoApiV1ElementosParametricosElementoIdInsumosInsumoIdDelete,
} from '@/api/generado/elementos-parametricos/elementos-parametricos';
import { queryClient } from '@/app/queryClient';

interface Props {
  readonly elementoId: string;
  readonly clave: string;
  readonly tipo: 'castillo' | 'lineal' | 'zapata' | 'losa';
  readonly materiales: Readonly<Record<string, unknown>>;
  readonly puedeDefinir: boolean;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

const PARTES = [
  ['concreto', 'Concreto', 'Concretos'],
  ['alambre', 'Alambre de amarre', 'Aceros'],
  ['varilla', 'Varilla', 'Acero De Refuerzo'],
  ['anillo', 'Anillo', 'Aceros'],
] as const;

const MARCA: Record<string, string> = { '=': '=', '≈': '≈', '≠': '≠', solo_catalogo: 'solo catálogo', solo_elemento: 'solo elemento' };
const num = (n: number | null | undefined) => (n === null || n === undefined ? '—' : Math.abs(n) >= 1 ? n.toFixed(2) : n.toFixed(4));

function SelectorDeMaterial({ elementoId, parte, etiqueta, familia, actual, deshabilitado, onElegir }: {
  readonly elementoId: string;
  readonly parte: string;
  readonly etiqueta: string;
  readonly familia: string;
  readonly actual: string;
  readonly deshabilitado: boolean;
  readonly onElegir: (clave: string) => void;
}) {
  const lista = useBuscarInsumosApiV1ElementosParametricosElementoIdInsumosDisponiblesGet(elementoId, { clase: 'material', familia, limite: 200 });
  const opciones = (lista.data ?? []).filter((i) => i.permitido);
  return (
    <label className="text-xs text-mute" style={{ display: 'grid', gap: 2 }}>
      {etiqueta}
      <select aria-label={`${etiqueta} (${parte})`} disabled={deshabilitado} value={actual} onChange={(e) => onElegir(e.target.value)}>
        <option value="">Sin elegir</option>
        {actual !== '' && !opciones.some((i) => i.clave === actual) && <option value={actual}>{actual}</option>}
        {opciones.map((i) => (
          <option key={i.clave} value={i.clave}>
            {i.clave} · {i.descripcion}
          </option>
        ))}
      </select>
    </label>
  );
}

function VentanaDeInsumos({ elementoId, tipo, onCerrar, onAgregado, onError }: {
  readonly elementoId: string;
  readonly tipo: Props['tipo'];
  readonly onCerrar: () => void;
  readonly onAgregado: (n: number) => void;
  readonly onError: (m: string) => void;
}) {
  const [clase, setClase] = useState<string | null>(null);
  const [familia, setFamilia] = useState('');
  const [q, setQ] = useState('');
  const [marcados, setMarcados] = useState<string[]>([]);
  const familias = useFamiliasDeInsumosApiV1ElementosParametricosFamiliasDeInsumosGet({ tipo });
  const lista = useBuscarInsumosApiV1ElementosParametricosElementoIdInsumosDisponiblesGet(
    elementoId,
    { clase: (clase ?? undefined) as never, familia: familia || undefined, q: q || undefined, limite: 200 },
    { query: { enabled: clase !== null } },
  );
  const agregar = useAgregarInsumosApiV1ElementosParametricosElementoIdInsumosPost<ErrorApi>();
  const crear = useCrearInsumoProvisionalApiV1ElementosParametricosElementoIdInsumosNuevosPost<ErrorApi>();
  const clases = familias.data?.clases ?? [];
  const actual = clases.find((c) => c.clase === clase);

  async function confirmar() {
    try {
      const r = await agregar.mutateAsync({ elementoId, data: { insumos: marcados.map((insumo_id) => ({ insumo_id, cantidad: 0 })) } });
      onAgregado(r.agregados);
      onCerrar();
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudieron agregar los insumos.');
    }
  }
  async function sugerir(s: { clave: string; descripcion: string; unidad: string; subfamilia: string }) {
    try {
      await crear.mutateAsync({ elementoId, data: { clase: 'herramienta', clave: s.clave, descripcion: s.descripcion, unidad: s.unidad, subfamilia: s.subfamilia } });
      void lista.refetch();
      void familias.refetch();
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo crear el insumo.');
    }
  }

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label="Agregar insumos al elemento" style={{ padding: 12, gap: 8, width: 560 }}>
      {clase === null ? (
        <>
          <p className="text-xs text-mute">¿Qué vas a agregar? Elige la clase y luego buscas dentro de ella.</p>
          {clases.map((c) => (
            <button key={c.clase} type="button" className="btn" data-clase-de-insumo={c.clase} onClick={() => setClase(c.clase)}>
              {c.nombre} · {c.total} insumos
            </button>
          ))}
        </>
      ) : (
        <>
          <div className="row" style={{ gap: 6 }}>
            <button type="button" className="btn" onClick={() => { setClase(null); setFamilia(''); setMarcados([]); }}>
              ← Clases
            </button>
            <strong>{actual?.nombre}</strong>
          </div>
          <input type="search" aria-label="Buscar insumo" placeholder="Teclea para buscar por clave, nombre o familia" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
            <button type="button" className="btn" aria-pressed={familia === ''} onClick={() => setFamilia('')}>Todas</button>
            {(actual?.familias ?? []).map((f) => (
              <button key={`${f.familia}|${f.subfamilia ?? ''}`} type="button" className="btn" aria-pressed={familia === (f.subfamilia ?? f.familia)} onClick={() => setFamilia(f.subfamilia ?? f.familia)}>
                {f.subfamilia ? `${f.familia} · ${f.subfamilia}` : f.familia} {f.total}
              </button>
            ))}
          </div>
          {clase === 'herramienta' && (
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
              {(familias.data?.sugerencias_de_herramienta ?? []).map((s) => (
                <button key={s.clave} type="button" className="btn" data-sugerencia={s.clave} onClick={() => void sugerir(s)}>
                  Sugerencia: {s.descripcion} (provisional, sin precio)
                </button>
              ))}
            </div>
          )}
          <div style={{ maxHeight: 260, overflowY: 'auto', display: 'grid', gap: 2 }}>
            {(lista.data ?? []).map((i) => (
              <label key={i.clave} className="row text-xs" data-insumo-disponible={i.clave} style={{ gap: 6, opacity: i.permitido ? 1 : 0.55 }}>
                <input
                  type="checkbox"
                  aria-label={`Marcar ${i.clave}`}
                  disabled={!i.permitido || i.id === null}
                  checked={i.id !== null && marcados.includes(i.id)}
                  onChange={(e) => setMarcados((m) => (e.target.checked && i.id ? [...m, i.id] : m.filter((x) => x !== i.id)))}
                />
                <span className="mono">{i.clave}</span>
                <span>{i.descripcion}</span>
                <span className="text-mute">{i.familia}{i.subfamilia ? ` · ${i.subfamilia}` : ''}</span>
                {!i.permitido && <span className="badge badge--warn">fuera de lo usual</span>}
                {i.provisional && <span className="badge badge--warn">provisional, sin precio</span>}
              </label>
            ))}
            {lista.isSuccess && (lista.data ?? []).length === 0 && <span className="text-xs text-mute">Ningún insumo coincide{clase === 'herramienta' ? ': esta clase aún no tiene insumos en el catálogo' : ''}.</span>}
          </div>
        </>
      )}
      <div className="row" style={{ gap: 6, justifyContent: 'flex-end' }}>
        <button type="button" className="btn" onClick={onCerrar}>Cancelar</button>
        <button type="button" className="btn btn--primary" disabled={marcados.length === 0 || agregar.isPending} onClick={() => void confirmar()}>
          Agregar {marcados.length > 0 ? `${marcados.length} ` : ''}seleccionado{marcados.length === 1 ? '' : 's'}
        </button>
      </div>
    </div>
  );
}

export function InsumosDelElemento({ elementoId, clave, tipo, materiales, puedeDefinir, onCambio, onError }: Props) {
  const [abierta, setAbierta] = useState(false);
  const detalle = useInsumosDelElementoApiV1ElementosParametricosElementoIdInsumosGet(elementoId);
  const comparacion = useCompararConElCatalogoApiV1ElementosParametricosElementoIdComparacionGet(elementoId);
  const quitar = useQuitarInsumoApiV1ElementosParametricosElementoIdInsumosInsumoIdDelete<ErrorApi>();
  const actualizar = useActualizarElementoParametricoApiV1ElementosParametricosElementoIdPatch<ErrorApi>();
  if (tipo === 'losa') return null;

  const recargar = () => {
    void queryClient.invalidateQueries({ queryKey: getInsumosDelElementoApiV1ElementosParametricosElementoIdInsumosGetQueryKey(elementoId) });
    void queryClient.invalidateQueries({ queryKey: getCompararConElCatalogoApiV1ElementosParametricosElementoIdComparacionGetQueryKey(elementoId) });
    void queryClient.invalidateQueries({ queryKey: getListarElementosParametricosApiV1ElementosParametricosGetQueryKey() });
  };
  const fallo = (m: string) => onError(m);

  async function elegir(parte: string, valor: string) {
    const nuevos: Record<string, unknown> = { ...materiales };
    if (valor === '') delete nuevos[parte];
    else nuevos[parte] = valor;
    for (const k of Object.keys(nuevos)) if (nuevos[k] === null || nuevos[k] === undefined) delete nuevos[k];
    try {
      await actualizar.mutateAsync({ elementoId, data: { materiales: nuevos as never } });
      recargar();
      onCambio(`${clave}: material actualizado.`);
    } catch (err) {
      fallo(err instanceof Error ? err.message : 'No se pudo cambiar el material.');
    }
  }
  async function sacar(insumoId: string) {
    try {
      await quitar.mutateAsync({ elementoId, insumoId });
      recargar();
    } catch (err) {
      fallo(err instanceof Error ? err.message : 'No se pudo quitar el insumo.');
    }
  }

  return (
    <div role="group" aria-label={`Insumos de ${clave}`} data-insumos-del-elemento={clave} style={{ display: 'grid', gap: 6 }}>
      <div className="text-xs text-mute">Materiales (con qué insumo se paga cada parte)</div>
      <div className="arbol-edicion__alta">
        {PARTES.map(([parte, etiqueta, familia]) => (
          <SelectorDeMaterial
            key={parte}
            elementoId={elementoId}
            parte={parte}
            etiqueta={etiqueta}
            familia={familia}
            actual={String(materiales[parte] ?? '')}
            deshabilitado={!puedeDefinir || actualizar.isPending}
            onElegir={(v) => void elegir(parte, v)}
          />
        ))}
      </div>
      <div className="row" style={{ gap: 8, alignItems: 'center' }}>
        <span className="text-xs text-mute">Insumos del elemento</span>
        {puedeDefinir && (
          <button type="button" className="btn" onClick={() => setAbierta(true)}>
            + Agregar insumos
          </button>
        )}
      </div>
      {(detalle.data?.insumos ?? []).length === 0 && <span className="text-xs text-mute">Ninguno agregado.</span>}
      {(detalle.data?.insumos ?? []).map((i) => (
        <div key={i.id} className="row text-xs" data-insumo-agregado={i.insumo.clave} style={{ gap: 6, flexWrap: 'wrap' }}>
          <span className="mono">{i.insumo.clave}</span>
          <span>{i.insumo.descripcion}</span>
          <span className="text-mute">{i.insumo.familia}</span>
          {i.insumo.provisional && <span className="badge badge--warn">Provisional, sin precio</span>}
          {puedeDefinir && (
            <button type="button" className="btn" aria-label={`Quitar ${i.insumo.clave}`} onClick={() => void sacar(i.insumo.id ?? '')}>
              Quitar
            </button>
          )}
        </div>
      ))}
      {abierta && (
        <VentanaDeInsumos
          elementoId={elementoId}
          tipo={tipo}
          onCerrar={() => setAbierta(false)}
          onAgregado={(n) => { recargar(); onCambio(`${clave}: ${n} insumo${n === 1 ? '' : 's'} agregado${n === 1 ? '' : 's'}.`); }}
          onError={fallo}
        />
      )}
      {(comparacion.data?.conceptos ?? []).map((c) => (
        <details key={c.fila_id} data-comparacion={c.concepto_clave} open>
          <summary className="text-xs">
            Contraste con el catálogo: {c.concepto_clave} · = hasta 3 %, ≈ hasta 8 %, ≠ más · {c.resumen.igual} =, {c.resumen.aproximado} ≈, {c.resumen.distinto} ≠
          </summary>
          {c.sin_catalogo && <p className="text-xs text-mute">Concepto nuevo: aún no tiene composición en el catálogo.</p>}
          {c.avisos.map((a) => (
            <div key={a} role="note" className="text-xs">{a}</div>
          ))}
          <table className="text-xs" aria-label={`Comparación de ${c.concepto_clave}`}>
            <thead>
              <tr><th>Clave</th><th>Insumo</th><th>Catálogo</th><th>Elemento</th><th>Dif.</th><th /></tr>
            </thead>
            <tbody>
              {c.filas.map((f) => (
                <tr key={f.clave} data-insumo-comparado={f.clave} data-marca={f.marca}>
                  <td className="mono">{f.clave}</td>
                  <td>{f.descripcion}</td>
                  <td>{num(f.catalogo)}</td>
                  <td>{num(f.elemento)}</td>
                  <td>{f.diferencia_pct === null ? '—' : `${f.diferencia_pct > 0 ? '+' : ''}${f.diferencia_pct.toFixed(1)} %`}</td>
                  <td><span className="badge">{MARCA[f.marca] ?? f.marca}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ))}
    </div>
  );
}
