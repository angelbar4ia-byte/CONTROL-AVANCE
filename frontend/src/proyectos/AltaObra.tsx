/**
 * Alta de obra (lote) — `POST /api/v1/obras` (§11.2, solo Control de obra) ·
 * paso 1 del Workflow A (§11.3 A.1).
 *
 * El contrato pide `cluster_id` y `clave`, y marca `prototipo_id` como
 * "obligatorio salvo en urbanización (`es_urba`)" (§7.2): eso se refleja en
 * el formulario para no mandar una petición que el servidor ya va a
 * rechazar. La regla sigue siendo del backend.
 */

import { useMemo, useState, type FormEvent } from 'react';

import { useCrearObraApiV1ObrasPost } from '@/api/generado/obras/obras';
import { useListarUsuariosApiV1UsuariosGet } from '@/api/generado/usuarios/usuarios';
import { Rol } from '@/api/generado/modelo';
import type {
  ClusterRespuesta,
  PrototipoRespuesta,
  ProyectoRespuesta,
  UsuarioRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { CampoSelect, CampoTexto, type Opcion } from './Campos';
import { proyectoDeCluster, prototiposDeProyecto } from './arbol';
import { numeroOpcional, textoOpcional } from './formulario';

interface Props {
  readonly proyectos: readonly ProyectoRespuesta[];
  readonly clusters: readonly ClusterRespuesta[];
  readonly prototipos: readonly PrototipoRespuesta[];
  readonly clusterInicial?: string;
  readonly onCerrar: () => void;
  readonly onCreada: () => void;
}

/** `PROYECTO · CLUSTER — nombre`, para no confundir clusters homónimos. */
export function opcionesCluster(
  proyectos: readonly ProyectoRespuesta[],
  clusters: readonly ClusterRespuesta[],
): readonly Opcion[] {
  const claveProyecto = new Map(proyectos.map((proyecto) => [proyecto.id, proyecto.clave]));
  return clusters.map((cluster) => ({
    valor: cluster.id,
    etiqueta: `${claveProyecto.get(cluster.proyecto_id) ?? '—'} · ${cluster.clave} — ${cluster.nombre}`,
  }));
}

export function AltaObra({
  proyectos,
  clusters,
  prototipos,
  clusterInicial = '',
  onCerrar,
  onCreada,
}: Props) {
  const [clusterId, setClusterId] = useState(clusterInicial);
  const [clave, setClave] = useState('');
  const [prototipoId, setPrototipoId] = useState('');
  const [residenteId, setResidenteId] = useState('');
  const [fechaInicio, setFechaInicio] = useState('');
  const [fechaFin, setFechaFin] = useState('');
  const [m2, setM2] = useState('');
  const [esUrba, setEsUrba] = useState(false);
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  const crear = useCrearObraApiV1ObrasPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        onCreada();
      },
      onError: (err) => setError({ mensaje: err.message, campo: err.campo }),
    },
  });

  // Residente sale de Equipo, no se teclea a mano: un uuid copiado mal manda
  // a un residente equivocado sin que nadie lo note hasta que ya no ve su obra.
  const usuariosQ = useListarUsuariosApiV1UsuariosGet<UsuarioRespuesta[], ErrorApi>({
    rol: Rol.residente,
  });
  const residentes = useMemo(
    () => (usuariosQ.data ?? []).filter((usuario) => usuario.estatus === 'activo'),
    [usuariosQ.data],
  );

  const prototiposDelCluster = useMemo(
    () => prototiposDeProyecto(prototipos, proyectoDeCluster(clusters, clusterId)),
    [prototipos, clusters, clusterId],
  );

  const faltaPrototipo = !esUrba && prototipoId === '';
  const puedeEnviar =
    clusterId !== '' && clave.trim() !== '' && !faltaPrototipo && !crear.isPending;

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!puedeEnviar) return;
    crear.mutate({
      data: {
        cluster_id: clusterId,
        clave: clave.trim(),
        prototipo_id: esUrba ? null : textoOpcional(prototipoId),
        residente_id: textoOpcional(residenteId),
        fecha_inicio: textoOpcional(fechaInicio),
        fecha_fin: textoOpcional(fechaFin),
        m2: numeroOpcional(m2),
        es_urba: esUrba,
      },
    });
  }

  return (
    <Modal titulo="Nueva obra" onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          <CampoSelect
            id="obra-cluster"
            etiqueta="Cluster"
            valor={clusterId}
            onCambio={(valor) => {
              setClusterId(valor);
              setPrototipoId('');
            }}
            opciones={opcionesCluster(proyectos, clusters)}
            vacio="Selecciona un cluster"
            requerido
          />
          <CampoTexto
            id="obra-clave"
            etiqueta="Clave"
            valor={clave}
            onCambio={setClave}
            mono
            requerido
            marcador="FRESNO 01"
            pista="CLUSTER + LOTE (§10.1)."
          />

          <div className="field">
            <label className="field__label" htmlFor="obra-es-urba">
              Urbanización
            </label>
            <div className="row gap-4">
              <input
                id="obra-es-urba"
                type="checkbox"
                checked={esUrba}
                onChange={(e) => {
                  setEsUrba(e.target.checked);
                  if (e.target.checked) setPrototipoId('');
                }}
              />
              <span className="text-sm text-soft">
                La obra es de urbanización: no lleva prototipo (§7.2).
              </span>
            </div>
          </div>

          <CampoSelect
            id="obra-prototipo"
            etiqueta="Prototipo"
            valor={prototipoId}
            onCambio={setPrototipoId}
            opciones={prototiposDelCluster.map((prototipo) => ({
              valor: prototipo.id,
              etiqueta: `${prototipo.clave} · ${prototipo.nombre}`,
            }))}
            vacio={esUrba ? 'No aplica en urbanización' : 'Selecciona un prototipo'}
            requerido={!esUrba}
            deshabilitado={esUrba || clusterId === ''}
            pista={
              clusterId === ''
                ? 'Elige primero el cluster: los prototipos son del proyecto (§7.2).'
                : 'Es el árbol que recorre la generación de actividades (§11.3 A.2).'
            }
          />

          <CampoSelect
            id="obra-residente"
            etiqueta="Residente"
            valor={residenteId}
            onCambio={setResidenteId}
            opciones={residentes.map((usuario) => ({
              valor: usuario.id,
              etiqueta: usuario.nombre,
            }))}
            vacio={
              usuariosQ.isLoading
                ? 'Cargando…'
                : residentes.length === 0
                  ? 'No hay usuarios con rol Residente'
                  : 'Sin asignar'
            }
            deshabilitado={usuariosQ.isLoading || residentes.length === 0}
            pista="Define el alcance del Residente sobre esta obra (§4). Sale de Equipo — se puede asignar después."
          />

          <div className="row gap-12">
            <div style={{ flex: 1 }}>
              <CampoTexto
                id="obra-fecha-inicio"
                etiqueta="Fecha de inicio"
                valor={fechaInicio}
                onCambio={setFechaInicio}
                tipo="date"
              />
            </div>
            <div style={{ flex: 1 }}>
              <CampoTexto
                id="obra-fecha-fin"
                etiqueta="Fecha de fin"
                valor={fechaFin}
                onCambio={setFechaFin}
                tipo="date"
              />
            </div>
            <div style={{ flex: 1 }}>
              <CampoTexto
                id="obra-m2"
                etiqueta="m²"
                valor={m2}
                onCambio={setM2}
                tipo="number"
                mono
                paso="any"
                minimo="0"
              />
            </div>
          </div>

          {error && <ErrorBanner mensaje={error.mensaje} campo={error.campo} />}
        </div>

        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={!puedeEnviar}>
            {crear.isPending ? 'Creando…' : 'Crear obra'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
