import React from 'react';
import { useNavigation } from '@react-navigation/native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { View, Text, StyleSheet, Pressable } from 'react-native';

import { useAuth } from '../context/AuthContext';
import { commonStyles } from '../styles/commonStyles';
import { colors } from '../styles/colors';

export default function ProfileScreen() {
  const navigation = useNavigation<any>();
  const { currentUser } = useAuth();

  return (
    <SafeAreaView style={commonStyles.screen}>
      <View style={commonStyles.header}>
        <Pressable onPress={() => navigation.goBack()}>
          <Text style={styles.backButton}>{'<'}</Text>
        </Pressable>

        <Text style={commonStyles.headerTitle}>Profile</Text>

        <View style={{ width: 24 }} />
      </View>

      <View style={styles.content}>
        <View style={styles.avatar}>
          <Text style={styles.avatarIcon}>
            {(currentUser?.displayName || 'U').slice(0, 1).toUpperCase()}
          </Text>
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>Display Name</Text>
          <View style={styles.inputBox}>
            <Text style={styles.value}>
              {currentUser?.displayName || 'Not set'}
            </Text>
          </View>
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>User ID</Text>
          <View style={styles.inputBox}>
            <Text style={styles.value}>{currentUser?.userId || 'Not set'}</Text>
          </View>
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>Device ID</Text>
          <View style={styles.inputBox}>
            <Text style={styles.value}>
              {currentUser?.deviceId || 'Not connected'}
            </Text>
          </View>
        </View>

        <Text style={styles.syncText}>
          Search and media requests now follow the signed-in user and the
          registered smart-glass device.
        </Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  content: {
    flex: 1,
    paddingHorizontal: 36,
    paddingTop: 48,
  },
  avatar: {
    width: 88,
    height: 88,
    borderRadius: 44,
    backgroundColor: '#DCEAFE',
    alignSelf: 'center',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 36,
  },
  avatarIcon: {
    fontSize: 36,
    fontWeight: '700',
    color: colors.primary,
  },
  fieldGroup: {
    marginBottom: 16,
  },
  label: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
    marginBottom: 8,
  },
  inputBox: {
    minHeight: 46,
    borderRadius: 12,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: colors.border,
    justifyContent: 'center',
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  value: {
    fontSize: 15,
    color: colors.text,
  },
  syncText: {
    fontSize: 12,
    color: colors.subText,
    textAlign: 'right',
    marginTop: 8,
    lineHeight: 18,
  },
  backButton: {
    fontSize: 24,
    color: colors.text,
    width: 24,
    lineHeight: 24,
  },
});
