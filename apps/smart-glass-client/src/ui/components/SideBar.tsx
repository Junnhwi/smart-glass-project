import React from 'react';
import { Modal, View, Text, StyleSheet, Pressable, Image } from 'react-native';

import { useAppNavigation } from '../navigation/appNavigation';
import { useAuth } from '../context/AuthContext';
import historyIcon from '../icon/history.png';
import logo from '../icon/logo.png';
import settingsIcon from '../icon/setting.png';
import userIcon from '../icon/user.png';
import { colors } from '../styles/colors';

type SidebarProps = {
  visible: boolean;
  onClose: () => void;
};

export default function Sidebar({ visible, onClose }: SidebarProps) {
  const navigation = useAppNavigation();
  const { currentUser, getDeviceLabel, signOut } = useAuth();

  const handleMove = (
    screen: 'Capture' | 'History' | 'Profile' | 'Settings'
  ) => {
    onClose();
    navigation.navigate(screen);
  };

  const handleLogout = () => {
    onClose();
    void signOut();
  };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <View style={styles.overlay}>
        <View style={styles.sidebarWrapper}>
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
              style={styles.menuItem}
              onPress={() => handleMove('Capture')}
            >
              <Text style={styles.menuText}>업로드 홈</Text>
              <Image source={logo} style={styles.menuIconImage} />
            </Pressable>

            <Pressable
              style={styles.menuItem}
              onPress={() => handleMove('History')}
            >
              <Text style={styles.menuText}>히스토리</Text>
              <Image source={historyIcon} style={styles.menuIconImage} />
            </Pressable>

            <Pressable
              style={styles.menuItem}
              onPress={() => handleMove('Profile')}
            >
              <Text style={styles.menuText}>사용자 정보</Text>
              <Image source={userIcon} style={styles.menuIconImage} />
            </Pressable>

            <Pressable
              style={styles.menuItem}
              onPress={() => handleMove('Settings')}
            >
              <Text style={styles.menuText}>설정</Text>
              <Image source={settingsIcon} style={styles.menuIconImage} />
            </Pressable>

            <View style={styles.logoutArea}>
              <Pressable style={styles.logoutButton} onPress={handleLogout}>
                <Text style={styles.logoutText}>로그아웃</Text>
              </Pressable>
            </View>
          </View>
        </View>
        <Pressable style={styles.backdrop} onPress={onClose} />
      </View>
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
