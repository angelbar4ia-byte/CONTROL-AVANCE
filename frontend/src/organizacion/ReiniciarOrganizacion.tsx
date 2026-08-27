/**
 * Reinicio de organización — `POST /organizacion/reiniciar` (§5.1).
 *
 * Pantalla dedicada, no una casilla dentro de Catálogos o Cargas: mezclar
 * un botón así de destructivo en una pantalla de uso diario sube el riesgo
 * de un clic accidental. Confirmación simple —una fila de "Sí, reiniciar
 * TODO" / "Cancelar", mismo patrón que borrar una carga
 * (`cargas/PanelCarga.tsx`)—, sin vista previa ni deshacer: se pidió así.
 */

import { useState } from 'react';

import { useReiniciarOrganizacionApiV1OrganizacionReiniciarPost } from '@/api/generado/organizacion/organizacion';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';

export default function ReiniciarOrganizacion() {
  const [confirmando, setConfirmando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resumen, setResumen] = useState<Record<string, number> | null>(null);

  const reiniciar = useReiniciarOrganizacionApiV1OrganizacionReiniciarPost<ErrorApi>({
    mutation: {
      onError: (err) => setError(err.message),
      onSuccess: (datos) => {
        setResumen(datos);
        setConfirmando(false);
      },
    },
  });

  function confirmar() {
    setError(null);
    reiniciar.mutate();
  }

  const filas = resumen
    ? Object.entries(resumen).sort(([, a], [, b]) => b - a)
    : null;

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Configuración</div>
          <h1 className="page__title">Reiniciar organización</h1>
          <div className="page__subtitle">
            Borra catálogos, proyectos, prototipos, presupuestos,
            programación, avance, cargas e incidencias — toda la operación
            de tu organización. Las cuentas de usuario no se tocan.
          </div>
        </div>
      </div>

      {error && <ErrorBanner mensaje={error} />}

      <div className="card mb-8">
        <div className="card__header">
          <h2 className="card__title">Borrado profundo</h2>
        </div>
        <div className="card__body col gap-12">
          <div className="field">
            <div className="field__label">Esto no se puede deshacer</div>
            <div className="field__hint">
              Se borra TODO: catálogos (unidades, familias, materiales, mano
              de obra, subcontratos, conceptos, cuadrillas), proyectos,
              prototipos, presupuestos, programación, avance, cargas y sus
              pendientes, incidencias, cierres, evaluaciones — todo lo
              operativo de esta organización. Solo se conservan las cuentas
              de usuario.
            </div>

            {confirmando ? (
              <div className="row gap-8" style={{ marginTop: 8 }}>
                <button
                  type="button"
                  className="btn btn--sm btn--danger"
                  disabled={reiniciar.isPending}
                  onClick={confirmar}
                >
                  {reiniciar.isPending ? 'Reiniciando…' : 'Sí, reiniciar TODO'}
                </button>
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={reiniciar.isPending}
                  onClick={() => setConfirmando(false)}
                >
                  Cancelar
                </button>
              </div>
            ) : (
              <button
                type="button"
                className="btn btn--sm btn--danger"
                style={{ alignSelf: 'flex-start', marginTop: 8 }}
                onClick={() => setConfirmando(true)}
              >
                Reiniciar organización
              </button>
            )}
          </div>
        </div>
      </div>

      {filas && (
        <div className="card">
          <div className="card__header">
            <h2 className="card__title">Se borró</h2>
            <div className="text-mute text-xs">
              {filas.reduce((total, [, cantidad]) => total + cantidad, 0)} filas
              en {filas.length} tablas
            </div>
          </div>
          <div className="card__body">
            <table className="table">
              <tbody>
                {filas.map(([tabla, cantidad]) => (
                  <tr key={tabla}>
                    <td className="mono text-sm">{tabla}</td>
                    <td className="is-num">{cantidad}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
