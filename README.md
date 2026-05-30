# Literature Digest — 脊柱骨科+医学生信文献日报

每日自动检索 PubMed 最新文献，通过 DeepSeek AI 生成结构化中文摘要，生成 HTML 报告并通过邮件推送。

## 功能特点

- **双检索源覆盖**：脊柱骨科基础研究 + 医学生物信息学，可自定义检索式
- **AI 智能摘要**：DeepSeek API 生成中文标题翻译、亚专业分类、研究类型、证据等级、创新点、核心要点和推荐评级
- **去重追踪**：SQLite 历史数据库，不会重复推送已读文献
- **精美 HTML 报告**：重点关注文献高亮，按推荐等级排序，30 秒快速浏览
- **邮件推送**：通过 QQ 邮箱 SMTP 发送，每天醒来就能看
- **GitHub Actions 自动运行**：每天定时执行，无需自己的服务器

## 流水线

```
PubMed API → 文献检索 → 去重过滤 → DeepSeek AI 摘要 → HTML 报告 → 邮件推送
```

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/ickkkkkkkkk/literature-digest.git
cd literature-digest
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
# DeepSeek API Key（用于生成中文摘要）
export DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxx"

# QQ 邮箱地址（发件人和收件人相同则只设这一个）
export QQ_SMTP_EMAIL="your-email@qq.com"

# QQ 邮箱 SMTP 授权码（用于发送邮件）
export QQ_SMTP_PASSWORD="xxxxxxxxxxxxxx"

# PubMed 联系邮箱（NCBI 强制要求）
export PUBMED_EMAIL="your-email@qq.com"
```

> **获取 API Key**：
> - DeepSeek：注册 [platform.deepseek.com](https://platform.deepseek.com)，充值后获取 API Key
> - QQ 邮箱授权码：QQ 邮箱 → 设置 → 账户 → POP3/SMTP 服务 → 生成授权码
> - PubMed 不需要 API Key，但填了邮箱才能请求

### 4. 修改配置（可选）

编辑 `config.yaml` 调整：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `pubmed.retmax` | 每条检索最多取回篇数 | 30 |
| `pubmed.lookback_days` | 检索最近 N 天的文献 | 2 |
| `focus_keywords` | 高亮匹配的关注领域关键词 | 椎间盘退变, 外泌体… |
| `queries.*.query` | PubMed 检索式 | 脊柱骨科 / 医学+生信 |
| `output.keep_days` | 本地保留报告天数 | 90 |

### 5. 手动运行一次

```bash
python main.py
```

成功后会在 `output/` 目录生成 `YYYY-MM-DD.html` 报告，同时发送邮件。

## GitHub Actions 自动化

仓库自带 `.github/workflows/daily.yml`，每天北京时间 5:47 AM 自动运行。

### 配置 Secrets

在 GitHub 仓库页面：**Settings → Secrets and variables → Actions → New repository secret**，添加以下三个 secrets：

| Secret 名称 | 说明 |
|-------------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `QQ_SMTP_EMAIL` | QQ 邮箱地址（同时作为发件人和收件人） |
| `QQ_SMTP_PASSWORD` | QQ 邮箱 SMTP 授权码 |
| `PUBMED_EMAIL` | PubMed 联系邮箱 |

### 手动触发

在 GitHub 仓库页面：**Actions → Daily Literature Digest → Run workflow**。

### 修改运行时间

编辑 `.github/workflows/daily.yml` 中的 cron 表达式：

```yaml
on:
  schedule:
    # UTC 时间，北京时间 = UTC + 8
    - cron: "47 21 * * *"   # 北京时间 5:47 AM
```

### 查看报告

每次运行后，可在 Actions 运行记录的 **Artifacts** 中下载 HTML 报告（保留 7 天）。

## 自定义检索式

编辑 `config.yaml` 中的 `queries` 部分，添加或修改检索式：

```yaml
queries:
  my_topic:
    name: "我的研究方向"
    query: >
      ("your mesh term"[MeSH] OR "your keyword"[tiab])
      AND ("2025"[pdat] OR "2026"[pdat])
```

检索式语法遵循 [PubMed 查询规范](https://pubmed.ncbi.nlm.nih.gov/advanced/)。

## 报告示例

生成的 HTML 报告包含：

- **今日推荐**：评级为"必读"和"值得关注"的文献概览
- **全部文献卡片**：每篇包含中文标题、英文原标题、期刊/作者、亚专业标签、研究类型、证据等级、创新点、临床核心要点
- **重点关注标识**：匹配 `focus_keywords` 的文献左侧红色边框高亮

## 项目结构

```
literature-digest/
├── main.py                 # 主入口，编排流水线
├── config.yaml             # 配置文件（检索式、API、邮件等）
├── requirements.txt        # Python 依赖
├── src/
│   ├── fetcher.py          # PubMed Entrez API 检索
│   ├── dedup.py            # SQLite 去重
│   ├── summarizer.py       # DeepSeek AI 摘要生成
│   ├── reporter.py         # HTML 报告生成
│   └── mailer.py           # QQ 邮箱 SMTP 发送
├── .github/workflows/
│   └── daily.yml           # GitHub Actions 定时运行
├── output/                 # 生成的报告（gitignore）
└── history.db              # 去重数据库（gitignore）
```

## 依赖

- Python ≥ 3.10
- [Biopython](https://biopython.org) — PubMed Entrez API
- [OpenAI SDK](https://github.com/openai/openai-python) — DeepSeek API（OpenAI 兼容接口）
- [PyYAML](https://pyyaml.org) — 配置解析
- [Jinja2](https://jinja.palletsprojects.com) — HTML 模板（备用）

## License

MIT License — 详见 [LICENSE](LICENSE) 文件。
