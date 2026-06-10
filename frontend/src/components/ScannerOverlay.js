import React from 'react';
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { CameraView } from 'expo-camera';

export default function ScannerOverlay({
  isCameraReady,
  onCameraReady,
  onScan,
  scanned,
  onClose,
}) {
  return (
    <View
      style={[StyleSheet.absoluteFillObject, styles.fullScreenCameraContainer]}
    >
      <CameraView
        style={StyleSheet.absoluteFillObject}
        facing="back"
        onCameraReady={onCameraReady}
        onBarcodeScanned={scanned ? undefined : onScan}
        onBarCodeScanned={scanned ? undefined : onScan}
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
      />

      <View style={styles.overlayMaskTop}>
        {!isCameraReady && (
          <ActivityIndicator
            size="small"
            color="#30D158"
            style={{ marginTop: 'auto' }}
          />
        )}
      </View>
      <View style={styles.overlayMaskMiddleRow}>
        <View style={styles.overlayMaskSide} />
        <View style={styles.fullScreenTargetViewfinder}>
          <View
            style={[
              styles.cornerBracket,
              styles.topLeftCorner,
              !isCameraReady && styles.disabledBracketColor,
            ]}
          />
          <View
            style={[
              styles.cornerBracket,
              styles.topRightCorner,
              !isCameraReady && styles.disabledBracketColor,
            ]}
          />
          <View
            style={[
              styles.cornerBracket,
              styles.bottomLeftCorner,
              !isCameraReady && styles.disabledBracketColor,
            ]}
          />
          <View
            style={[
              styles.cornerBracket,
              styles.bottomRightCorner,
              !isCameraReady && styles.disabledBracketColor,
            ]}
          />
        </View>
        <View style={styles.overlayMaskSide} />
      </View>
      <View style={styles.overlayMaskBottom}>
        <Text style={styles.cameraInstructionsText}>
          {isCameraReady
            ? 'Center the UPI merchant QR code inside the box to scan'
            : 'Waking camera hardware optics...'}
        </Text>
        <TouchableOpacity
          style={styles.fullScreenCloseButton}
          onPress={onClose}
        >
          <Text style={styles.fullScreenCloseButtonText}>✕ Cancel Scan</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fullScreenCameraContainer: { zIndex: 999, backgroundColor: '#000000' },
  overlayMaskTop: {
    height: '25%',
    backgroundColor: 'rgba(0, 0, 0, 0.65)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  overlayMaskMiddleRow: { height: 250, flexDirection: 'row' },
  overlayMaskSide: { flex: 1, backgroundColor: 'rgba(0, 0, 0, 0.65)' },
  fullScreenTargetViewfinder: {
    width: 250,
    height: 250,
    backgroundColor: 'transparent',
    position: 'relative',
  },
  overlayMaskBottom: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.65)',
    alignItems: 'center',
    paddingHorizontal: 40,
    paddingTop: 20,
  },
  cameraInstructionsText: {
    color: '#AEAEB2',
    fontSize: 14,
    textAlign: 'center',
    lineHeight: 20,
    marginBottom: 40,
  },
  fullScreenCloseButton: {
    backgroundColor: 'rgba(255, 255, 255, 0.2)',
    paddingVertical: 14,
    paddingHorizontal: 36,
    borderRadius: 24,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.15)',
  },
  fullScreenCloseButtonText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '600',
  },
  cornerBracket: {
    position: 'absolute',
    width: 24,
    height: 24,
    borderColor: '#30D158',
    borderWidth: 4,
  },
  disabledBracketColor: { borderColor: '#48484A' },
  topLeftCorner: { top: 0, left: 0, borderRightWidth: 0, borderBottomWidth: 0 },
  topRightCorner: {
    top: 0,
    right: 0,
    borderLeftWidth: 0,
    borderBottomWidth: 0,
  },
  bottomLeftCorner: {
    bottom: 0,
    left: 0,
    borderRightWidth: 0,
    borderTopWidth: 0,
  },
  bottomRightCorner: {
    bottom: 0,
    right: 0,
    borderLeftWidth: 0,
    borderTopWidth: 0,
  },
});
