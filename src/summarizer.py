"""
Claude API summarizer.
Takes raw article data and produces structured Chinese summaries.
"""

import json
from anthropic import Anthropic


SYSTEM_PROMPT = """你是一位资深的骨科基础研究和医学生物信息学学术助手。你的任务是对以下英文学术文献生成高质量的中文摘要。

对每篇文献，严格按照以下格式输出：

**标题**：英文原标题
**中文标题**：中文翻译标题
**期刊**：期刊名称
**DOI/PMID**：文献标识符
**背景**：（1-2句，该研究要解决什么问题）
**方法**：（1-2句，核心技术手段或实验设计）
**关键发现**：（2-3句，最重要的结果和结论）
**临床/学术价值**：（1句，对临床实践或学术研究的潜在影响）
**推荐等级**：★★★必读 / ★★值得关注 / ★可略读 / ❌不相关

---重要说明---
1. 如果文献与以下领域完全无关，直接输出「❌不相关」并跳过详细摘要：
   - 骨科（脊柱、关节、骨肿瘤、创伤、运动医学、骨代谢）
   - 医学生物信息学（计算生物学、基因组学、转录组学、AI/ML在医学中的应用）
2. 仅总结每篇文献自己报告的内容，不要添加你的外部知识。
3. 用专业但平实的中文，避免过度口语化。
4. 作者名字保持英文原文。
5. 按照给定顺序输出所有文献。
6. 文献之间用 --- 分隔线。"""

USER_PROMPT_TEMPLATE = """请为以下 {count} 篇文献生成中文摘要。

检索类别：{source_name}

文献列表：

{articles_json}
"""


def summarize(
    articles: list[dict],
    source_name: str,
    api_key: str,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 800,
) -> str:
    """
    Send articles to Claude for summarization.

    Args:
        articles: list of article dicts
        source_name: human-readable source label (e.g. "脊柱+骨科基础研究")
        api_key: Anthropic API key
        model: Claude model to use
        max_tokens: max output tokens

    Returns:
        Markdown-formatted summary string
    """
    if not articles:
        return ""

    # Prepare compact article data for the prompt
    articles_for_prompt = []
    for art in articles:
        # Truncate abstract to save tokens (Haiku context is large enough but let's be safe)
        abstract = art["abstract"]
        if len(abstract) > 3000:
            abstract = abstract[:3000] + "..."

        articles_for_prompt.append({
            "pmid": art["pmid"],
            "title": art["title"],
            "journal": art["journal"],
            "authors": art["authors"],
            "pubdate": art.get("pubdate", ""),
            "doi": art["doi"],
            "keywords": art.get("keywords", []),
            "abstract": abstract,
        })

    user_prompt = USER_PROMPT_TEMPLATE.format(
        count=len(articles),
        source_name=source_name,
        articles_json=json.dumps(articles_for_prompt, ensure_ascii=False, indent=2),
    )

    client = Anthropic(api_key=api_key)

    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_prompt}
        ],
    )

    return message.content[0].text


def batch_summarize(
    articles: list[dict],
    source_name: str,
    api_key: str,
    model: str = "claude-haiku-4-5-20251001",
    batch_size: int = 15,
) -> str:
    """
    Summarize articles in batches to avoid token limits.
    Returns concatenated results.
    """
    if not articles:
        return ""

    results = []
    for i in range(0, len(articles), batch_size):
        batch = articles[i : i + batch_size]
        result = summarize(
            articles=batch,
            source_name=source_name,
            api_key=api_key,
            model=model,
        )
        if result:
            results.append(result)

    return "\n\n".join(results)
