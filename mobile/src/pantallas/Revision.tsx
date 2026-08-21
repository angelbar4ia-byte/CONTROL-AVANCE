/**
 * Revisión física de Control de obra (§5.2, §7.8 `RevisionFisica`, §12.5).
 *
 * Junto con la captura de avance, es la **otra** cosa que el §12.5 exige que
 * funcione sin señal, y la razón es la misma: pasa parado frente al muro.
 *
 * Por eso escribe directo en la réplica SQLite y sube por PowerSync, no por
 * la API. A diferencia de una incidencia, aquí no hay efecto colateral que se
 * pierda: `revision_fisica` es una entidad propia (§7.8), no dispara bloqueos
 * ni replanea el CPM, y su estrategia de conflictos es "acumular" —dos
 * revisiones de la misma actividad son dos hechos distintos, no dos versiones
 * del mismo—.
 *
 * Las fotos siguen su propia cola (§12.5): la revisión se guarda al instante
 * con `fotos = []` y las claves se cosen encima conforme suben. Así el
 * comentario y la calificación existen desde el primer segundo, aunque la
 * evidencia tarde en salir.
 */

import { useState } from 'react';
import { FlatList, Pressable, Text, View } from 'react-native';
import { usePowerSync, useQuery } from '@powersync/react-native';

import type { FotoTomada } from '@/evidencias/captura';
import { encolar as encolarFoto } from '@/evidencias/cola';
import { generarId } from '@/lib/id';
import { useSesion } from '@/lib/sesion';
import { useEmpujarSalida } from '@/salida/ProveedorSalida';
import { Barra } from '@/ui/Barra';
import { Encabezado } from '@/ui/Encabezado';
import { Estatus } from '@/ui/Estatus';
import { Fotos } from '@/ui/Fotos';
import { Acciones, Aviso, Campo, Cargando, Hoja, Opciones, Vacio } from '@/ui/Formulario';

/**
 * Escala de calidad: 1 a 5, la misma que el backend
 * (`domain/revisiones/reglas.py`, `CALIDAD_MINIMA`/`CALIDAD_MAXIMA`) y la
 * misma que el `CHECK` de la migración 0009. Aquí solo se le ponen etiquetas
 * en español; los números no se inventan de este lado, o una revisión
 * capturada en campo sería rechazada al sincronizar.
 */
export const CALIDADES = [
  { valor: '1', texto: '1 · Rehacer' },
  { valor: '2', texto: '2 · Deficiente' },
  { valor: '3', texto: '3 · Aceptable' },
  { valor: '4', texto: '4 · Bueno' },
  { valor: '5', texto: '5 · Excelente' },
] as const;

type Calidad = (typeof CALIDADES)[number]['valor'];

interface FilaActividad {
  id: string;
  obra_id: string;
  obra_clave: string | null;
  descripcion: string;
  estatus: string;
  avance_pct: number;
  revisiones: number;
  ultima_calidad: number | null;
}

/**
 * Se listan las actividades con avance —lo que no se ha empezado no se puede
 * revisar físicamente— y arriba las que nadie ha revisado todavía: en una obra
 * de doscientas actividades, lo que falta es lo que hay que encontrar rápido.
 */
const CONSULTA = `
  SELECT a.id, a.obra_id, a.descripcion, a.estatus, a.avance_pct,
         o.clave AS obra_clave,
         (SELECT COUNT(*) FROM revision_fisica r
           WHERE r.actividad_id = a.id) AS revisiones,
         (SELECT r.calidad FROM revision_fisica r
           WHERE r.actividad_id = a.id
           ORDER BY r.fecha DESC LIMIT 1) AS ultima_calidad
    FROM actividad a
    LEFT JOIN obra o ON o.id = a.obra_id
   WHERE a.avance_pct > 0
   ORDER BY revisiones ASC, a.avance_pct DESC
`;

export function Revision() {
  const db = usePowerSync();
  const { sesion } = useSesion();
  const empujar = useEmpujarSalida();

  const { data: actividades, isLoading } = useQuery<FilaActividad>(CONSULTA);
  const [seleccionada, setSeleccionada] = useState<FilaActividad | null>(null);

  const [calidad, setCalidad] = useState<Calidad>('3');
  const [comentario, setComentario] = useState('');
  const [fotos, setFotos] = useState<FotoTomada[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  function abrir(actividad: FilaActividad) {
    setSeleccionada(actividad);
    setCalidad('3');
    setComentario('');
    setFotos([]);
    setError(null);
  }

  async function guardar() {
    if (!seleccionada || !sesion) return;

    setError(null);
    setGuardando(true);

    try {
      const id = generarId();
      const ahora = new Date().toISOString();

      await db.execute(
        `INSERT INTO revision_fisica
           (id, org_id, obra_id, actividad_id, usuario_id, fecha, fotos,
            comentario, calidad, sync_status)
         VALUES (?, ?, ?, ?, ?, ?, '[]', ?, ?, 'pendiente')`,
        [
          id,
          sesion.orgId,
          seleccionada.obra_id,
          seleccionada.id,
          sesion.usuarioId,
          ahora,
          comentario.trim(),
          Number(calidad),
        ],
      );

      // Las fotos van aparte y se cosen sobre `revision_fisica.fotos` cuando
      // suben (§12.5). La revisión ya existe sin ellas: el juicio de calidad
      // es el dato, la foto es su respaldo.
      for (const foto of fotos) {
        await encolarFoto(db, {
          entidad: 'revision_fisica',
          entidadId: id,
          obraId: seleccionada.obra_id,
          uri: foto.uri,
          nombre: foto.nombre,
          contentType: foto.contentType,
        });
      }

      setSeleccionada(null);
      empujar();
    } catch {
      setError('No se pudo guardar la revisión en el dispositivo. Intenta de nuevo.');
    } finally {
      setGuardando(false);
    }
  }

  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Encabezado
        eyebrow="Control de obra"
        titulo="Revisión"
        descripcion="Califica el trabajo en sitio. Funciona sin señal (§7.8, §12.5)."
      />

      {isLoading ? (
        <Cargando />
      ) : (
        <FlatList
          data={actividades}
          keyExtractor={(item) => item.id}
          ListEmptyComponent={<Vacio texto="No hay actividades con avance para revisar." />}
          renderItem={({ item }) => (
            <Pressable
              testID="actividad"
              onPress={() => abrir(item)}
              className="mb-3 rounded-lg border border-line bg-surface p-4 active:opacity-70"
            >
              <View className="flex-row items-start justify-between gap-3">
                <View className="flex-1">
                  {item.obra_clave ? (
                    <Text className="font-mono text-xs text-text-faint">{item.obra_clave}</Text>
                  ) : null}
                  <Text className="text-base text-text">{item.descripcion}</Text>
                </View>
                <Estatus valor={item.estatus} />
              </View>

              <View className="mt-3">
                <Barra pct={item.avance_pct} />
              </View>

              <View className="mt-2 flex-row items-center justify-between">
                <Text className="text-xs text-text-mute">
                  {item.revisiones === 0
                    ? 'Sin revisar'
                    : `${item.revisiones} revisión${item.revisiones === 1 ? '' : 'es'} · última ${item.ultima_calidad ?? '—'}/5`}
                </Text>
                <Text className="font-mono text-sm text-text">{item.avance_pct}%</Text>
              </View>
            </Pressable>
          )}
        />
      )}

      <Hoja
        visible={seleccionada !== null}
        titulo={seleccionada?.descripcion ?? ''}
        subtitulo={seleccionada ? `Avance ${seleccionada.avance_pct}%` : undefined}
        onCerrar={() => (guardando ? undefined : setSeleccionada(null))}
      >
        <Opciones
          etiqueta="Calidad del trabajo"
          opciones={CALIDADES}
          valor={calidad}
          onCambio={setCalidad}
          deshabilitado={guardando}
        />
        <Campo
          testID="comentario"
          etiqueta="Comentario"
          valor={comentario}
          onCambio={setComentario}
          placeholder="Qué se observó en sitio"
          editable={!guardando}
          multilinea
        />

        <View className="mt-3">
          <Text className="mb-1 text-sm text-text-soft">Fotos</Text>
          <Fotos fotos={fotos} onCambio={setFotos} deshabilitado={guardando} maximo={8} />
        </View>

        <Aviso mensaje={error} />
        <Acciones
          onCancelar={() => setSeleccionada(null)}
          onConfirmar={() => void guardar()}
          ocupado={guardando}
          textoConfirmar="Registrar revisión"
        />
      </Hoja>
    </View>
  );
}
