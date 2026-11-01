import BottomSheet, { type BottomSheetBackgroundProps, BottomSheetTextInput, BottomSheetView } from '@gorhom/bottom-sheet';
import * as Haptics from 'expo-haptics';
import { forwardRef, useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { normalizeServer } from '../hooks/useSettings';
import { fmtTimeS } from '../lib/geo';
import { C, DEFAULT_SERVER, R } from '../lib/theme';
import type { ConnState, LonLat, Snapshot } from '../lib/types';
import { Glass } from './Glass';

function SheetGlass({ style }: BottomSheetBackgroundProps) {
  return <Glass radius={R.xl} style={style} intensity={60} />;
}

interface Props {
  server: string;
  home: LonLat | null;
  snap: Snapshot | null;
  conn: ConnState;
  lastError: string | null;
  onSave(url: string): void;
  onResetHome(): void;
}

/** Налаштування: адреса сервера (зберігається в AsyncStorage), стан зʼєднання, скидання дому. */
export const SettingsSheet = forwardRef<BottomSheet, Props>(function SettingsSheet({ server, home, snap, conn, lastError, onSave, onResetHome }, ref) {
  const [url, setUrl] = useState(server);
  useEffect(() => setUrl(server), [server]);
  const snapPoints = useMemo(() => ['62%'], []);
  const h = snap?.health;

  const statusTxt =
    conn === 'live'
      ? 'Зʼєднано' + (snap ? ' · станом на ' + fmtTimeS(snap.now) : '')
      : conn === 'connecting'
        ? 'Підключення…'
        : 'Немає звʼязку' + (lastError ? ' · ' + lastError : '');

  return (
    <BottomSheet
      ref={ref}
      index={-1}
      snapPoints={snapPoints}
      enablePanDownToClose
      enableDynamicSizing={false}
      keyboardBehavior="interactive"
      keyboardBlurBehavior="restore"
      backgroundComponent={SheetGlass}
      handleIndicatorStyle={{ backgroundColor: 'rgba(255,255,255,0.4)', width: 42 }}
    >
      <BottomSheetView style={styles.body}>
        <Text style={styles.title}>Налаштування</Text>

        <Text style={styles.label}>Адреса сервера</Text>
        <BottomSheetTextInput
          value={url}
          onChangeText={setUrl}
          placeholder={DEFAULT_SERVER}
          placeholderTextColor={C.ink3}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          returnKeyType="done"
          style={styles.input}
          onSubmitEditing={() => onSave(url)}
        />
        <Text style={styles.hint}>
          Телефон і компʼютер мають бути в одній Wi‑Fi мережі. Сервер запускайте з параметром --host 0.0.0.0 (або вкажіть адресу розгорнутого сервера, напр. https://…).
        </Text>
        <Pressable
          onPress={() => {
            Haptics.selectionAsync().catch(() => {});
            onSave(normalizeServer(url));
          }}
          style={({ pressed }) => [styles.btn, pressed && { opacity: 0.7 }]}
        >
          <Text style={styles.btnTxt}>Зберегти й перепідключитися</Text>
        </Pressable>

        <View style={styles.card}>
          <Row k="Стан" v={statusTxt} tone={conn === 'live' ? C.green : conn === 'connecting' ? C.amber : C.redHot} />
          {h?.channels ? <Row k="Канали наживо" v={h.channels.live + ' з ' + h.channels.channels} /> : null}
          {h ? <Row k="Офіційні тривоги" v={h.alerts ? snap?.official?.source || 'доступні' : 'недоступні'} /> : null}
          {h?.replay ? <Row k="Режим" v="ДЕМО (запис)" tone={C.amber} /> : null}
          {h?.version ? <Row k="Версія сервера" v={h.version} /> : null}
        </View>

        <View style={styles.card}>
          <Row k="Мій дім" v={home ? home[1].toFixed(4) + ', ' + home[0].toFixed(4) : 'не позначено — довго натисніть на карту'} />
          {home ? (
            <Pressable onPress={onResetHome} style={({ pressed }) => [styles.btnGhost, pressed && { opacity: 0.6 }]}>
              <Text style={styles.btnGhostTxt}>Скинути дім</Text>
            </Pressable>
          ) : null}
        </View>
      </BottomSheetView>
    </BottomSheet>
  );
});

function Row({ k, v, tone }: { k: string; v: string; tone?: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowK}>{k}</Text>
      <Text style={[styles.rowV, tone ? { color: tone } : null]} numberOfLines={2}>
        {v}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  body: { paddingHorizontal: 18, paddingBottom: 24 },
  title: { color: C.ink, fontSize: 21, fontWeight: '700', letterSpacing: -0.4, marginBottom: 14 },
  label: { color: C.ink2, fontSize: 13, fontWeight: '600', marginBottom: 6 },
  input: {
    color: C.ink,
    fontSize: 16,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: R.md,
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.hairStrong,
  },
  hint: { color: C.ink3, fontSize: 12.5, lineHeight: 17, marginTop: 8 },
  btn: { marginTop: 12, paddingVertical: 13, borderRadius: R.md, alignItems: 'center', backgroundColor: C.blue },
  btnTxt: { color: '#08101F', fontSize: 15, fontWeight: '700' },
  btnGhost: { marginTop: 8, alignSelf: 'flex-start', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, backgroundColor: 'rgba(255,59,78,0.16)' },
  btnGhostTxt: { color: C.redHot, fontSize: 14, fontWeight: '600' },
  card: { marginTop: 16, padding: 12, borderRadius: R.md, backgroundColor: 'rgba(255,255,255,0.05)', borderWidth: StyleSheet.hairlineWidth, borderColor: C.hair },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5, gap: 12 },
  rowK: { color: C.ink3, fontSize: 13.5 },
  rowV: { color: C.ink, fontSize: 13.5, flex: 1, textAlign: 'right' },
});
