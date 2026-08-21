/**
 * Calidad — lo que dejaron las revisiones físicas (§5.2, §7.8).
 *
 * No es la pantalla de *Evaluaciones* (§7.8 `Evaluacion`), y la distinción
 * importa: una evaluación es un cuestionario por criterios ponderados que
 * califica a una obra, un residente o un contratista en un periodo, y se hace
 * sentado. Esto es el promedio de las calificaciones que Control de obra fue
 * dejando frente a cada muro, con la escala de `Revision.tsx`.
 *
 * Sirve para una decisión concreta de campo: *¿a qué obra vuelvo?*. Por eso
 * ordena por promedio ascendente —lo peor calificado primero— y no
 * alfabéticamente.
 *
 * Todo el cálculo es local: las revisiones ya están en el dispositivo, las
 * propias desde antes de sincronizar. Un promedio que solo apareciera con
 * señal sería inútil justo el día de la visita.
 */

import { FlatList, Text, View } from 'react-native';
import { useQuery } from '@powersync/react-native';

import { Encabezado } from '@/ui/Encabezado';
import { Cargando, Vacio } from '@/ui/Formulario';

interface FilaCalidad {
  obra_id: string;
  clave: string;
  revisiones: number;
  promedio: number | null;
  bajas: number;
  ultima: string | null;
}

/**
 * `HAVING` no hace falta: interesa también la obra **sin** revisiones, que es
 * la que hay que ir a ver. Por eso el `LEFT JOIN` y el orden con `COALESCE`
 * que las manda arriba junto con las peor calificadas.
 *
 * `bajas` cuenta 1 y 2 —"rehacer" y "deficiente"— porque son las dos que
 * obligan a volver; un 3 es aceptable y no genera visita.
 */
const CONSULTA = `
  SELECT o.id AS obra_id, o.clave,
         COUNT(r.id) AS revisiones,
         AVG(r.calidad) AS promedio,
         SUM(CASE WHEN r.calidad <= 2 THEN 1 ELSE 0 END) AS bajas,
         MAX(r.fecha) AS ultima
    FROM obra o
    LEFT JOIN revision_fisica r ON r.obra_id = o.id
   GROUP BY o.id, o.clave
   ORDER BY COALESCE(promedio, 0) ASC, bajas DESC, o.clave
`;

export function Calidad() {
  const { data: obras, isLoading } = useQuery<FilaCalidad>(CONSULTA);

  const conRevision = (obras ?? []).filter((o) => o.revisiones > 0);
  const global =
    conRevision.length > 0
      ? conRevision.reduce((suma, o) => suma + (o.promedio ?? 0), 0) / conRevision.length
      : null;

  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Encabezado
        eyebrow="Control de obra"
        titulo="Calidad"
        descripcion="Promedio de tus revisiones en sitio. Lo peor calificado, arriba."
      />

      <View className="mb-4 rounded-lg border border-line bg-surface p-4">
        <Text className="font-mono text-3xl text-text">
          {global === null ? '—' : global.toFixed(1)}
          <Text className="text-lg text-text-mute"> / 5</Text>
        </Text>
        <Text className="mt-1 text-sm text-text-mute">
          {conRevision.length} de {obras?.length ?? 0} obras con al menos una revisión
        </Text>
      </View>

      {isLoading ? (
        <Cargando />
      ) : (
        <FlatList
          data={obras}
          keyExtractor={(item) => item.obra_id}
          ListEmptyComponent={<Vacio texto="No hay obras en el dispositivo todavía." />}
          renderItem={({ item }) => (
            <View className="mb-3 rounded-lg border border-line bg-surface p-4">
              <View className="flex-row items-center justify-between">
                <Text className="font-mono text-lg text-text">{item.clave}</Text>
                <Nota promedio={item.promedio} revisiones={item.revisiones} />
              </View>

              <View className="mt-2 flex-row items-center justify-between">
                <Text className="text-sm text-text-mute">
                  {item.revisiones === 0
                    ? 'Sin revisar'
                    : `${item.revisiones} revisión${item.revisiones === 1 ? '' : 'es'}`}
                </Text>
                {item.ultima ? (
                  <Text className="font-mono text-xs text-text-faint">
                    última {item.ultima.slice(0, 10)}
                  </Text>
                ) : null}
              </View>

              {item.bajas > 0 ? (
                <Text className="mt-2 text-xs text-danger">
                  {item.bajas} trabajo{item.bajas === 1 ? '' : 's'} por rehacer o deficiente{item.bajas === 1 ? '' : 's'}.
                </Text>
              ) : null}
            </View>
          )}
        />
      )}
    </View>
  );
}

function Nota({
  promedio,
  revisiones,
}: {
  readonly promedio: number | null;
  readonly revisiones: number;
}) {
  if (revisiones === 0 || promedio === null) {
    return (
      <View className="rounded-full bg-elev px-2 py-1">
        <Text className="text-xs text-text-mute">Sin datos</Text>
      </View>
    );
  }

  const tono =
    promedio >= 4 ? 'bg-ok-soft text-ok' : promedio >= 3 ? 'bg-warn-soft text-warn' : 'bg-danger-soft text-danger';
  const [fondo, color] = tono.split(' ');

  return (
    <View className={`rounded-full px-2 py-1 ${fondo}`}>
      <Text className={`font-mono text-xs ${color}`}>{promedio.toFixed(1)} / 5</Text>
    </View>
  );
}
