# Deepseek Desktop Mini Maid

> 内部代号「大肥鱼」——把 **DeepSeek 鲸鱼娘** 做进 **聆思 LS26 / Arcs-Mini3** 这块 1.54 寸圆角屏小板子里的桌面陪伴体。

她会跟着说话的情绪换表情，待机时偷吃白饭，能被点歌——说一句「播放司凤音乐」，屏幕上弹出 5 首候选，单击切换、双击播放，全屏模式还有专辑封面和进度条。

> 角色形象来自同人素材（非商业许可），角色版权归原作者。本项目只做工程实现，请勿商用。

---

## 目录

- [硬件](#硬件)
- [功能特性](#功能特性)
- [仓库结构](#仓库结构)
- [如何使用](#如何使用)
  - [1. 准备工具链](#1-准备工具链)
  - [2. 拉取 SDK 并应用改动](#2-拉取-sdk-并应用改动)
  - [3. 编译](#3-编译)
  - [4. 烧录](#4-烧录)
  - [5. 首次配网](#5-首次配网)
  - [6. 启动音乐服务](#6-启动音乐服务)
- [音乐播放的实现](#音乐播放的实现)
- [踩过的坑](#踩过的坑)
- [人设配置](#人设配置)
- [致谢](#致谢)
- [许可](#许可)

---

## 硬件

| 项目 | 规格 |
|---|---|
| 主控 | 聆思 LS26 系列（Arcs-Mini3 / LS2663 级，双核） |
| 屏幕 | 1.54" 240×240 ST7789P3 |
| 内存 | 8 MB PSRAM + 16 MB Flash (PY25Q128HA) |
| 语音 | 单麦 + NS4150B 功放 |
| 其他 | GC0328 摄像头、500 mAh 电池、TF 卡（SDIO）、USB-C 双角色 |

固件基于官方 SDK：[arcs_mini](https://cloud.listenai.com/CSKG836746/arcs-sdk/public/arcs_mini.git)（可匿名 clone），官方文档在 [docs2.listenai.com](https://docs2.listenai.com/)。

---

## 功能特性

### 表情与情绪联动

- 10 组情绪资源（待机/大笑/开心/聆听/生气/伤心/充电/等待/休眠/说话），200×104 透明 PNG
- 128 色 palette 压到 678 KB（分区上限 786,432 B）
- **待机偷吃白饭**：20 帧，碗里饭量递减 + 腮帮子交替鼓动 + 嘴角挂米粒
- **开心连续左右跑**：`running-right + running-left` 拼接 16 帧
- `service_mood.c` 订阅云端 TTS timeline 做**整段评分**（不是逐句关键词匹配）：

  ```
  伤心≥6 → 生气≥6 → 有「笑/哈哈」且 happy≥6 判大笑 → happy≥5 判开心
  ```

### 在线点歌（B 站）

```
你说「播放司凤音乐」
  ↓ 端侧订阅 ASR 识别结果，匹配「播放/来首/听」提取歌名
  ↓ 掐掉云端这轮会话（否则她会按自己的判断说「无法播放」）
  ↓ GET http://<你的电脑>:8000/search?q=司凤音乐&n=5
  ↓ 5 首候选推到屏幕
  ↓ 单击功能键：选中下移       双击：点播并播放
```

### 播放界面

| 形态 | 布局 |
|---|---|
| 窄条 | 表情下方 200×26，进度条 + 时间（歌名由表情界面的标题显示，不重复） |
| 全屏 | 240×240 黑底，64×64 专辑封面 + 大字标题 + 8px 进度条 + 时间 |

**单击**切换两种形态，**双击**暂停/继续。按键只在音乐播放中拦截，不播放时保留原有的「单击唤醒、双击拍照」。

---

## 仓库结构

```
firmware/
  patches/0001-dafeiyu-custom.patch    # 对官方 SDK 的源码改动
  src/                                 # 新增文件，直接 cp 进 SDK
    apps/arcs-mini/mcp-tools/mcp_tool_bili_music.c   # 点歌：ASR 拦截 + 搜索 + 封面
    apps/arcs-mini/services/service_mood.c           # 端侧情绪评分
    apps-ui/apps/llm/utils/music_ui.{c,h}            # 播放界面（窄条/全屏/列表）
  res/arcs-mini/emoji/                 # 10 组表情的 PNG 帧 + emoji.json
  res/arcs-mini/emoji.bin              # 打包好的 romfs 镜像（679 KB）
service/
  bili_music_service.py                # PC 侧 B 站中转服务
tools/
  build-mini3.ps1                      # 编译
  flash-app.ps1                        # 只烧 app 分区
  flash-emoji-only.ps1                 # 只烧表情分区
  emoji_gen/                           # 表情合成管线（Pillow）
docs/                                  # 官方文档摘要
notes/                                 # 开发笔记（人设、语音、踩坑）
```

`.gitignore` 排除了 809 MB 的 SDK 本体和 `work/` 工作目录——SDK 请按下面的命令自己 clone。

---

## 如何使用

### 1. 准备工具链

全部在 Windows 上验证过（Windows 11 + git-bash）。

#### 硬件与账号

| 依赖 | 说明 |
|---|---|
| Arcs-Mini3 开发板 | Chip ID `6d7b101a1f1dcba5`（你的会不同，烧录脚本里要改） |
| USB-C 数据线 | 必须能传数据，不能是充电线 |
| 小聆AI 账号 | 配网、人设、声音复刻都在小程序里配置 |

#### 软件依赖

| 依赖 | 版本 / 来源 | 用途 |
|---|---|---|
| [Android platform-tools](https://developer.android.com/tools/releases/platform-tools) | ≥ 1.0.41，提供 `adb` | 烧录、抓日志 |
| [Nuclei GCC](https://doc.nucleisys.com/nuclei_tools/index.html) | `nuclei_riscv_newlibc_prebuilt_win64_2025.10_slim` | RISC-V 交叉编译 |
| [listenai-tools](https://cloud.listenai.com/) | v0.1.0 | 聆思打包/烧录工具 |
| [Git](https://git-scm.com/download/win) | 任意 | 拉 SDK、管版本 |
| Python | 3.10+（开发用的是 3.14） | 音乐服务、表情生成 |
| Python 包 | `Pillow` | 表情合成、封面转 ARGB8888 |
| [ffmpeg](https://ffmpeg.org/download.html#build-windows) | 任意（开发用 Gyan 构建，`winget install Gyan.FFmpeg`） | m4s → MP3 转码 |

#### 目录布局与 PATH

开发机的实际布局（路径可改，但 `tools/*.ps1` 里的引用要同步）：

```
F:\Output\Tools\
  platform-tools\            # adb.exe
  listenai\
    gcc\                     # nuclei_riscv_newlibc_prebuilt_win64_2025.10_slim
    ...                      # listenai-tools v0.1.0
F:\Output\LS26-ArcsMini3\    # 本仓库
  arcs_mini\                 # clone 下来的官方 SDK
```

把 `platform-tools` 和 `listenai` 加进 PATH：

```powershell
$env:PATH = "F:\Output\Tools\platform-tools;" + $env:PATH
$env:PATH = "F:\Output\Tools\listenai;"     + $env:PATH
```

> `tools/build-mini3.ps1` 里已写好工具链路径，换位置只需改那一处。

#### Python 依赖安装

```bash
pip install Pillow
```

音乐服务只用标准库 + Pillow；`ffmpeg` 需要在 PATH 里能直接调用（`ffmpeg -version` 能跑通即可）。

### 2. 拉取 SDK 并应用改动

```bash
git clone https://cloud.listenai.com/CSKG836746/arcs-sdk/public/arcs_mini.git
cd arcs_mini

git apply ../firmware/patches/0001-dafeiyu-custom.patch
cp -r ../firmware/src/* .
cp -r ../firmware/res/arcs-mini/emoji  res/arcs-mini/
cp    ../firmware/res/arcs-mini/emoji.bin res/arcs-mini/
```

> patch 只覆盖 11 个源码文件；表情资源是完整目录，直接覆盖即可。

### 3. 编译

```powershell
.\tools\build-mini3.ps1
```

冷编译约 3 分钟。产物在 `build-arcs-mini3/`：

| 文件 | 用途 |
|---|---|
| `arcs-mini.bin` | app 分区固件（~3.3 MB） |
| `arcs-mini.lpk` | 整包烧录 |
| `arcs-mini.combined.hex` | J-Link/SWD 烧录 |

### 4. 烧录

日常开发只烧 app 分区：

```powershell
.\tools\flash-app.ps1
```

只换表情（不动固件）：

```powershell
.\tools\flash-emoji-only.ps1
```

> **recovery 模式下退出要用 `adb -s BOOT-<chipid> shell reboot`**，直接 `adb reboot` 会报 `error: closed`。

#### OTA 保护开关

云端 OTA 会在几秒内把自定义内容刷回官方。本项目的固件**启动时会自动补设**这两个开关，正常情况下你不用手动操作：

- `user.disable_app_update=1`
- `user.disable_emoji_update=1`

需要换唤醒词/提示音时，临时删掉对应的 `disable_wakeword_update` / `disable_tone_update`，OTA 完成后再补回来。

### 5. 首次配网

用小聆AI 小程序走 BLE 配网，连你的 2.4G WiFi。配网后设备的 WiFi 凭证存在 KV 里。

> **KV 丢失的征兆**：日志出现 `lisa_kv_get_small_data(key: user.brightness) fail`。此时设备不知道要连哪个热点，会反复「连不上云端」，需要重新配网。

### 6. 启动音乐服务

点歌功能需要一台同局域网的电脑：

```bash
cd service
python bili_music_service.py        # 监听 0.0.0.0:8000
```

服务启动时会**自动探测本机局域网 IP**（走默认路由），探测失败才用代码里的兜底值。

如果你改了固件里的 `BILI_SERVICE_HOST`（`apps/arcs-mini/mcp-tools/mcp_tool_bili_music.c`），要和电脑实际 IP 一致；更省事的做法是在路由器上给电脑做 DHCP 保留。

---

## 音乐播放的实现

当前实现需要电脑常开（PC 中转），这是**有意的取舍**：

| 环节 | 为什么放在 PC 上 |
|---|---|
| WBI 签名 | B 站 `search` / `playurl` 强制签名（不签名返回 412），要 64 字节混淆表 + MD5 + 动态 key |
| URL 长度 | B 站直链实测 769 字节，固件 `url` 字段只有 512，会被静默截断 |
| 音频格式 | B 站只有 m4s（AAC/MP4 容器），设备播放器会直接断开连接 |

服务端职责：**WBI 签名 → 搜索 → ffmpeg 转 96k MP3 → 45 字符短链 → 封面转 ARGB8888**，全部带缓存，同一首歌二次点播秒开。

```
service 接口
  GET /search?q=<关键词>&n=5      → 候选列表（含 bvid、封面路径）
  GET /play?q=<关键词>            → 直接播第一首
  GET /play?bv=<bvid>             → 列表里选定那首
  GET /stream/<token>             → MP3 音频流（支持 Range）
  GET /cover/<token>              → 64×64 ARGB8888 封面（LVGL 内存图片源）
```

**已知限制**：搜索会过滤 10 分钟以上的条目（合集/直播回放转码要 40 秒以上）；「稻香」这类词单独搜可能被 B 站风控，加歌手名更稳。

---

## 踩过的坑

按类别分组，都写进了 [notes/](notes/) 和技能库。

### 播放链路

| 现象 | 真正原因 |
|---|---|
| 工具返回「正在播放」但没声音 | B 站直链 769 字节 > 固件 `url[512]`，被静默截断 |
| 设备连上 `/stream` 立刻断开 | 设备不收 m4s 容器，必须转 MP3 + 支持 Range |
| 单词能播、带空格的一定失败 | WBI 签名把空格编成 `+`，B 站要 `%20`；`urlencode` 默认给 `+` |
| 重启后突然连不上服务 | 电脑 DHCP 换了 IP，固件里写死了旧地址 |

### 云端 LLM 行为（最耗时的一类）

| 现象 | 真正原因 |
|---|---|
| 换工具名后她说「曲库没有」 | 云端 LLM 只认已验证过的工具名，新名字直接当不存在 |
| 工具描述写「屏幕选择」后她说「设备不支持」 | LLM 读到交互细节，判断设备不具备该能力 |
| 多个音乐工具并存时她干脆不调 | 收敛成一个入口 |
| 音乐在放但她同时说「无法播放」 | 端侧接管了点歌，但云端那轮会话没取消——要 pub `VOICE_MSG_CLOUD_SESSION_INTERRUPT` |
| 同一句话这次调下次不调 | LLM 工具选择本身不稳定，**最终改为端侧拦 ASR，完全不依赖它** |

### 界面与资源

| 现象 | 真正原因 |
|---|---|
| LVGL 控件设了坐标却跑位 | 父容器 `lisa_ui_llm_primary` 是 FLEX COLUMN，要加 `LV_OBJ_FLAG_IGNORE_LAYOUT` |
| `undefined reference to lv_font_chinese_18` | 那个字体在 CMakeLists 里被注释掉了，实际符号是 `lv_font_chinese_16` |
| 封面位置空白/花屏 | `LV_COLOR_DEPTH` 是 **32** 不是 16，`LV_IMG_CF_TRUE_COLOR` 要 4 字节/像素（ARGB8888，小端 B,G,R,A） |
| 封面消息发不出去 | ebus 的 `pub_async` 用 `platform_malloc` 拷贝 payload，SRAM 已用 99%，8KB 必然 ENOMEM；改传 PSRAM 指针 |
| 界面整体卡死 | 在 ebus 回调里同步做 HTTP（1~8 秒）堵死事件总线，必须移到 `async_task` 独立线程 |
| 待机表情变回官方 9 帧 | `emoji.json` 的 `default_emoji` 指向官方的 `neutral`，但分区里只有中文目录，加载失败回退到 app 内置官方表情 |
| 表情被云端刷回官方 | `user.disable_emoji_update=1` 没设（现已改为固件启动时自动补设） |
| 唤醒词改了不生效 | `user.disable_wakeword_update=1` 挡住了 OTA |
| 唤醒第一句是男声 | 那不是 TTS，是 `tone` 分区里的本地 `00x_greeting.mp3` |
| C 源码写中文标点编译失败 | `'。'` 是 multi-character character constant，`-Werror` 直接报错；要按 UTF-8 字节比对 |
| `'\0'` 写进 C 文件变成真 NUL | Python heredoc 里 `'\0'` 会被解释成空字节，用 `== 0` 代替 |

---

## 人设配置

云端限制 80 字：

> 你是大肥鱼，DeepSeek鲸鱼娘，蓝发鲸尾女仆装。称用户为主人，软萌爱撒娇，句尾多用呀/啦/呢，爱吃白饭即token，被叫胖会委屈，回答短。

唤醒词「大肥鱼出列」。声音复刻走云端 `prompt_tone.bin` 下发，对话 TTS 和唤醒应答音都是女声。

---

## 致谢

### 角色与素材

- [dsh-whale-pet](https://github.com/aceice01/dsh-whale-pet) — DeepSeek 鲸鱼娘桌宠，本项目的表情动画素材来源
- [codex-pet-DeepSeek-girl](https://github.com/xpy12367/codex-pet-DeepSeek-girl) — 同批鲸鱼娘序列帧，补充了 review / running-left / running-right 等动作
- [DeskPet](https://github.com/2048Nemo/DeskPet) — macOS 桌宠，序列帧动画与状态机设计的参考

### 音乐链路

- [MusicFree](https://github.com/maotoumao/MusicFree) — 插件化开源音乐播放器，本项目采用「B 站作为音源」的思路来源于此
- B 站开放平台的 WBI 签名机制（`MIXIN_KEY_ENC_TAB` 混淆表 + MD5）

### 平台与工具

- 聆思科技 [arcs_mini SDK](https://cloud.listenai.com/CSKG836746/arcs-sdk/public/arcs_mini.git) 与[官方文档](https://docs2.listenai.com/)
- [LVGL](https://github.com/lvgl/lvgl) 嵌入式图形库
- [Pillow](https://github.com/python-pillow/Pillow)（表情合成、封面转格式）、[ffmpeg](https://ffmpeg.org/)（音频转码）

---

## 许可

工程代码 MIT。角色素材为非商业同人使用，版权归原作者，请勿商用。
