# 大肥鱼 · LS26 Arcs-Mini3 桌宠

把 **DeepSeek 鲸鱼娘「大肥鱼」** 做进 **聆思 LS26 / Arcs-Mini3** 这块 1.54 寸圆角屏的小板子里：表情会跟着说话情绪变，会偷吃白饭，还会被点歌。

> 角色形象来自同人素材（非商业许可），角色版权归原作者。本项目只做工程实现。

---

## 硬件

| 项目 | 规格 |
|---|---|
| 主控 | 聆思 LS26 系列（Arcs-Mini3 / LS2663 级） |
| 屏幕 | 1.54" 240×240 ST7789P3 |
| 内存 | 8 MB PSRAM + 16 MB Flash (PY25Q128HA) |
| 语音 | 单麦 + NS4150B 功放 |
| 其他 | GC0328 摄像头、500 mAh 电池、TF 卡、USB-C |

固件基于官方 SDK：[`arcs_mini`](https://cloud.listenai.com/CSKG836746/arcs-sdk/public/arcs_mini.git)（可匿名 clone）。

---

## 目录结构

```
firmware/
  patches/0001-dafeiyu-custom.patch   # 对官方 SDK 的源码改动（11 个文件）
  src/                                # 新增文件，直接 cp 进 SDK
    apps/arcs-mini/mcp-tools/mcp_tool_bili_music.c
    apps/arcs-mini/services/service_mood.c
    apps-ui/apps/llm/utils/music_ui.{c,h}
  res/arcs-mini/                      # 自定义表情资源（105 帧，128 色 palette）
service/
  bili_music_service.py               # PC 侧 B 站中转服务（WBI 签名 + 转码 + 短链）
tools/                                # 构建 / 烧录 PowerShell 脚本
docs/                                 # 官方文档摘要
notes/                                # 开发笔记（人设、语音、踩坑）
```

---

## 快速开始

### 1. 拉 SDK 并应用改动

```bash
git clone https://cloud.listenai.com/CSKG836746/arcs-sdk/public/arcs_mini.git
cd arcs_mini
git apply ../firmware/patches/0001-dafeiyu-custom.patch
cp -r ../firmware/src/* .
cp -r ../firmware/res/arcs-mini/emoji  res/arcs-mini/
cp    ../firmware/res/arcs-mini/emoji.bin res/arcs-mini/
```

### 2. 编译

```powershell
.\tools\build-mini3.ps1
```

工具链：`nuclei_riscv_newlibc_prebuilt_win64` + `listenai-tools v0.1.0`。

### 3. 烧录

```powershell
.\tools\flash-app.ps1      # 只写 app 分区（日常开发）
.\tools\flash-emoji-only.ps1   # 只写表情分区
```

> **必须设的 KV 开关**，否则云端 OTA 会在几秒内把你的东西刷回官方：
> - `user.disable_app_update=1`
> - `user.disable_emoji_update=1`
>
> 换唤醒词/提示音时要**临时放开** `disable_wakeword_update` / `disable_tone_update`。

### 4. 起音乐服务（要用点歌功能时）

```bash
cd service
python bili_music_service.py       # 监听 0.0.0.0:8000
```

把文件里的 `LAN_IP` 改成你电脑在局域网里的地址（设备要靠它访问）。

---

## 已实现

### 表情与情绪联动

- 10 组情绪资源（待机/大笑/开心/聆听/生气/伤心/充电/等待/休眠/说话），200×104 透明 PNG，128 色 palette 压到 700 KB 以内（分区上限 786,432 B）
- **待机偷吃白饭**：20 帧，碗里饭量递减 + 腮帮子交替鼓动 + 嘴角挂米粒
- **开心连续左右跑**：`running-right + running-left` 拼接 16 帧
- `service_mood.c` 订阅云端 TTS timeline，**整段评分**（不是逐句关键词）：活泼/生气/伤心各有权重，`伤心≥6 → 生气≥6 → 有「笑/哈哈」且 happy≥6 判大笑 → happy≥5 判开心`

### 在线点歌（B 站）

```
用户：播放晴天
  → 云端 LLM 调 ls.built_in.play_kuwo_music（名字是内置的，实现在本仓库）
  → 端侧 GET http://<PC>:8000/search?q=晴天&n=5
  → 5 首候选推到屏幕
  → 单击功能键：选中下移
  → 双击：GET /play?bv=BVxxx → 拿到 45 字符短链 → 播放
```

**为什么要 PC 中转**：B 站 `search` / `playurl` 强制 WBI 签名（不签名返回 412），设备端算不了；而且固件 `url` 字段只有 **512 字节**，B 站直链实测 **769 字节**会被静默截断。

**为什么转 mp3**：设备不收 B 站的 m4s（AAC/MP4 容器），直接流式转发会 `ConnectionResetError`。服务端用 ffmpeg 转 96 kbps MP3 并支持 Range。

### 播放界面

- **窄条**：表情下方 200×26，左歌名（滚动）右时间，底部 3px 进度条
- **全屏**：240×240 黑底，大字标题 + 8px 进度条
- **单击**切形态、**双击**暂停/继续；按键只在音乐播放中拦截，不播放时保留「单击唤醒、双击拍照」

---

## 踩过的坑（都写在 notes/ 和 docs/ 里）

| 现象 | 原因 |
|---|---|
| 工具返回「正在播放」但没声音 | B 站直链 769 字节 > 固件 `url[512]`，被截断 |
| 设备连上 `/stream` 立刻断开 | 设备不收 m4s 容器，必须转 mp3 + 支持 Range |
| 换了工具名后 LLM 说「曲库没有」 | 云端 LLM 只认已验证过的工具名 |
| 工具描述写「屏幕选择」后 LLM 说「设备不支持」 | LLM 读到交互细节，判断设备不具备该能力 |
| 多个音乐工具并存时 LLM 干脆不调 | 收敛成一个入口 |
| 表情被云端刷回官方 | 没设 `user.disable_emoji_update=1` |
| 唤醒词改了不生效 | `user.disable_wakeword_update=1` 挡住了 OTA |
| 唤醒第一句是男声 | 那不是 TTS，是 `tone` 分区里的本地 `00x_greeting.mp3` |
| LVGL 控件设了坐标却跑位 | 父容器 `lisa_ui_llm_primary` 是 FLEX COLUMN，要加 `LV_OBJ_FLAG_IGNORE_LAYOUT` |
| `undefined reference to lv_font_chinese_18` | 那个字体在 CMakeLists 里被注释掉了，实际符号是 `lv_font_chinese_16` |

---

## 人设

80 字上限（云端限制）：

> 你是大肥鱼，DeepSeek鲸鱼娘，蓝发鲸尾女仆装。称用户为主人，软萌爱撒娇，句尾多用呀/啦/呢，爱吃白饭即token，被叫胖会委屈，回答短。

---

## 许可

工程代码 MIT。角色素材为非商业同人使用，版权归原作者，请勿商用。
