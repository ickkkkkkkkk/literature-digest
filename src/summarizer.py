"""
DeepSeek API summarizer (OpenAI-compatible).
Takes raw article data and produces structured JSON summaries.
"""

import json
from openai import OpenAI

SYSTEM_PROMPT = """你是一位资深的骨科临床研究助理。你的任务是对英文学术文献生成高度结构化的中文信息，帮助临床医生在30秒内判断是否精读。

对每篇文献，严格输出以下JSON对象（一行一个JSON，用换行分隔），不要输出任何其他内容：

{
  "pmid": "PMID",
  "title_cn": "中文标题翻译",
  "specialty": "亚专业（自由文本，≤8字，如：脊柱外科/关节外科/创伤骨科/运动医学/骨肿瘤/骨代谢/单细胞组学/AI医学/肿瘤免疫等）",
  "study_type": "系统综述与Meta分析/随机对照试验/队列研究/病例对照研究/个案报道/技术说明/基础实验/综述/其他",
  "evidence": "高/中/低/不适用（仅系统综述与RCT为高，队列为中等，病例对照、个案、技术说明为低，基础实验为不适用）",
  "is_focus": true/false,
  "novelty": "核心创新发现（≤30字，无可填'常规更新，无特殊创新'）",
  "rating": "必读/值得关注/可略读/不相关",
  "takeaway": "临床核心要点（≤100字）"
}

重要说明：
1. 若文献与骨科或医学生物信息学完全无关，rating 填"不相关"，其余字段可简略。
2. 期刊名称不要缩写。
3. novelty 要直接、犀利，一眼看出新颖性，避免空泛。
4. is_focus 仅当标题或摘要明确包含用户关注领域关键词时才为 true。
5. 每篇文献输出一行完整 JSON，不要加逗号分隔符，不要加数组包裹。
6. 若无法确定某字段，选最接近的值，不可留空。"""

USER_PROMPT_TEMPLATE = """请为以下 {count} 篇文献生成结构化中文摘要。

检索类别：{source_name}
{focus_line}

文献列表：

{articles_json}"""


def _build_articles_json(articles: list[dict]) -> list[dict]:
    """Prepare article data for the LLM prompt, truncating long abstracts."""
    slim = []
    for art in articles:
        abstract = art["abstract"]
        if len(abstract) > 3000:
            abstract = abstract[:3000] + "..."
        slim.append({
            "pmid": art["pmid"],
            "title": art["title"],
            "journal": art["journal"],
            "authors": art["authors"][:120],
            "pubdate": art.get("pubdate", ""),
            "doi": art["doi"],
            "keywords": art.get("keywords", []),
            "abstract": abstract,
        })
    return slim


def _parse_json_response(text: str) -> list[dict]:
    """Robustly parse JSON from LLM response — handles NDJSON, JSON array, code fences."""
    if not text:
        return []

    # Strip code fences
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove opening ```json or ```
        end_of_first = cleaned.find("\n")
        if end_of_first != -1:
            cleaned = cleaned[end_of_first + 1:]
        # Remove closing ```
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]

    cleaned = cleaned.strip()

    # Try 1: JSON array [{...}, {...}]
    if cleaned.startswith("["):
        try:
            arr = json.loads(cleaned)
            if isinstance(arr, list):
                return [obj for obj in arr if isinstance(obj, dict) and "pmid" in obj]
        except json.JSONDecodeError:
            pass

    # Try 2: Single object with embedded array (e.g. {"papers": [...]})
    if cleaned.startswith("{"):
        try:
            obj = json.loads(cleaned)
            if isinstance(obj, dict):
                # Direct single paper
                if "pmid" in obj:
                    return [obj]
                # Search all values for paper lists
                for val in obj.values():
                    if isinstance(val, list):
                        papers = [v for v in val if isinstance(v, dict) and "pmid" in v]
                        if papers:
                            return papers
        except json.JSONDecodeError:
            pass

    # Try 3: NDJSON — extract each {...} block via brace matching
    results = []
    i = 0
    while i < len(cleaned):
        if cleaned[i] == "{":
            depth = 0
            j = i
            in_string = False
            escape = False
            while j < len(cleaned):
                ch = cleaned[j]
                if escape:
                    escape = False
                    j += 1
                    continue
                if ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = not in_string
                elif not in_string:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            j += 1
                            break
                j += 1
            try:
                obj = json.loads(cleaned[i:j])
                if isinstance(obj, dict) and "pmid" in obj:
                    results.append(obj)
            except json.JSONDecodeError:
                pass
            i = j
        else:
            i += 1

    return results


def summarize(
    articles: list[dict],
    source_name: str,
    api_key: str,
    model: str = "deepseek-chat",
    focus_keywords: str = "",
) -> list[dict]:
    """Send articles to DeepSeek, return parsed JSON list."""
    if not articles:
        return []

    focus_line = ""
    if focus_keywords:
        focus_line = f"用户当前重点关注领域：{focus_keywords}"

    user_prompt = USER_PROMPT_TEMPLATE.format(
        count=len(articles),
        source_name=source_name,
        focus_line=focus_line,
        articles_json=json.dumps(_build_articles_json(articles), ensure_ascii=False, indent=2),
    )

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    response = client.chat.completions.create(
        model=model,
        max_tokens=8192,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    raw = response.choices[0].message.content
    print(f"[summarize] Raw response length: {len(raw)} chars, first 200: {raw[:200]}")
    parsed = _parse_json_response(raw)
    print(f"[summarize] Parsed {len(parsed)} papers from response")
    return parsed


def batch_summarize(
    articles: list[dict],
    source_name: str,
    api_key: str,
    model: str = "deepseek-chat",
    batch_size: int = 10,
    focus_keywords: str = "",
) -> list[dict]:
    """Summarize articles in batches, returning concatenated JSON results."""
    if not articles:
        return []

    results = []
    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]
        parsed = summarize(
            articles=batch,
            source_name=source_name,
            api_key=api_key,
            model=model,
            focus_keywords=focus_keywords,
        )
        results.extend(parsed)

    return results
