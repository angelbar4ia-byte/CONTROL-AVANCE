/**
 * Lo que la junta de arranque tiene a la vista y las alertas de ritmo de las partes
 * (migración 0079; cerebro D-574, D-575, D-577).
 *
 *  - «Todo validado» es un requisito de la junta: avisa, no impide nada. Lo que impide es
 *    **asignar**, con el candado, que Control pone o quita **por obra**.
 *  - El presupuesto debe ir por delante del programa: una parte sin autorizar que el programa
 *    necesita pronto avisa (2 semanas) o es importante (1 semana). Avisa; no bloquea. Los
 *    umbrales son globales y los edita Control.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getAlertasDePartesApiV1ObrasObraIdPartesAlertasGetQueryKey,
  getArranqueDeLaObraApiV1ObrasObraIdArranqueGetQueryKey,
  getDesfaseDePartesApiV1ConfiguracionDesfaseDePartesGetQueryKey,
  useAlertasDePartesApiV1ObrasObraIdPartesAlertasGet,
  useArranqueDeLaObraApiV1ObrasObraIdArranqueGet,
  useDesfaseDePartesApiV1ConfiguracionDesfaseDePartesGet,
  useFijarCandadoDeAsignarApiV1ObrasObraIdCandadoAsignarPut,
  useFijarDesfaseDePartesApiV1ConfiguracionDesfaseDePartesPut,
} from '@/api/generado/partes/partes';
import { queryClient } from '@/app/queryClient';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtFecha } from '@/lib/formato';
import type { Rol } from '@/shell/navegacion';
import { ETIQUETA_SEVERIDAD, etiquetaDeDias, etiquetaDeEstado, puedeConfigurar } from './reglas';

export default function ArranqueYAlertas({ obraId, rol }: { obraId: string; rol: Rol }) {
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState('');
  const [importante, setImportante] = useState('');
  const configura = puedeConfigurar(rol);

  const arranque = useArranqueDeLaObraApiV1ObrasObraIdArranqueGet(obraId, { query: { enabled: obraId !== '' } });
  const alertas = useAlertasDePartesApiV1ObrasObraIdPartesAlertasGet(obraId, {
    query: { enabled: obraId !== '' },
  });
  const desfase = useDesfaseDePartesApiV1ConfiguracionDesfaseDePartesGet();

  const candado = useFijarCandadoDeAsignarApiV1ObrasObraIdCandadoAsignarPut<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        void queryClient.invalidateQueries({
          queryKey: getArranqueDeLaObraApiV1ObrasObraIdArranqueGetQueryKey(obraId),
        });
      },
      onError: (e) => setError(e.message),
    },
  });
  const umbrales = useFijarDesfaseDePartesApiV1ConfiguracionDesfaseDePartesPut<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        setAviso('');
        setImportante('');
        void queryClient.invalidateQueries({
          queryKey: getDesfaseDePartesApiV1ConfiguracionDesfaseDePartesGetQueryKey(),
        });
        void queryClient.invalidateQueries({
          queryKey: getAlertasDePartesApiV1ObrasObraIdPartesAlertasGetQueryKey(obraId),
        });
      },
      onError: (e) => setError(e.message),
    },
  });

  const a = arranque.data;
  const lista = alertas.data?.alertas ?? [];
  const aviso0 = String(desfase.data?.aviso_dias ?? '');
  const importante0 = String(desfase.data?.importante_dias ?? '');

  return (
    <section aria-label="Arranque y alertas" className="mb-8">
      {error && <ErrorBanner mensaje={error} />}

      {a && (
        <div className="row gap-8 mb-8" style={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <span className={`badge badge--${a.todo_validado ? 'ok' : 'warn'}`}>
            {a.todo_validado ? 'Todo validado' : `Falta validar ${a.sin_autorizar.length} de ${a.total}`}
          </span>
          {a.programas_por_revisar > 0 && (
            <span className="badge badge--warn">
              {a.programas_por_revisar} {a.programas_por_revisar === 1 ? 'programa por revisar' : 'programas por revisar'}
            </span>
          )}
          {configura ? (
            <label className="text-sm row gap-4" style={{ alignItems: 'center' }}>
              <input
                type="checkbox"
                checked={a.candado_asignar}
                disabled={candado.isPending}
                onChange={(e) => candado.mutate({ obraId, data: { activo: e.target.checked } })}
              />
              Candado de asignar
            </label>
          ) : (
            <span className="badge badge--outline">
              {a.candado_asignar ? 'Con candado de asignar' : 'Sin candado de asignar'}
            </span>
          )}
        </div>
      )}
      {a?.candado_asignar && (
        <div className="text-xs text-mute mb-8">
          Con el candado, quien valida una parte deja una anotación y no se asigna sin ella.
        </div>
      )}

      {lista.length > 0 && (
        <ul aria-label="Alertas de desfase" className="text-sm" style={{ margin: '0 0 8px', padding: 0, listStyle: 'none' }}>
          {lista.map((x) => (
            <li key={x.clave} role="alert">
              <span className={`badge badge--${x.severidad === 'importante' ? 'danger' : 'warn'}`}>
                {ETIQUETA_SEVERIDAD[x.severidad] ?? x.severidad}
              </span>{' '}
              <strong>{x.nombre}</strong> sin autorizar ({etiquetaDeEstado(x.estado)}): el programa la necesita{' '}
              {etiquetaDeDias(x.dias)} ({fmtFecha(x.inicio)}).
            </li>
          ))}
        </ul>
      )}

      {configura && desfase.data && (
        <details>
          <summary className="text-sm">Umbrales de la alerta (afectan a todas las obras)</summary>
          <form
            className="row gap-8"
            style={{ alignItems: 'flex-end', margin: '8px 0', flexWrap: 'wrap' }}
            onSubmit={(e) => {
              e.preventDefault();
              umbrales.mutate({
                data: {
                  aviso_dias: Number(aviso || aviso0),
                  importante_dias: Number(importante || importante0),
                },
              });
            }}
          >
            <div className="field">
              <label className="field__label" htmlFor="desfase-aviso">
                Aviso (días antes)
              </label>
              <input
                id="desfase-aviso"
                className="input"
                type="number"
                min={0}
                value={aviso || aviso0}
                onChange={(e) => setAviso(e.target.value)}
              />
            </div>
            <div className="field">
              <label className="field__label" htmlFor="desfase-importante">
                Importante (días antes)
              </label>
              <input
                id="desfase-importante"
                className="input"
                type="number"
                min={0}
                value={importante || importante0}
                onChange={(e) => setImportante(e.target.value)}
              />
            </div>
            <button type="submit" className="btn btn--sm" disabled={umbrales.isPending}>
              Guardar umbrales
            </button>
          </form>
        </details>
      )}
    </section>
  );
}
