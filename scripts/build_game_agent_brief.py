#!/usr/bin/env python3
"""Build GAME_AGENT_BRIEF.md via RouterAI preset (multi-section orchestrator)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts" / "agent_brief"
DEFAULT_PARTS_DIR = ROOT / "tmp" / "agent_brief" / "parts"
DEFAULT_OUTPUT = ROOT / "docs" / "GAME_AGENT_BRIEF.md"
CORPUS_CHAR_LIMIT = 8000
MAX_TOKENS = 8192
TIMEOUT_SEC = 240.0
DEFAULT_PRESET = "expert"

VALIDATION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("postgresql/sql", re.compile(r"\bpostgresql\b|\basyncpg\b|\balembic\b", re.I)),
    ("sql_statement", re.compile(r"\bSELECT\b|\bINSERT\b|\bUPDATE\b|\bFROM\s+\w+_", re.I)),
    ("orm_table", re.compile(r"\b(?:class|table)\s+\w+\(Base\)", re.I)),
    ("percent_balance", re.compile(r"\+\d+%|\-\d+%|\d+\s*%\s*(?:урон|HP|шанс)", re.I)),
    ("fusion_artifact", re.compile(r"Эксперт\s*[12]|Judge|fusion_roles", re.I)),
]

logger = logging.getLogger(__name__)


def _git_hash() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:
        return "unknown"


def load_sections() -> list[dict]:
    data = json.loads((PROMPTS_DIR / "sections.json").read_text(encoding="utf-8"))
    return list(data["sections"])


def _read_excerpt(path: Path, max_chars: int) -> str:
    if not path.is_file():
        return f"[файл не найден: {path.relative_to(ROOT)}]"
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n\n…[обрезано]…\n\n" + text[-half:]


def build_corpus(sources: list[str], char_limit: int = CORPUS_CHAR_LIMIT) -> str:
    if not sources:
        return ""
    per_file = max(500, char_limit // len(sources))
    parts: list[str] = []
    used = 0
    for rel in sources:
        if used >= char_limit:
            break
        budget = min(per_file, char_limit - used)
        path = ROOT / rel
        excerpt = _read_excerpt(path, budget)
        parts.append(f"### Источник: `{rel}`\n\n{excerpt}")
        used += len(excerpt)
    return "\n\n---\n\n".join(parts)


def build_prompt(section: dict, extra_sections: list[dict] | None = None) -> str:
    common = (PROMPTS_DIR / "_common_constraints.md").read_text(encoding="utf-8")
    task_parts: list[str] = []
    all_sources: list[str] = list(section.get("sources") or [])

    prompt_path = PROMPTS_DIR / section["prompt_file"]
    task_parts.append(prompt_path.read_text(encoding="utf-8"))

    if extra_sections:
        for extra in extra_sections:
            extra_path = PROMPTS_DIR / extra["prompt_file"]
            task_parts.append(extra_path.read_text(encoding="utf-8"))
            all_sources.extend(extra.get("sources") or [])

    corpus = build_corpus(all_sources)
    return (
        f"{common}\n\n"
        f"# Задание на генерацию раздела документа GAME_AGENT_BRIEF\n\n"
        f"## Раздел: {section['title']}\n\n"
        + "\n\n".join(task_parts)
        + f"\n\n## Выдержки из исходников (для фактов, не копируй дословно баланс)\n\n{corpus}\n"
    )


def part_path(parts_dir: Path, section: dict) -> Path:
    return parts_dir / f"{section['id']}_{section['slug']}.md"


def merged_sections(sections: list[dict]) -> list[dict]:
    """Skip sections merged into a previous one (e.g. 01 into 00)."""
    skip_ids: set[str] = set()
    for sec in sections:
        if sec.get("merge_with"):
            skip_ids.add(sec["merge_with"])
    return [s for s in sections if s["id"] not in skip_ids]


def resolve_section(sections: list[dict], spec: str) -> list[dict]:
    if spec == "all":
        return merged_sections(sections)
    for sec in sections:
        if spec in (sec["id"], sec["slug"], f"{sec['id']}_{sec['slug']}"):
            return [sec]
    raise SystemExit(f"Unknown section: {spec}")


async def generate_section(
    section: dict,
    sections: list[dict],
    *,
    parts_dir: Path,
    dry_run: bool,
    resume: bool,
    max_tokens: int,
    timeout_sec: float,
    preset: str,
) -> Path | None:
    out = part_path(parts_dir, section)
    if resume and out.is_file() and out.stat().st_size > 100:
        logger.info("Skip %s (exists)", out.name)
        return out

    extra: list[dict] = []
    if section.get("merge_with"):
        target = next((s for s in sections if s["id"] == section["merge_with"]), None)
        if target:
            extra = [target]

    prompt = build_prompt(section, extra or None)
    if dry_run:
        print(f"\n{'='*60}\nDRY RUN: {section['id']} {section['title']}\n{'='*60}\n")
        print(prompt[:4000])
        if len(prompt) > 4000:
            print(f"\n… [{len(prompt) - 4000} chars truncated in preview] …")
        return None

    from waifu_bot.services.ai_service import generate as ai_generate
    from waifu_bot.services.llm_client import has_text_llm_configured

    if not has_text_llm_configured():
        raise SystemExit("ROUTERAI_API_KEY is not configured")

    caller = f"agent-brief-{section['slug']}"
    logger.info("Generating %s (%s)…", section["id"], section["title"])
    text = await ai_generate(
        prompt,
        preset=preset,
        caller=caller,
        timeout_sec=timeout_sec,
        max_tokens=max_tokens,
        post_process_rhythm=False,
    )
    if not text or not text.strip():
        raise RuntimeError(f"Empty {preset} output for {section['id']}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text.strip() + "\n", encoding="utf-8")
    logger.info("Wrote %s (%d chars)", out, len(text))
    return out


def normalize_section_text(text: str, sec: dict) -> str:
    """Ensure H2 heading and fix common expert output quirks."""
    text = text.strip()
    sid = sec["id"]
    title = sec["title"]
    if sid == "A":
        h2 = "## Приложение A. Справочник"
    elif sid == "00":
        h2 = "## 0. Введение"
    elif sid.isdigit():
        h2 = f"## {int(sid)}. {title}"
    else:
        h2 = f"## {sid}. {title}"

    lines = text.splitlines()
    if not lines:
        return h2 + "\n"

    first = lines[0].strip()
    if first.startswith("##"):
        lines[0] = h2
    elif re.match(r"^\d+\.", first) or first.lower().startswith("приложение"):
        lines[0] = h2
    else:
        lines = [h2, ""] + lines

    out: list[str] = []
    for line in lines:
        m = re.match(r"^(\d+\.\d+(?:\.\d+)?)\s+(.+)$", line.strip())
        if m and not line.strip().startswith("#"):
            out.append(f"### {m.group(1)} {m.group(2)}")
        else:
            m2 = re.match(r"^(\d+\.)\s+([А-ЯA-Z].+)$", line.strip())
            if m2 and sid != "00" and not line.strip().startswith("#"):
                out.append(f"### {m2.group(1)} {m2.group(2)}")
            else:
                out.append(line)
    return "\n".join(out).strip()


def sanitize_document(text: str) -> str:
    """Remove DB product names from presentation doc (keep conceptual storage)."""
    replacements = [
        (r"participant DB as PostgreSQL", "participant DB as База данных"),
        (r"DB\[\(PostgreSQL\)\]", "DB[(База данных)]"),
        (r"\bPostgreSQL\b", "база данных"),
        (r"\bRedis\b", "кэш"),
        (r"агрегирующих данные из база данных и кэш", "агрегирующих игровые данные"),
        (r"UPDATE\[", "обновление["),
    ]
    for old, new in replacements:
        text = re.sub(old, new, text, flags=re.I)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text


def _slug_anchor(title: str) -> str:
    s = title.lower().strip()
    s = re.sub(r"[^\w\s\-]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s)
    return s


def build_toc(sections: list[dict], parts_dir: Path) -> str:
    lines = ["## Оглавление", ""]
    for sec in sections:
        part = part_path(parts_dir, sec)
        if not part.is_file():
            continue
        first_line = part.read_text(encoding="utf-8").splitlines()[0] if part.stat().st_size else sec["title"]
        anchor = _slug_anchor(first_line.lstrip("# ").strip() or sec["title"])
        num = sec["id"]
        if num == "A":
            lines.append(f"- [Приложение A. {sec['title']}](#приложение-a-справочник)")
        elif num == "00":
            lines.append(f"- [0. {sec['title']}](#0-введение)")
            lines.append("- [1. Сквозной игровой цикл](#1-сквозной-игровой-цикл)")
        else:
            lines.append(f"- [{num}. {sec['title']}](#{anchor})")
    lines.append("")
    return "\n".join(lines)


def merge_document(
    sections: list[dict],
    parts_dir: Path,
    output: Path,
    *,
    validate: bool,
    preset: str,
) -> list[str]:
    commit = _git_hash()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = (
        f"# GAME_AGENT_BRIEF — Waifu Bot REBORN\n\n"
        f"> Презентационный бриф для ИИ-агента и миграции WebApp → Steam.  \n"
        f"> Сгенерировано: {now} · commit `{commit}` · preset `{preset}`  \n"
        f"> Без числовых балансов и схем БД. Runtime-справка: [ARCHITECTURE_AND_INTERACTIONS.md](ARCHITECTURE_AND_INTERACTIONS.md)\n\n"
    )
    toc = build_toc(sections, parts_dir)
    body_parts: list[str] = []
    for sec in sections:
        part = part_path(parts_dir, sec)
        if part.is_file():
            body_parts.append(normalize_section_text(part.read_text(encoding="utf-8"), sec))
        else:
            logger.warning("Missing part: %s", part.name)

    doc = header + toc + "\n---\n\n" + "\n\n---\n\n".join(body_parts) + "\n"
    doc = sanitize_document(doc)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(doc, encoding="utf-8")
    logger.info("Merged %s (%d chars)", output, len(doc))

    warnings: list[str] = []
    if validate:
        warnings = validate_document(doc)
        if warnings:
            report = output.with_suffix(".validation.txt")
            report.write_text("\n".join(warnings) + "\n", encoding="utf-8")
            logger.warning("Validation: %d warnings → %s", len(warnings), report)
    return warnings


def validate_document(text: str) -> list[str]:
    warnings: list[str] = []
    for name, pattern in VALIDATION_PATTERNS:
        for match in pattern.finditer(text):
            start = max(0, match.start() - 40)
            end = min(len(text), match.end() + 40)
            snippet = text[start:end].replace("\n", " ")
            warnings.append(f"[{name}] …{snippet}…")
    return warnings[:50]


async def polish_document(
    output: Path,
    *,
    max_tokens: int,
    timeout_sec: float,
    preset: str,
) -> None:
    """Optional final pass: dedupe headings, unify style."""
    from waifu_bot.services.ai_service import generate as ai_generate

    raw = output.read_text(encoding="utf-8")
    if len(raw) > 48000:
        raw = raw[:24000] + "\n\n…[середина опущена для polish]…\n\n" + raw[-24000:]

    prompt = (
        (PROMPTS_DIR / "_common_constraints.md").read_text(encoding="utf-8")
        + "\n\n# Финальная вычитка GAME_AGENT_BRIEF\n\n"
        "Проверь черновик: убери повторы между разделами, артефакты fusion, "
        "выровняй терминологию (ОВ, GD v1). НЕ удаляй mermaid и таблицы. "
        "Верни **полный** документ с заголовком H1.\n\n"
        f"```markdown\n{raw}\n```"
    )
    logger.info("Final polish pass…")
    text = await ai_generate(
        prompt,
        preset=preset,
        caller="agent-brief-polish",
        timeout_sec=timeout_sec,
        max_tokens=max_tokens,
        post_process_rhythm=False,
    )
    if text and len(text) > len(raw) * 0.5:
        output.write_text(text.strip() + "\n", encoding="utf-8")
        logger.info("Polished document written")


async def run(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sections = load_sections()
    parts_dir = args.parts_dir
    parts_dir.mkdir(parents=True, exist_ok=True)

    if args.merge_only:
        merge_document(
            sections, parts_dir, args.output, validate=args.validate, preset=args.preset
        )
        return 0

    targets = resolve_section(sections, args.section)
    for sec in targets:
        await generate_section(
            sec,
            sections,
            parts_dir=parts_dir,
            dry_run=args.dry_run,
            resume=args.resume,
            max_tokens=args.max_tokens,
            timeout_sec=args.timeout,
            preset=args.preset,
        )

    if args.dry_run:
        return 0

    if args.section == "all" or args.merge_after:
        merge_document(
            sections, parts_dir, args.output, validate=args.validate, preset=args.preset
        )

    if args.polish and not args.dry_run:
        await polish_document(
            args.output,
            max_tokens=args.max_tokens,
            timeout_sec=args.timeout,
            preset=args.preset,
        )
        if args.validate:
            doc = args.output.read_text(encoding="utf-8")
            warnings = validate_document(doc)
            if warnings:
                args.output.with_suffix(".validation.txt").write_text(
                    "\n".join(warnings) + "\n", encoding="utf-8"
                )

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--section",
        default="all",
        help="Section id/slug or 'all' (default)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print prompt only")
    parser.add_argument("--resume", action="store_true", help="Skip existing parts")
    parser.add_argument("--merge-only", action="store_true", help="Merge parts → output")
    parser.add_argument("--merge-after", action="store_true", default=True, help="Merge after generation")
    parser.add_argument("--no-merge-after", dest="merge_after", action="store_false")
    parser.add_argument("--polish", action="store_true", help="Final style pass via same preset")
    parser.add_argument(
        "--preset",
        default=DEFAULT_PRESET,
        help=f"AI preset (default: {DEFAULT_PRESET})",
    )
    parser.add_argument("--validate", action="store_true", default=True)
    parser.add_argument("--no-validate", dest="validate", action="store_false")
    parser.add_argument("--parts-dir", type=Path, default=DEFAULT_PARTS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    parser.add_argument("--timeout", type=float, default=TIMEOUT_SEC)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
