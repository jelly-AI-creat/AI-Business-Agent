#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
email_reply_drafter_llm.py

在离线版 email_reply_drafter.py 之上叠加 LLM 能力：

  - 复用离线版的「读取输入 / 切分邮件 / 正则抽取需求」逻辑（不重复实现，也不修改原文件）
  - 用 requests + python-dotenv 调用 DeepSeek（OpenAI 兼容格式）生成英文回复草稿
  - 无 Key 或调用失败时，自动回退到离线版草稿，保证流程不中断

依赖安装：
    python -m pip install requests python-dotenv
    # 若 pip 卡住（连不上 pypi.org），改用清华镜像：
    python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple requests python-dotenv

用法（与离线版一致，请在 AI_Email_Agent 目录下执行）：
    python email_reply_drafter_llm.py --check              # 免 token 预检 Key 与余额
    python email_reply_drafter_llm.py --limit 1 --dry-run  # 完全不联网，验证排版与降级逻辑
    python email_reply_drafter_llm.py --limit 1            # 只处理第 1 封（省钱试跑）
    python email_reply_drafter_llm.py                      # 全量处理 raw_emails.txt
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

# 让「从任意工作目录执行本脚本」时也能 import 同目录的离线版模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit(
        "缺少依赖 requests。请先安装：\n"
        "    python -m pip install requests python-dotenv\n"
        "若 pip 卡住（连不上 pypi.org），改用清华镜像：\n"
        "    python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple requests python-dotenv"
    )

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    sys.exit(
        "缺少依赖 python-dotenv。请先安装：\n"
        "    python -m pip install python-dotenv"
    )

try:
    # 复用离线版的解析层：其 main() 有 __name__ 保护，import 不会触发执行
    from email_reply_drafter import (
        RAW_FILE,
        build_draft,
        ensure_raw_file,
        extract_requirements,
        parse_email,
        split_emails,
    )
except ImportError as exc:  # pragma: no cover
    sys.exit(
        f"无法导入同目录的 email_reply_drafter.py：{exc}\n"
        "请确认本脚本与 email_reply_drafter.py 位于同一目录。"
    )


# ---------------------------------------------------------------------------
# 常量与默认配置
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(SCRIPT_DIR, ".env")

DRAFT_MARKER = "【回复草稿】"      # 与离线版 build_draft() 的分节标题保持一致
CHAT_PATH = "/chat/completions"    # DeepSeek（OpenAI 兼容格式）对话端点
MODELS_PATH = "/models"
BALANCE_PATH = "/user/balance"

DEFAULT_BASE_URL = "https://api.deepseek.com"
# 2026 年 DeepSeek 现役模型：deepseek-flash（快、便宜）/ deepseek-v4-pro（更强、更贵）
# 注意：旧模型名 deepseek-chat、deepseek-reasoner 已下线，填了会返回 HTTP 400
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_TIMEOUT = 60
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 1024
DEFAULT_RETRIES = 2
DEFAULT_DRAFT_FILE = "reply_drafts_llm.txt"
DEFAULT_REASONING_EFFORT = "high"

# .env 里未替换的占位符特征，命中即视为「尚未配置 Key」
PLACEHOLDER_HINTS = ("请把", "粘贴到这里", "your-key", "your_key", "xxxxxxxx", "sk-xxx")

RETRY_STATUS = (429, 500, 503)     # 仅这些状态码退避重试；401/402/422 立即失败
ERROR_HINTS = {
    400: "请求格式不合法（常见原因：LLM_MODEL 填了不存在的模型名）",
    401: "API Key 无效或已失效（请检查 LLM_API_KEY）",
    402: "账户余额不足，请到 DeepSeek 开放平台充值",
    422: "请求参数不合法",
    429: "触发限流（请求过于频繁）",
    500: "DeepSeek 服务端错误",
    503: "DeepSeek 服务繁忙",
}

TONE_STYLES = {
    "formal": "Formal, courteous and businesslike. Neutral professional wording.",
    "friendly": "Warm and approachable, still professional. Slightly conversational.",
    "concise": "Concise and to the point. Short paragraphs, no filler.",
}

SYSTEM_PROMPT = (
    "You are a senior export sales manager at a Chinese manufacturer that sells to "
    "overseas buyers, and you are replying to inbound customer inquiries.\n"
    "Hard rules:\n"
    "1. Write ONLY in English, as a ready-to-send email body (no subject line).\n"
    "2. NEVER invent facts: no made-up prices, MOQ, lead times, certifications, "
    "payment terms or stock status. When the buyer asked for something you cannot "
    "know, use a placeholder such as [to be confirmed] and promise to confirm it in "
    "the next email.\n"
    "3. Greet the customer by name when the contact name is known.\n"
    "4. Acknowledge every concrete requirement in the structured fields (product, "
    "quantity, pricing basis, lead time, certification, samples, extra notes).\n"
    "5. Plain text only: no markdown, no code fences, no emoji.\n"
    "6. End with exactly this signature block:\n"
    "[Your Name]\n[Your Title]\n[Your Company]\n[Email] | [Phone]\n"
    "7. Keep the whole email under 220 words."
)
# ---------------------------------------------------------------------------
# 失败处理与配置读取
# ---------------------------------------------------------------------------
class LLMError(Exception):
    """调用 LLM 失败时抛出；message 已是可直接展示给用户的中文提示。"""

    def __init__(self, message: str, status=None):
        super().__init__(message)
        self.status = status


def mask_secret(secret: str) -> str:
    """只展示 Key 的头尾，避免密钥出现在终端输出或错误信息中。"""
    secret = (secret or "").strip()
    if not secret:
        return "（未设置）"
    if len(secret) <= 8:
        return "****"
    return f"{secret[:3]}****{secret[-4:]}"


def is_placeholder(value: str) -> bool:
    """判断 Key 是否为空、或仍是 .env 里的占位文字。"""
    low = (value or "").strip().lower()
    if not low:
        return True
    return any(hint.lower() in low for hint in PLACEHOLDER_HINTS)


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, "")).strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, "")).strip() or default)
    except ValueError:
        return default


def load_config() -> dict:
    """读取同目录 .env（已存在的系统环境变量优先）并回填默认值。"""
    if os.path.exists(ENV_FILE):
        load_dotenv(ENV_FILE, override=False)

    api_key = (os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or "").strip()
    return {
        "api_key": api_key,
        "base_url": (os.getenv("LLM_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/"),
        "model": (os.getenv("LLM_MODEL") or DEFAULT_MODEL).strip(),
        "timeout": _env_int("LLM_TIMEOUT", DEFAULT_TIMEOUT),
        "temperature": _env_float("LLM_TEMPERATURE", DEFAULT_TEMPERATURE),
        "max_tokens": _env_int("LLM_MAX_TOKENS", DEFAULT_MAX_TOKENS),
        "retries": max(0, _env_int("LLM_RETRIES", DEFAULT_RETRIES)),
        "draft_file": (os.getenv("LLM_DRAFT_FILE") or DEFAULT_DRAFT_FILE).strip(),
        "tone": (os.getenv("LLM_TONE") or "formal").strip(),
        "reasoning_effort": (os.getenv("LLM_REASONING_EFFORT") or DEFAULT_REASONING_EFFORT).strip(),
        "thinking": False,
    }


# ---------------------------------------------------------------------------
# HTTP 调用层（requests）
# ---------------------------------------------------------------------------
def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


def resp_json(resp):
    """解析响应 JSON，失败时抛出统一的 LLMError。"""
    try:
        return resp.json()
    except ValueError:
        raise LLMError("响应不是合法 JSON（可能被网络中间层改写）")


def _server_error_message(resp) -> str:
    """尽力从响应体里取出服务端错误说明（不含任何密钥信息）。"""
    try:
        data = resp.json()
    except ValueError:
        return (resp.text or "").strip()[:300]
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])[:300]
        if isinstance(err, str):
            return err[:300]
    return json.dumps(data, ensure_ascii=False)[:300]


def _raise_for_status(resp) -> None:
    if resp.status_code < 400:
        return
    hint = ERROR_HINTS.get(resp.status_code, "未知错误")
    raise LLMError(
        f"HTTP {resp.status_code} {hint}；服务端返回：{_server_error_message(resp)}",
        status=resp.status_code,
    )


def _retry_wait(resp, attempt: int) -> float:
    """优先尊重服务端的 Retry-After，否则指数退避（上限 30s）。"""
    raw = resp.headers.get("Retry-After", "")
    try:
        return max(0.0, min(float(raw), 30.0))
    except (TypeError, ValueError):
        return min(2.0 ** attempt, 8.0)


def api_request(session, cfg: dict, method: str, path: str, payload=None):
    """发送一次请求；仅对 429/500/503 与超时做退避重试。"""
    url = f"{cfg['base_url']}{path}"
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}
    last_error = None

    for attempt in range(cfg["retries"] + 1):
        try:
            resp = session.request(
                method, url, headers=headers, json=payload, timeout=cfg["timeout"]
            )
        except requests.exceptions.Timeout:
            last_error = LLMError(
                f"请求超时（LLM_TIMEOUT={cfg['timeout']}s）：{url}\n"
                "        可调大 LLM_TIMEOUT，或检查网络/代理是否拦截了该域名。"
            )
        except requests.exceptions.RequestException as exc:
            raise LLMError(f"网络请求失败：{exc.__class__.__name__}（目标 {url}）")
        else:
            if resp.status_code < 400:
                return resp
            if resp.status_code in RETRY_STATUS and attempt < cfg["retries"]:
                wait = _retry_wait(resp, attempt)
                print(
                    f"    [重试] HTTP {resp.status_code}，等待 {wait:.1f}s"
                    f"（{attempt + 1}/{cfg['retries']}）"
                )
                time.sleep(wait)
                continue
            _raise_for_status(resp)

        if attempt < cfg["retries"]:
            wait = min(2.0 ** attempt, 8.0)
            print(f"    [重试] 等待 {wait:.1f}s（{attempt + 1}/{cfg['retries']}）")
            time.sleep(wait)

    raise last_error or LLMError("请求失败（重试次数已用尽）")
# ---------------------------------------------------------------------------
# 业务层：Prompt 组装 / 调用 / 结果拼接
# ---------------------------------------------------------------------------
def api_chat(session, cfg: dict, messages: list):
    """调用 /chat/completions，返回 (回复正文, usage, 耗时秒数)。"""
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "max_tokens": cfg["max_tokens"],
        "stream": False,
    }
    if cfg["thinking"]:
        # 思考模式：temperature 无效，改用 reasoning_effort 控制思考深度
        payload["thinking"] = {"type": "enabled"}
        payload["reasoning_effort"] = cfg["reasoning_effort"]
    else:
        # DeepSeek 默认开启思考模式（effort=high）；写询盘回复不需要，显式关闭更快更省钱
        payload["thinking"] = {"type": "disabled"}
        payload["temperature"] = cfg["temperature"]

    started = time.time()
    resp = api_request(session, cfg, "POST", CHAT_PATH, payload)
    elapsed = time.time() - started

    data = resp_json(resp)
    try:
        text = (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        preview = json.dumps(data, ensure_ascii=False)[:300]
        raise LLMError(f"响应结构异常，缺少 choices[0].message.content：{preview}")

    if not text:
        raise LLMError("模型返回了空内容（如开启思考模式，请调大 LLM_MAX_TOKENS）")

    return text, (data.get("usage") or {}), elapsed


def build_messages(email: dict, req: dict, tone_key: str) -> list:
    """把「结构化字段 + 邮件原文」拼成 Prompt（不含任何密钥）。"""
    def val(x):
        return x if x else "（未提及）"

    tone = TONE_STYLES.get(tone_key, TONE_STYLES["formal"])
    lines = [
        f"Tone: {tone}",
        "",
        "Structured fields extracted from the inquiry (regex pre-pass, may be incomplete):",
        f"- Product: {val(req['product'])}",
        f"- Quantity: {val(req['quantity'])}",
        f"- Pricing requested: {val(req['price_request'])}",
        f"- Lead time: {val(req['lead_time'])}",
        f"- Certification: {val(req['certification'])}",
        f"- Samples: {val(req['samples'])}",
        f"- Customer company: {val(req['company'])}",
        f"- Contact name: {val(req['contact_name'])}",
        f"- Contact email: {val(req['contact_email'])}",
        f"- Contact phone: {val(req['contact_phone'])}",
        f"- Extra notes: {'；'.join(req['notes']) if req['notes'] else '（无）'}",
        "",
        "Original inquiry email:",
        f"From: {email['from']}",
        f"To: {email['to']}",
        f"Subject: {email['subject']}",
        "",
        email["body"],
        "",
        "Task: write the reply email body answering this inquiry, following all hard rules.",
    ]
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(lines)},
    ]


def replace_reply_section(offline_draft: str, llm_text: str) -> str:
    """保留离线草稿的「客户需求提取」区块，只把【回复草稿】正文换成 LLM 产出。"""
    idx = offline_draft.find(DRAFT_MARKER)
    if idx == -1:
        # 兜底：标记不存在时也不丢内容
        return offline_draft.rstrip() + "\n\n" + llm_text.strip() + "\n"
    head = offline_draft[: idx + len(DRAFT_MARKER)]
    return f"{head}\n\n{llm_text.strip()}\n"


def run_check(cfg: dict) -> int:
    """免 token 预检：GET /models 校验 Key，GET /user/balance 查余额。"""
    if is_placeholder(cfg["api_key"]):
        print("[失败] 尚未配置有效的 API Key。")
        print(f"        请把 {ENV_FILE} 里的 LLM_API_KEY 换成真实 Key 后重试。")
        return 1

    print(f"[信息] 预检地址：{cfg['base_url']}（Key: {mask_secret(cfg['api_key'])}）")
    session = make_session()
    ok = True

    try:
        resp = api_request(session, cfg, "GET", MODELS_PATH)
        models = [
            m.get("id") for m in (resp_json(resp).get("data") or []) if isinstance(m, dict)
        ]
        print(f"[成功] Key 有效，当前可用模型：{', '.join(models) or '（接口未返回模型列表）'}")
        if models and cfg["model"] not in models:
            print(f"[警告] LLM_MODEL={cfg['model']} 不在可用模型列表中，请修改 .env。")
    except LLMError as exc:
        ok = False
        print(f"[失败] /models 校验未通过：{exc}")

    try:
        data = resp_json(api_request(session, cfg, "GET", BALANCE_PATH))
        print(f"[成功] 余额状态 is_available={data.get('is_available')}")
        for info in data.get("balance_infos") or []:
            print(
                f"        - {info.get('currency')}: 总额 {info.get('total_balance')}"
                f"（充值 {info.get('topped_up_balance')} / 赠送 {info.get('granted_balance')}）"
            )
    except LLMError as exc:
        # 余额接口对部分账号不可用，仅提示，不影响主流程
        print(f"[提示] 余额查询未成功（不影响主流程）：{exc}")

    return 0 if ok else 1
# ---------------------------------------------------------------------------
# 命令行与主流程
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="用 DeepSeek（OpenAI 兼容格式）为 raw_emails.txt 中的客户询盘生成英文回复草稿。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python email_reply_drafter_llm.py --check\n"
            "  python email_reply_drafter_llm.py --limit 1 --dry-run\n"
            "  python email_reply_drafter_llm.py --limit 1 --tone friendly\n"
            "\n配置全部来自同目录 .env（模板见 .env.example）。\n"
        ),
    )
    parser.add_argument("--check", action="store_true", help="只校验 API Key 与余额，不消耗 token")
    parser.add_argument("--dry-run", action="store_true", help="完全不联网，输出离线正则草稿")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 封邮件（0 = 全部）")
    parser.add_argument("--out", default=None, help="输出文件名（默认取 .env 的 LLM_DRAFT_FILE）")
    parser.add_argument("--model", default=None, help="覆盖 .env 里的 LLM_MODEL")
    parser.add_argument(
        "--tone", choices=sorted(TONE_STYLES), default=None, help="回复语气（默认 formal）"
    )
    parser.add_argument(
        "--thinking", action="store_true", help="开启思考模式（默认关闭：更快、更省钱）"
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = load_config()

    if args.model:
        cfg["model"] = args.model
    if args.out:
        cfg["draft_file"] = args.out
    if args.tone:
        cfg["tone"] = args.tone
    cfg["thinking"] = bool(args.thinking)

    if args.check:
        return run_check(cfg)

    offline_only = args.dry_run or is_placeholder(cfg["api_key"])
    reason = "--dry-run 指定" if args.dry_run else "未配置有效 API Key"
    if offline_only:
        print(f"[信息] 离线模式（{reason}）：本次不会调用任何网络接口。")
        print(f"        如需 LLM 草稿，请在 {ENV_FILE} 填写 LLM_API_KEY。")
    else:
        print(
            f"[信息] LLM 模式：model={cfg['model']} | base_url={cfg['base_url']}"
            f" | tone={cfg['tone']} | thinking={'on' if cfg['thinking'] else 'off'}"
            f" | Key={mask_secret(cfg['api_key'])}"
        )

    created = ensure_raw_file(RAW_FILE)
    if created:
        print(f"[信息] 未找到 {RAW_FILE}，已自动生成包含 3 封英文询盘邮件的假数据文件。")
    else:
        print(f"[信息] 已找到现有文件 {RAW_FILE}，直接读取。")

    with open(RAW_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    emails = split_emails(content)
    if args.limit and args.limit > 0:
        emails = emails[: args.limit]
    print(f"[信息] 共解析到 {len(emails)} 封邮件。")

    session = None if offline_only else make_session()
    drafts = [
        "客户询盘回复草稿 - LLM 版 (Reply Drafts, LLM edition)\n"
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"来源文件: {RAW_FILE}\n"
        f"邮件数量: {len(emails)}\n"
        f"生成方式: {'离线正则规则（未调用 LLM）' if offline_only else 'DeepSeek ' + cfg['model']}\n"
        f"回复语气: {cfg['tone']}\n"
    ]

    ok_count = fallback_count = 0
    total_prompt = total_completion = 0

    for i, raw in enumerate(emails, start=1):
        email = parse_email(raw)
        req = extract_requirements(email)
        offline_draft = build_draft(i, email, req)
        llm_text = None

        if offline_only:
            status = f"离线草稿（原因：{reason}）"
        else:
            print(f"[{i}/{len(emails)}] 调用 {cfg['model']} 生成回复：{email['subject'][:60]}")
            try:
                llm_text, usage, elapsed = api_chat(
                    session, cfg, build_messages(email, req, cfg["tone"])
                )
                status = (
                    f"LLM: {cfg['model']} | 用时 {elapsed:.1f}s"
                    f" | tokens 输入 {usage.get('prompt_tokens', '?')}"
                    f" / 输出 {usage.get('completion_tokens', '?')}"
                )
                total_prompt += int(usage.get("prompt_tokens") or 0)
                total_completion += int(usage.get("completion_tokens") or 0)
            except LLMError as exc:
                print(f"    [回退] {exc}")
                status = f"离线草稿（LLM 调用失败：{exc}）"

        if llm_text:
            ok_count += 1
            body = replace_reply_section(offline_draft, llm_text)
        else:
            fallback_count += 1
            body = offline_draft

        drafts.append(f"处理状态: {status}\n{body}")

    out_path = cfg["draft_file"]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(drafts))

    print()
    print(f"[完成] 已生成草稿文件: {out_path}")
    print(f"[完成] 文件路径: {os.path.abspath(out_path)}")
    if not offline_only:
        print(
            f"[统计] LLM 成功 {ok_count} 封 / 回退 {fallback_count} 封"
            f" | 累计 tokens: 输入 {total_prompt} / 输出 {total_completion}"
        )
        if ok_count == 0:
            print("[警告] 所有邮件都回退了，请用 --check 排查 Key / 余额 / 网络。")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())