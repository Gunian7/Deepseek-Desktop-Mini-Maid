#ifndef __MUSIC_UI_H__
#define __MUSIC_UI_H__

#include "lvgl.h"

/**
 * @brief 创建音乐播放界面（窄条形态，隐藏状态）。
 * @param parent 一般传 home 页的 view（lisa_ui_llm_primary）
 */
void music_ui_init(lv_obj_t *parent);

/**
 * @brief 更新歌曲标题。传入空串会清空。
 */
void music_ui_set_title(const char *title);

/**
 * @brief 在「窄条」和「全屏」两种形态之间切换（单击功能键触发）。
 */
void music_ui_toggle_mode(void);

#include <stdbool.h>
#include "voice_msg.h"

/** 搜索结果列表是否正在显示 */
bool music_ui_list_active(void);

/** 单击：选中项下移 */
void music_ui_list_next(void);

/** 双击：选定并播放 */
void music_ui_list_confirm(void);

/** 直接用数据刷新列表（一般由 ebus 消息驱动，不必手动调） */
void music_ui_show_list(const voice_msg_music_list_t *list);

#endif /* __MUSIC_UI_H__ */
