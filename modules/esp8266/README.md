# ESP8266 HTTP server

## Protocol

Connect to `http://<device-ip>/` and send a single binary byte:

| Byte   | Action       |
| ------ | ------------ |
| `0x00` | Stop         |
| `0x01` | Forward      |
| `0x02` | Backward     |
| `0x03` | Rotate left  |
| `0x04` | Rotate right |

The firmware stops the motors when a client disconnects or when no command is
received for 500 ms.

Build with PlatformIO:

```sh
WIFI_SSID='your-ssid' WIFI_PASSWORD='your-password' pio run
```

Upload to the board:

```sh
WIFI_SSID='your-ssid' WIFI_PASSWORD='your-password' pio run --target upload
```

Send one or more motion words as a single request:

```sh
./send-motion.sh <device-ip> forward left stop
```

To forward ESP8266 logs into the hub's `/v1/logs` stream:

```sh
HUB_LOG_URL='http://<hub-ip>:8080/v1/logs' pio run
```
