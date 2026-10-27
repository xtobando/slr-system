"""Behavioral regression tests; run with the same interpreter as engine.py."""
import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import pymupdf as fitz

PROJECT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("slr_engine", PROJECT / "2_skills/engine.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FixtureHTTP:
    def __init__(self, callback):
        self.callback = callback

    def data(self, url, params=None, xml=False):
        return self.callback(url, params, xml)

    def close(self):
        return None


class FixtureEncoder:
    """Vectors for workflow tests; real-model quality is checked separately."""
    def __init__(self, workspace, backend=None, model=None):
        if backend == "tfidf" or os.getenv("SLR_RANK_BACKEND") == "tfidf":
            raise module.EngineError("TF-IDF is not a semantic backend.")
        self.identity = {"backend": "fastembed", "model": "fixture-embedding"}

    def encode(self, texts, mode="passage"):
        return [[0.0, 1.0] if any(word in text.lower() for word in ("geological", "mineral", "ocean"))
                else [1.0, 0.0] for text in texts]

    def close(self):
        pass


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="case-", dir=TEST_ROOT)).resolve()
        assert self.root.is_relative_to(TEST_ROOT)
        self.e = module.Engine(self.root)
        encoder = patch.object(module, "SemanticEncoder", FixtureEncoder)
        encoder.start()
        self.addCleanup(encoder.stop)
        shutil.copyfile(PROJECT / ".gitignore", self.root / ".gitignore")
        shutil.copyfile(PROJECT / "1_workspace/protocol.md", self.root / "1_workspace/protocol.md")
        self.sink = io.StringIO()
        self.output = contextlib.redirect_stdout(self.sink)
        self.output.__enter__()

    def tearDown(self):
        self.output.__exit__(None, None, None)
        self.e.close()
        target = self.root.resolve()
        assert target.is_relative_to(TEST_ROOT) and target != TEST_ROOT
        def remove_readonly(function, path, exception):
            safe = Path(path).resolve()
            assert safe.is_relative_to(TEST_ROOT)
            os.chmod(safe, 0o700)
            function(safe)
        shutil.rmtree(target, onerror=remove_readonly)

    def add(self, db="openalex", **changes):
        record = {"title": "Learning evidence in systematic reviews", "authors": ["Ada Lovelace"],
                  "year": 2024, "abstract": "We study machine learning in systematic reviews.",
                  "doi": "10.1234/Example", "openalex_id": "https://openalex.org/W1"}
        record.update(changes)
        with self.e.conn:
            self.e.upsert(record, db, "fixture")
        return self.e.conn.execute("SELECT bib_key FROM papers ORDER BY rowid DESC").fetchone()[0]

    def decide(self, key, stage="TITLE_ABSTRACT", decision="INCLUDE", quote=None, **extra):
        try:
            self.e.require_semantic_pass(self.e.paper(key))
        except module.EngineError:
            self.e.rank("machine learning systematic reviews", threshold=0.5)
        args = argparse.Namespace(bib_key=key, stage=stage, decision=decision,
                                  code="EC1" if decision == "EXCLUDE" else "IC1",
                                  devils_advocate="The study population may be outside the specified scope.",
                                  quote=quote or "We study machine learning in systematic reviews.", notes="")
        for name, value in extra.items():
            setattr(args, name, value)
        self.e.record_decision(args)

    def pdf(self, key):
        path = self.root / "3_papers/raw_pdfs" / (key + ".pdf")
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((72, 72), "The sample included 42 participants. Figure 1. Architecture.")
            page.draw_rect(fitz.Rect(72, 100, 200, 180))
            doc.new_page()
            doc.save(path)
        return path

    def final_paper(self):
        key = self.add()
        self.decide(key)
        self.pdf(key)
        self.assertTrue(self.e.ingest(key))
        self.decide(key, "FULL_TEXT", quote="The sample included 42 participants.")
        return key

    def test_exact_schema_and_foreign_keys(self):
        tables = {r[0] for r in self.e.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        self.assertEqual(tables, {"papers", "screening", "extractions", "audit_log"})
        self.assertEqual(len(self.e.conn.execute("PRAGMA table_info(papers)").fetchall()), 17)
        self.assertEqual(len(self.e.conn.execute("PRAGMA index_list(papers)").fetchall()), 5)
        with self.assertRaises(sqlite3.IntegrityError):
            self.e.conn.execute("INSERT INTO screening(bib_key) VALUES('unknown')")
        self.e.conn.rollback()

    def test_cross_database_dedup_and_repeat_counts(self):
        key = self.add()
        self.add("arxiv", doi="https://doi.org/10.1234/EXAMPLE", arxiv_id="2401.00001v2", openalex_id=None)
        self.add("arxiv", arxiv_id="2401.00001v4", openalex_id=None)
        self.add("pubmed", pmid="1234", openalex_id=None)
        self.assertEqual(self.e.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0], 1)
        paper = self.e.paper(key)
        self.assertEqual(paper["arxiv_id"], "2401.00001")
        self.assertEqual(paper["source_db"], "arxiv,openalex,pubmed")
        counts = self.e.flow_counts()
        self.assertEqual(counts["identified"], 3)
        self.assertEqual(counts["duplicates_removed"], 2)
        self.e.sync_bib()
        self.e.sync_bib()
        self.assertEqual((self.root / "3_papers/references.bib").read_text().count("@article"), 1)

    def test_title_dedup_and_identifier_conflict(self):
        self.add(doi=None, openalex_id=None)
        self.add("arxiv", doi=None, openalex_id=None, title="Learning Evidence: in Systematic Reviews!", arxiv_id="2401.00111")
        self.assertEqual(self.e.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0], 1)
        self.add("arxiv", doi="10.2000/new", arxiv_id="2401.99999", openalex_id=None)
        self.assertEqual(self.e.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0], 2)

    def test_bibkey_collision_suffixes(self):
        keys = []
        for index in range(29):
            keys.append(self.add(doi=f"10.1/{index}", openalex_id=f"https://openalex.org/W{index}",
                                 title=f"Learning study {index}"))
        self.assertEqual(len(set(keys)), 29)
        self.assertTrue(keys[1].endswith("a"))
        self.assertTrue(keys[27].endswith("aa"))

    def test_quote_first_validation_and_stage_gating(self):
        key = self.add()
        with self.assertRaises(module.EngineError):
            self.decide(key, quote="This is invented.")
        with self.assertRaises(module.EngineError):
            self.decide(key, devils_advocate=" ")
        with self.assertRaises(module.EngineError):
            self.decide(key, code="EC1")
        with self.assertRaises(module.EngineError):
            self.decide(key, "FULL_TEXT")
        self.assertEqual(self.e.paper(key)["title"], "Learning evidence in systematic reviews")
        self.decide(key, quote="We study machine\nlearning in systematic reviews.")

    def test_pdf_markers_blank_page_visuals_and_200_dpi(self):
        key = self.add()
        self.decide(key)
        self.pdf(key)
        self.assertTrue(self.e.ingest(key))
        folder = self.root / "3_papers/parsed_cache" / key
        text = (folder / "fulltext.md").read_text(encoding="utf-8")
        self.assertIn("<!-- PAGE 2 -->", text)
        self.assertEqual(text.count("[VISUAL_ASSET:"), 2)
        pix = fitz.Pixmap(str(folder / "page_1_visual.png"))
        self.assertEqual(pix.xres, 200)
        self.assertGreater(pix.width, 1600)

    def test_text_extraction_is_page_grounded_and_idempotent(self):
        key = self.final_paper()
        args = argparse.Namespace(bib_key=key, variable="sample", quote="The sample included 42 participants.",
                                  page=1, value="42", used_vision=0)
        self.e.record_extraction(args)
        self.e.record_extraction(args)
        self.assertEqual(self.e.conn.execute("SELECT COUNT(*) FROM extractions").fetchone()[0], 1)
        args.page = 2
        with self.assertRaises(module.EngineError):
            self.e.record_extraction(args)
        args.page = 3
        with self.assertRaises(module.EngineError):
            self.e.record_extraction(args)
        matrix = (self.root / "1_workspace/extraction_matrix.md").read_text()
        self.assertIn(f"[@{key}](../3_papers/raw_pdfs/{key}.pdf)", matrix)
        self.assertIn("([DOI](https://doi.org/10.1234/example))", matrix)

    def test_visual_evidence_requires_page_and_asset(self):
        key = self.final_paper()
        args = argparse.Namespace(bib_key=key, variable="figure", quote="Visible architecture panel",
                                  page=1, value="Reviewer inspected the architecture", used_vision=1)
        self.e.record_extraction(args)
        (self.root / "3_papers/parsed_cache" / key / "page_1_visual.png").unlink()
        with self.assertRaises(module.EngineError):
            self.e.record_extraction(args)

    def test_prisma_history_reopening_and_report_preservation(self):
        key = self.final_paper()
        counts = self.e.flow_counts()
        self.assertEqual((counts["screened"], counts["fulltext_sought"], counts["final_included"]), (1, 1, 1))
        self.decide(key, "FULL_TEXT", "EXCLUDE", quote="The sample included 42 participants.")
        self.assertEqual(self.e.flow_counts()["ft_exclusions"], {"EC1": 1})
        self.decide(key, decision="EXCLUDE")
        counts = self.e.flow_counts()
        self.assertEqual(counts["fulltext_sought"], 0)
        self.assertEqual(counts["ft_excluded"], 0)
        self.assertEqual(counts["ta_excluded"], 1)
        report = self.root / "1_workspace/synthesis_report.md"
        report.write_text("# Narrative\nKeep this.\n<!-- PRISMA:START -->old<!-- PRISMA:END -->\nKeep that.")
        self.e.prisma()
        self.assertIn("Keep this.", report.read_text())
        self.assertIn("Keep that.", report.read_text())
        self.assertEqual(report.read_text().count("```mermaid"), 1)

    def test_manual_pdf_is_not_an_exclusion(self):
        key = self.add(oa_pdf_url=None)
        self.decide(key)
        with patch.dict(os.environ, {"UNPAYWALL_EMAIL": "", "INSTITUTIONAL_PROXY_URL": ""}):
            self.assertFalse(self.e.ingest(key))
        counts = self.e.flow_counts()
        self.assertEqual(counts["manual_pdf"], 1)
        self.assertEqual(counts["ta_excluded"] + counts["ft_excluded"], 0)

    def test_rank_determinism_and_batch_limits(self):
        key = self.add()
        self.add(title="Geological minerals", doi="10.1/mineral", openalex_id="W9", abstract="Rock formation and mineral composition.")
        with patch.dict(os.environ, {"SLR_RANK_BACKEND": "fastembed"}):
            self.e.rank("machine learning systematic reviews")
            scores = list(self.e.conn.execute("SELECT semantic_score FROM screening ORDER BY bib_key"))
            self.e.rank("machine learning systematic reviews")
            self.assertEqual([r[0] for r in scores], [r[0] for r in self.e.conn.execute("SELECT semantic_score FROM screening ORDER BY bib_key")])
        with self.assertRaises(module.EngineError):
            self.e.fetch_batch("screen", 16)
        with self.assertRaises(module.EngineError):
            self.e.fetch_batch("extract", 4)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.e.fetch_batch("screen")
        items = json.loads(output.getvalue())
        self.assertEqual(items[0]["bib_key"], key)
        self.assertTrue(all(0 <= r["semantic_score"] <= 1 for r in items))

    def test_openalex_pagination_and_abstract_reconstruction(self):
        calls = []
        def fetch(url, params, xml):
            calls.append(dict(params))
            index = len(calls)
            return {"meta": {"count": 2, "next_cursor": "second" if index == 1 else None},
                    "results": [{"id": f"W{index}", "title": f"Study {index}",
                                 "abstract_inverted_index": {"second": [1], "first": [0]},
                                 "best_oa_location": {"pdf_url": "https://example.org/paper.pdf"}}]}
        self.e.http = FixtureHTTP(fetch)
        stats = {}
        with patch.dict(os.environ, {"OPENALEX_API_KEY": "fixture-key"}):
            rows = list(self.e.openalex("topic", 2, "2024-01-01", stats))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["abstract"], "first second")
        self.assertEqual(calls[1]["cursor"], "second")
        self.assertIn("from_publication_date:2024-01-01", calls[0]["filter"])

    def test_arxiv_atom_and_date_filter(self):
        feed = '''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:o="http://a9.com/-/spec/opensearch/1.1/" xmlns:x="http://arxiv.org/schemas/atom"><o:totalResults>1</o:totalResults><entry><id>http://arxiv.org/abs/2401.00001v2</id><title>A study</title><summary>An abstract</summary><published>2024-01-01T00:00:00Z</published><author><name>Ada Lovelace</name></author><x:doi>10.1/study</x:doi></entry></feed>'''
        def fetch(url, params, xml):
            self.assertIn("submittedDate:[202401010000", params["search_query"])
            return ET.fromstring(feed)
        self.e.http = FixtureHTTP(fetch)
        rows = list(self.e.arxiv('all:"review"', 3, "2024-01-01", {}))
        self.assertEqual(rows[0]["arxiv_id"], "2401.00001")
        self.assertEqual(rows[0]["oa_pdf_url"], "https://arxiv.org/pdf/2401.00001.pdf")

    def test_pubmed_mixed_xml_and_pmc_metadata(self):
        article = '''<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><ArticleTitle>Study of <i>cells</i></ArticleTitle><Abstract><AbstractText Label="RESULTS">42 participants</AbstractText></Abstract><Journal><Title>Journal</Title><JournalIssue><PubDate><MedlineDate>2024 Jan-Feb</MedlineDate></PubDate></JournalIssue></Journal><AuthorList><Author><LastName>Lovelace</LastName><ForeName>Ada</ForeName></Author></AuthorList></Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="doi">10.1/cells</ArticleId><ArticleId IdType="pmc">PMC123</ArticleId></ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>'''
        def fetch(url, params, xml):
            if "esearch" in url:
                self.assertEqual(params["datetype"], "pdat")
                return ET.fromstring("<eSearchResult><Count>1</Count><IdList><Id>123</Id></IdList></eSearchResult>")
            return ET.fromstring(article)
        self.e.http = FixtureHTTP(fetch)
        rows = list(self.e.pubmed("cells", 10, "2024-01-01", {}))
        self.assertEqual(rows[0]["title"], "Study of cells")
        self.assertEqual(rows[0]["year"], 2024)
        self.assertEqual(rows[0]["pmc_id"], "PMC123")
        self.assertEqual(rows[0]["authors"], ["Lovelace, Ada"])

    def test_capped_search_and_failure_keep_provenance(self):
        def capped(query, maximum, since, stats):
            stats["total"] = 10
            yield {"title": "Search study", "authors": ["Ada Lovelace"], "openalex_id": "W1"}
        self.e.openalex = capped
        self.assertFalse(self.e.search("topic", ["openalex"], 1))
        row = self.e.conn.execute("SELECT action,notes FROM audit_log ORDER BY id DESC").fetchone()
        self.assertEqual(row[0], "capped")
        self.assertEqual(json.loads(row[1])["retrieved"], 1)
        def failure(query, maximum, since, stats):
            raise module.EngineError("Intentional provider failure")
        self.e.arxiv = failure
        self.assertFalse(self.e.search("topic", ["arxiv"], 1))
        self.assertEqual(self.e.flow_counts()["identified"], 1)

    def test_download_validates_pdf_and_rejects_html(self):
        key = self.add()
        original = self.pdf(key)
        pdf_bytes = original.read_bytes()
        original.unlink()
        class Response:
            def __init__(self, content):
                self.content = content
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def iter_content(self, size):
                yield self.content
        class Client:
            def __init__(self, content):
                self.content = content
            def get(self, url, stream):
                return Response(self.content)
        with self.assertRaises(module.EngineError):
            self.e.download("https://example.org/login", original, Client(b"<html>Log in</html>"))
        self.assertFalse(original.exists())
        self.assertFalse(original.with_suffix(".pdf.part").exists())
        self.e.download("https://example.org/paper", original, Client(pdf_bytes))
        self.assertEqual(original.read_bytes(), pdf_bytes)

    def test_interrupted_initial_search_is_retried_by_update(self):
        (self.root / "1_workspace/protocol.md").write_text("## Research Questions\nHow do reviews work?\n## PICOC\nSystematic reviews.\n")
        with self.e.conn:
            self.e.audit("search", "started", {"db": "openalex", "started": "2024-01-01T00:00:00+00:00",
                         "since": None, "max_results": 20}, "review")
        with patch.object(self.e, "search", return_value=True) as search, patch.object(self.e, "rank"), \
             patch.object(self.e, "checkpoint"), patch.object(self.e, "stage_skill_updates", return_value={}):
            self.e.update()
        search.assert_called_once_with("review", ["openalex"], 20, None)

    def test_checkpoint_snapshots_sqlite_and_preserves_unrelated_index(self):
        self.e.init()
        self.add()
        unrelated = self.root / "2_skills/unrelated.md"
        unrelated.write_text("Unrelated staged work")
        self.e.git("add", "2_skills/unrelated.md")
        commit = self.e.checkpoint("Test backup")
        files = self.e.git("ls-tree", "-r", "--name-only", commit).splitlines()
        self.assertIn("1_workspace/slr_state.sqlite", files)
        self.assertIn("3_papers/references.bib", files)
        self.assertNotIn("2_skills/unrelated.md", files)
        self.assertIn("2_skills/unrelated.md", self.e.git("diff", "--cached", "--name-only"))
        snapshot = self.root / "1_workspace/snapshot.sqlite"
        snapshot.write_bytes(self.e.git("show", f"{commit}:1_workspace/slr_state.sqlite", binary=True))
        with contextlib.closing(sqlite3.connect(snapshot)) as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0], 1)

    def test_replaced_pdf_requires_review_and_invalidates_final_inclusion(self):
        key = self.final_paper()
        pdf = self.root / "3_papers/raw_pdfs" / (key + ".pdf")
        replacement = pdf.with_suffix(".new.pdf")
        with fitz.open(pdf) as doc:
            doc[0].insert_text((72, 250), "A new version of this report.")
            doc.save(replacement)
        os.replace(replacement, pdf)
        with self.assertRaises(module.EngineError):
            self.decide(key, "FULL_TEXT", quote="The sample included 42 participants.")
        self.assertTrue(self.e.ingest(key))
        self.assertEqual(self.e.flow_counts()["final_included"], 0)
        self.assertEqual(self.e.flow_counts()["assessment_pending"], 1)

    def test_failed_reparse_does_not_preserve_final_inclusion(self):
        key = self.final_paper()
        pdf = self.root / "3_papers/raw_pdfs" / (key + ".pdf")
        pdf.write_bytes(b"not a valid PDF")
        self.assertFalse(self.e.ingest(key))
        self.assertEqual(self.e.flow_counts()["final_included"], 0)

    def test_update_uses_completed_watermark_and_original_translations(self):
        (self.root / "1_workspace/protocol.md").write_text("## Research Questions\nHow do reviews work?\n## PICOC\nSystematic reviews using machine learning.\n")
        for db, query, action, started in [("openalex", "learning", "completed", "2024-01-02T00:00:00+00:00"),
                                           ("arxiv", "all:learning", "capped", "2024-01-03T00:00:00+00:00")]:
            with self.e.conn:
                self.e.audit("search", action, {"db": db, "started": started, "since": None, "max_results": 200}, query)
        calls = []
        with patch.object(self.e, "search", side_effect=lambda *a: calls.append(a) or True), \
             patch.object(self.e, "rank"), patch.object(self.e, "checkpoint"), \
             patch.object(self.e, "stage_skill_updates", return_value={"status": "no_upstream"}):
            self.assertTrue(self.e.update())
        self.assertEqual(calls[0], ("learning", ["openalex"], 200, "2024-01-02"))
        self.assertEqual(calls[1], ("all:learning", ["arxiv"], 200, None))

    def test_upstream_updates_stage_without_overwriting_state_or_code(self):
        self.e.init()
        skill = self.root / "2_skills/engine.py"
        skill.write_text("original implementation\n")
        self.e.git("add", "2_skills/engine.py", ".gitignore")
        self.e.git("-c", "user.name=Test", "-c", "user.email=test@localhost", "commit", "-qm", "Initial source")
        branch = self.e.git("branch", "--show-current")
        remote = self.root / "1_workspace/.tests/upstream"
        remote.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([shutil.which("git"), "clone", "--quiet", str(self.root), str(remote)], check=True)
        (remote / "2_skills/engine.py").write_text("new implementation\n")
        for arguments in [("add", "."), ("-c", "user.name=Test", "-c", "user.email=test@localhost", "commit", "-qm", "New skill")]:
            subprocess.run([shutil.which("git"), "-C", str(remote), *arguments], check=True)
        self.e.git("remote", "add", "origin", str(remote))
        self.e.git("fetch", "--quiet", "origin")
        self.e.git("branch", "--set-upstream-to", "origin/" + branch)
        before = (self.root / "1_workspace/protocol.md").read_bytes()
        result = self.e.stage_skill_updates()
        self.assertEqual(skill.read_text(), "original implementation\n")
        self.assertEqual((self.root / result["path"] / "2_skills/engine.py").read_text(), "new implementation\n")
        self.assertEqual(before, (self.root / "1_workspace/protocol.md").read_bytes())

    def test_nested_workspace_lock_rejected(self):
        with module.workspace_lock(self.root / "1_workspace"):
            with self.assertRaises(module.EngineError):
                with module.workspace_lock(self.root / "1_workspace"):
                    self.fail("Second lock should not succeed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
