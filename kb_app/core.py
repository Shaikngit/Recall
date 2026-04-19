from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from kb_app.blob_content import BlobContentStore


APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AZURE_FILES_CONTENT_ROOT = Path('/mounts/mykb-content')
CONTENT_STORE = BlobContentStore.from_environment(APP_ROOT)


def resolve_content_root() -> Path:
    if CONTENT_STORE.enabled:
        return CONTENT_STORE.runtime_root
    configured_root = os.getenv("MYKB_CONTENT_ROOT", "").strip()
    if configured_root:
        return Path(configured_root).expanduser().resolve()
    if DEFAULT_AZURE_FILES_CONTENT_ROOT.exists():
        return DEFAULT_AZURE_FILES_CONTENT_ROOT
    return APP_ROOT


CONTENT_ROOT = resolve_content_root()
INBOX_DIR = CONTENT_ROOT / "Inbox"
KB_DIR = CONTENT_ROOT / "KB"
QUICK_TIPS_DIR = CONTENT_ROOT / "Quick Tips"
LEGACY_NOTE_ROOTS_ENV = "MYKB_LEGACY_NOTE_ROOTS"
MANAGED_NOTE_ROOT_NAMES = ("Inbox", "KB", "Quick Tips")

TOPIC_PATHS = {
    "aks": KB_DIR / "AKS",
    "kubernetes": KB_DIR / "AKS",
    "network": KB_DIR / "Networking",
    "networking": KB_DIR / "Networking",
    "vpn": KB_DIR / "Networking",
    "expressroute": KB_DIR / "Networking",
    "packet": KB_DIR / "Networking",
    "private endpoint": KB_DIR / "PrivateEndpoint",
    "privateendpoint": KB_DIR / "PrivateEndpoint",
    "dns": KB_DIR / "PrivateEndpoint",
    "sql": KB_DIR / "SQL",
    "sql server": KB_DIR / "SQL",
    "database": KB_DIR / "SQL",
    "copilot": KB_DIR / "Copilot",
    "agent": KB_DIR / "Copilot",
}

TOPIC_OPTIONS = [
    ("aks", "AKS", KB_DIR / "AKS"),
    ("networking", "Networking", KB_DIR / "Networking"),
    ("privateendpoint", "Private Endpoint", KB_DIR / "PrivateEndpoint"),
    ("sql", "SQL", KB_DIR / "SQL"),
    ("copilot", "Copilot", KB_DIR / "Copilot"),
]

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "what",
    "when",
    "with",
}


@dataclass
class SearchResult:
    path: Path
    title: str
    score: int
    snippet: str
    content: str


@dataclass
class NoteDocument:
    path: Path
    title: str
    content: str


@dataclass
class SearchScope:
    query: str
    root: Path | None
    label: str = ""
    is_scoped: bool = False


@dataclass
class InboxEntry:
    heading: str
    body: list[str]
    capture_id: str = ""

    @property
    def text(self) -> str:
        return "\n".join(self.body).strip()


@dataclass
class OrganizedEntry:
    source_path: Path
    destination_path: Path
    title: str
    summary: str
    capture_id: str = ""


def append_to_daily_inbox(raw_note: str) -> tuple[Path, str]:
    initialize_content_root()
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    note_path = INBOX_DIR / f"{now:%Y-%m-%d}.md"
    heading = f"# Inbox for {now:%Y-%m-%d}\n\nUse this file for quick note capture during the day. Keep entries short.\n"
    timestamp = now.strftime("%H:%M")
    capture_id = f"cap-{now:%Y%m%d%H%M%S}-{uuid4().hex[:8]}"
    entry = f"\n## {timestamp} Quick Capture\n{format_note(raw_note, capture_id=capture_id)}\n"

    if note_path.exists():
        note_path.write_text(note_path.read_text(encoding="utf-8").rstrip() + entry + "\n", encoding="utf-8")
    else:
        note_path.write_text(heading + entry + "\n", encoding="utf-8")
    sync_content_write(note_path)

    return note_path, capture_id


def save_quick_tip(raw_note: str) -> Path:
    initialize_content_root()
    QUICK_TIPS_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    title = sanitize_title(build_capture_title_hint(raw_note, max_words=10))
    if not title or title == "Untitled note":
        title = f"Quick tip {now:%Y-%m-%d %H%M}"

    destination_path = unique_note_path(QUICK_TIPS_DIR, title)
    lines = [
        f"# {title}",
        "",
        f"- Date: {now:%Y-%m-%d}",
        "",
        "## Summary",
        raw_note.strip(),
        "",
    ]
    destination_path.write_text("\n".join(lines), encoding="utf-8")
    sync_content_write(destination_path)
    return destination_path


def format_note(raw_note: str, capture_id: str = "") -> str:
    lines = [line.strip() for line in raw_note.splitlines() if line.strip()]
    if not lines:
        return "- Summary:"

    first_line = lines[0]
    details = extract_metadata(raw_note)
    bullets = [f"- Summary: {first_line}"]

    if details.get("topic"):
        bullets.insert(0, f"- Topic: {details['topic']}")
    if details.get("service"):
        bullets.append(f"- Service: {details['service']}")
    if details.get("icm"):
        bullets.append(f"- ICM: {details['icm']}")
    if details.get("case"):
        bullets.append(f"- Case: {details['case']}")
    if capture_id:
        bullets.append(f"- CaptureId: {capture_id}")

    extra_lines = lines[1:]
    if extra_lines:
        bullets.append("- Details:")
        bullets.extend([f"  - {line}" for line in extra_lines])

    return "\n".join(bullets)


def extract_metadata(text: str) -> dict[str, str]:
    lowered = text.lower()
    metadata: dict[str, str] = {}

    icm_match = re.search(r"\bICM[-\s]?(\d{6,})\b", text, re.IGNORECASE)
    if icm_match:
        metadata["icm"] = f"ICM-{icm_match.group(1)}"

    case_match = re.search(r"\bcase[-\s#:]*([A-Za-z0-9-]+)\b", text, re.IGNORECASE)
    if case_match:
        metadata["case"] = case_match.group(1)

    topic_bullet = re.search(r"^- Topic:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    if topic_bullet:
        metadata["topic"] = topic_bullet.group(1).strip()
    else:
        for key in TOPIC_PATHS:
            if key in lowered:
                metadata["topic"] = normalize_topic(key)
                break

    service_bullet = re.search(r"^- Service:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    if service_bullet:
        metadata["service"] = service_bullet.group(1).strip()
    else:
        service_match = re.search(r"\b(AKS|ExpressRoute|VPN|SQL Server|Private Endpoint|Copilot)\b", text, re.IGNORECASE)
        if service_match:
            metadata["service"] = service_match.group(1)

    summary_match = re.search(r"^- Summary:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    if summary_match:
        metadata["summary"] = summary_match.group(1).strip()

    fix_match = re.search(r"^- Fix:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    if fix_match:
        metadata["fix"] = fix_match.group(1).strip()

    learning_match = re.search(r"^- Learning:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    if learning_match:
        metadata["learning"] = learning_match.group(1).strip()

    capture_id_match = re.search(r"^- CaptureId:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    if capture_id_match:
        metadata["capture_id"] = capture_id_match.group(1).strip()

    return metadata


def normalize_topic(topic_key: str) -> str:
    lowered = topic_key.lower()
    if lowered in {"aks", "kubernetes"}:
        return "AKS"
    if lowered in {"network", "networking", "vpn", "expressroute", "packet"}:
        return "Networking"
    if lowered in {"private endpoint", "privateendpoint", "dns"}:
        return "PrivateEndpoint"
    if lowered in {"copilot", "agent"}:
        return "Copilot"
    return "SQL"


def suggest_destinations(text: str) -> list[str]:
    lowered = text.lower()
    suggestions: list[str] = []
    seen: set[str] = set()
    for keyword, path in TOPIC_PATHS.items():
        if keyword in lowered:
            relative = relative_note_path(path)
            if relative not in seen:
                seen.add(relative)
                suggestions.append(relative)
    return suggestions


def suggest_topic_keys(text: str) -> list[str]:
    lowered = text.lower()
    topic_keys: list[str] = []
    seen: set[str] = set()

    for keyword, _ in TOPIC_PATHS.items():
        if keyword not in lowered:
            continue
        canonical_key = destination_key_for_topic(keyword)
        if canonical_key and canonical_key not in seen:
            seen.add(canonical_key)
            topic_keys.append(canonical_key)

    return topic_keys


def extract_hashtags(text: str) -> list[str]:
    return [match.group(2).strip().lower() for match in re.finditer(r"(^|\s)#([A-Za-z0-9][A-Za-z0-9_-]*)", text)]


def strip_hashtags(text: str) -> str:
    cleaned = re.sub(r"(^|\s)#[A-Za-z0-9][A-Za-z0-9_-]*", " ", text)
    cleaned = re.sub(r"\n\s+", "\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def normalize_hashtags_to_terms(text: str) -> str:
    normalized = re.sub(r"(^|\s)#([A-Za-z0-9][A-Za-z0-9_-]*)", lambda match: f"{match.group(1)}{match.group(2)}", text)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n\s+", "\n", normalized)
    return normalized.strip()


def hashtag_folder_name(tag: str) -> str:
    normalized_tag = tag.strip().lower()
    if not normalized_tag:
        return "Notes"

    known_paths = {key: path for key, path in TOPIC_PATHS.items()}
    if normalized_tag in known_paths:
        return known_paths[normalized_tag].name

    compact_tag = normalized_tag.replace("-", " ").replace("_", " ")
    compact_tag = re.sub(r"\s+", " ", compact_tag).strip()
    if compact_tag in {"aks", "sql"}:
        return compact_tag.upper()
    if compact_tag == "privateendpoint":
        return "PrivateEndpoint"
    if compact_tag == "new learning":
        return "New Learning"
    return " ".join(word.upper() if word in {"aks", "sql"} else word.capitalize() for word in compact_tag.split()) or "Notes"


def destination_path_for_hashtag(tag: str) -> Path:
    return KB_DIR / hashtag_folder_name(tag)


def resolve_search_scope(query: str) -> SearchScope:
    initialize_content_root()
    hashtags = extract_hashtags(query)
    if not hashtags:
        return SearchScope(query=query.strip(), root=None)

    primary_tag = hashtags[0]
    destination_root = destination_path_for_hashtag(primary_tag)
    if destination_root.exists() and destination_root.is_dir():
        return SearchScope(
            query=strip_hashtags(query),
            root=destination_root,
            label=destination_root.name,
            is_scoped=True,
        )

    return SearchScope(query=normalize_hashtags_to_terms(query), root=None)


def capture_resolution_options() -> list[dict[str, str]]:
    return [
        {
            "key": key,
            "label": label,
            "path": relative_note_path(path),
        }
        for key, label, path in TOPIC_OPTIONS
    ]


def summarize_text_for_kb(raw_text: str, ai_helper: object | None = None) -> dict[str, str]:
    metadata = extract_metadata(raw_text)
    summary = metadata.get("summary") or first_meaningful_line(raw_text)
    draft = {
        "title": build_capture_title_hint(raw_text, max_words=10),
        "summary": summary,
        "fix": metadata.get("fix", ""),
        "learning": metadata.get("learning", ""),
    }
    if ai_helper is not None:
        try:
            enhanced = ai_helper.summarize_note(raw_text)
        except Exception:
            enhanced = None
        if enhanced:
            draft.update({key: value for key, value in enhanced.items() if value})
    draft["title"] = sanitize_title(draft.get("title") or build_capture_title_hint(raw_text, max_words=10))
    return draft


def write_kb_note_from_capture(
    destination_path: Path,
    raw_text: str,
    draft: dict[str, str],
    hashtags: list[str] | None = None,
    extracted_text: str = "",
) -> None:
    cleaned_text = raw_text.strip()
    metadata = extract_metadata(cleaned_text)
    body_lines = [f"# {draft['title']}", ""]
    if hashtags:
        body_lines.append(f"- Tags: {' '.join(f'#{tag}' for tag in hashtags)}")
    if metadata.get("icm"):
        body_lines.append(f"- ICM: {metadata['icm']}")
    if metadata.get("case"):
        body_lines.append(f"- Case: {metadata['case']}")
    if metadata.get("service"):
        body_lines.append(f"- Service: {metadata['service']}")
    body_lines.append(f"- Date: {datetime.now():%Y-%m-%d}")
    body_lines.append("")
    body_lines.append("## Summary")
    body_lines.append(draft.get("summary") or first_meaningful_line(cleaned_text))
    if draft.get("fix"):
        body_lines.extend(["", "## Fix", draft["fix"]])
    if draft.get("learning"):
        body_lines.extend(["", "## Learnings", f"- {draft['learning']}"])
    if extracted_text.strip():
        body_lines.extend(["", "## Screenshot Text", extracted_text.strip()])
    if cleaned_text:
        body_lines.extend(["", "## Source Capture", cleaned_text])
    body = "\n".join(body_lines).rstrip() + "\n"

    if destination_path.exists():
        existing = destination_path.read_text(encoding="utf-8")
        if cleaned_text in existing:
            return
        merged = existing.rstrip() + "\n\n---\n\n" + "\n".join(body_lines[2:]).rstrip() + "\n"
        destination_path.write_text(merged, encoding="utf-8")
    else:
        destination_path.write_text(body, encoding="utf-8")
    sync_content_write(destination_path)


def save_detailed_capture(
    raw_note: str,
    ai_helper: object | None = None,
    screenshot_bytes: bytes | None = None,
    screenshot_mime_type: str | None = None,
) -> dict[str, str] | None:
    initialize_content_root()
    hashtags = extract_hashtags(raw_note)
    if screenshot_bytes is not None and not hashtags:
        raise ValueError("Add a hashtag when uploading a screenshot.")
    if not hashtags:
        return None

    destination_dir = destination_path_for_hashtag(hashtags[0])
    destination_dir.mkdir(parents=True, exist_ok=True)
    cleaned_text = strip_hashtags(raw_note)
    if not cleaned_text:
        cleaned_text = raw_note.strip()

    extracted_text = ""
    if screenshot_bytes is not None:
        if ai_helper is None:
            raise ValueError("Configure a vision-capable AI model before uploading screenshots.")
        try:
            image_draft = ai_helper.summarize_note_with_image(
                cleaned_text,
                screenshot_bytes,
                screenshot_mime_type or "image/png",
            )
        except Exception as error:
            raise ValueError("Could not process the screenshot with the current AI model.") from error
        if not image_draft:
            raise ValueError("Could not process the screenshot with the current AI model.")
        extracted_text = image_draft.pop("extracted_text", "")
        draft = summarize_text_for_kb(cleaned_text, ai_helper=None)
        draft.update({key: value for key, value in image_draft.items() if value})
    else:
        draft = summarize_text_for_kb(cleaned_text, ai_helper=ai_helper)

    title = sanitize_title(draft.get("title") or build_capture_title_hint(cleaned_text, max_words=10))
    destination_path = unique_note_path(destination_dir, title)
    draft["title"] = title
    write_kb_note_from_capture(
        destination_path,
        cleaned_text,
        draft,
        hashtags=hashtags,
        extracted_text=extracted_text,
    )
    return {
        "destination": relative_note_path(destination_path),
        "title": title,
        "summary": draft.get("summary") or first_meaningful_line(cleaned_text),
    }


def destination_key_for_topic(topic_key: str) -> str:
    normalized_topic = normalize_topic(topic_key).lower()
    for option_key, label, _ in TOPIC_OPTIONS:
        if label.lower().replace(" ", "") == normalized_topic.replace(" ", ""):
            return option_key
    return ""


def destination_path_for_key(destination_key: str) -> Path | None:
    normalized_key = destination_key.strip().lower()
    for option_key, _, path in TOPIC_OPTIONS:
        if option_key == normalized_key:
            return path
    return None


def get_recent_notes(limit: int = 10) -> list[dict[str, str]]:
    initialize_content_root()
    note_files = sorted(iter_note_files(), key=lambda path: path.stat().st_mtime, reverse=True)
    recent_items = []
    for note_file in note_files[:limit]:
        title, snippet = read_title_and_snippet(note_file)
        recent_items.append(
            {
                "path": relative_note_path(note_file),
                "title": title,
                "snippet": snippet,
            }
        )
    return recent_items


def iter_note_files(base_root: Path | None = None) -> Iterable[Path]:
    initialize_content_root()
    seen_paths: set[Path] = set()
    if base_root is not None:
        if not base_root.exists():
            return
        roots: list[Path] = [base_root]
    else:
        roots = list(iter_search_roots())

    for root_path in roots:
        if root_path.is_file():
            if root_path not in seen_paths:
                seen_paths.add(root_path)
                yield root_path
            continue

        for note_file in root_path.rglob("*.md"):
            if note_file not in seen_paths:
                seen_paths.add(note_file)
                yield note_file


def iter_search_roots(base_root: Path | None = None) -> Iterable[Path]:
    root = base_root or CONTENT_ROOT
    yielded_paths: set[Path] = set()

    for root_name in MANAGED_NOTE_ROOT_NAMES:
        root_path = root / root_name
        if not root_path.exists() or root_path in yielded_paths:
            continue
        yielded_paths.add(root_path)
        yield root_path

    for extra_root in configured_legacy_note_roots(root):
        if extra_root in yielded_paths:
            continue
        yielded_paths.add(extra_root)
        yield extra_root


def configured_legacy_note_roots(base_root: Path) -> list[Path]:
    raw_value = os.getenv(LEGACY_NOTE_ROOTS_ENV, "")
    if not raw_value:
        return []

    resolved_paths: list[Path] = []
    for raw_path in raw_value.split(";"):
        normalized_path = raw_path.strip().replace("\\", "/").strip("/")
        if not normalized_path:
            continue
        candidate_path = (base_root / normalized_path).resolve()
        try:
            candidate_path.relative_to(base_root)
        except ValueError:
            continue
        if candidate_path.exists():
            resolved_paths.append(candidate_path)

    return resolved_paths


def note_inventory(base_root: Path) -> dict[str, set[str]]:
    inventory: dict[str, set[str]] = {}

    if not base_root.exists():
        return inventory

    for root_path in iter_search_roots(base_root):
        relative_root = root_path.relative_to(base_root).as_posix()
        if root_path.is_file():
            inventory[relative_root] = {root_path.name}
            continue

        note_paths = {note_file.relative_to(root_path).as_posix() for note_file in root_path.rglob("*.md")}
        if note_paths:
            inventory[relative_root] = note_paths

    return inventory


def get_content_library_status() -> dict[str, object]:
    initialize_content_root()
    return {
        "hostedMode": CONTENT_STORE.enabled or CONTENT_ROOT != APP_ROOT,
        "repoRoot": APP_ROOT.as_posix(),
        "contentRoot": CONTENT_ROOT.as_posix(),
        "storageBackend": "blob" if CONTENT_STORE.enabled else "local",
        "blobAccountUrl": CONTENT_STORE.account_url if CONTENT_STORE.enabled else "",
        "blobContainer": CONTENT_STORE.container_name if CONTENT_STORE.enabled else "",
        "storageDiagnostics": CONTENT_STORE.diagnostics(),
        "roots": [],
        "missingRootCount": 0,
        "missingNoteCount": 0,
        "supportsPackagedContent": False,
        "message": "This reusable template starts with an empty knowledge base and does not import packaged note libraries.",
    }


def import_content_library(relative_paths: list[str] | None = None) -> dict[str, object]:
    return {
        "message": "Packaged content import is disabled in the reusable public template.",
        "importedRoots": [],
        "importedNoteCount": 0,
        "skippedNoteCount": 0,
        "status": get_content_library_status(),
    }


def search_notes(query: str, search_root: Path | None = None) -> list[SearchResult]:
    initialize_content_root()
    terms = tokenize(query)
    normalized_query = normalize_search_text(query)

    if not terms and not normalized_query:
        if search_root is None:
            return []
        recent_results: list[SearchResult] = []
        note_files = sorted(iter_note_files(search_root), key=lambda path: path.stat().st_mtime, reverse=True)
        for note_file in note_files[:12]:
            text = note_file.read_text(encoding="utf-8", errors="ignore")
            title, snippet = read_title_and_snippet(note_file)
            recent_results.append(
                SearchResult(
                    path=note_file,
                    title=title,
                    score=1,
                    snippet=snippet,
                    content=text,
                )
            )
        return recent_results

    results: list[SearchResult] = []
    for note_file in iter_note_files(search_root):
        text = note_file.read_text(encoding="utf-8", errors="ignore")
        relative_path = relative_note_path(note_file)
        score = score_text(text, note_file.stem, relative_path, terms, normalized_query)
        if score <= 0:
            continue
        title, _ = read_title_and_snippet(note_file)
        results.append(
            SearchResult(
                path=note_file,
                title=title,
                score=score,
                snippet=best_snippet(text, terms, normalized_query),
                content=text,
            )
        )

    return sorted(results, key=lambda item: (item.score, item.title.lower()), reverse=True)


def tokenize(text: str) -> list[str]:
    tokens = normalize_search_text(text).split()
    return [token for token in tokens if token not in STOP_WORDS and len(token) > 1]


def normalize_search_text(text: str) -> str:
    lowered = text.lower().replace("_", " ").replace("-", " ").replace("/", " ").replace("\\", " ")
    return " ".join(re.findall(r"[A-Za-z0-9]+", lowered))


def is_marker_term(term: str) -> bool:
    return any(character.isdigit() for character in term) or "-" in term


def score_text(text: str, stem: str, relative_path: str, terms: list[str], normalized_query: str) -> int:
    if not terms and not normalized_query:
        return 0

    haystack = text.lower()
    title = stem.lower()
    relative_path_lower = relative_path.lower()
    normalized_haystack = normalize_search_text(text)
    normalized_title = normalize_search_text(stem)
    normalized_path = normalize_search_text(relative_path)
    score = 0
    matched_terms = 0

    if normalized_query:
        if normalized_query in normalized_title:
            score += 140
        if normalized_query in normalized_path:
            score += 120
        if normalized_query in normalized_haystack:
            score += 90

    for term in terms:
        term_score = 0
        marker_multiplier = 3 if is_marker_term(term) else 1
        if term in normalized_title:
            term_score += 18 * marker_multiplier
        if term in normalized_path:
            term_score += 14 * marker_multiplier
        occurrences = normalized_haystack.count(term)
        if occurrences:
            term_score += min(occurrences, 8) * (6 if marker_multiplier > 1 else 3)
        if term_score:
            matched_terms += 1
            score += term_score

    if matched_terms == len(terms) and terms:
        score += 40 + (len(terms) * 4)

    best_line_score = max((score_line(line, terms, normalized_query) for line in text.splitlines()), default=0)
    score += best_line_score
    return score


def score_line(line: str, terms: list[str], normalized_query: str) -> int:
    lowered = line.lower()
    normalized_line = normalize_search_text(line)
    score = 0
    if normalized_query and normalized_query in normalized_line:
        score += 60
    matched_terms = 0
    for term in terms:
        if term in normalized_line or term in lowered:
            matched_terms += 1
            score += 18 if is_marker_term(term) else 8
    if matched_terms == len(terms) and terms:
        score += 20
    return score


def best_snippet(text: str, terms: list[str], normalized_query: str, max_length: int = 240) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""

    scored_lines = [(score_line(line, terms, normalized_query), index, line) for index, line in enumerate(lines)]
    best_score, best_index, best_line = max(scored_lines, key=lambda item: (item[0], -item[1]))
    if best_score > 0:
        context_lines = [best_line]
        if best_index + 1 < len(lines):
            next_line = lines[best_index + 1]
            if score_line(next_line, terms, normalized_query) > 0 or len(best_line) < 120:
                context_lines.append(next_line)
        return trim_snippet(" ".join(context_lines), max_length)
    return trim_snippet(" ".join(lines[:3]), max_length)


def trim_snippet(text: str, max_length: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_length:
        return compact
    return compact[: max_length - 3].rstrip() + "..."


def read_title_and_snippet(note_file: Path) -> tuple[str, str]:
    text = note_file.read_text(encoding="utf-8", errors="ignore")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = note_file.stem
    for line in lines:
        if line.startswith("#"):
            title = line.lstrip("# ").strip()
            break
    snippet = trim_snippet(" ".join(lines[1:4]) if len(lines) > 1 else "", 180)
    return title, snippet


def get_note_document(relative_path_value: str) -> NoteDocument | None:
    initialize_content_root()
    normalized_target = relative_path_value.strip().replace("\\", "/").lstrip("/")
    if not normalized_target:
        return None

    for note_file in iter_note_files():
        if relative_note_path(note_file) != normalized_target:
            continue
        title, _ = read_title_and_snippet(note_file)
        return NoteDocument(
            path=note_file,
            title=title,
            content=note_file.read_text(encoding="utf-8", errors="ignore"),
        )
    return None


def select_display_results(results: list[SearchResult], query: str, limit: int = 4) -> list[SearchResult]:
    if not results:
        return []

    terms = tokenize(query)
    marker_query = any(is_marker_term(term) for term in terms)
    top_score = results[0].score
    minimum_score = max(36, int(top_score * 0.6))
    if marker_query:
        minimum_score = max(minimum_score, int(top_score * 0.75))

    if marker_query and len(results) > 1 and results[1].score > 0 and top_score >= results[1].score * 2:
        return [results[0]]

    filtered = [result for result in results if result.score >= minimum_score]
    if not filtered:
        filtered = results[:1]
    return filtered[:limit]


def build_fallback_answer(query: str, results: list[SearchResult]) -> str:
    if not results:
        return f"I could not find a direct match for '{query}'. Try a service name, ICM number, symptom, or fix keyword."

    top_results = results[:3]
    if len(top_results) == 1:
        return summarize_single_result(query, top_results[0])

    intro = [f"I found {len(results)} relevant notes. The strongest matches are:"]
    for result in top_results:
        note = summarize_note_for_chat(result)
        intro.append(f"- {result.title}: {note}")
    return "\n".join(intro)


def summarize_single_result(query: str, result: SearchResult) -> str:
    sections = extract_markdown_sections(result.content)
    summary = first_section_text(sections, ["summary", "resolution status", "root cause hypothesis"]) or result.snippet
    details: list[str] = [f"I found one strong match: {result.title}."]
    if summary:
        details.append(summary)

    resolution = first_section_text(sections, ["resolution status", "fix", "next step"])
    if resolution and resolution != summary:
        details.append(f"Current outcome: {resolution}")

    root_cause = first_section_text(sections, ["root cause hypothesis", "important platform detail"])
    if root_cause and root_cause not in {summary, resolution}:
        details.append(f"Key detail: {root_cause}")

    if query.lower().find("vip") >= 0:
        vip = extract_metadata_value(result.content, "VIP")
        if vip:
            details.append(f"The note references VIP {vip}.")

    return " ".join(details)


def summarize_note_for_chat(result: SearchResult) -> str:
    sections = extract_markdown_sections(result.content)
    summary = first_section_text(sections, ["summary", "resolution status", "root cause hypothesis"])
    if summary:
        return summary
    return result.snippet


def extract_markdown_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current_heading = ""
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_heading:
                sections[current_heading] = current_lines
            current_heading = line[3:].strip().lower()
            current_lines = []
            continue
        if current_heading:
            current_lines.append(line)

    if current_heading:
        sections[current_heading] = current_lines

    return {heading: normalize_section_text(lines) for heading, lines in sections.items()}


def normalize_section_text(lines: list[str]) -> str:
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            stripped = stripped[2:]
        cleaned_lines.append(stripped)
    return trim_snippet(" ".join(cleaned_lines), 320)


def first_section_text(sections: dict[str, str], headings: list[str]) -> str:
    for heading in headings:
        if heading in sections and sections[heading]:
            return sections[heading]
    return ""


def extract_metadata_value(text: str, label: str) -> str:
    pattern = rf"^- {re.escape(label)}:\s*(.+)$"
    match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def parse_inbox_file(note_path: Path) -> list[InboxEntry]:
    text = note_path.read_text(encoding="utf-8", errors="ignore")
    entries: list[InboxEntry] = []
    current_heading: str | None = None
    current_body: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_heading is not None:
                entry_text = "\n".join(current_body)
                entries.append(
                    InboxEntry(
                        heading=current_heading,
                        body=current_body,
                        capture_id=extract_metadata(entry_text).get("capture_id", ""),
                    )
                )
            current_heading = line.strip()
            current_body = []
            continue
        if current_heading is None:
            continue
        current_body.append(line)

    if current_heading is not None:
        entry_text = "\n".join(current_body)
        entries.append(
            InboxEntry(
                heading=current_heading,
                body=current_body,
                capture_id=extract_metadata(entry_text).get("capture_id", ""),
            )
        )
    return entries


def should_skip_entry(entry: InboxEntry) -> bool:
    text = entry.text.lower()
    if not text:
        return True
    return "example entry" in entry.heading.lower() or "use this file for quick note capture" in text


def choose_destination(entry: InboxEntry) -> Path | None:
    metadata = extract_metadata(entry.text)
    topic = metadata.get("topic", "")
    if not topic:
        return None
    destination_key = destination_key_for_topic(topic)
    return destination_path_for_key(destination_key)


def build_entry_title(entry: InboxEntry) -> str:
    metadata = extract_metadata(entry.text)
    summary = metadata.get("summary") or first_meaningful_line(entry.text)
    fix = metadata.get("fix")
    title = sanitize_title(summary, max_words=8)
    if fix:
        title = f"{title} - {shorten_fix_text(fix)}"
    title = re.sub(r"\bICM[-\s]?\d+\b", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip(" -")
    if not title:
        title = entry.heading.replace("##", "").strip()
    return sanitize_title(title)


def sanitize_title(text: str, max_words: int = 12) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .-")
    words = cleaned.split()
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words])
    return cleaned or "Untitled note"


def unique_note_path(directory: Path, title: str) -> Path:
    base_title = sanitize_title(title)
    candidate = directory / f"{base_title}.md"
    suffix = 2
    while candidate.exists():
        candidate = directory / f"{base_title} {suffix}.md"
        suffix += 1
    return candidate


def extract_labeled_value(text: str, label: str) -> str:
    pattern = rf"^[-*#\s]*{re.escape(label)}\s*:\s*(.+)$"
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else ""


def normalize_service_anchor(service: str) -> str:
    lowered = service.lower().strip()
    if not lowered:
        return ""
    if "expressroute" in lowered:
        return "ExpressRoute"
    if "private endpoint" in lowered or "privateendpoint" in lowered:
        return "Private Endpoint"
    if "sql" in lowered:
        return "SQL"
    if "aks" in lowered or "kubernetes" in lowered:
        return "AKS"
    if "copilot" in lowered:
        return "Copilot"
    if "gpu" in lowered and "cluster" in lowered:
        return "GPU cluster"
    primary = re.split(r"[/,]", service, maxsplit=1)[0].strip()
    primary = re.sub(r"\b(service|services|platform|networking|system|systems)\b", "", primary, flags=re.IGNORECASE)
    primary = re.sub(r"\s+", " ", primary).strip(" -")
    return sanitize_title(primary, max_words=3)


def compact_summary_text(text: str) -> str:
    cleaned = re.sub(r"^(customer|traffic|incident|issue)\s+", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(saw|experienced|had)\b", "", cleaned, count=1, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .-")
    return cleaned


def build_capture_title_hint(text: str, max_words: int = 8) -> str:
    service = extract_labeled_value(text, "Service") or extract_metadata(text).get("service", "")
    preferred_labels = ["Issue", "Topic", "Symptom", "Summary", "Learning", "Root Cause", "Fix"]

    candidate = ""
    for label in preferred_labels:
        value = extract_labeled_value(text, label)
        if value:
            candidate = value
            break

    if not candidate:
        candidate = first_meaningful_line(text)

    candidate = compact_summary_text(candidate)
    anchor = normalize_service_anchor(service)
    normalized_candidate = candidate.lower()
    normalized_anchor = anchor.lower()

    if anchor and normalized_anchor and normalized_anchor not in normalized_candidate:
        candidate = f"{anchor} {candidate}"

    candidate = re.sub(r"\bICM[-\s]?\d+\b", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\s+", " ", candidate).strip(" -")
    return sanitize_title(candidate or first_meaningful_line(text), max_words=max_words)


def shorten_fix_text(text: str, max_words: int = 4) -> str:
    filler_words = {"the", "a", "an", "affected", "issue", "problem", "instance", "instances"}
    words = [word for word in re.findall(r"[A-Za-z0-9-]+", text) if word.lower() not in filler_words]
    if not words:
        return sanitize_title(text, max_words=max_words)
    shortened = " ".join(words[:max_words])
    if any(word.lower().startswith("recreat") for word in words) and "VMSS" in words:
        return "VMSS recreate"
    return shortened


def first_meaningful_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^-\s*[A-Za-z ]+:\s*", "", stripped)
        if stripped:
            return stripped
    return "Quick note"


def clean_entry_body_lines(entry: InboxEntry) -> list[str]:
    return [line for line in entry.body if not re.match(r"^- CaptureId:\s*", line.strip(), re.IGNORECASE)]


def clean_entry_text(entry: InboxEntry) -> str:
    return "\n".join(clean_entry_body_lines(entry)).strip()


def find_inbox_entry(capture_id: str, inbox_path: Path | None = None) -> tuple[Path, InboxEntry, list[InboxEntry]] | None:
    if not capture_id:
        return None

    candidate_paths = [inbox_path] if inbox_path is not None else sorted(INBOX_DIR.glob("*.md"))
    for candidate_path in candidate_paths:
        if candidate_path is None or not candidate_path.exists():
            continue
        entries = parse_inbox_file(candidate_path)
        for entry in entries:
            if entry.capture_id == capture_id:
                return candidate_path, entry, entries
    return None


def remove_inbox_entry(note_path: Path, capture_id: str) -> None:
    entries = parse_inbox_file(note_path)
    remaining_entries = [entry for entry in entries if entry.capture_id != capture_id and not should_skip_entry(entry)]
    if remaining_entries:
        rewrite_inbox_file(note_path, remaining_entries)
    else:
        note_path.unlink(missing_ok=True)
        sync_content_delete(note_path)


def resolve_capture_clarification(
    capture_id: str,
    destination_key: str,
    custom_title: str = "",
    inbox_path: Path | None = None,
    ai_helper: object | None = None,
) -> dict[str, str]:
    initialize_content_root()
    match = find_inbox_entry(capture_id, inbox_path=inbox_path)
    if match is None:
        raise ValueError("The saved inbox note could not be found for clarification.")

    source_path, entry, _ = match
    destination_dir = destination_path_for_key(destination_key)
    if destination_dir is None:
        raise ValueError("Choose a valid KB destination before continuing.")

    draft = summarize_entry_for_kb(entry)
    if ai_helper is not None:
        try:
            enhanced = ai_helper.summarize_note(clean_entry_text(entry))
        except Exception:
            enhanced = None
        if enhanced:
            draft.update(enhanced)

    title = sanitize_title(custom_title or draft.get("title") or build_entry_title(entry))
    draft["title"] = title
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / f"{title}.md"
    write_kb_note(destination_path, entry, draft)
    remove_inbox_entry(source_path, capture_id)

    return {
        "source": relative_note_path(source_path),
        "destination": relative_note_path(destination_path),
        "title": title,
        "summary": draft.get("summary") or first_meaningful_line(clean_entry_text(entry)),
    }


def build_capture_clarification(raw_note: str, capture_id: str, saved_path: Path) -> dict[str, object]:
    suggested_topic_keys = suggest_topic_keys(raw_note)
    title_hint = build_capture_title_hint(raw_note, max_words=8)
    return {
        "captureId": capture_id,
        "savedTo": relative_note_path(saved_path),
        "options": capture_resolution_options(),
        "suggestedTopicKey": suggested_topic_keys[0] if suggested_topic_keys else "",
        "titleHint": title_hint,
    }


def organize_inbox(ai_helper: object | None = None, inbox_paths: Iterable[Path] | None = None) -> dict[str, object]:
    initialize_content_root()
    organized: list[OrganizedEntry] = []
    kept_files: list[str] = []
    deleted_files: list[str] = []
    INBOX_DIR.mkdir(parents=True, exist_ok=True)

    target_paths = sorted(inbox_paths) if inbox_paths is not None else sorted(INBOX_DIR.glob("*.md"))

    for inbox_path in target_paths:
        if not inbox_path.exists() or inbox_path.suffix.lower() != ".md":
            continue
        entries = parse_inbox_file(inbox_path)
        remaining_entries: list[InboxEntry] = []
        for entry in entries:
            if should_skip_entry(entry):
                continue
            destination_dir = choose_destination(entry)
            if destination_dir is None:
                remaining_entries.append(entry)
                continue
            destination_dir.mkdir(parents=True, exist_ok=True)
            draft = summarize_entry_for_kb(entry)
            if ai_helper is not None:
                try:
                    enhanced = ai_helper.summarize_note(entry.text)
                except Exception:
                    enhanced = None
                if enhanced:
                    draft.update(enhanced)
            title = sanitize_title(draft.get("title") or build_entry_title(entry))
            draft["title"] = title
            destination_path = destination_dir / f"{title}.md"
            write_kb_note(destination_path, entry, draft)
            organized.append(
                OrganizedEntry(
                    source_path=inbox_path,
                    destination_path=destination_path,
                    title=title,
                    summary=draft.get("summary") or first_meaningful_line(entry.text),
                    capture_id=entry.capture_id,
                )
            )

        if remaining_entries:
            rewrite_inbox_file(inbox_path, remaining_entries)
            kept_files.append(relative_note_path(inbox_path))
        else:
            inbox_path.unlink(missing_ok=True)
            sync_content_delete(inbox_path)
            deleted_files.append(relative_note_path(inbox_path))

    return {
        "organized": [
            {
                "source": relative_note_path(item.source_path),
                "destination": relative_note_path(item.destination_path),
                "title": item.title,
                "summary": item.summary,
                "captureId": item.capture_id,
            }
            for item in organized
        ],
        "keptFiles": kept_files,
        "deletedFiles": deleted_files,
    }


def summarize_entry_for_kb(entry: InboxEntry) -> dict[str, str]:
    cleaned_text = clean_entry_text(entry)
    metadata = extract_metadata(cleaned_text)
    summary = metadata.get("summary") or first_meaningful_line(cleaned_text)
    title = build_entry_title(entry)
    fix = metadata.get("fix")
    learning = metadata.get("learning")
    return {
        "title": title,
        "summary": summary,
        "fix": fix or "",
        "learning": learning or "",
    }


def write_kb_note(destination_path: Path, entry: InboxEntry, draft: dict[str, str]) -> None:
    cleaned_text = clean_entry_text(entry)
    metadata = extract_metadata(cleaned_text)
    body_lines = [f"# {draft['title']}", ""]
    if metadata.get("icm"):
        body_lines.append(f"- ICM: {metadata['icm']}")
    if metadata.get("case"):
        body_lines.append(f"- Case: {metadata['case']}")
    if metadata.get("service"):
        body_lines.append(f"- Service: {metadata['service']}")
    body_lines.append(f"- Date: {datetime.now():%Y-%m-%d}")
    body_lines.append("")
    body_lines.append("## Summary")
    body_lines.append(draft["summary"])
    if draft.get("fix"):
        body_lines.extend(["", "## Fix", draft["fix"]])
    if draft.get("learning"):
        body_lines.extend(["", "## Learnings", f"- {draft['learning']}"])
    raw_details = cleaned_text
    if raw_details:
        body_lines.extend(["", "## Source Capture", raw_details])
    body = "\n".join(body_lines).rstrip() + "\n"

    if destination_path.exists():
        existing = destination_path.read_text(encoding="utf-8")
        if raw_details in existing:
            return
        merged = existing.rstrip() + "\n\n---\n\n" + "\n".join(body_lines[2:]).rstrip() + "\n"
        destination_path.write_text(merged, encoding="utf-8")
    else:
        destination_path.write_text(body, encoding="utf-8")
    sync_content_write(destination_path)


def rewrite_inbox_file(inbox_path: Path, entries: list[InboxEntry]) -> None:
    date_text = inbox_path.stem
    lines = [
        f"# Inbox for {date_text}",
        "",
        "Use this file for quick note capture during the day. Keep entries short.",
        "",
    ]
    for entry in entries:
        lines.append(entry.heading)
        lines.extend(entry.body)
        lines.append("")
    inbox_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    sync_content_write(inbox_path)


def app_status(ai_helper: object | None = None) -> dict[str, object]:
    ai_enabled = bool(ai_helper and getattr(ai_helper, "is_configured", False))
    return {
        "repoRoot": APP_ROOT.as_posix(),
        "contentRoot": CONTENT_ROOT.as_posix(),
        "hostedMode": CONTENT_STORE.enabled or CONTENT_ROOT != APP_ROOT,
        "storageBackend": "blob" if CONTENT_STORE.enabled else "local",
        "blobAccountUrl": CONTENT_STORE.account_url if CONTENT_STORE.enabled else "",
        "blobContainer": CONTENT_STORE.container_name if CONTENT_STORE.enabled else "",
        "storageDiagnostics": CONTENT_STORE.diagnostics(),
        "aiEnabled": ai_enabled,
        "aiRequired": True,
        "aiProvider": getattr(ai_helper, "provider", "") if ai_helper else "",
        "hotkey": "Ctrl+Alt+N",
        "topics": sorted({relative_note_path(path) for path in TOPIC_PATHS.values()}),
        "supportsPackagedContent": False,
        "noteRoots": list(MANAGED_NOTE_ROOT_NAMES),
    }


def dump_results_for_prompt(results: list[SearchResult], limit: int = 6) -> str:
    payload = []
    for result in results[:limit]:
        payload.append(
            {
                "path": relative_note_path(result.path),
                "title": result.title,
                "snippet": result.snippet,
                "content": trim_snippet(result.content, 1200),
            }
        )
    return json.dumps(payload, indent=2)


def initialize_content_root() -> Path:
    CONTENT_ROOT.mkdir(parents=True, exist_ok=True)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    KB_DIR.mkdir(parents=True, exist_ok=True)
    QUICK_TIPS_DIR.mkdir(parents=True, exist_ok=True)
    CONTENT_STORE.ensure_ready()
    return CONTENT_ROOT


def content_root_has_notes() -> bool:
    initialize_content_root()
    return any(CONTENT_ROOT.rglob("*.md"))


def sync_content_write(path: Path) -> None:
    CONTENT_STORE.upload_file(path)


def sync_content_delete(path: Path) -> None:
    CONTENT_STORE.delete_file(path)


def relative_note_path(path: Path) -> str:
    for base_root in (CONTENT_ROOT, APP_ROOT):
        try:
            return path.relative_to(base_root).as_posix()
        except ValueError:
            continue
    return path.as_posix()
