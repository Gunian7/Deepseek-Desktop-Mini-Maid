# Arcs-Mini3（LS26 / LS2684）官方文档摘要

> 来源：https://docs2.listenai.com （聆思文档中心）
> 抓取日期：2026-10-24　共整理 40+ 篇 LS26 系列页面
> 本文只做索引与要点，原始正文见本目录 `raw/`（如已保存）

---

## 1. 硬件（Arcs-Mini3 / 板型 ID `arcs_mini3`）

| 项目 | 规格 |
|---|---|
| 主控 | LS26 系列（文档三处写法不一致，见 §6 矛盾点） |
| 内存 | 8MB PSRAM：AP 核 3MB @0x28000000，CP 核 5MB @0x28300000 |
| Flash | PY25Q128HA 16MB |
| 外扩 MCU | CH32V003，I2C1 @0x6c，扩展 GPIO/ADC/PWM/充电检测/TF 检测 |
| 屏幕 | 1.54" 240×240 ST7789P3，4 线 SPI，旋转 180°，TE 同步，背光 PWM 2kHz |
| 摄像头 | GC0328 30 万像素，DVP，I2C1 配置，PWDN 在 exgpiod-6（低电平释放，延时 100ms） |
| 音频 | 单麦（模拟）+ NS4150B 功放（PA_MUTE = exgpioc-2，低有效静音） |
| 电池 | 500mAh，3.7V/4.2V，3pin 带 NTC（**严禁只接 2pin**） |
| 存储 | TF 卡 SDIO（PA04~PA09，原生 func15），TF_DET = exgpiod-3，热插拔重挂载 |
| USB | 单 Type-C **双角色**：Device（MSC + UAC + ADB）/ Host（CDC-ACM、CH34X、HID），角色由 I2C1 @0x31 控制器硬件检测自动切换 |
| 4G | 可选模组，UART2（PB06/PB07）+ PA00 电源 / PA01 复位 + exgpiod-4 检测 |
| 用户 LED | 3 颗（exgpioa-2 / exgpioc-0 / exgpioc-3，低有效） |
| 尺寸 | 外壳 47×54.5×29.5mm，PCBA 47×43mm / 1.6mm / 4 层 |

### 关键：Mini3 可用扩展 IO 极少
大部分 GPIO 被屏幕/摄像头/TF/USB/音频/电源占用，且**不能与 Mini2 混用**。示例中常用的扩展口全部是复用：

| 引脚 | 默认用途 | 被示例复用为 |
|---|---|---|
| PA00 | EXT4G_PWR | PWM0 CH0（舵机）、I2C1 SDA |
| PA01 | EXT4G_RST | I2C1 SCL |
| PB06 | UART2 TX（4G） | UART2 TX / I2C0 SDA |
| PB07 | UART2 RX（4G） | UART2 RX / I2C0 SCL / PWM0 CH7 |

> 结论：Mini3 想外接设备，基本要在「4G 控制 / 外部串口 / I2C / PWM」之间做取舍。板载 9pin 扩展座的具体引脚需查原理图（文档里只有图片）。

---

## 2. 软件栈与仓库结构

仓库：`git clone https://cloud.listenai.com/CSKG836746/arcs-sdk/public/arcs_mini.git`（**私有 GitLab，需要聆思账号 → 访问令牌**）

```
arcs_mini/
├── apps/arcs-mini/          ← CP 核应用：产品业务、prj.conf、services/、mcp-tools/、button/、miniapp/
├── apps/remote-ap/           ← AP 核固件（算法侧），仅在改算法时单独构建
├── apps-ui/                  ← UI 应用与资源（表情、界面，模型层 model_voice.c 在这里）
├── src/                      ← 项目级公共代码：middleware/、category/、server/lschat_server/、shell/
├── boards/                   ← 产品变体覆盖配置
├── arcs-sdk/                 ← 子模块：SoC / FreeRTOS / HAL / 驱动 / 板型 / 构建系统
│   └── boards/arcs_mini3/    ← pinmux.h、board.c、board.h、Kconfig、overlay.conf
├── modules/                  ← ebus、lisaui、lschat
├── res/arcs-mini3/           ← Mini3 专用 boot / AP / 分区表 / 提示音 / 唤醒词 / 表情
└── build*.ps1|sh、adb_download.*、tools/(cskburn, adb)
```

- RTOS：**FreeRTOS**（不是 CSK6 那套 Zephyr）
- GUI：LVGL v7/v8
- 实际生效配置以 `build/.config` 为准；应用默认配置 `apps/arcs-mini/prj.conf`，Mini3 叠加 `arcs_mini3.conf`
- 仓库自带 `.agents/skills/`：`coding / build / device / flash / run-log / review / commit / mcp / local-memory`，供 AI Agent 按项目规范执行

---

## 3. 标准工作流

1. **环境**：Windows 装 python + git → clone → 在仓库根目录执行 `./arcs-sdk/env.ps1`（工具链装到 `C:\Users\<user>\.listenai`，可用 `LISTENAI_HOME` 改路径）
2. **编译**：
   - Windows：`.\build.ps1 -S .\apps\arcs-mini -B build-arcs-mini3 -DBOARD=arcs_mini3`
   - Linux：`./build.sh -S ./apps/arcs-mini -B build-arcs-mini3 -DBOARD=arcs_mini3`
   - 产物：`arcs-mini.hex / .bin / .lpk / .ota.txz / .ota-info.txt`
3. **烧录**（两条路）
   - 脚本：`.\adb_download.ps1 -S res\arcs-mini3 -B build-arcs-mini3 app`（会校验 product/model/device 与板型一致，不匹配直接中文报错停止）
   - GUI：cskburn desktop（v1.2）— 按住功能键 + 点 RST 进 Recovery（屏显「ADB更新模式」），或 `adb shell recovery`，再拖 .hex/.lpk 烧
   - 串口烧录：拆机接 TX/RX/GND，DTR/RTS 自动进升级模式；或短接 TX-GND 后按 RST
4. **日志**：`adb shell` 交互（shell 支持 version / device / wifi / sd / kv / reboot / threads / heap / gain / interact start|stop）；串口 921600 更完整（能拿到上电瞬间日志）
5. **OTA**：改 `apps/arcs-mini/version` → 编译 → LSPlatform 应用模板中心建「大模型语音交互」应用 → 上传 ota 包 → 设备联网自动升级（电量 >50% 或接 USB 才触发）
6. **关闭 OTA（调试必做）**：`adb shell kv set int user.disable_app_update 1`，否则云端会把你的固件刷掉

---

## 4. 能力边界（能做什么 / 不能做什么）

### 能做
- **端侧 MCP 工具**：`MCP_TOOL_DEFINE(name, list_cb, call_cb)` 注册，云端 LLM 通过语音调用；已有内置工具：音量/亮度/设备信息/闹钟/LED/拍照识图/闻声图/交互模式/TF 卡音乐/上传日志/表情/play_audio_link/退出对话/酷我音乐/播放控制/版本查询/小应用
- **云端配置（零代码）**：小聆AI 小程序或 LSPlatform —— 人设提示词、声音复刻、唤醒词+应答语、知识库、表情、用户画像声纹、备忘闹钟、专业词汇、音乐源、OpenClaw 绑定
- **离线命令词**：算法资源打包平台生成 `cae_esr.bin` + `wrap.json` → `python3 ./tools/romfs.py pack` → 关闭 `CONFIG_OTA_DISABLE_WAKEWORD_UPDATE`，唤醒后超时内可识别本地命令
- **表情**：GIF 拆帧为 PNG → `romfs.py pack` → 烧到 0x00380000 → `user.disable_emoji_update 1`
- **TF 卡音乐**：FAT32 / `audio/` 目录 / 仅 mp3 / 文件名 ≤64 字 / 层数 ≤3
- **USB Host**：可接 CDC-ACM / CH34X 串口、HID，`usb_serial` shell 指令读写
- **对外协议**：设备侧按端云协议上报 MCP 声明（ESP32 也能接）

### 不能 / 限制
- 无端侧离线 TTS（FAQ 明确：暂不支持）
- 单麦，不支持双麦；官方口径：人声高于噪声 10dB、3m 内唤醒率 ~90%
- 只支持 2.4G WiFi
- 一个设备只能接一个智能体（不支持多 product_id）
- 默认应用每天赠送 30 万 token，用完需接自建应用（新账号赠 10 元）
- 芯片不支持取视频流（FAQ 说硬件性能限制，只能拍照）

---

## 5. 参考实现（官方 sample 分支，可直接抄）
- `sample/i2c_aht10` — AHT10 温湿度 → MCP `sensor_temperature_humidity`
- `sample/pwm_mg90s` — MG90S-360° 舵机（~53Hz，1.5ms 停，1.3/1.7ms 正反转）→ `mg90s_control`
- `sample/uart` — 串口收发回显 → `uart1_send`
- `sample/uart_i2c_pwm` — 多外设综合
- `sample/offline_cammand` — 离线命令词
仓库：`https://cloud.listenai.com/CSKG532016/arcs_mini_sample/-/tree/sample/xxx`
SDK 版本基线：**mini-v3.0.2-m3**（示例代码都基于此）

---

## 6. 文档矛盾点（需实板确认，勿猜）
`开发板简介` 同一页出现三个型号，`外设使用情况` 又是第四个说法：
- 概述：「采用聆思 **LS2684L0U** AI 芯片」（LS2684 = 16MB PSRAM + 有 NPU）
- 规格参数表：「主控芯片 芯片型号：**LS2662L0U**」
- PCBA 硬件资源表：「芯片型号：**LS2663L0U**」
- 外设使用情况：「**LS2663**，8M PSRAM：AP 3MB / CP 5MB」

**先确认方式**：`adb devices -l`（需 ≥3.0.3 固件，状态栏也显示设备类型）+ 看 PCBA 丝印 + `adb shell` 里读芯片 ID。
区别影响：有没有 NPU（64 GOPS）决定能不能跑端侧视觉算法（人脸/头肩/手势）。

---

## 7. 本机环境现状（2026-10-24 检查）
- git 2.53.0 ✅
- python 3.14.7 ✅
- adb ❌ 未安装（需 1.0.41+）
- `~/.listenai` ❌ 无工具链
- 本地无 arcs_mini 仓库
- cskburn desktop ❌ 未安装

## 8. 前置阻塞
1. **聆思账号 + GitLab 访问令牌**（无账号拉不到 SDK，这是硬阻塞）
2. LSPlatform 账号（接自建应用 / 传 OTA / 配唤醒词）
3. USB 数据线（必须是数据线，不是纯充电线）
