"""无头冒烟测试：用 Streamlit 自带的 AppTest 跑一遍界面，确认没有异常、数据能出来。

运行方式（在 inquiry-webapp 目录下）：
    python smoke_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).with_name("app.py")


def _button(at: AppTest, label_part: str):
    """按标签找按钮（AppTest 里的元素顺序是：主区在前、侧边栏在后，不要用下标硬取）。"""
    for button in at.button:
        if label_part in button.label:
            return button
    raise AssertionError(f"页面上没找到按钮：{label_part}")


def _text_area(at: AppTest, label_part: str):
    for area in at.text_area:
        if label_part in area.label:
            return area
    raise AssertionError(f"页面上没找到输入框：{label_part}")


def main() -> int:
    at = AppTest.from_file(str(APP_PATH), default_timeout=60)
    at.run()
    if at.exception:
        print("❌ 首次加载就报错：", [str(e.value) for e in at.exception])
        return 1
    print("✅ 页面首次加载成功，标题：", at.title[0].value)

    # 1) 点侧边栏"载入示例询盘"，确认文本进了左侧输入框
    _button(at, "载入示例询盘").click().run()
    if at.exception:
        print("❌ 载入示例失败：", [str(e.value) for e in at.exception])
        return 1
    loaded = _text_area(at, "整段贴进来").value
    if len(loaded) < 100:
        print(f"❌ 示例询盘没载入（当前 {len(loaded)} 字）")
        return 1
    print(f"✅ 示例询盘已载入，{len(loaded)} 字")

    # 2) 点主区"解析询盘并生成回复"
    _button(at, "解析询盘并生成回复").click().run()
    if at.exception:
        print("❌ 解析失败：", [str(e.value) for e in at.exception])
        return 1

    print("✅ 指标：", [(m.label, m.value) for m in at.metric])
    if not at.dataframe:
        print("❌ 需求表格没有渲染出来")
        return 1
    rows = at.dataframe[0].value.to_dict("records")
    print(f"✅ 需求表格 {len(rows)} 行：")
    for row in rows:
        print("   -", row["需求项"], "=", row["内容"])

    reply = at.session_state.get("reply_box", "")
    print("✅ 回复草稿前 5 行：")
    for line in reply.splitlines()[:5]:
        print("   |", line)
    if "Subject:" not in reply or "Dear" not in reply:
        print("❌ 回复草稿内容不像是完整邮件")
        return 1

    # 3) 点"清空"，确认输入框和结果都被清掉
    _button(at, "清空").click().run()
    if at.exception:
        print("❌ 清空失败：", [str(e.value) for e in at.exception])
        return 1
    if _text_area(at, "整段贴进来").value != "" or at.session_state.get("reply_box", ""):
        print("❌ 清空后仍残留内容")
        return 1
    print("✅ 清空正常")

    print("\n🎉 冒烟测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

