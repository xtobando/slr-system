"""Copy public source into a clean upstream clone without copying a live review."""
import argparse
from contextlib import closing
from datetime import date
import importlib.util
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile


SOURCE_FILES = (
    ".env.example", ".gitignore", "requirements.txt", "opencode.json", "AGENTS.md", "README.md", "LICENSE",
    "1_workspace/SLRBlueprint.tex", "1_workspace/validation_report.md",
    "1_workspace/validation/test_engine.py", "1_workspace/validation/test_pdf_conversion.py",
    "1_workspace/validation/test_publication.py",
    "1_workspace/validation/test_semantic_pipeline.py", "1_workspace/validation/live_connectors.py",
    "1_workspace/validation/live_semantic.py", "1_workspace/validation/check_opencode_skills.py",
    "1_workspace/validation/package_source.py", "1_workspace/validation/prepare_publication.py",
    "2_skills/engine.py", "2_skills/01_protocol_and_search.md", "2_skills/02_semantic_rank_screen.md",
    "2_skills/03_multimodal_extract.md", "2_skills/04_synthesis_and_bibtex.md",
    "2_skills/05_reasoning_calibration.md", "2_skills/pdf-to-markdown/SKILL.md",
    "2_skills/pdf-to-markdown/agents/openai.yaml", "2_skills/latex-visuals/SKILL.md",
)
TEMPLATES = ("1_workspace/protocol.md", "1_workspace/extraction_matrix.md",
             "1_workspace/synthesis_report.md", "3_papers/references.bib")


def git(destination, *args):
    result = subprocess.run(["git", "-c", f"safe.directory={destination.as_posix()}",
                             "-C", str(destination), *args], check=True,
                            capture_output=True, encoding="utf-8")
    return result.stdout.strip()


def prepare(root, destination):
    staging = (root / "1_workspace/.publication").resolve()
    destination = destination.resolve()
    if destination == staging or staging not in destination.parents:
        raise ValueError("Destination must be a clone beneath 1_workspace/.publication/.")
    if Path(git(destination, "rev-parse", "--show-toplevel")).resolve() != destination:
        raise ValueError("Destination must be the root of its own Git clone.")
    if git(destination, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Destination must be clean; existing edits will not be overwritten.")
    if git(destination, "rev-parse", "HEAD") != git(destination, "rev-parse", "origin/main"):
        raise ValueError("Destination HEAD must equal its fetched origin/main.")
    # Preserve only empty upstream templates; never silently republish an existing review.
    templates = {name: git(destination, "show", f"HEAD:{name}") + "\n" for name in TEMPLATES}
    templates["1_workspace/protocol.md"] = templates["1_workspace/protocol.md"].replace(
        "Default 200 per provider (or user-specified limit).",
        "5,000 per query/provider in search_strings.txt (or an explicit override).",
    )
    if any(line.lstrip().startswith("@") for line in templates["3_papers/references.bib"].splitlines()):
        raise ValueError("Upstream bibliography contains review data; prepare empty templates first.")
    database = destination / "1_workspace/slr_state.sqlite"
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        for table in ("papers", "screening", "extractions"):
            if connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]:
                raise ValueError("Upstream database is not empty; prepare an empty template first.")
    # Check every source before making any edits.
    for name in SOURCE_FILES:
        source, target = root / name, destination / name
        if not source.is_file() or source.resolve() != source.absolute():
            raise ValueError(f"Source missing or indirect: {name}")
        if destination not in target.resolve().parents:
            raise ValueError(f"Indirect destination: {name}")
    for name in SOURCE_FILES:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    for name, content in templates.items():
        (destination / name).write_text(content, encoding="utf-8")
    # Recreate the empty schema rather than copying upstream setup/checkpoint logs.
    spec = importlib.util.spec_from_file_location("publication_engine", destination / "2_skills/engine.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix=".template-", dir=destination / "1_workspace") as scratch:
        engine = module.Engine(Path(scratch))
        engine.close()
        shutil.copyfile(Path(scratch) / "1_workspace/slr_state.sqlite", database)
    plan = f'''# Executable example, not a validated systematic-review strategy.
# Replace the topic, dates, translations and semantic query for your own RQs.
[review]
since = 2015-01-01
until = {date.today().isoformat()}
max_results = 5000
semantic_threshold = 0.5
semantic_query = Retrieval augmented generation methods for factual question answering, including retrieval quality, answer accuracy, factuality and hallucination evaluation.

[openalex.question_answering]
db = openalex
query = ("retrieval augmented generation" OR "retrieval-augmented generation") AND ("question answering" OR factuality OR hallucination)

[arxiv.question_answering]
db = arxiv
query = (ti:"retrieval augmented generation" OR abs:"retrieval augmented generation" OR ti:"retrieval-augmented generation" OR abs:"retrieval-augmented generation") AND (ti:"question answering" OR abs:"question answering" OR ti:factuality OR abs:factuality OR ti:hallucination OR abs:hallucination)

[pubmed.question_answering]
db = pubmed
query = ("retrieval augmented generation"[Title/Abstract] OR "retrieval-augmented generation"[Title/Abstract]) AND ("question answering"[Title/Abstract] OR factuality[Title/Abstract] OR hallucination[Title/Abstract])
'''
    (destination / "1_workspace/search_strings.txt").write_text(plan, encoding="utf-8")
    subprocess.run([sys.executable, "-B", str(destination / "1_workspace/validation/package_source.py")],
                   check=True, cwd=destination)
    print(f"Prepared source-only working tree: {destination}")
    print("Live review files and local Git history were not copied. Review the diff before committing.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path,
                        help="Clean upstream clone beneath 1_workspace/.publication/.")
    args = parser.parse_args()
    try:
        prepare(Path(__file__).resolve().parents[2], args.destination)
    except (OSError, ValueError, sqlite3.Error, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Publication preparation failed: {exc}\n")


if __name__ == "__main__":
    main()
