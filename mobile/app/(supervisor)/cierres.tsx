import { Text, View } from 'react-native';

export default function Pantalla() {
  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Text className="text-2xl text-text">Cierres</Text>
      <Text className="mt-2 text-md text-text-mute">El Supervisor autoriza el cierre de actividad (§4).</Text>
    </View>
  );
}
