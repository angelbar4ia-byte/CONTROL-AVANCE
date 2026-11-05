/**
 * Escenario «Nuevo» (cerebro WORKFLOWS.md §8.9; D-571, D-574): se entra por el cuantificador y la
 * obra se crea desde aquí, sin prototipo de dónde copiar.
 *
 * Se elige el **catálogo base de 1 o de 2 plantas** —los dos tipos de prototipo—: se forma
 * con la estructura y los conceptos de ese prototipo, **sin cantidades**. Crear la obra y su
 * presupuesto es un solo acto: aquí se crea y se genera. Las cantidades llegan midiendo, y en
 * esta obra lo que se mide **es** el presupuesto.
 *
 * **Desde cero** (escenario 4, D-578): sin obra anterior de dónde copiar, *el paramétrico primero y
 * luego se mide*. En vez del catálogo se eligen ensambles —uno por tipo de espacio, D-579— que
 * componen la estructura con cantidades estimadas; después se mide por partes.
 */

import { useMemo, useState, type FormEvent, type ReactNode } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { Rol } from '@/api/generado/modelo';
import type { ClusterRespuesta, ProyectoRespuesta, UsuarioRespuesta } from '@/api/generado/modelo';
import { useGenerarObraApiV1ObrasObraIdGenerarPost } from '@/api/generado/obras/obras';
import { useListarEnsamblesApiV1EnsamblesGet, useGenerarDesdeEnsambleApiV1EnsamblesEnsambleIdGenerarPost } from '@/api/generado/ensambles/ensambles';
import {
  useCatalogosBaseApiV1CatalogosBaseGet,
  useCrearObraDesdeCatalogoBaseApiV1ObrasDesdeCatalogoBasePost,
  useCrearObraDesdeCeroApiV1ObrasDesdeCeroPost,
} from '@/api/generado/partes/partes';
import {
  useListarClustersApiV1ClustersGet,
  useListarProyectosApiV1ProyectosGet,
} from '@/api/generado/proyectos/proyectos';
import { useListarUsuariosApiV1UsuariosGet } from '@/api/generado/usuarios/usuarios';
import { claveDeIdempotencia } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { CampoSelect, CampoTexto } from '@/proyectos/Campos';
import { opcionesCluster } from '@/proyectos/AltaObra';
import { textoOpcional } from '@/proyectos/formulario';

interface Props {
  readonly onCerrar: () => void;
  /** La obra ya está creada y generada: se abre en el cuantificador. */
  readonly onCreada: (obraId: string) => void;
  /** El selector «Parte de» del Creador de obra. */
  readonly origen?: ReactNode;
}

export function NuevaObra({ onCerrar, onCreada, origen }: Props) {
  const [clusterId, setClusterId] = useState('');
  const [clave, setClave] = useState('');
  const [plantas, setPlantas] = useState<1 | 2>(1);
  const [residenteId, setResidenteId] = useState('');
  const [arranque, setArranque] = useState<'catalogo' | 'cero'>('catalogo');
  // Por tipo de espacio: el ensamble elegido y cuántas veces entra.
  const [espacios, setEspacios] = useState<Readonly<Record<string, string>>>({});
  const [trabajando, setTrabajando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Una clave por intento: un doble clic no deja dos obras.
  const idem = useMemo(claveDeIdempotencia, []);

  const proyectos = useListarProyectosApiV1ProyectosGet<ProyectoRespuesta[], ErrorApi>();
  const clusters = useListarClustersApiV1ClustersGet<ClusterRespuesta[], ErrorApi>();
  const catalogos = useCatalogosBaseApiV1CatalogosBaseGet();
  const usuarios = useListarUsuariosApiV1UsuariosGet<UsuarioRespuesta[], ErrorApi>({ rol: Rol.residente });
  const residentes = useMemo(
    () => (usuarios.data ?? []).filter((u) => u.estatus === 'activo'),
    [usuarios.data],
  );

  const ensambles = useListarEnsamblesApiV1EnsamblesGet(undefined, { query: { enabled: arranque === 'cero' } });
  const desdeCero = useCrearObraDesdeCeroApiV1ObrasDesdeCeroPost<ErrorApi>({
    request: { headers: { 'Idempotency-Key': idem } },
  });
  const componer = useGenerarDesdeEnsambleApiV1EnsamblesEnsambleIdGenerarPost<ErrorApi>();
  const generar = useGenerarObraApiV1ObrasObraIdGenerarPost<ErrorApi>({
    mutation: { onError: (e) => setError(`La obra se creó, pero no se pudo generar: ${e.message}`) },
  });
  const crear = useCrearObraDesdeCatalogoBaseApiV1ObrasDesdeCatalogoBasePost<ErrorApi>({
    mutation: {
      onError: (e) => setError(e.message),
      onSuccess: (obra) =>
        generar.mutate(
          { obraId: obra.obra_id, data: { modo_pago: 'destajo' } },
          { onSuccess: () => onCreada(obra.obra_id) },
        ),
    },
    request: { headers: { 'Idempotency-Key': idem } },
  });

  const elegido = (catalogos.data ?? []).find((c) => c.plantas === plantas);
  const elegidos = Object.entries(espacios).filter(([, f]) => Number(f) > 0);
  const puedeEnviar =
    clusterId !== '' &&
    clave.trim() !== '' &&
    !crear.isPending &&
    !generar.isPending &&
    !trabajando &&
    (arranque === 'catalogo' ? elegido?.disponible === true : elegidos.length > 0);

  /** Desde cero: la obra vacía, un ensamble por tipo de espacio y la generación. */
  async function crearDesdeCero() {
    setTrabajando(true);
    try {
      const obra = await desdeCero.mutateAsync({
        data: {
          cluster_id: clusterId,
          clave: clave.trim(),
          plantas,
          residente_id: textoOpcional(residenteId),
        },
      });
      for (const [ensambleId, factor] of elegidos) {
        const e = (ensambles.data ?? []).find((x) => x.id === ensambleId);
        await componer.mutateAsync({
          ensambleId,
          data: {
            presupuesto_id: obra.presupuesto_id,
            prototipo_id: obra.prototipo_id,
            factor,
            nombre: e?.nombre ?? 'Espacio',
          },
        });
      }
      await generar.mutateAsync({ obraId: obra.obra_id, data: { modo_pago: 'destajo' } });
      onCreada(obra.obra_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo crear la obra.');
    } finally {
      setTrabajando(false);
    }
  }

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!puedeEnviar) return;
    setError(null);
    if (arranque === 'cero') {
      void crearDesdeCero();
      return;
    }
    crear.mutate({
      data: {
        cluster_id: clusterId,
        clave: clave.trim(),
        plantas,
        residente_id: textoOpcional(residenteId),
      },
    });
  }

  return (
    <Modal titulo="Nueva obra" onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          {origen}
          <p className="text-mute text-sm">
            Una obra cuyo proyecto es diferente de todos los prototipos. Se forma su catálogo con la estructura y
            los conceptos de un prototipo, <strong>sin cantidades</strong>: llegan midiendo, y lo que mides es el
            presupuesto.
          </p>
          {error && <ErrorBanner mensaje={error} />}
          <CampoSelect
            id="nueva-cluster"
            etiqueta="Cluster"
            valor={clusterId}
            onCambio={setClusterId}
            opciones={opcionesCluster(proyectos.data ?? [], clusters.data ?? [])}
            vacio="Selecciona un cluster"
            requerido
          />
          <CampoTexto
            id="nueva-clave"
            etiqueta="Clave"
            valor={clave}
            onCambio={setClave}
            mono
            requerido
            marcador="FRESNO 01"
            pista="CLUSTER + LOTE (§10.1)."
          />
          <div className="field">
            <label className="field__label" htmlFor="nueva-arranque">
              Cómo arranca
            </label>
            <select
              id="nueva-arranque"
              className="select"
              value={arranque}
              onChange={(e) => setArranque(e.target.value as 'catalogo' | 'cero')}
            >
              <option value="catalogo">Midiendo sobre el catálogo base de 1 o 2 plantas</option>
              <option value="cero">Desde cero: el paramétrico primero y luego se mide</option>
            </select>
          </div>
          {arranque === 'cero' && (
            <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className="field__label">Ensambles por tipo de espacio</legend>
              <div className="col gap-8">
                {(ensambles.data ?? []).length === 0 && (
                  <span className="text-xs text-mute">No hay ensambles en el catálogo.</span>
                )}
                {(ensambles.data ?? []).map((e) => (
                  <div key={e.id} className="row gap-8" style={{ alignItems: 'center' }}>
                    <input
                      type="checkbox"
                      aria-label={`Usar ${e.nombre}`}
                      checked={e.id in espacios}
                      onChange={(ev) => {
                        const siguiente = { ...espacios };
                        if (ev.target.checked) siguiente[e.id] = '1';
                        else delete siguiente[e.id];
                        setEspacios(siguiente);
                      }}
                    />
                    <span className="text-sm" style={{ flex: 1 }}>
                      {e.clave} · {e.nombre}
                    </span>
                    {e.id in espacios && (
                      <input
                        className="input"
                        type="number"
                        min="0"
                        step="any"
                        aria-label={`Veces que entra ${e.nombre}`}
                        style={{ width: 90 }}
                        value={espacios[e.id]}
                        onChange={(ev) => setEspacios({ ...espacios, [e.id]: ev.target.value })}
                      />
                    )}
                  </div>
                ))}
              </div>
            </fieldset>
          )}
          <fieldset
            className="field"
            style={{ border: 0, padding: 0, margin: 0, display: arranque === 'cero' ? 'none' : undefined }}
          >
            <legend className="field__label">Catálogo base de cuantificación</legend>
            <div className="row gap-12" style={{ flexWrap: 'wrap' }}>
              {(catalogos.data ?? []).map((c) => (
                <label key={c.plantas} className="row gap-4" style={{ alignItems: 'flex-start' }}>
                  <input
                    type="radio"
                    name="nueva-plantas"
                    checked={plantas === c.plantas}
                    disabled={!c.disponible}
                    onChange={() => setPlantas(c.plantas as 1 | 2)}
                  />
                  <span className="col">
                    <span className="text-sm">{c.plantas === 1 ? '1 planta' : '2 plantas'}</span>
                    <span className="text-xs text-mute">
                      {c.disponible
                        ? `Plazo base ${c.plazo_base_semanas} semanas · de ${c.prototipo_clave} (${c.n_nodos} nodos)`
                        : 'Sin prototipo con estructura de dónde formarlo'}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          <CampoSelect
            id="nueva-residente"
            etiqueta="Residente"
            valor={residenteId}
            onCambio={setResidenteId}
            opciones={residentes.map((r) => ({ valor: r.id, etiqueta: r.nombre }))}
            vacio="Sin residente por ahora"
          />
        </div>
        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={!puedeEnviar}>
            {crear.isPending || generar.isPending || trabajando ? 'Creando…' : arranque === 'cero' ? 'Crear y componer' : 'Crear y empezar a medir'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
