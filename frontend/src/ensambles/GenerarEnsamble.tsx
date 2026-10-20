/**
 * Generación: compone una instancia del ensamble dentro del presupuesto de un
 * prototipo — `POST /ensambles/{id}/generar` (§11.2, solo Control de obra;
 * skill `erp-parametrico` §6).
 *
 * Un mismo botón explícito sirve para **generar** (sin instancia previa: todo
 * concepto de la receta sale nuevo) y **regenerar** (con una instancia ya
 * existente: se refresca lo que nadie tocó y se *reporta* lo demás). Nunca se
 * regenera solo — es una decisión de quien aprieta el botón.
 *
 * El presupuesto no se elige: es el **vigente** del prototipo (§7.3, §10.8),
 * el mismo que ya consultan el resto de las pantallas. Se muestra qué
 * versión es antes de escribir en él.
 *
 * El factor es cuántas veces entra el ensamble completo en esta instancia
 * ("2 recámaras tipo A"); **no** es el divisor de la tasa (§2 vs §5.7).
 */

import { useState, type FormEvent } from 'react';

import { useExplotarEnsambleApiV1EnsamblesEnsambleIdExplosionGet } from '@/api/generado/ensambles/ensambles';
import { useGenerarDesdeEnsambleApiV1EnsamblesEnsambleIdGenerarPost } from '@/api/generado/ensambles/ensambles';
import { usePresupuestoDePrototipoApiV1PrototiposPrototipoIdPresupuestoGet } from '@/api/generado/presupuesto/presupuesto';
import {
  useListarNodosDePrototipoApiV1PrototiposPrototipoIdNodosGet,
  useListarPrototiposApiV1PrototiposGet,
} from '@/api/generado/proyectos/proyectos';
import type {
  EnsambleRespuesta,
  ExplosionEnsambleRespuesta,
  InstanciaEnsambleRespuesta,
  NodoPrototipoRespuesta,
  PresupuestoRespuesta,
  PrototipoRespuesta,
  ReporteGeneracionRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { CampoSelect, CampoTexto } from '@/catalogos/Campos';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { fmtMXN } from '@/lib/formato';
import { ReporteGeneracion } from './ReporteGeneracion';
import { factorValido } from './reglas';

interface Props {
  readonly ensamble: EnsambleRespuesta;
  /** Si viene, se regenera esa instancia; si no, se crea una nueva. */
  readonly instancia?: InstanciaEnsambleRespuesta;
  readonly onCerrar: () => void;
  /** Para que quien abrió el modal refresque la lista de instancias. */
  readonly onGenerado: (reporte: ReporteGeneracionRespuesta) => void;
}

export function GenerarEnsamble({ ensamble, instancia, onCerrar, onGenerado }: Props) {
  const regenera = instancia !== undefined;

  const [prototipoId, setPrototipoId] = useState(instancia?.prototipo_id ?? '');
  const [factor, setFactor] = useState(instancia?.factor ?? '1');
  const [nombre, setNombre] = useState(instancia?.nombre ?? '');
  const [padreId, setPadreId] = useState(instancia?.parent_id ?? '');
  const [reporte, setReporte] = useState<ReporteGeneracionRespuesta | null>(null);
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  const prototiposQ = useListarPrototiposApiV1PrototiposGet<PrototipoRespuesta[], ErrorApi>();

  const presupuestoQ = usePresupuestoDePrototipoApiV1PrototiposPrototipoIdPresupuestoGet<
    PresupuestoRespuesta,
    ErrorApi
  >(prototipoId, { query: { enabled: prototipoId !== '', retry: false } });

  const nodosQ = useListarNodosDePrototipoApiV1PrototiposPrototipoIdNodosGet<
    NodoPrototipoRespuesta[],
    ErrorApi
  >(prototipoId, { query: { enabled: prototipoId !== '' && !regenera } });

  const factorOk = factorValido(factor);
  const previewQ = useExplotarEnsambleApiV1EnsamblesEnsambleIdExplosionGet<
    ExplosionEnsambleRespuesta,
    ErrorApi
  >(ensamble.id, { factor }, { query: { enabled: factorOk, retry: false } });

  const generar = useGenerarDesdeEnsambleApiV1EnsamblesEnsambleIdGenerarPost<ErrorApi>({
    mutation: {
      onSuccess: (respuesta) => {
        setError(null);
        setReporte(respuesta);
        onGenerado(respuesta);
      },
      onError: (err) => setError({ mensaje: err.message, campo: err.campo }),
    },
  });

  const presupuesto = presupuestoQ.data;
  const puedeEnviar =
    presupuesto !== undefined &&
    prototipoId !== '' &&
    nombre.trim() !== '' &&
    factorOk &&
    !generar.isPending;

  // Solo los niveles/etapas pueden agrupar la instancia; un concepto es hoja.
  const nodosPadre = (nodosQ.data ?? []).filter((nodo) => nodo.tipo !== 'concepto');

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!puedeEnviar || presupuesto === undefined) return;
    generar.mutate({
      ensambleId: ensamble.id,
      data: {
        presupuesto_id: presupuesto.id,
        prototipo_id: prototipoId,
        factor,
        nombre: nombre.trim(),
        prototipo_nodo_id: instancia?.id ?? null,
        parent_id: regenera || padreId === '' ? null : padreId,
      },
    });
  }

  return (
    <Modal
      titulo={`${regenera ? 'Regenerar' : 'Generar'} · ${ensamble.clave}`}
      onCerrar={onCerrar}
    >
      <form onSubmit={alEnviar}>
        <div className="sheet__body" style={{ maxHeight: '70vh' }}>
         <div className="col gap-12">
          {reporte !== null ? (
            <ReporteGeneracion reporte={reporte} />
          ) : (
            <>
              <CampoSelect
                id="gen-prototipo"
                etiqueta="Prototipo"
                valor={prototipoId}
                onCambio={(valor) => {
                  setPrototipoId(valor);
                  setPadreId('');
                }}
                opciones={(prototiposQ.data ?? []).map((p) => ({
                  valor: p.id,
                  etiqueta: `${p.clave} · ${p.nombre}`,
                }))}
                vacio="Elige un prototipo…"
                requerido
                pista={
                  regenera
                    ? 'Una instancia ya generada no cambia de prototipo.'
                    : 'Se escribe en su presupuesto vigente.'
                }
              />
              {regenera && (
                // Una instancia regenerada se queda en su prototipo.
                <div className="text-mute text-xs">Instancia: {instancia.nombre}</div>
              )}

              {prototipoId !== '' && (
                <div className="text-sm" role="status">
                  {presupuestoQ.isLoading ? (
                    <span className="text-mute">Buscando el presupuesto vigente…</span>
                  ) : presupuesto ? (
                    <span className="badge badge--outline">
                      Presupuesto vigente · v{presupuesto.version} · {presupuesto.origen}
                    </span>
                  ) : (
                    <ErrorBanner
                      mensaje={
                        presupuestoQ.error?.message ??
                        'Este prototipo no tiene un presupuesto vigente donde escribir.'
                      }
                    />
                  )}
                </div>
              )}

              <div className="row gap-12" style={{ alignItems: 'flex-start' }}>
                <div style={{ flex: 2 }}>
                  <CampoTexto
                    id="gen-nombre"
                    etiqueta="Nombre de la instancia"
                    valor={nombre}
                    onCambio={setNombre}
                    requerido
                    marcador="Recámara 1"
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <CampoTexto
                    id="gen-factor"
                    etiqueta="Veces que entra"
                    valor={factor}
                    onCambio={setFactor}
                    tipo="number"
                    mono
                    paso="any"
                    minimo="0"
                    requerido
                    pista="2 = dos recámaras tipo A."
                  />
                </div>
              </div>

              {!regenera && prototipoId !== '' && (
                <CampoSelect
                  id="gen-padre"
                  etiqueta="Dónde colgarla en el árbol"
                  valor={padreId}
                  onCambio={setPadreId}
                  opciones={nodosPadre.map((nodo) => ({ valor: nodo.id, etiqueta: nodo.nombre }))}
                  vacio="En la raíz del prototipo"
                />
              )}

              {factorOk && previewQ.data && (
                <div className="card">
                  <div className="card__body col gap-4">
                    <div className="text-mute text-xs mono" style={{ textTransform: 'uppercase' }}>
                      Costo con este factor (preview)
                    </div>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="text-mute text-sm">Total</span>
                      <span className="mono tnum">{fmtMXN(previewQ.data.precio.total)}</span>
                    </div>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="text-mute text-sm">Destajo</span>
                      <span className="mono tnum">{fmtMXN(previewQ.data.precio.destajo)}</span>
                    </div>
                  </div>
                </div>
              )}

              {regenera && (
                <div className="text-mute text-sm">
                  Regenerar refresca lo que nadie tocó y reporta el resto: no pisa ninguna partida
                  editada a mano ni borra nada (skill §6).
                </div>
              )}

              {error && <ErrorBanner mensaje={error.mensaje} campo={error.campo} />}
            </>
          )}
         </div>
        </div>

        <div className="sheet__footer">
          {reporte !== null ? (
            <button key="cerrar" type="button" className="btn btn--primary" onClick={onCerrar}>
              Cerrar
            </button>
          ) : (
            <>
              <button key="cancelar" type="button" className="btn" onClick={onCerrar}>
                Cancelar
              </button>
              <button
                key="enviar"
                type="submit"
                className="btn btn--primary"
                disabled={!puedeEnviar}
              >
                {generar.isPending ? 'Generando…' : regenera ? 'Regenerar' : 'Generar'}
              </button>
            </>
          )}
        </div>
      </form>
    </Modal>
  );
}
