"""外贸询盘助手 —— 核心逻辑（不依赖 Streamlit，可以单独运行测试）。

这个文件负责两件事：
1. analyze()        ：从客户询盘邮件里提取关键需求（产品、数量、规格、认证、目的地…）；
2. generate_reply() ：根据提取结果生成一封地道的英文回复草稿。

为什么单独放一个文件？
- app.py（Streamlit 网页）只负责界面，逻辑放这里方便你用 `python inquiry_core.py`
  直接看到解析结果，界面出问题时也能单独调试；
- 你原来跑通的命令行脚本可以无缝接进来：设置环境变量 INQUIRY_SCRIPT_PATH
  指向你的脚本文件即可。只要它提供 extract_requirements(text)（必需）和
  generate_reply(text)（可选）两个函数，本模块会优先使用你的脚本；
  你的脚本报错或没提供函数时，会自动退回下面的内置规则，网页不会崩。
"""

from __future__ import annotations

import importlib.util
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------- 数据模型


@dataclass
class Requirement:
    """一条提取出来的需求。"""

    field: str     # 需求项名称（中文，给商务同事看）
    value: str     # 提取到的内容
    evidence: str  # 原文依据，便于人工核对

    def as_row(self) -> dict[str, str]:
        return {"需求项": self.field, "内容": self.value, "原文依据": self.evidence}


@dataclass
class InquiryAnalysis:
    """一封询盘的完整解析结果。"""

    raw_text: str
    requirements: list[Requirement] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    is_urgent: bool = False
    source: str = "内置规则"  # "内置规则" 或 "你的脚本"

    def to_rows(self) -> list[dict[str, str]]:
        return [r.as_row() for r in self.requirements]

    def value_of(self, field_name: str) -> str:
        for item in self.requirements:
            if item.field == field_name:
                return item.value
        return ""


# ---------------------------------------------------------------- 字段名常量

FIELD_PRODUCT = "产品/型号"
FIELD_QTY = "数量"
FIELD_SPEC = "规格要求"
FIELD_PRICE = "目标价格"
FIELD_LEAD_TIME = "交期要求"
FIELD_DEST = "目的地/港口"
FIELD_PAYMENT = "付款方式"
FIELD_CERT = "认证要求"
FIELD_INCOTERM = "贸易术语"
FIELD_MOQ = "MOQ"
FIELD_REQUEST = "客户诉求"
FIELD_CONTACT = "客户称呼"

# 用于"缺失信息"检查和回复里反问客户的问句（中英对照）
_MISSING_EN: dict[str, str] = {
    FIELD_PRODUCT: "the exact product name or model number you are interested in",
    FIELD_QTY: "the quantity you need (for example a trial order or a full container load)",
    FIELD_SPEC: "the detailed specifications (size, material, power/voltage, colour, etc.)",
    FIELD_CERT: "the certificates you require (e.g. CE, RoHS, FCC, UL)",
    FIELD_DEST: "your destination port so that we can include the freight in our quotation",
    FIELD_PRICE: "your target price or acceptable price range",
    FIELD_LEAD_TIME: "your required delivery time",
    FIELD_PAYMENT: "your preferred payment terms",
}
_MISSING_ORDER = [
    FIELD_PRODUCT, FIELD_QTY, FIELD_SPEC, FIELD_CERT,
    FIELD_DEST, FIELD_PRICE, FIELD_LEAD_TIME, FIELD_PAYMENT,
]

# 回复草稿里用的英文字段名
_FIELD_EN: dict[str, str] = {
    FIELD_PRODUCT: "Product / model",
    FIELD_QTY: "Quantity",
    FIELD_SPEC: "Specifications",
    FIELD_CERT: "Certificates required",
    FIELD_DEST: "Destination / port",
    FIELD_PRICE: "Target price",
    FIELD_LEAD_TIME: "Required delivery time",
    FIELD_PAYMENT: "Payment terms",
    FIELD_INCOTERM: "Trade term",
    FIELD_REQUEST: "Requested documents / services",
}

# 回复草稿里用的英文"客户诉求"标签
_REQUEST_EN: dict[str, str] = {
    "报价/价格": "price / quotation",
    "产品目录": "product catalogue",
    "样品": "sample",
    "MOQ": "MOQ",
    "交期/生产周期": "lead time",
    "付款方式": "payment terms",
    "认证/检测报告": "certificates / test reports",
    "OEM/ODM 贴牌": "OEM / ODM service",
    "包装要求": "packaging requirement",
}

# 你自己的脚本若用英文/别的字段名，这里做一次归一化，
# 好让"缺失信息"的判断在接入你的脚本后依然生效
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    FIELD_PRODUCT: ("product", "product/model", "item", "commodity", "model", "产品", "产品/型号", "产品名称"),
    FIELD_QTY: ("quantity", "qty", "order quantity", "数量"),
    FIELD_SPEC: ("spec", "specs", "specification", "specifications", "requirement", "requirements", "规格", "规格要求"),
    FIELD_PRICE: ("target price", "price", "budget", "目标价", "目标价格"),
    FIELD_LEAD_TIME: ("lead time", "delivery time", "delivery", "交期", "交期要求"),
    FIELD_DEST: ("destination", "port", "destination port", "目的地", "目的地/港口"),
    FIELD_PAYMENT: ("payment", "payment terms", "付款方式"),
    FIELD_CERT: ("certificate", "certificates", "certification", "certifications", "认证", "认证要求"),
    FIELD_INCOTERM: ("incoterm", "incoterms", "trade term", "贸易术语"),
    FIELD_REQUEST: ("request", "requests", "customer request", "客户诉求"),
    FIELD_CONTACT: ("contact", "contact name", "name", "客户称呼"),
}

# ---------------------------------------------------------------- 词表 / 正则

# 产品：优先识别"我们在找 / 询价 xxx"这类句式
_PRODUCT_PATTERNS = [
    r"(?:we\s+(?:are|'re)?\s*(?:currently\s+|now\s+)?(?:looking\s+for|interested\s+in|sourcing|importing|buying|in\s+need\s+of))\s+(?P<v>[^\n\.;!?]{3,80})",
    r"(?:inquir(?:y|ies)|enquir(?:y|ies)|rfq|quotation|quote)\s+(?:for|about|on|of)\s+(?P<v>[^\n\.;!?]{3,80})",
    r"(?:product|item|model|part\s*(?:number|no)|commodity|goods)\s*[:\-]\s*(?P<v>[^\n]{2,80})",
    r"(?:need|require|want)\s+to\s+(?:buy|order|import|purchase)\s+(?P<v>[^\n\.;!?]{3,80})",
]

_QTY_RE = re.compile(
    r"(?P<num>\d[\d,\.]*)\s*(?P<unit>pcs|pieces?|units?|sets?|kgs?|kilograms?|tons?|tonnes?|mt|"
    r"meters?|metres?|m2|sqm|cbm|containers?|pallets?|cartons?|bags?|rolls?|pairs?|boxes?|drums?|20gp|40gp|40hq)",
    re.IGNORECASE,
)

_SPEC_RE = re.compile(
    r"\b(?P<k>specifications?|spec|dimensions?|material|colours?|colors?|thickness|width|length|height|"
    r"voltage|power|wattage|capacity|grade|surface|packaging|packing|weight|diameter|output|frequency|"
    r"application|models?|sizes?)\b\s*[:\-]?\s*(?P<v>[^\n;,\.]{1,40})",
    re.IGNORECASE,
)

# 单独出现的硬性参数，例如 IP65、150W、4000K
_TECH_TOKEN_RE = re.compile(
    r"\b(?:IP\d{2}|IK\d{2}|\d{4}K|\d+(?:\.\d+)?\s?(?:W|V|A|mA|Ah|Hz|kHz|mm|cm|kg|lm|LM))\b"
)

# 金额：USD 28 / 28 USD / $28
_PRICE_BEFORE_RE = re.compile(
    r"(?P<cur>USD|EUR|CNY|RMB|GBP|JPY|AUD|CAD|US\$|\$|€|¥)\s*(?P<num>\d[\d,]*(?:\.\d+)?)", re.IGNORECASE
)
_PRICE_AFTER_RE = re.compile(
    r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<cur>USD|EUR|CNY|RMB|GBP|JPY|AUD|CAD|dollars?|euros?|yuan)", re.IGNORECASE
)

_LEAD_TIME_RE = re.compile(
    r"(?P<v>(?:\d+\s*(?:-|to|–)\s*\d+\s*)?\d+\s*(?:working\s+)?(?:days?|weeks?|months?))", re.IGNORECASE
)

_INCOTERM_RE = re.compile(
    r"\b(?P<code>EXW|FCA|FAS|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP)"
    r"(?:\s+(?P<port>[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,1}))?"
)

_CERT_RE = re.compile(
    r"(?P<v>\bCE\b|\bRoHS\b|\bROHS\b|\bRoHs\b|\bREACH\b|\bFCC\b|\bUL\b|\bETL\b|\bcUL\b|\bGS\b|\bCB\b|"
    r"\bFDA\b|\bSGS\b|\bTUV\b|\bTÜV\b|\bISO\s?9001\b|\bISO\s?14001\b|\bBSCI\b|\bSASO\b|\bSONCAP\b|"
    r"\bCCC\b|\bPSE\b|\bKC\b|\bENEC\b|\bEMC\b|\bLVD\b)"
)

_MOQ_RE = re.compile(r"(?:moq|minimum\s+order(?:\s+quantity)?)\s*[:\-]?\s*(?P<v>\d[\d,]*\s*\w{0,12})", re.IGNORECASE)

_DEST_RE = re.compile(
    r"(?:deliver(?:y|ed)?|ship(?:ment|ped)?|send|destinations?|port\s+of\s+discharge|final\s+destination)"
    r"[^\.\n]{0,40}?(?:to|:|=|is|will\s+be)\s+"
    r"(?P<v>[A-Za-z][A-Za-z \-]{1,30}?(?:\s+port)?)"
    r"(?=\s*$|\s*(?:within|by|before|in\s+\d|[\.\,\;\n]))",
    re.IGNORECASE | re.MULTILINE,
)

# 付款方式：命中就把中文标签塞进结果
_PAYMENT_PATTERNS: list[tuple[str, str]] = [
    ("T/T 电汇", r"\bt\s*/\s*t\b|telegraphic\s+transfer|wire\s+transfer|bank\s+transfer"),
    ("L/C 信用证", r"\bl\s*/\s*c\b|\blc\b|letter\s+of\s+credit"),
    ("D/P 付款交单", r"\bd\s*/\s*p\b|documents\s+against\s+payment"),
    ("D/A 承兑交单", r"\bd\s*/\s*a\b|documents\s+against\s+acceptance"),
    ("O/A 赊销", r"\bo\s*/\s*a\b|open\s+account"),
    ("PayPal", r"paypal"),
    ("西联汇款", r"western\s+union"),
    ("30% 定金 + 70% 尾款", r"30\s*%\s*(?:deposit|t/?t)[^\n]{0,60}?(?:70\s*%|balance)"),
]

# 客户在邮件里向我们"要什么"：回复里对应回答，避免反过来又问客户
_REQUEST_PATTERNS: list[tuple[str, str]] = [
    ("报价/价格", r"\b(?:prices?|quotations?|quotes?|pricing|cost|offer)\b"),
    ("产品目录", r"\b(?:catalogues?|catalogs?|brochures?|product\s+list)\b"),
    ("样品", r"\bsamples?\b"),
    ("MOQ", r"\bmoq\b|minimum\s+order"),
    ("交期/生产周期", r"\blead\s*time\b|delivery\s+time|production\s+time"),
    ("付款方式", r"\bpayment\s+(?:terms?|method)\b|how\s+to\s+pay\b"),
    ("认证/检测报告", r"\b(?:certificates?|certifications?|test\s+reports?|inspection)\b"),
    ("OEM/ODM 贴牌", r"\b(?:oem|odm|logo|private\s+label|branding)\b"),
    ("包装要求", r"\b(?:packaging|packing|cartons?|pallets?)\b"),
]

_URGENT_RE = re.compile(
    r"\b(?:urgent|urgency|asap|as\s+soon\s+as\s+possible|immediately|at\s+your\s+earliest)\b", re.IGNORECASE
)

_CONTACT_PATTERNS = [
    r"(?:my\s+name\s+is|this\s+is|i\s+am|i'm)\s+(?P<v>[A-Z][a-zA-Z]{1,20})\b",
    r"^dear\s+(?P<v>[A-Z][a-zA-Z]{1,20})\b",
    r"(?:best\s+regards|kind\s+regards|sincerely|regards)[,\s]*\n\s*(?P<v>[A-Z][a-zA-Z]{1,20})\b",
]

_NOISE_WORDS = {
    "n/a", "none", "unknown", "tbd", "information", "details", "detail",
    "requirement", "requirements", "list", "please", "us", "you", "me", "it", "them", "price",
}
# "Specifications:" 这类只是标题，不算一条具体规格
_SPEC_HEADER_KEYS = {"spec", "specification", "requirement"}
_STOP_WORDS = re.compile(
    r"^(?:is|are|was|were|do|does|did|can|could|would|will|shall|should|what|which|how|"
    r"please|thanks|thank|and|or|the|a|an|of|to|for|your|our|we|i)\b",
    re.IGNORECASE,
)

# 内置示例询盘：网页上点"载入示例"就能直接试跑
SAMPLE_EMAIL = """\
Subject: Inquiry for 5,000 pcs LED High Bay Light - urgent

Dear Sales Team,

My name is Michael and I am the purchasing manager of Brightline Trading in Germany.

We are looking for 5,000 pcs LED high bay light for our new warehouse project.
Specifications: power 150W, voltage 220-240V, color 4000K, IP65, material die-cast aluminium.
Please quote us your best price FOB Shenzhen, and let us know your MOQ, lead time and payment terms.
We also need CE and RoHS certificates, and please send us your product catalogue and a sample.
Our target price is around USD 28 per unit and we need the goods delivered to Hamburg port within 30 days.

Looking forward to your quotation.

Best regards,
Michael Braun
Brightline Trading GmbH
"""


# ---------------------------------------------------------------- 小工具


def _clean_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", (text or "").replace("\r\n", "\n").replace("\r", "\n")).strip()


def _evidence(text: str, match: re.Match[str], window: int = 25) -> str:
    """截取匹配位置附近的一小段原文，方便人工核对。"""
    start = max(0, match.start() - window)
    end = min(len(text), match.end() + window)
    snippet = text[start:end].replace("\n", " ").strip()
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{snippet}{suffix}"


def _is_noise(value: str) -> bool:
    value = value.strip(" .,;:?!-*")
    if len(value) < 2 or "?" in value:
        return True
    if _STOP_WORDS.match(value):
        return True
    return value.lower() in _NOISE_WORDS


def _find_first(text: str, patterns: list[str], *, transform=None) -> tuple[str, str] | None:
    """返回第一个匹配到的 (值, 原文依据)。"""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if not match or not match.group("v"):
            continue
        value = match.group("v").strip(" .,;:-\t")
        if transform is not None:
            value = transform(value)
        value = value.strip(" .,;:-")
        if value and not _is_noise(value):
            return value, _evidence(text, match)
    return None


def _find_all(text: str, pattern: re.Pattern[str], *, limit: int = 6) -> tuple[list[str], str]:
    """找出所有匹配值（去重、限量），并汇总原文依据。"""
    values: list[str] = []
    evidences: list[str] = []
    for match in pattern.finditer(text):
        value = match.group("v").strip(" .,;:-")
        if value and value not in values and not _is_noise(value):
            values.append(value)
            evidences.append(_evidence(text, match))
        if len(values) >= limit:
            break
    return values, " | ".join(evidences)


def _clean_product(value: str) -> str:
    """去掉产品名里混进来的数量、冠词、用途说明。"""
    value = re.sub(r"^\d[\d,\.]*\s*\w+\s+", "", value)  # 去掉开头的 "5,000 pcs "
    value = re.sub(r"^(?:the|some|any|new|a|an)\s+", "", value, flags=re.IGNORECASE)
    value = re.split(r"\s+for\s+(?:our|my|a|the)\b", value, flags=re.IGNORECASE)[0]
    return value.strip(" .,;:-")


def _find_specs(text: str) -> list[tuple[str, str, str]]:
    """提取 关键词+值 形式的规格，例如 power: 150W。"""
    # 先把 "Specifications:" 这类纯标题去掉，否则它会把后面的第一条规格一起吃掉
    text = re.sub(r"\b(?:specifications?|specs?|requirements?)\s*[:\-]\s*", "", text, flags=re.IGNORECASE)
    specs: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for match in _SPEC_RE.finditer(text):
        key = match.group("k").lower().rstrip("s")
        value = match.group("v").strip(" .,;:-")
        if key in seen or key in _SPEC_HEADER_KEYS or _is_noise(value):
            continue
        seen.add(key)
        specs.append((key, value, _evidence(text, match)))
        if len(specs) >= 8:
            break
    return specs


def _find_tech_tokens(text: str, spec_values: list[str]) -> list[tuple[str, str]]:
    """找出没有关键词但很重要的参数，例如 IP65。"""
    joined = " ".join(spec_values).lower().replace(" ", "")
    tokens: list[tuple[str, str]] = []
    for match in _TECH_TOKEN_RE.finditer(text):
        token = re.sub(r"\s+", "", match.group(0))
        if token.lower() in joined:
            continue
        if any(token == existing for existing, _ in tokens):
            continue
        tokens.append((token, _evidence(text, match)))
        if len(tokens) >= 6:
            break
    return tokens


def _find_payments(text: str) -> tuple[list[str], str]:
    labels: list[str] = []
    evidences: list[str] = []
    for label, pattern in _PAYMENT_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            labels.append(label)
            evidences.append(_evidence(text, match))
    return labels, " | ".join(evidences)


def _find_requests(text: str) -> list[str]:
    return [label for label, pattern in _REQUEST_PATTERNS if re.search(pattern, text, re.IGNORECASE)]


def _find_price(text: str) -> tuple[str, str] | None:
    match = _PRICE_BEFORE_RE.search(text)
    if match:
        return f"{match.group('cur').upper()} {match.group('num')}", _evidence(text, match)
    match = _PRICE_AFTER_RE.search(text)
    if match:
        return f"{match.group('num')} {match.group('cur').upper()}", _evidence(text, match)
    return None


def _find_incoterm(text: str) -> tuple[str, str] | None:
    match = _INCOTERM_RE.search(text)
    if not match:
        return None
    value = match.group("code")
    if match.group("port"):
        value = f"{value} {match.group('port')}"
    return value, _evidence(text, match)


# ---------------------------------------------------------------- 内置解析主流程


def _build_missing(found: dict[str, bool], requests: list[str]) -> list[str]:
    """检查哪些关键信息客户没给，供回复里反问。"""
    missing: list[str] = []
    for name in _MISSING_ORDER:
        if found.get(name):
            continue
        # 客户自己在邮件里问我们"付款方式 / 交期"，回复里就别反过来问他
        if name == FIELD_PAYMENT and "付款方式" in requests:
            continue
        if name == FIELD_LEAD_TIME and "交期/生产周期" in requests:
            continue
        missing.append(name)
    return missing


def _analyze_builtin(text: str) -> InquiryAnalysis:
    """内置规则解析（不依赖任何外部服务和大模型）。"""
    analysis = InquiryAnalysis(raw_text=text, source="内置规则")
    found: dict[str, bool] = {}

    product = _find_first(text, _PRODUCT_PATTERNS, transform=_clean_product)
    if product:
        analysis.requirements.append(Requirement(FIELD_PRODUCT, product[0], product[1]))
        found[FIELD_PRODUCT] = True

    qty = _QTY_RE.search(text)
    if qty:
        value = f"{qty.group('num')} {qty.group('unit').lower()}"
        analysis.requirements.append(Requirement(FIELD_QTY, value, _evidence(text, qty)))
        found[FIELD_QTY] = True

    specs = _find_specs(text)
    tech_tokens = _find_tech_tokens(text, [value for _, value, _ in specs])
    if specs or tech_tokens:
        spec_text = "；".join(f"{key}: {value}" for key, value, _ in specs)
        if tech_tokens:
            extra = "其他参数: " + ", ".join(token for token, _ in tech_tokens)
            spec_text = f"{spec_text}；{extra}" if spec_text else extra
        evidence = " | ".join([ev for _, _, ev in specs] + [ev for _, ev in tech_tokens])[:300]
        analysis.requirements.append(Requirement(FIELD_SPEC, spec_text, evidence))
        found[FIELD_SPEC] = True

    certs, cert_evidence = _find_all(text, _CERT_RE)
    if certs:
        analysis.requirements.append(Requirement(FIELD_CERT, " / ".join(certs), cert_evidence))
        found[FIELD_CERT] = True

    dest = _find_first(text, [_DEST_RE.pattern])
    if dest:
        analysis.requirements.append(Requirement(FIELD_DEST, dest[0], dest[1]))
        found[FIELD_DEST] = True

    price = _find_price(text)
    if price:
        analysis.requirements.append(Requirement(FIELD_PRICE, price[0], price[1]))
        found[FIELD_PRICE] = True

    lead_time = _LEAD_TIME_RE.search(text)
    if lead_time:
        analysis.requirements.append(Requirement(FIELD_LEAD_TIME, lead_time.group("v"), _evidence(text, lead_time)))
        found[FIELD_LEAD_TIME] = True

    payments, payment_evidence = _find_payments(text)
    if payments:
        analysis.requirements.append(Requirement(FIELD_PAYMENT, "、".join(payments), payment_evidence))
        found[FIELD_PAYMENT] = True

    incoterm = _find_incoterm(text)
    if incoterm:
        analysis.requirements.append(Requirement(FIELD_INCOTERM, incoterm[0], incoterm[1]))

    moq = _MOQ_RE.search(text)
    if moq:
        analysis.requirements.append(Requirement(FIELD_MOQ, moq.group("v").strip(), _evidence(text, moq)))

    requests = _find_requests(text)
    if requests:
        analysis.requirements.append(Requirement(FIELD_REQUEST, "、".join(requests), "邮件中的关键词命中"))

    contact = _find_first(text, _CONTACT_PATTERNS)
    if contact:
        analysis.requirements.append(Requirement(FIELD_CONTACT, contact[0], contact[1]))

    analysis.is_urgent = bool(_URGENT_RE.search(text))
    analysis.missing = _build_missing(found, requests)
    return analysis


def analyze(text: str, *, use_legacy: bool = True) -> InquiryAnalysis:
    """解析一封询盘邮件。

    use_legacy=True 时，如果接上了你自己的脚本（见文件末尾说明）就优先用它，
    它报错或没提供函数时自动退回内置规则。
    """
    text = _clean_text(text)
    if not text:
        return InquiryAnalysis(raw_text="", missing=list(_MISSING_ORDER), source="内置规则")
    if use_legacy:
        module = load_legacy_module()
        if module is not None:
            try:
                analysis = _analyze_with_legacy(module, text)
            except Exception:  # 你的脚本报错不能影响网页
                analysis = None
            if analysis is not None:
                return analysis
    return _analyze_builtin(text)


# ---------------------------------------------------------------- 英文回复草稿


def _value_for_reply(field_name: str, value: str) -> str:
    """把中文的提取结果转成适合放进英文邮件里的写法。"""
    if field_name == FIELD_REQUEST:
        parts = [part.strip() for part in value.split("、") if part.strip()]
        return ", ".join(_REQUEST_EN.get(part, part) for part in parts)
    if field_name == FIELD_SPEC:
        return value.replace("；", "; ").replace("其他参数", "other specs")
    return value


def _build_reply(
    analysis: InquiryAnalysis,
    *,
    company: str = "",
    sender: str = "",
    sign_off: str = "Best regards",
) -> str:
    """按模板生成英文回复草稿（纯规则，不调用 AI，稳定且不花钱）。"""
    product = analysis.value_of(FIELD_PRODUCT)
    contact = analysis.value_of(FIELD_CONTACT)
    subject = f"Re: Your inquiry about {product}" if product else "Re: Your inquiry"

    lines: list[str] = [f"Subject: {subject}", ""]
    lines.append(f"Dear {contact}," if contact else "Dear Sir or Madam,")
    lines.append("")
    lines.append(
        "Thank you very much for your inquiry and for your interest in our products. "
        "It is a pleasure to hear from you."
    )
    lines.append("")
    if analysis.is_urgent:
        lines.append(
            "We noticed that your inquiry is urgent, so we have marked it as a priority "
            "and our sales team will handle it first."
        )
        lines.append("")

    summary = [
        (_FIELD_EN[item.field], _value_for_reply(item.field, item.value))
        for item in analysis.requirements
        if item.field in _FIELD_EN
    ]
    if summary:
        lines.append("We have carefully reviewed your email and noted the following requirements:")
        lines.append("")
        lines.extend(f"- {label}: {value}" for label, value in summary)
        lines.append("")

    if analysis.missing:
        lines.append("To work out an exact quotation for you, could you please confirm the following points?")
        lines.append("")
        lines.extend(
            f"{index}. {_MISSING_EN.get(name, name)}"
            for index, name in enumerate(analysis.missing, start=1)
        )
        lines.append("")

    lines.append(
        "Once we have the above information, we will send you our best price together with the detailed "
        "specification, MOQ, production lead time, payment terms and packing details within one working day."
    )
    lines.append("")

    requested = analysis.value_of(FIELD_REQUEST)
    if "样品" in requested or "产品目录" in requested:
        lines.append(
            "As requested, we will also send you our latest catalogue, and we are happy to arrange "
            "a sample for your evaluation."
        )
        lines.append("")

    lines.append(
        "If you have any questions in the meantime, please feel free to contact me directly. "
        "We look forward to your reply and to a long-term cooperation with you."
    )
    lines.append("")
    lines.append(f"{sign_off},")
    lines.append(sender or "[Your Name]")
    lines.append(company or "[Your Company]")
    return "\n".join(lines)


def generate_reply(
    analysis: InquiryAnalysis,
    *,
    company: str = "",
    sender: str = "",
    sign_off: str = "Best regards",
    use_legacy: bool = True,
) -> str:
    """生成英文回复草稿；接上了你自己的脚本时，优先用它的 generate_reply()。"""
    if use_legacy:
        module = load_legacy_module()
        generator = getattr(module, "generate_reply", None) if module is not None else None
        if callable(generator):
            # 依次尝试 generate_reply(text, analysis) 与 generate_reply(text) 两种签名
            for args in ((analysis.raw_text, analysis), (analysis.raw_text,)):
                try:
                    draft = generator(*args)
                except TypeError:
                    continue
                except Exception:  # 你的脚本报错就退回内置模板
                    break
                if isinstance(draft, str) and draft.strip():
                    return draft
    return _build_reply(analysis, company=company, sender=sender, sign_off=sign_off)


# ---------------------------------------------------------------- 接入你自己的脚本
# 用法（不用改任何代码）：
#   1) 把你的询盘脚本放好，例如 D:\work\my_inquiry.py；
#   2) 启动网页前设置环境变量：
#        PowerShell : $env:INQUIRY_SCRIPT_PATH="D:\work\my_inquiry.py"
#        CMD        : set INQUIRY_SCRIPT_PATH=D:\work\my_inquiry.py
#   3) 你的脚本里只要提供下面任意一个函数即可：
#        def extract_requirements(text) -> list     # 必需
#            # 每项可以是 dict，键名支持 field/需求项/name/key 与 value/内容/result/text，
#            # 也可以直接返回字符串列表
#        def generate_reply(text) 或 generate_reply(text, analysis) -> str   # 可选
#   提示：加载时会执行脚本文件顶层的代码，所以别在顶层写 input() 之类会卡住的交互。

LEGACY_PATH_ENV = "INQUIRY_SCRIPT_PATH"
_LEGACY_FILENAMES = ("inquiry_script.py", "main.py", "app_core.py", "script.py")


@lru_cache(maxsize=1)
def load_legacy_module():
    """按环境变量 INQUIRY_SCRIPT_PATH 加载你自己的脚本；加载失败返回 None。"""
    raw_path = os.getenv(LEGACY_PATH_ENV, "").strip().strip('"').strip("'")
    if not raw_path:
        return None
    script_path = Path(raw_path).expanduser()
    if script_path.is_dir():
        for name in _LEGACY_FILENAMES:
            if (script_path / name).is_file():
                script_path = script_path / name
                break
    if not script_path.is_file() or script_path.suffix.lower() != ".py":
        return None
    try:
        spec = importlib.util.spec_from_file_location("legacy_inquiry_script", script_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def legacy_status() -> str:
    """给网页显示用：接上了返回脚本路径，没接上返回空字符串。"""
    module = load_legacy_module()
    if module is None:
        return ""
    return str(getattr(module, "__file__", "你的脚本"))


def reload_legacy_module() -> None:
    """改完自己的脚本后清缓存，下次解析会重新加载。"""
    load_legacy_module.cache_clear()


def _map_field_name(name: Any) -> str:
    """把你脚本里的字段名（中英文都行）归一化成这里统一的中文字段名。"""
    key = str(name).strip().lower()
    for canonical, aliases in _FIELD_ALIASES.items():
        if key == canonical.lower() or key in aliases:
            return canonical
    return str(name).strip() or "其他信息"


def _coerce_requirements(raw: Any) -> list[Requirement]:
    """把你脚本返回的任意结构，尽量转成 Requirement 列表。"""
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    items: list[Requirement] = []
    for item in raw:
        if isinstance(item, Requirement):
            items.append(item)
        elif isinstance(item, dict):
            field_name = item.get("field") or item.get("需求项") or item.get("name") or item.get("key") or "其他信息"
            value = item.get("value") or item.get("内容") or item.get("result") or item.get("text") or ""
            evidence = item.get("evidence") or item.get("原文依据") or item.get("source") or ""
            if str(value).strip():
                items.append(
                    Requirement(_map_field_name(field_name), str(value).strip(), str(evidence).strip())
                )
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            items.append(Requirement(_map_field_name(item[0]), str(item[1]).strip(), ""))
        elif isinstance(item, str) and item.strip():
            items.append(Requirement("其他信息", item.strip(), ""))
    return items


def _analyze_with_legacy(module: Any, text: str) -> InquiryAnalysis | None:
    """用你自己的脚本解析；它没提供可用函数时返回 None（调用方会退回内置规则）。"""
    extractor = getattr(module, "extract_requirements", None) or getattr(module, "extract_inquiry", None)
    if not callable(extractor):
        return None
    requirements = _coerce_requirements(extractor(text))
    if not requirements:
        return None
    present = {item.field for item in requirements}
    return InquiryAnalysis(
        raw_text=text,
        requirements=requirements,
        missing=[name for name in _MISSING_ORDER if name not in present],
        is_urgent=bool(_URGENT_RE.search(text)),
        source="你的脚本",
    )


if __name__ == "__main__":
    # 不用开网页也能验证逻辑：python inquiry_core.py
    demo = analyze(SAMPLE_EMAIL, use_legacy=False)
    print("=" * 70)
    print("提取到的需求：")
    for row in demo.to_rows():
        print(f"  · {row['需求项']}：{row['内容']}")
        print(f"      依据：{row['原文依据']}")
    print(f"缺少的信息：{'、'.join(demo.missing) if demo.missing else '无'}")
    print(f"是否紧急：{'是' if demo.is_urgent else '否'}")
    print("=" * 70)
    print(generate_reply(demo, company="ABC Industrial Co., Ltd.", sender="Lily Chen", use_legacy=False))
