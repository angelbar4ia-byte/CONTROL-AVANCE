/**
 * Mis obras — Residente (§4, §5.2).
 *
 * Lee la réplica SQLite local de PowerSync, no la API: en campo puede no
 * haber señal y la lista tiene que estar igual (§12.5). El alcance ("mis
 * obras") no se filtra aquí — lo resuelven las sync rules con el mismo
 * criterio que RLS (`residente_obras` en `sync-rules.yaml`, §12.4), así que
 * lo que está en la base local ya es lo que este residente puede ver.
 *
 * De aquí se entra a la captura: tocar una obra abre Avances filtrado por
 * ella.
 */

import { router } from 'expo-router';
import { ActivityIndicator, FlatList, Pressable, Text, View } from 'react-native';
import { useQuery } from '@powersync/react-native';

import { TOKENS } from '@/lib/tabs';
import { Barra } from '@/ui/Barra';
import { Encabezado } from '@/ui/Encabezado';
import { Estatus } from '@/ui/Estatus';

interface FilaObra {
  id: string;
  clave: string;
  estatus: string;
  avance_pct: number;
  fecha_inicio: string | null;
  actividades: number;
  por_capturar: number;
  sin_subir: number;
}

/**
 * Subconsultas en vez de JOIN + GROUP BY: cada conteo mide una cosa distinta
 * y un solo join las multiplicaría entre sí.
 */
const CONSULTA = `
  SELECT o.id, o.clave, o.estatus, o.avance_pct, o.fecha_inicio,
         (SELECT COUNT(*) FROM actividad a
           WHERE a.obra_id = o.id) AS actividades,
         (SELECT COUNT(*) FROM actividad a
           WHERE a.obra_id = o.id AND a.estatus != 'concluida') AS por_capturar,
         (SELECT COUNT(*) FROM registro_avance r
            JOIN actividad a ON a.id = r.actividad_id
           WHERE a.obra_id = o.id AND r.sync_status = 'pendiente') AS sin_subir
    FROM obra o
   ORDER BY o.clave
`;

export default function Pantalla() {
  const { data: obras, isLoading } = useQuery<FilaObra>(CONSULTA);

  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Encabezado
        eyebrow="Residente"
        titulo="Mis obras"
        descripcion="Obras donde soy residente (§4). Disponibles sin señal."
      />

      {isLoading ? (
        <View className="mt-10 items-center">
          <ActivityIndicator color={TOKENS.accent} />
        </View>
      ) : (
        <FlatList
          className="mt-1"
          data={obras}
          keyExtractor={(item) => item.id}
          ListEmptyComponent={
            <Text className="mt-8 text-md text-text-mute">
              Todavía no hay obras en el dispositivo. Se descargan solas en cuanto haya señal.
            </Text>
          }
          renderItem={({ item }) => (
            <Pressable
              onPress={() =>
                router.push({
                  pathname: '/(residente)/avances',
                  params: { obraId: item.id, obraClave: item.clave },
                })
              }
              className="mb-3 rounded-lg border border-line bg-surface p-4 active:opacity-70"
            >
              <View className="flex-row items-center justify-between">
                <Text className="font-mono text-lg text-text">{item.clave}</Text>
                <Estatus valor={item.estatus} />
              </View>

              <View className="mt-3">
                <Barra pct={item.avance_pct} />
              </View>

              <View className="mt-2 flex-row items-center justify-between">
                <Text className="text-sm text-text-mute">
                  {item.por_capturar} de {item.actividades} actividades por capturar
                </Text>
                <Text className="font-mono text-sm text-text">{item.avance_pct}%</Text>
              </View>

              {item.sin_subir > 0 ? (
                <Text className="mt-2 text-xs text-warn">
                  {item.sin_subir} captura{item.sin_subir === 1 ? '' : 's'} sin subir
                </Text>
              ) : null}
            </Pressable>
          )}
        />
      )}
    </View>
  );
}
