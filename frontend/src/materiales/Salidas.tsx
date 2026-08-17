/**
 * Salidas de almacén — bandeja y alta (§7.7, §11.2 "Materiales").
 *
 * `GET /salidas` es (C, SI) y `POST /obras/{id}/salidas` es solo (C) (§11.2,
 * §4). RLS ya acota la bandeja al alcance del usuario (§12.4); esconder el
 * botón de alta a quien no es Control de obra evita ofrecer un 403, no
 * sustituye al RBAC.
 *
 * Ruta `/materiales/salidas` (`shell/navegacion.ts`, sección "Control de
 * materiales" del sidebar de Control de obra).
 */

import { useState } from 'react';

import { useListarSalidasApiV1SalidasGet } from '@/api/generado/materiales/materiales';
import { useListarMaterialesApiV1MaterialesGet } from '@/api/generado/catalogos/catalogos';
import { useSesion } from '@/app/sesion';
import { fmtFecha, fmtMXN, fmtNum } from '@/lib/formato';
import { SelectorObra } from '@/lib/SelectorObra';
import { AltaSalida } from './AltaSalida';
import { puedeRegistrarSalida } from './reglas';

export default function Salidas() {
  const { sesion } = useSesion();
  const [obraId, setObraId] = useState('');
  const [abriendoAlta, setAbriendoAlta] = useState(false);

  const consulta = useListarSalidasApiV1SalidasGet(
    obraId === '' ? undefined : { obra_id: obraId },
  );

  const materiales = useListarMaterialesApiV1MaterialesGet();
  const porId = new Map((materiales.data ?? []).map((m) => [m.id, m]));

  if (!sesion) return null;
  const puedeAlta = puedeRegistrarSalida(sesion.rol);

  const filas = consulta.data ?? [];

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Control de materiales</div>
          <h1 className="page__title">Salidas de almacén</h1>
          <div className="page__subtitle">
            Movimientos de almacén por obra: cantidad e importe llegan{' '}
            <strong>con signo</strong> y el motivo clasifica el bucket de KPI
            (§10.5). El consumo real de la obra sale de aquí (§7.7).
          </div>
        </div>
        {puedeAlta && (
          <div className="page__actions">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setAbriendoAlta(true)}
            >
              Registrar salida
            </button>
          </div>
        )}
      </div>

      <div className="filterbar">
        <div style={{ minWidth: 260 }}>
          <SelectorObra
            id="salidas-obra"
            etiqueta="Obra"
            valor={obraId}
            onCambio={setObraId}
            vacio="Todas las obras de mi alcance"
          />
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Material</th>
                <th>Descripción</th>
                <th className="is-num">Cantidad</th>
                <th className="is-num">Costo</th>
                <th>Concepto</th>
                <th>Contratista</th>
              </tr>
            </thead>
            <tbody>
              {consulta.isLoading ? (
                <tr>
                  <td colSpan={7}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : filas.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      No hay movimientos de almacén en este filtro.
                    </div>
                  </td>
                </tr>
              ) : (
                filas.map((salida) => {
                  const material = porId.get(salida.insumo_id);
                  return (
                    <tr key={salida.id}>
                      <td>{fmtFecha(salida.fecha)}</td>
                      <td className="is-key" title={salida.insumo_id}>
                        {material?.clave ?? salida.insumo_id.slice(0, 8)}
                      </td>
                      <td>{material?.descripcion ?? '—'}</td>
                      <td className="is-num">{fmtNum(salida.cantidad)}</td>
                      <td className="is-num">{fmtMXN(salida.costo)}</td>
                      <td className="is-key">{salida.concepto_id?.slice(0, 8) ?? '—'}</td>
                      <td className="is-key">{salida.contratista_id?.slice(0, 8) ?? '—'}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {abriendoAlta && (
        <AltaSalida
          obraIdInicial={obraId}
          onCerrar={() => setAbriendoAlta(false)}
          onRegistrada={() => {
            setAbriendoAlta(false);
            void consulta.refetch();
          }}
        />
      )}
    </div>
  );
}
