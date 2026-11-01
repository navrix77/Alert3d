import type BottomSheet from '@gorhom/bottom-sheet';
import type { CameraRef } from '@maplibre/maplibre-react-native';
import * as Haptics from 'expo-haptics';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import Animated, { FadeIn, FadeInDown, FadeOut } from 'react-native-reanimated';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';

import { Glass, SpringButton } from './src/components/Glass';
import { HomePanel } from './src/components/HomePanel';
import { OfflineBanner } from './src/components/OfflineBanner';
import { SettingsSheet } from './src/components/SettingsSheet';
import { TacticalMap } from './src/components/TacticalMap';
import { TargetSheet } from './src/components/TargetSheet';
import { useHomeAlerts, prepareNotifications } from './src/hooks/useHomeAlerts';
import { useLiveState } from './src/hooks/useLiveState';
import { usePushRegistration } from './src/hooks/usePushRegistration';
import { SettingsProvider, useSettings } from './src/hooks/useSettings';
import { DISP } from './src/lib/display';
import { C, R } from './src/lib/theme';
import type { LonLat } from './src/lib/types';

export default function App() {
  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: C.bg }}>
      <SafeAreaProvider>
        <SettingsProvider>
          <StatusBar style="light" />
          <Main />
        </SettingsProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

function Main() {
  const insets = useSafeAreaInsets();
  const { ready, server, home, setServer, setHome } = useSettings();
  const { snap, conn, lastError } = useLiveState(server, ready);
  const [selected, setSelected] = useState<string | null>(null);
  const [follow, setFollow] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const camera = useRef<CameraRef>(null);
  const targetSheet = useRef<BottomSheet>(null);
  const settingsSheet = useRef<BottomSheet>(null);

  useHomeAlerts(snap, home);
  usePushRegistration(server, home);

  const say = useCallback((m: string) => {
    setToast(m);
    setTimeout(() => setToast((t) => (t === m ? null : t)), 2400);
  }, []);

  const select = useCallback((id: string | null) => {
    setSelected(id);
    setFollow(false);
    if (id) {
      Haptics.selectionAsync().catch(() => {});
      settingsSheet.current?.close();
      targetSheet.current?.snapToIndex(0);
      const d = DISP.get(id);
      if (d) camera.current?.easeTo({ center: d.p, zoom: 8.5, duration: 650 });
    } else {
      targetSheet.current?.close();
    }
  }, []);

  const onLongPress = useCallback(
    (p: LonLat) => {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      setHome([p[0], p[1]]);
      say('Дім збережено');
      prepareNotifications().then((ok) => {
        if (!ok) say('Сповіщення вимкнені — увімкніть у налаштуваннях телефона');
      });
    },
    [setHome, say],
  );

  // режим «Стежити за ціллю»: камера плавно веде вибрану ціль
  useEffect(() => {
    if (!follow || !selected) return;
    const h = setInterval(() => {
      const d = DISP.get(selected);
      if (d) camera.current?.easeTo({ center: d.p, duration: 480, easing: 'linear' });
    }, 500);
    return () => clearInterval(h);
  }, [follow, selected]);

  // ціль зникла зі знімка — закриваємо картку
  useEffect(() => {
    if (selected && snap && !snap.tracks.some((t) => t.id === selected)) select(null);
  }, [snap, selected, select]);

  return (
    <View style={styles.root}>
      <TacticalMap server={server} snap={snap} home={home} selected={selected} onSelect={select} onLongPress={onLongPress} cameraRef={camera} />

      <View pointerEvents="box-none" style={[styles.top, { paddingTop: insets.top + 6 }]}>
        <HomePanel
          snap={snap}
          conn={conn}
          home={home}
          onOpen={select}
          onSettings={() => {
            targetSheet.current?.close();
            settingsSheet.current?.snapToIndex(0);
          }}
        />
        <OfflineBanner conn={conn} server={server} />
      </View>

      <Animated.View entering={FadeInDown.delay(200).springify()} pointerEvents="box-none" style={[styles.fabs, { bottom: insets.bottom + 26 }]}>
        <SpringButton
          accessibilityLabel="До дому"
          onPress={() => {
            if (!home) return say('Довго натисніть на карту, щоб позначити дім');
            camera.current?.flyTo({ center: home, zoom: 9, duration: 1200 });
          }}
        >
          <Glass radius={R.lg} style={styles.fab}>
            <Text style={styles.fabTxt}>⌂</Text>
          </Glass>
        </SpringButton>
        <SpringButton accessibilityLabel="Уся Україна" onPress={() => camera.current?.flyTo({ center: [31.4, 48.6], zoom: 5.2, bearing: 0, pitch: 0, duration: 1200 })}>
          <Glass radius={R.lg} style={styles.fab}>
            <Text style={styles.fabTxtSm}>UA</Text>
          </Glass>
        </SpringButton>
      </Animated.View>

      {toast ? (
        <Animated.View entering={FadeIn.duration(180)} exiting={FadeOut.duration(220)} pointerEvents="none" style={[styles.toastWrap, { bottom: insets.bottom + 96 }]}>
          <Glass radius={999} style={styles.toast}>
            <Text style={styles.toastTxt}>{toast}</Text>
          </Glass>
        </Animated.View>
      ) : null}

      <TargetSheet
        ref={targetSheet}
        snap={snap}
        home={home}
        selected={selected}
        follow={follow}
        onClose={() => {
          setSelected(null);
          setFollow(false);
        }}
        onToggleFollow={() => {
          Haptics.selectionAsync().catch(() => {});
          setFollow((f) => !f);
        }}
      />
      <SettingsSheet
        ref={settingsSheet}
        server={server}
        home={home}
        snap={snap}
        conn={conn}
        lastError={lastError}
        onSave={(u) => {
          setServer(u);
          settingsSheet.current?.close();
          say('Підключаюся до ' + u);
        }}
        onResetHome={() => {
          setHome(null);
          say('Дім скинуто');
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  top: { position: 'absolute', left: 12, right: 12, top: 0 },
  fabs: { position: 'absolute', right: 14, gap: 10 },
  fab: { width: 52, height: 52, alignItems: 'center', justifyContent: 'center' },
  fabTxt: { color: C.ink, fontSize: 24, marginTop: -2 },
  fabTxtSm: { color: C.ink, fontSize: 14, fontWeight: '700', letterSpacing: 0.5 },
  toastWrap: { position: 'absolute', left: 0, right: 0, alignItems: 'center' },
  toast: { paddingHorizontal: 16, paddingVertical: 10 },
  toastTxt: { color: C.ink, fontSize: 14, fontWeight: '600' },
});
