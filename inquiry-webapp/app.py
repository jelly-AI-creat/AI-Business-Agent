"""外贸询盘助手 —— Streamlit 网页版。

启动方式（在 app.py 所在目录下执行）：
    python -m streamlit run app.py
浏览器会自动打开 http://localhost:8501

界面布局：左边贴客户询盘邮件，右边显示提取到的需求 + 自动生成的英文回复草稿。
"""

from __future__ import annotations

import datetime as dt

import streamlit as st

import inquiry_core as core

st.set_page_config(page_title="外贸询盘助手", page_icon="✉️", layout="wide")


# ---------------------------------------------------------------- 会话状态与回调
# Streamlit 每次交互都会把整个脚本从头跑一遍，所以解析结果放在 st.session_state 里。


def _request_sample() -> None:
    """点按钮时只留一个标记，真正的赋值放到本轮渲染最开始做。"""
    st.session_state["pending_action"] = "sample"


def _request_clear() -> None:
    st.session_state["pending_action"] = "clear"


def _apply_pending_action() -> None:
    """在创建任何输入框之前更新 session_state，避免和输入框自身状态打架。"""
    action = st.session_state.get("pending_action", "")
    if not action:
        return
    st.session_state["pending_action"] = ""
    st.session_state["analysis"] = None
    st.session_state["reply_box"] = ""
    st.session_state["inquiry_text"] = core.SAMPLE_EMAIL if action == "sample" else ""


def _run_analysis() -> None:
    """解析询盘 + 生成回复，结果写进 session_state，由右侧列渲染。"""
    text = st.session_state.get("inquiry_text", "")
    if not text.strip():
        st.session_state["analysis"] = None
        st.session_state["reply_box"] = ""
        return
    use_legacy = st.session_state.get("use_legacy", True)
    try:
        with st.spinner("正在解析询盘并生成英文回复…"):
            analysis = core.analyze(text, use_legacy=use_legacy)
            reply = core.generate_reply(
                analysis,
                company=st.session_state.get("company", ""),
                sender=st.session_state.get("sender", ""),
                use_legacy=use_legacy,
            )
    except Exception as exc:  # 任何异常只提示，不让页面白屏
        st.session_state["analysis"] = None
        st.session_state["reply_box"] = ""
        st.error(f"解析失败：{exc}")
        return
    st.session_state["analysis"] = analysis
    st.session_state["reply_box"] = reply


st.session_state.setdefault("inquiry_text", "")
st.session_state.setdefault("analysis", None)
st.session_state.setdefault("reply_box", "")
st.session_state.setdefault("pending_action", "")

_apply_pending_action()


# ---------------------------------------------------------------- 侧边栏：设置
with st.sidebar:
    st.header("⚙️ 设置")
    st.text_input("公司名（签在回复末尾）", key="company", placeholder="ABC Industrial Co., Ltd.")
    st.text_input("你的名字 / 签名", key="sender", placeholder="Lily Chen")
    st.divider()

    st.checkbox(
        "优先使用我原来的询盘脚本",
        key="use_legacy",
        value=True,
        help=f"脚本路径由环境变量 {core.LEGACY_PATH_ENV} 指定，加载失败会自动用内置规则。",
    )
    legacy_path = core.legacy_status()
    if legacy_path:
        st.caption(f"✅ 已接入你的脚本：\n\n`{legacy_path}`")
        if st.button("重新加载脚本"):
            core.reload_legacy_module()
            st.rerun()
    else:
        st.caption(
            "⚠️ 还没接入你自己的脚本，当前使用内置规则。\n\n"
            f"接入方法：设置环境变量 `{core.LEGACY_PATH_ENV}` 指向脚本文件。"
        )

    st.divider()
    st.button("载入示例询盘", on_click=_request_sample)
    st.button("清空", on_click=_request_clear)


# ---------------------------------------------------------------- 主界面
st.title("✉️ 外贸询盘助手")
st.caption("左边贴客户的询盘邮件 → 右边自动提取需求要点，并生成英文回复草稿。")

col_inquiry, col_result = st.columns(2, gap="large")

with col_inquiry:
    st.subheader("① 询盘邮件原文")
    st.text_area(
        "把客户的邮件（含主题、正文、签名）整段贴进来",
        key="inquiry_text",
        height=430,
        placeholder="Subject: Inquiry for 5,000 pcs LED high bay light\n\nDear Sales Team,\n...",
    )
    st.button("🔍 解析询盘并生成回复", type="primary", on_click=_run_analysis)
    st.caption(f"当前字数：{len(st.session_state.get('inquiry_text', ''))}")
    if st.checkbox("修改后自动解析", value=False, help="邮件很长时可以关掉，手动点按钮更快。"):
        _run_analysis()

with col_result:
    st.subheader("② 提取的需求")
    analysis: core.InquiryAnalysis | None = st.session_state.get("analysis")
    if analysis is None:
        st.info("在左边粘贴询盘邮件，然后点「🔍 解析询盘并生成回复」。")
    else:
        metric_left, metric_mid, metric_right = st.columns(3)
        metric_left.metric("需求项", len(analysis.requirements))
        metric_mid.metric("缺少信息", len(analysis.missing))
        metric_right.metric("紧急程度", "⚡ 紧急" if analysis.is_urgent else "普通")

        if analysis.requirements:
            st.dataframe(analysis.to_rows(), hide_index=True)
        else:
            st.warning("没有提取到结构化信息，可能邮件格式比较特殊，建议人工看一下原文。")

        if analysis.missing:
            st.warning(
                "邮件里没提到这些信息，回复草稿已自动加上反问：\n\n"
                + "\n".join(f"- {name}" for name in analysis.missing)
            )
        else:
            st.success("关键信息比较完整，可以直接核算报价。")
        st.caption(f"解析来源：{analysis.source}")

    st.subheader("③ 英文回复草稿")
    reply = st.session_state.get("reply_box", "")
    if not reply:
        st.info("生成后显示在这里，可以直接复制，也可以下载成 txt。")
    else:
        st.text_area("可以让同事先改一遍再发出去", key="reply_box", height=380)
        st.download_button(
            "⬇️ 下载回复草稿 (txt)",
            data=reply,
            file_name=f"reply_draft_{dt.date.today():%Y%m%d}.txt",
            mime="text/plain",
        )