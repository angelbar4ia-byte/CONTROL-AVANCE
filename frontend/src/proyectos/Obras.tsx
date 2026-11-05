/**
 * Proyecto · Cluster · Obra — pantalla del árbol y del creador de obra
 * (§4, §5.1, §5.3, §11.2 bloque "Proyecto · Obra", §11.3 A).
 *
 * Pantalla **compartida** (§5.3): se implementa una vez y cambia por rol y
 * alcance. El alcance no se filtra aquí — lo impone RLS en el servidor
 * (§12.4); esta pantalla solo refleja lo que la API devolvió.
 *
 *   - **Control de obra** (`/config/creador-obra`, §5.1) — árbol completo,
 *     alta de proyecto/cluster/prototipo/obra, alta masiva y generación
 *     desde prototipo.
 *   - **Super intendente** (`/avance-proyecto`) — árbol completo y alta de
 *     proyecto/cluster/prototipo; las obras son del creador de obra (§11.2).
 *   - **Residente** (`/obras`, "Mis obras") y **Supervisor** (`/obras`,
 *     "Obras supervisadas") — lista plana: el contrato no les expone
 *     `GET /proyectos` ni `GET /clusters` (ver `TablaObras`).
 *
 * ## Ruta de datos (§10.7)
 *
 * Todo va por los hooks de Orval contra la API, igual que `avance`,
 * `cierres` y `estimacion`. Aunque `proyecto`, `cluster` y `prototipo`
 * aparecen en la lista blanca de `lib/supabase.ts`, aquí no se usa la ruta
 * directa: estos endpoints ya existen en el contrato y son la ruta de
 * dominio (altas con caso de uso, Workflow A). Ninguna otra feature usa hoy
 * la ruta directa; abrir una segunda para lo mismo partiría el alcance en
 * dos fronteras distintas.
 */

import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  useListarClustersApiV1ClustersGet,
  useListarPrototiposApiV1PrototiposGet,
  useListarProyectosApiV1ProyectosGet,
} from '@/api/generado/proyectos/proyectos';
import { useListarObrasApiV1ObrasGet } from '@/api/generado/obras/obras';
import { EstatusObra } from '@/api/generado/modelo';
import type {
  ClusterRespuesta,
  ObraRespuesta,
  PrototipoRespuesta,
  ProyectoRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import type { Rol } from '@/shell/navegacion';
import { construirArbol, filtrarObrasPorTexto } from './arbol';
import { ArbolProyecto } from './ArbolProyecto';
import { TablaObras } from './TablaObras';
import { PanelObra } from './PanelObra';
import { AltaProyecto } from './AltaProyecto';
import { AltaCluster } from './AltaCluster';
import { AltaPrototipo } from './AltaPrototipo';
import { CreadorDeObra } from './CreadorDeObra';
import { AltaMasivaObras } from './AltaMasivaObras';
import { etiquetaEstatusObra, puedeAdministrarObras, puedeConfigurarEstructura } from './reglas';

const ENCABEZADO: Record<Rol, { readonly eyebrow: string; readonly titulo: string }> = {
  residente: { eyebrow: 'Mi trabajo', titulo: 'Mis obras' },
  supervisor: { eyebrow: 'Control supervisión', titulo: 'Obras supervisadas' },
  control_obra: { eyebrow: 'Configuración', titulo: 'Creador de obra' },
  super_intendente: { eyebrow: 'Control general', titulo: 'Avance de proyecto' },
  costos: { eyebrow: 'Presupuesto', titulo: 'Obras' },
};

const ESTATUS: readonly EstatusObra[] = [
  EstatusObra.pendiente,
  EstatusObra.iniciada,
  EstatusObra.en_proceso,
  EstatusObra.por_entregar,
  EstatusObra.entregada,
];

type Dialogo =
  | { readonly tipo: 'proyecto' }
  | { readonly tipo: 'cluster'; readonly proyectoId?: string }
  | { readonly tipo: 'prototipo'; readonly proyectoId?: string }
  | { readonly tipo: 'obra'; readonly clusterId?: string }
  | { readonly tipo: 'lote'; readonly clusterId?: string }
  | null;

export default function Obras() {
  const { sesion } = useSesion();
  const navegar = useNavigate();
  const rol = sesion?.rol ?? null;
  const configura = rol !== null && puedeConfigurarEstructura(rol);
  const administraObras = rol !== null && puedeAdministrarObras(rol);

  const [proyectoId, setProyectoId] = useState('');
  const [estatus, setEstatus] = useState<EstatusObra | ''>('');
  const [texto, setTexto] = useState('');
  const [dialogo, setDialogo] = useState<Dialogo>(null);
  const [seleccionadaId, setSeleccionadaId] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const proyectosQ = useListarProyectosApiV1ProyectosGet<ProyectoRespuesta[], ErrorApi>({
    query: { enabled: configura },
  });

  const clustersQ = useListarClustersApiV1ClustersGet<ClusterRespuesta[], ErrorApi>(
    { proyecto_id: proyectoId === '' ? undefined : proyectoId },
    { query: { enabled: configura } },
  );

  const prototiposQ = useListarPrototiposApiV1PrototiposGet<PrototipoRespuesta[], ErrorApi>(
    {},
    { query: { enabled: configura } },
  );

  const obrasQ = useListarObrasApiV1ObrasGet<ObraRespuesta[], ErrorApi>({
    proyecto_id: proyectoId === '' ? undefined : proyectoId,
    estatus: estatus === '' ? undefined : estatus,
  });

  const proyectos = useMemo(() => proyectosQ.data ?? [], [proyectosQ.data]);
  const clusters = useMemo(() => clustersQ.data ?? [], [clustersQ.data]);
  const prototipos = useMemo(() => prototiposQ.data ?? [], [prototiposQ.data]);

  const obras = useMemo(
    () => filtrarObrasPorTexto(obrasQ.data ?? [], texto),
    [obrasQ.data, texto],
  );

  const arbol = useMemo(
    () => construirArbol(proyectos, clusters, obras, { ocultarVacios: texto.trim() !== '' }),
    [proyectos, clusters, obras, texto],
  );

  // La obra del cajón se re-deriva de la lista para que un PATCH o una
  // generación se reflejen ahí sin copiar estado.
  const obraSeleccionada = obras.find((obra) => obra.id === seleccionadaId) ?? null;

  if (!sesion || rol === null) return null;
  const encabezado = ENCABEZADO[rol];

  function refrescarObras() {
    void obrasQ.refetch();
  }

  function cerrarDialogo() {
    setDialogo(null);
  }

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">{encabezado.eyebrow}</div>
          <h1 className="page__title">{encabezado.titulo}</h1>
          <div className="page__subtitle">
            Árbol Proyecto → Cluster → Obra. El alcance lo impone RLS en el servidor
            (§4): aquí solo se muestra lo que te toca.
          </div>
        </div>

        {(configura || administraObras) && (
          <div className="page__actions">
            {configura && (
              <>
                <button
                  type="button"
                  className="btn"
                  onClick={() => setDialogo({ tipo: 'proyecto' })}
                >
                  Nuevo proyecto
                </button>
                <button
                  type="button"
                  className="btn"
                  onClick={() =>
                    setDialogo({
                      tipo: 'cluster',
                      proyectoId: proyectoId === '' ? undefined : proyectoId,
                    })
                  }
                >
                  Nuevo cluster
                </button>
                <button
                  type="button"
                  className="btn"
                  onClick={() =>
                    setDialogo({
                      tipo: 'prototipo',
                      proyectoId: proyectoId === '' ? undefined : proyectoId,
                    })
                  }
                >
                  Nuevo prototipo
                </button>
              </>
            )}
            {administraObras && (
              <>
                <button
                  type="button"
                  className="btn"
                  onClick={() => setDialogo({ tipo: 'lote' })}
                >
                  Alta masiva
                </button>
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => setDialogo({ tipo: 'obra' })}
                >
                  Nueva obra
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {aviso !== null && (
        <div className="mb-8" role="status">
          <span className="badge badge--ok">{aviso}</span>
        </div>
      )}

      {obrasQ.isError && (
        <div className="mb-8">
          <ErrorBanner mensaje={obrasQ.error.message} />
        </div>
      )}
      {configura && proyectosQ.isError && (
        <div className="mb-8">
          <ErrorBanner mensaje={proyectosQ.error.message} />
        </div>
      )}

      <div className="filterbar">
        {configura && (
          <select
            className="select"
            value={proyectoId}
            onChange={(e) => setProyectoId(e.target.value)}
            aria-label="Filtrar por proyecto"
          >
            <option value="">Todos los proyectos</option>
            {proyectos.map((proyecto) => (
              <option key={proyecto.id} value={proyecto.id}>
                {proyecto.clave} · {proyecto.nombre}
              </option>
            ))}
          </select>
        )}

        <select
          className="select"
          value={estatus}
          onChange={(e) => setEstatus(e.target.value as EstatusObra | '')}
          aria-label="Filtrar por estatus de obra"
        >
          <option value="">Todos los estatus</option>
          {ESTATUS.map((valor) => (
            <option key={valor} value={valor}>
              {etiquetaEstatusObra(valor)}
            </option>
          ))}
        </select>

        <input
          className="input search"
          type="search"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Buscar por clave de obra…"
          aria-label="Buscar por clave de obra"
        />
      </div>

      {configura ? (
        <div className="table-wrap">
          {obrasQ.isLoading || clustersQ.isLoading || proyectosQ.isLoading ? (
            <div className="text-mute text-sm" style={{ padding: '24px 12px' }}>
              Cargando…
            </div>
          ) : (
            <ArbolProyecto
              arbol={arbol}
              obraSeleccionada={seleccionadaId}
              onSeleccionarObra={(obra) => setSeleccionadaId(obra.id)}
              expandirTodo={texto.trim() !== ''}
              onNuevoCluster={(id) => setDialogo({ tipo: 'cluster', proyectoId: id })}
              onNuevaObra={
                administraObras
                  ? (id) => setDialogo({ tipo: 'obra', clusterId: id })
                  : undefined
              }
            />
          )}
        </div>
      ) : (
        <TablaObras
          obras={obras}
          cargando={obrasQ.isLoading}
          obraSeleccionada={seleccionadaId}
          onSeleccionarObra={(obra) => setSeleccionadaId(obra.id)}
        />
      )}

      {obraSeleccionada && (
        <PanelObra
          key={obraSeleccionada.id}
          obra={obraSeleccionada}
          rol={rol}
          cluster={clusters.find((cluster) => cluster.id === obraSeleccionada.cluster_id)}
          prototipo={prototipos.find(
            (prototipo) => prototipo.id === obraSeleccionada.prototipo_id,
          )}
          onCerrar={() => setSeleccionadaId(null)}
          onCambiada={refrescarObras}
        />
      )}

      {dialogo?.tipo === 'proyecto' && (
        <AltaProyecto
          onCerrar={cerrarDialogo}
          onCreado={() => {
            cerrarDialogo();
            setAviso('Proyecto creado');
            void proyectosQ.refetch();
          }}
        />
      )}

      {dialogo?.tipo === 'cluster' && (
        <AltaCluster
          proyectos={proyectos}
          proyectoInicial={dialogo.proyectoId}
          onCerrar={cerrarDialogo}
          onCreado={() => {
            cerrarDialogo();
            setAviso('Cluster creado');
            void clustersQ.refetch();
          }}
        />
      )}

      {dialogo?.tipo === 'prototipo' && (
        <AltaPrototipo
          proyectos={proyectos}
          proyectoInicial={dialogo.proyectoId}
          onCerrar={cerrarDialogo}
          onCreado={() => {
            cerrarDialogo();
            setAviso('Prototipo creado');
            void prototiposQ.refetch();
          }}
        />
      )}

      {dialogo?.tipo === 'obra' && (
        <CreadorDeObra
          proyectos={proyectos}
          clusters={clusters}
          prototipos={prototipos}
          clusterInicial={dialogo.clusterId}
          onCerrar={cerrarDialogo}
          onCreada={(obraId) => {
            cerrarDialogo();
            setAviso('Obra creada');
            refrescarObras();
            // Una obra nueva (catálogo base o desde cero) se forma midiendo: se abre en el cuantificador.
            if (obraId !== undefined) navegar(`/cuantificador?obra=${obraId}`);
          }}
        />
      )}

      {dialogo?.tipo === 'lote' && (
        <AltaMasivaObras
          proyectos={proyectos}
          clusters={clusters}
          prototipos={prototipos}
          clusterInicial={dialogo.clusterId}
          onCerrar={cerrarDialogo}
          onCreadas={(cuantas) => {
            cerrarDialogo();
            setAviso(`${cuantas} obras creadas`);
            refrescarObras();
          }}
        />
      )}
    </div>
  );
}
