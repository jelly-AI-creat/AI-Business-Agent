#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
email_reply_drafter.py

自动读取当前目录下的 raw_emails.txt 文件：
  - 如果文件不存在，则生成一个包含 3 封英文客户询盘邮件的假数据文件。
  - 提取每封邮件的客户需求（产品、数量、价格、交期、联系方式等）。
  - 生成格式清晰的 reply_drafts.txt 草稿文件。
"""

import os
import re
from datetime import datetime

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
RAW_FILE = "raw_emails.txt"
DRAFT_FILE = "reply_drafts.txt"

# 用于生成假数据的 3 封英文客户询盘邮件
FAKE_EMAILS = """\
From: john.smith@abctrading.com
To: sales@yourcompany.com
Subject: Inquiry about Wireless Bluetooth Headphones - Bulk Order

Dear Sales Team,

My name is John Smith, Purchasing Manager at ABC Trading Co. based in New York, USA.

We are interested in your Wireless Bluetooth Headphones (Model: WBH-200). We would
like to place an initial order of 500 units for a trial run. Could you please provide
your best FOB price and the estimated lead time for delivery to New York?

We also need to know the minimum order quantity (MOQ) and whether you can customize
the packaging with our company logo.

Looking forward to your quotation.

Best regards,
John Smith
Purchasing Manager, ABC Trading Co.
Email: john.smith@abctrading.com
Phone: +1-212-555-0147

================================================================================

From: maria.garcia@eurotech.es
To: sales@yourcompany.com
Subject: Request for Quotation - Solar Power Banks

Hello,

This is Maria Garcia from EuroTech Solutions in Madrid, Spain.

We are looking for a reliable supplier of Solar Power Banks (20000mAh). Our target
quantity is 2,000 units per month on a recurring basis. Please send us your unit price
for both 2,000 and 5,000 units, along with your payment terms.

We require CE certification for the European market. Please confirm if your products
are CE certified and provide the relevant documents.

Our required delivery date is within 30 days of order confirmation.

Thank you,
Maria Garcia
Procurement Specialist, EuroTech Solutions
Email: maria.garcia@eurotech.es
Phone: +34-91-555-0198

================================================================================

From: david.lee@smartelectronics.sg
To: sales@yourcompany.com
Subject: Urgent Inquiry - USB-C Charging Cables

Dear Sir/Madam,

I am David Lee, the founder of Smart Electronics Pte Ltd in Singapore.

We urgently need USB-C Charging Cables (2 meters, braided nylon). We are planning to
order 10,000 units. Please quote your best price including shipping to Singapore
(CIF Singapore).

We would also like to request samples before placing the bulk order. Can you send
3 samples to our address? We will cover the sample cost and shipping.

Please reply as soon as possible as we need to finalize our supplier this week.

Regards,
David Lee
Founder, Smart Electronics Pte Ltd
Email: david.lee@smartelectronics.sg
Phone: +65-6555-0123
"""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def ensure_raw_file(path: str) -> bool:
    """确保 raw_emails.txt 存在。若不存在则生成假数据。

    返回 True 表示文件是本次新建的，False 表示文件已存在。
    """
    if os.path.exists(path):
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(FAKE_EMAILS)
    return True


def split_emails(text: str):
    """按分隔线把原始文本拆分成多封邮件。"""
    # 使用连续 3 个以上 '=' 作为分隔符
    parts = re.split(r"\n={3,}\n", text)
    return [p.strip() for p in parts if p.strip()]


def parse_email(raw: str) -> dict:
    """解析单封邮件，提取头部字段和正文。"""
    lines = raw.splitlines()
    headers = {}
    body_start = 0

    for i, line in enumerate(lines):
        if not line.strip():
            body_start = i + 1
            break
        m = re.match(r"^(From|To|Subject):\s*(.*)$", line, re.IGNORECASE)
        if m:
            headers[m.group(1).lower()] = m.group(2).strip()

    body = "\n".join(lines[body_start:]).strip()
    return {
        "from": headers.get("from", "Unknown"),
        "to": headers.get("to", "Unknown"),
        "subject": headers.get("subject", "(No Subject)"),
        "body": body,
    }


def extract_requirements(email: dict) -> dict:
    """从邮件正文中提取客户需求的关键信息。"""
    body = email["body"]
    text = body.replace("\n", " ")

    req = {
        "product": None,
        "quantity": None,
        "price_request": None,
        "lead_time": None,
        "certification": None,
        "samples": None,
        "contact_name": None,
        "contact_email": None,
        "contact_phone": None,
        "company": None,
        "notes": [],
    }

    # 产品：优先匹配括号中的型号，其次匹配 "your X" / "need X" 等
    model = re.search(r"\(Model:\s*([^)]+)\)", text, re.IGNORECASE)
    if model:
        req["product"] = model.group(1).strip()
    else:
        # 优先匹配 "your <Product>" 或 "need <Product>"，避免误匹配公司名
        prod = re.search(
            r"(?:your|need|looking for a reliable supplier of)\s+"
            r"([A-Z][A-Za-z0-9\-\s]{3,40}?)(?:\s*\(|\.|,| for| with|$)",
            text,
        )
        if prod:
            req["product"] = prod.group(1).strip()
        else:
            # 兜底：匹配 "of <Product>"，但排除公司名后缀
            prod = re.search(
                r"\bof\s+([A-Z][A-Za-z0-9\-\s]{3,40}?)(?:\s*\(|\.|,| for| with|$)",
                text,
            )
            if prod and not re.search(
                r"(Co\.|Ltd|Pte Ltd|Solutions|Trading|Inc\.|LLC)",
                prod.group(1),
            ):
                req["product"] = prod.group(1).strip()

    # 数量：匹配 "X units" / "X,XXX units"
    qty = re.search(r"([\d,]+)\s*(?:units|pieces|pcs)", text, re.IGNORECASE)
    if qty:
        req["quantity"] = qty.group(1).strip()

    # 价格请求
    if re.search(r"\b(price|quotation|quote|FOB|CIF)\b", text, re.IGNORECASE):
        price_bits = []
        if re.search(r"\bFOB\b", text, re.IGNORECASE):
            price_bits.append("FOB price")
        if re.search(r"\bCIF\b", text, re.IGNORECASE):
            price_bits.append("CIF price")
        if re.search(r"\bunit price\b", text, re.IGNORECASE):
            price_bits.append("unit price")
        if re.search(r"\bbest price\b", text, re.IGNORECASE):
            price_bits.append("best price")
        req["price_request"] = ", ".join(price_bits) if price_bits else "Price quotation"

    # 交期
    lead = re.search(
        r"(?:lead time|delivery date|delivery)[^.]*?(\d+\s*days?)",
        text,
        re.IGNORECASE,
    )
    if lead:
        req["lead_time"] = lead.group(1).strip()
    elif re.search(r"within\s+(\d+)\s+days", text, re.IGNORECASE):
        req["lead_time"] = re.search(
            r"within\s+(\d+)\s+days", text, re.IGNORECASE
        ).group(0)

    # 认证
    cert = re.search(r"\b(CE|FCC|RoHS|UL|ISO)\b", text)
    if cert:
        req["certification"] = cert.group(1).upper()

    # 样品
    if re.search(r"\bsamples?\b", text, re.IGNORECASE):
        req["samples"] = "Requested"

    # 联系人姓名
    name = re.search(
        r"(?:my name is|this is|I am)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)",
        text,
        re.IGNORECASE,
    )
    if name:
        req["contact_name"] = name.group(1).strip()

    # 邮箱
    mail = re.search(r"[\w.\-]+@[\w.\-]+\.\w+", text)
    if mail:
        req["contact_email"] = mail.group(0)

    # 电话
    phone = re.search(r"\+?\d[\d\-\s]{7,}\d", text)
    if phone:
        req["contact_phone"] = phone.group(0).strip()

    # 公司
    comp = re.search(
        r"(?:at|from|of)\s+([A-Z][A-Za-z0-9&.\- ]+(?:Co\.|Ltd|Pte Ltd|Solutions|Trading|Inc\.|LLC))",
        text,
    )
    if comp:
        req["company"] = comp.group(1).strip()

    # 其他备注
    if re.search(r"\bMOQ\b|minimum order quantity", text, re.IGNORECASE):
        req["notes"].append("询问最小起订量 (MOQ)")
    if re.search(r"customiz|logo", text, re.IGNORECASE):
        req["notes"].append("需要定制包装/Logo")
    if re.search(r"payment terms", text, re.IGNORECASE):
        req["notes"].append("询问付款条件")
    if re.search(r"urgent|as soon as possible|this week", text, re.IGNORECASE):
        req["notes"].append("紧急需求，需尽快回复")

    return req


def build_draft(index: int, email: dict, req: dict) -> str:
    """为单封邮件生成格式清晰的回复草稿。"""
    def val(x):
        return x if x else "（未提及）"

    lines = []
    lines.append("=" * 78)
    lines.append(f"邮件 #{index}")
    lines.append("=" * 78)
    lines.append(f"发件人 (From)   : {email['from']}")
    lines.append(f"收件人 (To)     : {email['to']}")
    lines.append(f"主题 (Subject)  : {email['subject']}")
    lines.append("")
    lines.append("【客户需求提取】")
    lines.append(f"  - 产品        : {val(req['product'])}")
    lines.append(f"  - 数量        : {val(req['quantity'])}")
    lines.append(f"  - 价格要求    : {val(req['price_request'])}")
    lines.append(f"  - 交期要求    : {val(req['lead_time'])}")
    lines.append(f"  - 认证要求    : {val(req['certification'])}")
    lines.append(f"  - 样品        : {val(req['samples'])}")
    lines.append(f"  - 客户公司    : {val(req['company'])}")
    lines.append(f"  - 联系人      : {val(req['contact_name'])}")
    lines.append(f"  - 邮箱        : {val(req['contact_email'])}")
    lines.append(f"  - 电话        : {val(req['contact_phone'])}")
    if req["notes"]:
        lines.append(f"  - 其他备注    : {'；'.join(req['notes'])}")
    lines.append("")
    lines.append("【回复草稿】")
    lines.append("")
    greeting_name = req["contact_name"] or "Sir/Madam"
    lines.append(f"Dear {greeting_name},")
    lines.append("")
    lines.append(
        "Thank you for your inquiry and for your interest in our products. "
        "We are pleased to hear from you."
    )
    lines.append("")
    if req["product"]:
        lines.append(
            f"Regarding your request for {req['product']}, we are glad to confirm "
            "that we can supply this item."
        )
    if req["quantity"]:
        lines.append(
            f"We have noted your required quantity of {req['quantity']} units and "
            "will prepare a competitive quotation accordingly."
        )
    if req["price_request"]:
        lines.append(
            f"We will provide our {req['price_request']} in the attached quotation."
        )
    if req["lead_time"]:
        lines.append(
            f"Concerning the delivery timeline ({req['lead_time']}), we will confirm "
            "the exact schedule once the order details are finalized."
        )
    if req["certification"]:
        lines.append(
            f"Our products are {req['certification']} certified, and we will send you "
            "the relevant certificates for your reference."
        )
    if req["samples"]:
        lines.append(
            "We are happy to arrange samples for your evaluation. Please confirm your "
            "shipping address so we can dispatch them promptly."
        )
    if req["notes"]:
        lines.append("")
        lines.append("Additional points we will address:")
        for note in req["notes"]:
            lines.append(f"  - {note}")
    lines.append("")
    lines.append(
        "Please feel free to contact us if you have any further questions. "
        "We look forward to building a long-term business relationship with you."
    )
    lines.append("")
    lines.append("Best regards,")
    lines.append("[Your Name]")
    lines.append("[Your Title]")
    lines.append("[Your Company]")
    lines.append("[Email] | [Phone]")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    created = ensure_raw_file(RAW_FILE)
    if created:
        print(f"[信息] 未找到 {RAW_FILE}，已自动生成包含 3 封英文询盘邮件的假数据文件。")
    else:
        print(f"[信息] 已找到现有文件 {RAW_FILE}，直接读取。")

    with open(RAW_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    emails = split_emails(content)
    print(f"[信息] 共解析到 {len(emails)} 封邮件。")

    drafts = []
    header = (
        "客户询盘回复草稿 (Reply Drafts)\n"
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"来源文件: {RAW_FILE}\n"
        f"邮件数量: {len(emails)}\n"
    )
    drafts.append(header)

    for i, raw in enumerate(emails, start=1):
        email = parse_email(raw)
        req = extract_requirements(email)
        drafts.append(build_draft(i, email, req))

    with open(DRAFT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(drafts))

    print(f"[完成] 已生成草稿文件: {DRAFT_FILE}")
    print(f"[完成] 文件路径: {os.path.abspath(DRAFT_FILE)}")


if __name__ == "__main__":
    main()
