# 外贸询盘助手（Streamlit 网页版）

把原来只能在命令行里跑的询盘脚本，升级成不懂代码的商务同事也能用的网页：
左边贴客户询盘邮件，右边自动显示**提取到的需求**和**英文回复草稿**。

## 一、安装与启动

```powershell
cd C:\Users\Lenovo\.cline\data\workspaces\chat\inquiry-webapp
python -m pip install -r requirements.txt   # 已经装好可跳过（当前环境 streamlit 1.64.0）
python -m streamlit run app.py
```

浏览器会自动打开 `http://localhost:8501`。停止服务：在终端按 `Ctrl + C`。

## 二、给同事用（局域网）

```powershell
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

然后让同事在浏览器打开 `http://你的电脑IP:8501`（用 `ipconfig` 查 IP）。
注意：电脑要保持开机、别关终端窗口；跨公网使用需要额外做内网穿透或部署到服务器。

## 三、界面说明

| 区域 | 内容 |
| --- | --- |
| 左列 | ① 询盘邮件原文（整段粘贴，含主题和签名），点「🔍 解析询盘并生成回复」 |
| 右列 | ② 提取的需求：需求项 / 内容 / 原文依据 三列表格，另有需求项数、缺失信息数、是否紧急 |
| 右列 | ③ 英文回复草稿：可直接编辑、复制，或下载成 txt |
| 侧边栏 | 公司名、签名（自动签在回复末尾）、是否使用你原来的脚本、载入示例询盘、清空 |

字段名：产品/型号、数量、规格要求、认证要求、目的地/港口、目标价格、交期要求、
付款方式、贸易术语、MOQ、客户诉求、客户称呼。

"缺失信息"表示客户邮件里没提到的关键项，回复草稿会自动把它们变成反问句；
如果客户自己就是在问我们交期/付款方式，则不会反过来问客户。

## 四、接上你原来的询盘脚本（不用改代码）

目前内置的是通用规则解析。想用你自己调通的逻辑，只要两步：

1. 确认你的脚本里有下面任意一个函数：

   ```python
   def extract_requirements(text):          # 必需，返回 list
       return [{"field": "product", "value": "LED high bay light", "evidence": "..."}]
       # 键名支持 field/需求项/name/key + value/内容/result/text；也可以直接返回字符串列表

   def generate_reply(text):                # 可选；签名也可以是 generate_reply(text, analysis)
       return "Subject: ..."
   ```

2. 启动网页前设置环境变量，然后照常 `python -m streamlit run app.py`：

   ```powershell
   $env:INQUIRY_SCRIPT_PATH="D:\work\my_inquiry.py"    # 也可以是脚本所在目录
   python -m streamlit run app.py
   ```

侧边栏会显示 `✅ 已接入你的脚本`。你的脚本报错时会自动退回内置规则，网页不会崩；
改完脚本点侧边栏「重新加载脚本」即可生效。

## 五、不用网页也能验证逻辑

```powershell
python inquiry_core.py    # 打印示例询盘的提取结果和生成的英文回复
python smoke_test.py      # 无头跑一遍整个网页（Streamlit AppTest），确认界面没报错
```

## 六、文件结构

```
inquiry-webapp/
├── app.py            # Streamlit 界面（两个输入框 + 表格 + 回复草稿）
├── inquiry_core.py   # 解析与回复草稿的核心逻辑，可独立运行
├── smoke_test.py      # 无头界面冒烟测试（python smoke_test.py）
├── requirements.txt  # 依赖（streamlit）
└── README.md
```

## 七、后续可加的增强（按需）

- 接大模型（OpenAI / DeepSeek 等）把回复草稿写得更自然：在 `inquiry_core.generate_reply` 里加一个
  "有 API Key 就调用大模型，否则用模板" 的分支即可；
- 批量处理：把 `st.text_area` 换成 `st.file_uploader` 上传邮件导出文件，循环 `core.analyze`；
- 存记录：用 `sqlite3` 把每次解析结果落库，方便统计询盘来源和转化率。
