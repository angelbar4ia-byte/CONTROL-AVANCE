/**
 * Alta de incidencia — `POST /incidencias` (§11.2, §11.3 F.1).
 *
 * *"Cualquier rol abre una incidencia"* (§11.2, contrato). El formulario
 * traduce a DTO en `formulario.ts`; la lista de actividades bloqueadas solo
 * se manda con impacto `detiene` (§6) y la UI lo dice explícitamente.
 *
 * ## Dónde en la obra, sin un select de nivel
 *
 * `nivel_id`/`etapa_id` (§7.4, migración 0050) no tienen un `<select>`
 * propio: se derivan de **"va junto a esta actividad"**, el mismo gesto que
 * ya usa Fuera de catálogo. El residente sabe con qué actividad está la
 * incidencia —está viéndola— y no con qué nivel corresponde por catálogo.
 *
 * ## El multi-select de actividades bloqueadas
 *
 * Antes era un textarea donde se pegaba **un UUID por línea**, el mismo
 * antipatrón que tenía Avances antes de que existiera
 * `GET /obras/{id}/actividades`. Con el endpoint ya disponible, se eligen de
 * una lista real.
 */

import { useMemo, useState, type FormEvent } from 'react';

import { useAbrirIncidenciaApiV1IncidenciasPost } from '@/api/generado/incidencias/incidencias';
import { useListarFrentesApiV1FrentesGet } from '@/api/generado/proyectos/proyectos';
import { useActividadesDeObraApiV1ObrasObraIdActividadesGet } from '@/api/generado/torre/torre';
import { ImpactoIncidencia, TipoIncidencia, type ActividadRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import { SelectorObra } from '@/lib/SelectorObra';
import {
  formularioIncidenciaVacio,
  incidenciaCompleta,
  peticionDeIncidencia,
  type FormularioIncidencia,
} from './formulario';
import { descripcionImpacto, detieneObra, etiquetaImpacto, etiquetaTipo } from './reglas';

interface Props {
  readonly obraIdInicial: string;
  readonly onCerrar: () => void;
  readonly onAbierta: () => void;
}

export function AltaIncidencia({ obraIdInicial, onCerrar, onAbierta }: Props) {
  const [formulario, setFormulario] = useState<FormularioIncidencia>(() =>
    formularioIncidenciaVacio(
      obraIdInicial,
      TipoIncidencia.falta_material,
      ImpactoIncidencia.detalle,
    ),
  );
  const [error, setError] = useState<string | null>(null);
  const [viaActividadId, setViaActividadId] = useState('');

  const frentes = useListarFrentesApiV1FrentesGet();
  const actividadesQ = useActividadesDeObraApiV1ObrasObraIdActividadesGet<
    ActividadRespuesta[],
    ErrorApi
  >(formulario.obraId, undefined, { query: { enabled: formulario.obraId !== '' } });
  const actividades = useMemo(() => actividadesQ.data ?? [], [actividadesQ.data]);
  const viaActividad = actividades.find((a) => a.id === viaActividadId);

  const abrir = useAbrirIncidenciaApiV1IncidenciasPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        onAbierta();
      },
      onError: (err) => setError(err.message),
    },
  });

  function cambiar<K extends keyof FormularioIncidencia>(
    campo: K,
    valor: FormularioIncidencia[K],
  ) {
    setFormulario((previo) => ({ ...previo, [campo]: valor }));
  }

  const detiene = detieneObra(formulario.impacto);

  // Dónde en la obra: de "va junto a esta actividad" si se eligió, y si no,
  // de la primera actividad que la incidencia bloquea — cuando detiene una
  // actividad concreta, ya está diciendo dónde está pasando.
  const primeraBloqueada = actividades.find((a) => a.id === formulario.bloqueaActividades[0]);
  const ubicacion = viaActividad ?? (detiene ? primeraBloqueada : undefined);

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!incidenciaCompleta(formulario)) return;
    abrir.mutate({
      data: peticionDeIncidencia({
        ...formulario,
        nivelId: ubicacion?.nivel_id ?? '',
        etapaId: ubicacion?.etapa_id ?? '',
      }),
    });
  }

  return (
    <Sheet titulo="Abrir incidencia" subtitulo="POST /incidencias · §11.3 F.1" onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          {error && <ErrorBanner mensaje={error} />}

          <SelectorObra
            id="incidencia-obra"
            etiqueta="Obra"
            valor={formulario.obraId}
            onCambio={(obraId) => cambiar('obraId', obraId)}
            requerido
          />

          <div className="field">
            <label className="field__label" htmlFor="incidencia-titulo">
              Título
            </label>
            <input
              id="incidencia-titulo"
              className="input"
              required
              value={formulario.titulo}
              onChange={(e) => cambiar('titulo', e.target.value)}
            />
          </div>

          <div className="row gap-12">
            <div className="field w-full">
              <label className="field__label" htmlFor="incidencia-tipo">
                Tipo
              </label>
              <select
                id="incidencia-tipo"
                className="select"
                value={formulario.tipo}
                onChange={(e) => cambiar('tipo', e.target.value as TipoIncidencia)}
              >
                {Object.values(TipoIncidencia).map((tipo) => (
                  <option key={tipo} value={tipo}>
                    {etiquetaTipo(tipo)}
                  </option>
                ))}
              </select>
            </div>

            <div className="field w-full">
              <label className="field__label" htmlFor="incidencia-impacto">
                Impacto
              </label>
              <select
                id="incidencia-impacto"
                className="select"
                value={formulario.impacto}
                onChange={(e) => cambiar('impacto', e.target.value as ImpactoIncidencia)}
              >
                {Object.values(ImpactoIncidencia).map((impacto) => (
                  <option key={impacto} value={impacto}>
                    {etiquetaImpacto(impacto)}
                  </option>
                ))}
              </select>
              <div className="field__hint">{descripcionImpacto(formulario.impacto)}</div>
            </div>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="incidencia-frente">
              A quién se le compra (opcional)
            </label>
            <select
              id="incidencia-frente"
              className="select"
              value={formulario.frenteId}
              onChange={(e) => cambiar('frenteId', e.target.value)}
            >
              <option value="">Sin definir</option>
              {(frentes.data ?? []).map((frente) => (
                <option key={frente.id} value={frente.id}>
                  {frente.clave} · {frente.nombre}
                </option>
              ))}
            </select>
          </div>

          {formulario.obraId !== '' && (
            <div className="field">
              <label className="field__label" htmlFor="incidencia-via">
                Dónde en la obra (opcional)
              </label>
              <select
                id="incidencia-via"
                className="select"
                value={viaActividadId}
                onChange={(e) => setViaActividadId(e.target.value)}
              >
                <option value="">Sin ubicar</option>
                {actividades.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.nivel_descripcion ?? '—'} · {a.etapa_descripcion ?? '—'} ·{' '}
                    {(a.descripcion ?? '').slice(0, 34)}
                  </option>
                ))}
              </select>
              <div className="field__hint">
                Elige la actividad más cercana a donde pasa esto: de ahí sale
                el nivel y la etapa (§7.4) con los que se agrupa en la
                bandeja. Con impacto «detiene», elegir abajo qué bloquea ya lo
                ubica solo.
              </div>
            </div>
          )}

          <div className="field">
            <label className="field__label" htmlFor="incidencia-descripcion">
              Descripción (opcional)
            </label>
            <textarea
              id="incidencia-descripcion"
              className="textarea"
              value={formulario.descripcion}
              onChange={(e) => cambiar('descripcion', e.target.value)}
            />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="incidencia-limite">
              Fecha límite (opcional)
            </label>
            <input
              id="incidencia-limite"
              className="input"
              type="date"
              value={formulario.fechaLimite}
              onChange={(e) => cambiar('fechaLimite', e.target.value)}
            />
          </div>

          {detiene && (
            <div className="field">
              <span className="field__label">Actividades que se detienen</span>
              {formulario.obraId === '' ? (
                <div className="field__hint">Elige primero la obra.</div>
              ) : actividades.length === 0 ? (
                <div className="field__hint">
                  {actividadesQ.isLoading ? 'Cargando…' : 'Esta obra no tiene actividades.'}
                </div>
              ) : (
                <div
                  className="col gap-4"
                  style={{ maxHeight: 220, overflowY: 'auto', border: '1px solid var(--c-line)', borderRadius: 'var(--r-md)', padding: 8 }}
                >
                  {actividades.map((a) => {
                    const marcada = formulario.bloqueaActividades.includes(a.id);
                    return (
                      <label key={a.id} className="row gap-8 text-sm" style={{ alignItems: 'center' }}>
                        <input
                          type="checkbox"
                          checked={marcada}
                          onChange={() =>
                            cambiar(
                              'bloqueaActividades',
                              marcada
                                ? formulario.bloqueaActividades.filter((id) => id !== a.id)
                                : [...formulario.bloqueaActividades, a.id],
                            )
                          }
                        />
                        <span className="mono text-xs">{a.concepto_clave ?? 'EXT'}</span>
                        <span className="text-mute text-xs">
                          {a.nivel_descripcion} · {a.etapa_descripcion}
                        </span>
                        <span>{a.descripcion}</span>
                      </label>
                    );
                  })}
                </div>
              )}
              <div className="field__hint">
                Con impacto «detiene» la incidencia <strong>frena la obra</strong>: el
                backend bloquea estas actividades y recalcula la ruta crítica
                (§6, §11.3 F.5). El contrato solo acepta esta lista con este
                impacto.
              </div>
            </div>
          )}
        </div>

        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button
            type="submit"
            className="btn btn--accent"
            disabled={abrir.isPending || !incidenciaCompleta(formulario)}
          >
            {abrir.isPending ? 'Abriendo…' : 'Abrir incidencia'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
