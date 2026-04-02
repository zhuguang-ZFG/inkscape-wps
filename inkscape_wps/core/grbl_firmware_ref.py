"""与 GRBL 固件串口缓冲相关的**参考常数**（编译期默认值，供上位机默认配置与说明引用）。

主要对照 **Grbl_Esp32**（<https://github.com/bdring/Grbl_Esp32>），本地克隆可查看：

- ``Grbl_Esp32/src/Serial.h``：未在 ``Config.h`` 等覆盖时，``RX_BUFFER_SIZE`` 默认为 **256**。
- ``Grbl_Esp32/src/Uart.cpp``：``uart_driver_install(..., 256, ...)`` 的 UART 接收缓冲为 **256** 字节量级。

部分分支里 ``Report.cpp`` 的 ``Bf:`` 字段通过 ``client_get_rx_buffer_available()`` 上报「RX 剩余空间」；
**空闲、无待发字符时**，该值接近当前固件使用的串口接收容量（具体以固件实现为准）。

经典 **ATmega328p 单文件 Grbl** 常见 ``RX_BUFFER_SIZE`` 为 **128**。若与你的板子不符，请用手动或「Bf→RX」同步。
"""

GRBL_ESP32_DEFAULT_RX_BUFFER_SIZE: int = 256
GRBL_CLASSIC_AVR_DEFAULT_RX_BUFFER_SIZE: int = 128
