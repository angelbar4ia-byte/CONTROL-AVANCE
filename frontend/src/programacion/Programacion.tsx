/**
 * Programación · CPM — Gantt del cronograma de una obra con la ruta crítica
 * resaltada (§5.3, §6, §7.5, §11.2 bloque "Programación · CPM").
 *
 * Pantalla **compartida** (§5.3): se implementa una vez y cambia por rol y
 * alcance. El alcance no se filtra aquí — lo impone RLS en el servidor
 * (§12.4). Se monta en las rutas que los sidebars ya apuntan (§5.1):
 *
 *   - `/ruta-critica` — "Mi ruta crítica" (R) y "Ruta crítica" (S, C, SI).
 *   - `/programas` — "Programas de obra", en Reportes del Super intendente.
 *
 * ## De dónde salen los datos
 *
 * `GET /obras/{id}/ruta-critica` es de **todos los roles** y trae la
 * actividad con su cálculo del motor CPM: fechas tempranas y tardías,
 * `holgura`, `desfase` y `es_critica`. `GET /obras/{id}/programa` es (C, S) y
 * añade la programación capturada, el frente, la etapa y el historial de
 * versiones. `filas.ts` fusiona las dos vistas en una sola fila de Gantt.
 *
 * **Cero cálculo de CPM en el cliente** (§12.11): la pantalla pinta lo que el
 * backend ya resolvió y, cuando algo cambia, vuelve a pedirlo. El único
 * "cálculo" local es la aritmética de lienzo de `escala.ts`, que convierte
 * fechas a porcentajes.
 */

import { useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';

import {
  getListarEdicionesDelProgramaApiV1ObrasObraIdProgramaEdicionesGetQueryKey,
  useObtenerArbolDelProgramaApiV1ObrasObraIdProgramaArbolGet,
  useObtenerProgramaDeObraApiV1ObrasObraIdProgramaGet,
  useObtenerRutaCriticaApiV1ObrasObraIdRutaCriticaGet,
  useRecalcularRutaCriticaApiV1ObrasObraIdRutaCriticaRecalcularPost,
} from '@/api/generado/programacion/programacion';
import { useListarObrasApiV1ObrasGet } from '@/api/generado/obras/obras';
import { useListarFrentesApiV1FrentesGet } from '@/api/generado/proyectos/proyectos';
import type {
  ArbolDeProgramaRespuesta,
  FrenteRespuesta,
  ObraRespuesta,
  ProgramaObraRespuesta,
  RutaCriticaRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtEntero, fmtFecha } from '@/lib/formato';
import type { Rol } from '@/shell/navegacion';
import { construirEscala } from './escala';
import { agruparPorFrente, construirFilas, filtrarPorTexto, resumirPrograma, soloCriticas } from './filas';
import { BitacoraDelPrograma } from './BitacoraDelPrograma';
import { Gantt } from './Gantt';
import { InstanciarPrograma } from './InstanciarPrograma';
import {
  alternarColapso,
  colapsadosPorDefecto,
  construirFilasJerarquia,
  filtrarJerarquiaPorTexto,
  resumirJerarquia,
  visiblesEnJerarquia,
  type FilaJerarquia,
} from './jerarquia';
import { PanelActividad } from './PanelActividad';
import { ProgramarNodo } from './ProgramarNodo';
import { alcanceDeEdicion, puedeEditarProgramacion, puedeVerCronograma } from './reglas';

const ENCABEZADO: Record<Rol, { readonly eyebrow: string; readonly titulo: string }> = {
  residente: { eyebrow: 'Mi trabajo', titulo: 'Mi ruta crítica' },
  supervisor: { eyebrow: 'Control supervisión', titulo: 'Ruta crítica' },
  control_obra: { eyebrow: 'Control de obra', titulo: 'Ruta crítica' },
  super_intendente: { eyebrow: 'Control general', titulo: 'Ruta crítica' },
  costos: { eyebrow: 'Presupuesto', titulo: 'Ruta crítica' },
};

export default function Programacion() {
  const { sesion } = useSesion();
  const { pathname } = useLocation();
  const queryClient = useQueryClient();
  const rol = sesion?.rol ?? null;
  const verCronograma = rol !== null && puedeVerCronograma(rol);
  const edita = rol !== null && puedeEditarProgramacion(rol);
  const alcance = rol !== null ? alcanceDeEdicion(rol) : 'lectura';

  const [obraElegida, setObraElegida] = useState('');
  const [fechaCorte, setFechaCorte] = useState('');
  const [texto, setTexto] = useState('');
  const [soloRutaCritica, setSoloRutaCritica] = useState(false);
  const [abierta, setAbierta] = useState<string | null>(null);
  const [instanciando, setInstanciando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  // El Gantt se mira de dos maneras: por frente —lo que se lleva al campo— o
  // como el árbol WBS, con las barras resumen de nivel y etapa (§7.4). Son dos
  // lecturas del mismo cronograma, así que es un interruptor y no dos pantallas.
  const [vistaArbol, setVistaArbol] = useState(false);
  // `null` = todavía no se aplicó el default que guarda el programa base
  // (0041). Se distingue del conjunto vacío para no volver a colapsar lo que el
  // usuario acaba de expandir cada vez que la consulta se revalida.
  const [colapsados, setColapsados] = useState<ReadonlySet<string> | null>(null);
  const [nodoAProgramar, setNodoAProgramar] = useState<FilaJerarquia | null>(null);

  const obrasQ = useListarObrasApiV1ObrasGet<ObraRespuesta[], ErrorApi>({});
  const frentesQ = useListarFrentesApiV1FrentesGet<FrenteRespuesta[], ErrorApi>({});

  const obras = useMemo(() => obrasQ.data ?? [], [obrasQ.data]);
  // La primera obra del alcance es el valor por defecto: sin selección la
  // pantalla no tendría nada que pintar, y RLS ya acotó la lista (§12.4).
  const obraId = obraElegida !== '' ? obraElegida : (obras[0]?.id ?? '');
  const obra = obras.find((candidata) => candidata.id === obraId) ?? null;

  const corte = fechaCorte.trim() === '' ? undefined : fechaCorte;

  const rutaQ = useObtenerRutaCriticaApiV1ObrasObraIdRutaCriticaGet<
    RutaCriticaRespuesta,
    ErrorApi
  >(obraId, { fecha_corte: corte }, { query: { enabled: obraId !== '' } });

  const programaQ = useObtenerProgramaDeObraApiV1ObrasObraIdProgramaGet<
    ProgramaObraRespuesta,
    ErrorApi
  >(obraId, { query: { enabled: obraId !== '' && verCronograma } });

  // El árbol WBS con sus barras resumen (§7.4). Es de **todos los roles**, como
  // la ruta crítica: el residente lee el resumen de su obra aunque no pueda
  // pedir `GET /obras/{id}/programa` (§11.2). Sólo se pide en la vista de
  // árbol: en la plana no se dibuja nada de él.
  const arbolQ = useObtenerArbolDelProgramaApiV1ObrasObraIdProgramaArbolGet<
    ArbolDeProgramaRespuesta,
    ErrorApi
  >(obraId, { fecha_corte: corte }, { query: { enabled: obraId !== '' && vistaArbol } });

  const recalcular = useRecalcularRutaCriticaApiV1ObrasObraIdRutaCriticaRecalcularPost<ErrorApi>(
    {
      mutation: {
        onSuccess: () => {
          setAviso('Ruta crítica recalculada');
          void rutaQ.refetch();
          if (verCronograma) void programaQ.refetch();
        },
        onError: () => setAviso(null),
      },
    },
  );

  const frentes = useMemo(() => frentesQ.data ?? [], [frentesQ.data]);

  const filas = useMemo(
    () => construirFilas(programaQ.data, rutaQ.data),
    [programaQ.data, rutaQ.data],
  );

  const visibles = useMemo(() => {
    const porTexto = filtrarPorTexto(filas, texto);
    return soloRutaCritica ? soloCriticas(porTexto) : porTexto;
  }, [filas, texto, soloRutaCritica]);

  const grupos = useMemo(() => agruparPorFrente(visibles, frentes), [visibles, frentes]);
  const resumen = useMemo(() => resumirPrograma(filas), [filas]);

  const nodos = useMemo(
    () => construirFilasJerarquia(arbolQ.data, filas),
    [arbolQ.data, filas],
  );
  const resumenArbol = useMemo(() => resumirJerarquia(nodos), [nodos]);

  // El default de colapso se aplica una sola vez por árbol recibido: si se
  // recalculara en cada render, cada revalidación volvería a cerrar lo que el
  // usuario acabara de abrir (0041: la profundidad es un default, no una jaula).
  const profundidadCaptura = arbolQ.data?.profundidad_captura ?? null;
  const colapsadosEfectivos = useMemo(
    () =>
      colapsados ??
      (profundidadCaptura === null
        ? new Set<string>()
        : colapsadosPorDefecto(nodos, profundidadCaptura)),
    [colapsados, nodos, profundidadCaptura],
  );

  const nodosVisibles = useMemo(
    () => visiblesEnJerarquia(filtrarJerarquiaPorTexto(nodos, texto), colapsadosEfectivos),
    [nodos, texto, colapsadosEfectivos],
  );

  const fechaCorteEfectiva = rutaQ.data?.fecha_corte ?? programaQ.data?.fecha_corte ?? null;

  const escala = useMemo(
    () =>
      construirEscala(
        (vistaArbol ? nodosVisibles : visibles).map((fila) => ({
          inicio: fila.inicio,
          fin: fila.fin,
        })),
        fechaCorteEfectiva,
      ),
    [vistaArbol, nodosVisibles, visibles, fechaCorteEfectiva],
  );

  const filaAbierta = filas.find((fila) => fila.actividadId === abierta) ?? null;

  if (!sesion || rol === null) return null;

  const encabezado = ENCABEZADO[rol];
  const esVistaProgramas = pathname.startsWith('/programas');
  const titulo = esVistaProgramas ? 'Programas de obra' : encabezado.titulo;
  const eyebrow = esVistaProgramas ? 'Reportes' : encabezado.eyebrow;

  const errores = [
    obrasQ.error,
    frentesQ.error,
    rutaQ.error,
    programaQ.error,
    arbolQ.error,
  ].filter((error): error is ErrorApi => error !== null && error !== undefined);

  function refrescar() {
    void rutaQ.refetch();
    void queryClient.invalidateQueries({
      queryKey: getListarEdicionesDelProgramaApiV1ObrasObraIdProgramaEdicionesGetQueryKey(obraId),
    });
    if (verCronograma) void programaQ.refetch();
    if (vistaArbol) void arbolQ.refetch();
  }

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">{eyebrow}</div>
          <h1 className="page__title">{titulo}</h1>
          <div className="page__subtitle">
            Cronograma de la obra con la ruta crítica resaltada. Holgura, desfase y ruta las
            calcula el motor CPM del backend (§6); esta pantalla las muestra.
          </div>
        </div>

        {edita && obra !== null && (
          <div className="page__actions">
            <button
              type="button"
              className="btn"
              onClick={() => setInstanciando(true)}
              disabled={obraId === ''}
            >
              Instanciar programa
            </button>
            <button
              type="button"
              className="btn btn--accent"
              disabled={obraId === '' || recalcular.isPending}
              onClick={() => {
                setAviso(null);
                recalcular.mutate({
                  obraId,
                  params: corte === undefined ? undefined : { fecha_corte: corte },
                });
              }}
            >
              {recalcular.isPending ? 'Recalculando…' : 'Recalcular ruta crítica'}
            </button>
          </div>
        )}
      </div>

      {recalcular.isPending && (
        <div className="mb-8" role="status">
          <span className="badge badge--info">
            Recalculando la ruta crítica de la obra; puede tardar.
          </span>
        </div>
      )}

      {aviso !== null && !recalcular.isPending && (
        <div className="mb-8" role="status">
          <span className="badge badge--ok">{aviso}</span>
        </div>
      )}

      {recalcular.isError && (
        <div className="mb-8">
          <ErrorBanner mensaje={recalcular.error.message} campo={recalcular.error.campo} />
        </div>
      )}

      {errores.map((error, indice) => (
        <div className="mb-8" key={`${error.status}-${indice}`}>
          <ErrorBanner mensaje={error.message} />
        </div>
      ))}

      <div className="filterbar">
        <select
          className="select"
          value={obraId}
          onChange={(e) => {
            setObraElegida(e.target.value);
            setAbierta(null);
            setAviso(null);
          }}
          aria-label="Obra"
        >
          {obras.length === 0 && <option value="">Sin obras en tu alcance</option>}
          {obras.map((candidata) => (
            <option key={candidata.id} value={candidata.id}>
              {candidata.clave}
            </option>
          ))}
        </select>

        <div className="field" style={{ marginBottom: 0 }}>
          <label className="field__label" htmlFor="corte">
            Fecha de corte
          </label>
          <input
            id="corte"
            className="input"
            type="date"
            value={fechaCorte}
            onChange={(e) => setFechaCorte(e.target.value)}
          />
        </div>

        <input
          className="input search"
          type="search"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Buscar actividad…"
          aria-label="Buscar actividad por descripción"
        />

        <label className="row gap-4" style={{ alignItems: 'center' }}>
          <input
            type="checkbox"
            checked={soloRutaCritica}
            disabled={vistaArbol}
            onChange={(e) => setSoloRutaCritica(e.target.checked)}
          />
          <span className="text-sm text-mute">Solo la ruta crítica</span>
        </label>

        <label className="row gap-4" style={{ alignItems: 'center' }}>
          <input
            type="checkbox"
            checked={vistaArbol}
            onChange={(e) => {
              setVistaArbol(e.target.checked);
              // El default de colapso se vuelve a aplicar al entrar: es lo que
              // hace que el equipo abra viendo la misma profundidad (0041).
              setColapsados(null);
              setAbierta(null);
            }}
          />
          <span className="text-sm text-mute">Ver como árbol WBS</span>
        </label>
      </div>

      {vistaArbol && resumenArbol.nConflictos > 0 && (
        <div className="mb-8" role="alert">
          <span className="badge badge--warn">
            {fmtEntero(resumenArbol.nConflictos)} nodo(s) en conflicto
          </span>{' '}
          <span className="text-sm text-mute">
            La ventana que declara el programa base no cuadra con lo que sus conceptos ya
            traen programado. Abre &ldquo;Programar&rdquo; en el nodo marcado y elige cuál
            cifra conservar: nadie decide por ti (§7.5).
          </span>
        </div>
      )}

      <div className="kpi-grid mb-8">
        <Kpi etiqueta="Actividades" valor={fmtEntero(resumen.nActividades)} />
        <Kpi
          etiqueta="En ruta crítica"
          valor={fmtEntero(resumen.nCriticas)}
          alerta={resumen.nCriticas > 0}
        />
        <Kpi
          etiqueta="Con desfase"
          valor={fmtEntero(resumen.nConDesfase)}
          alerta={resumen.nConDesfase > 0}
        />
        <Kpi etiqueta="Sin fechas" valor={fmtEntero(resumen.nSinFecha)} />
        <Kpi etiqueta="Fecha de corte" valor={fmtFecha(fechaCorteEfectiva)} />
        <Kpi
          etiqueta="Fin programado"
          valor={fmtFecha(rutaQ.data?.fin_programado ?? null)}
          sub={
            rutaQ.data?.version !== null && rutaQ.data?.version !== undefined
              ? `Programa v${rutaQ.data.version}`
              : 'Sin programa instanciado'
          }
        />
      </div>

      {rutaQ.isLoading || (verCronograma && programaQ.isLoading) || (vistaArbol && arbolQ.isLoading) ? (
        <div className="text-mute text-sm" style={{ padding: '24px 12px' }}>
          Cargando cronograma…
        </div>
      ) : escala === null ? (
        <div className="text-mute text-sm" style={{ padding: '24px 12px' }}>
          {filas.length === 0
            ? 'La obra no tiene actividades programadas todavía. Genera las actividades desde el prototipo y luego instancia el programa (§11.3 A).'
            : 'Ninguna actividad visible tiene fechas: instancia el programa o captura inicio y término para dibujar el Gantt (§7.5).'}
        </div>
      ) : vistaArbol ? (
        <Gantt
          jerarquia={nodosVisibles}
          escala={escala}
          fechaCorte={fechaCorteEfectiva}
          seleccionada={abierta}
          onSeleccionar={(fila) => setAbierta(fila.actividadId)}
          colapsados={colapsadosEfectivos}
          onAlternar={(nodoId) =>
            setColapsados((previos) => alternarColapso(previos ?? colapsadosEfectivos, nodoId))
          }
          // Programar un nodo resumen escribe la duración y las fechas de sus
          // conceptos, así que es el mismo permiso que el `PATCH` (§11.2).
          onProgramarNodo={edita ? setNodoAProgramar : undefined}
        />
      ) : (
        <Gantt
          grupos={grupos}
          escala={escala}
          fechaCorte={fechaCorteEfectiva}
          seleccionada={abierta}
          onSeleccionar={(fila) => setAbierta(fila.actividadId)}
        />
      )}

      {programaQ.data && programaQ.data.versiones.length > 0 && (
        <div className="text-mute text-xs mono mt-8">
          Versiones del programa: {programaQ.data.versiones.join(' · ')}
        </div>
      )}

      {obraId !== '' && <BitacoraDelPrograma obraId={obraId} />}

      {filaAbierta && (
        <PanelActividad
          key={filaAbierta.actividadId}
          fila={filaAbierta}
          actividades={filas}
          frentes={frentes}
          alcance={alcance}
          onCerrar={() => setAbierta(null)}
          onAjustada={refrescar}
        />
      )}

      {nodoAProgramar !== null && (
        <ProgramarNodo
          key={nodoAProgramar.nodoId}
          obraId={obraId}
          nodo={nodoAProgramar}
          onCerrar={() => setNodoAProgramar(null)}
          onProgramado={refrescar}
        />
      )}

      {instanciando && obra !== null && (
        <InstanciarPrograma
          obra={obra}
          rol={rol}
          onCerrar={() => setInstanciando(false)}
          onInstanciado={refrescar}
        />
      )}
    </div>
  );
}

function Kpi({
  etiqueta,
  valor,
  sub,
  alerta = false,
}: {
  readonly etiqueta: string;
  readonly valor: string;
  readonly sub?: string;
  readonly alerta?: boolean;
}) {
  return (
    <div className={`kpi${alerta ? ' kpi--alert' : ''}`}>
      <div className="kpi__label">{etiqueta}</div>
      <div className="kpi__value mono tnum">{valor}</div>
      {sub !== undefined && <div className="kpi__sub">{sub}</div>}
    </div>
  );
}
