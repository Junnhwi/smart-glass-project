# Smart Glass Client

Smart-glass client workspace for the mobile app and device-facing firmware.

## Layout

```text
apps/smart-glass-client/
|-- src/        # React Native app source
|-- assets/     # App assets
|-- firmware/   # Smart-glass device firmware sketches
`-- tests/
```

## Firmware

The current firmware sketch lives at:

```text
firmware/xiao-esp32s3-ble-camera/xiao-esp32s3-ble-camera.ino
```

It targets the Seeed Studio XIAO ESP32S3 Sense camera board and exposes a Nordic UART-style BLE service.

BLE contract:

- Device name: `XIAO_BLE_CAM`
- Service UUID: `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`
- RX characteristic: `6E400002-B5A3-F393-E0A9-E50E24DCCA9E`
- TX characteristic: `6E400003-B5A3-F393-E0A9-E50E24DCCA9E`
- RX command `1`: capture a JPEG frame and send it over TX notifications
- RX command `2`: enter ESP32 deep sleep
- TX payload starts with `--- START ---`, sends JPEG chunks, then ends with `--- END ---`

Open the sketch directory in Arduino IDE or compile it with Arduino CLI after installing the ESP32 board package and the camera/BLE dependencies used by the ESP32 Arduino core.
