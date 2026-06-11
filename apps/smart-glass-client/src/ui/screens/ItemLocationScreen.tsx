import React, { useEffect, useState } from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import {
  issueMediaAccessUrls,
  searchMemories,
  type MemorySearchHit,
} from '../../networking/api';
import { useAuth } from '../context/AuthContext';
import { useAppNavigation, useAppRoute } from '../navigation/appNavigation';
import { commonStyles } from '../styles/commonStyles';
import { colors } from '../styles/colors';
import { pressableFeedback } from '../styles/pressableFeedback';

type LocationMemoryCard = MemorySearchHit & {
  accessUrl?: string;
};

const formatRelativeTime = (capturedAt?: string | null) => {
  if (!capturedAt) {
    return '시간 정보 없음';
  }

  const capturedTime = new Date(capturedAt).getTime();
  if (Number.isNaN(capturedTime)) {
    return capturedAt;
  }

  const diffSec = Math.max(0, Math.floor((Date.now() - capturedTime) / 1000));
  if (diffSec < 60) return '방금 전';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}분 전`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}시간 전`;
  return `${Math.floor(diffSec / 86400)}일 전`;
};

const buildLocationText = (item: MemorySearchHit) => {
  return (
    item.location?.name ||
    item.location?.address ||
    item.positionHint ||
    item.sceneSummary ||
    item.caption ||
    '위치 설명이 아직 없어요.'
  );
};

const buildDetailText = (item: MemorySearchHit) => {
  return (
    item.positionHint ||
    item.sceneSummary ||
    item.caption ||
    '상세 설명이 아직 없어요.'
  );
};

const uniqueImageKeys = (items: MemorySearchHit[]) => {
  const seen = new Set<string>();
  const keys: string[] = [];

  items.forEach((item) => {
    if (!item.imageKey || seen.has(item.imageKey)) {
      return;
    }
    seen.add(item.imageKey);
    keys.push(item.imageKey);
  });

  return keys;
};

export default function ItemLocationScreen() {
  const navigation = useAppNavigation();
  const route = useAppRoute<'ItemLocation'>();
  const { currentUser } = useAuth();
  const itemName = route.params?.itemName?.trim() || '';

  const [items, setItems] = useState<LocationMemoryCard[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    let isActive = true;

    const loadLocations = async () => {
      if (!currentUser || !itemName) {
        if (isActive) {
          setItems([]);
          setIsLoading(false);
        }
        return;
      }

      setIsLoading(true);
      setErrorMessage('');

      try {
        const searchResponse = await searchMemories({
          authToken: currentUser.authToken,
          userId: currentUser.userId,
          query: itemName,
          topK: 10,
        });

        let accessUrlByImageKey: Record<string, string> = {};
        const imageKeys = uniqueImageKeys(searchResponse.hits);

        if (imageKeys.length > 0) {
          try {
            const accessUrls = await issueMediaAccessUrls({
              authToken: currentUser.authToken,
              userId: currentUser.userId,
              imageKeys,
            });
            accessUrlByImageKey = accessUrls.items.reduce<Record<string, string>>(
              (acc, item) => {
                acc[item.imageKey] = item.accessUrl;
                return acc;
              },
              {}
            );
          } catch {
            accessUrlByImageKey = {};
          }
        }

        if (!isActive) {
          return;
        }

        setItems(
          searchResponse.hits.map((item) => ({
            ...item,
            accessUrl: item.imageKey
              ? accessUrlByImageKey[item.imageKey] || item.imageUrl || undefined
              : undefined,
          }))
        );
      } catch (error) {
        if (!isActive) {
          return;
        }

        setErrorMessage(
          error instanceof Error
            ? error.message
            : '위치 기록을 불러오는 중 문제가 생겼어요.'
        );
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    };

    loadLocations();
    return () => {
      isActive = false;
    };
  }, [currentUser, itemName]);

  return (
    <SafeAreaView style={commonStyles.screen}>
      <View style={commonStyles.header}>
        <Pressable
          style={({ pressed }) => pressableFeedback(pressed)}
          onPress={() => navigation.goBack()}
        >
          <Text style={styles.backButton}>{'<'}</Text>
        </Pressable>

        <Text style={commonStyles.headerTitle}>물건 위치</Text>

        <View style={styles.headerSpacer} />
      </View>

      <ScrollView
        contentContainerStyle={[styles.content, commonStyles.contentContainer]}
      >
        <View style={styles.titleBox}>
          <Text style={styles.itemName}>{itemName || '선택한 물건'}</Text>
          <Text style={styles.description}>
            최근 검색된 기록을 시간순으로 보여줘요.
          </Text>
        </View>

        {isLoading ? (
          <View style={commonStyles.card}>
            <ActivityIndicator color={colors.primary} />
            <Text style={styles.infoText}>위치 기록을 찾는 중이에요.</Text>
          </View>
        ) : null}

        {!isLoading && errorMessage ? (
          <View style={commonStyles.card}>
            <Text style={styles.errorTitle}>위치 기록을 불러오지 못했어요.</Text>
            <Text style={styles.infoText}>{errorMessage}</Text>
          </View>
        ) : null}

        {!isLoading && !errorMessage && !itemName ? (
          <View style={commonStyles.card}>
            <Text style={styles.errorTitle}>물건 이름이 없어요.</Text>
            <Text style={styles.infoText}>
              히스토리나 채팅에서 물건을 선택한 뒤 다시 열어주세요.
            </Text>
          </View>
        ) : null}

        {!isLoading && !errorMessage && itemName && items.length === 0 ? (
          <View style={commonStyles.card}>
            <Text style={styles.errorTitle}>아직 관련 기록이 없어요.</Text>
            <Text style={styles.infoText}>
              사진 업로드와 추론이 끝나면 여기에서 위치 기록을 볼 수 있어요.
            </Text>
          </View>
        ) : null}

        {!isLoading && !errorMessage
          ? items.map((item) => (
              <View key={item.memoryId} style={commonStyles.card}>
                {item.accessUrl ? (
                  <Image source={{ uri: item.accessUrl }} style={styles.thumbnail} />
                ) : null}

                <View style={styles.cardTop}>
                  <Text style={styles.location}>{buildLocationText(item)}</Text>
                  <Text style={styles.time}>
                    {formatRelativeTime(item.capturedAt)}
                  </Text>
                </View>

                <Text style={styles.detail}>{buildDetailText(item)}</Text>
              </View>
            ))
          : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: 16,
    gap: 12,
  },
  titleBox: {
    marginBottom: 8,
  },
  itemName: {
    fontSize: 22,
    fontWeight: '800',
    color: colors.text,
    marginBottom: 6,
  },
  description: {
    fontSize: 14,
    color: colors.subText,
  },
  headerSpacer: {
    width: 24,
  },
  backButton: {
    fontSize: 20,
    color: colors.text,
    width: 24,
  },
  infoText: {
    marginTop: 10,
    fontSize: 14,
    color: colors.subText,
    lineHeight: 20,
  },
  errorTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.text,
    marginBottom: 6,
  },
  thumbnail: {
    width: '100%',
    height: 180,
    borderRadius: 12,
    marginBottom: 12,
    backgroundColor: colors.border,
  },
  cardTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
    marginBottom: 6,
  },
  location: {
    flex: 1,
    fontSize: 16,
    fontWeight: '700',
    color: colors.text,
  },
  time: {
    fontSize: 13,
    color: colors.subText,
  },
  detail: {
    fontSize: 14,
    color: colors.subText,
    lineHeight: 20,
  },
});
