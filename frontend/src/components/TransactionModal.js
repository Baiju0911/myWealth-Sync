import React from 'react';
import {
  StyleSheet,
  Text,
  View,
  Modal,
  KeyboardAvoidingView,
  TextInput,
  TouchableOpacity,
  Platform,
} from 'react-native';

export default function TransactionModal({
  visible,
  merchantName,
  value,
  onChangeValue,
  onDrop,
  onConfirm,
}) {
  return (
    <Modal visible={visible} transparent={true} animationType="slide">
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.modalBlurView}
      >
        <View style={styles.modalContentCard}>
          <Text style={styles.modalTag}>🎯 LEDGER INTEGRITY SCAN</Text>
          <Text style={styles.modalMerchantName}>{merchantName}</Text>

          <Text style={styles.inputLabel}>Confirm Intent Amount (₹)</Text>
          <TextInput
            style={styles.amountInput}
            keyboardType="numeric"
            value={value}
            onChangeText={onChangeValue}
            autoFocus={true}
          />

          <View style={styles.modalActionRow}>
            <TouchableOpacity style={styles.cancelBtn} onPress={onDrop}>
              <Text style={styles.cancelBtnText}>Drop Scan</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.confirmBtn} onPress={onConfirm}>
              <Text style={styles.confirmBtnText}>💾 Cache Internally</Text>
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  modalBlurView: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(0,0,0,0.75)',
  },
  modalContentCard: {
    backgroundColor: '#1C1C1E',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 24,
    borderWidth: 1,
    borderColor: '#2C2C3E',
  },
  modalTag: {
    color: '#FF9500',
    fontSize: 11,
    fontWeight: 'bold',
    letterSpacing: 1,
  },
  modalMerchantName: {
    color: '#FFFFFF',
    fontSize: 20,
    fontWeight: 'bold',
    marginTop: 6,
    marginBottom: 20,
  },
  inputLabel: { color: '#AEAEB2', fontSize: 13, marginBottom: 8 },
  amountInput: {
    backgroundColor: '#2C2C2E',
    color: '#FFFFFF',
    fontSize: 28,
    fontWeight: 'bold',
    padding: 14,
    borderRadius: 12,
    textAlign: 'center',
    marginBottom: 24,
  },
  modalActionRow: { flexDirection: 'row', gap: 12 },
  cancelBtn: {
    flex: 1,
    backgroundColor: '#2C2C2E',
    padding: 14,
    borderRadius: 10,
    alignItems: 'center',
  },
  cancelBtnText: { color: '#FF453A', fontWeight: 'bold' },
  confirmBtn: {
    flex: 2,
    backgroundColor: '#30D158',
    padding: 14,
    borderRadius: 10,
    alignItems: 'center',
  },
  confirmBtnText: { color: '#000000', fontWeight: 'bold' },
});
