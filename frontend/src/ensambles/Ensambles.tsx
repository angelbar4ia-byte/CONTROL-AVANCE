/**
 * Ensambles paramétricos — catálogo, Extracción y Generación (skill
 * `erp-parametrico`, §11.2).
 *
 * "El mismo mecanismo del APU, un piso más arriba" (§0): un concepto se arma de
 * insumos con cantidad; un ensamble se arma de conceptos —o de otros
 * ensambles— con cantidad. Es la **plantilla** ("Recámara tipo A"): no se
 * contrata ni se programa, eso lo sigue haciendo cada concepto real una vez
 * que el ensamble se genera dentro de un presupuesto (§1).
 *
 * Leer el catálogo es de Control de obra y Super intendente; crear (Extracción)
 * y generar son solo de Control de obra (§11.2). Esta pantalla **muestra** lo
 * que calcula el backend y no recompone ni un costo.
 */

import { useState } from 'react';

import { useListarEnsamblesApiV1EnsamblesGet } from '@/api/generado/ensambles/ensambles';
import type { EnsambleCreadoRespuesta, EnsambleRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtMXN, fmtNum } from '@/lib/formato';
import { ExtraerEnsamble } from './ExtraerEnsamble';
import { PanelEnsamble } from './PanelEnsamble';
import { puedeConsultarEnsambles, puedeEscribirEnsambles, tasaPublicada } from './reglas';

export default function Ensambles() {
  const { sesion } = useSesion();
  const rol = sesion?.rol ?? null;

  const [incluirInactivos, setIncluirInactivos] = useState(false);
  const [creando, setCreando] = useState(false);
  const [abierto, setAbierto] = useState<EnsambleRespuesta | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const consulta = useListarEnsamblesApiV1EnsamblesGet<EnsambleRespuesta[], ErrorApi>(
    { incluir_inactivos: incluirInactivos },
    { query: { enabled: rol !== null && puedeConsultarEnsambles(rol) } },
  );

  if (!sesion || rol === null) return null;

  const ensambles = consulta.data ?? [];

  function alCrear(creado: EnsambleCreadoRespuesta) {
    setCreando(false);
    setAviso(`Ensamble ${creado.clave} creado con ${creado.renglones} renglones`);
    void consulta.refetch();
  }

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Configuración</div>
          <h1 className="page__title">Ensambles</h1>
          <div className="page__subtitle">
            Plantillas de presupuesto paramétrico: conceptos —u otros ensambles— con la cantidad que
            entra por una instancia completa. Se arman desde lo ya construido (Extracción) y se
            componen dentro de un presupuesto nuevo (Generación).
          </div>
        </div>
        {puedeEscribirEnsambles(rol) && (
          <div className="page__actions">
            <button type="button" className="btn btn--primary" onClick={() => setCreando(true)}>
              Nuevo ensamble
            </button>
          </div>
        )}
      </div>

      {aviso !== null && (
        <div role="status" className="mb-8">
          <span className="badge badge--ok">{aviso}</span>
        </div>
      )}
      {consulta.error && <ErrorBanner mensaje={consulta.error.message} />}

      <div className="row gap-12 mb-8">
        <label className="row gap-8 text-sm">
          <input
            type="checkbox"
            checked={incluirInactivos}
            onChange={(e) => setIncluirInactivos(e.target.checked)}
          />
          Incluir dados de baja
        </label>
        <span className="badge badge--outline tnum">{ensambles.length} ensambles</span>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Clave</th>
                <th>Nombre</th>
                <th>Divisor</th>
                <th>Tasa</th>
                <th>Dispersión</th>
                <th>Estatus</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {consulta.isLoading && (
                <tr>
                  <td colSpan={7} className="text-mute text-sm">
                    Cargando ensambles…
                  </td>
                </tr>
              )}
              {!consulta.isLoading && ensambles.length === 0 && (
                <tr>
                  <td colSpan={7} className="text-mute text-sm">
                    Todavía no hay ensambles. Arma el primero desde lo ya construido con «Nuevo
                    ensamble».
                  </td>
                </tr>
              )}
              {ensambles.map((ensamble) => (
                <tr key={ensamble.id}>
                  <td className="is-key mono">{ensamble.clave}</td>
                  <td>{ensamble.nombre}</td>
                  <td className="text-mute text-sm">{ensamble.divisor_nombre ?? '—'}</td>
                  <td className="is-num">
                    {tasaPublicada(ensamble.tasa, ensamble.dispersion)
                      ? fmtMXN(ensamble.tasa)
                      : '—'}
                  </td>
                  <td className="is-num">
                    {tasaPublicada(ensamble.tasa, ensamble.dispersion)
                      ? `${fmtNum(ensamble.dispersion)}%`
                      : '—'}
                  </td>
                  <td>
                    <span
                      className={`badge badge--${ensamble.estatus === 'activo' ? 'ok' : 'outline'}`}
                    >
                      {ensamble.estatus === 'activo' ? 'Activo' : 'De baja'}
                    </span>
                  </td>
                  <td className="cell-actions">
                    <button
                      type="button"
                      className="btn btn--sm"
                      aria-haspopup="dialog"
                      aria-label={`Abrir ${ensamble.clave}`}
                      onClick={() => setAbierto(ensamble)}
                    >
                      Abrir
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {creando && <ExtraerEnsamble onCerrar={() => setCreando(false)} onCreado={alCrear} />}
      {abierto !== null && (
        <PanelEnsamble ensamble={abierto} rol={rol} onCerrar={() => setAbierto(null)} />
      )}
    </div>
  );
}
