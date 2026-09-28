#!/usr/bin/env python3
"""Long-term append-only archives and the short indexes Jekyll builds from them.

Three layers, in order of authority:

1. `assets/data/archive/<dataset>/<key>.jsonl`
   The real history. One JSON object per line, partitioned by month for daily
   news and by year for academic frontiers and the site log. Records are only
   ever added or updated through their stable id; nothing is dropped because a
   retention window passed.

2. `assets/data/archive/manifest.json`
   Which partitions exist, how many records they hold and their SHA-256, so a
   page can fetch one partition without knowing anything else about the repo.

3. `_data/*.json`
   Short recent indexes generated from the archive (90 days of news, 180 days
   of articles, 100 log entries). Jekyll reads only these, so the default pages
   stay light and the site build stays fast.

Every write goes through a temporary file that is parsed before it replaces the
original, so an interrupted run cannot leave a half-written archive behind.
Only the standard library is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # Hosts without the IANA tz database keep the same offset.
    TZ = timezone(timedelta(hours=8))


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_RELATIVE = Path("assets") / "data" / "archive"
MANIFEST_NAME = "manifest.json"
SCHEMA_VERSION = 1

DATASETS = ("daily_news", "academic_frontiers", "site_updates")

SPECS = {
    "daily_news": {
        "directory": "daily-news",
        "partition": "monthly",
        "index": Path("_data") / "daily_news.json",
        "date_field": "date",
        "retention_days": 90,
    },
    "academic_frontiers": {
        "directory": "academic-frontiers",
        "partition": "yearly",
        "index": Path("_data") / "academic_frontiers.json",
        "date_field": "published_at",
        "retention_days": 180,
    },
    "site_updates": {
        "directory": "site-updates",
        "partition": "yearly",
        "index": Path("_data") / "site_updates.json",
        "date_field": "date",
        "retention_count": 100,
    },
}

# Keys that only exist for the archive itself and never reach the public index.
INTERNAL_KEYS = ("schema_version", "sha_source", "fetched_at")

SHA_RE = re.compile(r"\b[0-9a-f]{40}\b")
DOI_RE = re.compile(r"(?:https?://(?:dx\.)?doi\.org/)?(10\.\S+)", re.IGNORECASE)


class ArchiveWriteError(RuntimeError):
    """Raised when a file could not be replaced safely."""


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def archive_root(root: Path = ROOT) -> Path:
    return root / ARCHIVE_RELATIVE


def dataset_dir(root: Path, dataset: str) -> Path:
    return archive_root(root) / SPECS[dataset]["directory"]


def manifest_path(root: Path = ROOT) -> Path:
    return archive_root(root) / MANIFEST_NAME


# --------------------------------------------------------------------------- #
# Atomic writes
# --------------------------------------------------------------------------- #
def validate_json(payload: str) -> None:
    json.loads(payload)


def validate_jsonl(payload: str) -> None:
    for line in payload.splitlines():
        if line.strip():
            json.loads(line)


def atomic_write(path: Path, payload: str, validator) -> None:
    """Replace `path` only after `payload` parses, leaving the original intact.

    The temporary file lives in the same directory so the final step is a rename
    on one filesystem. If validation raises, the temporary file is removed and
    the previous file stays exactly as it was.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        validator(payload)
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def write_json(path: Path, payload: object) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    atomic_write(path, text, validate_json)


def write_jsonl(path: Path, records: list[dict]) -> None:
    text = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    atomic_write(path, text, validate_jsonl)


def read_jsonl(path: Path) -> tuple[list[dict], int]:
    """Return the records in one partition plus how many lines were unusable."""
    records: list[dict] = []
    invalid = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            invalid += 1
            continue
        if isinstance(record, dict):
            records.append(record)
        else:
            invalid += 1
    return records, invalid


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# Stable ids and record normalisation
# --------------------------------------------------------------------------- #
def _is_empty(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _doi_from(value: str) -> str:
    match = DOI_RE.search(value or "")
    if not match:
        return ""
    return match.group(1).rstrip(".,;")


def normalize_daily_news(entry: dict) -> dict | None:
    """One archived day of headlines."""
    date = str(entry.get("date") or "").strip()[:10]
    if len(date) != 10:
        return None
    items = [item for item in (entry.get("items") or []) if isinstance(item, dict)]
    record = {
        "id": f"daily-news:{date}",
        "date": date,
        "items": items,
        "schema_version": SCHEMA_VERSION,
    }
    if entry.get("fetched_at"):
        record["fetched_at"] = str(entry["fetched_at"])
    return record


def normalize_frontiers(entry: dict) -> dict | None:
    """One archived article, keyed by DOI or, failing that, OpenAlex work id."""
    published = str(entry.get("published_at") or "").strip()[:10]
    if len(published) != 10:
        return None

    identifier = str(entry.get("id") or "").strip()
    if not identifier:
        doi = _doi_from(str(entry.get("doi_url") or ""))
        identifier = f"doi:{doi}" if doi else ""
    if not identifier:
        # No DOI anywhere: fall back to a content key so the record is still
        # stable across runs instead of being duplicated every time.
        basis = f"{published}|{entry.get('journal', '')}|{entry.get('title', '')}"
        identifier = "frontiers:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]

    record = dict(entry)
    record["id"] = identifier
    record["published_at"] = published
    record["schema_version"] = SCHEMA_VERSION
    if entry.get("fetched_at"):
        record["fetched_at"] = str(entry["fetched_at"])
    return record


def normalize_site_update(entry: dict) -> dict | None:
    """One site-log entry, keyed by the full commit SHA when it is known."""
    date = str(entry.get("date") or "").strip()[:10]
    if len(date) != 10:
        return None

    url = str(entry.get("url") or "").strip()
    sha = str(entry.get("sha") or "").strip()
    full = ""
    found = SHA_RE.search(url)
    if found:
        full = found.group(0)
    elif len(sha) == 40:
        full = sha

    record = dict(entry)
    if full:
        record["id"] = f"commit:{full}"
        record["sha"] = sha or full[:7]
    else:
        # Older entries only carry the short SHA; keep them rather than dropping
        # history, and mark why the id is not a full commit hash.
        basis = f"{date}|{sha}|{entry.get('title_en', '')}|{entry.get('title_zh', '')}"
        record["id"] = "commit:" + (sha or hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12])
        record["sha_source"] = "short"
    record["date"] = date
    record["schema_version"] = SCHEMA_VERSION
    return record


NORMALIZERS = {
    "daily_news": normalize_daily_news,
    "academic_frontiers": normalize_frontiers,
    "site_updates": normalize_site_update,
}


def normalize(dataset: str, entry: dict) -> dict | None:
    return NORMALIZERS[dataset](entry)


# --------------------------------------------------------------------------- #
# Merging
# --------------------------------------------------------------------------- #
def merge_items(old_items: list[dict], new_items: list[dict]) -> list[dict]:
    """Merge headline lists by url, keeping translations already stored.

    A re-collected day can drop the Chinese headline that an earlier run paid
    for, so each new item is merged over the stored one instead of replacing it.
    """
    stored = {str(item.get("url") or ""): dict(item) for item in old_items if isinstance(item, dict)}
    merged: list[dict] = []
    for item in new_items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("url") or "")
        previous = stored.get(key)
        if previous is None:
            merged.append(dict(item))
            continue
        combined = dict(previous)
        for field, value in item.items():
            if not _is_empty(value):
                combined[field] = value
        merged.append(combined)
    return merged


def merge_records(old: dict, new: dict, dataset: str) -> dict:
    """Update one record without letting missing fields erase stored ones."""
    merged = dict(old)
    for key, value in new.items():
        if key in ("fetched_at", "schema_version"):
            continue
        if _is_empty(value):
            continue
        if key == "items" and dataset == "daily_news":
            merged["items"] = merge_items(old.get("items") or [], value)
            continue
        merged[key] = value

    # The recent index is a projection and carries no `fetched_at`, so an empty
    # incoming value must never replace the stamp already stored.
    previous_stamp = str(old.get("fetched_at") or "")
    incoming_stamp = str(new.get("fetched_at") or "")
    merged["fetched_at"] = max(previous_stamp, incoming_stamp) or now_iso()
    merged["schema_version"] = SCHEMA_VERSION
    if "sha_source" in old and "sha_source" not in merged:
        merged["sha_source"] = old["sha_source"]
    return merged


def partition_key(dataset: str, record: dict) -> str:
    spec = SPECS[dataset]
    date = str(record.get(spec["date_field"]) or "")
    if not date:
        return "unknown"
    return date[:7] if spec["partition"] == "monthly" else date[:4]


def sort_key(dataset: str, record: dict) -> tuple:
    spec = SPECS[dataset]
    date = str(record.get(spec["date_field"]) or "")
    if dataset == "daily_news":
        return (date,)
    if dataset == "academic_frontiers":
        return (date, str(record.get("journal") or ""), str(record.get("id") or ""))
    return (date, str(record.get("sha") or ""), str(record.get("id") or ""))


# --------------------------------------------------------------------------- #
# Reading and writing the three layers
# --------------------------------------------------------------------------- #
def read_archive(root: Path, dataset: str) -> tuple[list[dict], int]:
    directory = dataset_dir(root, dataset)
    if not directory.is_dir():
        return [], 0
    records: list[dict] = []
    invalid = 0
    for path in sorted(directory.glob("*.jsonl")):
        found, broken = read_jsonl(path)
        records.extend(found)
        invalid += broken
    return records, invalid


def read_index(root: Path, dataset: str) -> tuple[list[dict], int]:
    """Read the existing recent index as a migration source."""
    path = root / SPECS[dataset]["index"]
    if not path.exists():
        return [], 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"warning: cannot parse {path.name}; skipping it as a source", file=sys.stderr)
        return [], 1

    if dataset == "daily_news":
        entries = raw.get("days", []) if isinstance(raw, dict) else []
    elif dataset == "academic_frontiers":
        entries = raw.get("items", []) if isinstance(raw, dict) else []
    else:
        entries = raw if isinstance(raw, list) else []

    records: list[dict] = []
    skipped = 0
    for entry in entries:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        record = normalize(dataset, entry)
        if record is None:
            skipped += 1
        else:
            records.append(record)
    return records, skipped


def public_record(dataset: str, record: dict) -> dict:
    """The shape the site's pages already expect, without archive bookkeeping."""
    public = {key: value for key, value in record.items() if key not in INTERNAL_KEYS}
    if dataset != "academic_frontiers":
        public.pop("id", None)
    return public


def build_index_payload(dataset: str, records: list[dict]) -> object:
    """Cut the archive down to the window the default pages render."""
    if dataset == "site_updates":
        return [public_record(dataset, record) for record in records[: SPECS[dataset]["retention_count"]]]

    spec = SPECS[dataset]
    cutoff = (datetime.now(TZ) - timedelta(days=spec["retention_days"] - 1)).strftime("%Y-%m-%d")
    kept = [record for record in records if str(record.get(spec["date_field"]) or "") >= cutoff]
    if dataset == "daily_news":
        return {
            "updated_at": now_iso(),
            "days": [{"date": record["date"], "items": record.get("items") or []} for record in kept],
        }
    return {"updated_at": now_iso(), "items": [public_record(dataset, record) for record in kept]}


def index_length(dataset: str, payload: object) -> int:
    """How many entries an index payload holds, for the run summary."""
    if dataset == "site_updates":
        return len(payload)  # type: ignore[arg-type]
    if dataset == "daily_news":
        return len(payload["days"])  # type: ignore[index]
    return len(payload["items"])  # type: ignore[index]


def write_index(root: Path, dataset: str, records: list[dict]) -> int:
    payload = build_index_payload(dataset, records)
    write_json(root / SPECS[dataset]["index"], payload)
    return index_length(dataset, payload)


def write_partitions(root: Path, dataset: str, records: list[dict]) -> tuple[int, list[str]]:
    """Write only the partitions whose contents changed; drop empty ones."""
    directory = dataset_dir(root, dataset)
    directory.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(partition_key(dataset, record), []).append(record)

    changed = 0
    keys = sorted(grouped)
    for key in keys:
        path = directory / f"{key}.jsonl"
        wanted = grouped[key]
        payload = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in wanted)
        if path.exists() and path.read_text(encoding="utf-8") == payload:
            continue
        write_jsonl(path, wanted)
        changed += 1

    # A partition that no longer holds anything is removed rather than left as
    # an empty file; the manifest therefore only ever lists real data.
    for path in sorted(directory.glob("*.jsonl")):
        if path.stem not in grouped:
            path.unlink()
            changed += 1
    return changed, keys


def build_manifest_entry(root: Path, dataset: str) -> dict:
    directory = dataset_dir(root, dataset)
    available = []
    if directory.is_dir():
        for path in sorted(directory.glob("*.jsonl")):
            records, _ = read_jsonl(path)
            if not records:
                continue
            available.append(
                {
                    "key": path.stem,
                    "url": f"/{ARCHIVE_RELATIVE.as_posix()}/{SPECS[dataset]['directory']}/{path.name}",
                    "records": len(records),
                    "sha256": sha256_of(path),
                }
            )
    return {
        "format": "jsonl",
        "partition": SPECS[dataset]["partition"],
        "available": available,
    }


def update_manifest(root: Path, datasets: list[str]) -> dict:
    """Refresh only the datasets just written, keeping the others as they are."""
    path = manifest_path(root)
    manifest: dict = {}
    if path.exists():
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("warning: manifest was unreadable; rebuilding it from disk", file=sys.stderr)
            manifest = {}
    if not isinstance(manifest, dict):
        manifest = {}

    manifest["schema_version"] = SCHEMA_VERSION
    manifest["updated_at"] = now_iso()
    archives = manifest.get("archives")
    if not isinstance(archives, dict):
        archives = {}
    # Every dataset gets an entry, even an empty one: a reader can then rely on
    # the key being present and simply see that no partition exists yet.
    for dataset in DATASETS:
        archives[dataset] = build_manifest_entry(root, dataset)
    # Keep a stable, predictable order for readers and diffs.
    manifest["archives"] = {name: archives[name] for name in DATASETS if name in archives}
    write_json(path, manifest)
    return manifest


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
class Stats:
    """What one run did, for the job log."""

    def __init__(self, dataset: str) -> None:
        self.dataset = dataset
        self.added = 0
        self.updated = 0
        self.deduplicated = 0
        self.ignored = 0
        self.index_count = 0
        self.partitions = 0
        self.rewritten = 0

    def as_line(self) -> str:
        return (
            f"{self.dataset}: +{self.added} added, {self.updated} updated, "
            f"{self.deduplicated} merged duplicates, {self.ignored} ignored, "
            f"{self.index_count} in the recent index, {self.partitions} partitions "
            f"({self.rewritten} rewritten)"
        )


def process_dataset(root: Path, dataset: str, incoming: list[dict] | None = None, dry_run: bool = False) -> Stats:
    """Merge every source, write the archive, then regenerate the index."""
    stats = Stats(dataset)

    archived, broken = read_archive(root, dataset)
    stats.ignored += broken
    indexed, skipped = read_index(root, dataset)
    stats.ignored += skipped

    by_id: dict[str, dict] = {}
    # Sources are read weakest first: the archive itself, then the recent index
    # (which may still hold records from before the archive existed), then the
    # records this run just collected. Only the first two can be duplicates of
    # each other; later sources are updates or genuinely new records.
    for source_index, source in enumerate((archived, indexed, incoming or [])):
        seen_in_source: set[str] = set()
        for entry in source:
            # Normalising again is safe: it only fills in the stable id and the
            # archive-only fields, and callers may pass raw index entries.
            record = normalize(dataset, entry)
            if record is None:
                stats.ignored += 1
                continue
            identifier = str(record.get("id") or "")
            if not identifier:
                stats.ignored += 1
                continue
            if identifier in seen_in_source:
                stats.deduplicated += 1
                by_id[identifier] = merge_records(by_id[identifier], record, dataset)
                continue
            seen_in_source.add(identifier)
            if identifier in by_id:
                before = json.dumps(by_id[identifier], ensure_ascii=False, sort_keys=True)
                by_id[identifier] = merge_records(by_id[identifier], record, dataset)
                if json.dumps(by_id[identifier], ensure_ascii=False, sort_keys=True) != before:
                    stats.updated += 1
            else:
                by_id[identifier] = record
                if source_index > 0:  # already in the archive: nothing was added
                    stats.added += 1

    for record in by_id.values():
        record.setdefault("fetched_at", now_iso())

    records = sorted(by_id.values(), key=lambda record: sort_key(dataset, record), reverse=True)

    if dry_run:
        stats.index_count = index_length(dataset, build_index_payload(dataset, records))
        stats.partitions = len({partition_key(dataset, record) for record in records})
        return stats

    rewritten, keys = write_partitions(root, dataset, records)
    stats.rewritten = rewritten
    stats.partitions = len(keys)
    stats.index_count = write_index(root, dataset, records)
    # The manifest carries the checksum of every partition, so it has to follow
    # the write: a collector calling `upsert()` would otherwise leave a stale
    # checksum behind and the snapshot would not verify.
    update_manifest(root, [dataset])
    return stats


def run(root: Path, datasets: list[str], incoming: dict[str, list[dict]] | None = None, dry_run: bool = False) -> list[Stats]:
    incoming = incoming or {}
    results: list[Stats] = []
    for dataset in datasets:
        stats = process_dataset(root, dataset, incoming.get(dataset), dry_run=dry_run)
        results.append(stats)
    if not dry_run:
        update_manifest(root, datasets)
    return results


def upsert(root: Path, dataset: str, records: list[dict], dry_run: bool = False) -> Stats:
    """Used by the collectors: file new records, then rebuild that one index."""
    return process_dataset(root, dataset, records, dry_run=dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", action="append", choices=DATASETS, help="archive one dataset (repeatable)")
    parser.add_argument("--all", action="store_true", help="archive every dataset")
    parser.add_argument("--dry-run", action="store_true", help="report what would change without writing")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root (used by tests)")
    args = parser.parse_args()

    datasets = args.dataset or (list(DATASETS) if args.all else [])
    if not datasets:
        parser.error("pass --all or at least one --dataset")

    results = run(args.root, datasets, dry_run=args.dry_run)
    for stats in results:
        print(stats.as_line())
    print(f"{'dry run' if args.dry_run else 'archive'} complete for {len(results)} dataset(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
