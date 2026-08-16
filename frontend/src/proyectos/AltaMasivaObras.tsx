/**
 * Alta masiva de obras — `POST /api/v1/obras/bulk` (§11.2, solo Control de
 * obra).
 *
 * Un cluster se da de alta lote por lote, y capturarlos de uno en uno no
 * escala. Aquí se pegan las claves (una por línea) y se aplican los mismos
 * datos comunes a todas. El contrato es explícito: **o entran todas o no
 * entra ninguna**, así que se avisa de las claves repetidas antes de enviar
 * —bastaría una para tumbar el lote completo (§3.3).
 */

import { useMemo, useState, type FormEvent } from 'react';

import { useCrearObrasEnLoteApiV1ObrasBulkPost } from '@/api/generado/obras/obras';
import type {
  ClusterRespuesta,
  PrototipoRespuesta,
  ProyectoRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { CampoSelect, CampoTexto } from './Campos';
import { opcionesCluster } from './AltaObra';
import { proyectoDeCluster, prototiposDeProyecto } from './arbol';
import { numeroOpcional, obrasDelLote, parsearClavesLote, textoOpcional } from './formulario';

interface Props {
  readonly proyectos: readonly ProyectoRespuesta[];
  readonly clusters: readonly ClusterRespuesta[];
  readonly prototipos: readonly PrototipoRespuesta[];
  readonly clusterInicial?: string;
  readonly onCerrar: () => void;
  readonly onCreadas: (cuantas: number) => void;
}

export function AltaMasivaObras({
  proyectos,
  clusters,
  prototipos,
  clusterInicial = '',
  onCerrar,
  onCreadas,
}: Props) {
  const [clusterId, setClusterId] = useState(clusterInicial);
  const [prototipoId, setPrototipoId] = useState('');
  const [residenteId, setResidenteId] = useState('');
  const [fechaInicio, setFechaInicio] = useState('');
  const [m2, setM2] = useState('');
  const [esUrba, setEsUrba] = useState(false);
  const [texto, setTexto] = useState('');
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  const crear = useCrearObrasEnLoteApiV1ObrasBulkPost<ErrorApi>({
    mutation: {
      onSuccess: (obras) => {
        setError(null);
        onCreadas(obras.length);
      },
      onError: (err) => setError({ mensaje: err.message, campo: err.campo }),
    },
  });

  const prototiposDelCluster = useMemo(
    () => prototiposDeProyecto(prototipos, proyectoDeCluster(clusters, clusterId)),
    [prototipos, clusters, clusterId],
  );

  const { claves, duplicadas } = useMemo(() => parsearClavesLote(texto), [texto]);

  const faltaPrototipo = !esUrba && prototipoId === '';
  const puedeEnviar =
    clusterId !== '' && claves.length > 0 && !faltaPrototipo && !crear.isPending;

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!puedeEnviar) return;
    crear.mutate({
      data: {
        obras: [
          ...obrasDelLote(
            {
              cluster_id: clusterId,
              prototipo_id: esUrba ? null : textoOpcional(prototipoId),
              residente_id: textoOpcional(residenteId),
              fecha_inicio: textoOpcional(fechaInicio),
              m2: numeroOpcional(m2),
              es_urba: esUrba,
            },
            claves,
          ),
        ],
      },
    });
  }

  return (
    <Modal titulo="Alta masiva de obras" onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          <CampoSelect
            id="lote-cluster"
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

          <div className="field">
            <label className="field__label" htmlFor="lote-claves">
              Claves de obra (una por línea)
            </label>
            <textarea
              id="lote-claves"
              className="textarea mono"
              rows={7}
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder={'FRESNO 01\nFRESNO 02\nFRESNO 03'}
              required
            />
            <div className="field__hint mono tnum">
              {claves.length} obra{claves.length === 1 ? '' : 's'} a dar de alta
            </div>
            {duplicadas.length > 0 && (
              <div className="field__hint" style={{ color: 'var(--c-warn)' }}>
                Claves repetidas (se envían una sola vez): {duplicadas.join(', ')}
              </div>
            )}
          </div>

          <div className="field">
            <label className="field__label" htmlFor="lote-es-urba">
              Urbanización
            </label>
            <div className="row gap-4">
              <input
                id="lote-es-urba"
                type="checkbox"
                checked={esUrba}
                onChange={(e) => {
                  setEsUrba(e.target.checked);
                  if (e.target.checked) setPrototipoId('');
                }}
              />
              <span className="text-sm text-soft">
                Todo el lote es de urbanización: sin prototipo (§7.2).
              </span>
            </div>
          </div>

          <CampoSelect
            id="lote-prototipo"
            etiqueta="Prototipo (para todas)"
            valor={prototipoId}
            onCambio={setPrototipoId}
            opciones={prototiposDelCluster.map((prototipo) => ({
              valor: prototipo.id,
              etiqueta: `${prototipo.clave} · ${prototipo.nombre}`,
            }))}
            vacio={esUrba ? 'No aplica en urbanización' : 'Selecciona un prototipo'}
            requerido={!esUrba}
            deshabilitado={esUrba || clusterId === ''}
          />

          <CampoTexto
            id="lote-residente"
            etiqueta="Residente (uuid, para todas)"
            valor={residenteId}
            onCambio={setResidenteId}
            mono
          />

          <div className="row gap-12">
            <div style={{ flex: 1 }}>
              <CampoTexto
                id="lote-fecha-inicio"
                etiqueta="Fecha de inicio"
                valor={fechaInicio}
                onCambio={setFechaInicio}
                tipo="date"
              />
            </div>
            <div style={{ flex: 1 }}>
              <CampoTexto
                id="lote-m2"
                etiqueta="m² (para todas)"
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
            {crear.isPending ? 'Creando…' : `Crear ${claves.length} obras`}
          </button>
        </div>
      </form>
    </Modal>
  );
}
