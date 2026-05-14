import React, { useEffect, useMemo, useRef, useState } from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import Sidebar from '../components/SideBar';
import logo from '../icon/logo.png';
import micIcon from '../icon/mic.png';
import { useAuth } from '../context/AuthContext';
import { useItemContext } from '../context/ItemContext';
import { useAppNavigation } from '../navigation/appNavigation';
import { commonStyles } from '../styles/commonStyles';
import {
  ApiRequestError,
  chatWithMemories,
  issueMediaAccessUrls,
  type MemorySearchHit,
} from '../../networking/api';

type RelatedImage = {
  imageKey: string;
  accessUrl: string;
  itemName: string;
  locationText?: string | null;
  capturedAt?: string | null;
  caption?: string | null;
  sceneSummary?: string | null;
  positionHint?: string | null;
};

type Message = {
  id: number;
  sender: 'bot' | 'user';
  text: string;
  relatedImages?: RelatedImage[];
};

const knownItems = ['지갑', '이어폰', '노트북', '가방', '열쇠', '안경', '카드'];
const suggestedQueries = [
  '내 지갑 어디 있었지?',
  '이어폰 마지막으로 본 곳 알려줘',
  '노트북이 있던 장면 찾아줘',
];

const uniqueImageKeysFromHits = (hits: MemorySearchHit[]) => {
  const seen = new Set<string>();
  const keys: string[] = [];

  hits.forEach((hit) => {
    if (!hit.imageKey || seen.has(hit.imageKey)) {
      return;
    }
    seen.add(hit.imageKey);
    keys.push(hit.imageKey);
  });

  return keys;
};

const buildRelatedImages = (
  hits: MemorySearchHit[],
  accessUrlByImageKey: Record<string, string>,
  fallbackQuery: string
) => {
  return hits
    .map((hit) => {
      if (!hit.imageKey) {
        return null;
      }

      const accessUrl = accessUrlByImageKey[hit.imageKey] || hit.imageUrl;
      if (!accessUrl) {
        return null;
      }

      return {
        imageKey: hit.imageKey,
        accessUrl,
        itemName:
          hit.detectedObjects[0] || hit.tags[0] || fallbackQuery || '기록',
        locationText: hit.location?.name || hit.location?.address || null,
        capturedAt: hit.capturedAt,
        caption: hit.caption,
        sceneSummary: hit.sceneSummary,
        positionHint: hit.positionHint,
      };
    })
    .filter(Boolean) as RelatedImage[];
};

export default function ChatScreen() {
  const navigation = useAppNavigation();
  const { currentUser, refreshSession, signOut } = useAuth();
  const { addItem } = useItemContext();

  const [sidebarVisible, setSidebarVisible] = useState(false);
  const [isSearchMode, setIsSearchMode] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [inputText, setInputText] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isBotTyping, setIsBotTyping] = useState(false);

  const scrollViewRef = useRef<ScrollView>(null);
  const inputRef = useRef<TextInput>(null);
  const messagePositions = useRef<Record<number, number>>({});
  const [currentMatchIndex, setCurrentMatchIndex] = useState(0);

  const matchedMessageIds = useMemo(() => {
    const keyword = searchText.trim().toLowerCase();
    if (!keyword) {
      return [];
    }

    return messages
      .filter((message) => message.text.toLowerCase().includes(keyword))
      .map((message) => message.id);
  }, [messages, searchText]);

  const scrollToBottom = () => {
    setTimeout(() => {
      scrollViewRef.current?.scrollToEnd({ animated: true });
    }, 100);
  };

  const goToMatch = (index: number) => {
    if (matchedMessageIds.length === 0) {
      return;
    }

    const safeIndex =
      ((index % matchedMessageIds.length) + matchedMessageIds.length) %
      matchedMessageIds.length;
    const targetId = matchedMessageIds[safeIndex];
    const y = messagePositions.current[targetId] ?? 0;

    scrollViewRef.current?.scrollTo({
      y: Math.max(y - 20, 0),
      animated: true,
    });

    setCurrentMatchIndex(safeIndex);
  };

  useEffect(() => {
    if (matchedMessageIds.length > 0) {
      setCurrentMatchIndex(0);
      setTimeout(() => goToMatch(0), 50);
      return;
    }

    setCurrentMatchIndex(0);
  }, [matchedMessageIds.length, searchText, messages]);

  const renderHighlightedText = (text: string, sender: 'bot' | 'user') => {
    const keyword = searchText.trim();
    const baseTextStyle =
      sender === 'user' ? styles.userMessageText : styles.botMessageText;

    if (!keyword) {
      return <Text style={baseTextStyle}>{text}</Text>;
    }

    const lowerText = text.toLowerCase();
    const lowerKeyword = keyword.toLowerCase();

    if (!lowerText.includes(lowerKeyword)) {
      return <Text style={baseTextStyle}>{text}</Text>;
    }

    const parts: React.ReactNode[] = [];
    let startIndex = 0;
    let matchIndex = 0;

    while (startIndex < text.length) {
      const foundIndex = lowerText.indexOf(lowerKeyword, startIndex);

      if (foundIndex === -1) {
        parts.push(
          <Text key={`text-${startIndex}`}>{text.slice(startIndex)}</Text>
        );
        break;
      }

      if (foundIndex > startIndex) {
        parts.push(
          <Text key={`text-${startIndex}`}>
            {text.slice(startIndex, foundIndex)}
          </Text>
        );
      }

      parts.push(
        <Text key={`match-${matchIndex}`} style={styles.highlightText}>
          {text.slice(foundIndex, foundIndex + keyword.length)}
        </Text>
      );

      startIndex = foundIndex + keyword.length;
      matchIndex += 1;
    }

    return <Text style={baseTextStyle}>{parts}</Text>;
  };

  const sendQuery = async (rawText: string) => {
    if (!currentUser) {
      return;
    }

    const trimmed = rawText.trim();
    if (!trimmed) {
      return;
    }

    const foundItem = knownItems.find((item) => trimmed.includes(item));
    if (foundItem) {
      addItem(foundItem);
    }

    const userMessage: Message = {
      id: Date.now(),
      sender: 'user',
      text: trimmed,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputText('');
    setIsBotTyping(true);
    scrollToBottom();

    try {
      const runChatRequest = async (authToken: string, userId: string) =>
        chatWithMemories({
          authToken,
          userId,
          query: trimmed,
          topK: 3,
        });

      let activeSession = currentUser;
      let chatResponse;

      try {
        chatResponse = await runChatRequest(
          activeSession.authToken,
          activeSession.userId
        );
      } catch (error) {
        if (
          error instanceof ApiRequestError &&
          error.status === 401 &&
          activeSession.refreshToken
        ) {
          const refreshedUser = await refreshSession();
          if (!refreshedUser) {
            throw error;
          }
          activeSession = refreshedUser;
          chatResponse = await runChatRequest(
            refreshedUser.authToken,
            refreshedUser.userId
          );
        } else {
          throw error;
        }
      }

      const imageKeys = uniqueImageKeysFromHits(chatResponse.hits);
      let accessUrlByImageKey: Record<string, string> = {};

      if (imageKeys.length > 0) {
        try {
          const accessUrls = await issueMediaAccessUrls({
            authToken: activeSession.authToken,
            userId: activeSession.userId,
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

      const relatedImages = buildRelatedImages(
        chatResponse.hits,
        accessUrlByImageKey,
        trimmed
      );

      const botMessage: Message = {
        id: Date.now() + 1,
        sender: 'bot',
        text: chatResponse.answer || '관련 기록을 찾지 못했어요.',
        relatedImages,
      };

      setMessages((prev) => [...prev, botMessage]);
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 401) {
        void signOut();
      }

      const botMessage: Message = {
        id: Date.now() + 1,
        sender: 'bot',
        text: '답변을 불러오지 못했어요. 잠시 후 다시 시도해주세요.',
      };

      setMessages((prev) => [...prev, botMessage]);
    } finally {
      setIsBotTyping(false);
      scrollToBottom();
    }
  };

  const handleSend = () => {
    const draft = inputText.trim();
    if (!draft) {
      return;
    }

    void sendQuery(draft);
    setTimeout(() => {
      inputRef.current?.focus();
    }, 0);
  };

  const handleMicPress = () => {
    const botMessage: Message = {
      id: Date.now(),
      sender: 'bot',
      text: '음성 입력 기능은 곧 추가할 수 있도록 버튼만 먼저 열어두었어요.',
    };

    setMessages((prev) => [...prev, botMessage]);
    scrollToBottom();
  };

  return (
    <SafeAreaView style={commonStyles.screen}>
      <View style={commonStyles.header}>
        {isSearchMode ? (
          <>
            <TextInput
              value={searchText}
              onChangeText={setSearchText}
              placeholder="대화 내용 검색"
              placeholderTextColor="#9CA3AF"
              style={styles.searchInput}
              autoFocus
            />
            <Pressable
              onPress={() => {
                setIsSearchMode(false);
                setSearchText('');
              }}
            >
              <Text style={styles.cancel}>닫기</Text>
            </Pressable>
          </>
        ) : (
          <>
            <Pressable
              style={styles.menuButton}
              onPress={() => setSidebarVisible(true)}
            >
              <Text style={styles.menuText}>≡</Text>
            </Pressable>

            <View style={styles.headerCenter}>
              <Image source={logo} style={styles.headerLogo} />
            </View>

            <Pressable
              style={styles.searchButton}
              onPress={() => setIsSearchMode(true)}
            >
              <Text style={styles.searchIcon}>⌕</Text>
            </Pressable>
          </>
        )}
      </View>

      {isSearchMode && searchText.trim() ? (
        <View style={styles.searchInfoBar}>
          <Text style={styles.searchInfoText}>
            {matchedMessageIds.length > 0
              ? `${currentMatchIndex + 1} / ${matchedMessageIds.length}`
              : '검색 결과 0건'}
          </Text>

          <View style={styles.searchActions}>
            <Pressable
              style={styles.searchMoveButton}
              onPress={() => goToMatch(currentMatchIndex - 1)}
            >
              <Text style={styles.searchMoveText}>이전</Text>
            </Pressable>

            <Pressable
              style={styles.searchMoveButton}
              onPress={() => goToMatch(currentMatchIndex + 1)}
            >
              <Text style={styles.searchMoveText}>다음</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      <ScrollView
        ref={scrollViewRef}
        contentContainerStyle={[styles.chatArea, commonStyles.contentContainer]}
      >
        {messages.length === 0 ? (
          <>
            <View style={styles.emptyBox}>
              <Text style={styles.emptyTitle}>무엇을 찾고 있나요?</Text>
              <Text style={styles.emptyText}>
                예: 내 지갑 어디 있었지?, 이어폰 마지막으로 본 곳 알려줘
              </Text>
            </View>

            <View style={styles.suggestionSection}>
              <Text style={styles.suggestionTitle}>바로 질문해보기</Text>
              <View style={styles.suggestionList}>
                {suggestedQueries.map((query) => (
                  <Pressable
                    key={query}
                    style={styles.suggestionChip}
                    onPress={() => {
                      void sendQuery(query);
                    }}
                  >
                    <Text style={styles.suggestionChipText}>{query}</Text>
                  </Pressable>
                ))}
              </View>
            </View>
          </>
        ) : null}

        {messages.map((message) => {
          const isMatched = matchedMessageIds.includes(message.id);

          return (
            <View
              key={message.id}
              onLayout={(event) => {
                messagePositions.current[message.id] =
                  event.nativeEvent.layout.y;
              }}
              style={[
                message.sender === 'bot'
                  ? styles.botMessage
                  : styles.userMessage,
                isMatched && styles.matchedMessage,
                isMatched &&
                  matchedMessageIds[currentMatchIndex] === message.id &&
                  styles.activeMatchedMessage,
              ]}
            >
              {renderHighlightedText(message.text, message.sender)}

              {message.relatedImages?.length ? (
                <View style={styles.relatedImagesBlock}>
                  <Text style={styles.relatedImagesTitle}>관련 이미지</Text>
                  <ScrollView
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    contentContainerStyle={styles.relatedImagesList}
                  >
                    {message.relatedImages.map((image) => (
                      <Pressable
                        key={image.imageKey}
                        style={styles.relatedImageCard}
                        onPress={() =>
                          navigation.navigate('ItemLocation', {
                            itemName: image.itemName,
                          })
                        }
                      >
                        <Image
                          source={{ uri: image.accessUrl }}
                          style={styles.relatedImage}
                        />
                        <View style={styles.relatedImageMeta}>
                          <Text
                            numberOfLines={1}
                            style={styles.relatedImageItemName}
                          >
                            {image.itemName}
                          </Text>
                          <Text
                            numberOfLines={1}
                            style={styles.relatedImageLocation}
                          >
                            {image.locationText || image.capturedAt || '기록 보기'}
                          </Text>
                        </View>
                        <Text
                          numberOfLines={2}
                          style={styles.relatedImageCaption}
                        >
                          {image.positionHint ||
                            image.sceneSummary ||
                            image.caption ||
                            '눌러서 위치 기록 보기'}
                        </Text>
                        <Text style={styles.relatedImageAction}>위치 보기</Text>
                      </Pressable>
                    ))}
                  </ScrollView>
                </View>
              ) : null}
            </View>
          );
        })}

        {isBotTyping ? (
          <View style={styles.botMessage}>
            <Text style={styles.botMessageText}>답변을 준비하고 있어요...</Text>
          </View>
        ) : null}
      </ScrollView>

      <View style={styles.inputArea}>
        <View style={styles.inputInner}>
          <TextInput
            ref={inputRef}
            value={inputText}
            onChangeText={setInputText}
            placeholder="찾고 싶은 물건이나 장면을 입력하세요"
            placeholderTextColor="#9CA3AF"
            style={styles.input}
            onSubmitEditing={handleSend}
            blurOnSubmit={false}
          />

          {inputText.trim() ? (
            <Pressable style={styles.sendButton} onPress={handleSend}>
              <Text style={styles.actionButtonText}>전송</Text>
            </Pressable>
          ) : (
            <Pressable style={styles.micButton} onPress={handleMicPress}>
              <Image source={micIcon} style={styles.micIcon} />
            </Pressable>
          )}
        </View>
      </View>

      <Sidebar
        visible={sidebarVisible}
        onClose={() => setSidebarVisible(false)}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  menuButton: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  menuText: {
    fontSize: 20,
    color: '#111827',
  },
  searchButton: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  searchIcon: {
    fontSize: 20,
    color: '#111827',
  },
  searchInput: {
    flex: 1,
    height: 40,
    backgroundColor: '#F3F4F6',
    borderRadius: 20,
    paddingHorizontal: 14,
    fontSize: 15,
    color: '#111827',
  },
  cancel: {
    marginLeft: 10,
    color: '#2563EB',
    fontWeight: '500',
    fontSize: 16,
  },
  searchInfoBar: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: '#FFF7D6',
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  searchInfoText: {
    fontSize: 13,
    color: '#7C5E10',
    fontWeight: '600',
  },
  searchActions: {
    flexDirection: 'row',
    gap: 8,
  },
  searchMoveButton: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#FFFFFF',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#E5E7EB',
  },
  searchMoveText: {
    fontSize: 12,
    color: '#374151',
    fontWeight: '600',
  },
  chatArea: {
    padding: 16,
    gap: 12,
  },
  emptyBox: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 18,
    alignItems: 'center',
    marginTop: 8,
  },
  emptyTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#111827',
    marginBottom: 6,
  },
  emptyText: {
    fontSize: 14,
    color: '#6B7280',
    textAlign: 'center',
    lineHeight: 20,
  },
  suggestionSection: {
    gap: 10,
  },
  suggestionTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#4B5563',
  },
  suggestionList: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  suggestionChip: {
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 999,
    backgroundColor: '#EFF6FF',
    borderWidth: 1,
    borderColor: '#BFDBFE',
  },
  suggestionChipText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#1D4ED8',
  },
  botMessage: {
    alignSelf: 'flex-start',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 16,
    maxWidth: '82%',
  },
  botMessageText: {
    fontSize: 15,
    color: '#111827',
    lineHeight: 22,
  },
  userMessage: {
    alignSelf: 'flex-end',
    backgroundColor: '#2563EB',
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 16,
    maxWidth: '82%',
  },
  userMessageText: {
    fontSize: 15,
    color: '#FFFFFF',
    lineHeight: 22,
  },
  matchedMessage: {
    borderWidth: 2,
    borderColor: '#FACC15',
  },
  activeMatchedMessage: {
    borderColor: '#EAB308',
  },
  highlightText: {
    backgroundColor: '#FDE68A',
    color: '#111827',
    fontWeight: '700',
  },
  relatedImagesBlock: {
    marginTop: 12,
    gap: 8,
  },
  relatedImagesTitle: {
    fontSize: 12,
    color: '#4B5563',
    fontWeight: '700',
  },
  relatedImagesList: {
    gap: 10,
  },
  relatedImageCard: {
    width: 152,
    backgroundColor: '#F9FAFB',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#E5E7EB',
    overflow: 'hidden',
  },
  relatedImage: {
    width: '100%',
    height: 104,
    backgroundColor: '#E5E7EB',
  },
  relatedImageMeta: {
    paddingHorizontal: 8,
    paddingTop: 8,
    gap: 2,
  },
  relatedImageItemName: {
    fontSize: 12,
    fontWeight: '700',
    color: '#111827',
  },
  relatedImageLocation: {
    fontSize: 11,
    color: '#6B7280',
  },
  relatedImageCaption: {
    paddingHorizontal: 8,
    paddingTop: 8,
    fontSize: 12,
    lineHeight: 16,
    color: '#374151',
    minHeight: 48,
  },
  relatedImageAction: {
    paddingHorizontal: 8,
    paddingBottom: 8,
    fontSize: 12,
    fontWeight: '700',
    color: '#2563EB',
  },
  inputArea: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 20,
    borderTopWidth: 1,
    borderTopColor: '#E5E7EB',
    backgroundColor: '#FFFFFF',
  },
  inputInner: {
    width: '100%',
    maxWidth: 720,
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  input: {
    flex: 1,
    height: 48,
    backgroundColor: '#F3F4F6',
    borderRadius: 24,
    paddingHorizontal: 16,
    fontSize: 15,
    color: '#111827',
  },
  sendButton: {
    minWidth: 64,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#111827',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  micButton: {
    minWidth: 64,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#F1F5F9',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  micIcon: {
    width: 22,
    height: 22,
    resizeMode: 'contain',
  },
  headerCenter: {
    flex: 1,
    alignItems: 'center',
  },
  headerLogo: {
    width: 40,
    height: 40,
    resizeMode: 'contain',
  },
  actionButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
});
