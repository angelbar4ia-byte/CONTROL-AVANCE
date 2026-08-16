/**
 * Frentes de obra — `GET /api/v1/frentes` (§11.2, todos los roles).
 *
 * Catálogo base del §8.3 (`PRE` Preliminares · `CIM` Cimentación · `EST`
 * Estructura · `ALB` Albañilería · `HID` Hidrosanitaria · `ELE` Eléctrica ·
 * `ACA` Acabados · `HER` Herrería/carpintería). Es la pantalla "Frentes de
 * obra" del Residente (§5.1) y alimenta filtros y Gantt del resto.
 *
 * Solo lectura: el catálogo es semilla editable (§8.7) y su edición todavía
 * no está en el contrato.
 */

import { useState } from 'react';

import { useListarFrentesApiV1FrentesGet } from '@/api/generado/proyectos/proyectos';
import type { FrenteRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';

export default function Frentes() {
  const [incluirInactivos, setIncluirInactivos] = useState(false);

  const consulta = useListarFrentesApiV1FrentesGet<FrenteRespuesta[], ErrorApi>({
    incluir_inactivos: incluirInactivos,
  });

  const filas = consulta.data ?? [];

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Catálogo</div>
          <h1 className="page__title">Frentes de obra</h1>
          <div className="page__subtitle">
            Etapas/gremios del §8.3. Cada actividad cuelga de un frente.
          </div>
        </div>
      </div>

      {consulta.isError && (
        <div className="mb-8">
          <ErrorBanner mensaje={consulta.error.message} />
        </div>
      )}

      <div className="filterbar">
        <div className="row gap-4">
          <input
            id="frentes-inactivos"
            type="checkbox"
            checked={incluirInactivos}
            onChange={(e) => setIncluirInactivos(e.target.checked)}
          />
          <label className="text-sm text-soft" htmlFor="frentes-inactivos">
            Incluir frentes dados de baja (§8.7)
          </label>
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th className="is-num">Orden</th>
                <th>Clave</th>
                <th>Nombre</th>
                <th>Etapa</th>
              </tr>
            </thead>
            <tbody>
              {consulta.isLoading ? (
                <tr>
                  <td colSpan={4}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : filas.length === 0 ? (
                <tr>
                  <td colSpan={4}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      No hay frentes en el catálogo.
                    </div>
                  </td>
                </tr>
              ) : (
                filas.map((frente) => (
                  <tr key={frente.id}>
                    <td className="is-num">{frente.orden ?? '—'}</td>
                    {/* `frente.color` viene del catálogo, pero el sistema de
                        diseño prohíbe colores crudos (DESIGN_SYSTEM §5.1):
                        se usará en el Gantt, no como color de UI. */}
                    <td className="is-key">{frente.clave}</td>
                    <td>{frente.nombre}</td>
                    <td className="text-mute">{frente.etapa ?? '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
