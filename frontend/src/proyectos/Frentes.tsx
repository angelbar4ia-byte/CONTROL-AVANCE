/**
 * Frentes de obra y qué etapas agrupa cada uno (§8.3, §10.1, migración 0045).
 *
 * ## Qué es un frente aquí
 *
 * El jefe de obra lo dijo así: *"nuestro frente es una mezcla, es por etapa de
 * construcción. En mi nivel CIMENTACIÓN puedo tener 2 frentes, ESTRUCTURA e
 * INSTALACIONES, aunque INSTALACIONES tiene varias etapas de construcción"*.
 *
 * Y el catálogo real lo confirma: `ESTRUCTURA CIM`, `INSTALACIONES SANITARIAS
 * CIM`, `INSTALACIONES HIDRAULICAS CIM`, `INSTALACIONES ELECTRICAS CIM`,
 * `INSTALACIONES GAS CIM` — cuatro etapas que son **un** frente. Por eso los
 * ocho del §8.3 son semilla y no la lista cerrada: ésos nombran gremios, y el
 * frente es una decisión de cómo se contrata.
 *
 * ## Una etapa, un frente
 *
 * Marcarla en un frente la quita del que tuviera, y la pantalla lo dice antes
 * de guardar. Si estuviera en dos, su trabajo se contaría dos veces al planear
 * cuántas cuadrillas hacen falta — que es la cifra para la que existe este
 * mapeo.
 *
 * El `PUT` manda la lista **completa** del frente, no un delta: mover una
 * etapa es una llamada y no dos, y la pantalla no tiene que llevar la cuenta
 * de lo que quitó.
 */

import { useEffect, useMemo, useState } from 'react';

import { useListarEtapasApiV1EtapasGet } from '@/api/generado/catalogos/catalogos';
import {
  useAsignarEtapasAlFrenteApiV1FrentesFrenteIdEtapasPut,
  useCrearFrenteApiV1FrentesPost,
  useListarFrentesApiV1FrentesGet,
} from '@/api/generado/proyectos/proyectos';
import type { EtapaRespuesta, FrenteRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtEntero } from '@/lib/formato';
import { puedeAdministrarObras } from './reglas';

export default function Frentes() {
  const { sesion } = useSesion();
  const [elegido, setElegido] = useState<string | null>(null);
  const [marcadas, setMarcadas] = useState<ReadonlySet<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [alta, setAlta] = useState<{ clave: string; nombre: string } | null>(null);

  const frentesQ = useListarFrentesApiV1FrentesGet<FrenteRespuesta[], ErrorApi>({
    incluir_inactivos: false,
  });
  const etapasQ = useListarEtapasApiV1EtapasGet<EtapaRespuesta[], ErrorApi>();

  const frentes = useMemo(() => frentesQ.data ?? [], [frentesQ.data]);
  const etapas = useMemo(() => etapasQ.data ?? [], [etapasQ.data]);

  const guardar = useAsignarEtapasAlFrenteApiV1FrentesFrenteIdEtapasPut<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        setAviso('Mapeo guardado');
        void etapasQ.refetch();
      },
      onError: (err) => setError(err.message),
    },
  });

  const crear = useCrearFrenteApiV1FrentesPost<ErrorApi>({
    mutation: {
      onSuccess: (nuevo) => {
        setError(null);
        setAlta(null);
        void frentesQ.refetch();
        setElegido((nuevo as FrenteRespuesta).id);
      },
      onError: (err) => setError(err.message),
    },
  });

  const frente = frentes.find((f) => f.id === elegido) ?? frentes[0] ?? null;

  // Las casillas se siembran de lo que la API dice del frente elegido. En un
  // efecto y no al vuelo porque son estado editable: el usuario marca y
  // desmarca varias antes de guardar, y recalcularlas en cada render borraría
  // lo que lleva hecho.
  const frenteId = frente?.id ?? null;
  useEffect(() => {
    if (frenteId === null) return;
    setMarcadas(new Set(etapas.filter((e) => e.frente_id === frenteId).map((e) => e.id)));
    setAviso(null);
  }, [frenteId, etapas]);

  if (!sesion) return null;
  const administra = puedeAdministrarObras(sesion.rol);

  function alternar(etapaId: string): void {
    setMarcadas((previas) => {
      const siguiente = new Set(previas);
      if (!siguiente.delete(etapaId)) siguiente.add(etapaId);
      return siguiente;
    });
    setAviso(null);
  }

  const nombrePorFrente = new Map(frentes.map((f) => [f.id, f.clave]));

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Catálogo</div>
          <h1 className="page__title">Frentes de obra</h1>
          <div className="page__subtitle">
            Un frente agrupa varias etapas constructivas —Instalaciones cubre
            hidráulica, sanitaria, eléctrica y gas— y de ahí sale con qué
            contratista y cuántas cuadrillas se planea cada obra (§8.3).
          </div>
        </div>
        {administra && (
          <div className="page__actions">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setAlta({ clave: '', nombre: '' })}
            >
              Nuevo frente
            </button>
          </div>
        )}
      </div>

      {error && <ErrorBanner mensaje={error} />}
      {frentesQ.error && <ErrorBanner mensaje={frentesQ.error.message} />}
      {etapasQ.error && <ErrorBanner mensaje={etapasQ.error.message} />}

      {alta !== null && (
        <div className="card mb-8">
          <div className="card__body row gap-8" style={{ alignItems: 'flex-end' }}>
            <div className="field" style={{ maxWidth: 120 }}>
              <label className="field__label" htmlFor="alta-clave">
                Clave
              </label>
              <input
                id="alta-clave"
                className="input mono"
                value={alta.clave}
                onChange={(e) => setAlta({ ...alta, clave: e.target.value.toUpperCase() })}
              />
            </div>
            <div className="field" style={{ minWidth: 220 }}>
              <label className="field__label" htmlFor="alta-nombre">
                Nombre
              </label>
              <input
                id="alta-nombre"
                className="input"
                value={alta.nombre}
                onChange={(e) => setAlta({ ...alta, nombre: e.target.value })}
              />
            </div>
            <button
              type="button"
              className="btn btn--primary"
              disabled={alta.clave === '' || alta.nombre === '' || crear.isPending}
              onClick={() =>
                crear.mutate({
                  data: { clave: alta.clave, nombre: alta.nombre, orden: frentes.length + 1 },
                })
              }
            >
              {crear.isPending ? 'Guardando…' : 'Crear'}
            </button>
            <button type="button" className="btn" onClick={() => setAlta(null)}>
              Cancelar
            </button>
          </div>
        </div>
      )}

      <div className="split">
        <div className="split__list">
          <div className="list">
            {frentesQ.isLoading ? (
              <div className="text-mute text-sm" style={{ padding: 16 }}>
                Cargando…
              </div>
            ) : frentes.length === 0 ? (
              <div className="empty">
                <div className="empty-title">Sin frentes</div>
                <div className="empty-sub">
                  Da de alta el primero: es lo que agrupa las etapas para poder
                  planear por frente.
                </div>
              </div>
            ) : (
              frentes.map((f) => {
                const cuantas = etapas.filter((e) => e.frente_id === f.id).length;
                return (
                  <button
                    key={f.id}
                    type="button"
                    className={`list__item ${frente?.id === f.id ? 'is-active' : ''}`}
                    onClick={() => setElegido(f.id)}
                  >
                    <div className="col gap-2" style={{ alignItems: 'flex-start' }}>
                      <span className="is-key">
                        <span className="mono">{f.clave}</span> · {f.nombre}
                      </span>
                      <span className="text-mute text-xs">
                        {cuantas === 0
                          ? 'sin etapas'
                          : `${fmtEntero(cuantas)} etapa(s)`}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        <div className="split__detail">
          {frente === null ? (
            <div className="empty">
              <div className="empty-title">Elige un frente</div>
            </div>
          ) : (
            <div className="card">
              <div className="card__header">
                <div className="col gap-2" style={{ alignItems: 'flex-start' }}>
                  <h2 className="card__title">{frente.nombre}</h2>
                  <div className="text-mute text-xs">
                    Marca las etapas constructivas que lo componen. Una etapa
                    pertenece a un solo frente: marcarla aquí la quita del que
                    tuviera.
                  </div>
                </div>
                {administra && (
                  <button
                    type="button"
                    className="btn btn--primary"
                    disabled={guardar.isPending}
                    onClick={() =>
                      guardar.mutate({
                        frenteId: frente.id,
                        data: { etapa_ids: [...marcadas] },
                      })
                    }
                  >
                    {guardar.isPending ? 'Guardando…' : 'Guardar mapeo'}
                  </button>
                )}
              </div>
              <div className="card__body col gap-4">
                {aviso && <span className="badge badge--ok">{aviso}</span>}
                {etapasQ.isLoading ? (
                  <div className="text-mute text-sm">Cargando etapas…</div>
                ) : (
                  etapas.map((etapa) => {
                    const marcada = marcadas.has(etapa.id);
                    const otro =
                      etapa.frente_id !== null &&
                      etapa.frente_id !== undefined &&
                      etapa.frente_id !== frente.id;
                    return (
                      <label
                        key={etapa.id}
                        className="row gap-8"
                        style={{ alignItems: 'center', cursor: administra ? 'pointer' : 'default' }}
                      >
                        <input
                          type="checkbox"
                          checked={marcada}
                          disabled={!administra}
                          onChange={() => alternar(etapa.id)}
                        />
                        <span className="mono text-xs" style={{ minWidth: 96 }}>
                          {etapa.clave}
                        </span>
                        <span className="text-sm" style={{ flex: 1 }}>
                          {etapa.descripcion}
                        </span>
                        {/* Se avisa antes de guardar, no después: al marcarla
                            se la va a quitar a otro frente, y eso conviene
                            verlo mientras se decide. */}
                        {otro && !marcada && (
                          <span className="badge badge--outline">
                            {nombrePorFrente.get(etapa.frente_id ?? '') ?? '—'}
                          </span>
                        )}
                        {otro && marcada && (
                          <span className="badge badge--warn">
                            se la quitas a {nombrePorFrente.get(etapa.frente_id ?? '') ?? '—'}
                          </span>
                        )}
                      </label>
                    );
                  })
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
