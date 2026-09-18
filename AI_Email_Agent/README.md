# AI_Email_Agent

外贸客户询盘解析 + 英文回复草稿生成器。同一套输入，两种生成方式：

| 脚本 | 第三方依赖 | 生成方式 | 输出文件 |
| --- | --- | --- | --- |
| `email_reply_drafter.py` | **无**（纯标准库） | 离线正则规则，不联网、可复现、零成本 | `reply_drafts.txt` |
| `email_reply_drafter_llm.py` | `requests`、`python-dotenv` | 调用 DeepSeek 生成更自然的英文回复，语气可调；失败自动回退离线草稿 | `reply_drafts_llm.txt` |

LLM 版复用离线版的解析层（`split_emails` / `parse_email` / `extract_requirements` / `build_draft`），只替换「回复正文」部分，因此两个脚本的「客户需求提取」区块完全一致，便于对比。

## 1. 安装依赖

```bash
cd AI_Email_Agent
python -m pip install -r requirements.txt

# 如果 pip 卡在 "Collecting ..."（连不上 pypi.org），改用清华镜像：
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 也可以永久设置镜像源，避免以后每次卡住：
python -m pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

离线版 `email_reply_drafter.py` 不需要任何第三方依赖。

## 2. 配置 API Key

1. 到 <https://platform.deepseek.com> 申请 API Key（需充值）
2. 打开本目录的 `.env`，把 `LLM_API_KEY=` 后面换成你的真实 Key
3. 验证（**不消耗 token**）：

```bash
python email_reply_drafter_llm.py --check
```

`.env` 已被仓库根目录 `.gitignore` 屏蔽，不会提交；`.env.example` 是可提交的模板。

## 3. 运行

```bash
python email_reply_drafter_llm.py --limit 1 --dry-run   # 不联网：验证排版与降级逻辑
python email_reply_drafter_llm.py --limit 1             # 只跑第 1 封，省钱的试跑
python email_reply_drafter_llm.py                       # 全量处理 raw_emails.txt
python email_reply_drafter_llm.py --tone friendly       # 语气：formal(默认)/friendly/concise
python email_reply_drafter_llm.py --model deepseek-v4-pro --out reply_drafts_pro.txt
python email_reply_drafter_llm.py --help                # 查看全部参数
```

离线版：`python email_reply_drafter.py`

## 4. 配置项（`.env`）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LLM_API_KEY` | 空 | DeepSeek API Key（也兼容读 `DEEPSEEK_API_KEY`） |
| `LLM_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容接口地址 |
| `LLM_MODEL` | `deepseek-flash` | `deepseek-flash`（快、便宜）/ `deepseek-v4-pro`（更强、更贵） |
| `LLM_TIMEOUT` | `60` | 单次请求超时（秒） |
| `LLM_TEMPERATURE` | `0.3` | 采样温度，仅在非思考模式下生效 |
| `LLM_MAX_TOKENS` | `1024` | 单封回复最大输出 token |
| `LLM_RETRIES` | `2` | 仅对 429/500/503 与超时重试 |
| `LLM_DRAFT_FILE` | `reply_drafts_llm.txt` | 输出文件名 |
| `LLM_TONE` | `formal` | 语气：formal / friendly / concise |
| `LLM_REASONING_EFFORT` | `high` | 仅在 `--thinking` 时生效 |

命令行参数（`--model` / `--out` / `--tone`）优先级高于 `.env`；已存在的系统环境变量优先于 `.env`。

## 5. 关于 DeepSeek API 的三个要点（2026 年现状，已按官方文档核对）

1. **模型名**：现役为 `deepseek-flash`（DeepSeek-V4.1-Flash）与 `deepseek-v4-pro`。旧名 `deepseek-chat` / `deepseek-reasoner` 已下线，填了会返回 **HTTP 400**。
2. **思考模式默认开启**（effort=high）。写询盘回复不需要长思考，脚本显式传 `{"thinking": {"type": "disabled"}}`，更快更省；如需开启用 `--thinking`。
3. **思考模式下 `temperature` 不生效**（官方行为：不报错但被忽略）；只有非思考模式下才生效。

## 6. 输出说明

`reply_drafts_llm.txt` 每封邮件包含：

```text
处理状态: LLM: deepseek-flash | 用时 3.4s | tokens 输入 812 / 输出 236
==============================================================================
邮件 #1
==============================================================================
发件人 (From) ...
【客户需求提取】   <- 与离线版完全一致（正则结果）
【回复草稿】       <- 由 LLM 生成的英文正文；失败时回退为离线草稿
```

脚本**不会覆盖**被 git 跟踪的 `reply_drafts.txt`，两者可直接对比。

## 7. 排错

| 现象 | 原因与处理 |
| --- | --- |
| `HTTP 401` | Key 错误或已失效 → 重新复制 `LLM_API_KEY` |
| `HTTP 402` | 账户余额不足 → 到 DeepSeek 平台充值 |
| `HTTP 400` | 模型名不存在 → 检查 `LLM_MODEL`（旧名 `deepseek-chat` 已下线） |
| `HTTP 429` | 触发限流 → 脚本已自动退避重试，稍后再跑 |
| `请求超时` | 网络/代理拦截 → 调大 `LLM_TIMEOUT`，或给 `LLM_BASE_URL` 换可达网关 |
| 全部「回退」 | 先跑 `--check` 定位 Key / 余额 / 网络问题 |
| `pip` 卡住不动 | 连不上 pypi.org → 用清华镜像（见第 1 节） |

## 8. 安全与隐私

- `.env` 不会入库；脚本输出密钥时只显示 `sk-****abcd`，错误信息中也不含完整 Key。
- **与离线版的区别**：LLM 版会把邮件内容发送到 DeepSeek 服务器，离线版全程不联网。处理真实客户数据前请自行评估合规性。
- `raw_emails.txt` 中的示例邮件（发件人、公司、电话）均为虚构演示数据。
- 草稿末尾的 `[Your Name]` / `[Your Company]` 等占位符，请替换为真实签名后再发送。