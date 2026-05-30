#!/usr/bin/env python3
"""
Daily Literature Digest — 多用户文献日报

Pipeline:
  1. Search PubMed with configurable query sets
  2. Deduplicate against per-user history database
  3. Summarize new papers with DeepSeek API (structured JSON)
  4. Generate HTML report with overview + detail cards
  5. Email the report

Supports multi-user mode: place one YAML config per user in users/
"""

import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


def _load_dotenv() -> None:
    """Load .env file into os.environ if it exists (no external dependency)."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:  # don't override existing env vars
            os.environ[key] = val


_load_dotenv()

import yaml

from src.fetcher import search_pubmed
from src.dedup import filter_new, stats as db_stats
from src.summarizer import batch_summarize
from src.reporter import generate as generate_report, save_report
from src.mailer import send as send_email


def _resolve_env(value: str) -> str:
    """Replace ${VAR_NAME} patterns with environment variable values."""
    if not isinstance(value, str):
        return value

    def _replacer(match):
        var_name = match.group(1)
        env_val = os.environ.get(var_name, "")
        if not env_val:
            print(f"[warn] Environment variable '{var_name}' is not set")
        return env_val

    return re.sub(r"\$\{(\w+)\}", _replacer, value)


def resolve_config(cfg: dict) -> dict:
    """Recursively resolve env vars in config values."""
    if isinstance(cfg, dict):
        return {k: resolve_config(v) for k, v in cfg.items()}
    elif isinstance(cfg, list):
        return [resolve_config(item) for item in cfg]
    elif isinstance(cfg, str):
        return _resolve_env(cfg)
    return cfg


def load_config(path: str) -> dict:
    """Load and resolve config file. Tries multiple encodings for cross-platform compat."""
    raw = None
    for enc in ("utf-8", "utf-16-le", "utf-16-be", "gbk"):
        try:
            with open(path, "r", encoding=enc) as f:
                raw = yaml.safe_load(f)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if raw is None:
        raise ValueError(f"Failed to decode config file: {path}")
    return resolve_config(raw)


def cleanup_old_reports(output_dir: str, keep_days: int) -> None:
    """Remove reports older than keep_days."""
    cutoff = datetime.now() - timedelta(days=keep_days)
    out_path = Path(output_dir)
    if not out_path.exists():
        return

    for f in out_path.glob("*.html"):
        if f.name.endswith(".html"):
            try:
                file_date = datetime.strptime(f.stem, "%Y-%m-%d")
                if file_date < cutoff:
                    f.unlink()
                    print(f"[cleanup] Removed old report: {f.name}")
            except (ValueError, OSError):
                pass


def _merge(articles: list[dict], summaries: list[dict]) -> list[dict]:
    """Merge fetcher article metadata with LLM summary JSON by PMID."""
    summary_map = {s["pmid"]: s for s in summaries}
    merged = []
    for art in articles:
        s = summary_map.get(art["pmid"], {})
        merged.append({
            **art,
            "title_cn": s.get("title_cn", ""),
            "specialty": s.get("specialty", ""),
            "study_type": s.get("study_type", ""),
            "evidence": s.get("evidence", ""),
            "is_focus": s.get("is_focus", False),
            "novelty": s.get("novelty", ""),
            "rating": s.get("rating", ""),
            "takeaway": s.get("takeaway", ""),
        })
    return merged


def process_user(cfg_path: str) -> None:
    """Run the full pipeline for a single user config."""
    user_name = Path(cfg_path).stem
    cfg = load_config(cfg_path)

    label = cfg.get("label", user_name)
    print(f"\n{'#'*60}")
    print(f"# User: {label}")
    print(f"{'#'*60}")

    # --- DB path (per-user dedup) ---
    db_dir = Path(cfg_path).parent.parent / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(db_dir / f"history_{user_name}.db")

    # --- Resolve secrets ---
    pubmed_email = cfg["pubmed"]["email"]
    pubmed_api_key = cfg["pubmed"].get("api_key", "")
    if "${PUBMED_EMAIL}" == pubmed_email or not pubmed_email or "your-email" in pubmed_email:
        pubmed_email = os.environ.get("PUBMED_EMAIL", "")
    if not pubmed_email:
        print(f"[error] [{label}] PubMed email is required.")
        return

    llm_api_key = cfg["llm"]["api_key"]
    if not llm_api_key or llm_api_key.startswith("${"):
        print(f"[error] [{label}] DEEPSEEK_API_KEY is required.")
        return

    retmax = cfg["pubmed"].get("retmax", 30)
    lookback = cfg["pubmed"].get("lookback_days", 2)
    llm_model = cfg["llm"].get("model", "deepseek-chat")
    focus_keywords = cfg.get("focus_keywords", "")

    # --- Date ---
    beijing_now = datetime.now(timezone(timedelta(hours=8)))
    date_display = beijing_now.strftime("%Y-%m-%d")

    today_new = 0
    all_papers = []

    # --- Process each query ---
    for query_key, query_cfg in cfg["queries"].items():
        source_name = query_cfg["name"]
        query_string = query_cfg["query"]

        print(f"\n[fetch] Searching PubMed: {source_name}")

        articles = search_pubmed(
            query=query_string,
            email=pubmed_email,
            api_key=pubmed_api_key,
            retmax=retmax,
            lookback_days=lookback,
        )
        print(f"[fetch] Retrieved {len(articles)} articles with abstracts")

        # Deduplicate (per-user database)
        new_articles = filter_new(articles, source=source_name, db_path=db_path)
        today_new += len(new_articles)
        print(f"[dedup] {len(new_articles)} new, {len(articles) - len(new_articles)} already seen")

        if not new_articles:
            continue

        print(f"[summarize] Calling DeepSeek ({llm_model}) for {len(new_articles)} papers...")
        summaries = batch_summarize(
            articles=new_articles,
            source_name=source_name,
            api_key=llm_api_key,
            model=llm_model,
            focus_keywords=focus_keywords,
        )
        print(f"[summarize] Got {len(summaries)} structured summaries")

        merged = _merge(new_articles, summaries)
        all_papers.extend(merged)

    # --- Sort ---
    rating_order = {"必读": 0, "值得关注": 1, "可略读": 2, "不相关": 3, "": 4}
    all_papers.sort(key=lambda p: (
        0 if p.get("is_focus") else 1,
        rating_order.get(p.get("rating", ""), 4),
    ))

    # --- Generate report ---
    st = db_stats(db_path=db_path)
    st["today_new"] = today_new

    html = generate_report(date=date_display, papers=all_papers, stats=st)

    # --- Save ---
    output_dir = cfg.get("output", {}).get("dir", f"./output/{user_name}")
    saved_path = save_report(html, date_display, output_dir)
    print(f"\n[report] Saved to: {saved_path}")

    # --- Cleanup ---
    keep_days = cfg.get("output", {}).get("keep_days", 90)
    cleanup_old_reports(output_dir, keep_days)

    # --- Email ---
    email_cfg = cfg.get("email", {})
    if email_cfg.get("enabled", False):
        email_password = email_cfg.get("password", "")
        if email_password and not email_password.startswith("${"):
            print(f"[email] Sending report to {email_cfg.get('sender', '')}...")
            success = send_email(
                html_body=html,
                date=date_display,
                smtp_host=email_cfg["smtp_host"],
                smtp_port=email_cfg["smtp_port"],
                sender=email_cfg["sender"],
                password=email_password,
                receiver=email_cfg.get("receiver", email_cfg["sender"]),
            )
            if success:
                print(f"[email] Sent successfully")
            else:
                print(f"[email] Failed to send")
        else:
            print(f"[email] Skipped: QQ_SMTP_PASSWORD not configured")
    else:
        print(f"[email] Email disabled in config")

    print(f"\n[done] [{label}] {today_new} new papers today.")


def main():
    script_dir = Path(__file__).parent
    os.chdir(str(script_dir))

    # --- Discover user configs ---
    users_dir = script_dir / "users"
    if users_dir.is_dir():
        configs = sorted(users_dir.glob("*.yaml"))
    else:
        configs = []

    # Fallback: single config.yaml in root
    if not configs:
        root_config = script_dir / "config.yaml"
        if root_config.exists():
            configs = [root_config]

    if not configs:
        print("[error] No config files found. Place .yaml files in users/ or config.yaml in root.")
        sys.exit(1)

    print(f"[info] Found {len(configs)} user config(s): {[c.stem for c in configs]}")

    for cfg_path in configs:
        try:
            process_user(str(cfg_path))
        except Exception as e:
            print(f"[error] Failed to process {cfg_path.stem}: {e}")
            continue

    print(f"\n{'='*60}")
    print(f"[done] All user digests complete.")


if __name__ == "__main__":
    main()
