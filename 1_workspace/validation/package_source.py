"""Assemble the complete, unabridged handoff without adding a fourth folder."""
from pathlib import Path

root = Path(__file__).resolve().parents[2]
names = [".env.example", ".gitignore", "requirements.txt", "opencode.json", "AGENTS.md", "README.md", "LICENSE",
         "1_workspace/protocol.md", "1_workspace/extraction_matrix.md", "1_workspace/synthesis_report.md",
         "1_workspace/search_strings.txt",
         "1_workspace/SLRBlueprint.tex",
         "2_skills/01_protocol_and_search.md", "2_skills/02_semantic_rank_screen.md",
         "2_skills/03_multimodal_extract.md", "2_skills/04_synthesis_and_bibtex.md",
         "2_skills/05_reasoning_calibration.md", "2_skills/pdf-to-markdown/SKILL.md",
         "2_skills/pdf-to-markdown/agents/openai.yaml",
         "2_skills/engine.py", "3_papers/references.bib",
         "1_workspace/validation_report.md", "1_workspace/validation/test_engine.py",
         "1_workspace/validation/test_pdf_conversion.py",
         "1_workspace/validation/test_publication.py",
         "1_workspace/validation/test_semantic_pipeline.py",
         "1_workspace/validation/live_semantic.py",
         "1_workspace/validation/check_opencode_skills.py",
         "1_workspace/validation/prepare_publication.py",
         "1_workspace/validation/live_connectors.py", "1_workspace/validation/package_source.py"]
blocks = ["# Complete SLR system source\n\nEvery requested text file appears below in full. "
          "The initialized SQLite database is generated from engine.py's exact schema. "
          "The three application folders are 1_workspace, 2_skills, and 3_papers. "
          "Local .git metadata and optional .env are operational files.\n"]
for name in names:
    content = (root / name).read_text(encoding="utf-8")
    language = "python" if name.endswith(".py") else "markdown" if name.endswith(".md") else "text"
    blocks.append(f"## slr-system/{name}\n\n````{language}\n{content.rstrip()}\n````\n")
blocks.append("""## Quickstart (standard Python installation)

From PowerShell in slr-system, with Python, Git, and OpenCode installed:

```powershell
python -m venv 1_workspace/.venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& ./1_workspace/.venv/Scripts/Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
python 2_skills/engine.py init
python 2_skills/engine.py status
opencode --model openai/gpt-6.1-sol
```

Confirm the execution-policy change if prompted; it applies only to the current
PowerShell session. Repeat the policy and activation commands in each new terminal.
Complete the protocol and configure credentials as needed. OpenCode must expose
the requested model through the authenticated provider.

## Quickstart (original local development workspace only)

The portable runtime is excluded from GitHub. Use the commands above for a fresh clone.

```powershell
cd slr-system
$env:PATH = (Resolve-Path '1_workspace/.runtime/python').Path + ';' + (Resolve-Path '1_workspace/.runtime/git/cmd').Path + ';' + $env:PATH
python 2_skills/engine.py status
opencode --model openai/gpt-6.1-sol
```

OpenCode must be installed/authenticated separately. The protocol is intentionally
DRAFT: no review topic or eligibility judgments have been invented.
""")
(root / "1_workspace/system_source.md").write_text("\n".join(blocks), encoding="utf-8")
print(f"Bundled {len(names)} complete source files.")
