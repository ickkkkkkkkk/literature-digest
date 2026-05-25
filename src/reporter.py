"""
HTML report generator.
Produces a self-contained, readable daily digest page.
"""

from datetime import datetime
from pathlib import Path


CSS = """
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    max-width: 900px;
    margin: 0 auto;
    padding: 40px 20px;
    background: #f8f9fa;
    color: #212529;
    line-height: 1.7;
}
h1 { font-size: 1.8em; margin-bottom: 4px; color: #1a1a2e; }
h2 { font-size: 1.3em; margin-top: 32px; color: #16213e; border-bottom: 2px solid #0f3460; padding-bottom: 6px; }
.date { color: #666; font-size: 0.95em; margin-bottom: 24px; }
.stats { background: #e8f4f8; border-left: 4px solid #0f3460; padding: 12px 16px; margin: 16px 0; border-radius: 4px; font-size: 0.95em; }
.paper { background: white; border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px 24px; margin: 16px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.paper h3 { margin: 0 0 8px 0; font-size: 1.05em; color: #0f3460; }
.paper .meta { color: #888; font-size: 0.85em; margin-bottom: 10px; }
.paper .badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 0.8em; font-weight: 600; }
.badge-must { background: #ffe0e0; color: #c0392b; }
.badge-worth { background: #fff3cd; color: #856404; }
.badge-skim { background: #e2e3e5; color: #383d41; }
.badge-skip { background: #f0f0f0; color: #999; }
.paper .link { font-size: 0.85em; }
.paper .link a { color: #0f3460; text-decoration: none; border-bottom: 1px dotted #0f3460; }
.paper .link a:hover { color: #e94560; border-color: #e94560; }
.footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid #ddd; font-size: 0.8em; color: #aaa; text-align: center; }
.irrelevant { opacity: 0.5; }
"""


def _markdown_to_html(text: str) -> str:
    """Minimal markdown→HTML converter for the summary content."""
    import re

    lines = text.strip().split("\n")
    html_parts = []
    in_para = False

    for line in lines:
        stripped = line.strip()

        # Separator
        if stripped.startswith("---") and len(stripped) < 6:
            if in_para:
                html_parts.append("</p>")
                in_para = False
            # Don't render horizontal rules — they're section separators in our prompt
            continue

        # Bold
        stripped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped)

        # Headings
        if stripped.startswith("### "):
            if in_para:
                html_parts.append("</p>")
                in_para = False
            html_parts.append(f"<h4>{stripped[4:]}</h4>")
            continue

        # Star ratings
        if "★★★" in stripped or "★★" in stripped or "★" in stripped or "❌" in stripped:
            if in_para:
                html_parts.append("</p>")
                in_para = False
            cls = "badge-must" if "★★★" in stripped else (
                "badge-worth" if "★★" in stripped else (
                    "badge-skim" if "★" in stripped else "badge-skip"
                )
            )
            html_parts.append(f'<span class="badge {cls}">{stripped}</span>')
            continue

        # Empty line
        if not stripped:
            if in_para:
                html_parts.append("</p>")
                in_para = False
            continue

        # Regular paragraph
        if not in_para:
            html_parts.append("<p>")
            in_para = True
        else:
            html_parts.append("<br>")
        html_parts.append(stripped)

    if in_para:
        html_parts.append("</p>")

    return "\n".join(html_parts)


def generate(
    date: str,
    spine_ortho_summary: str,
    medical_bioinfo_summary: str,
    stats: dict,
    query1_name: str,
    query2_name: str,
) -> str:
    """
    Generate a complete HTML report.

    Args:
        date: formatted date string (e.g. "2026-05-25")
        spine_ortho_summary: markdown summary from Claude for spine/ortho papers
        medical_bioinfo_summary: markdown summary from Claude for medical bioinfo papers
        stats: dedup stats dict
        query1_name: name of first query
        query2_name: name of second query

    Returns:
        Complete HTML string
    """
    spine_html = _markdown_to_html(spine_ortho_summary)
    bioinfo_html = _markdown_to_html(medical_bioinfo_summary)

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
<p class="date">{date} · 由 Claude 自动生成 · 基于 PubMed 数据</p>

<div class="stats">
  <strong>统计</strong><br>
  数据库累计追踪：{stats['total']} 篇文献 · 今日新增：{stats.get('today_new', '—')} 篇
</div>

<h2>脊柱+骨科基础研究</h2>
<div class="content">
{spine_html if spine_html else '<p>今日无新文献或全部已读过。</p>'}
</div>

<h2>医学+生物信息学</h2>
<div class="content">
{bioinfo_html if bioinfo_html else '<p>今日无新文献或全部已读过。</p>'}
</div>

<div class="footer">
  自动生成于 {date} · 数据源：PubMed · 摘要：Claude ·
  <a href="https://github.com">项目地址</a>
</div>

</body>
</html>"""


def save_report(html: str, date: str, output_dir: str = "./output") -> str:
    """Write the HTML report to disk. Returns the file path."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    filepath = out_path / f"{date}.html"
    filepath.write_text(html, encoding="utf-8")
    return str(filepath)
