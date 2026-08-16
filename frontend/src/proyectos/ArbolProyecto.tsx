/**
 * Árbol Proyecto → Cluster → Obra (§7.2), con los estilos `.tree*` del
 * sistema de diseño.
 *
 * Presentación pura: recibe el árbol ya armado (`arbol.ts`) y avisa qué obra
 * se seleccionó. Lo único que guarda es qué nodos están desplegados.
 *
 * Cada nodo agrupador es un `button` con `aria-expanded`/`aria-controls`
 * (patrón de disclosure), así que el árbol se recorre completo con teclado.
 */

import { useState, type ReactNode } from 'react';
import { ChevronDown, ChevronRight, FolderTree, Home, Layers, Plus } from 'lucide-react';

import type { ObraRespuesta } from '@/api/generado/modelo';
import { fmtPct } from '@/lib/formato';
import type { Arbol } from './arbol';
import { etiquetaEstatusObra, tonoEstatusObra } from './reglas';

interface Props {
  readonly arbol: Arbol;
  readonly obraSeleccionada: string | null;
  readonly onSeleccionarObra: (obra: ObraRespuesta) => void;
  /** Solo se pasan cuando el rol puede darlos de alta (§11.2). */
  readonly onNuevoCluster?: (proyectoId: string) => void;
  readonly onNuevaObra?: (clusterId: string) => void;
  /** Con un filtro activo conviene mostrar todo desplegado. */
  readonly expandirTodo?: boolean;
}

export function ArbolProyecto({
  arbol,
  obraSeleccionada,
  onSeleccionarObra,
  onNuevoCluster,
  onNuevaObra,
  expandirTodo = false,
}: Props) {
  // Los proyectos arrancan desplegados: son el primer nivel y sin ellos el
  // árbol se ve vacío. Los clusters se abren a demanda.
  const [abiertos, setAbiertos] = useState<ReadonlySet<string>>(
    () => new Set(arbol.proyectos.map((nodo) => nodo.proyecto.id)),
  );

  function alternar(id: string) {
    setAbiertos((previos) => {
      const siguiente = new Set(previos);
      if (siguiente.has(id)) siguiente.delete(id);
      else siguiente.add(id);
      return siguiente;
    });
  }

  const estaAbierto = (id: string) => expandirTodo || abiertos.has(id);

  if (arbol.proyectos.length === 0 && arbol.sinCluster.length === 0) {
    return (
      <div className="text-mute text-sm" style={{ padding: '24px 12px' }}>
        No hay proyectos en tu alcance con estos filtros.
      </div>
    );
  }

  return (
    <div className="tree" style={{ padding: 12 }}>
      {arbol.proyectos.map((nodoProyecto) => {
        const { proyecto } = nodoProyecto;
        return (
          <Agrupador
            key={proyecto.id}
            id={`proyecto-${proyecto.id}`}
            abierto={estaAbierto(proyecto.id)}
            onAlternar={() => alternar(proyecto.id)}
            icono={<FolderTree className="tree__icon" size={16} strokeWidth={1.6} aria-hidden />}
            nombre={
              <>
                <span className="mono">{proyecto.clave}</span> {proyecto.nombre}
              </>
            }
            meta={`${nodoProyecto.clusters.length} cl · ${nodoProyecto.nObras} obras`}
            accion={
              onNuevoCluster && {
                etiqueta: 'Cluster',
                titulo: 'Nuevo cluster en este proyecto',
                onClick: () => onNuevoCluster(proyecto.id),
              }
            }
          >
            {nodoProyecto.clusters.length === 0 ? (
              <Vacio>Sin clusters.</Vacio>
            ) : (
              nodoProyecto.clusters.map((nodoCluster) => {
                const { cluster } = nodoCluster;
                return (
                  <Agrupador
                    key={cluster.id}
                    id={`cluster-${cluster.id}`}
                    abierto={estaAbierto(cluster.id)}
                    onAlternar={() => alternar(cluster.id)}
                    icono={<Layers className="tree__icon" size={16} strokeWidth={1.6} aria-hidden />}
                    nombre={
                      <>
                        <span className="mono">{cluster.clave}</span> {cluster.nombre}
                      </>
                    }
                    meta={`${nodoCluster.obras.length} obras`}
                    accion={
                      onNuevaObra && {
                        etiqueta: 'Obra',
                        titulo: 'Nueva obra en este cluster',
                        onClick: () => onNuevaObra(cluster.id),
                      }
                    }
                  >
                    {nodoCluster.obras.length === 0 ? (
                      <Vacio>Sin obras.</Vacio>
                    ) : (
                      nodoCluster.obras.map((obra) => (
                        <NodoObra
                          key={obra.id}
                          obra={obra}
                          seleccionada={obra.id === obraSeleccionada}
                          onSeleccionar={onSeleccionarObra}
                        />
                      ))
                    )}
                  </Agrupador>
                );
              })
            )}
          </Agrupador>
        );
      })}

      {arbol.sinCluster.length > 0 && (
        <>
          <div className="tree__node" style={{ cursor: 'default' }}>
            <span className="tree__caret" aria-hidden />
            <Layers className="tree__icon" size={16} strokeWidth={1.6} aria-hidden />
            <span className="tree__name text-mute">Obras cuyo cluster no está en la lista</span>
            <span className="tree__meta tnum">{arbol.sinCluster.length}</span>
          </div>
          <div className="tree__children">
            {arbol.sinCluster.map((obra) => (
              <NodoObra
                key={obra.id}
                obra={obra}
                seleccionada={obra.id === obraSeleccionada}
                onSeleccionar={onSeleccionarObra}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

interface AccionNodo {
  readonly etiqueta: string;
  readonly titulo: string;
  readonly onClick: () => void;
}

/** Nodo desplegable (proyecto o cluster) con su acción de alta opcional. */
function Agrupador({
  id,
  abierto,
  onAlternar,
  icono,
  nombre,
  meta,
  accion,
  children,
}: {
  readonly id: string;
  readonly abierto: boolean;
  readonly onAlternar: () => void;
  readonly icono: ReactNode;
  readonly nombre: ReactNode;
  readonly meta: string;
  readonly accion?: AccionNodo | undefined;
  readonly children: ReactNode;
}) {
  return (
    <div>
      <div className="tree__node tree__node--hover" style={{ padding: 0 }}>
        <button
          type="button"
          className="tree__node"
          style={{ flex: 1, minWidth: 0 }}
          aria-expanded={abierto}
          aria-controls={id}
          onClick={onAlternar}
        >
          <span className="tree__caret" aria-hidden>
            {abierto ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
          {icono}
          <span className="tree__name">{nombre}</span>
          <span className="tree__meta tnum">{meta}</span>
        </button>
        {accion && (
          <span className="tree__hover-actions">
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              title={accion.titulo}
              onClick={accion.onClick}
            >
              <Plus size={14} strokeWidth={1.6} aria-hidden />
              {accion.etiqueta}
            </button>
          </span>
        )}
      </div>
      {abierto && (
        <div className="tree__children" id={id}>
          {children}
        </div>
      )}
    </div>
  );
}

function Vacio({ children }: { readonly children: ReactNode }) {
  return (
    <div className="text-mute text-xs" style={{ padding: '6px 8px' }}>
      {children}
    </div>
  );
}

function NodoObra({
  obra,
  seleccionada,
  onSeleccionar,
}: {
  readonly obra: ObraRespuesta;
  readonly seleccionada: boolean;
  readonly onSeleccionar: (obra: ObraRespuesta) => void;
}) {
  return (
    <button
      type="button"
      className="tree__node w-full"
      aria-haspopup="dialog"
      aria-current={seleccionada ? 'true' : undefined}
      style={seleccionada ? { background: 'var(--c-elev)' } : undefined}
      onClick={() => onSeleccionar(obra)}
    >
      <span className="tree__caret" aria-hidden />
      <Home className="tree__icon" size={16} strokeWidth={1.6} aria-hidden />
      <span className="tree__name mono">{obra.clave}</span>
      <span className={`badge badge--${tonoEstatusObra(obra.estatus)}`}>
        {etiquetaEstatusObra(obra.estatus)}
      </span>
      <span className="tree__meta tnum">{fmtPct(obra.avance_pct)}</span>
    </button>
  );
}
