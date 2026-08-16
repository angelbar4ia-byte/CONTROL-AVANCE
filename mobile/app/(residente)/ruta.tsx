import { View } from 'react-native';

import { Encabezado } from '@/ui/Encabezado';

export default function Pantalla() {
  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Encabezado
        eyebrow="Residente"
        titulo="Mi ruta crítica"
        descripcion="Actividades críticas y holgura (§6)."
      />
    </View>
  );
}
