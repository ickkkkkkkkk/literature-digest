"""
PubMed Entrez API fetcher.
Searches for recent spine/orthopedic basic research and medical bioinformatics papers.
"""

import time
from datetime import datetime, timedelta
from typing import Optional

from Bio import Entrez


def _clean_text(text: str) -> str:
    """Clean up XML text nodes — collapse whitespace, strip."""
    if not text:
        return ""
    return " ".join(text.split())


def _safe_get(obj, key, default=""):
    """Get attribute from BioPython-parsed element (dict-like or StringElement)."""
    if hasattr(obj, "get"):
        return obj.get(key, default)
    return default


def _parse_article(article_xml) -> Optional[dict]:
    """Parse a single PubmedArticle XML element into a flat dict."""
    try:
        medline = article_xml["MedlineCitation"]
        art = medline["Article"]
        pmid = str(medline["PMID"])
    except (KeyError, IndexError, TypeError):
        return None

    # --- title ---
    title = _clean_text(_safe_get(art, "ArticleTitle"))

    # --- abstract ---
    abstract_parts = []
    abstract_elem = _safe_get(art, "Abstract", {})
    if not isinstance(abstract_elem, dict):
        abstract_elem = {}
    for at in abstract_elem.get("AbstractText", []):
        if hasattr(at, "get"):
            label = _safe_get(at, "Label")
            body = _clean_text(str(at))
        else:
            label = ""
            body = _clean_text(str(at))
        if label:
            abstract_parts.append(f"**{label}**: {body}")
        else:
            abstract_parts.append(body)
    abstract = "\n\n".join(abstract_parts)

    # --- authors (first 5) ---
    authors = []
    for au in art.get("AuthorList", []):
        last = _safe_get(au, "LastName")
        init = _safe_get(au, "Initials")
        if last:
            authors.append(f"{last} {init}")
    author_str = ", ".join(authors[:5])
    if len(authors) > 5:
        author_str += f" et al."

    # --- journal ---
    journal_elem = _safe_get(art, "Journal", {})
    if not isinstance(journal_elem, dict):
        journal_elem = {}
    journal = _clean_text(_safe_get(journal_elem, "Title"))

    # --- date ---
    pubdate_xml = _safe_get(journal_elem, "JournalIssue", {})
    if not isinstance(pubdate_xml, dict):
        pubdate_xml = {}
    pubdate_xml = _safe_get(pubdate_xml, "PubDate", {})
    if not isinstance(pubdate_xml, dict):
        pubdate_xml = {}
    year = _safe_get(pubdate_xml, "Year")
    month = _safe_get(pubdate_xml, "Month")
    day = _safe_get(pubdate_xml, "Day", "1")
    pubdate = f"{year}-{month}-{day}" if year else ""

    # --- DOI ---
    doi = ""
    for eid in art.get("ELocationID", []):
        if _safe_get(eid, "EIdType") == "doi":
            doi = _clean_text(str(eid))

    # --- keywords ---
    keywords = []
    for kw in medline.get("KeywordList", [[]])[0]:
        if isinstance(kw, str):
            keywords.append(kw)
        else:
            keywords.append(str(kw))

    return {
        "pmid": pmid,
        "doi": doi,
        "title": title,
        "authors": author_str,
        "journal": journal,
        "pubdate": pubdate,
        "abstract": abstract,
        "keywords": keywords,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    }


def search_pubmed(
    query: str,
    email: str,
    api_key: str = "",
    retmax: int = 30,
    lookback_days: int = 2,
) -> list[dict]:
    """
    Search PubMed and return parsed article dicts.

    Args:
        query: PubMed query string
        email: NCBI-required contact email
        api_key: optional NCBI API key for higher rate limits
        retmax: max PMIDs to retrieve
        lookback_days: days to look back (also filtered by query date range)

    Returns:
        List of article dicts with keys: pmid, doi, title, authors, journal,
        pubdate, abstract, keywords, url
    """
    Entrez.email = email
    if api_key:
        Entrez.api_key = api_key

    # Search
    handle = Entrez.esearch(
        db="pubmed",
        term=query,
        retmax=retmax,
        sort="relevance",
        reldate=lookback_days,
        datetype="edat",
    )
    result = Entrez.read(handle)
    handle.close()

    pmids = result["IdList"]
    if not pmids:
        return []

    # Rate limit: without API key, NCBI allows 3 req/s; with key, 10 req/s
    if not api_key:
        time.sleep(0.4)
    else:
        time.sleep(0.15)

    # Fetch abstracts in batch
    handle = Entrez.efetch(
        db="pubmed",
        id=",".join(pmids),
        rettype="xml",
        retmode="xml",
    )
    articles_xml = Entrez.read(handle)
    handle.close()

    articles = []
    for article_xml in articles_xml.get("PubmedArticle", []):
        parsed = _parse_article(article_xml)
        if parsed and parsed["abstract"]:
            articles.append(parsed)

    return articles
