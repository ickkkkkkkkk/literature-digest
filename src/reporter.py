"""
HTML report generator.
Produces a clean, no-frills daily digest page.
"""

from pathlib import Path

CSS = """
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    max-width: 860px;
    margin: 0 auto;
    padding: 32px 20px;
    background: #fff;
    color: #222;
    line-height: 1.6;
}
h1 { font-size: 1.4em; margin-bottom: 4px; }
.date { color: #888; font-size: 0.9em; margin-bottom: 24px; }

/* ---- overview ---- */
.overview { background: #f5f5f5; padding: 16px 20px; margin: 16px 0 28px; }
.overview h2 { font-size: 1em; margin: 0 0 10px; }
.overview-item { padding: 4px 0; font-size: 0.92em; border-bottom: 1px dotted #ddd; }
.overview-item:last-child { border-bottom: none; }
.overview .tag { font-size: 0.78em; padding: 1px 6px; font-weight: 600; }
.tag-must { background: #ffe0e0; color: #b71c1c; }
.tag-worth { background: #fff3cd; color: #856404; }

/* ---- section ---- */
h2.section { font-size: 1.1em; margin-top: 32px; padding-bottom: 4px; border-bottom: 2px solid #222; }
.empty-hint { color: #999; font-size: 0.9em; }

/* ---- paper card ---- */
.card { margin: 18px 0; padding: 16px 0; border-bottom: 1px solid #eee; }
.card:last-child { border-bottom: none; }
.card h3 { font-size: 1em; margin: 0 0 4px; font-weight: 600; }
.card .meta { color: #666; font-size: 0.82em; margin-bottom: 6px; }
.card .meta a { color: #555; }
.card .tags { margin-bottom: 6px; }
.card .tags span { display: inline-block; font-size: 0.75em; padding: 1px 8px; margin-right: 6px; margin-bottom: 4px; border: 1px solid #ccc; }
.tag-ev-high { border-color: #b71c1c; color: #b71c1c; font-weight: 600; }
.tag-ev-mid { border-color: #e65100; color: #e65100; }
.tag-ev-low { border-color: #999; color: #999; }
.novelty { font-size: 0.9em; color: #333; margin-bottom: 4px; }
.novelty strong { color: #b71c1c; }
.takeaway { font-size: 0.88em; color: #444; }
.focus-card { border-left: 3px solid #b71c1c; padding-left: 14px; }

/* ---- footer ---- */
.footer { margin-top: 40px; padding-top: 12px; border-top: 1px solid #ddd; font-size: 0.78em; color: #aaa; }
"""


def _rating_tag(rating: str) -> str:
    if rating == "必读":
        return '<span class="tag tag-must">必读</span>'
    elif rating == "值得关注":
        return '<span class="tag tag-worth">值得关注</span>'
    return ""


def _evidence_tag(evidence: str) -> str:
    cls = {"高": "tag-ev-high", "中": "tag-ev-mid", "低": "tag-ev-low"}.get(evidence, "")
    return f'<span class="{cls}">{evidence}证据</span>' if cls else ""


def _build_overview(papers: list[dict]) -> str:
    """Build overview list: only 必读 and 值得关注 papers."""
    worthy = [p for p in papers if p.get("rating") in ("必读", "值得关注")]
    if not worthy:
        return '<p style="color:#999">今日无特别推荐文献。</p>'

    items = []
    for p in worthy:
        tag_html = _rating_tag(p.get("rating", ""))
        novelty = p.get("novelty", "")
        novelty_str = f" — {novelty}" if novelty and novelty != "常规更新，无特殊创新" else ""
        items.append(
            f'<div class="overview-item">'
            f'{tag_html} <strong>{p.get("title_cn", p.get("title", ""))}</strong>'
            f' <span style="color:#888;font-size:0.82em">[{p.get("specialty", "")} · {p.get("study_type", "")}]</span>'
            f'{novelty_str}'
            f'</div>'
        )

    return "\n".join(items)


def _build_cards(papers: list[dict]) -> str:
    """Build full-detail cards for all papers."""
    if not papers:
        return '<p class="empty-hint">今日无新文献或全部已读过。</p>'

    cards = []
    for p in papers:
        is_focus = p.get("is_focus", False)
        focus_cls = "focus-card" if is_focus else ""

        # Title
        title_cn = p.get("title_cn", "") or p.get("title", "")
        title_en = p.get("title", "")

        # Meta line
        authors = p.get("authors", "")
        journal = p.get("journal", "")
        doi = p.get("doi", "")
        pmid = p.get("pmid", "")
        url = p.get("url", f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/") if pmid else ""
        meta_parts = [journal, authors]
        meta_str = " · ".join(p for p in meta_parts if p)
        if url:
            meta_str += f' · <a href="{url}">PubMed</a>'
        if doi:
            meta_str += f' · DOI: {doi}'

        # Tags
        tags = []
        specialty = p.get("specialty", "")
        study_type = p.get("study_type", "")
        evidence = p.get("evidence", "")
        if specialty:
            tags.append(f"<span>{specialty}</span>")
        if study_type:
            tags.append(f"<span>{study_type}</span>")
        if evidence:
            tags.append(_evidence_tag(evidence))

        # Novelty
        novelty = p.get("novelty", "")
        novelty_html = ""
        if novelty and novelty != "常规更新，无特殊创新":
            novelty_html = f'<div class="novelty"><strong>创新点：</strong>{novelty}</div>'

        # Takeaway
        takeaway = p.get("takeaway", "")
        takeaway_html = f'<div class="takeaway">{takeaway}</div>' if takeaway else ""

        # Rating badge
        rating_html = _rating_tag(p.get("rating", ""))

        cards.append(f"""<div class="card {focus_cls}">
<h3>{rating_html} {title_cn}</h3>
<div style="color:#888;font-size:0.82em">{title_en}</div>
<div class="meta">{meta_str}</div>
<div class="tags">{' '.join(tags)}</div>
{novelty_html}
{takeaway_html}
</div>""")

    return "\n".join(cards)


def generate(date: str, papers: list[dict], stats: dict) -> str:
    """Generate complete HTML report from merged paper dicts."""
    overview_html = _build_overview(papers)
    cards_html = _build_cards(papers)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>文献日报 — {date}</title>
<style>{CSS}</style>
</head>
<body>

<h1>骨科+生信文献日报</h1>
<p class="date">{date} · PubMed · DeepSeek 摘要生成</p>

<div class="overview">
<h2>今日推荐</h2>
{overview_html}
</div>

<div style="margin-top:12px;color:#888;font-size:0.82em">
累计追踪 {stats['total']} 篇 · 今日新增 {stats.get('today_new', 0)} 篇
</div>

<h2 class="section">全部文献</h2>
{cards_html}

<div class="footer">自动生成于 {date} · 数据源 PubMed</div>

</body>
</html>"""


def save_report(html: str, date: str, output_dir: str = "./output") -> str:
    """Write the HTML report to disk. Returns the file path."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    filepath = out_path / f"{date}.html"
    filepath.write_text(html, encoding="utf-8")
    return str(filepath)
