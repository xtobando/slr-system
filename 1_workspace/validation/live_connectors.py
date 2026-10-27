"""Small live smoke check; does not change the delivered review database."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_engine import module, TEST_ROOT
import json
import tempfile

root = Path(tempfile.mkdtemp(prefix="live-", dir=TEST_ROOT)).resolve()
assert root.is_relative_to(TEST_ROOT)
engine = module.Engine(root)
try:
    results = []
    for db, query in (("openalex", '"systematic review"'),
                      ("arxiv", '(ti:"systematic review" OR abs:"systematic review")'),
                      ("pubmed", '"systematic review"[Title/Abstract]')):
        stats = {}
        try:
            module.validate_metadata_query(db, query)
            first = next(iter(getattr(engine, db)(query, 1, None, stats)))
            results.append({"db": db, "ok": bool(first["title"]), "title": first["title"],
                            "total": stats.get("total"), "identifier": first.get("doi") or first.get("pmid") or first.get("arxiv_id")})
        except Exception as exc:
            results.append({"db": db, "ok": False, "error": str(exc) if isinstance(exc, module.EngineError) else type(exc).__name__})
    print(json.dumps(results, indent=2))
finally:
    engine.close()
raise SystemExit(0 if all(result["ok"] for result in results) else 1)
