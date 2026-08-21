/**
 * Incidencias en campo — pantalla compartida (§5.3, §7.8, §11.3 F).
 *
 * El §5.3 manda: *se implementa una sola vez y cambia comportamiento por rol*.
 * Residente y Supervisor ven la misma lista con el mismo alcance —el que
 * definen las sync rules, espejo de RLS— y difieren en lo que pueden hacer:
 *
 * | rol         | qué puede |
 * |-------------|-----------|
 * | residente   | abrir una incidencia (§11.3 F.1) |
 * | supervisor  | atender, cerrar y rechazar (§11.3 F.3, F.4) |
 *
 * ## Lectura local, escritura por la API
 *
 * La **lista** sale de la réplica SQLite: en campo, sin señal, el residente
 * tiene que poder ver qué está detenido. Las **acciones** viajan por la
 * bandeja de salida (`salida/bandeja.ts`), no por PowerSync, y la razón está
 * en el §11.3 F.5: abrir con `impacto=detiene` bloquea actividades y replanea
 * el CPM. Un `INSERT` directo crearía la incidencia sin bloquear nada, y una
 * obra que se ve libre estando detenida es peor que un error visible.
 *
 * Lo capturado sin señal aparece de inmediato en la lista, marcado como "por
 * enviar", y lo sustituye la incidencia real cuando baja por sync. Sin eso, el
 * residente la capturaría dos veces.
 */

import { useState } from 'react';
import { FlatList, Pressable, Text, View } from 'react-native';
import { usePowerSync, useQuery } from '@powersync/react-native';

import { encolar as encolarFoto } from '@/evidencias/cola';
import type { FotoTomada } from '@/evidencias/captura';
import { useSesion } from '@/lib/sesion';
import { encolar as encolarOperacion } from '@/salida/bandeja';
import { useEmpujarSalida } from '@/salida/ProveedorSalida';
import { Encabezado } from '@/ui/Encabezado';
import { Fotos } from '@/ui/Fotos';
import { Acciones, Aviso, Campo, Cargando, Hoja, Opciones, Vacio } from '@/ui/Formulario';

/** §8.2 — `incidencia.tipo`. */
const TIPOS = [
  { valor: 'falta_material', texto: 'Falta material' },
  { valor: 'error_ejecucion', texto: 'Error de ejecución' },
  { valor: 'cambio_cliente', texto: 'Cambio del cliente' },
  { valor: 'proyecto_indef', texto: 'Proyecto indefinido' },
  { valor: 'retrabajo', texto: 'Retrabajo' },
  { valor: 'detalle', texto: 'Detalle' },
] as const;

/** §8.2 — `incidencia.impacto`. §6: `detiene` frena la obra. */
const IMPACTOS = [
  { valor: 'detalle', texto: 'Detalle' },
  { valor: 'retraso', texto: 'Retraso' },
  { valor: 'detiene', texto: 'Detiene la obra' },
] as const;

type Tipo = (typeof TIPOS)[number]['valor'];
type Impacto = (typeof IMPACTOS)[number]['valor'];

const ETIQUETA_ESTATUS: Readonly<Record<string, string>> = {
  abierta: 'Abierta',
  programada: 'Programada',
  en_atencion: 'En atención',
  cierre_solicitado: 'Cierre solicitado',
  cerrada: 'Cerrada',
  rechazada: 'Rechazada',
};

interface FilaIncidencia {
  id: string;
  obra_id: string;
  obra_clave: string | null;
  titulo: string;
  descripcion: string | null;
  tipo: string;
  impacto: string;
  estatus: string;
  fecha_creada: string;
}

interface FilaObra {
  id: string;
  clave: string;
}

interface FilaPendiente {
  id: string;
  etiqueta: string;
  estado: string;
  error: string | null;
}

/**
 * Abiertas primero y recientes arriba: en una obra con cincuenta incidencias
 * históricas, lo que se necesita ver al abrir la app es lo que sigue sin
 * resolverse.
 */
const CONSULTA = `
  SELECT i.id, i.obra_id, i.titulo, i.descripcion, i.tipo, i.impacto,
         i.estatus, i.fecha_creada, o.clave AS obra_clave
    FROM incidencia i
    LEFT JOIN obra o ON o.id = i.obra_id
   ORDER BY (i.estatus IN ('cerrada', 'rechazada')) ASC, i.fecha_creada DESC
`;

const CONSULTA_OBRAS = 'SELECT id, clave FROM obra ORDER BY clave';

const CONSULTA_PENDIENTES = `
  SELECT id, etiqueta, estado, error
    FROM operacion_pendiente
   WHERE ruta = '/api/v1/incidencias' AND estado != 'enviada'
   ORDER BY creada_en DESC
`;

type Papel = 'residente' | 'supervisor';

export function Incidencias({ papel }: { readonly papel: Papel }) {
  const db = usePowerSync();
  const { sesion } = useSesion();
  const empujar = useEmpujarSalida();

  const { data: incidencias, isLoading } = useQuery<FilaIncidencia>(CONSULTA);
  const { data: obras } = useQuery<FilaObra>(CONSULTA_OBRAS);
  const { data: porEnviar } = useQuery<FilaPendiente>(CONSULTA_PENDIENTES);

  const [abriendo, setAbriendo] = useState(false);
  const [enAccion, setEnAccion] = useState<FilaIncidencia | null>(null);

  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Encabezado
        eyebrow={papel === 'residente' ? 'Residente' : 'Supervisor'}
        titulo="Incidencias"
        descripcion={
          papel === 'residente'
            ? 'Levanta lo que detiene la obra; sale en cuanto haya señal (§11.3 F).'
            : 'Atiende, cierra o rechaza lo que reporta el campo (§11.3 F).'
        }
      />

      {papel === 'residente' ? (
        <Pressable
          onPress={() => setAbriendo(true)}
          className="mb-3 h-fila items-center justify-center rounded-md bg-accent active:opacity-80"
        >
          <Text className="text-base font-medium text-accent-fg">Nueva incidencia</Text>
        </Pressable>
      ) : null}

      {isLoading ? (
        <Cargando />
      ) : (
        <FlatList
          data={incidencias}
          keyExtractor={(item) => item.id}
          ListHeaderComponent={<PorEnviar filas={porEnviar ?? []} />}
          ListEmptyComponent={<Vacio texto="No hay incidencias en tus obras." />}
          renderItem={({ item }) => (
            <Pressable
              onPress={() => (papel === 'supervisor' ? setEnAccion(item) : undefined)}
              disabled={papel !== 'supervisor' || esCerrada(item.estatus)}
              className="mb-3 rounded-lg border border-line bg-surface p-4 active:opacity-70"
            >
              <View className="flex-row items-start justify-between gap-3">
                <View className="flex-1">
                  {item.obra_clave ? (
                    <Text className="font-mono text-xs text-text-faint">{item.obra_clave}</Text>
                  ) : null}
                  <Text className="text-base text-text">{item.titulo}</Text>
                </View>
                <ChipImpacto impacto={item.impacto} />
              </View>

              {item.descripcion ? (
                <Text className="mt-2 text-sm text-text-mute" numberOfLines={2}>
                  {item.descripcion}
                </Text>
              ) : null}

              <View className="mt-3 flex-row items-center justify-between">
                <Text className="text-xs text-text-mute">
                  {ETIQUETA_ESTATUS[item.estatus] ?? item.estatus} ·{' '}
                  {etiquetaTipo(item.tipo)}
                </Text>
                <Text className="font-mono text-xs text-text-faint">
                  {item.fecha_creada.slice(0, 10)}
                </Text>
              </View>
            </Pressable>
          )}
        />
      )}

      <FormularioAlta
        visible={abriendo}
        obras={obras ?? []}
        onCerrar={() => setAbriendo(false)}
        onGuardar={async (datos) => {
          if (!sesion) return;

          // Las fotos se encolan sin dueño: el id de la incidencia lo asigna
          // el servidor, y sus claves se inyectan en el cuerpo del POST
          // cuando la operación sale (`salida/bandeja.ts`).
          const fotos: string[] = [];
          for (const foto of datos.fotos) {
            fotos.push(
              await encolarFoto(db, {
                entidad: 'ninguna',
                entidadId: '',
                obraId: datos.obraId,
                uri: foto.uri,
                nombre: foto.nombre,
                contentType: foto.contentType,
              }),
            );
          }

          await encolarOperacion(db, {
            ruta: '/api/v1/incidencias',
            cuerpo: {
              obra_id: datos.obraId,
              tipo: datos.tipo,
              impacto: datos.impacto,
              titulo: datos.titulo,
              descripcion: datos.descripcion || null,
            },
            etiqueta: `Incidencia: ${datos.titulo}`,
            obraId: datos.obraId,
            fotos,
          });

          setAbriendo(false);
          empujar();
        }}
      />

      <FormularioAccion
        incidencia={enAccion}
        onCerrar={() => setEnAccion(null)}
        onGuardar={async (incidencia, accion, comentario) => {
          await encolarOperacion(db, ruta(incidencia, accion, comentario));
          setEnAccion(null);
          empujar();
        }}
      />
    </View>
  );
}

function esCerrada(estatus: string): boolean {
  return estatus === 'cerrada' || estatus === 'rechazada';
}

function etiquetaTipo(valor: string): string {
  return TIPOS.find((t) => t.valor === valor)?.texto ?? valor;
}

/**
 * El impacto es lo primero que se lee: es lo que dice si hay que ir corriendo
 * (§6). Por eso va en la esquina y con color, no dentro del cuerpo del texto.
 */
function ChipImpacto({ impacto }: { readonly impacto: string }) {
  const estilo =
    impacto === 'detiene'
      ? { fondo: 'bg-danger-soft', texto: 'text-danger' }
      : impacto === 'retraso'
        ? { fondo: 'bg-warn-soft', texto: 'text-warn' }
        : { fondo: 'bg-elev', texto: 'text-text-mute' };

  const etiqueta = IMPACTOS.find((i) => i.valor === impacto)?.texto ?? impacto;

  return (
    <View className={`rounded-full px-2 py-1 ${estilo.fondo}`}>
      <Text className={`text-xs ${estilo.texto}`}>{etiqueta}</Text>
    </View>
  );
}

/** Lo capturado que aún no sale del teléfono, arriba de la lista real. */
function PorEnviar({ filas }: { readonly filas: readonly FilaPendiente[] }) {
  if (filas.length === 0) return null;

  return (
    <View className="mb-3 rounded-lg border border-line-strong bg-panel p-4">
      <Text className="font-mono text-xs uppercase text-text-faint">Por enviar</Text>
      {filas.map((fila) => (
        <View key={fila.id} className="mt-2">
          <Text className="text-base text-text">{fila.etiqueta}</Text>
          <Text className={`text-xs ${fila.estado === 'fallida' ? 'text-danger' : 'text-warn'}`}>
            {fila.estado === 'fallida'
              ? (fila.error ?? 'No se pudo enviar.')
              : 'Se enviará en cuanto haya señal.'}
          </Text>
        </View>
      ))}
    </View>
  );
}

interface DatosAlta {
  readonly obraId: string;
  readonly tipo: Tipo;
  readonly impacto: Impacto;
  readonly titulo: string;
  readonly descripcion: string;
  readonly fotos: readonly FotoTomada[];
}

function FormularioAlta({
  visible,
  obras,
  onCerrar,
  onGuardar,
}: {
  readonly visible: boolean;
  readonly obras: readonly FilaObra[];
  readonly onCerrar: () => void;
  readonly onGuardar: (datos: DatosAlta) => Promise<void>;
}) {
  const [obraId, setObraId] = useState('');
  const [tipo, setTipo] = useState<Tipo>('falta_material');
  const [impacto, setImpacto] = useState<Impacto>('detalle');
  const [titulo, setTitulo] = useState('');
  const [descripcion, setDescripcion] = useState('');
  const [fotos, setFotos] = useState<FotoTomada[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  const obraElegida = obraId || obras[0]?.id || '';

  async function guardar() {
    if (!obraElegida) {
      setError('No hay obras en el dispositivo todavía.');
      return;
    }
    if (!titulo.trim()) {
      setError('Escribe un título: es lo que se lee en la bandeja.');
      return;
    }

    setError(null);
    setGuardando(true);
    try {
      await onGuardar({
        obraId: obraElegida,
        tipo,
        impacto,
        titulo: titulo.trim(),
        descripcion: descripcion.trim(),
        fotos,
      });
      setTitulo('');
      setDescripcion('');
      setFotos([]);
      setImpacto('detalle');
    } catch {
      setError('No se pudo guardar en el dispositivo. Intenta de nuevo.');
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Hoja visible={visible} titulo="Nueva incidencia" onCerrar={onCerrar}>
      <Opciones
        etiqueta="Obra"
        opciones={obras.map((o) => ({ valor: o.id, texto: o.clave }))}
        valor={obraElegida}
        onCambio={setObraId}
        deshabilitado={guardando}
      />
      <Opciones
        etiqueta="Tipo (§8.2)"
        opciones={TIPOS}
        valor={tipo}
        onCambio={setTipo}
        deshabilitado={guardando}
      />
      <Opciones
        etiqueta="Impacto (§6)"
        opciones={IMPACTOS}
        valor={impacto}
        onCambio={setImpacto}
        deshabilitado={guardando}
      />
      {impacto === 'detiene' ? (
        <Text className="mt-2 text-xs text-danger">
          Detener la obra bloquea sus actividades y replanea la ruta crítica (§11.3 F.5). Las actividades
          concretas las elige Supervisión desde la web.
        </Text>
      ) : null}

      <Campo
        testID="titulo"
        etiqueta="Título"
        valor={titulo}
        onCambio={setTitulo}
        editable={!guardando}
      />
      <Campo
        testID="descripcion"
        etiqueta="Descripción (opcional)"
        valor={descripcion}
        onCambio={setDescripcion}
        editable={!guardando}
        multilinea
      />

      <View className="mt-3">
        <Text className="mb-1 text-sm text-text-soft">Evidencia</Text>
        <Fotos fotos={fotos} onCambio={setFotos} deshabilitado={guardando} maximo={5} />
      </View>

      <Aviso mensaje={error} />
      <Acciones onCancelar={onCerrar} onConfirmar={() => void guardar()} ocupado={guardando} />
    </Hoja>
  );
}

type Accion = 'atender' | 'cerrar' | 'rechazar';

const ACCIONES = [
  { valor: 'atender', texto: 'Atender' },
  { valor: 'cerrar', texto: 'Cerrar' },
  { valor: 'rechazar', texto: 'Rechazar' },
] as const;

/**
 * Cada acción tiene su endpoint porque cada una es un caso de uso distinto
 * (§11.3 F.3, F.4): cerrar desbloquea actividades y rechazar también, pero por
 * motivos distintos y con auditoría distinta.
 */
function ruta(
  incidencia: FilaIncidencia,
  accion: Accion,
  comentario: string,
): Parameters<typeof encolarOperacion>[1] {
  const base = `/api/v1/incidencias/${incidencia.id}`;
  const etiqueta = `${ACCIONES.find((a) => a.valor === accion)?.texto}: ${incidencia.titulo}`;

  if (accion === 'cerrar') {
    return { ruta: `${base}/cerrar`, cuerpo: { comentario: comentario || null }, etiqueta, obraId: incidencia.obra_id };
  }
  if (accion === 'rechazar') {
    return { ruta: `${base}/rechazar`, cuerpo: { motivo: comentario }, etiqueta, obraId: incidencia.obra_id };
  }
  return {
    ruta: `${base}/eventos`,
    cuerpo: { accion: 'atender', estatus_nuevo: 'en_atencion', comentario: comentario || null },
    etiqueta,
    obraId: incidencia.obra_id,
  };
}

function FormularioAccion({
  incidencia,
  onCerrar,
  onGuardar,
}: {
  readonly incidencia: FilaIncidencia | null;
  readonly onCerrar: () => void;
  readonly onGuardar: (i: FilaIncidencia, accion: Accion, comentario: string) => Promise<void>;
}) {
  const [accion, setAccion] = useState<Accion>('atender');
  const [comentario, setComentario] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  async function guardar() {
    if (!incidencia) return;
    if (accion === 'rechazar' && !comentario.trim()) {
      // El motivo es obligatorio en el contrato (§11.3 F.4): validarlo aquí
      // evita que la operación viaje para volver con un 422 dos horas después,
      // cuando ya nadie recuerda qué se quiso rechazar.
      setError('Rechazar exige un motivo.');
      return;
    }

    setError(null);
    setGuardando(true);
    try {
      await onGuardar(incidencia, accion, comentario.trim());
      setComentario('');
      setAccion('atender');
    } catch {
      setError('No se pudo guardar en el dispositivo. Intenta de nuevo.');
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Hoja
      visible={incidencia !== null}
      titulo={incidencia?.titulo ?? ''}
      subtitulo={incidencia ? ETIQUETA_ESTATUS[incidencia.estatus] : undefined}
      onCerrar={onCerrar}
    >
      <Opciones
        etiqueta="Acción"
        opciones={ACCIONES}
        valor={accion}
        onCambio={setAccion}
        deshabilitado={guardando}
      />
      <Campo
        testID="comentario"
        etiqueta={accion === 'rechazar' ? 'Motivo' : 'Comentario (opcional)'}
        valor={comentario}
        onCambio={setComentario}
        editable={!guardando}
        multilinea
      />
      <Aviso mensaje={error} />
      <Acciones
        onCancelar={onCerrar}
        onConfirmar={() => void guardar()}
        ocupado={guardando}
        textoConfirmar="Registrar"
      />
    </Hoja>
  );
}
