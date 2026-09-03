/**
 * El catálogo de oficios (§8.3, migración 0047).
 *
 * El **segundo eje** del trabajo. El frente —OBRA, INSTALACIONES,
 * SUBCONTRATOS, PINTURA— dice qué clase de contratista se contrata y cuelga de
 * la etapa; el oficio dice qué sabe hacer y cuelga del concepto. Hacen falta
 * los dos: en la obra real un solo frente concentra el 90% de las jornadas, y
 * nadie contrata "noventa por ciento de la obra".
 *
 * ## Por qué se puede fusionar
 *
 * El catálogo del cliente escribe el mismo oficio de dos formas —
 * `EQUIPAMIENTO` con claves `EQU` y `EQUIPAMIENTOS` con claves `MSA`—, y
 * separados parten el desglose de un frente en dos renglones que nadie puede
 * contratar por separado. Fusionar pasa conceptos y contratistas al que se
 * queda, y **registra el nombre absorbido como alias** (§10.3): sin eso, la
 * próxima carga del mismo archivo —que sigue trayendo los dos nombres— lo
 * volvería a crear y la fusión se desharía sola.
 *
 * Es difícil de revertir, así que se confirma y se dice qué se movió.
 */

import { useState } from 'react';

import {
  useCrearEspecialidadApiV1EspecialidadesPost,
  useEditarEspecialidadApiV1EspecialidadesEspecialidadIdPatch,
  useFusionarEspecialidadApiV1EspecialidadesEspecialidadIdFusionarPost,
} from '@/api/generado/proyectos/proyectos';
import type { EspecialidadRespuesta, FusionRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { fmtEntero } from '@/lib/formato';

interface Props {
  readonly especialidades: readonly EspecialidadRespuesta[];
  /** Cuántos conceptos usa cada oficio, para poder decidir cuál absorbe. */
  readonly conceptosPorOficio: ReadonlyMap<string, number>;
  readonly cargando: boolean;
  /** El rol configura catálogos: con `false` la pantalla es de lectura. */
  readonly administra: boolean;
  readonly onCambio: () => void;
}

export function Especialidades({
  especialidades,
  conceptosPorOficio,
  cargando,
  administra,
  onCambio,
}: Props) {
  const [fusionando, setFusionando] = useState<EspecialidadRespuesta | null>(null);
  const [resultado, setResultado] = useState<FusionRespuesta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nuevo, setNuevo] = useState({ clave: '', nombre: '' });

  const crear = useCrearEspecialidadApiV1EspecialidadesPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setNuevo({ clave: '', nombre: '' });
        onCambio();
      },
      onError: (err) => setError(err.message),
    },
  });

  const editar = useEditarEspecialidadApiV1EspecialidadesEspecialidadIdPatch<ErrorApi>({
    mutation: { onSuccess: onCambio, onError: (err) => setError(err.message) },
  });

  const fusionar =
    useFusionarEspecialidadApiV1EspecialidadesEspecialidadIdFusionarPost<ErrorApi>({
      mutation: {
        onSuccess: (respuesta) => {
          setFusionando(null);
          setResultado(respuesta as FusionRespuesta);
          onCambio();
        },
        onError: (err) => setError(err.message),
      },
    });

  return (
    <>
      {error && <ErrorBanner mensaje={error} />}

      {resultado !== null && (
        <div className="mb-8" role="status">
          <span className="badge badge--ok">Fusión aplicada</span>{' '}
          Se movieron {fmtEntero(resultado.conceptos)} concepto(s) y{' '}
          {fmtEntero(resultado.contratistas)} contratista(s).{' '}
          <strong>{resultado.alias_registrado}</strong> queda homologado: la
          próxima carga del catálogo ya no lo vuelve a crear.{' '}
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => setResultado(null)}
          >
            Entendido
          </button>
        </div>
      )}

      {administra && (
        <div className="filterbar">
          <div className="field" style={{ maxWidth: 130 }}>
            <label className="field__label" htmlFor="oficio-clave">
              Clave
            </label>
            <input
              id="oficio-clave"
              className="input"
              value={nuevo.clave}
              onChange={(e) => setNuevo({ ...nuevo, clave: e.target.value })}
              placeholder="ALB"
            />
          </div>
          <div className="field" style={{ minWidth: 220 }}>
            <label className="field__label" htmlFor="oficio-nombre">
              Nombre
            </label>
            <input
              id="oficio-nombre"
              className="input"
              value={nuevo.nombre}
              onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })}
              placeholder="Albañilería"
            />
          </div>
          <button
            type="button"
            className="btn btn--primary"
            disabled={
              nuevo.clave.trim() === '' ||
              nuevo.nombre.trim() === '' ||
              crear.isPending
            }
            onClick={() => {
              setError(null);
              crear.mutate({
                data: {
                  clave: nuevo.clave.trim().toUpperCase(),
                  nombre: nuevo.nombre.trim(),
                  orden: especialidades.length + 1,
                },
              });
            }}
          >
            {crear.isPending ? 'Guardando…' : 'Agregar oficio'}
          </button>
        </div>
      )}

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th style={{ minWidth: 90 }}>Clave</th>
                <th style={{ minWidth: 240 }}>Nombre</th>
                <th className="is-num" style={{ minWidth: 110 }}>
                  Conceptos
                </th>
                {administra && <th style={{ minWidth: 110 }} />}
              </tr>
            </thead>
            <tbody>
              {cargando && (
                <tr>
                  <td colSpan={administra ? 4 : 3} className="text-mute text-sm">
                    Cargando…
                  </td>
                </tr>
              )}
              {!cargando && especialidades.length === 0 && (
                <tr>
                  <td colSpan={administra ? 4 : 3}>
                    <div className="empty">
                      <div className="empty-title">Todavía no hay oficios</div>
                      <div className="empty-sub">
                        Se crean al cargar el catálogo de conceptos, o a mano
                        aquí arriba.
                      </div>
                    </div>
                  </td>
                </tr>
              )}
              {especialidades.map((oficio) => (
                <tr key={oficio.id}>
                  <td className="mono">{oficio.clave}</td>
                  <td>
                    {administra ? (
                      <input
                        className="input"
                        defaultValue={oficio.nombre}
                        aria-label={`Nombre de ${oficio.clave}`}
                        onBlur={(e) => {
                          const nombre = e.target.value.trim();
                          if (nombre === '' || nombre === oficio.nombre) return;
                          setError(null);
                          editar.mutate({
                            especialidadId: oficio.id,
                            data: { nombre },
                          });
                        }}
                      />
                    ) : (
                      oficio.nombre
                    )}
                  </td>
                  <td className="is-num">
                    {fmtEntero(conceptosPorOficio.get(oficio.id) ?? 0)}
                  </td>
                  {administra && (
                    <td>
                      <button
                        type="button"
                        className="btn btn--sm"
                        disabled={especialidades.length < 2}
                        title={
                          especialidades.length < 2
                            ? 'Hace falta otro oficio con el cual unirlo'
                            : 'Unir otro oficio dentro de éste'
                        }
                        onClick={() => {
                          setError(null);
                          setFusionando(oficio);
                        }}
                      >
                        Fusionar
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {fusionando !== null && (
        <DialogoDeFusion
          destino={fusionando}
          candidatos={especialidades.filter((e) => e.id !== fusionando.id)}
          conceptosPorOficio={conceptosPorOficio}
          guardando={fusionar.isPending}
          onCerrar={() => setFusionando(null)}
          onFusionar={(absorbidaId) =>
            fusionar.mutate({
              especialidadId: fusionando.id,
              data: { absorbida_id: absorbidaId },
            })
          }
        />
      )}
    </>
  );
}

function DialogoDeFusion({
  destino,
  candidatos,
  conceptosPorOficio,
  guardando,
  onCerrar,
  onFusionar,
}: {
  readonly destino: EspecialidadRespuesta;
  readonly candidatos: readonly EspecialidadRespuesta[];
  readonly conceptosPorOficio: ReadonlyMap<string, number>;
  readonly guardando: boolean;
  readonly onCerrar: () => void;
  readonly onFusionar: (absorbidaId: string) => void;
}) {
  const [absorbidaId, setAbsorbidaId] = useState('');
  const absorbida = candidatos.find((c) => c.id === absorbidaId);

  return (
    <Modal titulo={`Fusionar dentro de ${destino.clave}`} onCerrar={onCerrar}>
      <div className="sheet__body">
        <p className="text-mute text-sm">
          El oficio que elijas <strong>desaparece</strong>: sus conceptos y sus
          contratistas pasan a {destino.clave} · {destino.nombre}. Su nombre
          queda homologado, así que volver a cargar el catálogo no lo recrea.
        </p>

        <div className="field">
          <label className="field__label" htmlFor="absorbida">
            Oficio que desaparece
          </label>
          <select
            id="absorbida"
            className="select"
            value={absorbidaId}
            onChange={(e) => setAbsorbidaId(e.target.value)}
          >
            <option value="">Elige uno…</option>
            {candidatos.map((candidato) => (
              <option key={candidato.id} value={candidato.id}>
                {candidato.clave} · {candidato.nombre} (
                {fmtEntero(conceptosPorOficio.get(candidato.id) ?? 0)} conceptos)
              </option>
            ))}
          </select>
        </div>

        {absorbida !== undefined && (
          <div className="mt-8" role="status">
            <span className="badge badge--warn">Ojo</span> Se moverán{' '}
            {fmtEntero(conceptosPorOficio.get(absorbida.id) ?? 0)} concepto(s) de{' '}
            <strong>{absorbida.nombre}</strong> a{' '}
            <strong>{destino.nombre}</strong>, y {absorbida.clave} dejará de
            existir. Esto no se deshace solo.
          </div>
        )}
      </div>

      <div className="sheet__footer">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={absorbidaId === '' || guardando}
          onClick={() => onFusionar(absorbidaId)}
        >
          {guardando ? 'Fusionando…' : 'Fusionar'}
        </button>
      </div>
    </Modal>
  );
}
