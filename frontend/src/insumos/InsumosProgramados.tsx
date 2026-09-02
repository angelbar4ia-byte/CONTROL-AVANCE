/**
 * Insumos programados: qué hace falta para ejecutar, y cuándo (§7.3, §7.5).
 *
 * Contesta la pregunta con la que se compra —*"¿cuánto cemento necesito la
 * semana 22, y cuándo lo pido?"*— cruzando el cronograma con la explosión del
 * APU. La tabla la calcula el backend (`domain/insumos/programado.py`); esta
 * pantalla elige el alcance, el rango y la anticipación, y muestra lo que
 * vuelve.
 *
 * ## Los cuatro roles, cada uno con su alcance
 *
 * Un residente pregunta por una obra suya o por todas; un supervisor puede
 * además agrupar por residente; Control y el Super intendente, por supervisor.
 * RLS acota igual para todos (§12.4), así que lo que la lista de modos evita es
 * ofrecer un filtro que siempre saldría vacío. Los **importes** solo viajan a
 * Control y al Super intendente, y la columna simplemente no se dibuja para el
 * resto.
 *
 * ## La simulación por prototipo
 *
 * Antes de generar una obra ya se puede preguntar "¿qué necesito para cuarenta
 * casas de este modelo?", que es cuando se cotiza una manzana: el programa base
 * da las ventanas y el presupuesto las cantidades (§7.5). Hoy es además el
 * único modo con datos, porque el piloto todavía no genera obras.
 *
 * ## La anticipación
 *
 * "Lo requiero diez días antes" corre la necesidad hacia atrás, no la
 * actividad. El control de la barra aplica a todo; el `dias_entrega` capturado
 * en el catálogo de un insumo le gana, y el renglón lo dice.
 */

import { useMemo, useState } from 'react';

import { useInsumosProgramadosApiV1InsumosProgramadosGet } from '@/api/generado/insumos/insumos';
import { useListarPrototiposApiV1PrototiposGet } from '@/api/generado/proyectos/proyectos';
import { useListarUsuariosApiV1UsuariosGet } from '@/api/generado/usuarios/usuarios';
import type {
  InsumosProgramadosRespuesta,
  PrototipoRespuesta,
  UsuarioRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtEntero } from '@/lib/formato';
import { SelectorObra } from '@/lib/SelectorObra';
import { useEncolarReporteApiV1ReportesTipoPost } from '@/api/generado/reportes/reportes';
import type { TrabajoRespuesta } from '@/api/generado/modelo';
import { SeguimientoDeReporte } from '@/reportes/SeguimientoDeReporte';
import { TablaInsumos } from './TablaInsumos';
import {
  TIPOS_INSUMO,
  alternarTipo,
  etiquetaModo,
  etiquetaTipo,
  filtroInicial,
  listoParaConsultar,
  modosDeAlcance,
  parametrosDeConsulta,
  rangoPorDefecto,
  rangoValido,
  veImportes,
  type FiltroInsumos,
  type Granularidad,
  type ModoAlcance,
} from './reglas';

export default function InsumosProgramados() {
  const { sesion } = useSesion();
  const rol = sesion?.rol ?? 'residente';

  const [filtro, setFiltro] = useState<FiltroInsumos>(() =>
    filtroInicial(rol, new Date()),
  );
  const [abiertos, setAbiertos] = useState<ReadonlySet<string>>(new Set());
  const [reporteId, setReporteId] = useState<string | null>(null);
  const [errorReporte, setErrorReporte] = useState<string | null>(null);

  // El `.xlsx` lo arma el mismo caso de uso que la tabla, en el worker: si el
  // archivo lo generara la pantalla, el papel y la vista dirían números
  // distintos en cuanto uno de los dos cambiara (§11.2).
  const encolar = useEncolarReporteApiV1ReportesTipoPost<ErrorApi>({
    mutation: {
      onSuccess: (trabajo) => {
        setErrorReporte(null);
        setReporteId((trabajo as TrabajoRespuesta).id);
      },
      onError: (err) => setErrorReporte(err.message),
    },
  });

  const listo = listoParaConsultar(filtro);
  const parametros = useMemo(() => parametrosDeConsulta(filtro), [filtro]);

  const consulta = useInsumosProgramadosApiV1InsumosProgramadosGet<
    InsumosProgramadosRespuesta,
    ErrorApi
  >(parametros as never, { query: { enabled: listo } });

  const usuariosQ = useListarUsuariosApiV1UsuariosGet<UsuarioRespuesta[], ErrorApi>(
    undefined,
    { query: { enabled: filtro.modo === 'residente' || filtro.modo === 'supervisor' } },
  );
  const prototiposQ = useListarPrototiposApiV1PrototiposGet<
    PrototipoRespuesta[],
    ErrorApi
  >({}, { query: { enabled: filtro.modo === 'prototipo' } });

  if (!sesion) return null;

  const datos = consulta.data;
  const periodos = datos?.periodos ?? [];
  const filas = datos?.filas ?? [];
  const conSurtido = filtro.modo !== 'prototipo';
  // Los dos son opcionales en el contrato; aquí interesa el conteo, y un
  // arreglo vacío dice lo mismo que ausente: no quedó nada fuera.
  const sinProgramar = datos?.sin_programar ?? [];
  const sinExplosion = datos?.sin_explosion ?? [];

  function cambiar(cambios: Partial<FiltroInsumos>): void {
    setFiltro((previo) => ({ ...previo, ...cambios }));
  }

  function cambiarGranularidad(granularidad: Granularidad): void {
    // El rango se re-estira: doce semanas de columnas mensuales serían tres
    // columnas, y seis meses de columnas semanales serían veintiséis.
    cambiar({ granularidad, rango: rangoPorDefecto(new Date(), granularidad) });
  }

  function alternarDesglose(insumoId: string): void {
    setAbiertos((previos) => {
      const siguiente = new Set(previos);
      if (!siguiente.delete(insumoId)) siguiente.add(insumoId);
      return siguiente;
    });
  }

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Insumos</div>
          <h1 className="page__title">Insumos programados</h1>
          <div className="page__subtitle">
            Lo que el programa pide y cuándo lo pide, cruzando el cronograma con
            la explosión del APU (§7.3, §7.5). Se calcula al consultar: cambia
            el programa y cambia esta tabla.
          </div>
        </div>
        <div className="page__actions">
          <button
            type="button"
            className="btn btn--primary"
            disabled={!listo || encolar.isPending}
            title={
              listo
                ? 'Genera el archivo en segundo plano'
                : 'Elige primero el alcance y un rango válido'
            }
            onClick={() =>
              encolar.mutate({
                tipo: 'insumos-programados',
                data: parametros as never,
              })
            }
          >
            {encolar.isPending ? 'Encolando…' : 'Generar Excel'}
          </button>
        </div>
      </div>

      {consulta.error && <ErrorBanner mensaje={consulta.error.message} />}
      {errorReporte && <ErrorBanner mensaje={errorReporte} />}

      {reporteId && (
        <SeguimientoDeReporte
          reporteId={reporteId}
          titulo="Insumos programados"
          onCerrar={() => setReporteId(null)}
        />
      )}

      <div className="filterbar">
        <div className="field">
          <label className="field__label" htmlFor="modo">
            Alcance
          </label>
          <select
            id="modo"
            className="select"
            value={filtro.modo}
            onChange={(e) => cambiar({ modo: e.target.value as ModoAlcance })}
          >
            {modosDeAlcance(rol).map((modo) => (
              <option key={modo} value={modo}>
                {etiquetaModo(modo)}
              </option>
            ))}
          </select>
        </div>

        {filtro.modo === 'obra' && (
          <div style={{ minWidth: 260 }}>
            <SelectorObra
              id="obra"
              etiqueta="Obra"
              valor={filtro.obraId}
              onCambio={(obraId) => cambiar({ obraId })}
            />
          </div>
        )}

        {(filtro.modo === 'residente' || filtro.modo === 'supervisor') && (
          <SelectorDePersona
            modo={filtro.modo}
            usuarios={usuariosQ.data ?? []}
            valor={filtro.modo === 'residente' ? filtro.residenteId : filtro.supervisorId}
            onCambio={(id) =>
              cambiar(
                filtro.modo === 'residente' ? { residenteId: id } : { supervisorId: id },
              )
            }
          />
        )}

        {filtro.modo === 'prototipo' && (
          <>
            <div className="field" style={{ minWidth: 220 }}>
              <label className="field__label" htmlFor="prototipo">
                Prototipo
              </label>
              <select
                id="prototipo"
                className="select"
                value={filtro.prototipoId}
                onChange={(e) => cambiar({ prototipoId: e.target.value })}
              >
                <option value="">Elige un prototipo…</option>
                {(prototiposQ.data ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.clave} · {p.nombre}
                  </option>
                ))}
              </select>
            </div>
            <div className="field" style={{ maxWidth: 110 }}>
              <label className="field__label" htmlFor="casas">
                Casas
              </label>
              <input
                id="casas"
                className="input"
                type="number"
                min={1}
                value={filtro.nCasas}
                onChange={(e) => cambiar({ nCasas: Math.max(1, Number(e.target.value)) })}
              />
            </div>
          </>
        )}

        <div className="field" style={{ maxWidth: 150 }}>
          <label className="field__label" htmlFor="granularidad">
            Periodo
          </label>
          <select
            id="granularidad"
            className="select"
            value={filtro.granularidad}
            onChange={(e) => cambiarGranularidad(e.target.value as Granularidad)}
          >
            <option value="semana">Por semana</option>
            <option value="mes">Por mes</option>
          </select>
        </div>

        <div className="field" style={{ maxWidth: 160 }}>
          <label className="field__label" htmlFor="desde">
            Desde
          </label>
          <input
            id="desde"
            className="input"
            type="date"
            value={filtro.rango.desde}
            onChange={(e) =>
              cambiar({ rango: { ...filtro.rango, desde: e.target.value } })
            }
          />
        </div>
        <div className="field" style={{ maxWidth: 160 }}>
          <label className="field__label" htmlFor="hasta">
            Hasta
          </label>
          <input
            id="hasta"
            className="input"
            type="date"
            value={filtro.rango.hasta}
            onChange={(e) =>
              cambiar({ rango: { ...filtro.rango, hasta: e.target.value } })
            }
          />
        </div>

        <div className="field" style={{ maxWidth: 150 }}>
          <label className="field__label" htmlFor="anticipacion">
            Pedir con
          </label>
          <input
            id="anticipacion"
            className="input"
            type="number"
            min={0}
            value={filtro.diasAnticipacion}
            aria-describedby="anticipacion-ayuda"
            onChange={(e) =>
              cambiar({ diasAnticipacion: Math.max(0, Number(e.target.value)) })
            }
          />
          <span id="anticipacion-ayuda" className="field__hint">
            días de anticipación
          </span>
        </div>
      </div>

      <div className="row gap-8" style={{ padding: '0 0 12px', flexWrap: 'wrap' }}>
        {TIPOS_INSUMO.map((tipo) => {
          const activo = filtro.tipos.includes(tipo);
          return (
            <button
              key={tipo}
              type="button"
              className={`chip${activo ? ' is-active' : ''}`}
              aria-pressed={activo}
              onClick={() => cambiar({ tipos: alternarTipo(filtro.tipos, tipo) })}
            >
              {etiquetaTipo(tipo)}
            </button>
          );
        })}
        <span className="text-mute text-xs" style={{ alignSelf: 'center' }}>
          {filtro.tipos.length === 0 ? 'Los cuatro tipos' : 'Solo lo marcado'}
        </span>
      </div>

      {!rangoValido(filtro.rango) ? (
        <div className="empty">
          <div className="empty-title">El rango está al revés</div>
          <div className="empty-sub">La fecha de inicio va antes que la de fin.</div>
        </div>
      ) : !listo ? (
        <div className="empty">
          <div className="empty-title">Elige {etiquetaModo(filtro.modo).toLowerCase()}</div>
          <div className="empty-sub">
            Sin eso la consulta traería todo lo que alcanzas, que casi nunca es
            lo que se está preguntando.
          </div>
        </div>
      ) : consulta.isLoading ? (
        <div className="text-mute text-sm" style={{ padding: 24 }}>
          Calculando…
        </div>
      ) : filas.length === 0 ? (
        <div className="empty">
          <div className="empty-title">Nada programado en este rango</div>
          <div className="empty-sub">
            {sinProgramar.length > 0
              ? `Hay ${fmtEntero(sinProgramar.length)} actividad(es) sin calendarizar: la obra se generó pero todavía no se corre su programa.`
              : 'Ni el cronograma ni el APU tienen nada que aportar en estas fechas.'}
          </div>
        </div>
      ) : (
        <>
          <TablaInsumos
            periodos={periodos}
            filas={filas}
            abiertos={abiertos}
            onAlternar={alternarDesglose}
            conImportes={veImportes(rol)}
            conSurtido={conSurtido}
          />
          <div className="field__hint mt-8">
            {fmtEntero(filas.length)} insumo(s) en {fmtEntero(periodos.length)}{' '}
            periodo(s). Las cifras las calcula el backend a partir del programa y
            del APU vigente; esta pantalla no las recalcula.
            {sinExplosion.length > 0 &&
              ` ${fmtEntero(sinExplosion.length)} actividad(es) sin APU que explotar (extra-catálogo, §7.6).`}
            {sinProgramar.length > 0 &&
              ` ${fmtEntero(sinProgramar.length)} sin calendarizar.`}
          </div>
        </>
      )}
    </div>
  );
}

function SelectorDePersona({
  modo,
  usuarios,
  valor,
  onCambio,
}: {
  readonly modo: 'residente' | 'supervisor';
  readonly usuarios: readonly UsuarioRespuesta[];
  readonly valor: string;
  readonly onCambio: (id: string) => void;
}) {
  const candidatos = usuarios.filter(
    (u) => u.rol === modo && u.estatus === 'activo',
  );
  return (
    <div className="field" style={{ minWidth: 240 }}>
      <label className="field__label" htmlFor={`sel-${modo}`}>
        {modo === 'residente' ? 'Residente' : 'Supervisor'}
      </label>
      <select
        id={`sel-${modo}`}
        className="select"
        value={valor}
        onChange={(e) => onCambio(e.target.value)}
      >
        <option value="">
          {modo === 'residente' ? 'Elige un residente…' : 'Elige un supervisor…'}
        </option>
        {candidatos.map((u) => (
          <option key={u.id} value={u.id}>
            {u.nombre}
          </option>
        ))}
      </select>
      {candidatos.length === 0 && (
        <span className="field__hint">
          No hay {modo === 'residente' ? 'residentes' : 'supervisores'} en tu
          alcance (§4).
        </span>
      )}
    </div>
  );
}
