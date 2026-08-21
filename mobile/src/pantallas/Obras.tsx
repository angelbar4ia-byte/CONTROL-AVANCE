/**
 * Obras — pantalla compartida (§5.3 "Avance/Obras", §4, §5.2).
 *
 * Lee la réplica SQLite local, no la API: en campo puede no haber señal y la
 * lista tiene que estar igual (§12.5). El alcance no se filtra aquí — lo
 * resuelven las sync rules con el mismo criterio que RLS (§12.4), así que lo
 * que está en la base local ya es lo que este usuario puede ver.
 *
 * Cambia por rol una sola cosa, y es a dónde lleva tocar una obra: el
 * Residente entra a capturar avance, Control de obra a revisarla físicamente
 * (§5.2). Los contadores también, por la misma razón: al residente le importa
 * cuánto le falta por capturar; a Control, cuánto le falta por revisar.
 */

import { router } from 'expo-router';
import { FlatList, Pressable, Text, View } from 'react-native';
import { useQuery } from '@powersync/react-native';

import { Barra } from '@/ui/Barra';
import { Encabezado } from '@/ui/Encabezado';
import { Estatus } from '@/ui/Estatus';
import { Cargando, Vacio } from '@/ui/Formulario';

interface FilaObra {
  id: string;
  clave: string;
  estatus: string;
  avance_pct: number;
  fecha_inicio: string | null;
  actividades: number;
  por_capturar: number;
  sin_subir: number;
  con_avance: number;
  revisadas: number;
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
           WHERE a.obra_id = o.id AND r.sync_status = 'pendiente') AS sin_subir,
         (SELECT COUNT(*) FROM actividad a
           WHERE a.obra_id = o.id AND a.avance_pct > 0) AS con_avance,
         (SELECT COUNT(DISTINCT r.actividad_id) FROM revision_fisica r
           WHERE r.obra_id = o.id) AS revisadas
    FROM obra o
   ORDER BY o.clave
`;

type Papel = 'residente' | 'control_obra';

export function Obras({ papel }: { readonly papel: Papel }) {
  const { data: obras, isLoading } = useQuery<FilaObra>(CONSULTA);

  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Encabezado
        eyebrow={papel === 'residente' ? 'Residente' : 'Control de obra'}
        titulo={papel === 'residente' ? 'Mis obras' : 'Obras'}
        descripcion={
          papel === 'residente'
            ? 'Obras donde soy residente (§4). Disponibles sin señal.'
            : 'Obras de tus proyectos (§4). Toca una para revisarla en sitio.'
        }
      />

      {isLoading ? (
        <Cargando />
      ) : (
        <FlatList
          className="mt-1"
          data={obras}
          keyExtractor={(item) => item.id}
          ListEmptyComponent={
            <Vacio texto="Todavía no hay obras en el dispositivo. Se descargan solas en cuanto haya señal." />
          }
          renderItem={({ item }) => (
            <Pressable
              testID="obra"
              onPress={() =>
                papel === 'residente'
                  ? router.push({
                      pathname: '/(residente)/avances',
                      params: { obraId: item.id, obraClave: item.clave },
                    })
                  : router.push('/(control)/revision')
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
                  {papel === 'residente'
                    ? `${item.por_capturar} de ${item.actividades} actividades por capturar`
                    : `${item.revisadas} de ${item.con_avance} con avance ya revisadas`}
                </Text>
                <Text className="font-mono text-sm text-text">{item.avance_pct}%</Text>
              </View>

              {papel === 'residente' && item.sin_subir > 0 ? (
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
