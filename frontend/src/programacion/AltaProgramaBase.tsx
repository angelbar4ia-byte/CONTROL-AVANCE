/**
 * Alta de un programa base de duraciones (§11.2 `POST /programas-base`, §7.5).
 *
 * Cada alta **versiona**: crea la versión siguiente del prototipo y retira la
 * vigente anterior (§7.5, §10.8). El backend valida el cronograma completo y
 * responde 422 sin escribir nada si hay dependencias circulares.
 *
 * ## Limitación pagada
 *
 * Hasta la fase del editor gráfico, `prototipo_nodo_id`, `etapa_id` y las
 * `ref` de las dependencias —que en un programa base son el
 * `prototipo_nodo_id` de la predecesora— se **tecleaban como UUID**, porque el
 * contrato no exponía el árbol de `PrototipoNodo` (§7.4). `GET
 * /prototipos/{id}/nodos` ya existe: los tres campos son ahora selects sobre
 * el árbol real, cargado en cuanto se elige el prototipo.
 *
 * Este formulario se queda para el alta de pocos renglones y para capturar sin
 * ratón; el camino normal —armar el programa completo, con precedencias— es el
 * canvas (`EditorPrograma`), al que se llega desde la misma pantalla.
 */

import { useMemo, useState, type FormEvent } from 'react';

import { useCrearProgramaBaseApiV1ProgramasBasePost } from '@/api/generado/programacion/programacion';
import { useListarNodosDePrototipoApiV1PrototiposPrototipoIdNodosGet } from '@/api/generado/proyectos/proyectos';
import type {
  FrenteRespuesta,
  ItemProgramaBasePeticion,
  NodoPrototipoRespuesta,
  ProgramaBaseCreadoRespuesta,
  PrototipoRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import { EditorDependencias } from './Dependencias';
import { dependenciasDelFormulario, type FormularioDependencia } from './formulario';
import { opcionesDeEtapas, opcionesDeNodos } from './grafo';

interface ItemFormulario {
  readonly duracionDias: string;
  readonly frenteId: string;
  readonly etapaId: string;
  readonly prototipoNodoId: string;
  readonly dependencias: readonly FormularioDependencia[];
}

const ITEM_VACIO: ItemFormulario = {
  duracionDias: '',
  frenteId: '',
  etapaId: '',
  prototipoNodoId: '',
  dependencias: [],
};

interface Props {
  readonly prototipos: readonly PrototipoRespuesta[];
  readonly frentes: readonly FrenteRespuesta[];
  readonly prototipoInicial?: string;
  readonly onCerrar: () => void;
  readonly onCreado: (respuesta: ProgramaBaseCreadoRespuesta) => void;
}

export function AltaProgramaBase({
  prototipos,
  frentes,
  prototipoInicial,
  onCerrar,
  onCreado,
}: Props) {
  const [prototipoId, setPrototipoId] = useState(prototipoInicial ?? '');
  const [nombre, setNombre] = useState('');
  const [items, setItems] = useState<readonly ItemFormulario[]>([ITEM_VACIO]);
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  // El árbol WBS del prototipo elegido: es lo que convierte los tres campos de
  // UUID en selects. Sin prototipo no hay árbol que pedir.
  const nodosQ = useListarNodosDePrototipoApiV1PrototiposPrototipoIdNodosGet<
    NodoPrototipoRespuesta[],
    ErrorApi
  >(prototipoId, { query: { enabled: prototipoId !== '' } });

  const nodos = useMemo(() => nodosQ.data ?? [], [nodosQ.data]);
  const opcionesNodo = useMemo(() => opcionesDeNodos(nodos), [nodos]);
  const opcionesEtapa = useMemo(() => opcionesDeEtapas(nodos), [nodos]);

  // Las predecesoras elegibles son los nodos que este mismo formulario ya
  // asignó a un renglón: una `ref` a un nodo sin renglón no la puede resolver
  // el motor al instanciar (§6, `refs_no_resueltas`).
  const opcionesRef = useMemo(() => {
    const asignados = new Set(
      items.map((item) => item.prototipoNodoId).filter((id) => id !== ''),
    );
    return opcionesNodo
      .filter((opcion) => asignados.has(opcion.valor))
      .map((opcion) => ({ valor: opcion.valor, etiqueta: opcion.etiqueta.trim() }));
  }, [items, opcionesNodo]);

  const crear = useCrearProgramaBaseApiV1ProgramasBasePost<ErrorApi>({
    mutation: {
      onSuccess: (respuesta) => {
        setError(null);
        onCreado(respuesta);
      },
      onError: (err) => setError({ mensaje: err.message, campo: err.campo }),
    },
  });

  function actualizarItem(indice: number, parcial: Partial<ItemFormulario>) {
    setItems((previos) =>
      previos.map((item, i) => (i === indice ? { ...item, ...parcial } : item)),
    );
  }

  // Renglones sin duración no se mandan: `duracion_dias` es obligatorio en el
  // contrato y un renglón a medio llenar tumbaría el alta completa.
  const itemsListos = items.filter((item) => item.duracionDias.trim() !== '');
  const puedeEnviar = prototipoId !== '' && itemsListos.length > 0 && !crear.isPending;

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!puedeEnviar) return;

    const cuerpo: ItemProgramaBasePeticion[] = itemsListos.map((item, indice) => ({
      duracion_dias: Number(item.duracionDias),
      frente_id: item.frenteId === '' ? null : item.frenteId,
      etapa_id: item.etapaId === '' ? null : item.etapaId,
      prototipo_nodo_id: item.prototipoNodoId === '' ? null : item.prototipoNodoId,
      dependencias: [...dependenciasDelFormulario(item.dependencias)],
      orden: indice,
    }));

    crear.mutate({
      data: {
        prototipo_id: prototipoId,
        nombre: nombre.trim() === '' ? null : nombre.trim(),
        items: cuerpo,
      },
    });
  }

  return (
    <Sheet
      titulo="Nuevo programa base"
      subtitulo="Cada alta crea una versión nueva (§7.5)"
      onCerrar={onCerrar}
    >
      <form onSubmit={alEnviar} className="sheet__body col gap-16">
        <div className="field">
          <label className="field__label" htmlFor="base-prototipo">
            Prototipo *
          </label>
          <select
            id="base-prototipo"
            className="select"
            value={prototipoId}
            onChange={(e) => {
              // Los nodos elegidos son de otro árbol: dejarlos apuntaría a
              // nodos de un prototipo distinto y el POST fallaría en el borde.
              setPrototipoId(e.target.value);
              setItems((previos) =>
                previos.map((item) => ({
                  ...item,
                  prototipoNodoId: '',
                  etapaId: '',
                  dependencias: [],
                })),
              );
            }}
            required
          >
            <option value="">Elegir prototipo…</option>
            {prototipos.map((prototipo) => (
              <option key={prototipo.id} value={prototipo.id}>
                {prototipo.clave} · {prototipo.nombre}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="base-nombre">
            Nombre (opcional)
          </label>
          <input
            id="base-nombre"
            className="input"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="Programa 2026 · vivienda tipo A"
          />
        </div>

        {items.map((item, indice) => (
          <div className="card" key={`item-${indice}`}>
            <div className="card__header">
              <div>
                <h3 className="card__title">Renglón {indice + 1}</h3>
                <div className="card__sub">
                  Duración de la actividad y a qué nodo del prototipo aplica (§7.5).
                </div>
              </div>
              {items.length > 1 && (
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  aria-label={`Quitar renglón ${indice + 1}`}
                  onClick={() => setItems((previos) => previos.filter((_, i) => i !== indice))}
                >
                  Quitar
                </button>
              )}
            </div>
            <div className="card__body col gap-12">
              <div className="row gap-12" style={{ flexWrap: 'wrap' }}>
                <div className="field" style={{ flex: 1, minWidth: 120 }}>
                  <label className="field__label" htmlFor={`item-duracion-${indice}`}>
                    Duración (días) *
                  </label>
                  <input
                    id={`item-duracion-${indice}`}
                    className="input input--mono"
                    type="number"
                    step="any"
                    min="0"
                    value={item.duracionDias}
                    onChange={(e) => actualizarItem(indice, { duracionDias: e.target.value })}
                  />
                </div>
                <div className="field" style={{ flex: 2, minWidth: 180 }}>
                  <label className="field__label" htmlFor={`item-frente-${indice}`}>
                    Frente
                  </label>
                  <select
                    id={`item-frente-${indice}`}
                    className="select"
                    value={item.frenteId}
                    onChange={(e) => actualizarItem(indice, { frenteId: e.target.value })}
                  >
                    <option value="">Sin frente</option>
                    {frentes.map((frente) => (
                      <option key={frente.id} value={frente.id}>
                        {frente.clave} · {frente.nombre}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="row gap-12" style={{ flexWrap: 'wrap' }}>
                <div className="field" style={{ flex: 1, minWidth: 200 }}>
                  <label className="field__label" htmlFor={`item-nodo-${indice}`}>
                    Nodo del prototipo
                  </label>
                  <select
                    id={`item-nodo-${indice}`}
                    className="select"
                    value={item.prototipoNodoId}
                    disabled={prototipoId === ''}
                    onChange={(e) => actualizarItem(indice, { prototipoNodoId: e.target.value })}
                  >
                    <option value="">Sin nodo (plantilla gruesa por etapa)</option>
                    {opcionesNodo.map((opcion) => (
                      <option key={opcion.valor} value={opcion.valor}>
                        {opcion.etiqueta}
                      </option>
                    ))}
                  </select>
                  <div className="field__hint">
                    {prototipoId === ''
                      ? 'Elige primero el prototipo para cargar su árbol WBS (§7.4).'
                      : nodosQ.isLoading
                        ? 'Cargando el árbol…'
                        : 'Etapa o concepto exacto del árbol WBS (§7.4).'}
                  </div>
                </div>
                <div className="field" style={{ flex: 1, minWidth: 200 }}>
                  <label className="field__label" htmlFor={`item-etapa-${indice}`}>
                    Etapa constructiva
                  </label>
                  <select
                    id={`item-etapa-${indice}`}
                    className="select"
                    value={item.etapaId}
                    disabled={prototipoId === ''}
                    onChange={(e) => actualizarItem(indice, { etapaId: e.target.value })}
                  >
                    <option value="">Sin etapa</option>
                    {opcionesEtapa.map((opcion) => (
                      <option key={opcion.valor} value={opcion.valor}>
                        {opcion.etiqueta}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <EditorDependencias
                idBase={`item-${indice}`}
                dependencias={item.dependencias}
                onCambio={(dependencias) => actualizarItem(indice, { dependencias })}
                opciones={opcionesRef}
                vacio="Sin predecesoras: el renglón arranca al inicio del programa."
                pistaRef="Solo aparecen los nodos que ya tienen renglón en este formulario: una ref a un nodo sin renglón el motor no la puede resolver (§6)."
              />
            </div>
          </div>
        ))}

        <div className="row">
          <button
            type="button"
            className="btn"
            onClick={() => setItems((previos) => [...previos, ITEM_VACIO])}
          >
            Agregar renglón
          </button>
        </div>

        {error && <ErrorBanner mensaje={error.mensaje} campo={error.campo} />}
        {nodosQ.error && <ErrorBanner mensaje={nodosQ.error.message} />}

        <div className="sheet__footer">
          <button type="button" className="btn btn--ghost" onClick={onCerrar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={!puedeEnviar}>
            {crear.isPending ? 'Guardando…' : `Crear versión (${itemsListos.length} renglones)`}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
