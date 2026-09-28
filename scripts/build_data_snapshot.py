#!/usr/bin/env python3
"""Pack one calendar year of JSONL archives into a releaseable ZIP snapshot.

The snapshot is meant for a GitHub Release, so it has to stand on its own: it
carries the year's partition files, a manifest excerpt describing them, a
SHA-256 file for verification, and a README that says what the data is and what
it deliberately does not contain.

Nothing is written into the repository: the ZIP goes to the output directory the
caller passes (the workflow uses the runner's temporary directory), so no build
artefact can end up in a commit by accident.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # Hosts without the IANA tz database keep the same offset.
    from datetime import timedelta, timezone

    TZ = timezone(timedelta(hours=8))


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import archive_data  # noqa: E402  (the module lives next to this script)


ZIP_PREFIX = "haoxiangluo-data-archive"

README_TEMPLATE = """# Website data archive {year}

Snapshot generated {generated} (Asia/Shanghai) from the JSONL archives of
<https://haoxiangluo.github.io>.

## Contents

| File | Records | Description |
| --- | --- | --- |
| `daily-news/{year}-*.jsonl` | {daily_news} | One line per day; each line holds that day's headlines (title, translated title, source, link). |
| `academic-frontiers/{year}.jsonl` | {academic_frontiers} | One line per article: metadata only, plus an abstract excerpt of at most 450 characters. |
| `site-updates/{year}.jsonl` | {site_updates} | One line per site-log entry, keyed by commit. |

- `manifest.json` — the archive manifest excerpt for this year (partition keys,
  record counts and SHA-256 checksums).
- `SHA256SUMS.txt` — SHA-256 of every file in this archive.

## Schema

`schema_version` {schema_version}. Every line of every JSONL file is a complete
JSON object; parse the files line by line. Stable ids: `daily-news:YYYY-MM-DD`,
`doi:<DOI>` (or `openalex:<work id>` when a DOI is missing), `commit:<sha>`.

## Scope and limits

- The archive is metadata only. It contains **no** article full texts, **no**
  PDFs and **no** personal or private information.
- Headlines and links belong to their publishers; the Chinese headline is a
  machine translation and may differ from the original wording.
- Article metadata comes from OpenAlex. Abstracts are excerpts, never full text.
- The journal shortlist behind Academic Frontiers is curated by hand and
  checked once a year against licensed JCR data; the archive shows no inferred
  quartile.

## Verifying a download

```sh
sha256sum -c SHA256SUMS.txt
```
"""


def year_partitions(root: Path, dataset: str, year: int) -> list[Path]:
    """The partition files that belong to `year` for one dataset."""
    directory = archive_data.dataset_dir(root, dataset)
    if not directory.is_dir():
        return []
    if archive_data.SPECS[dataset]["partition"] == "monthly":
        prefix = f"{year}-"
        return sorted(path for path in directory.glob("*.jsonl") if path.stem.startswith(prefix))
    exact = directory / f"{year}.jsonl"
    return [exact] if exact.exists() else []


def collect_files(root: Path, year: int) -> dict[str, list[Path]]:
    return {
        dataset: year_partitions(root, dataset, year)
        for dataset in archive_data.DATASETS
    }


def count_records(paths: list[Path]) -> int:
    total = 0
    for path in paths:
        records, _ = archive_data.read_jsonl(path)
        total += len(records)
    return total


def manifest_excerpt(root: Path, year: int) -> dict:
    """The manifest, narrowed to the year being released."""
    path = archive_data.manifest_path(root)
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    archives = manifest.get("archives") if isinstance(manifest, dict) else {}
    excerpt: dict = {
        "schema_version": archive_data.SCHEMA_VERSION,
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "year": year,
        "archives": {},
    }
    for dataset in archive_data.DATASETS:
        entry = (archives or {}).get(dataset) or {}
        keys = [path.stem for path in year_partitions(root, dataset, year)]
        available = [item for item in entry.get("available", []) if item.get("key") in keys]
        excerpt["archives"][dataset] = {
            "format": "jsonl",
            "partition": archive_data.SPECS[dataset]["partition"],
            "available": available,
        }
    return excerpt


def build_zip(root: Path, year: int, output_dir: Path) -> tuple[Path, dict]:
    files = collect_files(root, year)
    if not any(files.values()):
        raise SystemExit(f"error: no archived partitions found for {year}")

    counts = {dataset: count_records(paths) for dataset, paths in files.items()}
    excerpt = manifest_excerpt(root, year)

    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{ZIP_PREFIX}-{year}.zip"

    checksums: dict[str, str] = {}
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for dataset, paths in files.items():
            directory = archive_data.SPECS[dataset]["directory"]
            for path in paths:
                name = f"{directory}/{path.name}"
                bundle.write(path, arcname=name)
                checksums[name] = archive_data.sha256_of(path)

        manifest_bytes = (json.dumps(excerpt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        bundle.writestr("manifest.json", manifest_bytes.decode("utf-8"))
        checksums["manifest.json"] = archive_data.sha256_bytes(manifest_bytes)

        readme = README_TEMPLATE.format(
            year=year,
            generated=datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
            schema_version=archive_data.SCHEMA_VERSION,
            **counts,
        )
        bundle.writestr("README.md", readme)
        checksums["README.md"] = archive_data.sha256_bytes(readme.encode("utf-8"))

        sums = "".join(f"{digest}  {name}\n" for name, digest in sorted(checksums.items()))
        bundle.writestr("SHA256SUMS.txt", sums)
        checksums["SHA256SUMS.txt"] = archive_data.sha256_bytes(sums.encode("utf-8"))

    summary = {
        "year": year,
        "schema_version": archive_data.SCHEMA_VERSION,
        "counts": counts,
        "checksums": checksums,
        "zip": str(zip_path),
        "zip_sha256": archive_data.sha256_of(zip_path),
        "files": sorted(checksums),
    }
    return zip_path, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, required=True, help="calendar year to package")
    parser.add_argument("--output-dir", type=Path, required=True, help="where the ZIP is written")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root (used by tests)")
    parser.add_argument("--summary-json", type=Path, help="write the run summary here as JSON")
    args = parser.parse_args()

    zip_path, summary = build_zip(args.root, args.year, args.output_dir)

    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {zip_path}")
    for dataset, count in summary["counts"].items():
        print(f"  {dataset}: {count} records")
    for name in summary["files"]:
        print(f"  {name}: {summary['checksums'][name]}")
    print(f"  zip sha256: {summary['zip_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
