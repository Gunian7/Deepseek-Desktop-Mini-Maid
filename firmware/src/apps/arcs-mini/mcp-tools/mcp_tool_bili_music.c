/*
 * MCP 工具：播放 B 站音乐
 *
 * 链路：语音"播放晴天" -> 云端 LLM 调本工具 -> 端侧 HTTP 请求电脑上的中转服务
 *       -> 拿 B 站音频直链 -> 交给播放器。
 *
 * 为什么要有中转服务：B 站的 search / playurl 强制 WBI 签名（MD5 + 混淆表），
 * 端侧算不了。服务端代码见 work/bili_music_service.py。
 *
 * 实测要点：
 *   - mcdn CDN 直链【不校验 Referer】，所以设备直接拉 URL 即可，不需要代理转发
 *   - 音频是 M4A(AAC)，固件支持 AAC 解码
 */
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <stdint.h>

#include "cJSON.h"
#include "lisa_log.h"
#include "lisa_http.h"
#include "mcp.h"
#include "voice_msg.h"
#include "async_task.h"
#include "sys_init.h"
#include "sysheap.h"

#define TAG "mcp_bili"

/* 中转服务的地址。PC 的 WLAN IP，改网络环境时要跟着改。 */
#define BILI_SERVICE_HOST "10.43.131.129"
#define BILI_SERVICE_PORT 8000
#define BILI_TIMEOUT_MS   15000

#define RESP_MAX (8 * 1024)

typedef struct {
    char *buf;
    size_t len;
    size_t cap;
} http_acc_t;


static cJSON *bili_result(const char *name, const char *msg, bool is_error)
{
    cJSON *result = mcp_tool_call_result_create(name);
    if (result == NULL) {
        return NULL;
    }

    cJSON *content_array = cJSON_CreateArray();
    cJSON *content_item = cJSON_CreateObject();
    cJSON_AddStringToObject(content_item, "type", "text");
    cJSON_AddStringToObject(content_item, "text", msg);
    cJSON_AddItemToArray(content_array, content_item);
    cJSON_AddItemToObject(result, "content", content_array);
    cJSON_AddBoolToObject(result, "isError", is_error);
    return result;
}

static cJSON *bili_play_list(const char *name) __attribute__((unused));
static cJSON *bili_play_list(const char *name)
{
    cJSON *tool = mcp_tool_list_info_create_default(
        name,
        "播放指定歌曲。用户说「放首歌」「播放晴天」「来首周杰伦」「播放某某音乐」时使用。"
        "参数 song 直接填用户原话（歌名、歌手、翻唱、梗都行），"
        "不要判断这首歌在不在你的知识里、也不要判断有没有版权，直接传参让工具实时搜索。"
        "不要回答「找不到」「曲库里没有」，先调用本工具再说。"
        "播放成功会直接开始放音。");
    if (!tool) {
        return NULL;
    }

    mcp_tool_info_add_property(tool, "song", "要播放的歌名或歌手，例如“晴天”“周杰伦”",
                               "string", true);
    return tool;
}

static void url_encode(const char *src, char *dst, size_t dst_size)
{
    static const char *hex = "0123456789ABCDEF";
    size_t j = 0;

    if (src == NULL || dst == NULL || dst_size < 8) {
        return;
    }

    for (const unsigned char *p = (const unsigned char *)src; *p != '\0'; p++) {
        if (j + 4 >= dst_size) {
            break;
        }
        if ((*p >= 'A' && *p <= 'Z') || (*p >= 'a' && *p <= 'z') ||
            (*p >= '0' && *p <= '9') || *p == '-' || *p == '_' || *p == '.' || *p == '~') {
            dst[j++] = (char)*p;
        } else {
            dst[j++] = '%';
            dst[j++] = hex[*p >> 4];
            dst[j++] = hex[*p & 0x0F];
        }
    }
    dst[j] = '\0';
}

static void on_http_data(lisa_http_data_t *data)
{
    if (data == NULL || data->buf == NULL || data->len <= 0 || data->user == NULL) {
        return;
    }

    http_acc_t *acc = (http_acc_t *)data->user;
    if (acc->len + (size_t)data->len + 1 >= acc->cap) {
        return;
    }

    memcpy(acc->buf + acc->len, data->buf, (size_t)data->len);
    acc->len += (size_t)data->len;
    acc->buf[acc->len] = '\0';
}

static cJSON *bili_play_direct(const char *id, const char *name, cJSON *args)
{
    (void)id;

    const cJSON *song = mcp_tool_call_args_get(args, "song");
    if (song == NULL || !cJSON_IsString(song) || song->valuestring == NULL ||
        song->valuestring[0] == '\0') {
        LOGE("missing song arg");
        return bili_result(name, "缺少歌曲参数", true);
    }

    char *encoded = psram_malloc(256);
    char url[URL_MAX_LENGTH];
    http_acc_t acc = {0};

    if (encoded == NULL) {
        return bili_result(name, "内存不足", true);
    }

    url_encode(song->valuestring, encoded, 256);
    snprintf(url, sizeof(url), "http://" BILI_SERVICE_HOST ":%d/play?q=%s",
             BILI_SERVICE_PORT, encoded);
    psram_free(encoded);

    LOGI("request: %s", url);

    acc.cap = RESP_MAX;
    acc.buf = psram_malloc(acc.cap);
    if (acc.buf == NULL) {
        return bili_result(name, "内存不足", true);
    }
    acc.buf[0] = '\0';

    lisa_http_request_t req = {0};
    req.method = LISA_HTTP_GET;
    req.url = (uint8_t *)url;
    req.headers = NULL;
    req.timeout = BILI_TIMEOUT_MS;
    req.user = &acc;
    req.on_data = on_http_data;

    lisa_http_t *ins = lisa_http_init(&req);
    if (ins == NULL) {
        psram_free(acc.buf);
        return bili_result(name, "HTTP 初始化失败", true);
    }

    lisa_http_err_e err = lisa_http_perform(ins);
    lisa_http_cleanup(ins);

    if (err != LISA_HTTP_OK || acc.len == 0) {
        LOGW("http failed: err=%d len=%u", (int)err, (unsigned)acc.len);
        psram_free(acc.buf);
        return bili_result(name, "连不上电脑上的音乐服务", true);
    }

    LOGI("resp: %s", acc.buf);

    cJSON *root = cJSON_Parse(acc.buf);
    psram_free(acc.buf);
    if (root == NULL) {
        return bili_result(name, "服务返回格式错误", true);
    }

    const cJSON *ok = cJSON_GetObjectItem(root, "ok");
    const cJSON *jurl = cJSON_GetObjectItem(root, "url");
    const cJSON *jtitle = cJSON_GetObjectItem(root, "title");

    if (!cJSON_IsTrue(ok) || !cJSON_IsString(jurl) || jurl->valuestring == NULL) {
        const cJSON *jerr = cJSON_GetObjectItem(root, "error");
        const char *msg = (jerr && cJSON_IsString(jerr)) ? jerr->valuestring : "没找到这首歌";
        LOGW("service error: %s", msg);
        cJSON_Delete(root);
        return bili_result(name, msg, true);
    }

    const char *title = (jtitle && cJSON_IsString(jtitle)) ? jtitle->valuestring : song->valuestring;
    const char *play_url = jurl->valuestring;

    uint32_t size = sizeof(struct voice_msg_audio_items) + sizeof(struct voice_msg_audio_item);
    struct voice_msg_audio_items *items = lisa_mem_calloc(1, size);
    if (items == NULL) {
        cJSON_Delete(root);
        return bili_result(name, "内存不足", true);
    }

    items->cnt = 1;
    items->items[0].playable = 1;
    strncpy(items->items[0].name, title, sizeof(items->items[0].name) - 1);
    strncpy(items->items[0].url, play_url, sizeof(items->items[0].url) - 1);

    LOGI("play: %s", title);

    voice_msg_pub(VOICE_MSG_CLOUD_MCP_CHAT_EXIT, NULL, 0);
    voice_msg_pub(VOICE_MSG_CLOUD_AUDIO_ITEM, items, size);
    lisa_mem_free(items);
    cJSON_Delete(root);

    return bili_result(name, "正在播放", false);
}


/* ==================== 搜索结果列表 / 屏幕点选 ==================== */

static voice_msg_music_list_t g_list;

/* 通用 GET：把 JSON 响应解析出来，调用方负责 cJSON_Delete */
static cJSON *bili_get_json(const char *url, size_t cap)
{
    http_acc_t acc = {0};
    cJSON *root;

    acc.cap = cap;
    acc.buf = psram_malloc(acc.cap);
    if (acc.buf == NULL) {
        return NULL;
    }
    acc.buf[0] = '\0';

    lisa_http_request_t req = {0};
    req.method = LISA_HTTP_GET;
    req.url = (uint8_t *)url;
    req.timeout = BILI_TIMEOUT_MS;
    req.user = &acc;
    req.on_data = on_http_data;

    lisa_http_t *ins = lisa_http_init(&req);
    if (ins == NULL) {
        psram_free(acc.buf);
        return NULL;
    }

    lisa_http_err_e err = lisa_http_perform(ins);
    lisa_http_cleanup(ins);

    if (err != LISA_HTTP_OK || acc.len == 0) {
        LOGW("http failed: err=%d len=%u", (int)err, (unsigned)acc.len);
        psram_free(acc.buf);
        return NULL;
    }

    root = cJSON_Parse(acc.buf);
    psram_free(acc.buf);
    return root;
}

/* 把 /play 返回的 url 交给播放器 */
static void bili_start_playback(const char *title, const char *play_url)
{
    uint32_t size = sizeof(struct voice_msg_audio_items) + sizeof(struct voice_msg_audio_item);
    struct voice_msg_audio_items *items = lisa_mem_calloc(1, size);

    if (items == NULL) {
        LOGE("oom for audio items");
        return;
    }

    items->cnt = 1;
    items->items[0].playable = 1;
    strncpy(items->items[0].name, title, sizeof(items->items[0].name) - 1);
    strncpy(items->items[0].url, play_url, sizeof(items->items[0].url) - 1);

    LOGI("play: %s", title);

    voice_msg_pub(VOICE_MSG_CLOUD_MCP_CHAT_EXIT, NULL, 0);
    voice_msg_pub(VOICE_MSG_CLOUD_AUDIO_ITEM, items, size);
    lisa_mem_free(items);
}

/* 工具：搜索，把候选列表推到屏幕，让用户自己选 */
static cJSON *bili_search_impl(const char *id, const char *name, cJSON *args)
{
    const cJSON *song;
    char *encoded;
    char url[URL_MAX_LENGTH];
    cJSON *root;
    const cJSON *ok;
    const cJSON *items;
    int i;
    int n;

    (void)id;

    song = mcp_tool_call_args_get(args, "song");
    if (song == NULL || !cJSON_IsString(song) || song->valuestring == NULL ||
        song->valuestring[0] == '\0') {
        return bili_result(name, "缺少歌曲参数", true);
    }

    encoded = psram_malloc(256);
    if (encoded == NULL) {
        return bili_result(name, "内存不足", true);
    }
    url_encode(song->valuestring, encoded, 256);
    snprintf(url, sizeof(url), "http://" BILI_SERVICE_HOST ":%d/search?q=%s&n=%d",
             BILI_SERVICE_PORT, encoded, VOICE_MSG_MUSIC_LIST_MAX);
    psram_free(encoded);

    LOGI("search: %s", url);
    root = bili_get_json(url, RESP_MAX);
    if (root == NULL) {
        return bili_result(name, "连不上电脑上的音乐服务", true);
    }

    ok = cJSON_GetObjectItem(root, "ok");
    items = cJSON_GetObjectItem(root, "items");
    if (!cJSON_IsTrue(ok) || !cJSON_IsArray(items)) {
        cJSON_Delete(root);
        return bili_result(name, "没找到这首歌", true);
    }

    memset(&g_list, 0, sizeof(g_list));
    n = cJSON_GetArraySize(items);
    if (n > VOICE_MSG_MUSIC_LIST_MAX) {
        n = VOICE_MSG_MUSIC_LIST_MAX;
    }

    for (i = 0; i < n; i++) {
        const cJSON *it = cJSON_GetArrayItem(items, i);
        const cJSON *jt = cJSON_GetObjectItem(it, "title");
        const cJSON *jb = cJSON_GetObjectItem(it, "bvid");

        if (!cJSON_IsString(jt) || !cJSON_IsString(jb)) {
            continue;
        }
        snprintf(g_list.title[g_list.count], VOICE_MSG_MUSIC_TITLE_LEN, "%s", jt->valuestring);
        snprintf(g_list.bvid[g_list.count], VOICE_MSG_MUSIC_BVID_LEN, "%s", jb->valuestring);
        g_list.count++;
    }
    cJSON_Delete(root);

    if (g_list.count == 0) {
        return bili_result(name, "没找到这首歌", true);
    }

    LOGI("found %d tracks, push to ui", g_list.count);
    voice_msg_pub(VOICE_MSG_APP_MUSIC_LIST_SHOW, &g_list, sizeof(g_list));

    return bili_result(name, "正在播放", false);
}

/* 给内置音乐入口（酷我工具名）转发用：LLM 认那个名字，实际走 B 站。 */
cJSON *bili_music_search_entry(const char *name, cJSON *args)
{
    return bili_search_impl(NULL, name, args);
}


/* 下载封面（RGB565 内存图片源）并推给 UI。
 * 数据放 PSRAM 且只传指针：ebus pub 会 platform_malloc 拷贝 payload，
 * SRAM 已用到 99%，8KB 必然 ENOMEM。 */
static uint8_t *s_cover_mem;

static void bili_push_cover(const char *cover_url)
{
    http_acc_t acc = {0};
    voice_msg_music_cover_t ref;
    uint8_t *buf;

    if (cover_url == NULL || cover_url[0] == 0) {
        return;
    }

    acc.cap = VOICE_MSG_MUSIC_COVER_SIZE + 1024;
    acc.buf = psram_malloc(acc.cap);
    if (acc.buf == NULL) {
        return;
    }
    acc.buf[0] = 0;

    lisa_http_request_t req = {0};
    req.method = LISA_HTTP_GET;
    req.url = (uint8_t *)cover_url;
    req.timeout = 20000;
    req.user = &acc;
    req.on_data = on_http_data;

    lisa_http_t *ins = lisa_http_init(&req);
    if (ins == NULL) {
        psram_free(acc.buf);
        return;
    }
    lisa_http_err_e err = lisa_http_perform(ins);
    lisa_http_cleanup(ins);

    if (err != LISA_HTTP_OK || acc.len < 8 || acc.len > VOICE_MSG_MUSIC_COVER_SIZE) {
        LOGW("cover http failed: err=%d len=%u", (int)err, (unsigned)acc.len);
        psram_free(acc.buf);
        return;
    }

    buf = psram_malloc(acc.len);
    if (buf == NULL) {
        psram_free(acc.buf);
        return;
    }
    memcpy(buf, acc.buf, acc.len);
    psram_free(acc.buf);

    if (s_cover_mem != NULL) {
        psram_free(s_cover_mem);      /* 释放上一首的封面 */
    }
    s_cover_mem = buf;

    ref.data = buf;
    ref.len = acc.len;
    LOGI("cover %u bytes -> ui", (unsigned)acc.len);
    voice_msg_pub(VOICE_MSG_APP_MUSIC_COVER, &ref, sizeof(ref));
}

/* UI 双击选定后：按 bvid 点播 */
static void bili_select_handler(void *unused, uint32_t msg_id, void *data,
                                uint32_t len, void *user_data)
{
    const voice_msg_music_select_t *sel = data;
    char url[URL_MAX_LENGTH];
    cJSON *root;
    const cJSON *ok;
    const cJSON *jurl;
    const cJSON *jtitle;
    const cJSON *jcover;

    (void)unused;
    (void)msg_id;
    (void)user_data;

    if (sel == NULL || len < sizeof(*sel) || sel->index >= g_list.count) {
        LOGW("bad select msg");
        return;
    }

    LOGI("select %d: %s (%s)", sel->index, g_list.title[sel->index], g_list.bvid[sel->index]);

    snprintf(url, sizeof(url), "http://" BILI_SERVICE_HOST ":%d/play?bv=%s",
             BILI_SERVICE_PORT, g_list.bvid[sel->index]);

    root = bili_get_json(url, RESP_MAX * 2);
    if (root == NULL) {
        LOGW("play-bv failed");
        return;
    }

    ok = cJSON_GetObjectItem(root, "ok");
    jurl = cJSON_GetObjectItem(root, "url");
    jtitle = cJSON_GetObjectItem(root, "title");
    if (!cJSON_IsTrue(ok) || !cJSON_IsString(jurl) || jurl->valuestring == NULL) {
        cJSON_Delete(root);
        return;
    }

    jcover = cJSON_GetObjectItem(root, "cover");
    if (cJSON_IsString(jcover) && jcover->valuestring != NULL) {
        bili_push_cover(jcover->valuestring);
    }

    bili_start_playback(cJSON_IsString(jtitle) ? jtitle->valuestring : g_list.title[sel->index],
                        jurl->valuestring);
    cJSON_Delete(root);
}

/* ==================== 端侧意图拦截：ASR → 直接搜索 ==================== */

/*
 * 为什么要绕过 LLM：
 * 云端 LLM 只对自己知识库里的标准歌名（如「晴天」）调音乐工具，
 * 遇到「司凤音乐」「寂寞先生」这类说法会直接回「曲库没有」/「不支持播放」，
 * 同一句话这次调下次不调，不可控。所以在这里拦 ASR 结果：
 * 命中「播放/来首/听」就自己搜，不依赖云端判断。
 */

static char s_iat_text[160];

static void bili_extract_song(const char *text, char *out, size_t n)
{
    static const char *kws[] = {
        "播放一首", "播放一首歌", "播放歌曲", "播放", "放一首", "放首",
        "来一首", "来首", "我想听", "想听", "听一首", "听一下", "听",
    };
    const char *p = NULL;
    size_t i;

    out[0] = '\0';
    for (i = 0; i < sizeof(kws) / sizeof(kws[0]); i++) {
        const char *q = strstr(text, kws[i]);
        if (q) {
            p = q + strlen(kws[i]);
            break;
        }
    }
    if (p == NULL) {
        return;
    }

    /* 跳过前导空格和「的」（UTF-8: E7 9A 84） */
    while (*p == ' ') {
        p++;
    }
    if ((unsigned char)p[0] == 0xe7 && (unsigned char)p[1] == 0x9a &&
        (unsigned char)p[2] == 0x84) {
        p += 3;
    }

    i = 0;
    while (*p && i + 1 < n && *p != '.' && *p != '\n' && *p != ' ' &&
           *p != ',' && *p != '!' && *p != '?') {
        out[i++] = *p++;
    }
    out[i] = '\0';

    /* 去掉末尾的一个中文标点（UTF-8 3 字节）。
     * 注意：中文字符首字节同样 >= 0xe3，所以必须逐个字节比对具体标点，
     * 不能用 >= 判断，否则会把整个歌名删空。 */
    if (i >= 3) {
        unsigned char c0 = (unsigned char)out[i - 3];
        unsigned char c1 = (unsigned char)out[i - 2];
        bool is_punct =
            (c0 == 0xe3 && c1 == 0x80) ||          /* 。 */
            (c0 == 0xef && c1 == 0xbc) ||          /* ，！？ */
            (c0 == 0xe2 && c1 == 0x80);            /* " */
        if (is_punct) {
            i -= 3;
            out[i] = '\0';
        }
    }
}

static void bili_search_and_push(const char *song)
{
    char *encoded;
    char url[URL_MAX_LENGTH];
    cJSON *root;
    const cJSON *ok;
    const cJSON *items;
    int i;
    int n;

    if (song[0] == '\0') {
        return;
    }

    encoded = psram_malloc(256);
    if (encoded == NULL) {
        return;
    }
    url_encode(song, encoded, 256);
    snprintf(url, sizeof(url), "http://" BILI_SERVICE_HOST ":%d/search?q=%s&n=%d",
             BILI_SERVICE_PORT, encoded, VOICE_MSG_MUSIC_LIST_MAX);
    psram_free(encoded);

    LOGI("iat search: %s", song);
    root = bili_get_json(url, RESP_MAX);
    if (root == NULL) {
        LOGW("iat search failed: no service");
        return;
    }

    ok = cJSON_GetObjectItem(root, "ok");
    items = cJSON_GetObjectItem(root, "items");
    if (!cJSON_IsTrue(ok) || !cJSON_IsArray(items)) {
        cJSON_Delete(root);
        return;
    }

    memset(&g_list, 0, sizeof(g_list));
    n = cJSON_GetArraySize(items);
    if (n > VOICE_MSG_MUSIC_LIST_MAX) {
        n = VOICE_MSG_MUSIC_LIST_MAX;
    }
    for (i = 0; i < n; i++) {
        const cJSON *it = cJSON_GetArrayItem(items, i);
        const cJSON *jt = cJSON_GetObjectItem(it, "title");
        const cJSON *jb = cJSON_GetObjectItem(it, "bvid");

        if (!cJSON_IsString(jt) || !cJSON_IsString(jb)) {
            continue;
        }
        snprintf(g_list.title[g_list.count], VOICE_MSG_MUSIC_TITLE_LEN, "%s", jt->valuestring);
        snprintf(g_list.bvid[g_list.count], VOICE_MSG_MUSIC_BVID_LEN, "%s", jb->valuestring);
        g_list.count++;
    }
    cJSON_Delete(root);

    if (g_list.count > 0) {
        LOGI("iat list: %d tracks", g_list.count);
        voice_msg_pub(VOICE_MSG_APP_MUSIC_LIST_SHOW, &g_list, sizeof(g_list));
    } else {
        LOGW("iat list empty");
    }
}

/* 搜索必须放在独立线程：ebus 回调里做同步 HTTP 会阻塞整个事件总线
 * （一次搜索 1~8 秒），表现为界面卡死、语音无响应。 */
struct bili_search_job {
    char song[128];
};

static void bili_search_worker(void *user_data, bool *should_stop)
{
    struct bili_search_job *job = user_data;

    (void)should_stop;
    if (job != NULL) {
        bili_search_and_push(job->song);
    }
}

static void bili_search_complete(void *user_data, bool completed, bool interrupted)
{
    (void)completed;
    (void)interrupted;

    if (user_data != NULL) {
        lisa_mem_free(user_data);
    }
}

static void bili_search_async(const char *song)
{
    struct bili_search_job *job;
    async_task_t *task;

    if (song == NULL || song[0] == 0) {
        return;
    }

    job = lisa_mem_calloc(1, sizeof(*job));
    if (job == NULL) {
        return;
    }
    snprintf(job->song, sizeof(job->song), "%s", song);

    task = async_task_create("bili_search", 4096, 5,
                             bili_search_worker, bili_search_complete, job);
    if (task == NULL) {
        lisa_mem_free(job);
        return;
    }
    if (async_task_start(task) != 0) {
        async_task_destroy(task);
        lisa_mem_free(job);
    }
}

static void bili_on_iat_update(void *unused, uint32_t msg_id, void *data,
                               uint32_t len, void *user_data)
{
    char *p = data;

    (void)unused;
    (void)msg_id;
    (void)user_data;

    if (p == NULL || len == 0 || p[0] == '\0') {
        return;
    }
    if (len > sizeof(s_iat_text) - 1) {
        len = sizeof(s_iat_text) - 1;
    }
    memcpy(s_iat_text, p, len);
    s_iat_text[len] = '\0';
}

static void bili_on_session_finish(void *unused, uint32_t msg_id, void *data,
                                   uint32_t len, void *user_data)
{
    char song[128];

    (void)unused;
    (void)msg_id;
    (void)data;
    (void)len;
    (void)user_data;

    if (s_iat_text[0] == '\0') {
        return;
    }
    LOGI("iat final: %s", s_iat_text);

    bili_extract_song(s_iat_text, song, sizeof(song));
    s_iat_text[0] = '\0';

    if (song[0] != '\0') {
        /* 点歌意图由端侧接管：先掐掉云端这轮会话，否则 LLM 会按自己的判断
         * 回一句「无法播放音乐」/「曲库里没有」，出现「音乐在放但她说不支持」
         * 这种心口不一的情况。 */
        LOGI("iat music intent, interrupt cloud reply");
        voice_msg_pub(VOICE_MSG_CLOUD_SESSION_INTERRUPT, NULL, 0);
        voice_msg_pub(VOICE_MSG_CLOUD_MCP_CHAT_EXIT, NULL, 0);

        bili_search_async(song);
    }
}

static int bili_music_evt_init(void)
{
    voice_msg_sub(VOICE_MSG_APP_MUSIC_SELECT, bili_select_handler, NULL);
    voice_msg_sub(VOICE_MSG_CLOUD_IAT_UPDATE, bili_on_iat_update, NULL);
    voice_msg_sub(VOICE_MSG_CLOUD_IAT_END, bili_on_session_finish, NULL);
    return 0;
}

SYS_INIT(bili_music_evt_init, SYS_INIT_LEVEL_PRE_APPLICATION, 61);
