/**
 * Fotos — la cola de evidencias, visible (§5.2 tab de Control de obra, §12.5).
 *
 * El §5.2 le da a Control de obra un tab llamado *Fotos*. Se resolvió como la
 * cola de subida y no como una galería, y esa fue la decisión de diseño de
 * esta pantalla.
 *
 * Una galería duplicaría lo que ya está en la app de fotos del teléfono. La
 * cola, en cambio, responde la única pregunta que la app puede contestar y el
 * carrete no: *de lo que fotografié en obra, ¿qué ya llegó al expediente?*.
 * Sin esta pantalla, una foto rechazada por el servidor moría en un
 * `console.warn` y nadie se enteraba hasta que faltaba en el cierre.
 *
 * Por eso las tres acciones son las de una cola y no las de un álbum:
 * reintentar, descartar y ver por qué falló.
 */

import { Image, Pressable, SectionList, Text, View } from 'react-native';
import { usePowerSync, useQuery } from '@powersync/react-native';

import { descartar, reintentar, type FotoEnCola } from '@/evidencias/cola';
import { useEmpujarSalida } from '@/salida/ProveedorSalida';
import { Encabezado } from '@/ui/Encabezado';
import { Vacio } from '@/ui/Formulario';

/**
 * `uri_local` puede venir vacía: `purgarSubidas` borra el binario de las
 * fotos ya en R2 y deja la fila como rastro. Esas se muestran sin miniatura,
 * que es exactamente lo que son.
 */
const CONSULTA = `
  SELECT id, entidad, entidad_id, obra_id, uri_local, nombre, content_type,
         clave, estado, intentos, error, creada_en, subida_en
    FROM evidencia_pendiente
   ORDER BY
     CASE estado WHEN 'fallida' THEN 0 WHEN 'pendiente' THEN 1 ELSE 2 END,
     creada_en DESC
`;

const NOMBRE_ENTIDAD: Readonly<Record<string, string>> = {
  registro_avance: 'Avance',
  revision_fisica: 'Revisión',
  incidencia: 'Incidencia',
  ninguna: 'Incidencia por enviar',
};

export function FotosPendientes() {
  const db = usePowerSync();
  const empujar = useEmpujarSalida();
  const { data: fotos } = useQuery<FotoEnCola>(CONSULTA);

  const todas = fotos ?? [];
  const secciones = [
    { title: 'No pudieron subir', data: todas.filter((f) => f.estado === 'fallida') },
    { title: 'Por subir', data: todas.filter((f) => f.estado === 'pendiente') },
    { title: 'En el expediente', data: todas.filter((f) => f.estado === 'subida') },
  ].filter((seccion) => seccion.data.length > 0);

  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Encabezado
        eyebrow="Control de obra"
        titulo="Fotos"
        descripcion="Qué evidencia ya llegó a R2 y qué sigue esperando señal (§12.5)."
      />

      <Pressable
        onPress={empujar}
        className="mb-3 h-fila items-center justify-center rounded-md border border-line bg-surface active:opacity-70"
      >
        <Text className="text-base text-text-soft">Intentar ahora</Text>
      </Pressable>

      <SectionList
        sections={secciones}
        keyExtractor={(item) => item.id}
        ListEmptyComponent={
          <Vacio texto="No has tomado fotos en la app. Las que tomes desde una revisión o una incidencia aparecen aquí." />
        }
        renderSectionHeader={({ section }) => (
          <Text className="mb-2 mt-3 font-mono text-xs uppercase text-text-faint">
            {section.title} · {section.data.length}
          </Text>
        )}
        renderItem={({ item }) => (
          <View className="mb-3 flex-row gap-3 rounded-lg border border-line bg-surface p-3">
            {item.uri_local ? (
              <Image source={{ uri: item.uri_local }} className="h-16 w-16 rounded-md bg-elev" />
            ) : (
              <View className="h-16 w-16 items-center justify-center rounded-md bg-elev">
                <Text className="text-xs text-text-faint">en R2</Text>
              </View>
            )}

            <View className="flex-1">
              <Text className="text-base text-text">
                {NOMBRE_ENTIDAD[item.entidad] ?? item.entidad}
              </Text>
              <Text className="font-mono text-xs text-text-faint">
                {item.creada_en.slice(0, 16).replace('T', ' ')}
              </Text>

              {item.estado === 'fallida' ? (
                <>
                  <Text className="mt-1 text-xs text-danger">
                    {item.error ?? 'No se pudo subir.'}
                  </Text>
                  <View className="mt-2 flex-row gap-2">
                    <Pressable
                      onPress={() => {
                        void reintentar(db, item.id).then(empujar);
                      }}
                      className="rounded-md border border-line px-3 py-1.5 active:opacity-70"
                    >
                      <Text className="text-sm text-text-soft">Reintentar</Text>
                    </Pressable>
                    <Pressable
                      onPress={() => void descartar(db, item.id)}
                      className="rounded-md border border-danger px-3 py-1.5 active:opacity-70"
                    >
                      <Text className="text-sm text-danger">Descartar</Text>
                    </Pressable>
                  </View>
                </>
              ) : item.estado === 'pendiente' ? (
                <Text className="mt-1 text-xs text-warn">
                  {item.intentos > 0 ? `${item.intentos} intento(s) · ` : ''}Espera señal.
                </Text>
              ) : (
                <Text className="mt-1 font-mono text-xs text-ok" numberOfLines={1}>
                  {item.clave}
                </Text>
              )}
            </View>
          </View>
        )}
      />
    </View>
  );
}
