"""Behavioral checks for the metadata-only semantic prefilter."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from test_engine import module, FixtureEncoder, FixtureHTTP, TEST_ROOT


class SemanticPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="case-semantic-", dir=TEST_ROOT)
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.engine = module.Engine(self.root)
        self.addCleanup(self.engine.close)
        self.sink = io.StringIO()
        redirect = contextlib.redirect_stdout(self.sink)
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)

    def add(self, title="Muscle signal prosthetic control", abstract="Learn to decode muscle electrical signals", identifier="W1"):
        with self.engine.conn:
            self.engine.upsert({"title": title, "abstract": abstract, "openalex_id": identifier}, "openalex", "fixture")
        return self.engine.conn.execute("SELECT bib_key FROM papers WHERE openalex_id=?", (identifier,)).fetchone()[0]

    def rank(self, threshold=0.5):
        with patch.object(module, "SemanticEncoder", FixtureEncoder):
            return self.engine.rank("Myoelectric prosthesis control", threshold=threshold)

    def test_only_passed_records_are_exposed_to_llm(self):
        relevant = self.add()
        self.add("Geological minerals", "Ocean sediment composition", "W2")
        self.add("Unknown abstract", None, "W3")
        self.rank()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.engine.fetch_batch("screen")
        records = json.loads(output.getvalue())
        self.assertEqual([row["bib_key"] for row in records], [relevant])
        states = dict(self.engine.conn.execute("SELECT semantic_status,COUNT(*) FROM screening GROUP BY semantic_status"))
        self.assertEqual(states, {"PASS": 1, "BELOW_THRESHOLD": 1, "MISSING_ABSTRACT": 1})
        self.assertEqual(self.engine.conn.execute("SELECT COUNT(*) FROM screening WHERE decision IS NOT NULL").fetchone()[0], 0)
        self.assertTrue((self.root / "1_workspace/semantic_ranking.csv").is_file())

    def test_threshold_boundary_and_reapplication_without_embedding(self):
        key = self.add()
        self.rank(1.0)
        self.engine.require_semantic_pass(self.engine.paper(key))
        with patch.object(module, "SemanticEncoder", side_effect=AssertionError("No reembedding")):
            self.engine.semantic_screen(0.7)
        self.assertEqual(self.engine.conn.execute("SELECT semantic_status FROM screening").fetchone()[0], "PASS")
        with patch.object(module, "SemanticEncoder", FixtureEncoder):
            result = self.engine.rank("Myoelectric prosthesis control")
        self.assertEqual(result['threshold'], 0.7)
        for invalid in (-1.01, 1.01, float("nan"), float("inf")):
            with self.assertRaises(argparse.ArgumentTypeError):
                module.cosine_threshold(invalid)

    def test_stale_metadata_and_new_records_do_not_bypass_filter(self):
        key = self.add()
        self.rank()
        with self.engine.conn:
            self.engine.conn.execute("UPDATE papers SET abstract='Changed abstract' WHERE bib_key=?", (key,))
        with self.assertRaises(module.EngineError):
            self.engine.require_semantic_pass(self.engine.paper(key))
        new = self.add(identifier="W2")
        with self.assertRaises(module.EngineError):
            self.engine.require_semantic_pass(self.engine.paper(new))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.engine.fetch_batch("screen")
        self.assertEqual(json.loads(output.getvalue()), [])

    def test_old_tfidf_scores_are_never_accepted_as_semantic(self):
        self.add()
        with self.engine.conn:
            self.engine.audit("ranking", "ranked", {"backend": "tfidf", "papers": 1})
        with self.assertRaises(module.EngineError):
            self.engine.fetch_batch("screen")
        with self.assertRaises(module.EngineError):
            module.SemanticEncoder(self.root / "1_workspace", backend="tfidf")

    def test_embedding_failure_preserves_previous_complete_ranking(self):
        self.add()
        self.rank()
        previous = tuple(self.engine.conn.execute("SELECT semantic_score,semantic_status,semantic_run_id FROM screening").fetchone())
        class Broken(FixtureEncoder):
            def encode(self, texts, mode="passage"):
                raise module.EngineError("Service unavailable")
        with patch.object(module, "SemanticEncoder", Broken), self.assertRaises(module.EngineError):
            self.engine.rank("Changed query")
        self.assertEqual(previous, tuple(self.engine.conn.execute("SELECT semantic_score,semantic_status,semantic_run_id FROM screening").fetchone()))

    def test_pdf_access_is_blocked_before_semantic_pass(self):
        key = self.add()
        with patch.object(self.engine, "download", side_effect=AssertionError("No PDF access")):
            with self.assertRaises(module.EngineError):
                self.engine.ingest(key)
        self.add("Geological minerals", "Ocean sediment", "W2")
        self.rank()
        rejected = self.engine.conn.execute("SELECT bib_key FROM screening WHERE semantic_status='BELOW_THRESHOLD'").fetchone()[0]
        with self.assertRaises(module.EngineError):
            self.engine.ingest(rejected)

    def test_thousands_of_records_skip_bad_metadata_and_keep_exact_queries(self):
        def source(query, maximum, since, stats):
            stats["total"] = 1202
            yield {"title": None, "openalex_id": "W-missing"}
            for index in range(1201):
                yield {"title": f"EMG control study {index}", "abstract": "Muscle signal decoding", "openalex_id": f"W{index}"}
        self.engine.openalex = source
        self.assertFalse(self.engine.search('EMG AND "prosthetic hand"', ["openalex"], 5000))
        self.assertEqual(self.engine.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0], 1201)
        snapshot = next((self.root / "1_workspace/search_runs").glob("*.txt")).read_text(encoding="utf-8")
        self.assertIn('EMG AND "prosthetic hand"', snapshot)
        self.assertIn('"skipped": 1', snapshot)

    def test_search_plan_dates_and_provider_translations_are_executed(self):
        path = self.root / "1_workspace/search_strings.txt"
        path.write_text('[review]\nsince=2015-01-01\nuntil=2026-12-31\nmax_results=5000\n'
                        '[oa]\ndb=openalex\nquery=EMG AND prosthesis\n'
                        '[pm]\ndb=pubmed\nquery=EMG[Title/Abstract]\n', encoding="utf-8")
        with patch.object(self.engine, "search", return_value=True) as search:
            self.assertTrue(self.engine.search_plan(dbs=["openalex"]))
        search.assert_called_once_with("EMG AND prosthesis", ["openalex"], 5000, "2015-01-01", "2026-12-31")

    def test_search_scope_is_title_and_abstract_only(self):
        calls = []
        def fetch(url, params, xml):
            calls.append(params)
            return {"meta": {"count": 0}, "results": []}
        self.engine.http = FixtureHTTP(fetch)
        self.assertEqual(list(self.engine.openalex("EMG", 5000, None, {})), [])
        self.assertIn("search.title_and_abstract", calls[0])
        self.assertNotIn("search", calls[0])
        self.assertFalse(self.engine.search("all:EMG", ["arxiv"], 5000))
        self.assertFalse(self.engine.search("EMG[All Fields]", ["pubmed"], 5000))
        self.assertFalse(self.engine.search('ti:EMG OR cancer', ["arxiv"], 5000))
        self.assertFalse(self.engine.search('EMG[Title/Abstract] OR cancer', ["pubmed"], 5000))
        self.assertEqual(len(calls), 1)

    def test_legacy_database_migration_preserves_decisions_and_four_tables(self):
        folder = self.root / "legacy"
        (folder / "1_workspace").mkdir(parents=True)
        path = folder / "1_workspace/slr_state.sqlite"
        with contextlib.closing(sqlite3.connect(path)) as connection:
            connection.executescript(module.SCHEMA)
            connection.execute("INSERT INTO papers(bib_key,title) VALUES('Existing','Historical paper')")
            connection.execute("INSERT INTO screening(bib_key,stage,decision) VALUES('Existing','FULL_TEXT','INCLUDE')")
            connection.commit()
        migrated = module.Engine(folder)
        try:
            row = migrated.conn.execute("SELECT decision,semantic_status FROM screening").fetchone()
            self.assertEqual(tuple(row), ("INCLUDE", "PENDING"))
            self.assertEqual(migrated.conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0], 4)
        finally:
            migrated.close()

    def test_ollama_uses_embedding_endpoint_no_truncation_and_model_scoped_cache(self):
        import requests
        calls = []
        class Response:
            status_code = 200
            def __init__(self, payload): self.payload = payload
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def json(self): return self.payload
        class Session:
            def request(self, method, url, json=None, timeout=None):
                calls.append((method, url, json))
                if url.endswith('/api/tags'):
                    return Response({'models': [{'name': 'fixture:latest', 'digest': 'model-v1'}]})
                self_case.assertTrue(url.endswith('/api/embed'))
                self_case.assertFalse(json['truncate'])
                self_case.assertTrue(all(len(text.encode('utf-8')) <= 1024 for text in json['input']))
                return Response({'embeddings': [[1.0, 0.0] for _ in json['input']]})
            def close(self): pass
        self_case = self
        with patch.object(requests, 'Session', Session):
            encoder = module.SemanticEncoder(self.root/'1_workspace', backend='ollama', model='fixture')
            try:
                text = 'α' * 900
                self.assertEqual(encoder.encode([text]), [[1.0, 0.0]])
                before = len(calls)
                self.assertEqual(encoder.encode([text]), [[1.0, 0.0]])
                self.assertEqual(len(calls), before)
                self.assertEqual(encoder.identity['digest'], 'model-v1')
            finally:
                encoder.close()

    def test_invalid_vectors_and_dimension_mismatch_fail_before_score_publication(self):
        self.add()
        self.rank()
        before = self.engine.latest_semantic_ranking()['run_id']
        class Invalid(FixtureEncoder):
            def encode(self, texts, mode='passage'):
                return [[1.0, 0.0]] if mode == 'query' else [[1.0]]
        with patch.object(module, 'SemanticEncoder', Invalid), self.assertRaises(module.EngineError):
            self.engine.rank('Myoelectric control')
        self.assertEqual(self.engine.latest_semantic_ranking()['run_id'], before)
        for vector in ([0, 0], [float('nan'), 1], [float('inf'), 0]):
            with self.assertRaises(module.EngineError):
                module.unit_vector(vector)

    def test_changed_plan_requires_reranking_and_no_pdf_text_is_used(self):
        self.add()
        path = self.root/'1_workspace/search_strings.txt'
        path.write_text('[review]\nsemantic_query=Myoelectric control\nsemantic_threshold=0.6\n', encoding='utf-8')
        with patch.object(module, 'SemanticEncoder', FixtureEncoder), \
                patch.object(self.engine, 'source_text', side_effect=AssertionError('No PDF text')):
            self.engine.rank()
        path.write_text('[review]\nsemantic_query=Changed review concept\n', encoding='utf-8')
        with self.assertRaises(module.EngineError):
            self.engine.fetch_batch('screen')

    def test_historical_records_outside_precise_queries_cannot_bypass_first_filter(self):
        matched = self.add(identifier='W1')
        old = self.add(title='Historical adjacent topic', identifier='W2')
        path = self.root/'1_workspace/search_strings.txt'
        path.write_text('[review]\nsemantic_query=Myoelectric control\n[oa]\ndb=openalex\nquery=EMG AND prosthesis\n', encoding='utf-8')
        def records(query, maximum, since, stats):
            stats['total'] = 1
            yield {'title': 'Muscle signal prosthetic control', 'abstract': 'Learn to decode muscle electrical signals', 'openalex_id': 'W1'}
        self.engine.openalex = records
        self.engine.search('EMG AND prosthesis', ['openalex'], 5000)
        with patch.object(module, 'SemanticEncoder', FixtureEncoder):
            self.engine.rank()
        states = dict(self.engine.conn.execute('SELECT bib_key,semantic_status FROM screening'))
        self.assertEqual(states[matched], 'PASS')
        self.assertEqual(states[old], 'OUTSIDE_SEARCH')
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.engine.fetch_batch('screen')
        self.assertEqual([r['bib_key'] for r in json.loads(output.getvalue())], [matched])

    def test_custom_search_plan_drives_ranking_and_survives_restart(self):
        default = self.root / '1_workspace/search_strings.txt'
        default.write_text('[review]\nsemantic_query=Wrong default\n[oa]\ndb=openalex\nquery=wrong\n', encoding='utf-8')
        alternate = self.root / '1_workspace/alternate.txt'
        alternate.write_text('[review]\nsemantic_query=Selected plan query\n[oa]\ndb=openalex\nquery=prosthesis\n', encoding='utf-8')
        def records(query, maximum, since, stats):
            stats['total'] = 1
            yield {'title': 'Prosthetic hand', 'abstract': 'Muscle control', 'openalex_id': 'W1'}
        self.engine.openalex = records
        self.assertTrue(self.engine.search_plan(filename='1_workspace/alternate.txt'))
        with patch.object(module, 'SemanticEncoder', FixtureEncoder):
            self.engine.rank()
        self.assertEqual(self.engine.conn.execute("SELECT query_executed FROM audit_log WHERE phase='ranking' ORDER BY id DESC LIMIT 1").fetchone()[0], 'Selected plan query')
        resumed = module.Engine(self.root)
        try:
            self.assertEqual(resumed.active_search_plan(), alternate.resolve())
            self.assertEqual(len(resumed.search_candidate_keys()), 1)
            self.assertEqual(resumed.latest_semantic_ranking()['plan_path'], '1_workspace/alternate.txt')
        finally:
            resumed.close()
        alternate.unlink()
        with self.assertRaises(module.EngineError):
            self.engine.fetch_batch('screen')

    def test_date_partitioned_queries_keep_every_partition_and_update_watermark(self):
        plan = self.root / '1_workspace/search_strings.txt'
        plan.write_text('[review]\nsemantic_query=Prosthesis\n'
                        '[first]\ndb=openalex\nquery=EMG\nsince=2015-01-01\nuntil=2015-12-31\n'
                        '[second]\ndb=openalex\nquery=EMG\nsince=2016-01-01\nuntil=2016-12-31\n', encoding='utf-8')
        def records(query, maximum, since, stats):
            stats['total'] = 1
            year = since[:4]
            yield {'title': f'EMG study {year}', 'abstract': 'Myoelectric control', 'openalex_id': 'W' + year}
        self.engine.openalex = records
        self.assertTrue(self.engine.search_plan())
        with patch.object(module, 'SemanticEncoder', FixtureEncoder):
            self.engine.rank()
        self.assertEqual(self.engine.conn.execute("SELECT COUNT(*) FROM screening WHERE semantic_status='PASS'").fetchone()[0], 2)
        (self.root / '1_workspace/protocol.md').write_text('## Research Questions\nHow?\n## PICOC\nMyoelectric control.\n', encoding='utf-8')
        with patch.object(self.engine, 'search', return_value=True) as search, \
                patch.object(self.engine, 'rank'), patch.object(self.engine, 'checkpoint'), \
                patch.object(self.engine, 'stage_skill_updates', return_value={}):
            self.assertTrue(self.engine.update())
        # The original successful searches occurred after both historical date
        # windows, so update must skip them rather than send an inverted range.
        search.assert_not_called()
        self.assertEqual(self.engine.conn.execute("SELECT COUNT(*) FROM audit_log WHERE phase='update' AND action='date_window_complete'").fetchone()[0], 2)

    def test_large_finite_embedding_vector_normalizes_without_overflow(self):
        vector = module.unit_vector([1e308, 1e308])
        self.assertAlmostEqual(sum(value * value for value in vector), 1.0)
        self.assertGreater(vector[0], 0.7)

    def test_date_partition_updates_keep_independent_watermarks(self):
        (self.root / '1_workspace/search_strings.txt').write_text(
            '[review]\nsemantic_query=Prosthesis\n'
            '[a]\ndb=openalex\nquery=EMG\nsince=2020-01-01\nuntil=2029-12-31\n'
            '[b]\ndb=openalex\nquery=EMG\nsince=2030-01-01\nuntil=2039-12-31\n', encoding='utf-8')
        (self.root / '1_workspace/protocol.md').write_text('## Research Questions\nHow?\n## PICOC\nControl.\n', encoding='utf-8')
        for since, until, started in [('2020-01-01', '2029-12-31', '2021-06-01T00:00:00+00:00'),
                                      ('2030-01-01', '2039-12-31', '2031-07-01T00:00:00+00:00')]:
            with self.engine.conn:
                self.engine.audit('search', 'completed', {'db': 'openalex', 'since': since, 'until': until,
                                  'started': started, 'max_results': 5000}, 'EMG')
        with patch.object(self.engine, 'search', return_value=True) as search, \
                patch.object(self.engine, 'rank'), patch.object(self.engine, 'checkpoint'), \
                patch.object(self.engine, 'stage_skill_updates', return_value={}):
            self.assertTrue(self.engine.update())
        self.assertEqual([call.args for call in search.call_args_list], [
            ('EMG', ['openalex'], 5000, '2021-06-01', '2029-12-31'),
            ('EMG', ['openalex'], 5000, '2031-07-01', '2039-12-31')])

    def test_overlapping_partitions_are_rejected_before_changing_active_plan(self):
        path = self.root / '1_workspace/overlap.txt'
        path.write_text('[review]\nsemantic_query=Prosthesis\n'
                        '[a]\ndb=openalex\nquery=EMG\nsince=2020-01-01\nuntil=2025-12-31\n'
                        '[b]\ndb=openalex\nquery=EMG\nsince=2025-01-01\nuntil=2030-12-31\n', encoding='utf-8')
        with self.assertRaises(module.EngineError):
            self.engine.search_plan(filename='1_workspace/overlap.txt')
        self.assertEqual(self.engine.conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='plan_selected'").fetchone()[0], 0)

    def test_extract_batch_skips_stale_rows_before_applying_limit(self):
        keys = [self.add(title=f'Study {letter}', identifier=f'W{letter}') for letter in 'ABCD']
        self.rank()
        with self.engine.conn:
            self.engine.conn.execute("UPDATE screening SET stage='TITLE_ABSTRACT', decision='INCLUDE'")
            self.engine.conn.execute("UPDATE papers SET local_md_path='dummy.md'")
            for key in sorted(keys)[:3]:
                self.engine.conn.execute("UPDATE papers SET abstract='Changed abstract' WHERE bib_key=?", (key,))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.engine.fetch_batch('extract', 3)
        self.assertEqual([item['bib_key'] for item in json.loads(output.getvalue())], [sorted(keys)[3]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
