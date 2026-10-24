/*
 * 音乐播放界面（两种形态，单击切换）
 *
 *   B 窄条（默认）：贴在表情下方一条，左歌名 / 右时间 / 底部细进度条
 *   A 全屏：整屏黑底，大字标题 + 粗进度条 + 时间
 *
 * 数据来源：
 *   标题  - home_presenter 的 on_standby_text_update（is_cloud_text=false 时是音乐名）
 *   进度  - voice_player_music_get_progress()（内部走 app_player_get_position）
 *
 * 只在 music active（播放/暂停）时显示，停止后自动隐藏。
 */
#include "music_ui.h"

#include <stdio.h>
#include <string.h>

#include "lisa_log.h"
#include "lvgl.h"
#include "voice_player_music.h"
#include "voice_msg.h"
#include "lisa_ui.h"
#include "sys_init.h"

#define TAG "music_ui"

LV_FONT_DECLARE(lv_font_chinese_16)

#define BAR_H        26      /* 窄条高度 */
#define SCREEN_W     240
#define SCREEN_H     240

static lv_obj_t *s_root;
static lv_obj_t *s_title;
static lv_obj_t *s_time;
static lv_obj_t *s_bar;
static lv_obj_t *s_cover;
static lv_timer_t *s_timer;
static uint8_t s_full;          /* 0 = 窄条, 1 = 全屏 */
static uint8_t s_visible;
static char s_last_title[96];

static void fmt_ms(char *buf, size_t n, uint32_t ms)
{
    unsigned m = (unsigned)(ms / 60000U);
    unsigned s = (unsigned)((ms / 1000U) % 60U);
    snprintf(buf, n, "%u:%02u", m, s);
}

static void apply_layout(void)
{
    if (s_root == NULL) {
        return;
    }

    if (s_full) {
        lv_obj_set_size(s_root, SCREEN_W, SCREEN_H);
        lv_obj_set_pos(s_root, 0, 0);
        lv_obj_set_style_bg_opa(s_root, LV_OPA_COVER, LV_PART_MAIN);

        lv_obj_set_size(s_title, SCREEN_W - 24, 90);
        lv_obj_set_pos(s_title, 12, 46);
        lv_obj_set_style_text_align(s_title, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
        lv_obj_clear_flag(s_title, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(s_cover, LV_OBJ_FLAG_HIDDEN);

        lv_obj_set_size(s_bar, SCREEN_W - 40, 8);
        lv_obj_set_pos(s_bar, 20, 146);

        lv_obj_set_size(s_time, SCREEN_W - 40, 22);
        lv_obj_set_pos(s_time, 20, 162);
        lv_obj_set_style_text_align(s_time, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
    } else {
        lv_obj_set_size(s_root, 200, BAR_H);
        lv_obj_set_pos(s_root, (SCREEN_W - 200) / 2, SCREEN_H - BAR_H - 2);
        lv_obj_set_style_bg_opa(s_root, (lv_opa_t)180, LV_PART_MAIN);

        /* 窄条不显示歌名：表情界面本身已经有标题，两处会重复 */
        lv_obj_add_flag(s_title, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(s_cover, LV_OBJ_FLAG_HIDDEN);

        lv_obj_set_size(s_bar, 192, 3);
        lv_obj_set_pos(s_bar, 4, 21);

        lv_obj_set_size(s_time, 60, 16);
        lv_obj_set_pos(s_time, 136, 2);
        lv_obj_set_style_text_align(s_time, LV_TEXT_ALIGN_RIGHT, LV_PART_MAIN);
    }
}

static void refresh_cb(lv_timer_t *timer)
{
    uint32_t pos = 0;
    uint32_t dur = 0;
    char buf[24];

    (void)timer;

    if (s_root == NULL) {
        return;
    }

    if (!voice_player_music_is_active()) {
        if (s_visible) {
            lv_obj_add_flag(s_root, LV_OBJ_FLAG_HIDDEN);
            s_visible = 0;
        }
        return;
    }

    if (!s_visible) {
        lv_obj_clear_flag(s_root, LV_OBJ_FLAG_HIDDEN);
        lv_obj_move_foreground(s_root);
        s_visible = 1;
    }

    if (voice_player_music_get_progress(&pos, &dur) == 0 && dur > 0) {
        lv_bar_set_range(s_bar, 0, (int32_t)dur);
        lv_bar_set_value(s_bar, (int32_t)pos, LV_ANIM_OFF);
        snprintf(buf, sizeof(buf), "%u:%02u/%u:%02u",
                 (unsigned)(pos / 60000U), (unsigned)((pos / 1000U) % 60U),
                 (unsigned)(dur / 60000U), (unsigned)((dur / 1000U) % 60U));
    } else {
        snprintf(buf, sizeof(buf), "播放中");
    }

    if (voice_player_music_is_paused()) {
        snprintf(buf + strlen(buf), sizeof(buf) - strlen(buf), " 暂停");
        lv_obj_set_style_bg_color(s_bar, lv_color_hex(0x66707f), LV_PART_INDICATOR);
    } else {
        lv_obj_set_style_bg_color(s_bar, lv_color_hex(0x4f8ef7), LV_PART_INDICATOR);
    }

    lv_label_set_text(s_time, buf);
}

static lv_img_dsc_t s_cover_dsc;
static uint8_t *s_cover_buf;   /* PSRAM 里分配，静态区放不下 8KB */

/* 收到 CP 侧推来的封面（RGB565 + 8 字节头），直接当内存图片源 */
void music_ui_set_cover(const uint8_t *data, uint32_t len)
{
    uint32_t dsize = 0;

    if (data == NULL || len < 8 || len > VOICE_MSG_MUSIC_COVER_SIZE) {
        return;
    }
    if (s_cover == NULL) {
        return;
    }

    if (s_cover_buf == NULL) {
        s_cover_buf = lisa_ui_malloc(VOICE_MSG_MUSIC_COVER_SIZE);
        if (s_cover_buf == NULL) {
            return;
        }
    }

    memcpy(s_cover_buf, data, len);
    memcpy(&s_cover_dsc.header, s_cover_buf, sizeof(s_cover_dsc.header));
    memcpy(&dsize, s_cover_buf + 4, 4);
    s_cover_dsc.data_size = dsize;
    s_cover_dsc.data = s_cover_buf + 8;

    lv_img_set_src(s_cover, &s_cover_dsc);
    LOGI("cover shown %ux%u", (unsigned)s_cover_dsc.header.w, (unsigned)s_cover_dsc.header.h);
}

static void music_on_cover(void *unused, uint32_t msg_id, void *data,
                           uint32_t len, void *user_data)
{
    (void)unused;
    (void)msg_id;
    (void)user_data;

    if (data == NULL || len < sizeof(voice_msg_music_cover_t)) {
        return;
    }
    music_ui_set_cover((const uint8_t *)data, len);
}

void music_ui_init(lv_obj_t *parent)
{
    if (parent == NULL || s_root != NULL) {
        return;
    }

    s_root = lv_obj_create(parent);
    lv_obj_clear_flag(s_root, LV_OBJ_FLAG_SCROLLABLE);
    /* 父对象 lisa_ui_llm_primary 是 FLEX COLUMN 布局，不忽略排版的话
     * 我们设的坐标会被 flex 冲掉，控件会跑到流的末尾。 */
    lv_obj_add_flag(s_root, LV_OBJ_FLAG_IGNORE_LAYOUT);
    lv_obj_set_style_border_width(s_root, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(s_root, 0, LV_PART_MAIN);
    lv_obj_set_style_bg_color(s_root, lv_color_black(), LV_PART_MAIN);
    lv_obj_set_style_pad_all(s_root, 0, LV_PART_MAIN);

    s_title = lv_label_create(s_root);
    lv_obj_set_style_text_font(s_title, &lv_font_chinese_16, LV_PART_MAIN);
    lv_obj_set_style_text_color(s_title, lv_color_white(), LV_PART_MAIN);
    lv_label_set_long_mode(s_title, LV_LABEL_LONG_SCROLL_CIRCULAR);
    lv_label_set_text(s_title, "");

    s_time = lv_label_create(s_root);
    lv_obj_set_style_text_font(s_time, &lv_font_chinese_16, LV_PART_MAIN);
    lv_obj_set_style_text_color(s_time, lv_color_hex(0xb8c4d8), LV_PART_MAIN);
    lv_label_set_text(s_time, "");

    s_cover = lv_img_create(s_root);
    lv_obj_add_flag(s_cover, LV_OBJ_FLAG_IGNORE_LAYOUT);
    lv_obj_set_size(s_cover, 64, 64);
    lv_obj_set_pos(s_cover, (SCREEN_W - 64) / 2, 8);
    lv_obj_add_flag(s_cover, LV_OBJ_FLAG_HIDDEN);

    s_bar = lv_bar_create(s_root);
    lv_obj_set_style_bg_color(s_bar, lv_color_hex(0x2a3342), LV_PART_MAIN);
    lv_obj_set_style_bg_color(s_bar, lv_color_hex(0x4f8ef7), LV_PART_INDICATOR);
    lv_obj_set_style_radius(s_bar, 2, LV_PART_MAIN);
    lv_obj_set_style_radius(s_bar, 2, LV_PART_INDICATOR);
    lv_bar_set_value(s_bar, 0, LV_ANIM_OFF);

    s_full = 0;
    apply_layout();

    lv_obj_add_flag(s_root, LV_OBJ_FLAG_HIDDEN);
    s_visible = 0;

    s_timer = lv_timer_create(refresh_cb, 1000, NULL);

    LOGI("music ui ready");
}

void music_ui_set_title(const char *title)
{
    if (s_root == NULL || title == NULL) {
        return;
    }

    if (strncmp(s_last_title, title, sizeof(s_last_title) - 1) == 0) {
        return;
    }
    strncpy(s_last_title, title, sizeof(s_last_title) - 1);
    s_last_title[sizeof(s_last_title) - 1] = '\0';

    lv_label_set_text(s_title, title);
    LOGI("title: %s", title);
}

void music_ui_toggle_mode(void)
{
    s_full = s_full ? 0 : 1;
    apply_layout();
    if (s_visible) {
        lv_obj_move_foreground(s_root);
    }
    LOGI("mode -> %s", s_full ? "fullscreen" : "bar");
}

/* ==================== 搜索结果选择列表 ==================== */

#define ROW_H        40
#define ROW_GAP      4
#define ROW_TOP      12
#define ROW_W        (SCREEN_W - 16)

static lv_obj_t *s_list_root;
static lv_obj_t *s_row[VOICE_MSG_MUSIC_LIST_MAX];
static uint8_t s_list_count;
static uint8_t s_list_sel;
static voice_msg_music_list_t s_list_data;

static void list_row_paint(uint8_t i, uint8_t selected)
{
    if (i >= s_list_count || s_row[i] == NULL) {
        return;
    }

    lv_obj_set_style_bg_color(s_row[i],
                              selected ? lv_color_hex(0x3a5fa8) : lv_color_hex(0x1c2230),
                              LV_PART_MAIN);
    lv_obj_set_style_bg_opa(s_row[i], LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_text_color(s_row[i],
                                selected ? lv_color_white() : lv_color_hex(0xa8b2c2),
                                LV_PART_MAIN);
}

void music_ui_show_list(const voice_msg_music_list_t *list)
{
    uint8_t i;

    if (list == NULL || list->count == 0) {
        return;
    }

    memcpy(&s_list_data, list, sizeof(s_list_data));
    s_list_count = s_list_data.count;
    s_list_sel = 0;

    if (s_list_root == NULL) {
        s_list_root = lv_obj_create(lv_scr_act());
        lv_obj_add_flag(s_list_root, LV_OBJ_FLAG_IGNORE_LAYOUT);
        lv_obj_clear_flag(s_list_root, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_set_size(s_list_root, SCREEN_W, SCREEN_H);
        lv_obj_set_pos(s_list_root, 0, 0);
        lv_obj_set_style_bg_color(s_list_root, lv_color_black(), LV_PART_MAIN);
        lv_obj_set_style_bg_opa(s_list_root, LV_OPA_COVER, LV_PART_MAIN);
        lv_obj_set_style_border_width(s_list_root, 0, LV_PART_MAIN);
        lv_obj_set_style_radius(s_list_root, 0, LV_PART_MAIN);
        lv_obj_set_style_pad_all(s_list_root, 0, LV_PART_MAIN);

        for (i = 0; i < VOICE_MSG_MUSIC_LIST_MAX; i++) {
            lv_obj_t *row = lv_label_create(s_list_root);
            lv_obj_add_flag(row, LV_OBJ_FLAG_IGNORE_LAYOUT);
            lv_obj_clear_flag(row, LV_OBJ_FLAG_SCROLLABLE);
            lv_obj_set_size(row, ROW_W, ROW_H);
            lv_obj_set_pos(row, 8, ROW_TOP + i * (ROW_H + ROW_GAP));
            lv_obj_set_style_border_width(row, 0, LV_PART_MAIN);
            lv_obj_set_style_radius(row, 6, LV_PART_MAIN);
            lv_obj_set_style_pad_all(row, 0, LV_PART_MAIN);
            lv_obj_set_style_text_font(row, &lv_font_chinese_16, LV_PART_MAIN);
            lv_obj_set_style_text_align(row, LV_TEXT_ALIGN_LEFT, LV_PART_MAIN);
            lv_label_set_long_mode(row, LV_LABEL_LONG_DOT);
            s_row[i] = row;
        }
    }

    for (i = 0; i < VOICE_MSG_MUSIC_LIST_MAX; i++) {
        char buf[VOICE_MSG_MUSIC_TITLE_LEN + 8];

        if (i >= s_list_count) {
            lv_obj_add_flag(s_row[i], LV_OBJ_FLAG_HIDDEN);
            continue;
        }

        lv_obj_clear_flag(s_row[i], LV_OBJ_FLAG_HIDDEN);
        snprintf(buf, sizeof(buf), "%u. %s", (unsigned)(i + 1), s_list_data.title[i]);
        lv_label_set_text(s_row[i], buf);
        list_row_paint(i, i == s_list_sel);
    }

    lv_obj_clear_flag(s_list_root, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(s_list_root);
    LOGI("list shown: %u items", (unsigned)s_list_count);
}

bool music_ui_list_active(void)
{
    return s_list_root != NULL && !lv_obj_has_flag(s_list_root, LV_OBJ_FLAG_HIDDEN);
}

void music_ui_list_next(void)
{
    uint8_t prev;

    if (!music_ui_list_active() || s_list_count == 0) {
        return;
    }

    prev = s_list_sel;
    s_list_sel = (uint8_t)((s_list_sel + 1) % s_list_count);
    list_row_paint(prev, 0);
    list_row_paint(s_list_sel, 1);
    LOGI("list sel -> %u", (unsigned)s_list_sel);
}

void music_ui_list_confirm(void)
{
    voice_msg_music_select_t sel;

    if (!music_ui_list_active() || s_list_count == 0) {
        return;
    }

    sel.index = s_list_sel;

    lv_obj_add_flag(s_list_root, LV_OBJ_FLAG_HIDDEN);

    LOGI("list confirm %u -> %s", (unsigned)s_list_sel, s_list_data.title[s_list_sel]);
    voice_msg_pub(VOICE_MSG_APP_MUSIC_SELECT, &sel, sizeof(sel));
}

static void music_on_list_show(void *unused, uint32_t msg_id, void *data,
                               uint32_t len, void *user_data)
{
    (void)unused;
    (void)msg_id;
    (void)user_data;

    if (data == NULL || len < sizeof(voice_msg_music_list_t)) {
        return;
    }

    music_ui_show_list((const voice_msg_music_list_t *)data);
}

static int music_ui_evt_init(void)
{
    voice_msg_sub(VOICE_MSG_APP_MUSIC_LIST_SHOW, music_on_list_show, NULL);
    voice_msg_sub(VOICE_MSG_APP_MUSIC_COVER, music_on_cover, NULL);
    return 0;
}

SYS_INIT(music_ui_evt_init, SYS_INIT_LEVEL_PRE_APPLICATION, 62);
