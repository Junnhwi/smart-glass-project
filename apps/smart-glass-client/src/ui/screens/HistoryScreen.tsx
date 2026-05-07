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
  listRecentMemories,
  type MemoryRecentItem,
} from '../../networking/api';
import { useAuth } from '../context/AuthContext';
import { useAppNavigation } from '../navigation/appNavigation';
import { commonStyles } from '../styles/commonStyles';
import { colors } from '../styles/colors';

type HistoryCardItem = MemoryRecentItem & {
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

const describeMemory = (item: MemoryRecentItem) => {
  const location = item.location?.name || item.location?.address || '';
  const subject = item.detectedObjects[0] || item.tags[0] || '기록';
  const detail =
    item.positionHint ||
    item.sceneSummary ||
    item.caption ||
    '저장된 설명이 아직 없어요.';

  if (location) {
    return `${subject} · ${location}`;
  }

  return detail;
};

const uniqueImageKeys = (items: MemoryRecentItem[]) => {
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

export default function HistoryScreen() {
  const navigation = useAppNavigation();
  const { currentUser } = useAuth();
  const [items, setItems] = useState<HistoryCardItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    let isActive = true;

    const loadHistory = async () => {
      if (!currentUser) {
        if (isActive) {
          setItems([]);
          setIsLoading(false);
        }
        return;
      }

      setIsLoading(true);
      setErrorMessage('');

      try {
        const recentResponse = await listRecentMemories({
          authToken: currentUser.authToken,
          userId: currentUser.userId,
          limit: 20,
        });

        let accessUrlByImageKey: Record<string, string> = {};
        const imageKeys = uniqueImageKeys(recentResponse.items);

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
          recentResponse.items.map((item) => ({
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
            : '히스토리를 불러오는 중 문제가 생겼어요.'
        );
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    };

    loadHistory();
    return () => {
      isActive = false;
    };
  }, [currentUser]);

  return (
    <SafeAreaView style={commonStyles.screen}>
      <View style={commonStyles.header}>
        <Pressable onPress={() => navigation.goBack()}>
          <Text style={styles.backButton}>{'<'}</Text>
        </Pressable>

        <Text style={commonStyles.headerTitle}>히스토리</Text>

        <View style={styles.headerSpacer} />
      </View>

      <ScrollView contentContainerStyle={styles.list}>
        <Text style={styles.sectionTitle}>최근에 저장된 기록</Text>

        {isLoading ? (
          <View style={commonStyles.card}>
            <ActivityIndicator color={colors.primary} />
            <Text style={styles.loadingText}>기록을 불러오는 중이에요.</Text>
          </View>
        ) : null}

        {!isLoading && errorMessage ? (
          <View style={commonStyles.card}>
            <Text style={styles.errorTitle}>기록을 불러오지 못했어요.</Text>
            <Text style={styles.errorText}>{errorMessage}</Text>
          </View>
        ) : null}

        {!isLoading && !errorMessage && items.length === 0 ? (
          <View style={commonStyles.card}>
            <Text style={styles.emptyTitle}>아직 저장된 기록이 없어요.</Text>
            <Text style={styles.emptyText}>
              사진을 업로드하고 추론이 끝나면 여기에서 최근 기록을 볼 수 있어요.
            </Text>
          </View>
        ) : null}

        {!isLoading && !errorMessage
          ? items.map((item) => {
              const itemName = item.detectedObjects[0] || item.tags[0] || '기록';

              return (
                <Pressable
                  key={item.memoryId}
                  style={commonStyles.card}
                  onPress={() => navigation.navigate('ItemLocation', { itemName })}
                >
                  {item.accessUrl ? (
                    <Image
                      source={{ uri: item.accessUrl }}
                      style={styles.thumbnail}
                    />
                  ) : null}

                  <View style={styles.cardTop}>
                    <Text style={styles.cardTitle}>{itemName}</Text>
                    <Text style={styles.time}>
                      {formatRelativeTime(item.capturedAt)}
                    </Text>
                  </View>

                  <Text style={styles.preview}>{describeMemory(item)}</Text>

                  <Text style={styles.detail}>
                    {item.positionHint ||
                      item.sceneSummary ||
                      item.caption ||
                      '상세 설명이 아직 없어요.'}
                  </Text>
                </Pressable>
              );
            })
          : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  list: {
    padding: 16,
    gap: 12,
  },
  headerSpacer: {
    width: 24,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
    marginBottom: 4,
  },
  backButton: {
    fontSize: 24,
    color: colors.text,
    width: 24,
  },
  loadingText: {
    marginTop: 10,
    fontSize: 14,
    color: colors.subText,
    textAlign: 'center',
  },
  errorTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.text,
    marginBottom: 6,
  },
  errorText: {
    fontSize: 14,
    color: colors.subText,
    lineHeight: 20,
  },
  emptyTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.text,
    marginBottom: 6,
  },
  emptyText: {
    fontSize: 14,
    color: colors.subText,
    lineHeight: 20,
  },
  thumbnail: {
    width: '100%',
    height: 160,
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
  cardTitle: {
    flex: 1,
    fontSize: 16,
    fontWeight: '700',
    color: colors.text,
  },
  time: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.subText,
  },
  preview: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.text,
    marginBottom: 6,
  },
  detail: {
    fontSize: 14,
    lineHeight: 20,
    color: colors.subText,
  },
});
