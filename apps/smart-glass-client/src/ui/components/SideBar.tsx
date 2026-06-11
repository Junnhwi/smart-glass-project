import React, { useEffect, useRef, useState } from 'react';
import {
  Animated,
  Easing,
  Image,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { useAppNavigation } from '../navigation/appNavigation';
import { useAuth } from '../context/AuthContext';
import historyIcon from '../icon/history.png';
import logo from '../icon/logo.png';
import settingsIcon from '../icon/setting.png';
import userIcon from '../icon/user.png';
import { colors } from '../styles/colors';
import { pressableFeedback } from '../styles/pressableFeedback';

type SidebarProps = {
  visible: boolean;
  onClose: () => void;
};

export default function Sidebar({ visible, onClose }: SidebarProps) {
  const navigation = useAppNavigation();
  const { currentUser, getDeviceLabel, signOut } = useAuth();
  const [isRendered, setIsRendered] = useState(visible);
  const motion = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!visible) {
      return;
    }

    setIsRendered(true);
    motion.setValue(0);
    Animated.timing(motion, {
      toValue: 1,
      duration: 240,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    }).start();
  }, [motion, visible]);

  const requestClose = () => {
    Animated.timing(motion, {
      toValue: 0,
      duration: 190,
      easing: Easing.in(Easing.cubic),
      useNativeDriver: true,
    }).start(({ finished }) => {
      if (!finished) {
        return;
      }
      setIsRendered(false);
      onClose();
    });
  };

  const handleMove = (
    screen: 'Capture' | 'History' | 'Profile' | 'Settings'
  ) => {
    Animated.timing(motion, {
      toValue: 0,
      duration: 170,
      easing: Easing.in(Easing.cubic),
      useNativeDriver: true,
    }).start(() => {
      setIsRendered(false);
      onClose();
      navigation.navigate(screen);
    });
  };

  const handleLogout = () => {
    requestClose();
    void signOut();
  };

  const sidebarTranslateX = motion.interpolate({
    inputRange: [0, 1],
    outputRange: [-290, 0],
  });

  if (!isRendered) {
    return null;
  }

  return (
    <Modal
      visible={isRendered}
      transparent
      animationType="none"
      onRequestClose={requestClose}
    >
      <Animated.View style={[styles.overlay, { opacity: motion }]}>
        <Animated.View
          style={[
            styles.sidebarWrapper,
            { transform: [{ translateX: sidebarTranslateX }] },
          ]}
        >
          <View style={styles.sidebar}>
            <Text style={styles.title}>메뉴</Text>

            <View style={styles.accountCard}>
              <Text style={styles.accountName}>
                {currentUser?.displayName || '사용자'}
              </Text>
              <Text style={styles.accountId}>
                {currentUser?.userId || '로그인 정보 없음'}
              </Text>
              <Text style={styles.accountDevice}>
                현재 기기: {getDeviceLabel(currentUser?.deviceId)}
              </Text>
            </View>

            <Pressable
              style={({ pressed }) => [
                styles.menuItem,
                pressableFeedback(pressed),
              ]}
              onPress={() => handleMove('Capture')}
            >
              <Text style={styles.menuText}>업로드 홈</Text>
              <Image source={logo} style={styles.menuIconImage} />
            </Pressable>

            <Pressable
              style={({ pressed }) => [
                styles.menuItem,
                pressableFeedback(pressed),
              ]}
              onPress={() => handleMove('History')}
            >
              <Text style={styles.menuText}>히스토리</Text>
              <Image source={historyIcon} style={styles.menuIconImage} />
            </Pressable>

            <Pressable
              style={({ pressed }) => [
                styles.menuItem,
                pressableFeedback(pressed),
              ]}
              onPress={() => handleMove('Profile')}
            >
              <Text style={styles.menuText}>사용자 정보</Text>
              <Image source={userIcon} style={styles.menuIconImage} />
            </Pressable>

            <Pressable
              style={({ pressed }) => [
                styles.menuItem,
                pressableFeedback(pressed),
              ]}
              onPress={() => handleMove('Settings')}
            >
              <Text style={styles.menuText}>설정</Text>
              <Image source={settingsIcon} style={styles.menuIconImage} />
            </Pressable>

            <View style={styles.logoutArea}>
              <Pressable
                style={({ pressed }) => [
                  styles.logoutButton,
                  pressableFeedback(pressed),
                ]}
                onPress={handleLogout}
              >
                <Text style={styles.logoutText}>로그아웃</Text>
              </Pressable>
            </View>
          </View>
        </Animated.View>
        <Pressable style={styles.backdrop} onPress={requestClose} />
      </Animated.View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    flexDirection: 'row',
    backgroundColor: 'rgba(0,0,0,0.28)',
  },
  sidebarWrapper: {
    width: 280,
    height: '100%',
    backgroundColor: 'transparent',
  },
  sidebar: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    paddingTop: 72,
    paddingHorizontal: 20,
    borderTopRightRadius: 28,
    borderBottomRightRadius: 28,
  },
  backdrop: {
    flex: 1,
  },
  title: {
    fontSize: 22,
    fontWeight: '700',
    color: colors.text,
    marginBottom: 20,
  },
  accountCard: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: '#F8FAFC',
    padding: 14,
    marginBottom: 14,
    gap: 4,
  },
  accountName: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.text,
  },
  accountId: {
    fontSize: 13,
    color: colors.subText,
  },
  accountDevice: {
    fontSize: 12,
    color: colors.subText,
  },
  menuItem: {
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#F3F4F6',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  menuText: {
    fontSize: 16,
    color: colors.text,
    fontWeight: '500',
  },
  menuIconImage: {
    width: 20,
    height: 20,
    resizeMode: 'contain',
  },
  logoutArea: {
    marginTop: 'auto',
    paddingBottom: 24,
  },
  logoutButton: {
    paddingVertical: 12,
  },
  logoutText: {
    fontSize: 14,
    color: '#333333',
    fontWeight: '600',
  },
});
