/**
 * El árbol de la obra y las versiones de su presupuesto (D-624). Una obra en diseño puede tener su **árbol propio**: se
 * clona el del prototipo base (que es compartido y no se toca) y se edita sin afectar a otras obras. Al primer cambio
 * nace un **borrador** del presupuesto que junta los cambios; Control de obra o Costos lo **confirma** (queda fijo) y
 * lo **fija como activo**. Todo es diseño, reversible, hasta que una parte se programa y se asigna.
 */

import { useMemo, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getVerArbolApiV1ObrasObraIdArbolGetQueryKey,
  useActivarVersionApiV1ObrasObraIdArbolVersionesPresupuestoIdActivarPost,
  useAgregarNodoApiV1ObrasObraIdArbolNodosPost,
  useAjustarNodoApiV1ObrasObraIdArbolNodosNodoIdPatch,
  useConfirmarVersionApiV1ObrasObraIdArbolVersionesConfirmarPost,
  useCrearArbolPropioApiV1ObrasObraIdArbolPropioPost,
  useQuitarNodoApiV1ObrasObraIdArbolNodosNodoIdDelete,
  useVerArbolApiV1ObrasObraIdArbolGet,
} from '@/api/generado/arbol-de-la-obra/arbol-de-la-obra';
import { useListarConceptosApiV1ConceptosGet } from '@/api/generado/catalogos/catalogos';
import type { NodoDeArbolDeObraRespuesta } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';

import { descripcionCorta, reordenar } from './arbol';

interface Props {
  readonly obraId: string;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

type Tipo = 'nivel' | 'etapa' | 'concepto';
const HIJO_DE: Readonly<Record<string, Tipo | undefined>> = { nivel: 'etapa', etapa: 'concepto' };
const NOMBRE_DEL_TIPO: Readonly<Record<Tipo, string>> = { nivel: 'Nivel', etapa: 'Etapa', concepto: 'Concepto' };

const dinero = (v: number | string) => Number(v).toLocaleString('es-MX', { style: 'currency', currency: 'MXN' });

export function ArbolDeLaObra({ obraId, onCambio, onError }: Props) {
  const consulta = useVerArbolApiV1ObrasObraIdArbolGet(obraId);
  const crearPropio = useCrearArbolPropioApiV1ObrasObraIdArbolPropioPost<ErrorApi>();
  const agregar = useAgregarNodoApiV1ObrasObraIdArbolNodosPost<ErrorApi>();
  const ajustar = useAjustarNodoApiV1ObrasObraIdArbolNodosNodoIdPatch<ErrorApi>();
  const quitar = useQuitarNodoApiV1ObrasObraIdArbolNodosNodoIdDelete<ErrorApi>();
  const confirmar = useConfirmarVersionApiV1ObrasObraIdArbolVersionesConfirmarPost<ErrorApi>();
  const activar = useActivarVersionApiV1ObrasObraIdArbolVersionesPresupuestoIdActivarPost<ErrorApi>();
  const conceptos = useListarConceptosApiV1ConceptosGet(undefined, { query: { staleTime: 60_000 } });

  /** Dónde se está agregando algo: bajo qué nodo (`null` = un nivel nuevo) y el texto escrito. */
  const [alta, setAlta] = useState<{ padre: string | null; tipo: Tipo; texto: string } | null>(null);
  const [renombrando, setRenombrando] = useState<{ id: string; texto: string } | null>(null);
  const [nota, setNota] = useState('');

  const arbol = consulta.data;
  const hijos = useMemo(() => {
    const por = new Map<string | null, NodoDeArbolDeObraRespuesta[]>();
    for (const n of arbol?.nodos ?? []) {
      const lista = por.get(n.parent_id ?? null) ?? [];
      lista.push(n);
      por.set(n.parent_id ?? null, lista);
    }
    for (const lista of por.values()) lista.sort((a, b) => a.orden - b.orden || a.nombre.localeCompare(b.nombre, 'es', { numeric: true }));
    return por;
  }, [arbol?.nodos]);

  const recargar = () => void queryClient.invalidateQueries({ queryKey: getVerArbolApiV1ObrasObraIdArbolGetQueryKey(obraId) });
  const fallo = (err: unknown, defecto: string) => onError(err instanceof Error ? err.message : defecto);

  if (consulta.isLoading || !arbol) return <div className="text-mute text-xs" style={{ padding: 8 }}>Leyendo el árbol de la obra…</div>;

  async function clonar() {
    if (!window.confirm('Se copia el árbol del prototipo y su presupuesto vigente para esta obra. El prototipo no cambia y las otras obras tampoco. ¿Crear el árbol propio?')) return;
    try {
      const r = await crearPropio.mutateAsync({ obraId });
      recargar();
      onCambio(`Árbol propio creado (${r.clave}): ${r.nodos} nodos copiados y ${r.partidas_religadas} partidas re-ligadas. Tu primer cambio abre el borrador del presupuesto.`);
    } catch (err) {
      fallo(err, 'No se pudo crear el árbol propio.');
    }
  }

  async function agregarNodo() {
    if (alta === null || alta.texto.trim() === '') return;
    try {
      if (alta.tipo === 'concepto') {
        const concepto = (conceptos.data ?? []).find((c) => c.clave.toLowerCase() === alta.texto.trim().toLowerCase());
        if (!concepto) {
          onError(`No hay un concepto con la clave «${alta.texto.trim()}».`);
          return;
        }
        await agregar.mutateAsync({ obraId, data: { tipo: 'concepto', parent_id: alta.padre, concepto_id: concepto.id } });
      } else {
        await agregar.mutateAsync({ obraId, data: { tipo: alta.tipo, parent_id: alta.padre, nombre: alta.texto.trim() } });
      }
      setAlta(null);
      recargar();
    } catch (err) {
      fallo(err, 'No se pudo agregar.');
    }
  }

  async function mover(n: NodoDeArbolDeObraRespuesta, dir: 'up' | 'down') {
    const hermanos = (hijos.get(n.parent_id ?? null) ?? []).map((h) => h.id);
    const nuevos = reordenar(hermanos, n.id, dir);
    if (nuevos === null) return;
    try {
      for (const [id, orden] of nuevos) {
        if ((arbol?.nodos.find((x) => x.id === id)?.orden ?? -1) === orden) continue;
        await ajustar.mutateAsync({ obraId, nodoId: id, data: { orden } });
      }
      recargar();
    } catch (err) {
      fallo(err, 'No se pudo cambiar el lugar.');
    }
  }

  async function renombrar(n: NodoDeArbolDeObraRespuesta) {
    const texto = renombrando?.texto.trim() ?? '';
    setRenombrando(null);
    if (texto === '' || texto === n.nombre) return;
    try {
      await ajustar.mutateAsync({ obraId, nodoId: n.id, data: { nombre: texto } });
      recargar();
    } catch (err) {
      fallo(err, 'No se pudo renombrar.');
    }
  }

  async function quitarNodo(n: NodoDeArbolDeObraRespuesta) {
    const dentro = (hijos.get(n.id) ?? []).length;
    if (!window.confirm(`¿Quitar «${n.nombre}»${dentro > 0 ? ` con todo lo que cuelga de él (${dentro})` : ''} del árbol de esta obra?`)) return;
    try {
      await quitar.mutateAsync({ obraId, nodoId: n.id });
      recargar();
    } catch (err) {
      fallo(err, 'No se pudo quitar.');
    }
  }

  async function confirmarBorrador() {
    try {
      await confirmar.mutateAsync({ obraId, data: { nota: nota.trim() || undefined } });
      setNota('');
      recargar();
      onCambio('Versión confirmada: queda fija. Fíjala como activa cuando quieras que sea la vigente.');
    } catch (err) {
      fallo(err, 'No se pudo confirmar la versión.');
    }
  }

  async function fijarActiva(id: string, version: number) {
    try {
      await activar.mutateAsync({ obraId, presupuestoId: id });
      recargar();
      onCambio(`La versión ${version} es ahora la activa del presupuesto de la obra.`);
    } catch (err) {
      fallo(err, 'No se pudo fijar como activa.');
    }
  }

  const nodoEnLista = (n: NodoDeArbolDeObraRespuesta) => {
    const tipo = n.tipo as Tipo;
    const hijo = HIJO_DE[tipo];
    return (
      <li key={n.id} data-nodo={n.nombre} data-tipo={tipo}>
        <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
          <span className="badge badge--outline">{NOMBRE_DEL_TIPO[tipo]}</span>
          {n.concepto_clave && <span className="mono text-xs">{n.concepto_clave}</span>}
          {arbol.propio && renombrando?.id === n.id ? (
            <input
              aria-label={`Nombre de ${n.nombre}`}
              autoFocus
              value={renombrando.texto}
              onChange={(e) => setRenombrando({ id: n.id, texto: e.target.value })}
              onBlur={() => void renombrar(n)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') e.currentTarget.blur();
                if (e.key === 'Escape') setRenombrando(null);
              }}
            />
          ) : (
            <span title={arbol.propio ? 'Doble clic para renombrar' : n.nombre} onDoubleClick={() => arbol.propio && setRenombrando({ id: n.id, texto: n.nombre })}>
              {descripcionCorta(n.nombre, 56)}
            </span>
          )}
          {n.unidad && <span className="text-mute text-xs">{n.unidad}</span>}
          {arbol.propio && (
            <>
              <button type="button" className="btn btn--ghost btn--sm" aria-label={`Subir ${n.nombre}`} onClick={() => void mover(n, 'up')}>
                ↑
              </button>
              <button type="button" className="btn btn--ghost btn--sm" aria-label={`Bajar ${n.nombre}`} onClick={() => void mover(n, 'down')}>
                ↓
              </button>
              {hijo && (
                <button type="button" className="btn btn--ghost btn--sm" aria-label={`Agregar ${NOMBRE_DEL_TIPO[hijo].toLowerCase()} en ${n.nombre}`} onClick={() => setAlta({ padre: n.id, tipo: hijo, texto: '' })}>
                  + {NOMBRE_DEL_TIPO[hijo]}
                </button>
              )}
              <button type="button" className="btn btn--ghost btn--sm" aria-label={`Quitar ${n.nombre}`} onClick={() => void quitarNodo(n)}>
                Quitar
              </button>
            </>
          )}
        </div>
        {alta?.padre === n.id && formularioDeAlta()}
        {(hijos.get(n.id) ?? []).length > 0 && <ul style={{ listStyle: 'none', margin: '2px 0 2px 14px', padding: 0 }}>{(hijos.get(n.id) ?? []).map(nodoEnLista)}</ul>}
      </li>
    );
  };

  function formularioDeAlta() {
    if (alta === null) return null;
    return (
      <div className="arbol-edicion__alta" role="group" aria-label={`Agregar ${NOMBRE_DEL_TIPO[alta.tipo].toLowerCase()}`}>
        <input
          aria-label={alta.tipo === 'concepto' ? 'Clave del concepto' : `Nombre del ${alta.tipo}`}
          list={alta.tipo === 'concepto' ? 'conceptos-del-arbol-propio' : undefined}
          placeholder={alta.tipo === 'concepto' ? 'Clave de un concepto del catálogo' : `Nombre del ${alta.tipo} · Intro agrega`}
          autoFocus
          value={alta.texto}
          onChange={(e) => setAlta({ ...alta, texto: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void agregarNodo();
            if (e.key === 'Escape') setAlta(null);
          }}
        />
        {alta.tipo === 'concepto' && (
          <datalist id="conceptos-del-arbol-propio">
            {(conceptos.data ?? []).slice(0, 1500).map((c) => (
              <option key={c.id} value={c.clave}>
                {c.descripcion}
              </option>
            ))}
          </datalist>
        )}
        <button type="button" className="btn btn--sm" onClick={() => void agregarNodo()}>
          Agregar
        </button>
        <button type="button" className="btn btn--ghost btn--sm" aria-label="Cancelar" onClick={() => setAlta(null)}>
          ×
        </button>
      </div>
    );
  }

  const borrador = arbol.versiones.find((v) => v.estado === 'borrador');
  return (
    <section aria-label="Árbol de la obra y versiones del presupuesto" style={{ display: 'grid', gap: 8, padding: 8 }}>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
        <strong>Árbol de la obra</strong>
        <span className={arbol.propio ? 'badge badge--ok' : 'badge badge--outline'}>{arbol.propio ? 'Propio de esta obra' : 'Compartido (prototipo base)'}</span>
        <span className="mono text-xs text-mute">{arbol.prototipo_clave}</span>
      </div>
      {!arbol.propio ? (
        <>
          <p className="text-mute text-xs" style={{ margin: 0 }}>
            Esta obra usa el árbol del prototipo base, que comparten otras obras: no se edita. Crea el árbol propio de esta obra para
            cambiarlo sin afectarlas; se copia el árbol y su presupuesto vigente.
          </p>
          <div>
            <button type="button" className="btn btn--sm" disabled={crearPropio.isPending} onClick={() => void clonar()}>
              Crear el árbol propio de esta obra
            </button>
          </div>
        </>
      ) : (
        <p className="text-mute text-xs" style={{ margin: 0 }}>
          Todo lo que cambies aquí es diseño y es reversible hasta que una parte se programe y se asigne. El primer cambio abre un
          borrador del presupuesto; confírmalo cuando esté listo.
        </p>
      )}

      <div role="group" aria-label="Versiones del presupuesto" style={{ display: 'grid', gap: 4 }}>
        <div className="text-xs text-mute">Versiones del presupuesto</div>
        {arbol.versiones.length === 0 && <div className="text-mute text-xs">Sin versiones.</div>}
        {arbol.versiones.map((v) => (
          <div key={v.id} className="row" data-version={v.version} style={{ gap: 6, flexWrap: 'wrap' }}>
            <span className="mono text-xs">v{v.version}</span>
            <span className={v.estado === 'borrador' ? 'badge badge--info' : 'badge badge--outline'}>{v.estado === 'borrador' ? 'Borrador' : 'Confirmada'}</span>
            {v.vigente && <span className="badge badge--ok">Activa</span>}
            <span className="text-xs text-mute">
              {v.partidas} partidas · {dinero(v.monto_total)}
              {v.nota ? ` · ${v.nota}` : ''}
            </span>
            {arbol.propio && v.estado === 'confirmada' && !v.vigente && (
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => void fijarActiva(v.id, v.version)}>
                Fijar como activa
              </button>
            )}
          </div>
        ))}
        {arbol.propio && borrador && (
          <div className="arbol-edicion__alta" role="group" aria-label="Confirmar el borrador">
            <input aria-label="Nota de la versión" placeholder="Qué cambió (opcional)" value={nota} onChange={(e) => setNota(e.target.value)} />
            <button type="button" className="btn btn--sm" disabled={confirmar.isPending} onClick={() => void confirmarBorrador()}>
              Confirmar versión
            </button>
          </div>
        )}
      </div>

      <div className="row" style={{ gap: 6 }}>
        <span className="text-xs text-mute">Niveles, etapas y conceptos</span>
        {arbol.propio && (
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setAlta({ padre: null, tipo: 'nivel', texto: '' })}>
            + Nivel
          </button>
        )}
      </div>
      {alta?.padre === null && formularioDeAlta()}
      <ul style={{ listStyle: 'none', margin: 0, padding: 0 }} aria-label="Árbol">
        {(hijos.get(null) ?? []).map(nodoEnLista)}
      </ul>
    </section>
  );
}
