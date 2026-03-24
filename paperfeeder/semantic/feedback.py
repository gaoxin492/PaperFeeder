"""Human-in-the-loop feedback utilities for manifest export, queue capture, and apply."""

from __future__ import annotations

import base64
import html
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote_plus
from urllib.parse import urlsplit, urlunsplit

from .resolver import SemanticPaperResolver


ALLOWED_LABELS = {"positive", "negative", "undecided"}
DEFAULT_QUEUE_PATH = "semantic_feedback_queue.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + pad)


def normalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower() if parts.scheme else "https"
        netloc = parts.netloc.lower()
        path = parts.path.rstrip("/")
        return urlunsplit((scheme, netloc, path, "", ""))
    except Exception:
        return url.strip().lower().rstrip("/")


def _normalize_title(title: str) -> str:
    return " ".join((title or "").strip().lower().split())


def normalize_paper_id(value: Any) -> str:
    """Normalize seed paper IDs (numeric corpus IDs -> CorpusId:<id>)."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if s.isdigit():
        return f"CorpusId:{s}"
    return s


def _extract_report_urls(report_html: str) -> set[str]:
    import re

    if not report_html:
        return set()
    raw_urls = re.findall(r'href=["\']([^"\']+)["\']', report_html, flags=re.IGNORECASE)
    return {normalize_url(u) for u in raw_urls if normalize_url(u)}


def make_email_safe_report_html(report_html: str) -> str:
    """Remove script tags so desktop email clients do not expose raw JS as text."""
    if not report_html:
        return report_html

    import re

    return re.sub(r"<script\b[^>]*>.*?</script\s*>", "", report_html, flags=re.IGNORECASE | re.DOTALL)


def build_run_id(now: datetime | None = None) -> str:
    dt = now or _utc_now()
    return dt.strftime("%Y-%m-%dT%H-%M-%SZ")


def create_feedback_token(claims: Dict[str, Any], signing_secret: str) -> str:
    """Create signed token for one-click feedback links."""
    if not signing_secret:
        raise ValueError("signing_secret is required")
    payload_json = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url_encode(payload_json)
    sig = hmac.new(signing_secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_b64}.{_b64url_encode(sig)}"


def verify_feedback_token(token: str, signing_secret: str) -> Dict[str, Any]:
    """Verify signed feedback token and return claims."""
    if not token or "." not in token:
        raise ValueError("invalid token format")
    if not signing_secret:
        raise ValueError("signing_secret is required")
    payload_b64, sig_b64 = token.split(".", 1)
    expected_sig = hmac.new(signing_secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    got_sig = _b64url_decode(sig_b64)
    if not hmac.compare_digest(expected_sig, got_sig):
        raise ValueError("invalid token signature")
    claims = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    if not isinstance(claims, dict):
        raise ValueError("invalid token claims")
    exp = claims.get("exp")
    exp_dt = _parse_iso(str(exp)) if exp else None
    if exp_dt is None:
        raise ValueError("invalid token expiry")
    if exp_dt < _utc_now():
        raise ValueError("expired token")
    label = str(claims.get("label", "")).strip().lower()
    if label not in ALLOWED_LABELS:
        raise ValueError("invalid label in token")
    if not str(claims.get("run_id", "")).strip() or not str(claims.get("item_id", "")).strip():
        raise ValueError("missing run_id/item_id in token")
    return claims


def _build_action_links(
    base_url: str,
    run_id: str,
    item_id: str,
    semantic_paper_id: str,
    reviewer: str,
    signing_secret: str,
    token_ttl_days: int = 7,
) -> Dict[str, str]:
    base = base_url.rstrip("/")
    out: Dict[str, str] = {}
    exp = _to_iso(_utc_now().replace(microsecond=0) + timedelta(days=max(1, token_ttl_days)))
    for label in ("positive", "negative", "undecided"):
        claims = {
            "v": 1,
            "run_id": run_id,
            "item_id": item_id,
            "semantic_paper_id": semantic_paper_id,
            "label": label,
            "reviewer": reviewer,
            "exp": exp,
        }
        token = create_feedback_token(claims, signing_secret)
        out[label] = f"{base}/feedback?t={quote_plus(token)}"
    return out


def build_feedback_run_view_url(base_url: str, run_id: str) -> str:
    base = (base_url or "").rstrip("/")
    rid = str(run_id or "").strip()
    if not base or not rid:
        return ""
    return f"{base}/run?run_id={quote_plus(rid)}"


def export_run_feedback_manifest(
    final_papers: Iterable[Any],
    report_html: str,
    output_dir: str = "artifacts",
    run_id: str | None = None,
    feedback_endpoint_base_url: str = "",
    feedback_link_signing_secret: str = "",
    reviewer: str = "",
    token_ttl_days: int = 7,
    semantic_scholar_api_key: str = "",
    resolver_enabled: bool = True,
    resolver_timeout_sec: int = 8,
    resolver_max_lookups: int = 25,
    resolver_no_key_max_lookups: int = 10,
    resolver_time_budget_sec: int = 20,
    resolver_run_cache_enabled: bool = True,
) -> Tuple[Path, Path] | None:
    """Export final report paper mappings for human feedback."""
    papers = list(final_papers or [])
    if not papers:
        return None

    visible_urls = _extract_report_urls(report_html)
    entries: List[Dict[str, Any]] = []
    resolver = SemanticPaperResolver(
        api_key=(semantic_scholar_api_key or "").strip(),
        timeout_sec=int(resolver_timeout_sec),
        max_lookups=int(resolver_max_lookups),
        no_key_max_lookups=int(resolver_no_key_max_lookups),
        time_budget_sec=int(resolver_time_budget_sec),
        enable_cache=bool(resolver_run_cache_enabled),
    )
    resolver_warnings: List[str] = []

    for p in papers:
        url = getattr(p, "url", "") or ""
        norm_url = normalize_url(url)
        if visible_urls and norm_url not in visible_urls:
            continue
        source = str(getattr(getattr(p, "source", None), "value", getattr(p, "source", "")) or "").strip()
        existing_semantic_id = normalize_paper_id(getattr(p, "semantic_paper_id", "")) or ""
        title = getattr(p, "title", "") or ""
        arxiv_id = str(getattr(p, "arxiv_id", "") or "")
        paper_year: Optional[int] = None
        published = getattr(p, "published_date", None)
        if hasattr(published, "year"):
            try:
                paper_year = int(published.year)
            except Exception:
                paper_year = None
        author_names = []
        for author in (getattr(p, "authors", []) or []):
            name = str(getattr(author, "name", "") or "").strip()
            if name:
                author_names.append(name)

        resolution_status = "existing" if existing_semantic_id else "unresolved"
        resolution_method = "existing" if existing_semantic_id else "none"
        resolution_error = ""
        semantic_id = existing_semantic_id
        if (
            resolver_enabled
            and not semantic_id
            and source in {"arxiv", "huggingface"}
        ):
            resolved = resolver.resolve(
                title=title,
                url=url,
                arxiv_id=arxiv_id,
                existing_semantic_paper_id=existing_semantic_id,
                source=source,
                paper_year=paper_year,
                author_names=author_names,
            )
            semantic_id = normalize_paper_id(resolved.semantic_paper_id) or ""
            resolution_status = resolved.resolution_status
            resolution_method = resolved.resolution_method
            resolution_error = resolved.error
            if resolution_error:
                resolver_warnings.append(
                    f"{title[:80]}: {resolution_method}:{resolution_error}"
                )

        feedback_enabled = bool(semantic_id)
        entries.append(
            {
                "title": title,
                "url": url,
                "arxiv_id": arxiv_id or None,
                "semantic_paper_id": semantic_id or None,
                "resolution_status": resolution_status,
                "resolution_method": resolution_method,
                "feedback_enabled": feedback_enabled,
                "resolution_error": resolution_error or None,
            }
        )

    if not entries:
        return None

    rid = run_id or build_run_id()
    for idx, e in enumerate(entries, 1):
        e["item_id"] = f"p{idx:02d}"
        semantic_paper_id = normalize_paper_id(e.get("semantic_paper_id"))
        if feedback_endpoint_base_url and feedback_link_signing_secret and semantic_paper_id:
            e["action_links"] = _build_action_links(
                base_url=feedback_endpoint_base_url,
                run_id=rid,
                item_id=e["item_id"],
                semantic_paper_id=semantic_paper_id,
                reviewer=reviewer,
                signing_secret=feedback_link_signing_secret,
                token_ttl_days=token_ttl_days,
            )

    payload = {
        "version": "v1",
        "run_id": rid,
        "generated_at": _to_iso(_utc_now()),
        "papers": entries,
        "resolution_stats": resolver.stats(),
        "resolution_warnings": resolver_warnings,
    }

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / f"run_feedback_manifest_{rid}.json"
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n")

    # Emit a starter questionnaire for direct copy/edit by reviewers.
    feedback_template = {
        "version": "v1",
        "run_id": rid,
        "reviewer": "",
        "reviewed_at": _to_iso(_utc_now()),
        "labels": [
            {
                "item_id": p["item_id"],
                "label": "undecided",
                "note": "",
            }
            for p in entries
            if bool(p.get("feedback_enabled"))
        ],
    }
    questionnaire_path = out_dir / f"semantic_feedback_template_{rid}.json"
    questionnaire_path.write_text(json.dumps(feedback_template, indent=2) + "\n")

    return manifest_path, questionnaire_path


def inject_feedback_actions_into_report(report_html: str, manifest_path: str) -> str:
    """Inject one-click feedback links beside paper links in report html."""
    if not report_html or not manifest_path:
        return report_html
    manifest = _load_json(manifest_path)
    papers = manifest.get("papers", []) or []
    by_url: Dict[str, Dict[str, str]] = {}
    for p in papers:
        if not isinstance(p, dict):
            continue
        action_links = p.get("action_links")
        if not isinstance(action_links, dict):
            continue
        norm = normalize_url(str(p.get("url", "")))
        if norm:
            by_url[norm] = {k: str(v) for k, v in action_links.items() if isinstance(v, str)}
    if not by_url:
        return report_html

    import re

    def repl(match: re.Match) -> str:
        whole = match.group(0)
        href = match.group(1) or ""
        norm = normalize_url(href)
        links = by_url.get(norm)
        if not links:
            return whole
        actions = []
        if links.get("positive"):
            actions.append(f'<a class="pf-feedback-btn positive" href="{links["positive"]}">👍 Positive</a>')
        if links.get("negative"):
            actions.append(f'<a class="pf-feedback-btn negative" href="{links["negative"]}">👎 Negative</a>')
        if links.get("undecided"):
            actions.append(f'<a class="pf-feedback-btn undecided" href="{links["undecided"]}">🤔 Undecided</a>')
        if not actions:
            return whole
        action_html = '<span class="pf-feedback-actions">' + " ".join(actions) + "</span>"
        return whole + action_html

    updated = re.sub(r'<a\s+href=["\']([^"\']+)["\'][^>]*>.*?</a>', repl, report_html, flags=re.IGNORECASE)

    style = """
<style>
:root{color-scheme:light}
.pf-feedback-actions{display:inline-flex;gap:6px;margin-left:8px;vertical-align:middle;flex-wrap:wrap}
.pf-feedback-btn{font-size:.72em;padding:2px 6px;border-radius:10px;text-decoration:none;border:1px solid #ccc;background:#f8f8f8;color:#333}
.pf-feedback-btn.positive{border-color:#59a96a;background:#eff9f2;color:#1f6a30}
.pf-feedback-btn.negative{border-color:#c85f5f;background:#fff1f1;color:#8f1f1f}
.pf-feedback-btn.undecided{border-color:#7a7d91;background:#f4f5fa;color:#374151}
.pf-feedback-btn.is-loading{opacity:.6;pointer-events:none}
.pf-feedback-btn.is-selected{box-shadow:0 0 0 2px rgba(40,120,220,.22) inset}
.pf-feedback-toast{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%) scale(.94);min-width:240px;max-width:86vw;padding:14px 18px;border-radius:14px;font-size:15px;font-weight:700;text-align:center;z-index:9999;opacity:0;pointer-events:none;transition:opacity .22s ease,transform .22s ease;box-shadow:0 12px 40px rgba(8,16,40,.34)}
.pf-feedback-toast.show{opacity:1;transform:translate(-50%,-50%) scale(1)}
.pf-feedback-toast.ok{color:#fff;background:linear-gradient(135deg,#2f855a,#38a169)}
.pf-feedback-toast.bad{color:#fff;background:linear-gradient(135deg,#b83280,#d53f8c)}
.pf-feedback-toast.err{color:#fff;background:linear-gradient(135deg,#2d3748,#4a5568)}
.pf-feedback-toast.neu{color:#fff;background:linear-gradient(135deg,#4b5563,#6b7280)}
.pf-feedback-toast .icon{margin-right:8px}
@keyframes pfPulse{0%{transform:translate(-50%,-50%) scale(.92)}55%{transform:translate(-50%,-50%) scale(1.04)}100%{transform:translate(-50%,-50%) scale(1)}}
.pf-feedback-toast.show{animation:pfPulse .34s ease}
</style>
"""
    script = """
<script>
(function(){
  function showToast(msg, tone){
    var t = document.querySelector('.pf-feedback-toast');
    if(!t){
      t = document.createElement('div');
      t.className = 'pf-feedback-toast';
      document.body.appendChild(t);
    }
    t.classList.remove('ok','bad','err');
    t.classList.add(tone || 'ok');
    t.innerHTML = msg;
    t.classList.add('show');
    setTimeout(function(){ t.classList.remove('show'); }, 1350);
  }
  document.addEventListener('click', async function(ev){
    var a = ev.target && ev.target.closest ? ev.target.closest('a.pf-feedback-btn') : null;
    if(!a) return;
    ev.preventDefault();
    if(a.classList.contains('is-loading')) return;
    a.classList.add('is-loading');
    try{
      var resp = await fetch(a.href, { method: 'GET', credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' }});
      if(!resp.ok){
        showToast('<span class="icon">⚠️</span>Feedback failed', 'bad');
        return;
      }
      var wrap = a.closest('.pf-feedback-actions');
      if(wrap){
        wrap.querySelectorAll('.pf-feedback-btn').forEach(function(btn){ btn.classList.remove('is-selected'); });
      }
      a.classList.add('is-selected');
      if(a.classList.contains('positive')){
        showToast('<span class="icon">✅</span>Saved as Positive', 'ok');
      }else if(a.classList.contains('undecided')){
        showToast('<span class="icon">↩️</span>Reset to Undecided', 'neu');
      }else{
        showToast('<span class="icon">🧪</span>Saved as Negative', 'bad');
      }
    }catch(_err){
      showToast('<span class="icon">📡</span>Network error', 'err');
    }finally{
      a.classList.remove('is-loading');
    }
  });
})();
</script>
"""
    if "</head>" in updated:
        return updated.replace("</head>", style + "\n" + script + "\n</head>", 1)
    return style + "\n" + script + "\n" + updated


def append_feedback_fallback_strip(report_html: str, manifest_path: str) -> str:
    """
    Add a bottom section with 👍/👎 per manifest row when action_links exist.

    LLM-generated HTML often uses different link URLs than paper.url, so
    inject_feedback_actions_into_report may not match; this strip always shows
    controls when the manifest has signed links.
    """
    if not report_html or not manifest_path:
        return report_html
    manifest = _load_json(manifest_path)
    papers = manifest.get("papers", []) or []
    rows: List[str] = []
    for p in papers:
        if not isinstance(p, dict):
            continue
        links = p.get("action_links")
        if not isinstance(links, dict) or not links:
            continue
        title = html.escape(str(p.get("title", "Paper"))[:220])
        item_id = html.escape(str(p.get("item_id", "")))
        chips: List[str] = []
        if isinstance(links.get("positive"), str):
            chips.append(f'<a class="pf-feedback-btn positive" href="{links["positive"]}">👍 Like</a>')
        if isinstance(links.get("negative"), str):
            chips.append(f'<a class="pf-feedback-btn negative" href="{links["negative"]}">👎 Dislike</a>')
        if isinstance(links.get("undecided"), str):
            chips.append(f'<a class="pf-feedback-btn undecided" href="{links["undecided"]}">🤔 Undecided</a>')
        if not chips:
            continue
        actions_html = " ".join(chips)
        rows.append(
            '<div class="pf-feedback-fallback-row" style="display:flex;flex-wrap:wrap;align-items:center;'
            'gap:6px;margin-bottom:6px;padding:6px 8px;background:#f8fafc;border-radius:8px;'
            'border:1px solid #e2e8f0;">'
            f'<span style="flex:1;min-width:12rem;font-size:0.9rem;color:#334155;line-height:1.4;">'
            f"<strong>{item_id}</strong> · {title}</span>"
            f'<span class="pf-feedback-actions" style="margin-left:0;">{actions_html}</span></div>'
        )
    if not rows:
        return report_html

    block = (
        '<div class="pf-feedback-fallback" style="margin:10px 0 4px;padding:8px 8px;border-radius:10px;'
        'border:1px solid #bae6fd;background:linear-gradient(180deg,#f0f9ff,#fff);">'
        '<p style="margin:0 0 6px;font-size:0.85rem;font-weight:700;color:#0369a1;">Quick feedback (same as inline buttons)</p>'
        + "".join(rows)
        + "</div>"
    )
    lower = report_html.lower()
    idx = lower.rfind("</body>")
    if idx != -1:
        return report_html[:idx] + block + report_html[idx:]
    return report_html + block


def inject_feedback_entry_link(report_html: str, run_view_url: str) -> str:
    """Inject a single run-level feedback entry link into report html."""
    if not report_html or not run_view_url:
        return report_html
    block = f"""
<div class="pf-feedback-entry" style="margin:8px 0;padding:8px;border:1px solid #d5deea;border-radius:8px;background:#f8fbff;">
  <strong>Feedback:</strong> Review this digest and submit preferences in the web viewer.
  <a href="{run_view_url}" style="margin-left:8px;">Open Feedback Web Viewer</a>
</div>
"""
    if "<body" in report_html and ">" in report_html:
        import re

        return re.sub(r"(<body[^>]*>)", r"\1\n" + block, report_html, count=1, flags=re.IGNORECASE)
    return block + "\n" + report_html


def get_run_id_from_manifest(manifest_path: str) -> str:
    data = _load_json(manifest_path)
    return str(data.get("run_id", "")).strip()


def publish_feedback_run_to_d1(
    *,
    manifest_path: str,
    report_html: str,
    account_id: str | None = None,
    api_token: str | None = None,
    database_id: str | None = None,
) -> str:
    """Persist run-level web viewer content into D1 and return run_id."""
    acc = account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    tok = api_token or os.getenv("CLOUDFLARE_API_TOKEN", "")
    dbid = database_id or os.getenv("D1_DATABASE_ID", "")
    if not acc or not tok or not dbid:
        raise ValueError("Missing D1 credentials (account_id/api_token/database_id)")
    manifest = _load_json(manifest_path)
    run_id = str(manifest.get("run_id", "")).strip()
    if not run_id:
        raise ValueError("manifest run_id is required")

    create_sql = """
    CREATE TABLE IF NOT EXISTS feedback_runs (
      run_id TEXT PRIMARY KEY,
      created_at TEXT NOT NULL,
      report_html TEXT NOT NULL
    );
    """
    _d1_execute(acc, tok, dbid, create_sql)

    upsert_sql = (
        "INSERT INTO feedback_runs (run_id, created_at, report_html) VALUES ("
        f"{_sql_quote(run_id)}, {_sql_quote(_to_iso(_utc_now()))}, {_sql_quote(report_html)}"
        ") ON CONFLICT(run_id) DO UPDATE SET "
        "created_at=excluded.created_at, report_html=excluded.report_html"
    )
    _d1_execute(acc, tok, dbid, upsert_sql)
    return run_id


def reset_feedback_d1_state(
    *,
    account_id: str | None = None,
    api_token: str | None = None,
    database_id: str | None = None,
) -> Dict[str, Any]:
    """Delete all feedback run HTML and queued/applied feedback events from D1."""
    acc = account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    tok = api_token or os.getenv("CLOUDFLARE_API_TOKEN", "")
    dbid = database_id or os.getenv("D1_DATABASE_ID", "")
    if not acc or not tok or not dbid:
        raise ValueError("Missing D1 credentials (account_id/api_token/database_id)")

    events_before_rows = _normalize_d1_rows(_d1_query(acc, tok, dbid, "SELECT COUNT(*) AS count FROM feedback_events"))
    runs_before_rows = _normalize_d1_rows(_d1_query(acc, tok, dbid, "SELECT COUNT(*) AS count FROM feedback_runs"))
    events_before = int(events_before_rows[0].get("count", 0) or 0) if events_before_rows else 0
    runs_before = int(runs_before_rows[0].get("count", 0) or 0) if runs_before_rows else 0

    _d1_execute(acc, tok, dbid, "DELETE FROM feedback_events")
    _d1_execute(acc, tok, dbid, "DELETE FROM feedback_runs")

    return {
        "events_deleted": events_before,
        "runs_deleted": runs_before,
        "database_id": dbid,
    }


def _load_json(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise ValueError(f"File not found: {path}")
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        raise ValueError(f"Invalid JSON in {path}: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return data


def _load_json_or_default(path: str, default: Dict[str, Any]) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return default
    return _load_json(path)


def _sort_seed_ids(values: Iterable[str]) -> List[str]:
    def sort_key(v: str) -> Tuple[int, str]:
        s = normalize_paper_id(v)
        if s.startswith("CorpusId:"):
            tail = s.split(":", 1)[1]
            if tail.isdigit():
                return (0, f"{int(tail):020d}")
        return (1, s.lower())

    return sorted({normalize_paper_id(v) for v in values if normalize_paper_id(v)}, key=sort_key)


def _load_queue(path: str = DEFAULT_QUEUE_PATH) -> Dict[str, Any]:
    data = _load_json_or_default(path, {"version": "v1", "events": []})
    events = data.get("events", [])
    if not isinstance(events, list):
        raise ValueError("queue.events must be an array")
    return {"version": str(data.get("version", "v1")), "events": events}


def _save_queue(data: Dict[str, Any], path: str = DEFAULT_QUEUE_PATH) -> None:
    Path(path).write_text(json.dumps(data, indent=2) + "\n")


def queue_feedback_event(
    *,
    run_id: str,
    item_id: str,
    label: str,
    reviewer: str,
    source: str = "email_link",
    queue_path: str = DEFAULT_QUEUE_PATH,
    resolved_semantic_paper_id: str = "",
) -> Dict[str, Any]:
    label = str(label).strip().lower()
    if label not in ALLOWED_LABELS:
        raise ValueError("invalid label")
    if not run_id or not item_id:
        raise ValueError("run_id and item_id are required")
    data = _load_queue(queue_path)
    now = _to_iso(_utc_now())
    event = {
        "event_id": f"evt_{uuid.uuid4().hex[:16]}",
        "run_id": str(run_id),
        "item_id": str(item_id),
        "label": label,
        "reviewer": str(reviewer or ""),
        "created_at": now,
        "source": str(source or "unknown"),
        "status": "pending",
        "resolved_semantic_paper_id": normalize_paper_id(resolved_semantic_paper_id) or None,
        "applied_at": None,
        "error": None,
    }
    data["events"].append(event)
    _save_queue(data, queue_path)
    return event


def ingest_feedback_token(
    token: str,
    signing_secret: str | None = None,
    queue_path: str = DEFAULT_QUEUE_PATH,
    source: str = "email_link",
) -> Dict[str, Any]:
    """Validate one-click token and append a pending queue event."""
    secret = signing_secret or os.getenv("FEEDBACK_LINK_SIGNING_SECRET", "")
    claims = verify_feedback_token(token, secret)
    return queue_feedback_event(
        run_id=str(claims.get("run_id", "")),
        item_id=str(claims.get("item_id", "")),
        label=str(claims.get("label", "")),
        reviewer=str(claims.get("reviewer", "")),
        source=source,
        queue_path=queue_path,
        resolved_semantic_paper_id=str(claims.get("semantic_paper_id", "")),
    )


def apply_feedback_to_seeds(
    feedback_path: str = "semantic_feedback.json",
    manifest_path: str = "",
    seeds_path: str = "state/semantic/seeds.json",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Validate feedback and deterministically update seed file."""
    if not manifest_path:
        raise ValueError("manifest_path is required")

    manifest = _load_json(manifest_path)
    feedback = _load_json(feedback_path)

    m_run_id = str(manifest.get("run_id", "")).strip()
    f_run_id = str(feedback.get("run_id", "")).strip()
    if not m_run_id or not f_run_id:
        raise ValueError("Both manifest.run_id and feedback.run_id are required")
    if m_run_id != f_run_id:
        raise ValueError(f"run_id mismatch: manifest={m_run_id}, feedback={f_run_id}")

    reviewer = str(feedback.get("reviewer", "")).strip()
    reviewed_at = str(feedback.get("reviewed_at", "")).strip()
    if not reviewer:
        raise ValueError("feedback.reviewer is required")
    if _parse_iso(reviewed_at) is None:
        raise ValueError("feedback.reviewed_at must be ISO-8601 timestamp")

    papers = manifest.get("papers", [])
    if not isinstance(papers, list):
        raise ValueError("manifest.papers must be an array")

    labels = feedback.get("labels", [])
    if not isinstance(labels, list):
        raise ValueError("feedback.labels must be an array")

    by_item_id: Dict[str, Dict[str, Any]] = {}
    by_semantic_id: Dict[str, Dict[str, Any]] = {}
    by_title_url: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for p in papers:
        if not isinstance(p, dict):
            continue
        item_id = str(p.get("item_id", "")).strip()
        title = str(p.get("title", "")).strip()
        url = str(p.get("url", "")).strip()
        semantic_id = normalize_paper_id(p.get("semantic_paper_id"))
        if item_id:
            by_item_id[item_id] = p
        if semantic_id:
            by_semantic_id[semantic_id] = p
        if title or url:
            by_title_url[(_normalize_title(title), normalize_url(url))] = p

    latest: Dict[str, Tuple[datetime, str]] = {}
    warnings: List[str] = []
    invalid_count = 0
    skipped_count = 0

    for idx, entry in enumerate(labels, 1):
        if not isinstance(entry, dict):
            invalid_count += 1
            warnings.append(f"label[{idx}] invalid: entry must be an object")
            continue

        label = str(entry.get("label", "")).strip().lower()
        if label not in ALLOWED_LABELS:
            invalid_count += 1
            warnings.append(f"label[{idx}] invalid label: {label!r}")
            continue

        label_ts = _parse_iso(str(entry.get("reviewed_at", "")).strip()) or _parse_iso(reviewed_at)
        if label_ts is None:
            invalid_count += 1
            warnings.append(f"label[{idx}] invalid reviewed_at")
            continue

        resolved = None
        item_id = str(entry.get("item_id", "")).strip()
        if item_id:
            resolved = by_item_id.get(item_id)

        if resolved is None:
            sem = normalize_paper_id(entry.get("semantic_paper_id"))
            if sem:
                resolved = by_semantic_id.get(sem)

        if resolved is None:
            title = _normalize_title(str(entry.get("title", "")))
            url = normalize_url(str(entry.get("url", "")))
            resolved = by_title_url.get((title, url))

        if resolved is None:
            skipped_count += 1
            warnings.append(f"label[{idx}] skipped: no matching paper in manifest")
            continue

        semantic_id = normalize_paper_id(resolved.get("semantic_paper_id"))
        if not semantic_id:
            skipped_count += 1
            warnings.append(f"label[{idx}] skipped: matched paper has no semantic_paper_id")
            continue

        current = latest.get(semantic_id)
        if current is None or label_ts >= current[0]:
            latest[semantic_id] = (label_ts, label)

    seeds_file = Path(seeds_path)
    if seeds_file.exists():
        seeds = _load_json(seeds_path)
    else:
        seeds = {}

    positive = set(normalize_paper_id(v) for v in seeds.get("positive_paper_ids", []) or [])
    negative = set(normalize_paper_id(v) for v in seeds.get("negative_paper_ids", []) or [])
    positive.discard("")
    negative.discard("")

    applied_count = 0
    for semantic_id, (_ts, label) in sorted(latest.items()):
        if label == "positive":
            positive.add(semantic_id)
            negative.discard(semantic_id)
            applied_count += 1
        elif label == "negative":
            negative.add(semantic_id)
            positive.discard(semantic_id)
            applied_count += 1
        else:
            positive.discard(semantic_id)
            negative.discard(semantic_id)
            applied_count += 1

    output = {
        "positive_paper_ids": _sort_seed_ids(positive),
        "negative_paper_ids": _sort_seed_ids(negative),
    }

    if not dry_run:
        seeds_file.write_text(json.dumps(output, indent=2) + "\n")

    return {
        "feedback_path": feedback_path,
        "manifest_path": manifest_path,
        "seeds_path": seeds_path,
        "dry_run": dry_run,
        "applied_count": applied_count,
        "invalid_count": invalid_count,
        "skipped_count": skipped_count,
        "warnings": warnings,
        "positive_total": len(output["positive_paper_ids"]),
        "negative_total": len(output["negative_paper_ids"]),
    }


def apply_feedback_queue_to_seeds(
    manifest_path: str,
    queue_path: str = DEFAULT_QUEUE_PATH,
    seeds_path: str = "state/semantic/seeds.json",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Apply pending queue events to seeds with status transitions."""
    manifest = _load_json(manifest_path)
    m_run_id = str(manifest.get("run_id", "")).strip()
    papers = manifest.get("papers", [])
    if not m_run_id or not isinstance(papers, list):
        raise ValueError("invalid manifest")

    by_item: Dict[str, Dict[str, Any]] = {}
    for p in papers:
        if not isinstance(p, dict):
            continue
        item_id = str(p.get("item_id", "")).strip()
        if item_id:
            by_item[item_id] = p

    queue = _load_queue(queue_path)
    events = queue["events"]

    pending_indices = [
        i for i, e in enumerate(events)
        if isinstance(e, dict)
        and str(e.get("status", "")).strip().lower() == "pending"
        and str(e.get("run_id", "")).strip() == m_run_id
    ]

    winners: Dict[str, Tuple[datetime, str, int]] = {}
    invalid_count = 0
    skipped_count = 0
    rejected_count = 0
    warnings: List[str] = []

    for idx in pending_indices:
        e = events[idx]
        label = str(e.get("label", "")).strip().lower()
        if label not in ALLOWED_LABELS:
            e["status"] = "rejected"
            e["error"] = "invalid label"
            rejected_count += 1
            invalid_count += 1
            continue
        item_id = str(e.get("item_id", "")).strip()
        mapped = by_item.get(item_id)
        if mapped is None:
            e["status"] = "rejected"
            e["error"] = "item_id not found in manifest"
            rejected_count += 1
            skipped_count += 1
            continue
        semantic_id = normalize_paper_id(mapped.get("semantic_paper_id"))
        if not semantic_id:
            e["status"] = "rejected"
            e["error"] = "no semantic_paper_id"
            rejected_count += 1
            skipped_count += 1
            continue
        e["resolved_semantic_paper_id"] = semantic_id
        ts = _parse_iso(str(e.get("created_at", ""))) or _utc_now()
        current = winners.get(semantic_id)
        if current is None:
            winners[semantic_id] = (ts, label, idx)
        else:
            cur_ts, _cur_label, cur_idx = current
            cur_event_id = str(events[cur_idx].get("event_id", ""))
            this_event_id = str(e.get("event_id", ""))
            if ts > cur_ts or (ts == cur_ts and this_event_id > cur_event_id):
                winners[semantic_id] = (ts, label, idx)

    seeds_file = Path(seeds_path)
    seeds = _load_json_or_default(seeds_path, {})
    positive = set(normalize_paper_id(v) for v in seeds.get("positive_paper_ids", []) or [])
    negative = set(normalize_paper_id(v) for v in seeds.get("negative_paper_ids", []) or [])
    positive.discard("")
    negative.discard("")

    applied_count = 0
    now_iso = _to_iso(_utc_now())
    winner_indices = {idx for (_ts, _label, idx) in winners.values()}

    for idx in pending_indices:
        e = events[idx]
        if str(e.get("status", "")).lower() != "pending":
            continue
        if idx not in winner_indices:
            e["status"] = "rejected"
            e["error"] = "superseded by newer event"
            rejected_count += 1
            continue
        semantic_id = normalize_paper_id(e.get("resolved_semantic_paper_id"))
        label = str(e.get("label", "")).strip().lower()
        if label == "positive":
            positive.add(semantic_id)
            negative.discard(semantic_id)
        elif label == "negative":
            negative.add(semantic_id)
            positive.discard(semantic_id)
        else:
            positive.discard(semantic_id)
            negative.discard(semantic_id)
        e["status"] = "applied"
        e["applied_at"] = now_iso
        e["error"] = None
        applied_count += 1

    output = {
        "positive_paper_ids": _sort_seed_ids(positive),
        "negative_paper_ids": _sort_seed_ids(negative),
    }
    if not dry_run:
        seeds_file.write_text(json.dumps(output, indent=2) + "\n")
        _save_queue(queue, queue_path)

    return {
        "mode": "queue",
        "manifest_path": manifest_path,
        "queue_path": queue_path,
        "seeds_path": seeds_path,
        "dry_run": dry_run,
        "applied_count": applied_count,
        "rejected_count": rejected_count,
        "invalid_count": invalid_count,
        "skipped_count": skipped_count,
        "warnings": warnings,
        "positive_total": len(output["positive_paper_ids"]),
        "negative_total": len(output["negative_paper_ids"]),
    }


def _sql_quote(value: Any) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def _d1_query(account_id: str, api_token: str, database_id: str, sql: str) -> List[Dict[str, Any]]:
    """Execute SQL against Cloudflare D1 via REST API and return rows."""
    if not account_id or not api_token or not database_id:
        raise ValueError("account_id, api_token, and database_id are required for D1 query")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query"
    req = urllib.request.Request(
        url,
        data=json.dumps({"sql": sql}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        details = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"D1 HTTP error {e.code}: {details}") from e
    except Exception as e:
        raise RuntimeError(f"D1 request failed: {e}") from e

    if not payload.get("success", False):
        raise RuntimeError(f"D1 query failed: {payload.get('errors', [])}")
    result = payload.get("result", [])
    if not result:
        return []
    rows = result[0].get("results", [])
    return rows if isinstance(rows, list) else []


def _d1_execute(account_id: str, api_token: str, database_id: str, sql: str) -> None:
    _ = _d1_query(account_id, api_token, database_id, sql)


def _build_manifest_index(
    manifest_file: str = "",
    manifests_dir: str = "artifacts",
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Build manifest index: run_id -> item_id -> paper entry."""
    run_map: Dict[str, Dict[str, Dict[str, Any]]] = {}
    paths: List[Path] = []
    if manifest_file:
        p = Path(manifest_file)
        if p.exists():
            paths.append(p)
    d = Path(manifests_dir)
    if d.exists() and d.is_dir():
        paths.extend(sorted(d.glob("run_feedback_manifest_*.json")))
    seen_paths = set()
    for p in paths:
        if str(p) in seen_paths:
            continue
        seen_paths.add(str(p))
        try:
            data = _load_json(str(p))
        except Exception:
            continue
        run_id = str(data.get("run_id", "")).strip()
        papers = data.get("papers", [])
        if not run_id or not isinstance(papers, list):
            continue
        bucket = run_map.setdefault(run_id, {})
        for paper in papers:
            if not isinstance(paper, dict):
                continue
            item_id = str(paper.get("item_id", "")).strip()
            if item_id:
                bucket[item_id] = paper
    return run_map


def _normalize_d1_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append(
            {
                "event_id": str(r.get("event_id", "")).strip(),
                "run_id": str(r.get("run_id", "")).strip(),
                "item_id": str(r.get("item_id", "")).strip(),
                "label": str(r.get("label", "")).strip().lower(),
                "reviewer": str(r.get("reviewer", "")).strip(),
                "created_at": str(r.get("created_at", "")).strip(),
                "source": str(r.get("source", "")).strip(),
                "status": str(r.get("status", "")).strip().lower() or "pending",
                "resolved_semantic_paper_id": normalize_paper_id(r.get("resolved_semantic_paper_id")) or "",
                "applied_at": str(r.get("applied_at", "")).strip() or None,
                "error": str(r.get("error", "")).strip() or None,
            }
        )
    return out


def apply_feedback_d1_to_seeds(
    *,
    seeds_path: str = "state/semantic/seeds.json",
    dry_run: bool = False,
    run_id_filter: str = "",
    manifest_file: str = "",
    manifests_dir: str = "artifacts",
    account_id: str | None = None,
    api_token: str | None = None,
    database_id: str | None = None,
) -> Dict[str, Any]:
    """
    Apply pending feedback events from D1.
    Default scope is all pending events; optional run_id_filter narrows scope.
    """
    acc = account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    tok = api_token or os.getenv("CLOUDFLARE_API_TOKEN", "")
    dbid = database_id or os.getenv("D1_DATABASE_ID", "")
    if not acc or not tok or not dbid:
        raise ValueError("Missing D1 credentials (account_id/api_token/database_id)")

    where = "status='pending'"
    if run_id_filter:
        where += f" AND run_id={_sql_quote(run_id_filter)}"
    sql = (
        "SELECT event_id, run_id, item_id, label, reviewer, created_at, source, status, "
        "resolved_semantic_paper_id, applied_at, error "
        f"FROM feedback_events WHERE {where} ORDER BY created_at ASC, event_id ASC"
    )
    rows = _normalize_d1_rows(_d1_query(acc, tok, dbid, sql))

    manifest_index = _build_manifest_index(manifest_file=manifest_file, manifests_dir=manifests_dir)

    seeds = _load_json_or_default(seeds_path, {})
    positive = set(normalize_paper_id(v) for v in seeds.get("positive_paper_ids", []) or [])
    negative = set(normalize_paper_id(v) for v in seeds.get("negative_paper_ids", []) or [])
    positive.discard("")
    negative.discard("")

    winners: Dict[str, Tuple[datetime, str, int]] = {}
    invalid_count = 0
    skipped_count = 0
    rejected_count = 0
    warnings: List[str] = []

    for idx, e in enumerate(rows):
        if e.get("status") != "pending":
            continue
        label = str(e.get("label", "")).strip().lower()
        if label not in ALLOWED_LABELS:
            e["status"] = "rejected"
            e["error"] = "invalid label"
            invalid_count += 1
            rejected_count += 1
            continue
        semantic_id = normalize_paper_id(e.get("resolved_semantic_paper_id", ""))
        if not semantic_id:
            run_id = str(e.get("run_id", ""))
            item_id = str(e.get("item_id", ""))
            mapped = manifest_index.get(run_id, {}).get(item_id)
            if mapped:
                semantic_id = normalize_paper_id(mapped.get("semantic_paper_id"))
        if not semantic_id:
            e["status"] = "rejected"
            e["error"] = "no semantic_paper_id mapping"
            skipped_count += 1
            rejected_count += 1
            continue
        e["resolved_semantic_paper_id"] = semantic_id
        ts = _parse_iso(str(e.get("created_at", ""))) or _utc_now()
        current = winners.get(semantic_id)
        if current is None:
            winners[semantic_id] = (ts, label, idx)
        else:
            cur_ts, _cur_label, cur_idx = current
            cur_eid = str(rows[cur_idx].get("event_id", ""))
            this_eid = str(e.get("event_id", ""))
            if ts > cur_ts or (ts == cur_ts and this_eid > cur_eid):
                winners[semantic_id] = (ts, label, idx)

    applied_count = 0
    now_iso = _to_iso(_utc_now())
    winner_indices = {idx for (_ts, _label, idx) in winners.values()}

    for idx, e in enumerate(rows):
        if e.get("status") != "pending":
            continue
        if idx not in winner_indices:
            e["status"] = "rejected"
            e["error"] = "superseded by newer event"
            rejected_count += 1
            continue
        semantic_id = normalize_paper_id(e.get("resolved_semantic_paper_id"))
        label = str(e.get("label", "")).strip().lower()
        if label == "positive":
            positive.add(semantic_id)
            negative.discard(semantic_id)
        elif label == "negative":
            negative.add(semantic_id)
            positive.discard(semantic_id)
        else:
            positive.discard(semantic_id)
            negative.discard(semantic_id)
        e["status"] = "applied"
        e["applied_at"] = now_iso
        e["error"] = None
        applied_count += 1

    output = {
        "positive_paper_ids": _sort_seed_ids(positive),
        "negative_paper_ids": _sort_seed_ids(negative),
    }

    if not dry_run:
        Path(seeds_path).write_text(json.dumps(output, indent=2) + "\n")
        for e in rows:
            event_id = str(e.get("event_id", ""))
            if not event_id:
                continue
            status = str(e.get("status", "pending"))
            if status not in {"applied", "rejected"}:
                continue
            update_sql = (
                "UPDATE feedback_events SET "
                f"status={_sql_quote(status)}, "
                f"applied_at={_sql_quote(e.get('applied_at')) if e.get('applied_at') else 'NULL'}, "
                f"error={_sql_quote(e.get('error')) if e.get('error') else 'NULL'}, "
                f"resolved_semantic_paper_id={_sql_quote(e.get('resolved_semantic_paper_id')) if e.get('resolved_semantic_paper_id') else 'NULL'} "
                f"WHERE event_id={_sql_quote(event_id)}"
            )
            _d1_execute(acc, tok, dbid, update_sql)

    return {
        "mode": "d1",
        "manifest_path": manifest_file or manifests_dir,
        "seeds_path": seeds_path,
        "dry_run": dry_run,
        "d1_pending_count": len(rows),
        "applied_count": applied_count,
        "rejected_count": rejected_count,
        "invalid_count": invalid_count,
        "skipped_count": skipped_count,
        "warnings": warnings,
        "positive_total": len(output["positive_paper_ids"]),
        "negative_total": len(output["negative_paper_ids"]),
    }

