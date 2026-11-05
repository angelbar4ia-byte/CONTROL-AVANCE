/**
 * La pestaña «Árbol»: se arma la estructura de la obra desde el cuantificador. Nivel → etapa → partida (la
 * actividad de la obra). Se crean niveles y etapas, se agregan partidas con un concepto que ya existe o uno nuevo, se
 * mueven de etapa y se cambia la **unidad** de un concepto, que cambia cómo se mide (m² área, ml lineal, pza conteo…).
 * Solo Control de obra y Costos. Sin botones de guardar: cada cambio llega a la API al hacerlo.
 *
 * Dos advertencias que la pantalla dice: la unidad es **del catálogo** (vale para todas las obras) y no se cambia si el
 * concepto ya mide con algo que la unidad nueva no admite; y una partida de una parte ya asignada no se toca.
 */

import { Plus } from 'lucide-react';
import { useEffect, useMemo, useState, type KeyboardEvent } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getListarEtapasApiV1EtapasGetQueryKey,
  getListarNivelesApiV1NivelesGetQueryKey,
  useListarConceptosApiV1ConceptosGet,
  useListarEtapasApiV1EtapasGet,
  useAsignarNivelALaEtapaApiV1EtapasEtapaIdNivelPut,
  useListarNivelesApiV1NivelesGet,
  useListarUnidadesApiV1UnidadesGet,
} from '@/api/generado/catalogos/catalogos';
import {
  useAgregarPartidaApiV1ObrasObraIdPartidasPost,
  useCambiarUnidadDelConceptoApiV1ConceptosConceptoIdUnidadPut,
  useCrearEtapaApiV1EtapasPost,
  useAjustarEtapaApiV1EtapasEtapaIdPatch,
  useAjustarNivelApiV1NivelesNivelIdPatch,
  useCrearNivelApiV1NivelesPost,
  useMoverPartidaApiV1ActividadesActividadIdUbicacionPut,
  useQuitarPartidaApiV1ActividadesActividadIdPartidaDelete,
  useSubirOBajarPartidaApiV1ActividadesActividadIdLugarPut,
} from '@/api/generado/arbol/arbol';
import { useCrearConceptoEnLaObraApiV1ObrasObraIdConceptosNuevosPost } from '@/api/generado/partes/partes';
import type { ActividadRespuesta } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';
import { descripcionCorta, reordenar } from './arbol';
import { ArbolDeLaObra } from './ArbolDeLaObra';
import { CambioDeUnidadDelConcepto } from './CambioDeUnidadDelConcepto';
import { MatricesDeActividad } from './MatricesDeActividad';
import { NOMBRE_DE_TIPO, tipoDeMedicion } from './tipos';

interface Props {
  readonly obraId: string;
  readonly actividades: readonly ActividadRespuesta[];
  /** Algo cambió en el servidor: hay que volver a leer actividades y cantidades. */
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

const SIN_ETAPA = '__sin_etapa__';

function Alta({ etiqueta, campos, onCrear, ocupado }: {
  readonly etiqueta: string;
  readonly campos: readonly [string, string];
  readonly onCrear: (a: string, b: string) => Promise<void>;
  readonly ocupado: boolean;
}) {
  const [abierto, setAbierto] = useState(false);
  const [a, setA] = useState('');
  const [b, setB] = useState('');
  const intro = (e: KeyboardEvent) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    if (a.trim() === '' || b.trim() === '' || ocupado) return;
    void onCrear(a.trim(), b.trim()).then(() => {
      setA('');
      setB('');
      setAbierto(false);
    });
  };
  if (!abierto) {
    return (
      <button type="button" className="btn btn--ghost btn--sm" aria-label={etiqueta} onClick={() => setAbierto(true)}>
        <Plus size={12} aria-hidden /> {etiqueta.replace(/^Agregar /, '').replace(/^Nuev[oa] /, '')}
      </button>
    );
  }
  return (
    <div className="arbol-edicion__alta" role="group" aria-label={etiqueta}>
      <input aria-label={`${etiqueta}: ${campos[0]}`} placeholder={campos[0]} value={a} onChange={(e) => setA(e.target.value)} onKeyDown={intro} autoFocus />
      <input aria-label={`${etiqueta}: ${campos[1]}`} placeholder={`${campos[1]} · Intro crea`} value={b} onChange={(e) => setB(e.target.value)} onKeyDown={intro} />
    </div>
  );
}

function NuevaPartida({ obraId, etapaId, onCreada, onError }: {
  readonly obraId: string;
  readonly etapaId: string | null;
  readonly onCreada: (aviso: string) => void;
  readonly onError: (m: string) => void;
}) {
  const [abierto, setAbierto] = useState(false);
  const [clave, setClave] = useState('');
  const [descripcion, setDescripcion] = useState('');
  const conceptos = useListarConceptosApiV1ConceptosGet(undefined, { query: { enabled: abierto, staleTime: 60_000 } });
  const unidades = useListarUnidadesApiV1UnidadesGet(undefined, { query: { enabled: abierto, staleTime: 60_000 } });
  const agregar = useAgregarPartidaApiV1ObrasObraIdPartidasPost<ErrorApi>();
  const crearConcepto = useCrearConceptoEnLaObraApiV1ObrasObraIdConceptosNuevosPost<ErrorApi>();
  const existente = useMemo(
    () => (conceptos.data ?? []).find((c) => c.clave.toLowerCase() === clave.trim().toLowerCase()),
    [conceptos.data, clave],
  );
  const esNueva = clave.trim() !== '' && !existente && conceptos.data !== undefined;
  const cerrar = () => {
    setClave('');
    setDescripcion('');
    setAbierto(false);
  };

  // Intro antes de que llegue la lista de conceptos no se pierde: queda pendiente y se aplica al cargar.
  const [pendiente, setPendiente] = useState(false);
  useEffect(() => {
    if (pendiente && conceptos.data !== undefined) {
      setPendiente(false);
      void ponerExistente();
    }
    // `ponerExistente` lee el estado del render en que llegó la lista.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendiente, conceptos.data]);

  async function ponerExistente() {
    if (!existente) return;
    try {
      await agregar.mutateAsync({ obraId, data: { concepto_id: existente.id, etapa_id: etapaId ?? undefined } });
      onCreada(`Partida ${existente.clave} agregada: llega sin cantidad, se mide en el plano.`);
      cerrar();
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo agregar la partida.');
    }
  }
  async function crearNuevo(unidadId: string) {
    if (!esNueva || descripcion.trim() === '' || unidadId === '') return;
    try {
      const r = await crearConcepto.mutateAsync({
        obraId,
        data: { clave: clave.trim(), descripcion: descripcion.trim(), unidad_id: unidadId, etapa_id: etapaId ?? undefined },
      });
      onCreada(`Concepto ${r.clave} creado y agregado como partida.`);
      cerrar();
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo crear el concepto.');
    }
  }

  if (!abierto) {
    return (
      <button type="button" className="btn btn--ghost btn--sm" aria-label="Agregar partida" onClick={() => setAbierto(true)}>
        <Plus size={12} aria-hidden /> Partida
      </button>
    );
  }
  return (
    <div className="arbol-edicion__alta" role="group" aria-label="Nueva partida">
      <input
        aria-label="Concepto de la partida (clave)"
        list="conceptos-del-arbol"
        placeholder="Clave de un concepto (o una nueva)"
        value={clave}
        onChange={(e) => setClave(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            if (conceptos.data === undefined) setPendiente(true);
            else void ponerExistente();
          }
        }}
      />
      <datalist id="conceptos-del-arbol">
        {(conceptos.data ?? []).slice(0, 1500).map((c) => (
          <option key={c.id} value={c.clave}>
            {c.descripcion}
          </option>
        ))}
      </datalist>
      {existente && <span className="text-mute text-xs">{existente.descripcion} · Intro la agrega</span>}
      {esNueva && (
        <>
          <input aria-label="Descripción del concepto nuevo" placeholder="Descripción" value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
          <select aria-label="Unidad del concepto nuevo" defaultValue="" onChange={(e) => void crearNuevo(e.target.value)}>
            <option value="">Unidad: elige para crearlo…</option>
            {(unidades.data ?? []).map((u) => (
              <option key={u.id} value={u.id}>
                {u.clave} · {u.nombre}
              </option>
            ))}
          </select>
        </>
      )}
      <button type="button" className="btn btn--ghost btn--sm" aria-label="Cerrar nueva partida" onClick={cerrar}>
        ×
      </button>
    </div>
  );
}

export function PanelDelArbol({ obraId, actividades, onCambio, onError }: Props) {
  /** Qué se ve: las partidas de la obra, o su árbol y las versiones del presupuesto (D-624). */
  const [vista, setVista] = useState<'partidas' | 'arbol'>('partidas');
  const [matricesAbiertas, setMatricesAbiertas] = useState<ReadonlySet<string>>(new Set());
  /** Un cambio de unidad que cruza de tipo en curso: pide equivalencia en vez de cambiarse directo. */
  const [cambioDeUnidad, setCambioDeUnidad] = useState<{ actividad: ActividadRespuesta; unidadId: string } | null>(null);
  const niveles = useListarNivelesApiV1NivelesGet();
  const etapas = useListarEtapasApiV1EtapasGet();
  const unidades = useListarUnidadesApiV1UnidadesGet(undefined, { query: { staleTime: 60_000 } });
  const crearNivel = useCrearNivelApiV1NivelesPost<ErrorApi>();
  const crearEtapa = useCrearEtapaApiV1EtapasPost<ErrorApi>();
  const ajustarNivel = useAjustarNivelApiV1NivelesNivelIdPatch<ErrorApi>();
  const ajustarEtapa = useAjustarEtapaApiV1EtapasEtapaIdPatch<ErrorApi>();
  /** El nivel o la etapa cuyo nombre se está escribiendo (doble clic), con lo escrito. */
  const [renombrando, setRenombrando] = useState<{ clave: string; texto: string } | null>(null);
  const cambiarUnidad = useCambiarUnidadDelConceptoApiV1ConceptosConceptoIdUnidadPut<ErrorApi>();
  const mover = useMoverPartidaApiV1ActividadesActividadIdUbicacionPut<ErrorApi>();
  const quitar = useQuitarPartidaApiV1ActividadesActividadIdPartidaDelete<ErrorApi>();
  const lugar = useSubirOBajarPartidaApiV1ActividadesActividadIdLugarPut<ErrorApi>();
  const asignarNivel = useAsignarNivelALaEtapaApiV1EtapasEtapaIdNivelPut<ErrorApi>();

  const unidadPorClave = useMemo(() => new Map((unidades.data ?? []).map((u) => [u.clave, u.id])), [unidades.data]);
  const partidasPorEtapa = useMemo(() => {
    const por = new Map<string, ActividadRespuesta[]>();
    for (const a of actividades) por.set(a.etapa_id ?? SIN_ETAPA, [...(por.get(a.etapa_id ?? SIN_ETAPA) ?? []), a]);
    // Por el lugar que se les dio (0116) y, sin él, por clave: así se ven y así suben y bajan.
    for (const lista of por.values()) {
      lista.sort(
        (x, y) =>
          (x.orden ?? Number.MAX_SAFE_INTEGER) - (y.orden ?? Number.MAX_SAFE_INTEGER) ||
          String(x.concepto_clave ?? '').localeCompare(String(y.concepto_clave ?? ''), 'es', { numeric: true }),
      );
    }
    return por;
  }, [actividades]);
  const datosDeEtapas = etapas.data;
  const etapasPorNivel = useMemo(() => {
    const por = new Map<string, NonNullable<typeof datosDeEtapas>>();
    for (const e of datosDeEtapas ?? []) por.set(e.nivel_id ?? '', [...(por.get(e.nivel_id ?? '') ?? []), e]);
    return por;
  }, [datosDeEtapas]);

  const recargar = () => {
    void queryClient.invalidateQueries({ queryKey: getListarNivelesApiV1NivelesGetQueryKey() });
    void queryClient.invalidateQueries({ queryKey: getListarEtapasApiV1EtapasGetQueryKey() });
  };

  /** Sube o baja un nivel o una etapa entre sus hermanos. Es del catálogo: vale para todas las obras. */
  async function cambiarLugar(tipo: 'nivel' | 'etapa', id: string, hermanos: readonly string[], dir: 'up' | 'down') {
    const nuevos = reordenar(hermanos, id, dir);
    if (nuevos === null) {
      onError('Ya está en ese extremo.');
      return;
    }
    try {
      for (const [hermano, orden] of nuevos) {
        const actual = tipo === 'nivel' ? niveles.data?.find((n) => n.id === hermano)?.orden : etapas.data?.find((e) => e.id === hermano)?.orden;
        if (actual === orden) continue;
        if (tipo === 'nivel') await ajustarNivel.mutateAsync({ nivelId: hermano, data: { orden } });
        else await ajustarEtapa.mutateAsync({ etapaId: hermano, data: { orden } });
      }
      recargar();
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo cambiar el lugar.');
    }
  }

  async function guardarNombre(tipo: 'nivel' | 'etapa', id: string, original: string) {
    const nuevo = renombrando?.texto.trim() ?? '';
    setRenombrando(null);
    if (nuevo === '' || nuevo === original) return;
    try {
      if (tipo === 'nivel') await ajustarNivel.mutateAsync({ nivelId: id, data: { descripcion: nuevo } });
      else await ajustarEtapa.mutateAsync({ etapaId: id, data: { descripcion: nuevo } });
      recargar();
      onCambio(`${tipo === 'nivel' ? 'Nivel' : 'Etapa'} renombrado.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo renombrar.');
    }
  }

  /** El nombre de un nivel o etapa: se lee como texto; con doble clic se escribe, Intro guarda y Esc cancela. */
  const nombreEditable = (tipo: 'nivel' | 'etapa', id: string, descripcion: string) => {
    const llave = `${tipo}:${id}`;
    if (renombrando?.clave === llave) {
      return (
        <input
          aria-label={`Nombre del ${tipo}`}
          autoFocus
          value={renombrando.texto}
          onChange={(e) => setRenombrando({ clave: llave, texto: e.target.value })}
          onBlur={() => void guardarNombre(tipo, id, descripcion)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') e.currentTarget.blur();
            if (e.key === 'Escape') setRenombrando(null);
          }}
        />
      );
    }
    return (
      <span className="text-mute" title="Doble clic para renombrar" onDoubleClick={() => setRenombrando({ clave: llave, texto: descripcion })}>
        {descripcion}
      </span>
    );
  };

  const flechas = (tipo: 'nivel' | 'etapa', id: string, hermanos: readonly string[], nombre: string) => (
    <span className="row" style={{ gap: 2 }}>
      <button type="button" className="btn btn--ghost btn--sm" aria-label={`Subir ${nombre}`} title="Subir" onClick={() => void cambiarLugar(tipo, id, hermanos, 'up')}>
        ↑
      </button>
      <button type="button" className="btn btn--ghost btn--sm" aria-label={`Bajar ${nombre}`} title="Bajar" onClick={() => void cambiarLugar(tipo, id, hermanos, 'down')}>
        ↓
      </button>
    </span>
  );

  async function nuevoNivel(clave: string, descripcion: string) {
    try {
      await crearNivel.mutateAsync({ data: { clave, descripcion } });
      recargar();
      onCambio(`Nivel ${clave.toUpperCase()} creado.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo crear el nivel.');
      throw err;
    }
  }
  async function nuevaEtapa(nivelId: string, clave: string, descripcion: string) {
    try {
      await crearEtapa.mutateAsync({ data: { nivel_id: nivelId, clave, descripcion } });
      recargar();
      onCambio(`Etapa ${clave.toUpperCase()} creada.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo crear la etapa.');
      throw err;
    }
  }
  async function conUnidad(a: ActividadRespuesta, unidadId: string) {
    if (!a.concepto_id || unidadId === '') return;
    const destino = (unidades.data ?? []).find((u) => u.id === unidadId);
    const tipoActual = tipoDeMedicion(a.unidad);
    const tipoNuevo = tipoDeMedicion(destino?.clave);
    if (destino && tipoNuevo !== tipoActual) {
      // Cruza de tipo (pieza, longitud, área): pide equivalencia y crea una versión del concepto.
      setCambioDeUnidad({ actividad: a, unidadId });
      return;
    }
    try {
      const r = await cambiarUnidad.mutateAsync({ conceptoId: a.concepto_id, data: { unidad_id: unidadId } });
      onCambio(
        `${a.concepto_clave ?? 'El concepto'} ahora es ${r.unidad_nueva}` +
          (r.tipo_nuevo ? ` y se mide como ${NOMBRE_DE_TIPO[r.tipo_nuevo as keyof typeof NOMBRE_DE_TIPO] ?? r.tipo_nuevo}` : '') +
          '. Vale para todas las obras.' +
          (r.enlaces_por_revisar > 0
            ? ` ${r.enlaces_por_revisar} enlace(s) ya no caben en la unidad nueva y quedaron por revisar.`
            : ''),
      );
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo cambiar la unidad.');
    }
  }
  async function subirOBajar(a: ActividadRespuesta, direccion: 'up' | 'down') {
    try {
      await lugar.mutateAsync({ actividadId: a.id, data: { direccion } });
      onCambio(`${a.concepto_clave ?? 'La partida'} ${direccion === 'up' ? 'subió' : 'bajó'}.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo cambiar el lugar de la partida.');
    }
  }
  /** Pasa una partida a la etapa anterior o siguiente del árbol, en el orden en que se ven (Subir/Bajar de nivel del mockup). */
  async function aOtraEtapa(a: ActividadRespuesta, sentido: -1 | 1) {
    const orden = (niveles.data ?? []).flatMap((n) => (etapasPorNivel.get(n.id) ?? []).map((e) => e.id));
    const i = a.etapa_id ? orden.indexOf(a.etapa_id) : -1;
    const destino = i === -1 ? undefined : orden[i + sentido];
    if (destino === undefined) {
      onError(sentido === -1 ? 'Ya está en la primera etapa.' : 'Ya está en la última etapa.');
      return;
    }
    await aEtapa(a, destino);
  }
  /** Pasa una etapa al nivel anterior o siguiente. */
  async function aOtroNivel(etapaId: string, nivelActual: string, sentido: -1 | 1) {
    const ids = (niveles.data ?? []).map((n) => n.id);
    const destino = ids[ids.indexOf(nivelActual) + sentido];
    if (destino === undefined) {
      onError(sentido === -1 ? 'Ya está en el primer nivel.' : 'Ya está en el último nivel.');
      return;
    }
    try {
      await asignarNivel.mutateAsync({ etapaId, data: { nivel_id: destino } });
      recargar();
      onCambio('Etapa pasada a otro nivel.');
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo pasar la etapa de nivel.');
    }
  }
  async function aEtapa(a: ActividadRespuesta, etapaId: string) {
    try {
      await mover.mutateAsync({ actividadId: a.id, data: { etapa_id: etapaId === SIN_ETAPA ? null : etapaId } });
      onCambio(`${a.concepto_clave ?? 'La partida'} movida de etapa.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo mover la partida.');
    }
  }

  async function quitarPartida(a: ActividadRespuesta) {
    if (!window.confirm(`¿Quitar la partida ${a.concepto_clave ?? ''} de la obra? El concepto sigue en el catálogo.`)) return;
    try {
      await quitar.mutateAsync({ actividadId: a.id });
      onCambio(`${a.concepto_clave ?? 'La partida'} quitada de la obra.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo quitar la partida.');
    }
  }

  const filaDePartida = (a: ActividadRespuesta) => {
    const tipo = tipoDeMedicion(a.unidad);
    const conMatrices = matricesAbiertas.has(a.id);
    return (
      <li key={a.id} className="arbol-edicion__partida" data-partida={a.concepto_clave ?? a.id}>
        <span className="arbol-edicion__concepto" title={String(a.descripcion ?? '')}>
          <span className="mono">{a.concepto_clave ?? '—'}</span> · {descripcionCorta(a.descripcion)}
        </span>
        <select
          aria-label={`Unidad de ${a.concepto_clave ?? 'la partida'}`}
          value={a.unidad ? (unidadPorClave.get(a.unidad) ?? '') : ''}
          disabled={!a.concepto_id}
          title="La unidad decide cómo se mide; cambia el catálogo"
          onChange={(e) => void conUnidad(a, e.target.value)}
        >
          {!a.unidad || !unidadPorClave.has(a.unidad) ? <option value="">{a.unidad ?? 'sin unidad'}</option> : null}
          {(unidades.data ?? []).map((u) => (
            <option key={u.id} value={u.id}>
              {u.clave}
            </option>
          ))}
        </select>
        <span className="badge badge--outline" title="Cómo se mide: sale de su unidad">
          {tipo ? NOMBRE_DE_TIPO[tipo] : '—'}
        </span>
        <select
          aria-label={`Mover ${a.concepto_clave ?? 'la partida'} a`}
          value={a.etapa_id ?? SIN_ETAPA}
          onChange={(e) => void aEtapa(a, e.target.value)}
        >
          <option value={SIN_ETAPA}>Sin etapa</option>
          {(etapas.data ?? []).map((e) => (
            <option key={e.id} value={e.id}>
              {e.clave}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          style={{ gridColumn: '1 / -1', justifySelf: 'start' }}
          aria-expanded={conMatrices}
          aria-label={`Matrices de ${a.concepto_clave ?? 'la partida'}`}
          title="Las matrices del concepto: agregarlas, quitarlas, su cantidad y su costo (cambia el catálogo)"
          onClick={() =>
            setMatricesAbiertas((actual) => {
              const siguiente = new Set(actual);
              if (siguiente.has(a.id)) siguiente.delete(a.id);
              else siguiente.add(a.id);
              return siguiente;
            })
          }
        >
          {conMatrices ? 'Ocultar matrices' : 'Matrices'}
        </button>
        <span className="row" style={{ gap: 2, justifySelf: 'start' }} role="group" aria-label={`Mover ${a.concepto_clave ?? 'la partida'} en el árbol`}>
          <button type="button" className="btn btn--ghost btn--sm" aria-label={`Subir posición de ${a.concepto_clave ?? 'la partida'}`} title="Subir posición" onClick={() => void subirOBajar(a, 'up')}>
            ↑
          </button>
          <button type="button" className="btn btn--ghost btn--sm" aria-label={`Bajar posición de ${a.concepto_clave ?? 'la partida'}`} title="Bajar posición" onClick={() => void subirOBajar(a, 'down')}>
            ↓
          </button>
          <button type="button" className="btn btn--ghost btn--sm" aria-label={`Subir ${a.concepto_clave ?? 'la partida'} a la etapa anterior`} title="Subir de nivel (pasa a la etapa anterior)" onClick={() => void aOtraEtapa(a, -1)}>
            ⇤
          </button>
          <button type="button" className="btn btn--ghost btn--sm" aria-label={`Bajar ${a.concepto_clave ?? 'la partida'} a la etapa siguiente`} title="Bajar de nivel (pasa a la etapa siguiente)" onClick={() => void aOtraEtapa(a, 1)}>
            ⇥
          </button>
        </span>
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          style={{ justifySelf: 'start' }}
          aria-label={`Quitar ${a.concepto_clave ?? 'la partida'}`}
          title="Quita la partida de la obra; solo si no tiene trazos, avance ni estimaciones"
          onClick={() => void quitarPartida(a)}
        >
          Quitar
        </button>
        {cambioDeUnidad?.actividad.id === a.id && a.concepto_id && (
          <div style={{ gridColumn: '1 / -1' }}>
            <CambioDeUnidadDelConcepto
              conceptoId={a.concepto_id}
              clave={a.concepto_clave ?? 'El concepto'}
              unidadActual={a.unidad ?? 'sin unidad'}
              unidadId={cambioDeUnidad.unidadId}
              unidadNueva={(unidades.data ?? []).find((u) => u.id === cambioDeUnidad.unidadId)?.clave ?? ''}
              onListo={(aviso) => {
                setCambioDeUnidad(null);
                if (aviso) onCambio(aviso);
              }}
              onError={onError}
            />
          </div>
        )}
        {conMatrices && (
          <div style={{ gridColumn: '1 / -1' }}>
            <MatricesDeActividad actividadId={a.id} puedeEditar />
          </div>
        )}
      </li>
    );
  };

  if (vista === 'arbol') {
    return (
      <div className="arbol-edicion" role="region" aria-label="Árbol de la obra">
        <div className="row" role="group" aria-label="Qué editar" style={{ gap: 4, padding: '6px 8px 0' }}>
          <button type="button" aria-pressed={false} className="btn btn--ghost btn--sm" onClick={() => setVista('partidas')}>
            Partidas de la obra
          </button>
          <button type="button" aria-pressed className="btn btn--sm">
            Árbol y versiones
          </button>
        </div>
        <ArbolDeLaObra obraId={obraId} onCambio={onCambio} onError={onError} />
      </div>
    );
  }

  return (
    <div className="arbol-edicion" role="region" aria-label="Armar el árbol">
      <div className="row" role="group" aria-label="Qué editar" style={{ gap: 4, padding: '6px 8px 0' }}>
        <button type="button" aria-pressed className="btn btn--sm">
          Partidas de la obra
        </button>
        <button type="button" aria-pressed={false} className="btn btn--ghost btn--sm" onClick={() => setVista('arbol')}>
          Árbol y versiones
        </button>
      </div>
      <p className="text-mute text-xs" style={{ margin: '6px 8px' }}>
        Aquí armas el árbol: niveles, etapas y partidas. La unidad de un concepto decide cómo se mide y es del catálogo (vale para
        todas las obras).
      </p>
      <div style={{ padding: '0 8px' }}>
        <Alta etiqueta="Nuevo nivel" campos={['Clave', 'Descripción']} ocupado={crearNivel.isPending} onCrear={nuevoNivel} />
      </div>
      <ul className="arbol-edicion__niveles" aria-label="Niveles">
        {(niveles.data ?? []).map((n) => (
          <li key={n.id} data-nivel={n.clave}>
            <div className="arbol-edicion__titulo">
              <strong>{n.clave}</strong> {nombreEditable('nivel', n.id, n.descripcion)}
              {flechas('nivel', n.id, (niveles.data ?? []).map((x) => x.id), n.clave)}
              <Alta etiqueta={`Nueva etapa en ${n.clave}`} campos={['Clave', 'Descripción']} ocupado={crearEtapa.isPending} onCrear={(c, d) => nuevaEtapa(n.id, c, d)} />
            </div>
            <ul aria-label={`Etapas de ${n.clave}`}>
              {(etapasPorNivel.get(n.id) ?? []).map((e) => (
                <li key={e.id} data-etapa={e.clave}>
                  <div className="arbol-edicion__titulo">
                    <strong>{e.clave}</strong> {nombreEditable('etapa', e.id, e.descripcion)}
                    {flechas('etapa', e.id, (etapasPorNivel.get(n.id) ?? []).map((x) => x.id), e.clave)}
                    <span className="row" style={{ gap: 2 }}>
                      <button type="button" className="btn btn--ghost btn--sm" aria-label={`Pasar ${e.clave} al nivel anterior`} title="Subir de nivel (pasa al nivel anterior)" onClick={() => void aOtroNivel(e.id, n.id, -1)}>
                        ⇤
                      </button>
                      <button type="button" className="btn btn--ghost btn--sm" aria-label={`Pasar ${e.clave} al nivel siguiente`} title="Bajar de nivel (pasa al nivel siguiente)" onClick={() => void aOtroNivel(e.id, n.id, 1)}>
                        ⇥
                      </button>
                    </span>
                    <NuevaPartida obraId={obraId} etapaId={e.id} onCreada={onCambio} onError={onError} />
                  </div>
                  <ul aria-label={`Partidas de ${e.clave}`}>{(partidasPorEtapa.get(e.id) ?? []).map(filaDePartida)}</ul>
                </li>
              ))}
            </ul>
          </li>
        ))}
        <li data-nivel="sin-etapa">
          <div className="arbol-edicion__titulo">
            <strong>Sin etapa</strong> <span className="text-mute">partidas sueltas</span>
            <NuevaPartida obraId={obraId} etapaId={null} onCreada={onCambio} onError={onError} />
          </div>
          <ul aria-label="Partidas sin etapa">{(partidasPorEtapa.get(SIN_ETAPA) ?? []).map(filaDePartida)}</ul>
        </li>
      </ul>
    </div>
  );
}
