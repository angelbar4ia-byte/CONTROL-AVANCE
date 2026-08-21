/**
 * Ruta crítica en campo — pantalla compartida (§5.3, §7.5, §11.3 A).
 *
 * Solo lectura, y a propósito: el CPM lo calcula el backend con el grafo
 * completo de dependencias (§11.1), y el teléfono no tiene ese grafo —las
 * sync rules bajan `actividad` con su `es_critica` y su `holgura` ya
 * resueltas, no `dependencia`—. Recalcular aquí daría otro número que el de
 * la web, que es exactamente lo que el §11.1 prohíbe: una sola fuente de
 * verdad para el cálculo.
 *
 * Lo que sí resuelve la pantalla es la pregunta de campo: *de lo que tengo
 * hoy, ¿qué no puede esperar?*. Críticas primero, luego por holgura, y
 * arriba el número que decide la jornada.
 *
 * Residente y Supervisor la comparten (§5.3). Lo que cambia es el alcance, y
 * ese ya viene resuelto: cada uno tiene en su réplica solo sus obras, con el
 * mismo criterio que RLS (`sync-rules.yaml`).
 */

import { FlatList, Text, View } from 'react-native';
import { useQuery } from '@powersync/react-native';

import { Barra } from '@/ui/Barra';
import { Encabezado } from '@/ui/Encabezado';
import { Estatus } from '@/ui/Estatus';
import { Cargando, Vacio } from '@/ui/Formulario';

interface FilaActividad {
  id: string;
  descripcion: string;
  obra_clave: string | null;
  estatus: string;
  avance_pct: number;
  holgura: number | null;
  es_critica: number | null;
  bloqueada: number | null;
  fecha_termino: string | null;
}

/**
 * Se excluyen las concluidas: una actividad crítica ya terminada no compite
 * por la jornada de nadie, y dejarla en la lista empuja hacia abajo lo que sí.
 *
 * El orden es el de la urgencia real: crítica antes que holgada, y dentro de
 * cada grupo la que vence primero. `fecha_termino` puede ser nula en una
 * actividad extra-catálogo aún sin programar (§11.3 G) — `COALESCE` la manda
 * al final en vez de dejar que SQLite decida.
 */
const CONSULTA = `
  SELECT a.id, a.descripcion, a.estatus, a.avance_pct, a.holgura,
         a.es_critica, a.bloqueada, a.fecha_termino, o.clave AS obra_clave
    FROM actividad a
    LEFT JOIN obra o ON o.id = a.obra_id
   WHERE a.estatus != 'concluida'
   ORDER BY a.es_critica DESC,
            COALESCE(a.holgura, 9999) ASC,
            COALESCE(a.fecha_termino, '9999-12-31') ASC
`;

type Papel = 'residente' | 'supervisor';

export function Ruta({ papel }: { readonly papel: Papel }) {
  const { data: actividades, isLoading } = useQuery<FilaActividad>(CONSULTA);

  const criticas = (actividades ?? []).filter((a) => a.es_critica === 1).length;
  const bloqueadas = (actividades ?? []).filter((a) => a.bloqueada === 1).length;

  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Encabezado
        eyebrow={papel === 'residente' ? 'Residente' : 'Supervisor'}
        titulo="Ruta crítica"
        descripcion="Lo que no puede esperar. El CPM lo calcula el servidor (§11.1)."
      />

      <View className="mb-3 flex-row gap-3">
        <Indicador etiqueta="Críticas" valor={criticas} tono="danger" />
        <Indicador etiqueta="Bloqueadas" valor={bloqueadas} tono="warn" />
        <Indicador etiqueta="Abiertas" valor={actividades?.length ?? 0} tono="neutro" />
      </View>

      {isLoading ? (
        <Cargando />
      ) : (
        <FlatList
          data={actividades}
          keyExtractor={(item) => item.id}
          ListEmptyComponent={<Vacio texto="No hay actividades abiertas en tus obras." />}
          renderItem={({ item }) => (
            <View className="mb-3 rounded-lg border border-line bg-surface p-4">
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
                  {item.es_critica === 1 ? 'Crítica · sin holgura' : `Holgura ${item.holgura ?? 0} d`}
                </Text>
                <Text className="font-mono text-xs text-text-faint">
                  {item.fecha_termino ?? 'sin programar'}
                </Text>
              </View>

              {item.bloqueada === 1 ? (
                <Text className="mt-2 text-xs text-danger">
                  Bloqueada por una incidencia que detiene la obra (§6).
                </Text>
              ) : null}
            </View>
          )}
        />
      )}
    </View>
  );
}

function Indicador({
  etiqueta,
  valor,
  tono,
}: {
  readonly etiqueta: string;
  readonly valor: number;
  readonly tono: 'danger' | 'warn' | 'neutro';
}) {
  const color =
    tono === 'danger' ? 'text-danger' : tono === 'warn' ? 'text-warn' : 'text-text';

  return (
    <View className="flex-1 rounded-lg border border-line bg-surface p-3">
      <Text className={`font-mono text-2xl ${color}`}>{valor}</Text>
      <Text className="text-xs text-text-mute">{etiqueta}</Text>
    </View>
  );
}
