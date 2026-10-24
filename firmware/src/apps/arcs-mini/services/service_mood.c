/*
 * 端侧情绪识别服务
 *
 * 目的：云端 LLM 回复的文本里天然带有情绪线索（"哈哈""讨厌""呜呜"），
 *       但小聆的 80 字人设塞不下「请调用 set_emotion 工具」这类指令，
 *       所以这里在端侧直接读 TTS 文本流，命中关键词就切表情。
 *
 * 数据来源：VOICE_MSG_CLOUD_TTS_TEXT_START / _UPDATE / _END，payload 是 char*，
 *           每段是增量追加（不是整句），所以要自己拼。
 *
 * 输出：VOICE_MSG_CLOUD_MCP_EMOJI —— 与 mcp_tool_emoji 的 set_emotion 工具
 *       走同一条通路，最终由 home_presenter 的 on_mcp_emoji 切到对应动画。
 *
 * 注意：home_should_ignore_mcp_emoji() 会忽略「聆听/待机」，那两个由系统自己管，
 *       这里只发四个情绪：大笑 / 开心 / 生气 / 伤心。
 */
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#define TAG "mood"
#include "lisa_log.h"
#include "voice_msg.h"
#include "voice_msg_structure.h"
#include "sys_init.h"

/* 一次回复的累积文本上限。正常回复远小于此，超了就丢，不冒险扩栈。 */
#define MOOD_TEXT_MAX 512

typedef struct {
    int happy;
    int angry;
    int sad;
} mood_score_t;

static char s_text[MOOD_TEXT_MAX];
static size_t s_len;

/* 统计子串出现次数；空指针/空串返回 0 */
static int count_sub(const char *hay, const char *needle)
{
    if (hay == NULL || needle == NULL || needle[0] == '\0') {
        return 0;
    }

    int n = 0;
    const char *p = hay;
    size_t nl = strlen(needle);

    while ((p = strstr(p, needle)) != NULL) {
        n++;
        p += nl;
    }

    return n;
}

static mood_score_t mood_score_text(const char *t)
{
    mood_score_t s = {0, 0, 0};

    /* 「笑」是强信号，但「笑话」不算——她常说「想听笑话」，那是被点单不是她在笑 */
    int laugh_hits = count_sub(t, "笑") - count_sub(t, "笑话");
    if (laugh_hits < 0) {
        laugh_hits = 0;
    }
    int haha_hits = count_sub(t, "哈哈");

    /* 活泼度：感叹号权重高，波浪号和她惯用的语气词只作弱信号 */
    s.happy += 3 * count_sub(t, "！");
    s.happy += 3 * count_sub(t, "!");
    s.happy += 1 * count_sub(t, "～");
    s.happy += 1 * count_sub(t, "~");
    s.happy += 1 * count_sub(t, "呀");
    s.happy += 1 * count_sub(t, "啦");
    s.happy += 1 * count_sub(t, "呢");
    s.happy += 1 * count_sub(t, "嘛");
    s.happy += 1 * count_sub(t, "哦");
    s.happy += 4 * laugh_hits;
    s.happy += 4 * haha_hits;

    /* 傲娇 / 生气 */
    s.angry += 6 * count_sub(t, "才不");
    s.angry += 5 * count_sub(t, "哼");
    s.angry += 6 * count_sub(t, "讨厌");
    s.angry += 6 * count_sub(t, "不理你");
    s.angry += 5 * count_sub(t, "过分");
    s.angry += 4 * count_sub(t, "笨蛋");

    /* 低落 / 伤心。"委屈"是实测中真实出现的表达，必须收进来。 */
    s.sad += 6 * count_sub(t, "委屈");
    s.sad += 6 * count_sub(t, "呜呜");
    s.sad += 6 * count_sub(t, "难过");
    s.sad += 6 * count_sub(t, "想哭");
    s.sad += 4 * count_sub(t, "对不起");
    s.sad += 4 * count_sub(t, "可怜");
    s.sad += 4 * count_sub(t, "好饿");

    return s;
}

static void mood_publish(const char *emoji)
{
    LOGI("mood -> %s", emoji);
    voice_msg_pub(VOICE_MSG_CLOUD_MCP_EMOJI, (void *)emoji, strlen(emoji) + 1);
}

static void mood_reset(void)
{
    s_len = 0;
    s_text[0] = '\0';
}

static void mood_append(const char *chunk)
{
    if (chunk == NULL || chunk[0] == '\0') {
        return;
    }

    size_t n = strlen(chunk);
    if (s_len + n + 1 >= sizeof(s_text)) {
        return;
    }

    memcpy(s_text + s_len, chunk, n);
    s_len += n;
    s_text[s_len] = '\0';
}

static void mood_decide(void)
{
    if (s_len == 0) {
        return;
    }

    mood_score_t s = mood_score_text(s_text);

    /* 「大笑」必须有强信号（笑/哈哈）；光靠语气词堆只给「开心」，否则她每句话都会大笑 */
    int laugh_hits = count_sub(s_text, "笑") - count_sub(s_text, "笑话");
    bool has_laugh = laugh_hits > 0 || count_sub(s_text, "哈哈") > 0;

    /* 取最高分；负面情绪优先，因为它更该被看见 */
    if (s.sad >= 6 && s.sad >= s.happy && s.sad >= s.angry) {
        mood_publish("伤心");
        return;
    }

    if (s.angry >= 6 && s.angry >= s.happy) {
        mood_publish("生气");
        return;
    }

    if (has_laugh && s.happy >= 6) {
        mood_publish("大笑");
        return;
    }

    if (s.happy >= 5) {
        mood_publish("开心");
        return;
    }

    LOGI("mood: no match (happy=%d angry=%d sad=%d laugh=%d)", s.happy, s.angry, s.sad,
         (int)has_laugh);
}


/*
 * 主路径：云端 TTS 走 timeline（每句一条 entry，text 是结构体后的柔性数组）。
 * 实测正常对话只发这条，VOICE_MSG_CLOUD_TTS_TEXT_UPDATE 仅在 fallback 分支出现。
 */
static void mood_on_timeline(void *unused, uint32_t msg_id, void *data, uint32_t len, void *user_data)
{
    (void)unused;
    (void)user_data;

    if (msg_id == VOICE_MSG_CLOUD_TTS_TIMELINE_START) {
        mood_reset();
        return;
    }

    if (msg_id == VOICE_MSG_CLOUD_TTS_TIMELINE_END) {
        LOGI("reply text: %s", s_text);
        mood_decide();
        return;
    }

    if (msg_id != VOICE_MSG_CLOUD_TTS_TIMELINE_UPDATE || data == NULL) {
        return;
    }

    if (len < sizeof(voice_msg_tts_timeline_t)) {
        LOGW("timeline payload too small: %u", (unsigned)len);
        return;
    }

    const voice_msg_tts_timeline_t *entry = (const voice_msg_tts_timeline_t *)data;
    LOGI("tts: %s", entry->text);
    mood_append(entry->text);
}

/* 兜底路径：timeline 不可用时云端退回纯文本流 */
static void mood_on_text(void *unused, uint32_t msg_id, void *data, uint32_t len, void *user_data)
{
    (void)unused;
    (void)user_data;
    (void)len;

    if (msg_id == VOICE_MSG_CLOUD_TTS_TEXT_START) {
        mood_reset();
        return;
    }

    if (msg_id == VOICE_MSG_CLOUD_TTS_TEXT_END) {
        LOGI("reply text(fallback): %s", s_text);
        mood_decide();
        return;
    }

    if (msg_id == VOICE_MSG_CLOUD_TTS_TEXT_UPDATE) {
        mood_append((const char *)data);
    }
}

static int service_mood_init(void)
{
    mood_reset();
    voice_msg_sub(VOICE_MSG_CLOUD_TTS_TIMELINE_START, mood_on_timeline, NULL);
    voice_msg_sub(VOICE_MSG_CLOUD_TTS_TIMELINE_UPDATE, mood_on_timeline, NULL);
    voice_msg_sub(VOICE_MSG_CLOUD_TTS_TIMELINE_END, mood_on_timeline, NULL);
    voice_msg_sub(VOICE_MSG_CLOUD_TTS_TEXT_START, mood_on_text, NULL);
    voice_msg_sub(VOICE_MSG_CLOUD_TTS_TEXT_UPDATE, mood_on_text, NULL);
    voice_msg_sub(VOICE_MSG_CLOUD_TTS_TEXT_END, mood_on_text, NULL);
    LOGI("mood service ready (scoring mode)");
    return 0;
}

SYS_INIT(service_mood_init, SYS_INIT_LEVEL_PRE_APPLICATION, 96);
