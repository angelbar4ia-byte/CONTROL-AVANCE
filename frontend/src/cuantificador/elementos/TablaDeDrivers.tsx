/**
 * Los drivers del Paramétrico (Ola 4B): parámetros que comparten los elementos y las plantillas, con tres niveles: el valor global y
 * su modo (fijo o ajustable), el ajuste de ESTA obra (solo en los ajustables) y el valor vigente que usan los cálculos.
 *
 * Costos y Control de obra editan (Q3); los demás roles ven la tabla en solo lectura. Cambiar un driver no recalcula nada guardado
 * (Q1): los trazos que ya traen su altura la conservan; el driver da la altura de lo que nace sin ella. El servidor decide el valor
 * vigente y valida; aquí solo se manda lo tecleado y se pinta lo que responde.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getDriversDeObraApiV1ObrasObraIdDriversGetQueryKey,
  useDriversDeObraApiV1ObrasObraIdDriversGet,
  useFijarDriverDeObraApiV1ObrasObraIdDriversClavePut,
  useFijarDriverGlobalApiV1DriversClavePut,
  useQuitarDriverDeObraApiV1ObrasObraIdDriversClaveDelete,
} from '@/api/generado/parametrico/parametrico';
import type { DriverRespuesta } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';

interface Props {
  readonly obraId: string;
  readonly obraClave?: string | null;
  readonly puedeEditar: boolean;
}

const ORIGEN: Record<string, string> = { obra: 'obra', global: 'global', inicial: 'de partida' };

/** Un número que se teclea: guarda el texto y solo manda el valor al salir del campo (o con Enter) si cambió. */
function CampoDeDriver({
  etiqueta,
  valor,
  vacioPermitido,
  deshabilitado,
  marcador,
  onConfirmar,
}: {
  readonly etiqueta: string;
  readonly valor: string;
  readonly vacioPermitido?: boolean;
  readonly deshabilitado: boolean;
  readonly marcador?: string;
  readonly onConfirmar: (texto: string) => void;
}) {
  const [texto, setTexto] = useState<string | null>(null);
  const visto = texto ?? valor;
  function confirmar() {
    const limpio = (texto ?? valor).trim().replace(',', '.');
    setTexto(null);
    if (limpio === valor) return;
    if (limpio === '' && !vacioPermitido) return;
    onConfirmar(limpio);
  }
  return (
    <input
      className="input mct__driver-campo"
      aria-label={etiqueta}
      inputMode="decimal"
      disabled={deshabilitado}
      placeholder={marcador}
      value={visto}
      onChange={(e) => {
        if (/^[0-9]*[.,]?[0-9]*$/.test(e.target.value)) setTexto(e.target.value);
      }}
      onBlur={confirmar}
      onKeyDown={(e) => {
        if (e.key === 'Enter') e.currentTarget.blur();
        if (e.key === 'Escape') setTexto(null);
      }}
    />
  );
}

export function TablaDeDrivers({ obraId, obraClave, puedeEditar }: Props) {
  const consulta = useDriversDeObraApiV1ObrasObraIdDriversGet(obraId, { query: { enabled: obraId !== '' } });
  const fijarGlobal = useFijarDriverGlobalApiV1DriversClavePut<ErrorApi>();
  const fijarDeObra = useFijarDriverDeObraApiV1ObrasObraIdDriversClavePut<ErrorApi>();
  const quitarDeObra = useQuitarDriverDeObraApiV1ObrasObraIdDriversClaveDelete<ErrorApi>();
  const [error, setError] = useState<string | null>(null);

  const recargar = () => queryClient.invalidateQueries({ queryKey: getDriversDeObraApiV1ObrasObraIdDriversGetQueryKey(obraId) });
  async function intentar(accion: () => Promise<unknown>) {
    setError(null);
    try {
      await accion();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar el driver.');
    }
    await recargar();
  }

  const drivers = consulta.data ?? [];
  return (
    <section className="mct__bloque" aria-label="Drivers" data-drivers>
      <h3>Drivers</h3>
      <p className="text-mute text-xs">
        {puedeEditar
          ? 'Costos y Control de obra editan el valor global y deciden si cada driver es fijo o ajustable. En los ajustables, esta obra puede tener su propio valor.'
          : 'Solo Costos y Control de obra editan los drivers: aquí los ves en solo lectura.'}{' '}
        El valor vigente es el de la obra si el driver es ajustable y la obra lo cambió; si no, el global. Cambiar un driver no recalcula lo ya
        guardado: un trazo que ya trae su altura la conserva, y el driver da la altura de lo que nace sin ella. Las medidas de castillos y
        cadenas no son drivers: son del elemento.
      </p>
      {error && (
        <p className="mct__error" role="alert">
          {error}
        </p>
      )}
      {consulta.isLoading ? (
        <p className="text-mute text-sm">Cargando los drivers…</p>
      ) : (
        <div className="mct__tabla-caja">
          <table className="mct__tabla" aria-label="Drivers del Paramétrico">
            <thead>
              <tr>
                <th>Driver</th>
                <th>Unidad</th>
                <th>Global</th>
                <th>Modo</th>
                <th>{obraClave ? `Obra ${obraClave}` : 'Esta obra'}</th>
                <th className="n">Vigente</th>
                <th>Origen</th>
              </tr>
            </thead>
            <tbody>
              {drivers.map((d: DriverRespuesta) => {
                const ajustable = d.modo === 'ajustable';
                return (
                  <tr key={d.clave} data-driver={d.clave}>
                    <td>
                      {d.nombre}
                      {d.por_confirmar && (
                        <>
                          {' '}
                          <span className="badge badge--warn">por confirmar</span>
                        </>
                      )}
                      <div className="text-mute text-xs">{d.nota}</div>
                    </td>
                    <td>{d.unidad}</td>
                    <td>
                      <CampoDeDriver
                        etiqueta={`Valor global de ${d.nombre}`}
                        valor={d.valor_global}
                        deshabilitado={!puedeEditar}
                        onConfirmar={(t) => void intentar(() => fijarGlobal.mutateAsync({ clave: d.clave, data: { valor: t } }))}
                      />
                    </td>
                    <td>
                      <select
                        className="input"
                        aria-label={`Modo de ${d.nombre}`}
                        disabled={!puedeEditar}
                        value={d.modo}
                        onChange={(e) =>
                          void intentar(() => fijarGlobal.mutateAsync({ clave: d.clave, data: { modo: e.target.value as 'fijo' | 'ajustable' } }))
                        }
                      >
                        <option value="fijo">Fijo</option>
                        <option value="ajustable">Ajustable por obra</option>
                      </select>
                    </td>
                    <td>
                      <CampoDeDriver
                        etiqueta={`Valor de la obra para ${d.nombre}`}
                        valor={d.valor_obra ?? ''}
                        vacioPermitido
                        deshabilitado={!puedeEditar || !ajustable}
                        marcador={ajustable ? 'igual al global' : '—'}
                        onConfirmar={(t) =>
                          void intentar(() =>
                            t === ''
                              ? quitarDeObra.mutateAsync({ obraId, clave: d.clave })
                              : fijarDeObra.mutateAsync({ obraId, clave: d.clave, data: { valor: t } }),
                          )
                        }
                      />
                      {d.ajuste_ignorado && <div className="text-xs mct__aviso">El driver es fijo: el ajuste de la obra no vale.</div>}
                    </td>
                    <td className="n" data-vigente>
                      {d.valor_vigente}
                    </td>
                    <td>
                      <span className={d.origen === 'obra' ? 'badge badge--info' : 'badge badge--ok'}>{ORIGEN[d.origen] ?? d.origen}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
