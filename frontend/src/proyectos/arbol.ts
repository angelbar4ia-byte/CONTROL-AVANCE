/**
 * Armado del árbol Proyecto → Cluster → Obra (§7.2, §11.2).
 *
 * Funciones puras de **presentación**: agrupan lo que ya devolvieron
 * `GET /proyectos`, `GET /clusters` y `GET /obras` —cada uno ya acotado por
 * RLS al alcance del rol (§4, §12.4)— para pintarlas anidadas. No calculan
 * ninguna métrica derivada: el `avance_pct` de una obra lo da el backend
 * (§6) y el spec no define un agregado por cluster o proyecto, así que aquí
 * no se inventa uno; solo se cuentan nodos.
 *
 * Vive fuera de los componentes por la regla del §12.11 (cero lógica en
 * React) y para poder fijarlo con pruebas.
 */

import type {
  ClusterRespuesta,
  ObraRespuesta,
  PrototipoRespuesta,
  ProyectoRespuesta,
} from '@/api/generado/modelo';

export interface NodoCluster {
  readonly cluster: ClusterRespuesta;
  readonly obras: readonly ObraRespuesta[];
}

export interface NodoProyecto {
  readonly proyecto: ProyectoRespuesta;
  readonly clusters: readonly NodoCluster[];
  /** Obras del proyecto, sumando todos sus clusters. */
  readonly nObras: number;
}

export interface Arbol {
  readonly proyectos: readonly NodoProyecto[];
  /**
   * Obras cuyo cluster no vino en la respuesta de `GET /clusters` — pasa
   * cuando los clusters se pidieron acotados a un proyecto y las obras no.
   * Se muestran aparte en vez de desaparecer sin explicación.
   */
  readonly sinCluster: readonly ObraRespuesta[];
}

export interface OpcionesArbol {
  /** Oculta proyectos y clusters que se quedaron sin obras (al filtrar). */
  readonly ocultarVacios?: boolean;
}

export function construirArbol(
  proyectos: readonly ProyectoRespuesta[],
  clusters: readonly ClusterRespuesta[],
  obras: readonly ObraRespuesta[],
  opciones: OpcionesArbol = {},
): Arbol {
  const obrasPorCluster = new Map<string, ObraRespuesta[]>();
  for (const obra of obras) {
    const lista = obrasPorCluster.get(obra.cluster_id);
    if (lista) lista.push(obra);
    else obrasPorCluster.set(obra.cluster_id, [obra]);
  }

  const clustersPorProyecto = new Map<string, ClusterRespuesta[]>();
  for (const cluster of clusters) {
    const lista = clustersPorProyecto.get(cluster.proyecto_id);
    if (lista) lista.push(cluster);
    else clustersPorProyecto.set(cluster.proyecto_id, [cluster]);
  }

  const nodos: NodoProyecto[] = [];
  for (const proyecto of proyectos) {
    const nodosCluster: NodoCluster[] = [];
    let nObras = 0;

    for (const cluster of clustersPorProyecto.get(proyecto.id) ?? []) {
      const obrasDelCluster = obrasPorCluster.get(cluster.id) ?? [];
      nObras += obrasDelCluster.length;
      if (opciones.ocultarVacios === true && obrasDelCluster.length === 0) continue;
      nodosCluster.push({ cluster, obras: obrasDelCluster });
    }

    if (opciones.ocultarVacios === true && nObras === 0) continue;
    nodos.push({ proyecto, clusters: nodosCluster, nObras });
  }

  const conocidos = new Set(clusters.map((cluster) => cluster.id));
  const sinCluster = obras.filter((obra) => !conocidos.has(obra.cluster_id));

  return { proyectos: nodos, sinCluster };
}

/**
 * Filtro por texto sobre la clave de la obra (§10.1: la clave es
 * `CLUSTER + LOTE`, p. ej. `FRESNO 12`). Es un filtro de UI sobre lo que el
 * servidor ya devolvió, no un recorte de alcance.
 */
export function filtrarObrasPorTexto(
  obras: readonly ObraRespuesta[],
  texto: string,
): readonly ObraRespuesta[] {
  const aguja = texto.trim().toLowerCase();
  if (aguja === '') return obras;
  return obras.filter((obra) => obra.clave.toLowerCase().includes(aguja));
}

/** Proyecto al que pertenece un cluster, para etiquetar selects encadenados. */
export function proyectoDeCluster(
  clusters: readonly ClusterRespuesta[],
  clusterId: string,
): string | null {
  return clusters.find((cluster) => cluster.id === clusterId)?.proyecto_id ?? null;
}

/**
 * Prototipos del proyecto indicado (§7.2: el prototipo cuelga del proyecto).
 * Con `proyectoId` en `null` no se puede acotar todavía, y devolver todos
 * dejaría elegir un prototipo de otro proyecto: mejor lista vacía.
 */
export function prototiposDeProyecto(
  prototipos: readonly PrototipoRespuesta[],
  proyectoId: string | null,
): readonly PrototipoRespuesta[] {
  if (proyectoId === null) return [];
  return prototipos.filter((prototipo) => prototipo.proyecto_id === proyectoId);
}
