/**
 * Bitácora de ediciones manuales del programa (0067): quién cambió qué, con qué
 * rol y cómo estaba. No se edita ni se borra.
 *
 * Trae solo lo que esa persona pidió cambiar: el recálculo de la ruta crítica
 * reescribe fechas y holguras de toda la obra en cada edición y eso no es una
 * edición de nadie, así que no sale aquí.
 */

import { useListarEdicionesDelProgramaApiV1ObrasObraIdProgramaEdicionesGet } from '@/api/generado/programacion/programacion';
import type { EdicionDeProgramaRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { etiquetaRol } from '@/equipo/reglas';
import { fmtFecha } from '@/lib/formato';

const ROTULO_CAMPO: Readonly<Record<string, string>> = {
  duracion_dias: 'Duración (días)',
  dependencias: 'Dependencias',
  tramos: 'Tramos',
  frente_id: 'Frente',
  inicio_dias: 'Ancla de inicio (días)',
  fecha_inicio: 'Inicio',
  fecha_termino: 'Término',
};

const ROTULO_TIPO: Readonly<Record<string, string>> = {
  estructura: 'Estructura',
  fechas: 'Fechas',
  mixta: 'Estructura y fechas',
};

/** Un valor de la bitácora en una línea legible. */
export function valorDeBitacora(campo: string, valor: unknown): string {
  if (valor === null || valor === undefined || valor === '') return '—';
  if (campo === 'fecha_inicio' || campo === 'fecha_termino') return fmtFecha(String(valor));
  if (Array.isArray(valor)) return valor.length === 0 ? 'ninguna' : `${valor.length}`;
  return String(valor);
}

function Cambios({ edicion }: { readonly edicion: EdicionDeProgramaRespuesta }) {
  return (
    <ul className="col gap-4" style={{ margin: 0, paddingLeft: 16 }}>
      {Object.keys(edicion.despues).map((campo) => (
        <li key={campo} className="text-sm">
          <span className="text-mute">{ROTULO_CAMPO[campo] ?? campo}: </span>
          <span className="mono tnum">{valorDeBitacora(campo, edicion.antes[campo])}</span>
          {' → '}
          <span className="mono tnum">{valorDeBitacora(campo, edicion.despues[campo])}</span>
        </li>
      ))}
    </ul>
  );
}

export function BitacoraDelPrograma({ obraId }: { readonly obraId: string }) {
  const consulta = useListarEdicionesDelProgramaApiV1ObrasObraIdProgramaEdicionesGet<
    EdicionDeProgramaRespuesta[],
    ErrorApi
  >(obraId, { query: { enabled: obraId !== '' } });

  const ediciones = consulta.data ?? [];

  return (
    <section className="card mt-16" aria-label="Bitácora del programa">
      <div className="card__header">
        <div>
          <h2 className="card__title">Bitácora del programa</h2>
          <div className="card__sub">
            Cada edición manual queda aquí con quién la hizo y cómo estaba antes. No se borra.
          </div>
        </div>
      </div>
      <div className="card__body">
        {ediciones.length === 0 ? (
          <div className="text-mute text-sm">Todavía nadie ha editado el programa de esta obra.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Quién</th>
                <th>Actividad</th>
                <th>Tipo</th>
                <th>Cambio</th>
              </tr>
            </thead>
            <tbody>
              {ediciones.slice(0, 20).map((e) => (
                <tr key={e.id}>
                  <td className="mono tnum">{fmtFecha(e.creada_en)}</td>
                  <td>
                    {e.usuario_nombre ?? '—'}
                    <div className="text-mute text-xs">{etiquetaRol(e.rol)}</div>
                  </td>
                  <td>
                    {e.actividad ?? '—'}
                    {e.concepto_clave && (
                      <div className="text-mute text-xs mono">{e.concepto_clave}</div>
                    )}
                  </td>
                  <td>
                    <span className="badge badge--outline">{ROTULO_TIPO[e.tipo] ?? e.tipo}</span>
                  </td>
                  <td>
                    <Cambios edicion={e} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
