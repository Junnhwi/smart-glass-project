#include "esp_camera.h"
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// --- XIAO ESP32S3 Sense 핀 설정 ---
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     10
#define SIOD_GPIO_NUM     40
#define SIOC_GPIO_NUM     39
#define Y9_GPIO_NUM       48
#define Y8_GPIO_NUM       11
#define Y7_GPIO_NUM       12
#define Y6_GPIO_NUM       14
#define Y5_GPIO_NUM       16
#define Y4_GPIO_NUM       18
#define Y3_GPIO_NUM       17
#define Y2_GPIO_NUM       15
#define VSYNC_GPIO_NUM    38
#define HREF_GPIO_NUM     47
#define PCLK_GPIO_NUM     13

BLEServer *pServer = NULL;
BLECharacteristic *pTxCharacteristic;
bool deviceConnected = false;
bool takePictureCmd = false;
bool sleepCmd = false; // 절전 모드 진입 명령 변수

#define SERVICE_UUID           "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_RX "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_TX "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) { 
      deviceConnected = true; 
    };
    void onDisconnect(BLEServer* pServer) { 
      deviceConnected = false; 
    }
};

class MyCallbacks: public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
      String rxValue = pCharacteristic->getValue().c_str();
      
      if (rxValue.length() > 0) {
        if (rxValue.indexOf("1") != -1) { 
          // "1" 수신 시 사진 촬영
          takePictureCmd = true;
        } 
        else if (rxValue.indexOf("2") != -1) { 
          // "2" 수신 시 절전 모드 진입
          sleepCmd = true;
        }
      }
    }
};

void setup() {
  Serial.begin(115200);
  // 잠에서 깨어났을 때 로그 확인을 위해 대기
  delay(2000); 
  Serial.println("\n=== XIAO 무선 카메라 모드 시작 ===");

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM; config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM; config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM; config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM; config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM; config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM; config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM; config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM; config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  
  config.frame_size = FRAMESIZE_VGA; 
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 10;
  config.fb_count = 1;

  if (esp_camera_init(&config) != ESP_OK) {
    Serial.println("카메라 초기화 실패!");
    return;
  }

  // 색감 교정 설정
  sensor_t * s = esp_camera_sensor_get();
  s->set_wb_mode(s, 3); // Office 모드
  s->set_brightness(s, 1);

  BLEDevice::init("XIAO_BLE_CAM");
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());
  BLEService *pService = pServer->createService(SERVICE_UUID);
  
  pTxCharacteristic = pService->createCharacteristic(
                        CHARACTERISTIC_UUID_TX,
                        BLECharacteristic::PROPERTY_NOTIFY
                      );
  pTxCharacteristic->addDescriptor(new BLE2902());
  
  BLECharacteristic * pRxCharacteristic = pService->createCharacteristic(
                        CHARACTERISTIC_UUID_RX,
                        BLECharacteristic::PROPERTY_WRITE
                      );
  pRxCharacteristic->setCallbacks(new MyCallbacks());
  
  pService->start();
  pServer->getAdvertising()->start();
  
  Serial.println("블루투스 대기 중... ('1' 수신 시 촬영, '2' 수신 시 수동 절전모드)");
}

void loop() {
  // 1. 촬영 명령 처리
  if (takePictureCmd) {
    takePictureCmd = false;
    sendPhotoOverBLE();
  }

  // 2. 절전 명령 처리
  if (sleepCmd) {
    Serial.println("수동 절전 명령('2') 수신. 즉시 Deep Sleep 진입...");
    delay(1000); // 시리얼 출력 및 BLE 통신 마무리를 위한 여유 시간
    esp_deep_sleep_start();
  }
  
  delay(10);
}

void sendPhotoOverBLE() {
  if (!deviceConnected) return;

  // 웜업 촬영 10장
  for (int i = 0; i < 10; i++) {
    camera_fb_t * fb_tmp = esp_camera_fb_get();
    if (fb_tmp) { esp_camera_fb_return(fb_tmp); delay(50); }
  }

  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) return;

  size_t image_size = fb->len;
  size_t chunk_size = 128;
  uint8_t *image_data = fb->buf;
  
  pTxCharacteristic->setValue("--- START ---");
  pTxCharacteristic->notify();
  delay(500);

  for(size_t i = 0; i < image_size; i += chunk_size) {
    size_t current_chunk = (image_size - i < chunk_size) ? (image_size - i) : chunk_size;
    pTxCharacteristic->setValue(image_data + i, current_chunk);
    pTxCharacteristic->notify();
    delay(30);
  }

  delay(500);
  pTxCharacteristic->setValue("--- END ---");
  pTxCharacteristic->notify();
  
  esp_camera_fb_return(fb);
}