import React from 'react';
import {
  StyleSheet,
  Text,
  View,
  Modal,
  TouchableOpacity,
  ScrollView,
} from 'react-native';

const SUPPORTED_GATEWAYS = [
  { id: 'gpay', name: 'Google Pay', icon: '🤖', scheme: 'tez' },
  { id: 'phonepe', name: 'PhonePe', icon: '💜', scheme: 'phonepe' },
  { id: 'paytm', name: 'Paytm', icon: '💎', scheme: 'paytmmp' },
  { id: 'bhim', name: 'BHIM App', icon: '🇮🇳', scheme: 'bhim' },
  { id: 'generic', name: 'Other / Default Chooser', icon: '🏦', scheme: 'upi' },
];

export default function PaymentGatewayModal({
  visible,
  merchantName,
  amount,
  onSelect,
  onClose,
}) {
  return (
    <Modal visible={visible} transparent={true} animationType="fade">
      <View style={styles.modalBlurView}>
        <View style={styles.modalContentCard}>
          <Text style={styles.modalTag}>💸 SELECT PAYMENT METHOD</Text>
          <Text style={styles.merchantLabel} numberOfLines={1}>
            To: {merchantName}
          </Text>
          <Text style={styles.amountLabel}>
            ₹{parseFloat(amount).toFixed(2)}
          </Text>

          <Text style={styles.selectionPrompt}>
            Choose your preferred financial provider:
          </Text>

          <ScrollView
            style={styles.gatewayList}
            showsVerticalScrollIndicator={false}
          >
            {SUPPORTED_GATEWAYS.map((gateway) => (
              <TouchableOpacity
                key={gateway.id}
                style={styles.gatewayRowButton}
                onPress={() => onSelect(gateway.scheme)}
              >
                <Text style={styles.gatewayIcon}>{gateway.icon}</Text>
                <Text style={styles.gatewayName}>{gateway.name}</Text>
                <Text style={styles.arrowPointer}>➔</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <TouchableOpacity style={styles.closeBtn} onPress={onClose}>
            <Text style={styles.closeBtnText}>Cancel and Abort</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  modalBlurView: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.8)',
  },
  modalContentCard: {
    backgroundColor: '#1C1C1E',
    width: '85%',
    borderRadius: 20,
    padding: 24,
    borderWidth: 1,
    borderColor: '#2C2C3E',
  },
  modalTag: {
    color: '#30D158',
    fontSize: 11,
    fontWeight: 'bold',
    letterSpacing: 1,
    textAlign: 'center',
  },
  merchantLabel: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '600',
    textAlign: 'center',
    marginTop: 12,
  },
  amountLabel: {
    color: '#FFFFFF',
    fontSize: 36,
    fontWeight: 'bold',
    textAlign: 'center',
    marginTop: 4,
    marginBottom: 16,
  },
  selectionPrompt: {
    color: '#8E8E93',
    fontSize: 12,
    marginBottom: 12,
    fontWeight: '500',
  },
  gatewayList: { maxHeight: 260 },
  gatewayRowButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#2C2C2E',
    padding: 14,
    borderRadius: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#3A3A3C',
  },
  gatewayIcon: { fontSize: 20, marginRight: 12 },
  gatewayName: { color: '#FFFFFF', fontSize: 15, fontWeight: '600', flex: 1 },
  arrowPointer: { color: '#636366', fontSize: 14 },
  closeBtn: {
    marginTop: 16,
    padding: 14,
    borderRadius: 10,
    alignItems: 'center',
    backgroundColor: 'rgba(255, 69, 58, 0.1)',
  },
  closeBtnText: { color: '#FF453A', fontWeight: 'bold', fontSize: 14 },
});
