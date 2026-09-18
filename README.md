# AI-Business-Agent

> 面向外贸与电商业务场景的 AI 自动化 Agent 集合
> A curated collection of AI automation agents for international trade & e-commerce workflows

[![Python](https://img.shields.io/badge/Python-3.6%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)](https://github.com/jelly-AI-creat/AI-Business-Agent)
[![Last Commit](https://img.shields.io/github/last-commit/jelly-AI-creat/AI-Business-Agent)](https://github.com/jelly-AI-creat/AI-Business-Agent/commits/main)

<p align="center">
  <a href="#cn">中文文档</a> · <a href="#en">English Documentation</a>
</p>

---

<a id="cn"></a>

## 🇨🇳 中文文档

### 📖 项目简介

`AI-Business-Agent` 是一个面向真实业务场景的 **AI 自动化 Agent 工作区（monorepo）**。仓库采用「一个子项目一个文件夹」的组织方式，把日常业务中最耗时、最重复的环节沉淀为**可独立运行、可独立演进**的自动化工具。

目前仓库包含 **1 个子项目**：[`AI_Email_Agent`](AI_Email_Agent/) —— 面向外贸场景的**客户询盘邮件解析与英文回复草稿生成器**。

### 🎯 设计原则

| 原则 | 说明 |
| --- | --- |
| **零依赖** Zero-dependency | 仅使用 Python 标准库，克隆即可运行，无需 `pip install` |
| **离线可用** Offline-ready | 不依赖任何外部 API，业务数据不出本机 |
| **结构可预期** Predictable | 输入 `raw_emails.txt` → 输出 `reply_drafts.txt`，文件即接口 |
| **易扩展** Extensible | 每个 Agent 独立成目录，新增 Agent 不影响已有项目 |

### 🗂 仓库结构

```text
AI-Business-Agent/
├── .gitignore                  # 全局忽略规则（.env、密钥、虚拟环境等）
├── README.md                   # 本文件（中英双语）
└── AI_Email_Agent/             # 子项目 1：客户询盘解析与回复草稿生成
    ├── email_reply_drafter.py  # 主程序（纯 Python 标准库实现）
    ├── raw_emails.txt          # 输入：原始客户询盘邮件（缺失时自动生成示例数据）
    └── reply_drafts.txt        # 输出：结构化需求提取 + 英文回复草稿
```

### 🧩 子项目一览

| 子项目 | 目录 | 技术栈 | 核心能力 | 状态 |
| --- | --- | --- | --- | --- |
| **AI Email Agent** | [`AI_Email_Agent/`](AI_Email_Agent/) | Python 3.6+ / 标准库 | 批量解析客户询盘邮件，提取产品、数量、价格、交期、认证等关键需求，并逐封生成英文回复草稿 | ✅ 可运行 |

> 各子项目相互独立，可单独复制到任意位置使用。

### 🚀 快速开始

**环境要求**：Python **3.6 或以上**（程序使用 f-string 语法），**无需安装任何第三方依赖**。

```bash
# 1. 克隆仓库
git clone https://github.com/jelly-AI-creat/AI-Business-Agent.git
cd AI-Business-Agent/AI_Email_Agent

# 2. 运行（脚本按"当前工作目录"读写文件，请在 AI_Email_Agent 目录下执行）
python email_reply_drafter.py

# 3. 查看结果
#    当前目录下已生成 reply_drafts.txt
```

首次运行时若 `raw_emails.txt` 不存在，程序会**自动生成一份包含 3 封英文询盘邮件的示例数据**，便于先跑通完整流程。

#### 使用自己的数据

把客户询盘邮件按以下格式写入 `AI_Email_Agent/raw_emails.txt`，**每封邮件之间用一行由 3 个及以上 `=` 组成的分隔线隔开**：

```text
From: customer@example.com
To: sales@yourcompany.com
Subject: Inquiry about ...

（邮件正文）

==============================================================================
（下一封邮件，格式同上）
```

### 🔍 AI Email Agent 工作原理

```text
raw_emails.txt
   │
   ├─ ① split_emails()          按 "===" 分隔线切分为 N 封独立邮件
   ├─ ② parse_email()           解析 From / To / Subject 头部与正文
   ├─ ③ extract_requirements()  以正则规则提取 11 个业务字段
   ├─ ④ build_draft()           逐封生成「需求摘要 + 英文回复草稿」
   └─ ⑤ main()                  写出 reply_drafts.txt（含生成时间、来源、邮件数量）
```

**需求提取字段一览**

| 字段 | 提取内容 | 典型触发示例 |
| --- | --- | --- |
| `product` | 产品 / 型号 | `(Model: WBH-200)`、`your Wireless Bluetooth Headphones` |
| `quantity` | 采购数量 | `500 units`、`10,000 pieces` |
| `price_request` | 价格类型 | `FOB price`、`CIF price`、`unit price`、`best price` |
| `lead_time` | 交期要求 | `lead time ... 30 days`、`within 30 days` |
| `certification` | 认证要求 | `CE`、`FCC`、`RoHS`、`UL`、`ISO` |
| `samples` | 样品需求 | `samples` / `sample` |
| `contact_name` | 联系人姓名 | `my name is John Smith`、`I am David Lee` |
| `contact_email` | 联系邮箱 | `john.smith@abctrading.com` |
| `contact_phone` | 联系电话 | `+1-212-555-0147` |
| `company` | 客户公司 | `ABC Trading Co.`、`Smart Electronics Pte Ltd` |
| `notes` | 其他备注 | `MOQ`、`customize / logo`、`payment terms`、`urgent` |

> **技术说明**：当前版本采用**确定性正则规则**做信息抽取，**不调用任何 AI 大模型 API** —— 因此完全离线、结果可复现、零调用成本。LLM 增强能力见下方「路线图」。

### 📄 输出示例

以下为运行后 `reply_drafts.txt` 的真实生成结果（节选，时间戳随运行时间变化）：

```text
客户询盘回复草稿 (Reply Drafts)
生成时间: <运行时的日期时间>
来源文件: raw_emails.txt
邮件数量: 3

==============================================================================
邮件 #1
==============================================================================
发件人 (From)   : john.smith@abctrading.com
收件人 (To)     : sales@yourcompany.com
主题 (Subject)  : Inquiry about Wireless Bluetooth Headphones - Bulk Order

【客户需求提取】
  - 产品        : WBH-200
  - 数量        : 500
  - 价格要求    : FOB price
  - 交期要求    : （未提及）
  - 认证要求    : （未提及）
  - 样品        : （未提及）
  - 客户公司    : ABC Trading Co.
  - 联系人      : John Smith
  - 邮箱        : john.smith@abctrading.com
  - 电话        : +1-212-555-0147
  - 其他备注    : 询问最小起订量 (MOQ)；需要定制包装/Logo

【回复草稿】

Dear John Smith,

Thank you for your inquiry and for your interest in our products. We are pleased to hear from you.

Regarding your request for WBH-200, we are glad to confirm that we can supply this item.
We have noted your required quantity of 500 units and will prepare a competitive quotation accordingly.
We will provide our FOB price in the attached quotation.

Additional points we will address:
  - 询问最小起订量 (MOQ)
  - 需要定制包装/Logo

Please feel free to contact us if you have any further questions. We look forward to building a long-term business relationship with you.

Best regards,
[Your Name]
[Your Title]
[Your Company]
[Email] | [Phone]
```

> 邮箱、电话、公司名等均为脚本内置的**虚构演示数据**。草稿末尾的 `[Your Name]`、`[Your Company]` 等为预留签名占位符，请替换为你的真实信息后再发送。

### 🔒 安全与隐私

- 仓库根目录的 `.gitignore` 已屏蔽 `.env`、`.env.*`、`*.env`、`*.key`、`*.pem`、`secrets.json`、`credentials.json` 等敏感文件 —— **在任意子目录新建 `.env` 都不会被提交**。
- 程序运行**全程不联网**、不调用任何外部 API，客户邮件内容只保留在本地文件中。
- 仓库中的示例邮件（发件人、公司、邮箱、电话）均为**虚构演示数据**，与任何真实客户无关。
- 提交前建议自查：`git status` 与 `git diff --cached`，确认未将真实客户数据或密钥带入版本库。

### 🗺 路线图

- [x] 询盘邮件的批量解析与字段化需求提取
- [x] 英文回复草稿自动生成（离线、零依赖）
- [ ] 接入 LLM（OpenAI / Claude 等），生成语气可配置的自然回复
- [ ] 多语言询盘支持（西班牙语 / 德语 / 日语等）
- [ ] IMAP / SMTP 直连，打通「收信 → 生成草稿 → 人工确认 → 发送」闭环
- [ ] 新增子项目：`AI_Sales_Agent`（报价单生成）、`AI_Data_Analyst`（业务数据报表）

### 🤝 贡献指南

1. Fork 本仓库，并从 `main` 切出特性分支：`git checkout -b feature/your-feature`
2. 新增子项目请遵循「一个目录一个 Agent」的约定，建议目录内附带独立 README
3. 提交前自检：`git status` 干净、无敏感文件、代码可直接运行
4. 提交信息建议遵循 Conventional Commits（如 `feat: ...`、`fix: ...`、`docs: ...`）
5. 发起 Pull Request，并在描述中说明变更动机与验证方式

### 📬 联系与反馈

- 仓库地址：https://github.com/jelly-AI-creat/AI-Business-Agent
- 作者 GitHub：[@jelly-AI-creat](https://github.com/jelly-AI-creat)
- 问题反馈：欢迎通过 [Issues](https://github.com/jelly-AI-creat/AI-Business-Agent/issues) 交流

### 📜 许可协议

本仓库**暂未声明开源许可证**（License: not specified）。如需商用或二次分发，请先联系作者获得授权。

---

<a id="en"></a>

## 🇬🇧 English Documentation

### 📖 Overview

`AI-Business-Agent` is a **monorepo workspace of AI automation agents** built for real business workflows. Each sub-project lives in its own folder, turning the most repetitive, time-consuming parts of day-to-day operations into tools that run and evolve **independently**.

The repository currently ships **one sub-project**: [`AI_Email_Agent`](AI_Email_Agent/) — a **customer inquiry parser that extracts purchase requirements and drafts English replies** for cross-border trade.

### 🎯 Design Principles

| Principle | Description |
| --- | --- |
| **Zero-dependency** | Built entirely on the Python standard library — clone and run, no `pip install` required |
| **Offline-ready** | No external APIs; your business data never leaves your machine |
| **Predictable I/O** | `raw_emails.txt` in → `reply_drafts.txt` out; plain files as the interface |
| **Extensible** | One folder per agent; adding a new agent never touches existing ones |

### 🗂 Repository Structure

```text
AI-Business-Agent/
├── .gitignore                  # Global ignore rules (.env, keys, virtualenvs, ...)
├── README.md                   # This file (bilingual: Chinese / English)
└── AI_Email_Agent/             # Sub-project 1: inquiry parsing & reply drafting
    ├── email_reply_drafter.py  # Main script (standard library only)
    ├── raw_emails.txt          # Input: raw customer emails (auto-seeded when missing)
    └── reply_drafts.txt        # Output: extracted requirements + English reply drafts
```

### 🧩 Sub-projects

| Sub-project | Directory | Stack | Capabilities | Status |
| --- | --- | --- | --- | --- |
| **AI Email Agent** | [`AI_Email_Agent/`](AI_Email_Agent/) | Python 3.6+ / stdlib | Parses batches of customer inquiry emails, extracts product, quantity, pricing, lead time and certification requirements, then drafts an English reply per email | ✅ Working |

> Each sub-project stands alone — copy any folder out of the repo and it still works.

### 🚀 Quick Start

**Requirements:** Python **3.6 or newer** (the script uses f-strings). **No third-party dependencies.**

```bash
# 1. Clone the repository
git clone https://github.com/jelly-AI-creat/AI-Business-Agent.git
cd AI-Business-Agent/AI_Email_Agent

# 2. Run it (the script reads/writes files in the current working directory,
#    so run it from inside AI_Email_Agent)
python email_reply_drafter.py

# 3. Inspect the result — reply_drafts.txt is created in the same folder
```

On the first run, if `raw_emails.txt` is missing, the script **generates a sample file containing three English inquiry emails** so you can try the whole pipeline immediately.

#### Using your own data

Paste your inquiry emails into `AI_Email_Agent/raw_emails.txt` using this format, separating messages with **a line of three or more `=` characters**:

```text
From: customer@example.com
To: sales@yourcompany.com
Subject: Inquiry about ...

(message body)

==============================================================================
(next message, same format)
```

### 🔍 How AI Email Agent Works

```text
raw_emails.txt
   │
   ├─ ① split_emails()          split the text into N messages on the "===" separator
   ├─ ② parse_email()           parse the From / To / Subject headers and the body
   ├─ ③ extract_requirements()  extract 11 business fields using regex rules
   ├─ ④ build_draft()           build one "requirements summary + reply draft" per email
   └─ ⑤ main()                  write reply_drafts.txt (timestamp, source, email count)
```

**Extracted fields**

| Field | Content | Typical trigger |
| --- | --- | --- |
| `product` | Product / model | `(Model: WBH-200)`, `your Wireless Bluetooth Headphones` |
| `quantity` | Order quantity | `500 units`, `10,000 pieces` |
| `price_request` | Pricing basis | `FOB price`, `CIF price`, `unit price`, `best price` |
| `lead_time` | Delivery timeline | `lead time ... 30 days`, `within 30 days` |
| `certification` | Certifications | `CE`, `FCC`, `RoHS`, `UL`, `ISO` |
| `samples` | Sample request | `samples` / `sample` |
| `contact_name` | Contact person | `my name is John Smith`, `I am David Lee` |
| `contact_email` | Email address | `john.smith@abctrading.com` |
| `contact_phone` | Phone number | `+1-212-555-0147` |
| `company` | Buyer company | `ABC Trading Co.`, `Smart Electronics Pte Ltd` |
| `notes` | Other remarks | `MOQ`, `customize / logo`, `payment terms`, `urgent` |

> **Technical note:** this version performs information extraction with **deterministic regex rules** and **calls no LLM API at all** — it is fully offline, reproducible and free to run. Planned LLM enhancements are listed in the roadmap below.

### 📄 Output Example

A real excerpt from a generated `reply_drafts.txt` (the timestamp varies per run):

```text
客户询盘回复草稿 (Reply Drafts)
生成时间: <run timestamp>
来源文件: raw_emails.txt
邮件数量: 3

==============================================================================
邮件 #1
==============================================================================
发件人 (From)   : john.smith@abctrading.com
收件人 (To)     : sales@yourcompany.com
主题 (Subject)  : Inquiry about Wireless Bluetooth Headphones - Bulk Order

【客户需求提取】
  - 产品        : WBH-200
  - 数量        : 500
  - 价格要求    : FOB price
  - 客户公司    : ABC Trading Co.
  - 联系人      : John Smith
  - 邮箱        : john.smith@abctrading.com
  - 其他备注    : 询问最小起订量 (MOQ)；需要定制包装/Logo

【回复草稿】

Dear John Smith,

Thank you for your inquiry and for your interest in our products. We are pleased to hear from you.

Regarding your request for WBH-200, we are glad to confirm that we can supply this item.
We have noted your required quantity of 500 units and will prepare a competitive quotation accordingly.
We will provide our FOB price in the attached quotation.

Best regards,
[Your Name]
[Your Title]
[Your Company]
[Email] | [Phone]
```

> All contacts, companies and phone numbers in the sample data are **fictional demo data** bundled with the script. The `[Your Name]` / `[Your Company]` placeholders at the end of each draft must be replaced with your real signature before sending.

### 🔒 Security & Privacy

- The root `.gitignore` blocks `.env`, `.env.*`, `*.env`, `*.key`, `*.pem`, `secrets.json` and `credentials.json` — **a `.env` created in any sub-folder will never be committed**.
- The script **never touches the network** and calls no external service; email contents stay in local files only.
- All senders, companies, addresses and phone numbers in the sample data are **fictional demo data**, unrelated to any real customer.
- Before committing, check `git status` and `git diff --cached` to make sure no real customer data or API keys enter the repository.

### 🗺 Roadmap

- [x] Batch parsing of inquiry emails with structured requirement extraction
- [x] Automatic English reply drafting (offline, zero-dependency)
- [ ] LLM integration (OpenAI / Claude, etc.) for natural, tone-configurable replies
- [ ] Multi-language inquiry support (Spanish / German / Japanese, ...)
- [ ] Direct IMAP / SMTP integration: receive → draft → human review → send
- [ ] New sub-projects: `AI_Sales_Agent` (quotation generation), `AI_Data_Analyst` (business reporting)

### 🤝 Contributing

1. Fork this repository and branch off `main`: `git checkout -b feature/your-feature`
2. Keep the "one folder per agent" convention for new sub-projects, ideally with a dedicated README inside
3. Before committing, make sure `git status` is clean, no sensitive files are staged and the code runs as-is
4. Follow Conventional Commits for messages (`feat: ...`, `fix: ...`, `docs: ...`)
5. Open a Pull Request describing the motivation and how you verified the change

### 📬 Contact

- Repository: https://github.com/jelly-AI-creat/AI-Business-Agent
- Author on GitHub: [@jelly-AI-creat](https://github.com/jelly-AI-creat)
- Questions and feedback: please use [Issues](https://github.com/jelly-AI-creat/AI-Business-Agent/issues)

### 📜 License

No open-source license has been declared for this repository yet (License: not specified). Please contact the author before commercial use or redistribution.





