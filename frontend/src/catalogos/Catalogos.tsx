/**
 * Catálogos · APU — pantalla de catálogos maestros y editor de precios
 * unitarios (§7.3, §10.1, §11.2 bloque "Catálogos · APU").
 *
 * Montada en `/config/catalogos`, la entrada "Catálogos" del sidebar de
 * Control de obra (§5.1). El contrato deja todo este bloque en (C) —salvo
 * la lectura del APU, que es (C, SI)—, y el sidebar del Super intendente no
 * trae la entrada, así que no se monta una segunda ruta para él: se montan
 * las rutas que algún sidebar apunta, no las que el contrato permitiría.
 *
 * Trece catálogos en pestañas: unidades, familias, materiales, mano de
 * obra, equipo, herramienta, subcontrato, conceptos, contratistas,
 * cuadrillas, prototipos, nivel de construcción y etapa de construcción. El
 * buscador es **por clave** (§3.3): la clave manda y la descripción solo
 * desempata — `busqueda.ts` lo implementa y esta pantalla solo lo consume.
 *
 * Materiales/mano de obra/equipo/herramienta/subcontrato son la misma
 * entidad `Insumo` con `tipo` distinto (§7.3): antes vivían juntos en una
 * sola pestaña "Insumos" con un filtro Tipo, pero eso escondía cada
 * categoría detrás de un `<select>` en vez de dejarla ver de entrada — ahora
 * cada `tipo` es su propia pestaña, sin filtro, mismo patrón que ya tenía
 * Materiales.
 *
 * Niveles, etapas y prototipos no traen alta desde aquí: niveles/etapas los
 * da de alta el cargador dedicado del árbol de presupuesto (§10.6); los
 * prototipos ya tienen su propia pantalla en `/config/prototipos` con árbol
 * y alta — esta pestaña solo replica su listado para que "todos los
 * catálogos" vivan en un solo lugar, sin duplicar esa pantalla.
 *
 * ## Ruta de datos (§10.7)
 *
 * El §10.7 abre la puerta a leer catálogos **directo de Supabase** con
 * supabase-js + RLS. Aquí no se usa, por la misma razón que en `proyectos`:
 * el contrato ya expone `GET /unidades`, `/familias`, `/insumos`,
 * `/materiales`, `/conceptos` y `/contratistas`, y ninguna feature de la app
 * abre hoy la ruta directa. Mantener una sola frontera —API + RLS detrás—
 * evita que el mismo dato llegue por dos caminos con dos comportamientos de
 * caché, y deja el diccionario canónico (§8) del lado del backend, que es
 * quien lo aplica. La escritura, en cualquier caso, va **siempre** por la
 * API (§10.7), y el APU también: es lógica de dominio, no catálogo plano.
 *
 * El cliente de la ruta directa sigue disponible en `lib/supabase.ts` con su
 * lista blanca; si un día se quiere realtime en un select, ese es el lugar.
 */

import { useMemo, useState } from 'react';

import {
  useAsignarEspecialidadAlConceptoApiV1ConceptosConceptoIdEspecialidadPut,
  useListarConceptosApiV1ConceptosGet,
  useListarContratistasApiV1ContratistasGet,
  useListarCuadrillasApiV1CuadrillasGet,
  useListarEtapasApiV1EtapasGet,
  useListarFamiliasApiV1FamiliasGet,
  useListarInsumosApiV1InsumosGet,
  useListarMaterialesApiV1MaterialesGet,
  useListarNivelesApiV1NivelesGet,
  useListarUnidadesApiV1UnidadesGet,
} from '@/api/generado/catalogos/catalogos';
import {
  useListarEspecialidadesApiV1EspecialidadesGet,
  useListarPrototiposApiV1PrototiposGet,
  useListarProyectosApiV1ProyectosGet,
} from '@/api/generado/proyectos/proyectos';
import { TipoConcepto, TipoInsumo } from '@/api/generado/modelo';
import type {
  ConceptoRespuesta,
  ContratistaRespuesta,
  CuadrillaRespuesta,
  EspecialidadRespuesta,
  EtapaRespuesta,
  FamiliaRespuesta,
  InsumoRespuesta,
  NivelRespuesta,
  PrototipoRespuesta,
  ProyectoRespuesta,
  UnidadRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { buscarPorClave } from './busqueda';
import { AltaConcepto } from './AltaConcepto';
import { AltaContratista } from './AltaContratista';
import { AltaCuadrilla } from './AltaCuadrilla';
import { AltaFamilia } from './AltaFamilia';
import { AltaInsumo } from './AltaInsumo';
import { AltaUnidad } from './AltaUnidad';
import { Especialidades } from './Especialidades';
import { PanelAPU } from './PanelAPU';
import {
  TablaConceptos,
  TablaContratistas,
  TablaCuadrillas,
  TablaEtapas,
  TablaFamilias,
  TablaInsumos,
  TablaNiveles,
  TablaPrototipos,
  TablaUnidades,
} from './Tablas';
import {
  etiquetaTipoConcepto,
  puedeAdministrarCatalogos,
  puedeConsultarAPU,
} from './reglas';

type Pestania =
  | 'unidades'
  | 'familias'
  | 'materiales'
  | 'mano_obra'
  | 'equipo'
  | 'herramienta'
  | 'subcontrato'
  | 'conceptos'
  | 'contratistas'
  | 'cuadrillas'
  | 'niveles'
  | 'etapas'
  | 'especialidades'
  | 'prototipos';

const PESTANIAS: readonly { readonly clave: Pestania; readonly etiqueta: string }[] = [
  { clave: 'conceptos', etiqueta: 'Conceptos' },
  { clave: 'materiales', etiqueta: 'Materiales' },
  { clave: 'mano_obra', etiqueta: 'Mano de obra' },
  { clave: 'equipo', etiqueta: 'Equipo' },
  { clave: 'herramienta', etiqueta: 'Herramienta' },
  { clave: 'subcontrato', etiqueta: 'Subcontrato' },
  { clave: 'familias', etiqueta: 'Familias' },
  { clave: 'unidades', etiqueta: 'Unidades' },
  { clave: 'contratistas', etiqueta: 'Contratistas' },
  { clave: 'cuadrillas', etiqueta: 'Cuadrillas' },
  { clave: 'prototipos', etiqueta: 'Prototipos' },
  { clave: 'niveles', etiqueta: 'Nivel de construcción' },
  { clave: 'etapas', etiqueta: 'Etapa de construcción' },
  // El segundo eje del trabajo (§8.3, 0047): va junto a Etapa de construcción
  // porque las dos clasifican lo mismo desde lados distintos —la etapa lleva
  // el frente y el concepto el oficio— y se capturan en la misma sentada.
  { clave: 'especialidades', etiqueta: 'Oficios' },
];

/** Las cinco caras de `Insumo` (§7.3): mismo repositorio/endpoint, `tipo`
 * fijo por pestaña — la lista para no repetir el `Set`/el filtro cinco
 * veces. `material` no entra: tiene ruta y catálogo propios desde antes. */
const PESTANIAS_TIPO_INSUMO = new Set<Pestania>([
  'mano_obra',
  'equipo',
  'herramienta',
  'subcontrato',
]);

/** Sin `estatus` (no son catálogo dado-de-baja, §7.4/§7.2): el checkbox
 * "Incluir dados de baja" no aplica a estas tres. */
const PESTANIAS_SIN_ESTATUS = new Set<Pestania>(['niveles', 'etapas', 'prototipos']);

/** Sin alta desde esta pantalla: niveles/etapas los da de alta el cargador
 * dedicado (§10.6) o el árbol de presupuesto; prototipos ya tiene su propia
 * pantalla en `/config/prototipos` con árbol y alta — duplicarla aquí
 * confundiría cuál es la fuente de verdad. */
const PESTANIAS_SIN_ALTA = new Set<Pestania>(['niveles', 'etapas', 'prototipos']);

const TIPOS_CONCEPTO: readonly TipoConcepto[] = [
  TipoConcepto.concepto,
  TipoConcepto.auxiliar,
  TipoConcepto.matriz,
  TipoConcepto.basico,
];

type Dialogo = Pestania | null;

export default function Catalogos() {
  const { sesion } = useSesion();
  const rol = sesion?.rol ?? null;
  const administra = rol !== null && puedeAdministrarCatalogos(rol);
  const consultaAPU = rol !== null && puedeConsultarAPU(rol);

  const [pestania, setPestania] = useState<Pestania>('conceptos');
  const [texto, setTexto] = useState('');
  const [familiaId, setFamiliaId] = useState('');
  const [tipoConcepto, setTipoConcepto] = useState<TipoConcepto | ''>('');
  const [soloSinOficio, setSoloSinOficio] = useState(false);
  const [incluirInactivos, setIncluirInactivos] = useState(false);
  const [dialogo, setDialogo] = useState<Dialogo>(null);
  const [conceptoAbierto, setConceptoAbierto] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  // El catálogo de oficios (§8.3, 0047) alimenta la columna editable de
  // conceptos: es la forma de rellenar lo que el archivo cargado no clasifica.
  const especialidadesQ = useListarEspecialidadesApiV1EspecialidadesGet<
    EspecialidadRespuesta[],
    ErrorApi
  >(undefined, {
    query: { enabled: pestania === 'conceptos' || pestania === 'especialidades' },
  });

  const asignarOficio =
    useAsignarEspecialidadAlConceptoApiV1ConceptosConceptoIdEspecialidadPut<ErrorApi>({
      mutation: {
        onSuccess: () => void conceptosQ.refetch(),
        onError: (err) => setAviso(err.message),
      },
    });

  function cambiarOficio(conceptoId: string, especialidadId: string | null): void {
    setAviso(null);
    asignarOficio.mutate({
      conceptoId,
      data: { especialidad_id: especialidadId },
    });
  }

  // Unidades y familias se piden siempre: además de su pestaña, resuelven
  // las claves que las demás tablas muestran y alimentan los selects de las
  // altas. Son listas cortas (§8.7, semilla editable).
  const unidadesQ = useListarUnidadesApiV1UnidadesGet<UnidadRespuesta[], ErrorApi>({
    incluir_inactivos: incluirInactivos,
  });

  const familiasQ = useListarFamiliasApiV1FamiliasGet<FamiliaRespuesta[], ErrorApi>({
    incluir_inactivos: incluirInactivos,
  });

  const materialesQ = useListarMaterialesApiV1MaterialesGet<InsumoRespuesta[], ErrorApi>(
    {
      familia_id: familiaId === '' ? undefined : familiaId,
      incluir_inactivos: incluirInactivos,
    },
    { query: { enabled: pestania === 'materiales' } },
  );

  // Las cuatro caras restantes de `Insumo` (§7.3): mismo `GET /insumos`,
  // `tipo` fijo por pestaña en vez de un filtro que el usuario elige —
  // antes vivían juntas bajo "Insumos" con ese filtro (ver docstring).
  const manoObraQ = useListarInsumosApiV1InsumosGet<InsumoRespuesta[], ErrorApi>(
    {
      tipo: TipoInsumo.mano_obra,
      familia_id: familiaId === '' ? undefined : familiaId,
      incluir_inactivos: incluirInactivos,
    },
    { query: { enabled: pestania === 'mano_obra' } },
  );

  const equipoQ = useListarInsumosApiV1InsumosGet<InsumoRespuesta[], ErrorApi>(
    {
      tipo: TipoInsumo.equipo,
      familia_id: familiaId === '' ? undefined : familiaId,
      incluir_inactivos: incluirInactivos,
    },
    { query: { enabled: pestania === 'equipo' } },
  );

  const herramientaQ = useListarInsumosApiV1InsumosGet<InsumoRespuesta[], ErrorApi>(
    {
      tipo: TipoInsumo.herramienta,
      familia_id: familiaId === '' ? undefined : familiaId,
      incluir_inactivos: incluirInactivos,
    },
    { query: { enabled: pestania === 'herramienta' } },
  );

  const subcontratoQ = useListarInsumosApiV1InsumosGet<InsumoRespuesta[], ErrorApi>(
    {
      tipo: TipoInsumo.subcontrato,
      familia_id: familiaId === '' ? undefined : familiaId,
      incluir_inactivos: incluirInactivos,
    },
    { query: { enabled: pestania === 'subcontrato' } },
  );

  const conceptosQ = useListarConceptosApiV1ConceptosGet<ConceptoRespuesta[], ErrorApi>(
    {
      tipo: tipoConcepto === '' ? undefined : tipoConcepto,
      familia_id: familiaId === '' ? undefined : familiaId,
      incluir_inactivos: incluirInactivos,
    },
    { query: { enabled: pestania === 'conceptos' } },
  );

  const contratistasQ = useListarContratistasApiV1ContratistasGet<
    ContratistaRespuesta[],
    ErrorApi
  >({ incluir_inactivos: incluirInactivos }, { query: { enabled: pestania === 'contratistas' } });

  const cuadrillasQ = useListarCuadrillasApiV1CuadrillasGet<CuadrillaRespuesta[], ErrorApi>(
    { incluir_inactivos: incluirInactivos },
    // También en las cuatro pestañas de insumo: `TablaInsumos` resuelve
    // `cuadrilla_id` de mano de obra/subcontrato contra este catálogo
    // (§10.6), igual que ya hace con unidades.
    { query: { enabled: pestania === 'cuadrillas' || PESTANIAS_TIPO_INSUMO.has(pestania) } },
  );

  const nivelesQ = useListarNivelesApiV1NivelesGet<NivelRespuesta[], ErrorApi>({
    // También en "etapas": `TablaEtapas` resuelve la clave del nivel de
    // cada etapa contra este catálogo, igual que las tablas de insumo
    // resuelven unidad/cuadrilla.
    query: { enabled: pestania === 'niveles' || pestania === 'etapas' },
  });

  const etapasQ = useListarEtapasApiV1EtapasGet<EtapaRespuesta[], ErrorApi>({
    query: { enabled: pestania === 'etapas' },
  });

  const proyectosQ = useListarProyectosApiV1ProyectosGet<ProyectoRespuesta[], ErrorApi>({
    query: { enabled: pestania === 'prototipos' },
  });

  const prototiposQ = useListarPrototiposApiV1PrototiposGet<PrototipoRespuesta[], ErrorApi>(
    {},
    { query: { enabled: pestania === 'prototipos' } },
  );

  const unidades = useMemo(() => unidadesQ.data ?? [], [unidadesQ.data]);
  const familias = useMemo(() => familiasQ.data ?? [], [familiasQ.data]);
  const cuadrillasParaInsumos = useMemo(() => cuadrillasQ.data ?? [], [cuadrillasQ.data]);
  const conceptos = useMemo(() => conceptosQ.data ?? [], [conceptosQ.data]);

  // Cuántos conceptos usa cada oficio: es lo que deja decidir cuál absorbe a
  // cuál al fusionar. Sale de los conceptos ya cargados, sin otra consulta.
  const conceptosPorOficio = useMemo(() => {
    const cuenta = new Map<string, number>();
    for (const concepto of conceptos) {
      if (!concepto.especialidad_id) continue;
      cuenta.set(
        concepto.especialidad_id,
        (cuenta.get(concepto.especialidad_id) ?? 0) + 1,
      );
    }
    return cuenta;
  }, [conceptos]);
  const niveles = useMemo(() => nivelesQ.data ?? [], [nivelesQ.data]);
  const proyectos = useMemo(() => proyectosQ.data ?? [], [proyectosQ.data]);

  const resUnidades = useMemo(
    () => buscarPorClave(unidades, texto, (unidad) => unidad.nombre),
    [unidades, texto],
  );
  const resFamilias = useMemo(
    () => buscarPorClave(familias, texto, (familia) => familia.nombre),
    [familias, texto],
  );
  const resManoObra = useMemo(
    () => buscarPorClave(manoObraQ.data ?? [], texto, (insumo) => insumo.descripcion),
    [manoObraQ.data, texto],
  );
  const resEquipo = useMemo(
    () => buscarPorClave(equipoQ.data ?? [], texto, (insumo) => insumo.descripcion),
    [equipoQ.data, texto],
  );
  const resHerramienta = useMemo(
    () => buscarPorClave(herramientaQ.data ?? [], texto, (insumo) => insumo.descripcion),
    [herramientaQ.data, texto],
  );
  const resSubcontrato = useMemo(
    () => buscarPorClave(subcontratoQ.data ?? [], texto, (insumo) => insumo.descripcion),
    [subcontratoQ.data, texto],
  );
  const resMateriales = useMemo(
    () => buscarPorClave(materialesQ.data ?? [], texto, (material) => material.descripcion),
    [materialesQ.data, texto],
  );
  const resConceptos = useMemo(
    () =>
      buscarPorClave(
        // El filtro va antes de la búsqueda y no después: "sin oficio" es lo
        // que se está buscando, no un adorno del resultado, y aplicarlo al
        // final dejaría el contador diciendo cuántos hay en total.
        soloSinOficio ? conceptos.filter((c) => !c.especialidad_id) : conceptos,
        texto,
        (concepto) => concepto.descripcion,
      ),
    [conceptos, texto, soloSinOficio],
  );
  const resContratistas = useMemo(
    () =>
      buscarPorClave(contratistasQ.data ?? [], texto, (contratista) => contratista.razon_social),
    [contratistasQ.data, texto],
  );
  const resCuadrillas = useMemo(
    () => buscarPorClave(cuadrillasQ.data ?? [], texto, (cuadrilla) => cuadrilla.nombre),
    [cuadrillasQ.data, texto],
  );
  const resNiveles = useMemo(
    () => buscarPorClave(niveles, texto, (nivel) => nivel.descripcion),
    [niveles, texto],
  );
  const resEtapas = useMemo(
    () => buscarPorClave(etapasQ.data ?? [], texto, (etapa) => etapa.descripcion),
    [etapasQ.data, texto],
  );
  const resPrototipos = useMemo(
    () => buscarPorClave(prototiposQ.data ?? [], texto, (prototipo) => prototipo.nombre),
    [prototiposQ.data, texto],
  );

  // El concepto del cajón se re-deriva de la lista para que un cambio de
  // filtro no deje abierto un APU que ya no está en pantalla.
  const concepto = conceptos.find((c) => c.id === conceptoAbierto) ?? null;

  if (!sesion || rol === null) return null;

  const errores = [
    unidadesQ.error,
    familiasQ.error,
    materialesQ.error,
    manoObraQ.error,
    equipoQ.error,
    herramientaQ.error,
    subcontratoQ.error,
    conceptosQ.error,
    contratistasQ.error,
    cuadrillasQ.error,
    nivelesQ.error,
    etapasQ.error,
    proyectosQ.error,
    prototiposQ.error,
  ].filter((error): error is ErrorApi => error !== null && error !== undefined);

  function cambiarPestania(nueva: Pestania) {
    setPestania(nueva);
    setConceptoAbierto(null);
    // El filtro de tipo de concepto es de una sola pestaña; arrastrarlo
    // entre catálogos dejaría la tabla vacía sin razón visible.
    setTipoConcepto('');
  }

  function tituloAlta(): string | null {
    switch (pestania) {
      case 'unidades':
        return 'Nueva unidad';
      case 'familias':
        return 'Nueva familia';
      case 'materiales':
        return 'Nuevo material';
      case 'mano_obra':
        return 'Nueva mano de obra';
      case 'equipo':
        return 'Nuevo equipo';
      case 'herramienta':
        return 'Nueva herramienta';
      case 'subcontrato':
        return 'Nuevo subcontrato';
      case 'conceptos':
        return 'Nuevo concepto';
      case 'contratistas':
        return 'Nuevo contratista';
      case 'cuadrillas':
        return 'Nueva cuadrilla';
      case 'niveles':
      case 'etapas':
      // Los oficios se dan de alta en su propia pestaña, con clave y nombre a
      // la vista: son dos campos y un diálogo sobraría.
      case 'especialidades':
      case 'prototipos':
        return null;
    }
  }

  function alCrear(mensaje: string) {
    setDialogo(null);
    setAviso(mensaje);
    void unidadesQ.refetch();
    void familiasQ.refetch();
    if (pestania === 'materiales') void materialesQ.refetch();
    if (pestania === 'mano_obra') void manoObraQ.refetch();
    if (pestania === 'equipo') void equipoQ.refetch();
    if (pestania === 'herramienta') void herramientaQ.refetch();
    if (pestania === 'subcontrato') void subcontratoQ.refetch();
    if (pestania === 'conceptos') void conceptosQ.refetch();
    if (pestania === 'contratistas') void contratistasQ.refetch();
    if (pestania === 'cuadrillas') void cuadrillasQ.refetch();
  }

  const familiasDelLado = familias.filter((familia) =>
    pestania === 'conceptos'
      ? (familia.aplica_a ?? 'material') === 'concepto'
      : (familia.aplica_a ?? 'material') === 'material',
  );

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Configuración</div>
          <h1 className="page__title">Catálogos · APU</h1>
          <div className="page__subtitle">
            Catálogos maestros y análisis de precios unitarios. La clave es única y manda en
            todo cruce; la descripción solo desempata (§3.3).
          </div>
        </div>

        {administra && !PESTANIAS_SIN_ALTA.has(pestania) && (
          <div className="page__actions">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setDialogo(pestania)}
            >
              {tituloAlta()}
            </button>
          </div>
        )}
      </div>

      {aviso !== null && (
        <div className="mb-8" role="status">
          <span className="badge badge--ok">{aviso}</span>
        </div>
      )}

      {errores.map((error, indice) => (
        <div className="mb-8" key={`${error.status}-${indice}`}>
          <ErrorBanner mensaje={error.message} />
        </div>
      ))}

      <div className="tabs mb-8" role="tablist" aria-label="Catálogos">
        {PESTANIAS.map((opcion) => (
          <button
            key={opcion.clave}
            type="button"
            role="tab"
            id={`tab-${opcion.clave}`}
            aria-selected={pestania === opcion.clave}
            // Solo el panel activo existe en el DOM; apuntar al de una
            // pestaña inactiva sería un `aria-controls` colgado.
            aria-controls={pestania === opcion.clave ? `panel-${opcion.clave}` : undefined}
            className={`tabs__tab${pestania === opcion.clave ? ' is-active' : ''}`}
            onClick={() => cambiarPestania(opcion.clave)}
          >
            {opcion.etiqueta}
          </button>
        ))}
      </div>

      <div className="filterbar">
        <input
          className="input search"
          type="search"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Buscar por clave…"
          aria-label="Buscar por clave; la descripción solo desempata (§3.3)"
        />

        {pestania === 'conceptos' && (
          <select
            className="select"
            value={tipoConcepto}
            onChange={(e) => setTipoConcepto(e.target.value as TipoConcepto | '')}
            aria-label="Filtrar por tipo de concepto"
          >
            <option value="">Todos los tipos</option>
            {TIPOS_CONCEPTO.map((tipo) => (
              <option key={tipo} value={tipo}>
                {etiquetaTipoConcepto(tipo)}
              </option>
            ))}
          </select>
        )}

        {pestania === 'conceptos' && (
          <label className="row gap-4" style={{ alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={soloSinOficio}
              onChange={(e) => setSoloSinOficio(e.target.checked)}
            />
            <span className="text-sm">Solo sin oficio</span>
          </label>
        )}

        {(PESTANIAS_TIPO_INSUMO.has(pestania) || pestania === 'materiales' || pestania === 'conceptos') && (
          <select
            className="select"
            value={familiaId}
            onChange={(e) => setFamiliaId(e.target.value)}
            aria-label="Filtrar por familia"
          >
            <option value="">Todas las familias</option>
            {familiasDelLado.map((familia) => (
              <option key={familia.id} value={familia.id}>
                {familia.clave} · {familia.nombre}
              </option>
            ))}
          </select>
        )}

        {!PESTANIAS_SIN_ESTATUS.has(pestania) && (
          <label className="row gap-4" style={{ alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={incluirInactivos}
              onChange={(e) => setIncluirInactivos(e.target.checked)}
            />
            <span className="text-sm text-mute">Incluir dados de baja</span>
          </label>
        )}
      </div>

      {/* `tabIndex={0}`: hay catálogos cuya tabla no tiene ningún control
          enfocable (unidades, familias), y sin esto el panel quedaría
          inalcanzable con teclado tras la pestaña. */}
      <div
        id={`panel-${pestania}`}
        role="tabpanel"
        aria-labelledby={`tab-${pestania}`}
        tabIndex={0}
      >
        {pestania === 'unidades' && (
          <TablaUnidades resultados={resUnidades} cargando={unidadesQ.isLoading} />
        )}

        {pestania === 'familias' && (
          <TablaFamilias
            resultados={resFamilias}
            familias={familias}
            cargando={familiasQ.isLoading}
          />
        )}

        {pestania === 'materiales' && (
          <TablaInsumos
            resultados={resMateriales}
            unidades={unidades}
            familias={familias}
            cuadrillas={cuadrillasParaInsumos}
            cargando={materialesQ.isLoading}
            vacia="No hay materiales con estos filtros."
          />
        )}

        {pestania === 'mano_obra' && (
          <TablaInsumos
            resultados={resManoObra}
            unidades={unidades}
            familias={familias}
            cuadrillas={cuadrillasParaInsumos}
            cargando={manoObraQ.isLoading}
            vacia="No hay mano de obra con estos filtros."
          />
        )}

        {pestania === 'equipo' && (
          <TablaInsumos
            resultados={resEquipo}
            unidades={unidades}
            familias={familias}
            cuadrillas={cuadrillasParaInsumos}
            cargando={equipoQ.isLoading}
            vacia="No hay equipo con estos filtros."
          />
        )}

        {pestania === 'herramienta' && (
          <TablaInsumos
            resultados={resHerramienta}
            unidades={unidades}
            familias={familias}
            cuadrillas={cuadrillasParaInsumos}
            cargando={herramientaQ.isLoading}
            vacia="No hay herramienta con estos filtros."
          />
        )}

        {pestania === 'subcontrato' && (
          <TablaInsumos
            resultados={resSubcontrato}
            unidades={unidades}
            familias={familias}
            cuadrillas={cuadrillasParaInsumos}
            cargando={subcontratoQ.isLoading}
            vacia="No hay subcontratos con estos filtros."
          />
        )}

        {pestania === 'conceptos' && (
          <TablaConceptos
            resultados={resConceptos}
            unidades={unidades}
            familias={familias}
            especialidades={especialidadesQ.data ?? []}
            cargando={conceptosQ.isLoading}
            conceptoAbierto={conceptoAbierto}
            onAbrirAPU={consultaAPU ? (elegido) => setConceptoAbierto(elegido.id) : undefined}
            onCambiarOficio={administra ? cambiarOficio : undefined}
          />
        )}

        {pestania === 'especialidades' && (
          <Especialidades
            especialidades={especialidadesQ.data ?? []}
            conceptosPorOficio={conceptosPorOficio}
            cargando={especialidadesQ.isLoading}
            administra={administra}
            onCambio={() => {
              void especialidadesQ.refetch();
              void conceptosQ.refetch();
            }}
          />
        )}

        {pestania === 'contratistas' && (
          <TablaContratistas resultados={resContratistas} cargando={contratistasQ.isLoading} />
        )}

        {pestania === 'cuadrillas' && (
          <TablaCuadrillas
            resultados={resCuadrillas}
            unidades={unidades}
            cargando={cuadrillasQ.isLoading}
          />
        )}

        {pestania === 'niveles' && (
          <TablaNiveles resultados={resNiveles} cargando={nivelesQ.isLoading} />
        )}

        {pestania === 'etapas' && (
          <TablaEtapas resultados={resEtapas} niveles={niveles} cargando={etapasQ.isLoading} />
        )}

        {pestania === 'prototipos' && (
          <TablaPrototipos
            resultados={resPrototipos}
            proyectos={proyectos}
            cargando={prototiposQ.isLoading}
          />
        )}
      </div>

      {concepto && (
        <PanelAPU
          key={concepto.id}
          concepto={concepto}
          rol={rol}
          unidad={unidades.find((unidad) => unidad.id === concepto.unidad_id)}
          onCerrar={() => setConceptoAbierto(null)}
        />
      )}

      {dialogo === 'unidades' && (
        <AltaUnidad
          onCerrar={() => setDialogo(null)}
          onCreada={() => alCrear('Unidad creada')}
        />
      )}

      {dialogo === 'familias' && (
        <AltaFamilia
          familias={familias}
          onCerrar={() => setDialogo(null)}
          onCreada={() => alCrear('Familia creada')}
        />
      )}

      {dialogo === 'materiales' && (
        <AltaInsumo
          unidades={unidades}
          familias={familias}
          tipoFijo={TipoInsumo.material}
          titulo="Nuevo material"
          onCerrar={() => setDialogo(null)}
          onCreado={() => alCrear('Material creado')}
        />
      )}

      {dialogo === 'mano_obra' && (
        <AltaInsumo
          unidades={unidades}
          familias={familias}
          tipoFijo={TipoInsumo.mano_obra}
          titulo="Nueva mano de obra"
          onCerrar={() => setDialogo(null)}
          onCreado={() => alCrear('Mano de obra creada')}
        />
      )}

      {dialogo === 'equipo' && (
        <AltaInsumo
          unidades={unidades}
          familias={familias}
          tipoFijo={TipoInsumo.equipo}
          titulo="Nuevo equipo"
          onCerrar={() => setDialogo(null)}
          onCreado={() => alCrear('Equipo creado')}
        />
      )}

      {dialogo === 'herramienta' && (
        <AltaInsumo
          unidades={unidades}
          familias={familias}
          tipoFijo={TipoInsumo.herramienta}
          titulo="Nueva herramienta"
          onCerrar={() => setDialogo(null)}
          onCreado={() => alCrear('Herramienta creada')}
        />
      )}

      {dialogo === 'subcontrato' && (
        <AltaInsumo
          unidades={unidades}
          familias={familias}
          tipoFijo={TipoInsumo.subcontrato}
          titulo="Nuevo subcontrato"
          onCerrar={() => setDialogo(null)}
          onCreado={() => alCrear('Subcontrato creado')}
        />
      )}

      {dialogo === 'conceptos' && (
        <AltaConcepto
          unidades={unidades}
          familias={familias}
          onCerrar={() => setDialogo(null)}
          onCreado={() => alCrear('Concepto creado')}
        />
      )}

      {dialogo === 'contratistas' && (
        <AltaContratista
          onCerrar={() => setDialogo(null)}
          onCreado={() => alCrear('Contratista creado')}
        />
      )}

      {dialogo === 'cuadrillas' && (
        <AltaCuadrilla
          unidades={unidades}
          onCerrar={() => setDialogo(null)}
          onCreada={() => alCrear('Cuadrilla creada')}
        />
      )}
    </div>
  );
}
