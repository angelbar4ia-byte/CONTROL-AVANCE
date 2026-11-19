/**
 * El área de trabajo de la pestaña «Artefacto»: la plantilla de muro (tipo, material, ubicación con sus caras A y B, partes de
 * altura y los elementos que lleva), su vista previa y su validación contra la matriz de los conceptos de sus elementos.
 *
 * Costos y Control de obra editan; **solo Control de obra valida**. Toda plantilla nace «por validar» y cualquier cambio la deja así;
 * al cambiar una ya validada nace una versión nueva y los trazos ya medidos conservan la anterior. El servidor valida y deriva: aquí
 * solo se arma lo que se manda y se dibuja lo que responde.
 */

import { useEffect, useMemo, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getListarPlantillasApiV1MuroPlantillasGetQueryKey,
  getPrototiposDeMuroApiV1MuroArtefactoPrototiposGetQueryKey,
  getRevisarPlantillaApiV1MuroPlantillasPlantillaIdRevisionGetQueryKey,
  useBorrarPlantillaApiV1MuroPlantillasPlantillaIdDelete,
  useCambiarPlantillaApiV1MuroPlantillasPlantillaIdPut,
  useCatalogoDelArtefactoApiV1MuroArtefactoCatalogoGet,
  useCrearPlantillaApiV1MuroPlantillasPost,
  usePrototiposDeMuroApiV1MuroArtefactoPrototiposGet,
  useRevisarPlantillaApiV1MuroPlantillasPlantillaIdRevisionGet,
  useValidarPlantillaApiV1MuroPlantillasPlantillaIdValidarPost,
  useVerPlantillaApiV1MuroPlantillasPlantillaIdGet,
  useVersionesDeLaPlantillaApiV1MuroPlantillasPlantillaIdVersionesGet,
} from '@/api/generado/artefacto-de-muros/artefacto-de-muros';
import { useBibliotecaDeElementosApiV1BibliotecaDeElementosGet } from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';
import { useListarElementosParametricosApiV1ElementosParametricosGet } from '@/api/generado/elementos-parametricos/elementos-parametricos';
import { queryClient } from '@/app/queryClient';
import { useDriversDeObraApiV1ObrasObraIdDriversGet } from '@/api/generado/parametrico/parametrico';
import { useSesion } from '@/app/sesion';

import {
  type Borrador,
  borradorDe,
  borradorDePrototipo,
  borradorVacio,
  cambio,
  driversDeVistaDe,
  type ElementoBorrador,
  esPlantillaNueva,
  geometriaDeVista,
  type MedidaDeElemento,
  type ParteBorrador,
  peticionDe,
  type Planta,
  prototipoDeNueva,
  type ReglaDeCastillo,
  reglasDeCastillo,
  type RolDeParte,
  type TipoDeMuro,
} from './plantillaDeMuro';
import { VistaPreviaDePlantilla } from './VistaPreviaDePlantilla';

const ROLES_DE_PARTE: readonly RolDeParte[] = ['cuerpo', 'enrase', 'pretil', 'cadena'];
const NOMBRE_DE_REGLA: Readonly<Record<ReglaDeCastillo, string>> = {
  separacion: 'Cada separación y extremos',
  extremos: 'Solo extremos',
  por_ml: 'Por metro lineal',
  total: 'Total del prototipo',
};
const CARAS = [
  ['', '—'],
  ['exterior', 'Exterior'],
  ['interior', 'Interior'],
] as const;

interface Props {
  /** La plantilla que se edita, `PLANTILLA_NUEVA` para una nueva o `null` si no se ha elegido. */
  readonly plantillaId: string | null;
  readonly onElegir: (id: string | null) => void;
  /** La obra actual: de sus drivers sale la separación de castillos de la vista previa. */
  readonly obraId?: string;
}

interface OpcionDeElemento {
  readonly ref: string;
  readonly nombre: string;
  readonly clase: 'castillo' | 'cadena' | 'muro';
}

function mensajeDe(err: unknown, defecto: string): string {
  return err instanceof Error ? err.message : defecto;
}

export function PantallaDeArtefacto({ plantillaId, onElegir, obraId = '' }: Props) {
  const { sesion } = useSesion();
  const rol = sesion?.rol;
  const puedeEditar = rol === 'control_obra' || rol === 'costos';
  const puedeValidar = rol === 'control_obra';
  const nueva = esPlantillaNueva(plantillaId);
  const idGuardada = plantillaId && !nueva ? plantillaId : null;

  const catalogo = useCatalogoDelArtefactoApiV1MuroArtefactoCatalogoGet();
  const prototipos = usePrototiposDeMuroApiV1MuroArtefactoPrototiposGet();
  const consulta = useVerPlantillaApiV1MuroPlantillasPlantillaIdGet(idGuardada ?? '', { query: { enabled: idGuardada !== null } });
  const guardada = idGuardada ? (consulta.data ?? null) : null;
  const versiones = useVersionesDeLaPlantillaApiV1MuroPlantillasPlantillaIdVersionesGet(idGuardada ?? '', {
    query: { enabled: idGuardada !== null },
  });
  const revision = useRevisarPlantillaApiV1MuroPlantillasPlantillaIdRevisionGet(idGuardada ?? '', {
    query: { enabled: idGuardada !== null },
  });
  const elementosDelCatalogo = useListarElementosParametricosApiV1ElementosParametricosGet();
  const biblioteca = useBibliotecaDeElementosApiV1BibliotecaDeElementosGet();

  const crear = useCrearPlantillaApiV1MuroPlantillasPost<ErrorApi>();
  const cambiar = useCambiarPlantillaApiV1MuroPlantillasPlantillaIdPut<ErrorApi>();
  const borrar = useBorrarPlantillaApiV1MuroPlantillasPlantillaIdDelete<ErrorApi>();
  const validar = useValidarPlantillaApiV1MuroPlantillasPlantillaIdValidarPost<ErrorApi>();

  const [borrador, setBorrador] = useState<Borrador>(borradorVacio());
  const [aviso, setAviso] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aceptar, setAceptar] = useState(false);

  // Al cambiar de plantilla (o al llegar su versión nueva) el borrador vuelve a lo guardado.
  const huella = guardada ? `${guardada.id}:${guardada.updated_at}` : (plantillaId ?? '');
  useEffect(() => {
    // Una plantilla nueva de un prototipo nace como muro confinado de ese prototipo y planta, sin castillos (estructura por capturar).
    const { prototipo, planta } = prototipoDeNueva(nueva ? plantillaId : null);
    const ficha = (prototipos.data ?? []).find((x) => x.clave === prototipo);
    const sufijo = planta ? ` · ${planta}` : '';
    setBorrador(
      guardada
        ? borradorDe(guardada)
        : prototipo
          ? borradorDePrototipo(prototipo, planta, `Muro confinado · ${ficha?.nombre ?? prototipo}${sufijo}`)
          : borradorVacio(),
    );
    setError(null);
    setAceptar(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [huella, prototipos.isSuccess]);

  const opciones = useMemo<OpcionDeElemento[]>(() => {
    const salida: OpcionDeElemento[] = [];
    for (const e of elementosDelCatalogo.data ?? []) {
      if (e.categoria === 'castillos') salida.push({ ref: e.clave, nombre: e.nombre, clase: 'castillo' });
      else if (e.categoria === 'cadenas' || e.categoria === 'dalas') salida.push({ ref: e.clave, nombre: e.nombre, clase: 'cadena' });
    }
    for (const c of biblioteca.data ?? []) {
      if (c.clave !== 'muros') continue;
      for (const s of c.subcategorias) for (const e of s.elementos) salida.push({ ref: e.clave, nombre: e.nombre, clase: 'muro' });
    }
    return salida;
  }, [elementosDelCatalogo.data, biblioteca.data]);

  const medidas = useMemo(() => {
    const m: Record<string, MedidaDeElemento> = {};
    for (const e of elementosDelCatalogo.data ?? []) {
      m[e.clave] = { ancho_m: Number(e.parametros.ancho ?? 0.15), alto_m: Number(e.parametros.alto ?? 0.2) };
    }
    return m;
  }, [elementosDelCatalogo.data]);

  const driversDeLaObra = useDriversDeObraApiV1ObrasObraIdDriversGet(obraId, { query: { enabled: obraId !== '' } });
  const driversDeVista = useMemo(() => driversDeVistaDe(driversDeLaObra.data), [driversDeLaObra.data]);
  const geometria = useMemo(() => geometriaDeVista(borrador, medidas, driversDeVista), [borrador, medidas, driversDeVista]);
  const sinCambios = !cambio(borrador, guardada);
  const tipoFicha = (catalogo.data?.tipos ?? []).find((t) => t.clave === borrador.tipo);

  if (!idGuardada && !nueva) {
    return (
      <section className="pantalla-elementos pantalla-elementos--vacia" role="region" id="area-artefacto" aria-label="Artefacto">
        <div className="empty">
          <div className="empty-title">Artefacto</div>
          <div className="empty-sub">
            Elige una plantilla de muro en el panel, o crea una nueva: qué elementos lleva cada muro y con qué conceptos se paga.
          </div>
        </div>
      </section>
    );
  }
  if (idGuardada && consulta.isLoading) return <p className="text-mute text-sm" style={{ padding: 14 }}>Cargando la plantilla…</p>;
  if (idGuardada && !guardada) return <p className="text-sm" style={{ padding: 14 }} role="alert">No se pudo cargar la plantilla.</p>;

  const cambiarCampo = (c: Partial<Borrador>) => setBorrador((b) => ({ ...b, ...c }));
  const cambiarParte = (i: number, c: Partial<ParteBorrador>) =>
    setBorrador((b) => ({
      ...b,
      // Cambiar la cara de una parte vuelve personalizada la ubicación (regla 3); el servidor lo vuelve a derivar al guardar.
      ubicacion: 'caraA' in c || 'caraB' in c ? 'personalizada' : b.ubicacion,
      partes: b.partes.map((p, k) => (k === i ? { ...p, ...c } : p)),
    }));
  const cambiarElemento = (i: number, c: Partial<ElementoBorrador>) =>
    setBorrador((b) => ({ ...b, elementos: b.elementos.map((e, k) => (k === i ? { ...e, ...c } : e)) }));

  /** Cambiar el tipo de muro: solo el confinado lleva prototipo, y un castillo que se coloca en el plano (con cadena) no cuenta «por ml» ni «total». */
  function cambiarTipo(tipo: TipoDeMuro) {
    setBorrador((b) => ({
      ...b,
      tipo,
      ...(tipo === 'confinado' ? {} : { prototipo: '', planta: '' as const, porConfirmar: b.porConfirmar }),
      elementos: b.elementos.map((e) => (e.clase === 'castillo' && e.regla && !reglasDeCastillo(tipo).includes(e.regla) ? { ...e, regla: '' as const } : e)),
    }));
  }

  async function aplicarUbicacion(clave: string) {
    // Elegir la ubicación fija las caras de todas las partes (reglas 1 y 2): las calcula el servidor.
    setBorrador((b) => ({ ...b, ubicacion: clave }));
    if (clave === 'personalizada' || borrador.partes.length === 0) return;
    const r = peticionDe(borrador);
    if (!('peticion' in r)) return;
    try {
      const { aplicarUbicacionAPartesApiV1MuroArtefactoUbicacionPost } = await import('@/api/generado/artefacto-de-muros/artefacto-de-muros');
      const caras = await aplicarUbicacionAPartesApiV1MuroArtefactoUbicacionPost({
        ubicacion: clave as 'interior',
        partes: (r.peticion.partes ?? []).map((p) => ({ ...p, cara_a: null, cara_b: null })),
      });
      setBorrador((b) => ({
        ...b,
        ubicacion: clave,
        partes: b.partes.map((p, i) => ({
          ...p,
          caraA: (caras.partes[i]?.cara_a ?? '') as ParteBorrador['caraA'],
          caraB: (caras.partes[i]?.cara_b ?? '') as ParteBorrador['caraB'],
        })),
      }));
    } catch (e) {
      setError(mensajeDe(e, 'No se pudieron calcular las caras.'));
    }
  }

  function agregarElemento(ref: string) {
    const o = opciones.find((x) => x.ref === ref);
    if (!o) return;
    setBorrador((b) => {
      let uid = o.ref;
      for (let n = 2; b.elementos.some((e) => e.uid === uid); n++) uid = `${o.ref}#${n}`;
      return {
        ...b,
        elementos: [
          ...b.elementos,
          {
            uid, ref: o.ref, clase: o.clase, sep: '', posicion: o.clase === 'cadena' ? 'cerramiento' : '', z: '',
            regla: '', piezasPorMl: '', totalM: '', baseM2: '', origen: '',
          },
        ],
      };
    });
  }

  function refrescar() {
    void queryClient.invalidateQueries({ queryKey: getListarPlantillasApiV1MuroPlantillasGetQueryKey() });
    void queryClient.invalidateQueries({ queryKey: getPrototiposDeMuroApiV1MuroArtefactoPrototiposGetQueryKey() });
    if (idGuardada) {
      void queryClient.invalidateQueries({ queryKey: [`/api/v1/muro-plantillas/${idGuardada}`] });
      void queryClient.invalidateQueries({ queryKey: [`/api/v1/muro-plantillas/${idGuardada}/versiones`] });
      void queryClient.invalidateQueries({
        queryKey: getRevisarPlantillaApiV1MuroPlantillasPlantillaIdRevisionGetQueryKey(idGuardada),
      });
    }
  }

  async function guardar() {
    const r = peticionDe(borrador);
    if (!('peticion' in r)) {
      setError(r.motivo);
      return;
    }
    setError(null);
    setAviso(null);
    try {
      if (nueva) {
        const creada = await crear.mutateAsync({ data: r.peticion });
        setAviso('Plantilla creada: queda por validar.');
        refrescar();
        onElegir(creada.id);
      } else if (idGuardada) {
        const cambiada = await cambiar.mutateAsync({ plantillaId: idGuardada, data: r.peticion });
        setAviso(
          cambiada.version_nueva
            ? `Nació la versión ${cambiada.version}: queda por validar y los trazos ya medidos conservan la anterior.`
            : 'Plantilla guardada.',
        );
        refrescar();
        if (cambiada.id !== idGuardada) onElegir(cambiada.id);
      }
    } catch (e) {
      setError(mensajeDe(e, 'No se pudo guardar la plantilla.'));
    }
  }

  async function validarPlantilla() {
    if (!idGuardada) return;
    setError(null);
    try {
      await validar.mutateAsync({ plantillaId: idGuardada, data: { aceptar_alertas: aceptar } });
      setAviso('Plantilla validada.');
      refrescar();
    } catch (e) {
      setError(mensajeDe(e, 'No se pudo validar la plantilla.'));
    }
  }

  async function borrarPlantilla() {
    if (!idGuardada) return;
    setError(null);
    try {
      await borrar.mutateAsync({ plantillaId: idGuardada });
      refrescar();
      onElegir(null);
    } catch (e) {
      setError(mensajeDe(e, 'No se pudo borrar la plantilla.'));
    }
  }

  const ocupado = crear.isPending || cambiar.isPending || borrar.isPending || validar.isPending;
  const vigente = nueva || guardada?.vigente === true;
  const editable = puedeEditar && vigente;
  const alertas = revision.data?.alertas ?? [];
  const bloquea = revision.data?.bloquea ?? false;

  return (
    <section className="pantalla-elementos" role="region" id="area-artefacto" aria-label="Artefacto">
      <div className="pantalla-elementos__tarjeta" style={{ display: 'grid', gap: 12, alignContent: 'start' }}>
        <div className="mct__cabecera">
          <h2 className="mct__titulo">{nueva ? 'Nueva plantilla de muro' : guardada?.nombre}</h2>
          {guardada && (
            <div className="mct__resumen">
              <span className="badge badge--outline">Versión {guardada.version}</span>
              <span className={guardada.validacion === 'validada' ? 'badge badge--ok' : 'badge badge--warn'} data-validacion={guardada.validacion}>
                {guardada.validacion === 'validada' ? 'Validada' : 'Por validar'}
              </span>
              {!guardada.vigente && <span className="badge badge--outline">Versión anterior</span>}
              {guardada.trazos > 0 && <span className="badge badge--info">{guardada.trazos} trazos la usan</span>}
            </div>
          )}
        </div>
        {!puedeEditar && <p className="text-mute text-sm">Solo Costos y Control de obra editan las plantillas: tú la ves en solo lectura.</p>}
        {aviso && (
          <p className="text-sm" role="status">
            {aviso}
          </p>
        )}
        {error && (
          <p className="text-sm mct__error" role="alert">
            {error}
          </p>
        )}

        <div className="mct__bloque">
          <h3>El muro</h3>
          <div className="mct__parametros">
            <label className="mct__campo">
              Nombre de la plantilla
              <input
                className="input"
                aria-label="Nombre de la plantilla"
                value={borrador.nombre}
                maxLength={80}
                disabled={!editable}
                onChange={(e) => cambiarCampo({ nombre: e.target.value })}
              />
            </label>
            <label className="mct__campo">
              Material
              <select
                className="input"
                aria-label="Material de la plantilla"
                value={borrador.material}
                disabled={!editable}
                onChange={(e) => cambiarCampo({ material: e.target.value })}
              >
                {(catalogo.data?.materiales ?? []).map((m) => (
                  <option key={m.clave} value={m.clave}>
                    {m.nombre}
                  </option>
                ))}
              </select>
            </label>
            <label className="mct__campo">
              Ubicación (caras A y B)
              <select
                className="input"
                aria-label="Ubicación de la plantilla"
                value={borrador.ubicacion}
                disabled={!editable}
                onChange={(e) => void aplicarUbicacion(e.target.value)}
              >
                {(catalogo.data?.ubicaciones ?? []).map((u) => (
                  <option key={u.clave} value={u.clave}>
                    {u.nombre}
                  </option>
                ))}
              </select>
            </label>
            <label className="mct__campo">
              Altura base (m)
              <input
                className="input"
                inputMode="decimal"
                aria-label="Altura de la plantilla (m)"
                placeholder="la de la herramienta (3.00)"
                value={borrador.altura}
                disabled={!editable}
                onChange={(e) => /^[0-9]*[.,]?[0-9]*$/.test(e.target.value) && cambiarCampo({ altura: e.target.value })}
              />
            </label>
          </div>
          <div className="opciones__fila" role="group" aria-label="Tipo de muro de la plantilla">
            {(catalogo.data?.tipos ?? []).map((t) => (
              <button
                key={t.clave}
                type="button"
                className={borrador.tipo === t.clave ? 'chip is-active' : 'chip'}
                aria-pressed={borrador.tipo === t.clave}
                disabled={!editable}
                title={t.descripcion}
                onClick={() => cambiarTipo(t.clave as TipoDeMuro)}
              >
                {t.nombre}
              </button>
            ))}
          </div>
          {tipoFicha && <p className="text-mute text-xs">{tipoFicha.descripcion}</p>}
          {borrador.tipo === 'confinado' && (
            <div className="mct__parametros" role="group" aria-label="Datos del prototipo">
              <label className="mct__campo">
                Prototipo
                <select
                  className="input"
                  aria-label="Prototipo de la plantilla"
                  value={borrador.prototipo}
                  disabled={!editable}
                  onChange={(e) => {
                    const ficha = (prototipos.data ?? []).find((x) => x.clave === e.target.value);
                    cambiarCampo({ prototipo: e.target.value, planta: ficha && !ficha.es_global ? 'PB' : '' });
                  }}
                >
                  <option value="">Ninguno (plantilla general)</option>
                  {(prototipos.data ?? []).map((x) => (
                    <option key={x.clave} value={x.clave}>
                      {x.nombre}
                    </option>
                  ))}
                </select>
              </label>
              {borrador.prototipo !== '' && !borrador.prototipo.startsWith('global_') && (
                <label className="mct__campo">
                  Planta
                  <select
                    className="input"
                    aria-label="Planta de la plantilla"
                    value={borrador.planta}
                    disabled={!editable}
                    onChange={(e) => cambiarCampo({ planta: e.target.value as Planta })}
                  >
                    {((prototipos.data ?? []).find((x) => x.clave === borrador.prototipo)?.plantas ?? 2) >= 2 ? (
                      <>
                        <option value="PB">Planta baja (PB)</option>
                        <option value="PA">Planta alta (PA)</option>
                      </>
                    ) : (
                      <option value="PB">Planta baja (PB)</option>
                    )}
                  </select>
                </label>
              )}
              <label className="mct__manual">
                <input
                  type="checkbox"
                  aria-label="Datos por confirmar"
                  checked={borrador.porConfirmar}
                  disabled={!editable}
                  onChange={(e) => cambiarCampo({ porConfirmar: e.target.checked })}
                />
                Datos por confirmar
              </label>
            </div>
          )}
          <label className="mct__campo">
            Notas (de dónde salen los datos)
            <textarea
              className="input"
              aria-label="Notas de la plantilla"
              rows={borrador.notas ? 6 : 2}
              maxLength={6000}
              value={borrador.notas}
              disabled={!editable}
              onChange={(e) => cambiarCampo({ notas: e.target.value })}
            />
          </label>
        </div>

        <div className="mct__bloque">
          <h3>Partes de altura y caras</h3>
          <p className="text-mute text-xs">
            La cara A es la izquierda del sentido de dibujo y la B, la derecha. Cambiar la cara de una parte vuelve personalizada la ubicación.
          </p>
          {borrador.partes.length > 0 && (
            <div className="mct__tabla-caja">
              <table className="mct__tabla" aria-label="Partes de altura">
                <thead>
                  <tr>
                    <th>Parte</th>
                    <th>Desde (m)</th>
                    <th>Hasta (m)</th>
                    <th>Rol</th>
                    <th>Cara A</th>
                    <th>Cara B</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {borrador.partes.map((p, i) => (
                    <tr key={i} data-parte={i}>
                      <td>
                        <input className="input" aria-label={`Nombre de la parte ${i + 1}`} value={p.nombre} maxLength={40} disabled={!editable} onChange={(e) => cambiarParte(i, { nombre: e.target.value })} />
                      </td>
                      <td>
                        <input className="input" inputMode="decimal" aria-label={`Desde de la parte ${i + 1}`} value={p.desde} disabled={!editable} onChange={(e) => /^[0-9]*[.,]?[0-9]*$/.test(e.target.value) && cambiarParte(i, { desde: e.target.value })} />
                      </td>
                      <td>
                        <input className="input" inputMode="decimal" aria-label={`Hasta de la parte ${i + 1}`} value={p.hasta} disabled={!editable} onChange={(e) => /^[0-9]*[.,]?[0-9]*$/.test(e.target.value) && cambiarParte(i, { hasta: e.target.value })} />
                      </td>
                      <td>
                        <select className="input" aria-label={`Rol de la parte ${i + 1}`} value={p.rol} disabled={!editable} onChange={(e) => cambiarParte(i, { rol: e.target.value as RolDeParte | '' })}>
                          <option value="">—</option>
                          {ROLES_DE_PARTE.map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <select className="input" aria-label={`Cara A de la parte ${i + 1}`} value={p.caraA} disabled={!editable} onChange={(e) => cambiarParte(i, { caraA: e.target.value as ParteBorrador['caraA'] })}>
                          {CARAS.map(([v, n]) => (
                            <option key={v} value={v}>
                              {n}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <select className="input" aria-label={`Cara B de la parte ${i + 1}`} value={p.caraB} disabled={!editable} onChange={(e) => cambiarParte(i, { caraB: e.target.value as ParteBorrador['caraB'] })}>
                          {CARAS.map(([v, n]) => (
                            <option key={v} value={v}>
                              {n}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        {editable && (
                          <button type="button" className="btn btn--sm" aria-label={`Quitar la parte ${i + 1}`} onClick={() => setBorrador((b) => ({ ...b, partes: b.partes.filter((_, k) => k !== i) }))}>
                            ×
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {editable && (
            <div>
              <button
                type="button"
                className="btn btn--sm"
                onClick={() =>
                  setBorrador((b) => {
                    const ultimo = b.partes[b.partes.length - 1];
                    const desde = ultimo ? ultimo.hasta : '0';
                    return { ...b, partes: [...b.partes, { nombre: '', desde, hasta: '', rol: '', caraA: '', caraB: '' }] };
                  })
                }
              >
                + Parte de altura
              </button>
            </div>
          )}
        </div>

        <div className="mct__bloque">
          <h3>Elementos de la plantilla</h3>
          <p className="text-mute text-xs">
            Cada uno se enlaza a sus conceptos. {borrador.tipo === 'tabique' ? 'Un muro de tabique no lleva castillos ni cadenas.' : ''}
          </p>
          {borrador.elementos.length === 0 && <p className="text-mute text-sm">Sin elementos: solo la mampostería del material.</p>}
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 6 }} aria-label="Elementos de la plantilla">
            {borrador.elementos.map((e, i) => (
              <li key={e.uid} data-elemento={e.uid} className="mct__par">
                <strong className="mono">{e.uid}</strong>
                <span className="badge badge--outline">{e.clase === 'castillo' ? 'castillo' : e.clase === 'cadena' ? 'cadena' : 'muro'}</span>
                {e.clase === 'castillo' && (
                  <>
                    <span className="text-mute text-xs">{borrador.tipo === 'con_cadena' ? 'ubicado en el plano' : 'estimado'}</span>
                    <label className="text-xs">
                      Regla
                      <select
                        className="input"
                        aria-label={`Regla de ${e.uid}`}
                        value={e.regla}
                        disabled={!editable}
                        onChange={(ev) => cambiarElemento(i, { regla: ev.target.value as ReglaDeCastillo | '' })}
                      >
                        <option value="">{borrador.tipo === 'con_cadena' ? 'Extremos' : 'Separación de la obra'} (por defecto)</option>
                        {reglasDeCastillo(borrador.tipo).map((r) => (
                          <option key={r} value={r}>
                            {NOMBRE_DE_REGLA[r]}
                          </option>
                        ))}
                      </select>
                    </label>
                    {(e.regla === '' || e.regla === 'separacion') && (
                      <label className="text-xs">
                        Separación (m)
                        <input
                          className="input"
                          inputMode="decimal"
                          aria-label={`Separación de ${e.uid} (m)`}
                          placeholder={borrador.tipo === 'confinado' ? String(driversDeVista.separacion_m) : 'extremos'}
                          value={e.sep}
                          disabled={!editable}
                          onChange={(ev) => /^[0-9]*[.,]?[0-9]*$/.test(ev.target.value) && cambiarElemento(i, { sep: ev.target.value })}
                        />
                      </label>
                    )}
                    {e.regla === 'por_ml' && (
                      <label className="text-xs">
                        Piezas por ml de muro
                        <input
                          className="input"
                          inputMode="decimal"
                          aria-label={`Piezas por ml de ${e.uid}`}
                          value={e.piezasPorMl}
                          disabled={!editable}
                          onChange={(ev) => /^[0-9]*[.,]?[0-9]*$/.test(ev.target.value) && cambiarElemento(i, { piezasPorMl: ev.target.value })}
                        />
                      </label>
                    )}
                    {e.regla === 'total' && (
                      <>
                        <label className="text-xs">
                          Metros de castillo (total)
                          <input
                            className="input"
                            inputMode="decimal"
                            aria-label={`Metros totales de ${e.uid}`}
                            value={e.totalM}
                            disabled={!editable}
                            onChange={(ev) => /^[0-9]*[.,]?[0-9]*$/.test(ev.target.value) && cambiarElemento(i, { totalM: ev.target.value })}
                          />
                        </label>
                        <label className="text-xs">
                          Sobre m² de muro
                          <input
                            className="input"
                            inputMode="decimal"
                            aria-label={`m² de muro de la base de ${e.uid}`}
                            value={e.baseM2}
                            disabled={!editable}
                            onChange={(ev) => /^[0-9]*[.,]?[0-9]*$/.test(ev.target.value) && cambiarElemento(i, { baseM2: ev.target.value })}
                          />
                        </label>
                      </>
                    )}
                    {e.origen && (
                      <span className="text-mute text-xs mono" data-testid={`origen-de-${e.uid}`}>
                        {e.origen}
                      </span>
                    )}
                  </>
                )}
                {e.clase === 'cadena' && (
                  <label className="text-xs">
                    Posición
                    <select className="input" aria-label={`Posición de ${e.uid}`} value={e.posicion} disabled={!editable} onChange={(ev) => cambiarElemento(i, { posicion: ev.target.value as ElementoBorrador['posicion'] })}>
                      <option value="desplante">Desplante</option>
                      <option value="cerramiento">Cerramiento</option>
                      <option value="remate">Remate</option>
                    </select>
                  </label>
                )}
                {editable && (
                  <button type="button" className="btn btn--sm" aria-label={`Quitar ${e.uid}`} onClick={() => setBorrador((b) => ({ ...b, elementos: b.elementos.filter((_, k) => k !== i) }))}>
                    ×
                  </button>
                )}
              </li>
            ))}
          </ul>
          {editable && (
            <label className="mct__campo">
              Agregar un elemento
              <select
                className="input"
                aria-label="Agregar un elemento a la plantilla"
                value=""
                onChange={(e) => {
                  agregarElemento(e.target.value);
                }}
              >
                <option value="">Elige un elemento…</option>
                {opciones
                  .filter((o) => !(borrador.tipo === 'tabique' && o.clase !== 'muro'))
                  .map((o) => (
                    <option key={o.ref} value={o.ref}>
                      {o.ref} · {o.nombre}
                    </option>
                  ))}
              </select>
            </label>
          )}
        </div>

        <div className="mct__bloque">
          <h3>Vista previa</h3>
          <VistaPreviaDePlantilla g={geometria} aparente />
          <p className="text-mute text-xs">
            Tramo de muestra de 6 m. Un castillo «por ml» o «total» cuenta piezas con fracción (una estimación); aquí se dibujan redondeadas hacia arriba. Sin altura propia se dibuja con la de la herramienta de trazo ({driversDeVista.altura_m} m); un castillo
            estimado sin separación propia se reparte con la separación de castillos de la obra ({driversDeVista.separacion_m} m), y uno
            ubicado va en los extremos. La separación es un driver del Paramétrico{obraId === '' ? ' (sin obra elegida: valores de partida)' : ''}.
          </p>
        </div>

        {editable && (
          <div className="mct__par">
            <button type="button" className="btn btn--primary" disabled={ocupado || sinCambios} onClick={() => void guardar()}>
              {nueva ? 'Crear plantilla' : 'Guardar cambios'}
            </button>
            {guardada && guardada.trazos === 0 && (
              <button type="button" className="btn" disabled={ocupado} onClick={() => void borrarPlantilla()}>
                Borrar la plantilla
              </button>
            )}
            {guardada?.validacion === 'validada' && !sinCambios && (
              <span className="text-mute text-xs">Cambiarla creará una versión nueva por validar; los trazos ya medidos conservan la anterior.</span>
            )}
          </div>
        )}

        {guardada && (
          <div className="mct__bloque" role="group" aria-label="Validación contra la matriz">
            <h3>Validación contra la matriz de los conceptos</h3>
            {revision.isLoading && <p className="text-mute text-sm">Revisando…</p>}
            {revision.data && alertas.length === 0 && <p className="text-sm">Todo cuadra: no hay alertas.</p>}
            {alertas.length > 0 && (
              <ul className="mct__advertencias" aria-label="Alertas de la plantilla">
                {alertas.map((a, i) => (
                  <li key={i} data-codigo={a.codigo} data-nivel={a.nivel}>
                    {a.nivel === 'bloquea' ? 'Bloquea: ' : 'Por revisar: '}
                    {a.mensaje}
                  </li>
                ))}
              </ul>
            )}
            {guardada.validacion === 'validada' ? (
              <p className="text-sm">
                Validada por {guardada.validada_por_nombre ?? 'Control de obra'}
                {guardada.validada_en ? ` el ${new Date(guardada.validada_en).toLocaleDateString('es-MX')}` : ''}.
              </p>
            ) : puedeValidar && guardada.vigente ? (
              <div className="mct__par">
                {alertas.length > 0 && !bloquea && (
                  <label className="mct__manual">
                    <input type="checkbox" checked={aceptar} onChange={(e) => setAceptar(e.target.checked)} />
                    Acepto las alertas por revisar
                  </label>
                )}
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={ocupado || bloquea || !sinCambios || (alertas.length > 0 && !aceptar)}
                  onClick={() => void validarPlantilla()}
                >
                  Validar la plantilla
                </button>
                {!sinCambios && <span className="text-mute text-xs">Guarda los cambios antes de validar.</span>}
              </div>
            ) : (
              <p className="text-mute text-sm">Por validar: solo Control de obra la valida contra la matriz.</p>
            )}
          </div>
        )}

        {versiones.data && versiones.data.length > 1 && (
          <div className="mct__bloque">
            <h3>Versiones</h3>
            <ul style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 2 }} aria-label="Versiones de la plantilla">
              {versiones.data.map((v) => (
                <li key={v.id} className="text-sm">
                  <button type="button" className="chip" aria-current={v.id === idGuardada ? 'true' : undefined} onClick={() => onElegir(v.id)}>
                    Versión {v.version}
                  </button>{' '}
                  {v.validacion === 'validada' ? 'validada' : 'por validar'}
                  {v.vigente ? ' · vigente' : ''}
                  {v.trazos > 0 ? ` · ${v.trazos} trazos` : ''}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
