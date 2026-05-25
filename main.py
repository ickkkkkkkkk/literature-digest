#!/usr/bin/env python3
"""
Daily Literature Digest — 脊柱骨科+医学生信文献日报

Pipeline:
  1. Search PubMed with two query sets
  2. Deduplicate against history database
  3. Summarize new papers with Claude API
  4. Generate HTML report
  5. Email the report
"""

import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

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


def load_config(path: str = "config.yaml") -> dict:
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


def main():
    # --- Load config ---
    script_dir = Path(__file__).parent
    config_path = script_dir / "config.yaml"

    if not config_path.exists():
        print(f"[error] Config file not found: {config_path}")
        sys.exit(1)

    cfg = load_config(str(config_path))

    # Change to script dir so relative paths (output/, history.db) resolve correctly
    os.chdir(str(script_dir))

    # --- Resolve secrets ---
    pubmed_email = cfg["pubmed"]["email"]
    pubmed_api_key = cfg["pubmed"].get("api_key", "")
    if "${PUBMED_EMAIL}" == pubmed_email or not pubmed_email or "your-email" in pubmed_email:
        pubmed_email = os.environ.get("PUBMED_EMAIL", "")
    if not pubmed_email:
        print("[error] PubMed email is required. Set it in config.yaml or PUBMED_EMAIL env var.")
        sys.exit(1)

    claude_api_key = cfg["claude"]["api_key"]
    if not claude_api_key or claude_api_key.startswith("${"):
        print("[error] ANTHROPIC_API_KEY is required. Set it via environment variable.")
        sys.exit(1)

    retmax = cfg["pubmed"].get("retmax", 30)
    lookback = cfg["pubmed"].get("lookback_days", 2)
    claude_model = cfg["claude"].get("model", "claude-haiku-4-5-20251001")
    claude_max_tokens = cfg["claude"].get("max_tokens", 800)

    # --- Date ---
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Beijing time for display
    beijing_now = datetime.now(timezone(timedelta(hours=8)))
    date_display = beijing_now.strftime("%Y-%m-%d")

    # Track today's new count for stats
    today_new = 0
    all_summaries = {}

    # --- Process each query ---
    for query_key, query_cfg in cfg["queries"].items():
        source_name = query_cfg["name"]
        query_string = query_cfg["query"]

        print(f"\n{'='*60}")
        print(f"[fetch] Searching PubMed: {source_name}")
        print(f"{'='*60}")

        # 1. Fetch
        articles = search_pubmed(
            query=query_string,
            email=pubmed_email,
            api_key=pubmed_api_key,
            retmax=retmax,
            lookback_days=lookback,
        )
        print(f"[fetch] Retrieved {len(articles)} articles with abstracts")

        # 2. Deduplicate
        new_articles = filter_new(articles, source=source_name)
        today_new += len(new_articles)
        print(f"[dedup] {len(new_articles)} new, {len(articles) - len(new_articles)} already seen")

        if not new_articles:
            all_summaries[source_name] = ""
            continue

        # 3. Summarize
        print(f"[summarize] Calling Claude ({claude_model}) for {len(new_articles)} papers...")
        summary = batch_summarize(
            articles=new_articles,
            source_name=source_name,
            api_key=claude_api_key,
            model=claude_model,
        )
        all_summaries[source_name] = summary
        print(f"[summarize] Done. Summary length: {len(summary)} chars")

    # --- Generate report ---
    st = db_stats()
    st["today_new"] = today_new

    query1_name = cfg["queries"]["spine_ortho"]["name"]
    query2_name = cfg["queries"]["medical_bioinfo"]["name"]

    html = generate_report(
        date=date_display,
        spine_ortho_summary=all_summaries.get(query1_name, ""),
        medical_bioinfo_summary=all_summaries.get(query2_name, ""),
        stats=st,
        query1_name=query1_name,
        query2_name=query2_name,
    )

    # --- Save ---
    output_dir = cfg.get("output", {}).get("dir", "./output")
    saved_path = save_report(html, date_display, output_dir)
    print(f"\n[report] Saved to: {saved_path}")

    # --- Cleanup old reports ---
    keep_days = cfg.get("output", {}).get("keep_days", 90)
    cleanup_old_reports(output_dir, keep_days)

    # --- Email ---
    email_cfg = cfg.get("email", {})
    if email_cfg.get("enabled", False):
        email_password = email_cfg.get("password", "")
        if email_password and not email_password.startswith("${"):
            print("[email] Sending report...")
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
                print("[email] Sent successfully")
            else:
                print("[email] Failed to send")
        else:
            print("[email] Skipped: QQ_SMTP_PASSWORD not configured")
    else:
        print("[email] Email disabled in config")

    print(f"\n[done] Literature digest complete. {today_new} new papers today.")


if __name__ == "__main__":
    main()
