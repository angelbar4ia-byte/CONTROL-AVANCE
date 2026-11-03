/**
 * Las mediciones del plano (la capa sombra, migración 0088): grupos con nombre de trazos de un tipo
 * —área, lineal o conteo— que se dibujan una vez y se asignan a uno o varios conceptos. La losa de
 * cimentación se mide por espacios (recámara 1, cocina…) y su total es la suma de ellos.
 *
 * Un clic en el nombre la vuelve **la medición activa**: lo que se dibuje entra a ella, y la barra
 * resalta el bloque de su tipo. Las que aún no alimentan ningún concepto se marcan «sin asignar».
 */

import { ChevronRight, Link2, Pencil, Plus, Trash2, X } from 'lucide-react';
import { useMemo, useState, type FormEvent } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useAsignarMedicionApiV1MedicionesMedicionIdAsignacionesPost,
  useCrearMedicionApiV1PlanosPlanoIdMedicionesPost,
  useEliminarMedicionApiV1MedicionesMedicionIdDelete,
  usePonerElementoEnMedicionApiV1MedicionesMedicionIdElementoPut,
  useQuitarAsignacionApiV1AsignacionesDeMedicionAsignacionIdDelete,
  useRenombrarMedicionApiV1MedicionesMedicionIdPatch,
} from '@/api/generado/mediciones/mediciones';
import type { ActividadRespuesta, ElementoRespuesta, MedicionRespuesta } from '@/api/generado/modelo';
import { fmtNum } from '@/lib/formato';
import { OpcionesDeMatriz } from './MatricesDeActividad';
import { PanelDeElementos, UNIDAD_DEL_PESO } from './PanelDeElementos';
import { tipoDeMedicion } from './tipos';
import {
  arbolDeMediciones,
  coloresDeMediciones,
  candidatasAMadre,
  MEDIDAS_ASIGNABLES,
  NOMBRE_DE_TIPO_DE_MEDICION,
  type NodoDeMedicion,
  type TipoDeMedicionSombra,
} from './mediciones';

interface Props {
  readonly planoId: string;
  readonly mediciones: readonly MedicionRespuesta[];
  readonly cargando: boolean;
  readonly actividades: readonly ActividadRespuesta[];
  /** Los elementos con peso (K1…) y si quien mira puede ponerles peso (Control de obra y Costos). */
  readonly elementos: readonly ElementoRespuesta[];
  readonly puedePonerPeso: boolean;
  /** El concepto que se está midiendo en el árbol: trae elegido el destino de una asignación. */
  readonly conceptoEnFoco?: string;
  /** Sobre qué se crea una medición: el concepto (o la matriz) elegido en el Presupuesto. Sin él no se crea. */
  readonly destino?: DestinoDeMedicion | null;
  /** Se pidió crear sin tener elegido un concepto o una matriz: la pantalla lleva al Presupuesto. */
  readonly onPedirDestino?: () => void;
  readonly activaId: string | null;
  readonly onActivar: (medicion: MedicionRespuesta | null) => void;
  /** Algo cambió en el servidor: hay que volver a leer mediciones, trazos y cantidades. */
  readonly onCambio: (aviso?: string) => void;
  readonly onError: (mensaje: string) => void;
}

/** El concepto o la matriz sobre los que se crea una medición. */
export interface DestinoDeMedicion {
  readonly actividadId: string;
  readonly matrizId?: string;
  /** «EST-10101 LOSA ENTREPISO» o «MOE-10001 MO LOSA MACIZA». */
  readonly nombre: string;
  readonly unidad: string | null;
}

/** La unidad que se elige al crear una medición decide su tipo (m² y m³ miden con un área; ml, con una longitud; pza, con un conteo). */
export const UNIDADES_DE_MEDICION: readonly { readonly valor: string; readonly nombre: string; readonly tipo: TipoDeMedicionSombra }[] = [
  { valor: 'm²', nombre: 'm² · Metro cuadrado', tipo: 'area' },
  { valor: 'm³', nombre: 'm³ · Metro cúbico', tipo: 'area' },
  { valor: 'ml', nombre: 'ml · Metro lineal', tipo: 'lineal' },
  { valor: 'pza', nombre: 'pza · Pieza', tipo: 'conteo' },
];

/** La unidad de la lista que más se parece a la del concepto (m2, M2, m², mts…); `m²` si no se sabe. */
export function unidadDeMedicionPorDefecto(unidad: string | null | undefined): string {
  const tipo = tipoDeMedicion(unidad);
  if (tipo === 'lineal') return 'ml';
  if (tipo === 'conteo') return 'pza';
  if (tipo === 'volumen') return 'm³';
  return 'm²';
}

function etiquetaActividad(a: ActividadRespuesta): string {
  const donde = [a.nivel_clave, a.etapa_clave].filter(Boolean).join(' · ');
  const que = a.concepto_clave ?? a.descripcion ?? 'Actividad';
  return donde ? `${que} — ${donde}` : String(que);
}

export function PanelDeMediciones({
  planoId,
  mediciones,
  cargando,
  actividades,
  elementos,
  puedePonerPeso,
  conceptoEnFoco,
  destino = null,
  onPedirDestino,
  activaId,
  onActivar,
  onCambio,
  onError,
}: Props) {
  const arbol = useMemo(() => arbolDeMediciones(mediciones), [mediciones]);
  /** El mismo color con que se pinta la medición en el plano. */
  const colores = useMemo(() => coloresDeMediciones(mediciones), [mediciones]);
  const [cerradas, setCerradas] = useState<ReadonlySet<string>>(new Set());
  const [creando, setCreando] = useState<{ parentId: string | null; tipo: TipoDeMedicionSombra; unidad: string } | null>(null);
  const asignarAlCrear = useAsignarMedicionApiV1MedicionesMedicionIdAsignacionesPost<ErrorApi>();
  const [nombreNuevo, setNombreNuevo] = useState('');
  const [renombrando, setRenombrando] = useState<{ id: string; nombre: string } | null>(null);
  const [asignando, setAsignando] = useState<string | null>(null);
  const [porBorrar, setPorBorrar] = useState<string | null>(null);
  const ponerElemento = usePonerElementoEnMedicionApiV1MedicionesMedicionIdElementoPut<ErrorApi>();

  const crear = useCrearMedicionApiV1PlanosPlanoIdMedicionesPost<ErrorApi>();
  const renombrar = useRenombrarMedicionApiV1MedicionesMedicionIdPatch<ErrorApi>();
  const eliminar = useEliminarMedicionApiV1MedicionesMedicionIdDelete<ErrorApi>();
  const quitar = useQuitarAsignacionApiV1AsignacionesDeMedicionAsignacionIdDelete<ErrorApi>();

  const alternar = (id: string) =>
    setCerradas((actual) => {
      const s = new Set(actual);
      if (s.has(id)) s.delete(id);
      else s.add(id);
      return s;
    });

  async function alCrear(e: FormEvent) {
    e.preventDefault();
    if (!creando || nombreNuevo.trim() === '') return;
    try {
      const r = await crear.mutateAsync({
        planoId,
        data: { nombre: nombreNuevo.trim(), tipo: creando.tipo, parent_id: creando.parentId },
      });
      setCreando(null);
      setNombreNuevo('');
      // Creada sobre un concepto o una matriz: se asigna a él en el mismo paso, con la medida que corresponde a su tipo.
      let aviso = `Medición «${nombreNuevo.trim()}» creada.`;
      if (destino && creando.parentId === null) {
        // Solo se asigna sola si el concepto se mide igual que la medición (m² con área, ml con longitud, pza con conteo): un
        // concepto en kg se mide con un elemento y su peso, y un volumen con un espesor; eso se asigna a mano.
        const igual = tipoDeMedicion(destino.unidad) === (creando.tipo === 'area' ? 'area' : creando.tipo);
        const medida = !igual ? null : creando.tipo === 'area' ? (creando.unidad === 'm²' ? 'area' : null) : creando.tipo === 'lineal' ? 'longitud' : 'conteo';
        if (medida) {
          try {
            await asignarAlCrear.mutateAsync({
              medicionId: r.id,
              data: {
                actividad_id: destino.actividadId,
                matriz_concepto_id: destino.matrizId ?? null,
                medida,
                factor: '1',
                usar_peso: false,
              },
            });
            aviso = `Medición «${nombreNuevo.trim()}» creada sobre ${destino.nombre}: lo que dibujes suma ahí.`;
          } catch (err) {
            aviso = `Medición «${nombreNuevo.trim()}» creada, pero no se pudo asignar a ${destino.nombre}: ${err instanceof Error ? err.message : 'error'}.`;
          }
        } else {
          aviso = `Medición «${nombreNuevo.trim()}» creada sobre ${destino.nombre}. Este concepto se mide distinto (volumen con espesor, o kg con un elemento y su peso): asígnala con su factor.`;
        }
      }
      onCambio(aviso);
      const hecha: MedicionRespuesta = {
        id: r.id,
        parent_id: creando.parentId,
        nombre: nombreNuevo.trim(),
        tipo: creando.tipo,
        orden: 9999,
        n_trazos: 0,
        valor: '0',
        unidad: creando.unidad,
        asignaciones: [],
      };
      onActivar(hecha); // una medición recién hecha es la que se va a dibujar
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo crear la medición.');
    }
  }

  async function alRenombrar(e: FormEvent) {
    e.preventDefault();
    if (!renombrando || renombrando.nombre.trim() === '') return;
    try {
      await renombrar.mutateAsync({ medicionId: renombrando.id, data: { nombre: renombrando.nombre.trim() } });
      setRenombrando(null);
      onCambio('Medición renombrada.');
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo renombrar.');
    }
  }

  async function alCambiarElemento(m: MedicionRespuesta, elementoId: string) {
    try {
      await ponerElemento.mutateAsync({ medicionId: m.id, data: { elemento_id: elementoId === '' ? null : elementoId } });
      onCambio(elementoId === '' ? `«${m.nombre}» ya no tiene elemento.` : `«${m.nombre}» mide ahora a ${elementos.find((e) => e.id === elementoId)?.nombre ?? 'un elemento'}.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo cambiar el elemento.');
    }
  }

  async function alEliminar(m: MedicionRespuesta) {
    try {
      await eliminar.mutateAsync({ medicionId: m.id });
      setPorBorrar(null);
      if (activaId === m.id) onActivar(null);
      onCambio(
        m.asignaciones.length > 0
          ? `Medición «${m.nombre}» borrada con sus ${m.asignaciones.length} ${m.asignaciones.length === 1 ? 'asignación' : 'asignaciones'}; los conceptos se recalcularon y sus trazos quedan sueltos.`
          : `Medición «${m.nombre}» borrada; sus trazos quedan sueltos.`,
      );
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo borrar la medición.');
    }
  }

  async function alQuitarAsignacion(id: string) {
    try {
      const r = await quitar.mutateAsync({ asignacionId: id });
      onCambio(`Asignación quitada: ${r.trazos_enlazados} ${r.trazos_enlazados === 1 ? 'enlace' : 'enlaces'} dejaron de sumar.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo quitar la asignación.');
    }
  }

  const fila = (n: NodoDeMedicion<MedicionRespuesta>) => {
    const m = n.medicion;
    const conHijos = n.hijos.length > 0;
    const abierto = !cerradas.has(m.id);
    const activa = m.id === activaId;
    return (
      <li key={m.id} role="treeitem" aria-label={m.nombre} aria-expanded={conHijos ? abierto : undefined} aria-selected={activa}>
        <div className={['arbol__fila arbol__fila--medicion', activa && 'is-foco'].filter(Boolean).join(' ')}>
          {conHijos ? (
            <button
              type="button"
              className="arbol__giro"
              aria-label={`${abierto ? 'Contraer' : 'Expandir'} ${m.nombre}`}
              onClick={() => alternar(m.id)}
            >
              <ChevronRight size={13} className={abierto ? 'is-abierto' : undefined} aria-hidden />
            </button>
          ) : (
            <span className="arbol__giro" aria-hidden />
          )}
          {renombrando?.id === m.id ? (
            <form className="row" style={{ flex: 1, gap: 4 }} onSubmit={(e) => void alRenombrar(e)}>
              <input
                className="input"
                aria-label={`Nuevo nombre de ${m.nombre}`}
                value={renombrando.nombre}
                autoFocus
                onChange={(e) => setRenombrando({ id: m.id, nombre: e.target.value })}
              />
              <button type="submit" className="btn btn--sm btn--accent">
                Guardar
              </button>
              <button type="button" className="btn btn--sm btn--ghost" onClick={() => setRenombrando(null)}>
                Cancelar
              </button>
            </form>
          ) : (
            <>
              <i className="arbol__color-medicion" data-testid="color-de-medicion" style={{ background: colores.get(m.id) }} aria-hidden />
            <button
              type="button"
              className="arbol__texto arbol__activar"
              title={activa ? 'Es la medición activa: lo que dibujes entra aquí. Clic para soltarla.' : 'Hacer activa: lo que dibujes entra a esta medición'}
              aria-pressed={activa}
              onClick={() => onActivar(activa ? null : m)}
            >
              {m.nombre}
            </button>
            </>
          )}
          <span className="badge badge--outline" data-testid="tipo-de-medicion">
            {NOMBRE_DE_TIPO_DE_MEDICION[m.tipo]}
          </span>
          <span className="arbol__cuenta" title={`${m.n_trazos} ${m.n_trazos === 1 ? 'trazo' : 'trazos'}`} data-testid="valor-de-medicion">
            {fmtNum(m.valor)} {m.unidad}
          </span>
        </div>
        <div className="arbol__meta arbol__meta--medicion">
          <span className="text-mute text-xs">
            {m.n_trazos} {m.n_trazos === 1 ? 'trazo' : 'trazos'}
          </span>
          {n.sinAsignar && <span className="badge badge--warn">Sin asignar</span>}
          {m.asignaciones.map((a) => (
            <span key={a.id} className="chip chip--asignacion" title={`${a.descripcion} · ${a.medida} × ${a.factor}`}>
              {a.concepto_clave || a.descripcion}
              {a.matriz_clave ? ` › ${a.matriz_clave}` : ''} · {a.usa_peso ? 'peso' : a.medida}
              <button
                type="button"
                className="chip__quitar"
                aria-label={`Quitar la asignación de ${m.nombre} a ${a.concepto_clave || a.descripcion}`}
                onClick={() => void alQuitarAsignacion(a.id)}
              >
                <X size={11} aria-hidden />
              </button>
            </span>
          ))}
          <span className="arbol__acciones">
            <button
              type="button"
              className="btn-icono btn-icono--chico"
              aria-label={`Asignar ${m.nombre} a un concepto`}
              title="Asignar a un concepto"
              onClick={() => setAsignando(asignando === m.id ? null : m.id)}
            >
              <Link2 size={13} aria-hidden />
            </button>
            <button
              type="button"
              className="btn-icono btn-icono--chico"
              aria-label={`Agregar una submedición a ${m.nombre}`}
              title="Agregar una submedición (del mismo tipo)"
              onClick={() => setCreando({ parentId: m.id, tipo: m.tipo, unidad: m.tipo === 'area' ? 'm²' : m.tipo === 'lineal' ? 'ml' : 'pza' })}
            >
              <Plus size={13} aria-hidden />
            </button>
            <button
              type="button"
              className="btn-icono btn-icono--chico"
              aria-label={`Renombrar ${m.nombre}`}
              title="Renombrar"
              onClick={() => setRenombrando({ id: m.id, nombre: m.nombre })}
            >
              <Pencil size={13} aria-hidden />
            </button>
            <button
              type="button"
              className="btn-icono btn-icono--chico btn-icono--peligro"
              aria-label={`Borrar ${m.nombre}`}
              title="Borrar (sin asignaciones ni submediciones)"
              onClick={() => (m.asignaciones.length > 0 ? setPorBorrar(m.id) : void alEliminar(m))}
            >
              <Trash2 size={13} aria-hidden />
            </button>
          </span>
        </div>
        <div className="arbol__meta arbol__meta--medicion">
          <label className="text-xs text-mute" htmlFor={`el-${m.id}`}>
            Elemento
          </label>
          <select
            id={`el-${m.id}`}
            className="select select--chico"
            aria-label={`Elemento de ${m.nombre}`}
            value={m.elemento?.id ?? ''}
            onChange={(e) => void alCambiarElemento(m, e.target.value)}
          >
            <option value="">Sin elemento</option>
            {elementos
              .filter((e) => e.tipo === m.tipo)
              .map((e) => (
                <option key={e.id} value={e.id}>
                  {e.nombre} · {Number(e.peso_kg)} {UNIDAD_DEL_PESO[e.tipo]}
                </option>
              ))}
          </select>
        </div>
        {porBorrar === m.id && (
          <div className="mediciones__confirmar" role="alert">
            <span>
              «{m.nombre}» alimenta {m.asignaciones.length} {m.asignaciones.length === 1 ? 'concepto' : 'conceptos'}: al
              borrarla se quitan esas asignaciones y los conceptos se recalculan. Sus trazos quedan sueltos.
            </span>
            <span className="row" style={{ gap: 4 }}>
              <button type="button" className="btn btn--sm btn--danger" onClick={() => void alEliminar(m)}>
                Borrar con sus asignaciones
              </button>
              <button type="button" className="btn btn--sm btn--ghost" onClick={() => setPorBorrar(null)}>
                Cancelar
              </button>
            </span>
          </div>
        )}
        {asignando === m.id && (
          <FormularioDeAsignacion
            medicion={m}
            actividades={actividades}
            conceptoEnFoco={conceptoEnFoco}
            onCerrar={() => setAsignando(null)}
            onListo={(aviso) => {
              setAsignando(null);
              onCambio(aviso);
            }}
            onError={onError}
          />
        )}
        {conHijos && abierto && (
          <ul role="group" className="arbol__hijos">
            {n.hijos.map(fila)}
          </ul>
        )}
      </li>
    );
  };

  return (
    <div className="mediciones" role="region" aria-label="Mediciones del plano">
      <div className="mediciones__cabeza">
        <span className="text-xs text-mute">
          Se crea sobre el concepto o la matriz que elegiste: nombre, unidad y a trazar.
        </span>
        <button
          type="button"
          className="btn btn--sm btn--accent"
          onClick={() => {
            if (!destino) {
              onError('Elige primero un concepto o una matriz en el Presupuesto: la medición se crea sobre esa selección.');
              onPedirDestino?.();
              return;
            }
            const unidad = unidadDeMedicionPorDefecto(destino.unidad);
            setCreando({ parentId: null, tipo: UNIDADES_DE_MEDICION.find((u) => u.valor === unidad)?.tipo ?? 'area', unidad });
          }}
        >
          <Plus size={13} aria-hidden /> Nueva medición
        </button>
      </div>

      <PanelDeElementos elementos={elementos} puedePonerPeso={puedePonerPeso} onCambio={onCambio} onError={onError} />

      {creando && (
        <form className="mediciones__nueva" onSubmit={(e) => void alCrear(e)} aria-label="Nueva medición">
          {destino && (
            <div className="text-xs" data-testid="medicion-sobre">
              Sobre <strong>{destino.nombre}</strong>
            </div>
          )}
          <input
            className="input"
            aria-label="Nombre de la medición"
            placeholder="RECÁMARA 01, Cocina, Muros eje A…"
            value={nombreNuevo}
            autoFocus
            onChange={(e) => setNombreNuevo(e.target.value)}
          />
          <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
            <select
              className="select"
              aria-label="Unidad de la medición"
              value={creando.unidad}
              disabled={creando.parentId !== null}
              onChange={(e) =>
                setCreando({
                  parentId: null,
                  unidad: e.target.value,
                  tipo: UNIDADES_DE_MEDICION.find((u) => u.valor === e.target.value)?.tipo ?? 'area',
                })
              }
            >
              {UNIDADES_DE_MEDICION.map((u) => (
                <option key={u.valor} value={u.valor}>
                  {u.nombre}
                </option>
              ))}
            </select>
            <select
              className="select"
              aria-label="Dentro de"
              value={creando.parentId ?? ''}
              onChange={(e) => {
                const madre = mediciones.find((m) => m.id === e.target.value);
                setCreando({
                  ...creando,
                  parentId: madre ? madre.id : null,
                  ...(madre ? { tipo: madre.tipo, unidad: madre.tipo === 'area' ? 'm²' : madre.tipo === 'lineal' ? 'ml' : 'pza' } : {}),
                });
              }}
            >
              <option value="">Sola (en el nivel de arriba)</option>
              {candidatasAMadre(mediciones, creando.tipo).map((m) => (
                <option key={m.id} value={m.id}>
                  Dentro de {m.nombre}
                </option>
              ))}
            </select>
          </div>
          <div className="row" style={{ gap: 4 }}>
            <button type="submit" className="btn btn--sm btn--accent" disabled={nombreNuevo.trim() === '' || crear.isPending}>
              Crear medición
            </button>
            <button
              type="button"
              className="btn btn--sm btn--ghost"
              onClick={() => {
                setCreando(null);
                setNombreNuevo('');
              }}
            >
              Cancelar
            </button>
          </div>
        </form>
      )}

      {cargando ? (
        <div className="text-mute text-xs" style={{ padding: 8 }}>
          Cargando mediciones…
        </div>
      ) : arbol.length === 0 ? (
        <div className="text-mute text-sm" style={{ padding: 10 }}>
          Este plano aún no tiene mediciones. Crea una (por ejemplo «Losa de cimentación»), actívala y dibuja:
          lo que trazas entra a ella.
        </div>
      ) : (
        <ul role="tree" className="arbol__lista" aria-label="Árbol de mediciones">
          {arbol.map(fila)}
        </ul>
      )}
    </div>
  );
}

function FormularioDeAsignacion({
  medicion,
  actividades,
  conceptoEnFoco,
  onCerrar,
  onListo,
  onError,
}: {
  readonly medicion: MedicionRespuesta;
  readonly actividades: readonly ActividadRespuesta[];
  readonly conceptoEnFoco?: string;
  readonly onCerrar: () => void;
  readonly onListo: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}) {
  const medidas = MEDIDAS_ASIGNABLES[medicion.tipo];
  const [actividadId, setActividadId] = useState(conceptoEnFoco ?? '');
  const [matrizId, setMatrizId] = useState('');
  const [medida, setMedida] = useState<string>(medidas[0]?.medida ?? 'area');
  const [factor, setFactor] = useState('1');
  const [usarPeso, setUsarPeso] = useState(true);
  const unidadDelConcepto = (actividades.find((a) => a.id === actividadId)?.unidad ?? '').trim().toLowerCase();
  // El peso del elemento solo alimenta conceptos en kg o ton, con la medida cuya unidad es la de su peso.
  const puedeUsarPeso = medicion.elemento != null && (unidadDelConcepto === 'kg' || unidadDelConcepto === 'ton');
  const conPeso = puedeUsarPeso && usarPeso;
  const medidaBase = medicion.tipo === 'conteo' ? 'conteo' : medicion.tipo === 'lineal' ? 'longitud' : 'area';
  const asignar = useAsignarMedicionApiV1MedicionesMedicionIdAsignacionesPost<ErrorApi>();

  async function alEnviar(e: FormEvent) {
    e.preventDefault();
    if (actividadId === '') return;
    try {
      const r = await asignar.mutateAsync({
        medicionId: medicion.id,
        data: {
          actividad_id: actividadId,
          matriz_concepto_id: matrizId === '' ? null : matrizId,
          medida: (conPeso ? medidaBase : medida) as 'area' | 'perimetro' | 'longitud' | 'conteo',
          factor: conPeso ? '1' : factor,
          usar_peso: conPeso,
        },
      });
      onListo(
        `«${medicion.nombre}» alimenta al concepto: ${r.trazos_enlazados} ${r.trazos_enlazados === 1 ? 'trazo enlazado' : 'trazos enlazados'}.`,
      );
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo asignar la medición.');
    }
  }

  return (
    <form className="mediciones__asignar" onSubmit={(e) => void alEnviar(e)} aria-label={`Asignar ${medicion.nombre}`}>
      <label className="field__label" htmlFor={`as-act-${medicion.id}`}>
        Concepto
      </label>
      <select
        id={`as-act-${medicion.id}`}
        className="select"
        value={actividadId}
        onChange={(e) => {
          setActividadId(e.target.value);
          setMatrizId('');
        }}
      >
        <option value="">Elige un concepto…</option>
        {actividades.map((a) => (
          <option key={a.id} value={a.id}>
            {etiquetaActividad(a)}
          </option>
        ))}
      </select>
      {actividadId !== '' && (
        <select className="select" aria-label="Matriz interna" value={matrizId} onChange={(e) => setMatrizId(e.target.value)}>
          <option value="">El concepto entero</option>
          <OpcionesDeMatriz actividadId={actividadId} />
        </select>
      )}
      {puedeUsarPeso && medicion.elemento && (
        <label className="row text-sm" style={{ gap: 6 }}>
          <input type="checkbox" checked={usarPeso} onChange={(e) => setUsarPeso(e.target.checked)} />
          Con el peso de {medicion.elemento.nombre} ({Number(medicion.elemento.peso_kg)} {UNIDAD_DEL_PESO[medicion.tipo]})
        </label>
      )}
      <div className="row" style={{ gap: 4 }}>
        <select className="select" aria-label="Medida" value={conPeso ? medidaBase : medida} disabled={conPeso} onChange={(e) => setMedida(e.target.value)}>
          {medidas.map((m) => (
            <option key={m.medida} value={m.medida}>
              {m.etiqueta}
            </option>
          ))}
        </select>
        <input
          className="input"
          aria-label="Factor"
          inputMode="decimal"
          value={factor}
          style={{ width: 70 }}
          disabled={conPeso}
          onChange={(e) => setFactor(e.target.value)}
        />
      </div>
      <div className="row" style={{ gap: 4 }}>
        <button type="submit" className="btn btn--sm btn--accent" disabled={actividadId === '' || asignar.isPending}>
          Asignar
        </button>
        <button type="button" className="btn btn--sm btn--ghost" onClick={onCerrar}>
          Cancelar
        </button>
      </div>
    </form>
  );
}
