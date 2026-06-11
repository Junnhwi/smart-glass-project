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
  deleteRecentMemory,
  issueMediaAccessUrls,
  listRecentMemories,
  type MemoryRecentItem,
} from '../../networking/api';
import { useAuth } from '../context/AuthContext';
import { useAppNavigation } from '../navigation/appNavigation';
import { commonStyles } from '../styles/commonStyles';
import { colors } from '../styles/colors';
import {
  pressableCardFeedback,
  pressableFeedback,
} from '../styles/pressableFeedback';

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
  const { currentUser, refreshSession } = useAuth();
  const [items, setItems] = useState<HistoryCardItem[]>([]);
  const [imageAspectRatios, setImageAspectRatios] = useState<
    Record<string, number>
  >({});
  const [isLoading, setIsLoading] = useState(true);
  const [deletingMemoryIds, setDeletingMemoryIds] = useState<
    Record<string, boolean>
  >({});
  const [pendingDeleteMemoryId, setPendingDeleteMemoryId] = useState<
    string | null
  >(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [deleteErrorMessage, setDeleteErrorMessage] = useState('');

  const handleImageLoad = (memoryId: string, event: any) => {
    const width = event?.nativeEvent?.source?.width;
    const height = event?.nativeEvent?.source?.height;

    if (!width || !height) {
      return;
    }

    const nextRatio = width / height;
    setImageAspectRatios((currentRatios) => {
      if (currentRatios[memoryId] === nextRatio) {
        return currentRatios;
      }

      return {
        ...currentRatios,
        [memoryId]: nextRatio,
      };
    });
  };

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
        let authToken = currentUser.authToken;
        let userId = currentUser.userId;
        let recentResponse: Awaited<ReturnType<typeof listRecentMemories>>;

        try {
          recentResponse = await listRecentMemories({
            authToken,
            userId,
            limit: 20,
          });
        } catch (error) {
          const message = error instanceof Error ? error.message : '';
          if (!message.toLowerCase().includes('access token has expired')) {
            throw error;
          }

          const refreshedUser = await refreshSession();
          if (!refreshedUser) {
            throw error;
          }
          authToken = refreshedUser.authToken;
          userId = refreshedUser.userId;
          recentResponse = await listRecentMemories({
            authToken,
            userId,
            limit: 20,
          });
        }

        let accessUrlByImageKey: Record<string, string> = {};
        const imageKeys = uniqueImageKeys(recentResponse.items);

        if (imageKeys.length > 0) {
          try {
            const accessUrls = await issueMediaAccessUrls({
              authToken,
              userId,
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

  const deleteMemoryItem = async (item: HistoryCardItem) => {
    if (!currentUser || deletingMemoryIds[item.memoryId]) {
      return;
    }

    setDeletingMemoryIds((current) => ({
      ...current,
      [item.memoryId]: true,
    }));
    setDeleteErrorMessage('');

    try {
      let authToken = currentUser.authToken;
      let userId = currentUser.userId;

      try {
        await deleteRecentMemory({
          authToken,
          userId,
          memoryId: item.memoryId,
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : '';
        if (!message.toLowerCase().includes('access token has expired')) {
          throw error;
        }

        const refreshedUser = await refreshSession();
        if (!refreshedUser) {
          throw error;
        }
        authToken = refreshedUser.authToken;
        userId = refreshedUser.userId;
        await deleteRecentMemory({
          authToken,
          userId,
          memoryId: item.memoryId,
        });
      }

      setItems((currentItems) =>
        currentItems.filter(
          (currentItem) => currentItem.memoryId !== item.memoryId
        )
      );
      setPendingDeleteMemoryId((currentMemoryId) =>
        currentMemoryId === item.memoryId ? null : currentMemoryId
      );
      setImageAspectRatios((currentRatios) => {
        const nextRatios = { ...currentRatios };
        delete nextRatios[item.memoryId];
        return nextRatios;
      });
    } catch (error) {
      setDeleteErrorMessage(
        error instanceof Error
          ? error.message
          : '기록을 삭제하는 중 문제가 생겼어요.'
      );
    } finally {
      setDeletingMemoryIds((current) => {
        const next = { ...current };
        delete next[item.memoryId];
        return next;
      });
    }
  };

  const confirmDeleteMemory = (item: HistoryCardItem) => {
    if (pendingDeleteMemoryId !== item.memoryId) {
      setPendingDeleteMemoryId(item.memoryId);
      setDeleteErrorMessage('');
      return;
    }

    void deleteMemoryItem(item);
  };

  return (
    <SafeAreaView style={commonStyles.screen}>
      <View style={commonStyles.header}>
        <Pressable
          style={({ pressed }) => pressableFeedback(pressed)}
          onPress={() => navigation.goBack()}
        >
          <Text style={styles.backButton}>{'<'}</Text>
        </Pressable>

        <Text style={commonStyles.headerTitle}>히스토리</Text>

        <View style={styles.headerSpacer} />
      </View>

      <ScrollView
        contentContainerStyle={[styles.list, commonStyles.contentContainer]}
      >
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

        {!isLoading && deleteErrorMessage ? (
          <View style={styles.deleteErrorBox}>
            <Text style={styles.deleteErrorText}>{deleteErrorMessage}</Text>
          </View>
        ) : null}

        {!isLoading && !errorMessage
          ? items.map((item) => {
              const itemName = item.detectedObjects[0] || item.tags[0] || '기록';
              const isDeleting = Boolean(deletingMemoryIds[item.memoryId]);
              const isConfirmingDelete =
                pendingDeleteMemoryId === item.memoryId;

              return (
                <View
                  key={item.memoryId}
                  style={commonStyles.card}
                >
                  <View style={styles.cardTop}>
                    <Text style={styles.cardTitle}>{itemName}</Text>
                    <View style={styles.cardActions}>
                      <Text style={styles.time}>
                        {formatRelativeTime(item.capturedAt)}
                      </Text>
                      <View style={styles.deleteActions}>
                        {isConfirmingDelete && !isDeleting ? (
                          <Pressable
                            style={({ pressed }) => [
                              styles.cancelDeleteButton,
                              pressed ? styles.deleteButtonPressed : null,
                            ]}
                            onPress={() => setPendingDeleteMemoryId(null)}
                          >
                            <Text style={styles.cancelDeleteButtonText}>취소</Text>
                          </Pressable>
                        ) : null}
                        <Pressable
                          disabled={isDeleting}
                          style={({ pressed }) => [
                            styles.deleteButton,
                            isConfirmingDelete ? styles.confirmDeleteButton : null,
                            pressed && !isDeleting
                              ? styles.deleteButtonPressed
                              : null,
                            isDeleting ? styles.deleteButtonDisabled : null,
                          ]}
                          onPress={() => confirmDeleteMemory(item)}
                        >
                          <Text style={styles.deleteButtonText}>
                            {isDeleting
                              ? '삭제 중'
                              : isConfirmingDelete
                                ? '삭제 확인'
                                : '삭제'}
                          </Text>
                        </Pressable>
                      </View>
                    </View>
                  </View>

                  {isConfirmingDelete ? (
                    <Text style={styles.deleteConfirmText}>
                      이 사진과 추론 정보를 삭제할까요?
                    </Text>
                  ) : null}

                  <Pressable
                    style={({ pressed }) => [
                      styles.cardBody,
                      pressableCardFeedback(pressed),
                    ]}
                    onPress={() => navigation.navigate('ItemLocation', { itemName })}
                  >
                    {item.accessUrl ? (
                      <Image
                        source={{ uri: item.accessUrl }}
                        style={[
                          styles.thumbnail,
                          imageAspectRatios[item.memoryId]
                            ? { aspectRatio: imageAspectRatios[item.memoryId] }
                            : styles.thumbnailFallback,
                        ]}
                        resizeMode="contain"
                        onLoad={(event) => handleImageLoad(item.memoryId, event)}
                      />
                    ) : null}

                    <Text style={styles.preview}>{describeMemory(item)}</Text>

                    <Text style={styles.detail}>
                      {item.positionHint ||
                        item.sceneSummary ||
                        item.caption ||
                        '상세 설명이 아직 없어요.'}
                    </Text>
                  </Pressable>
                </View>
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
  deleteErrorBox: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#fecaca',
    backgroundColor: '#fef2f2',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  deleteErrorText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#b91c1c',
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
    borderRadius: 12,
    marginBottom: 12,
    backgroundColor: colors.border,
  },
  thumbnailFallback: {
    height: 220,
  },
  cardBody: {
    borderRadius: 12,
  },
  cardTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
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
  cardActions: {
    alignItems: 'flex-end',
    gap: 6,
  },
  deleteActions: {
    flexDirection: 'row',
    gap: 6,
  },
  deleteButton: {
    minWidth: 52,
    minHeight: 30,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#fecaca',
    backgroundColor: '#fff5f5',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 10,
  },
  deleteButtonPressed: {
    opacity: 0.72,
  },
  confirmDeleteButton: {
    minWidth: 72,
    backgroundColor: '#fee2e2',
  },
  cancelDeleteButton: {
    minWidth: 48,
    minHeight: 30,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 10,
  },
  deleteButtonDisabled: {
    opacity: 0.5,
  },
  deleteButtonText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#b91c1c',
  },
  cancelDeleteButtonText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.subText,
  },
  deleteConfirmText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#b91c1c',
    marginBottom: 10,
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
