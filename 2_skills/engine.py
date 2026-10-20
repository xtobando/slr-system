#!/usr/bin/env python3
"""Deterministic SLR engine. Python 3.10+, no LLM service calls.

Run from any working directory; all project paths derive from this file.
Search provenance and historical decisions fit inside the prescribed four tables.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import http.cookiejar
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from urllib.parse import quote as urlquote, unquote, urlparse
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DBS = ("openalex", "arxiv", "pubmed")
SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
 bib_key TEXT PRIMARY KEY, doi TEXT, arxiv_id TEXT, pmid TEXT, openalex_id TEXT,
 title TEXT, authors TEXT, year INTEGER, venue TEXT, abstract TEXT, source_db TEXT,
 oa_pdf_url TEXT, pdf_status TEXT DEFAULT 'PENDING', local_pdf_path TEXT,
 local_md_path TEXT, bibtex_raw TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_doi ON papers(doi);
CREATE INDEX IF NOT EXISTS idx_arxiv_id ON papers(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_pmid ON papers(pmid);
CREATE INDEX IF NOT EXISTS idx_openalex_id ON papers(openalex_id);
CREATE TABLE IF NOT EXISTS screening (
 bib_key TEXT PRIMARY KEY REFERENCES papers(bib_key), semantic_score REAL DEFAULT 0.0,
 stage TEXT DEFAULT 'UNSCREENED', devils_advocate_argument TEXT, verbatim_quote TEXT,
 decision TEXT, criterion_code TEXT, notes TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS extractions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, bib_key TEXT REFERENCES papers(bib_key),
 variable_name TEXT, verbatim_quote TEXT, page_number INTEGER, extracted_value TEXT,
 used_vision_asset INTEGER DEFAULT 0, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_log (
 id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
 phase TEXT, action TEXT, query_executed TEXT, git_commit_hash TEXT, notes TEXT
);
"""


class EngineError(Exception):
    """A safe, user-facing operational error (never an HTTP credential URL)."""


def compact(text):
    return " ".join(str(text or "").split())


def xmltext(node):
    return compact("".join(node.itertext())) if node is not None else ""


def ascii_word(text):
    return re.sub(r"[^a-zA-Z0-9]", "", unicodedata.normalize("NFKD", text).encode(
        "ascii", "ignore").decode())


def title_id(text):
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold()
                   if c.isalnum())[:96]


def norm_doi(value):
    value = unquote(str(value or "")).strip().lower()
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value)


def norm_arxiv(value):
    value = re.sub(r"^https?://(?:export\.)?arxiv\.org/(?:abs|pdf)/", "", str(value or ""))
    return re.sub(r"v\d+$", "", re.sub(r"\.pdf$", "", value.strip())).lower()


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def iso_date(value):
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content.encode("utf-8") if isinstance(content, str) else content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextlib.contextmanager
def workspace_lock(workspace):
    """Kernel lock released on crashes; do not unlink a lock another process may hold."""
    workspace.mkdir(parents=True, exist_ok=True)
    with (workspace / ".engine.lock").open("a+b") as handle:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise EngineError("Another engine process is using this workspace.") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


class HTTP:
    def __init__(self, cookies=None):
        try:
            import requests
        except ImportError as exc:
            raise EngineError("Install requirements.txt to use network retrieval.") from exc
        self.requests = requests
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "SLR-System/1.0"
        self.last = {}
        if cookies:
            jar = http.cookiejar.MozillaCookieJar(str(cookies))
            jar.load(ignore_discard=True, ignore_expires=False)
            self.session.cookies.update(jar)

    def get(self, url, params=None, stream=False):
        host = urlparse(url).hostname or ""
        if urlparse(url).scheme not in ("http", "https") or not host:
            raise EngineError("Only HTTP(S) retrieval URLs are supported.")
        delay = 3.1 if host.endswith("arxiv.org") else 0.36
        for attempt in range(4):
            time.sleep(max(0, delay - (time.monotonic() - self.last.get(host, 0))))
            self.last[host] = time.monotonic()
            try:
                response = self.session.get(url, params=params, stream=stream,
                                            timeout=(10, float(os.getenv("SLR_HTTP_TIMEOUT", "45"))))
            except self.requests.RequestException:
                if attempt == 3:
                    raise EngineError(f"Network request failed for {host}; check connectivity/access.") from None
                time.sleep(2 ** attempt)
                continue
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                retry = response.headers.get("Retry-After", "")
                wait = min(60, float(retry)) if retry.isdigit() else 2 ** (attempt + 1)
                response.close()
                time.sleep(wait)
                continue
            if response.status_code >= 400:
                status = response.status_code
                response.close()
                raise EngineError(f"HTTP {status} from {host}; check credentials, query, or limits.")
            return response
        raise EngineError(f"Retry budget exhausted for {host}.")

    def data(self, url, params=None, xml=False):
        with self.get(url, params) as response:
            if len(response.content) > 40 * 1024 * 1024:
                raise EngineError("Metadata response exceeds 40 MiB; narrow the query.")
            return ET.fromstring(response.content) if xml else response.json()

    def close(self):
        self.session.close()


class Engine:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.workspace = self.root / "1_workspace"
        self.papers_dir = self.root / "3_papers"
        for folder in (self.workspace, self.root / "2_skills", self.papers_dir / "raw_pdfs",
                       self.papers_dir / "parsed_cache"):
            folder.mkdir(parents=True, exist_ok=True)
        try:
            from dotenv import load_dotenv
            load_dotenv(self.root / ".env", override=False)
        except ImportError:
            if (self.root / ".env").exists():
                raise EngineError("Install python-dotenv to load the existing .env file.") from None
        self.conn = sqlite3.connect(self.workspace / "slr_state.sqlite", timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=DELETE")
        self.conn.execute("PRAGMA synchronous=FULL")
        self.conn.executescript(SCHEMA)
        self.http = None

    def close(self):
        self.conn.close()
        if self.http:
            self.http.close()

    def net(self):
        if self.http is None:
            self.http = HTTP()
        return self.http

    def audit(self, phase, action, notes, query=None):
        return self.conn.execute(
            "INSERT INTO audit_log(phase,action,query_executed,notes) VALUES(?,?,?,?)",
            (phase, action, query, json.dumps(notes, ensure_ascii=False, sort_keys=True))).lastrowid

    def paper(self, key):
        if not re.fullmatch(r"[A-Za-z0-9]+", key):
            raise EngineError("Invalid bibliography key.")
        row = self.conn.execute("SELECT * FROM papers WHERE bib_key=?", (key,)).fetchone()
        if row is None:
            raise EngineError(f"Unknown paper: {key}")
        return dict(row)

    def local(self, relative):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise EngineError("Stored path escapes the project.")
        return path

    def git(self, *args, binary=False, check=True, env=None):
        if shutil.which("git") is None:
            raise EngineError("Git is required for init/checkpoint/update; install Git and add it to PATH.")
        result = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True,
                                timeout=120, env=env)
        if check and result.returncode:
            # Do not echo stderr: remote URLs can contain credentials.
            raise EngineError(f"Git {args[0]} failed (exit {result.returncode}); inspect repository configuration.")
        return result.stdout if binary else result.stdout.decode("utf-8", "replace").strip()

    def init(self):
        if not (self.root / ".git").exists():
            self.git("init", "--quiet")
        with self.conn:
            self.audit("setup", "initialized", {"schema": 1})
        self.sync_bib()
        print(f"Initialized {self.root}; four application tables, local Git repository.")

    @staticmethod
    def bibtex(paper):
        def escape(text):
            mapping = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}",
                       "%": r"\%", "&": r"\&", "_": r"\_", "#": r"\#", "$": r"\$"}
            return "".join(mapping.get(c, c) for c in compact(text))
        authors = json.loads(paper.get("authors") or "[]")
        fields = {"title": paper.get("title"), "author": " and ".join(authors),
                  "year": paper.get("year"), "journal": paper.get("venue"), "doi": paper.get("doi")}
        if paper.get("arxiv_id"):
            fields.update(eprint=paper["arxiv_id"], archivePrefix="arXiv")
        if paper.get("pmid"):
            fields["pmid"] = paper["pmid"]
        lines = [f"@article{{{paper['bib_key']},"]
        lines += [f"  {name} = {{{escape(str(value))}}}," for name, value in fields.items() if value]
        return "\n".join(lines + ["}"])

    def sync_bib(self):
        entries = []
        with self.conn:
            for row in self.conn.execute("SELECT * FROM papers ORDER BY bib_key").fetchall():
                entry = self.bibtex(dict(row))
                self.conn.execute("UPDATE papers SET bibtex_raw=? WHERE bib_key=?", (entry, row["bib_key"]))
                entries.append(entry)
        atomic_write(self.papers_dir / "references.bib",
                     "% Managed by 2_skills/engine.py from SQLite.\n\n" + "\n\n".join(entries) + "\n")

    def upsert(self, record, db, run_id):
        record = dict(record)
        record["title"] = compact(record.get("title"))
        if not record["title"]:
            raise EngineError(f"{db} returned a record without a title.")
        record["doi"] = norm_doi(record.get("doi"))
        record["arxiv_id"] = norm_arxiv(record.get("arxiv_id"))
        record["authors"] = json.dumps([compact(name) for name in (record.get("authors") or [])
                                        if compact(name)], ensure_ascii=False)
        identifiers = ("doi", "pmid", "arxiv_id", "openalex_id")
        matches = {}
        for field in identifiers:
            if record.get(field):
                for row in self.conn.execute(f"SELECT * FROM papers WHERE {field}=?", (record[field],)):
                    matches[row["bib_key"]] = dict(row)
        if len(matches) > 1:
            raise EngineError("Conflicting identifier matches require manual metadata adjudication.")
        existing = next(iter(matches.values()), None)
        if existing is None:
            normalized = title_id(record["title"])
            for row in self.conn.execute("SELECT * FROM papers ORDER BY bib_key"):
                conflicting = any(row[f] and record.get(f) and row[f] != record[f] for f in identifiers)
                if (normalized and title_id(row["title"]) == normalized and not conflicting
                        and (not row["year"] or not record.get("year") or row["year"] == record["year"])):
                    existing = dict(row)
                    break
        is_new = existing is None
        if is_new:
            names = json.loads(record["authors"])
            first = names[0] if names else "Anonymous"
            surname = first.split(",")[0] if "," in first else first.split()[-1]
            words = re.findall(r"\w+", record["title"])
            significant = next((w for w in words if w.lower() not in
                                {"a", "an", "the", "of", "on", "in", "and", "for", "to", "with"}), "Study")
            base = (ascii_word(surname) or "Anonymous") + str(record.get("year") or "nd") + (
                ascii_word(significant).capitalize() or "Study")
            key, counter = base, 0
            while self.conn.execute("SELECT 1 FROM papers WHERE bib_key=?", (key,)).fetchone():
                counter += 1
                n, suffix = counter, ""
                while n:
                    n, rem = divmod(n - 1, 26)
                    suffix = chr(97 + rem) + suffix
                key = base + suffix
            fields = ["doi", "arxiv_id", "pmid", "openalex_id", "title", "authors", "year",
                      "venue", "abstract", "oa_pdf_url"]
            self.conn.execute(f"INSERT INTO papers(bib_key,source_db,{','.join(fields)}) "
                              f"VALUES({','.join('?' for _ in range(len(fields)+2))})",
                              [key, db] + [record.get(f) for f in fields])
            self.conn.execute("INSERT INTO screening(bib_key) VALUES(?)", (key,))
        else:
            key = existing["bib_key"]
            for field in ("doi", "arxiv_id", "pmid", "openalex_id", "abstract", "oa_pdf_url", "venue", "year"):
                if not existing[field] and record.get(field):
                    self.conn.execute(f"UPDATE papers SET {field}=? WHERE bib_key=?", (record[field], key))
            if existing["authors"] in (None, "[]") and json.loads(record["authors"]):
                self.conn.execute("UPDATE papers SET authors=? WHERE bib_key=?", (record["authors"], key))
            sources = sorted(set((existing["source_db"] or "").split(",")) | {db})
            self.conn.execute("UPDATE papers SET source_db=? WHERE bib_key=?", (",".join(filter(None, sources)), key))
        source_id = record.get({"openalex": "openalex_id", "arxiv": "arxiv_id", "pubmed": "pmid"}[db])
        source_id = source_id or record.get("doi") or title_id(record["title"])
        self.audit("search", "record", {"run_id": run_id, "db": db, "source_id": source_id,
                   "bib_key": key, "new": is_new, "pmc_id": record.get("pmc_id")})
        return is_new

    def openalex(self, query, maximum, since, stats):
        params = {"search": query, "per-page": min(maximum, 200), "cursor": "*"}
        for env, param in (("OPENALEX_EMAIL", "mailto"), ("OPENALEX_API_KEY", "api_key")):
            if os.getenv(env):
                params[param] = os.environ[env]
        if since:
            params["filter"] = "from_publication_date:" + since
        count, cursors = 0, set()
        while count < maximum:
            params["per-page"] = min(200, maximum - count)
            data = self.net().data("https://api.openalex.org/works", params)
            stats["total"] = int(data.get("meta", {}).get("count", 0))
            items = data.get("results", [])
            if not items:
                return
            for item in items:
                positions = {}
                for word, offsets in (item.get("abstract_inverted_index") or {}).items():
                    for offset in offsets:
                        positions[int(offset)] = word
                location = item.get("best_oa_location") or {}
                primary = item.get("primary_location") or {}
                ids = item.get("ids") or {}
                yield {"openalex_id": item.get("id"), "doi": item.get("doi"),
                       "pmid": str(ids.get("pmid") or "").rstrip("/").split("/")[-1],
                       "title": item.get("display_name") or item.get("title"),
                       "authors": [a["author"]["display_name"] for a in item.get("authorships", [])
                                   if (a.get("author") or {}).get("display_name")],
                       "year": item.get("publication_year"),
                       "venue": (primary.get("source") or {}).get("display_name"),
                       "abstract": " ".join(positions[i] for i in sorted(positions)),
                       "oa_pdf_url": location.get("pdf_url")}
                count += 1
            cursor = data.get("meta", {}).get("next_cursor")
            if not cursor:
                return
            if cursor in cursors:
                raise EngineError("OpenAlex repeated a pagination cursor.")
            cursors.add(cursor)
            params["cursor"] = cursor

    def arxiv(self, query, maximum, since, stats):
        ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom",
              "o": "http://a9.com/-/spec/opensearch/1.1/"}
        effective = query
        if since:
            effective = f"({query}) AND submittedDate:[{since.replace('-', '')}0000 TO 300001010000]"
        start = 0
        while start < maximum:
            data = self.net().data("https://export.arxiv.org/api/query", {
                "search_query": effective, "start": start, "max_results": min(100, maximum-start),
                "sortBy": "submittedDate", "sortOrder": "ascending"}, xml=True)
            stats["total"] = int(data.findtext("o:totalResults", "0", ns))
            items = data.findall("a:entry", ns)
            if not items:
                return
            for item in items:
                identifier = norm_arxiv(item.findtext("a:id", "", ns))
                if "api/errors" in identifier:
                    raise EngineError("arXiv rejected the query; check its field syntax.")
                published = item.findtext("a:published", "", ns)
                yield {"arxiv_id": identifier, "title": item.findtext("a:title", "", ns),
                       "authors": [xmltext(a.find("a:name", ns)) for a in item.findall("a:author", ns)],
                       "abstract": compact(item.findtext("a:summary", "", ns)),
                       "year": int(published[:4]) if published[:4].isdigit() else None,
                       "doi": item.findtext("x:doi", "", ns), "venue": "arXiv",
                       "oa_pdf_url": f"https://arxiv.org/pdf/{identifier}.pdf"}
            start += len(items)
            if start >= stats["total"]:
                return

    def pubmed(self, query, maximum, since, stats):
        base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        common = {"db": "pubmed", "retmode": "xml", "tool": "slr_system"}
        for env, param in (("NCBI_API_KEY", "api_key"), ("NCBI_EMAIL", "email")):
            if os.getenv(env):
                common[param] = os.environ[env]
        start = 0
        while start < min(maximum, 9999):
            params = dict(common, term=query, retstart=start, retmax=min(200, maximum-start, 9999-start))
            if since:
                params.update(mindate=since.replace("-", "/"), maxdate="3000/01/01", datetype="pdat")
            result = self.net().data(base + "esearch.fcgi", params, xml=True)
            if result.find(".//ERROR") is not None or result.find("ErrorList") is not None:
                raise EngineError("PubMed rejected the query; check field tags and spelling.")
            stats["total"] = int(result.findtext("Count", "0"))
            ids = [n.text for n in result.findall("IdList/Id")]
            if not ids:
                return
            records = self.net().data(base + "efetch.fcgi", dict(common, id=",".join(ids)), xml=True)
            if records.find(".//ERROR") is not None:
                raise EngineError("PubMed efetch failed for an ID batch.")
            articles = records.findall("PubmedArticle")
            if len(articles) != len(ids):
                raise EngineError("PubMed returned unsupported or missing records; narrow the query.")
            for item in articles:
                article = item.find("MedlineCitation/Article")
                identifiers = {n.get("IdType"): n.text for n in item.findall("PubmedData/ArticleIdList/ArticleId")}
                pmc = identifiers.get("pmc")
                authors = []
                for author in article.findall("AuthorList/Author"):
                    collective = xmltext(author.find("CollectiveName"))
                    surname = xmltext(author.find("LastName"))
                    given = xmltext(author.find("ForeName")) or xmltext(author.find("Initials"))
                    authors.append(collective or compact(f"{surname}, {given}").rstrip(","))
                year_text = (article.findtext("Journal/JournalIssue/PubDate/Year") or
                             article.findtext("ArticleDate/Year") or
                             article.findtext("Journal/JournalIssue/PubDate/MedlineDate") or "")
                year_match = re.search(r"\b(\d{4})\b", year_text)
                abstract = "\n".join((n.get("Label", "") + ": " if n.get("Label") else "") + xmltext(n)
                                     for n in article.findall("Abstract/AbstractText"))
                yield {"pmid": item.findtext("MedlineCitation/PMID"), "doi": identifiers.get("doi"),
                       "pmc_id": pmc, "title": xmltext(article.find("ArticleTitle")),
                       "authors": list(filter(None, authors)), "abstract": abstract,
                       "year": int(year_match[1]) if year_match else None,
                       "venue": xmltext(article.find("Journal/Title")),
                       "oa_pdf_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmc}/pdf/" if pmc else None}
            start += len(ids)
            if start >= stats["total"]:
                return

    def search(self, query, dbs, maximum, since=None):
        if not compact(query):
            raise EngineError("Search query cannot be empty.")
        unknown = set(dbs) - set(DBS)
        if unknown:
            raise EngineError("Unknown database: " + ", ".join(sorted(unknown)))
        reports = []
        for db in dict.fromkeys(dbs):
            run_id = uuid.uuid4().hex
            stats = {"run_id": run_id, "db": db, "max_results": maximum, "since": since,
                     "started": datetime.now(timezone.utc).isoformat(), "retrieved": 0, "new": 0}
            with self.conn:
                self.audit("search", "started", stats, query)
            try:
                for record in getattr(self, db)(query, maximum, since, stats):
                    with self.conn:
                        is_new = self.upsert(record, db, run_id)
                    stats["retrieved"] += 1
                    stats["new"] += int(is_new)
                stats["complete"] = stats["retrieved"] >= stats.get("total", stats["retrieved"])
                action = "completed" if stats["complete"] else "capped"
            except (EngineError, ValueError, ET.ParseError, KeyError, TypeError) as exc:
                stats["error"] = str(exc) if isinstance(exc, EngineError) else type(exc).__name__
                stats["complete"] = False
                action = "failed"
            with self.conn:
                self.audit("search", action, stats, query)
            reports.append(dict(stats, outcome=action))
        self.sync_bib()
        print(json.dumps(reports, indent=2, ensure_ascii=False))
        return all(r["complete"] for r in reports)

    def protocol_query(self):
        path = self.workspace / "protocol.md"
        if not path.exists():
            raise EngineError("Create protocol.md with Research Questions and PICOC, or use --picoc-text.")
        text = path.read_text(encoding="utf-8")
        sections = []
        for name in ("Research Questions", "PICOC"):
            match = re.search(r"^## " + re.escape(name) + r"\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
            if match:
                sections.append(match[1].strip())
        result = "\n".join(sections)
        if not result or "Not yet specified" in result or "No research questions have been specified" in result:
            raise EngineError("Complete the RQs and PICOC in protocol.md, or supply --picoc-text.")
        return result

    @staticmethod
    def lexical_scores(query, documents):
        def terms(text):
            return Counter(re.findall(r"\b\w+\b", text.casefold()))
        counts = [terms(d) for d in documents]
        frequency = Counter(term for row in counts for term in row)
        idf = {term: math.log((1 + len(counts)) / (1 + freq)) + 1 for term, freq in frequency.items()}
        def vector(count):
            weights = {term: (1 + math.log(n)) * idf[term] for term, n in count.items() if term in idf}
            norm = math.sqrt(sum(w*w for w in weights.values())) or 1
            return {term: weight/norm for term, weight in weights.items()}
        q = vector(terms(query))
        return [max(0.0, min(1.0, sum(q.get(term, 0)*weight for term, weight in vector(row).items())))
                for row in counts]

    def rank(self, picoc_text=None):
        query = picoc_text if picoc_text is not None else self.protocol_query()
        if not compact(query):
            raise EngineError("Ranking query cannot be empty.")
        rows = self.conn.execute("SELECT bib_key,title,abstract FROM papers ORDER BY bib_key").fetchall()
        documents = [compact(r["title"]) + " " + compact(r["abstract"]) for r in rows]
        scores = self.lexical_scores(query, documents)
        backend, model_name = "tfidf", None
        requested = os.getenv("SLR_RANK_BACKEND", "auto").lower()
        if requested not in ("auto", "tfidf", "fastembed"):
            raise EngineError("SLR_RANK_BACKEND must be auto, tfidf, or fastembed.")
        if documents and requested != "tfidf":
            try:
                from fastembed import TextEmbedding
                import numpy as np
            except ImportError:
                if requested == "fastembed":
                    raise EngineError("FastEmbed was requested but is not installed.") from None
                print("FastEmbed absent: using deterministic TF-IDF cosine.", file=sys.stderr)
            else:
                model_name = os.getenv("SLR_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
                try:
                    model = TextEmbedding(model_name=model_name, cache_dir=str(self.workspace / ".models"))
                    q = np.asarray(next(iter(model.query_embed(query))), dtype=float)
                    q /= max(float(np.linalg.norm(q)), 1e-12)
                    # Stream document vectors; do not retain a corpus-wide dense matrix.
                    for i, v in enumerate(model.passage_embed(documents, batch_size=32)):
                        v = np.asarray(v, dtype=float)
                        cosine = max(0.0, min(1.0, float(np.dot(q, v) / max(np.linalg.norm(v), 1e-12))))
                        scores[i] = 0.8 * cosine + 0.2 * scores[i]
                    backend = "fastembed+tfidf"
                except Exception as exc:
                    raise EngineError(f"Neural ranking failed ({type(exc).__name__}); set SLR_RANK_BACKEND=tfidf for offline ranking.") from None
        with self.conn:
            self.conn.executemany("UPDATE screening SET semantic_score=?,updated_at=CURRENT_TIMESTAMP WHERE bib_key=?",
                                  [(float(score), row["bib_key"]) for row, score in zip(rows, scores)])
            self.audit("ranking", "ranked", {"backend": backend, "model": model_name,
                       "papers": len(rows), "query_sha256": hashlib.sha256(query.encode()).hexdigest()}, query)
        print(json.dumps({"ranked": len(rows), "backend": backend, "model": model_name}))

    def fetch_batch(self, phase, limit=None):
        cap = 15 if phase == "screen" else 3
        limit = cap if limit is None else limit
        if limit > cap:
            raise EngineError(f"{phase} batches may contain at most {cap} papers per turn.")
        if phase == "screen":
            rows = self.conn.execute("""SELECT p.bib_key,p.title,p.abstract,p.year,p.doi,p.arxiv_id,p.pmid,
                s.semantic_score FROM papers p JOIN screening s USING(bib_key)
                WHERE s.stage='UNSCREENED' ORDER BY s.semantic_score DESC,p.bib_key LIMIT ?""", (limit,)).fetchall()
            items = [dict(row) for row in rows]
        else:
            rows = self.conn.execute("""SELECT p.bib_key,p.title,p.local_md_path,p.local_pdf_path,p.pdf_status,
                s.stage,s.semantic_score FROM papers p JOIN screening s USING(bib_key)
                WHERE s.decision='INCLUDE' AND p.local_md_path IS NOT NULL
                ORDER BY (SELECT COUNT(*) FROM extractions e WHERE e.bib_key=p.bib_key),
                s.semantic_score DESC,p.bib_key LIMIT ?""", (limit,)).fetchall()
            items = []
            for row in rows:
                item = dict(row)
                folder = self.papers_dir / "parsed_cache" / row["bib_key"]
                item["visual_assets"] = [p.relative_to(self.root).as_posix() for p in sorted(folder.glob("page_*_visual.png"))]
                item["extracted_variables"] = [r[0] for r in self.conn.execute(
                    "SELECT DISTINCT variable_name FROM extractions WHERE bib_key=?", (row["bib_key"],))]
                items.append(item)
        # A conservative UTF-8 byte cap bounds new tool text, not the wrapper's history or image tokens.
        while len(json.dumps(items, ensure_ascii=False).encode()) > 120_000:
            if len(items) == 1:
                raise EngineError("A single record exceeds the batch output budget; inspect its stored source separately.")
            items.pop()
        print(json.dumps(items, indent=2, ensure_ascii=False))

    def source_text(self, paper, page=None):
        if not paper.get("local_md_path"):
            raise EngineError("Ingest this PDF before full-text review.")
        markdown = self.local(paper["local_md_path"]).read_text(encoding="utf-8")
        digest = re.search(r"<!-- PDF_SHA256: ([0-9a-f]{64}) -->", markdown)
        pdf = self.local(paper["local_pdf_path"]) if paper.get("local_pdf_path") else None
        if not pdf or not pdf.is_file():
            raise EngineError("The source PDF is missing; restore it before recording full-text evidence.")
        if digest and hashlib.sha256(pdf.read_bytes()).hexdigest() != digest[1]:
            raise EngineError("PDF changed since parsing; run ingest and repeat full-text review.")
        pages = re.findall(r"<!-- PAGE (\d+) -->\s*\n(.*?)(?=<!-- PAGE \d+ -->|\Z)", markdown, re.S)
        found = {int(n): text for n, text in pages}
        if page is not None and page not in found:
            raise EngineError("Page number is outside the parsed PDF.")
        text = found[page] if page is not None else "\n".join(found.values())
        text = re.sub(r"\[VISUAL_ASSET:[^\]]+\]", "", text)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        return text

    def validate_quote(self, paper, quotation, stage, page=None, vision=False):
        if not compact(quotation):
            raise EngineError("A nonempty verbatim quote is required.")
        source = ((paper.get("title") or "") + "\n" + (paper.get("abstract") or "")
                  if stage == "TITLE_ABSTRACT" else self.source_text(paper, page))
        if vision:
            if page is None or not (self.papers_dir / "parsed_cache" / paper["bib_key"] /
                                    f"page_{page}_visual.png").is_file():
                raise EngineError("Visual evidence requires a valid PDF page and its rendered PNG.")
        elif compact(quotation) not in compact(source):
            raise EngineError("Quote does not match the source after whitespace normalization.")

    def record_decision(self, args):
        paper = self.paper(args.bib_key)
        if not compact(args.devils_advocate):
            raise EngineError("A substantive devil's-advocate argument is required.")
        if not re.fullmatch(r"(?:IC|EC)\d+", args.code):
            raise EngineError("Criterion code must have the form IC1 or EC1.")
        if ((args.decision == "INCLUDE" and not args.code.startswith("IC")) or
                (args.decision == "EXCLUDE" and not args.code.startswith("EC"))):
            raise EngineError("INCLUDE requires an IC code; EXCLUDE requires an EC code.")
        protocol = self.workspace / "protocol.md"
        if not protocol.exists() or not re.search(r"\b" + args.code + r"\b", protocol.read_text(encoding="utf-8")):
            raise EngineError("Define this criterion code in protocol.md before using it.")
        previous = dict(self.conn.execute("SELECT * FROM screening WHERE bib_key=?", (args.bib_key,)).fetchone())
        history = self.decision_history().get(args.bib_key, {})
        if args.stage == "FULL_TEXT" and history.get("TITLE_ABSTRACT", {}).get("decision") != "INCLUDE":
            raise EngineError("Full-text review requires a current title/abstract INCLUDE decision.")
        visual = re.search(r"\bvision:page=(\d+)\b", args.notes or "") if args.stage == "FULL_TEXT" else None
        self.validate_quote(paper, args.quote, args.stage, int(visual[1]) if visual else None, bool(visual))
        event = {"bib_key": args.bib_key, "stage": args.stage, "decision": args.decision,
                 "criterion_code": args.code, "quote": args.quote, "devils_advocate": args.devils_advocate,
                 "notes": args.notes, "previous": previous,
                 "protocol_sha256": hashlib.sha256(protocol.read_bytes()).hexdigest()}
        with self.conn:
            self.conn.execute("""UPDATE screening SET stage=?,devils_advocate_argument=?,verbatim_quote=?,
                decision=?,criterion_code=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE bib_key=?""",
                (args.stage, args.devils_advocate, args.quote, args.decision, args.code, args.notes, args.bib_key))
            self.audit("screening", "decision", event)
        self.matrix()
        print(json.dumps({"bib_key": args.bib_key, "stage": args.stage, "decision": args.decision}))

    def decision_history(self):
        history = defaultdict(dict)
        for row in self.conn.execute("SELECT action,notes FROM audit_log WHERE phase='screening' AND action IN ('decision','source_changed') ORDER BY id"):
            event = json.loads(row["notes"])
            if row["action"] == "source_changed":
                history[event["bib_key"]].pop("FULL_TEXT", None)
                continue
            if event["stage"] == "TITLE_ABSTRACT":
                history[event["bib_key"]].pop("FULL_TEXT", None)
            history[event["bib_key"]][event["stage"]] = event
        return history

    @staticmethod
    def source_link(paper):
        if paper.get("doi"):
            return "DOI", "https://doi.org/" + urlquote(paper["doi"], safe="/")
        if paper.get("arxiv_id"):
            return "arXiv", "https://arxiv.org/abs/" + urlquote(paper["arxiv_id"], safe="/")
        if paper.get("pmid"):
            return "PubMed", "https://pubmed.ncbi.nlm.nih.gov/" + urlquote(paper["pmid"], safe="") + "/"
        return None, None

    def pmc_pdf(self, pmc_id):
        """Resolve current PMC Cloud metadata instead of scraping its reader/login page."""
        base = "https://pmc-oa-opendata.s3.amazonaws.com/"
        listing = self.net().data(base, {"list-type": "2", "prefix": pmc_id + ".", "delimiter": "/"}, xml=True)
        ns = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
        candidates = []
        for node in listing.findall("s:CommonPrefixes/s:Prefix", ns):
            prefix = node.text.rstrip("/")
            meta = self.net().data(base + prefix + "/" + prefix + ".json")
            if meta.get("pdf_url"):
                candidates.append(meta)
        # Prefer the published version; retain chosen version/license in the audit.
        candidates.sort(key=lambda m: (str(m.get("is_manuscript")).lower() in ("yes", "true"),
                                       str(m.get("version", ""))))
        if candidates:
            selected = candidates[0]
            with self.conn:
                self.audit("ingest", "pmc_version", {k: selected.get(k) for k in
                           ("pmcid", "version", "is_manuscript", "license_code", "pdf_url")})
            return selected["pdf_url"]
        return None

    def download(self, url, target, client):
        temporary = target.with_suffix(".pdf.part")
        size = 0
        maximum = int(os.getenv("SLR_MAX_PDF_MB", "100")) * 1024 * 1024
        try:
            with client.get(url, stream=True) as response, temporary.open("wb") as handle:
                for chunk in response.iter_content(64 * 1024):
                    size += len(chunk)
                    if size > maximum:
                        raise EngineError("PDF download exceeds SLR_MAX_PDF_MB.")
                    handle.write(chunk)
            with temporary.open("rb") as handle:
                if b"%PDF-" not in handle.read(1024):
                    raise EngineError("Retrieved content is not a PDF (possibly a login page).")
            import pymupdf as fitz
            with fitz.open(temporary) as document:
                if not document.is_pdf or document.needs_pass or not len(document):
                    raise EngineError("PDF is encrypted or empty.")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def parse_pdf(self, paper, pdf):
        import pymupdf as fitz
        folder = self.papers_dir / "parsed_cache" / paper["bib_key"]
        folder.mkdir(parents=True, exist_ok=True)
        pieces = []
        with fitz.open(pdf) as document:
            if not document.is_pdf or document.needs_pass or not len(document):
                raise EngineError("PDF is empty, encrypted, or invalid.")
            for number, page in enumerate(document, 1):
                text = page.get_text("text", sort=True)
                reasons = []
                if page.get_images():
                    reasons.append("image")
                if page.get_drawings():
                    reasons.append("vector drawing")
                if re.search(r"\b(?:Fig\.|Figure|Table|Algorithm)\s*\d*", text, re.I):
                    reasons.append("caption/table/algorithm")
                if sum(text.count(c) for c in "∑∫∂∈≥≤±√∏∞⊗αβλσ") >= 2:
                    reasons.append("math")
                if not text.strip():
                    reasons.append("scanned or empty page; inspect image")
                # Full-page rendering is intentionally a superset of heuristic detections.
                asset = folder / f"page_{number}_visual.png"
                if page.rect.width * page.rect.height * (200/72)**2 > 80_000_000:
                    raise EngineError("Oversized PDF page exceeds the safe 200-DPI render budget.")
                pixmap = page.get_pixmap(dpi=200, alpha=False, colorspace=fitz.csRGB)
                atomic_write(asset, pixmap.tobytes("png"))
                relative = asset.relative_to(self.root).as_posix()
                pieces.append(f"<!-- PAGE {number} -->\n{text.rstrip()}\n\n"
                              f"<!-- Visual triggers: {', '.join(reasons) or 'conservative preservation'} -->\n"
                              f"[VISUAL_ASSET: {relative}]\n")
            page_count = len(document)
        markdown = folder / "fulltext.md"
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        atomic_write(markdown, f"<!-- PDF_SHA256: {digest} -->\n" + "\n".join(pieces))
        return markdown, page_count

    def reopen_changed_source(self, paper, pdf):
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        prior = self.conn.execute("SELECT notes FROM audit_log WHERE phase='ingest' AND action='parsed' ORDER BY id DESC")
        old_digest = next((event["pdf_sha256"] for event in (json.loads(r[0]) for r in prior)
                           if event["bib_key"] == paper["bib_key"]), None)
        if old_digest and old_digest != digest:
            ta = self.decision_history().get(paper["bib_key"], {}).get("TITLE_ABSTRACT")
            with self.conn:
                if ta:
                    self.conn.execute("""UPDATE screening SET stage='TITLE_ABSTRACT',decision=?,
                        criterion_code=?,verbatim_quote=?,devils_advocate_argument=?,notes=?,
                        updated_at=CURRENT_TIMESTAMP WHERE bib_key=?""",
                        (ta["decision"], ta["criterion_code"], ta["quote"], ta["devils_advocate"],
                         "PDF changed; repeat full-text review and adjudicate previous extractions.", paper["bib_key"]))
                self.audit("screening", "source_changed", {"bib_key": paper["bib_key"],
                           "old_sha256": old_digest, "new_sha256": digest})
        return digest

    def ingest(self, key=None):
        try:
            import pymupdf as fitz
        except ImportError as exc:
            raise EngineError("Install PyMuPDF before ingesting PDFs.") from exc
        rows = [self.paper(key)] if key else [dict(r) for r in self.conn.execute(
            "SELECT p.* FROM papers p JOIN screening s USING(bib_key) WHERE s.decision='INCLUDE' ORDER BY p.bib_key")]
        cookie_path = os.getenv("CUSTOM_COOKIES_PATH")
        cookie_file = ((self.root / cookie_path).resolve() if cookie_path else None)
        client = None
        results = []
        try:
            for paper in rows:
                pdf = self.papers_dir / "raw_pdfs" / (paper["bib_key"] + ".pdf")
                errors = []
                if not pdf.exists():
                    candidates = []
                    oa = paper.get("oa_pdf_url")
                    pmc_match = re.search(r"/(PMC\d+)/", oa or "")
                    if pmc_match:
                        try:
                            resolved = self.pmc_pdf(pmc_match[1])
                            if resolved:
                                candidates.append(resolved)
                        except (EngineError, ValueError, ET.ParseError) as exc:
                            errors.append(type(exc).__name__ + " resolving PMC")
                    elif oa:
                        candidates.append(oa)
                    if paper.get("doi") and os.getenv("UNPAYWALL_EMAIL"):
                        try:
                            data = self.net().data("https://api.unpaywall.org/v2/" + urlquote(paper["doi"], safe=""),
                                                   {"email": os.environ["UNPAYWALL_EMAIL"]})
                            for location in [data.get("best_oa_location")] + (data.get("oa_locations") or []):
                                if location and location.get("url_for_pdf"):
                                    candidates.append(location["url_for_pdf"])
                        except (EngineError, ValueError) as exc:
                            errors.append(type(exc).__name__ + " resolving Unpaywall")
                    proxy = os.getenv("INSTITUTIONAL_PROXY_URL")
                    if proxy:
                        targets = list(candidates) or [self.source_link(paper)[1]]
                        for target in filter(None, targets):
                            candidates.append(proxy.replace("{url_encoded}", urlquote(target, safe="")).replace(
                                "{url}", target) if "{url" in proxy else proxy + target)
                    for candidate in dict.fromkeys(candidates):
                        try:
                            if client is None:
                                client = HTTP(cookie_file)
                            self.download(candidate, pdf, client)
                            break
                        except Exception as exc:
                            errors.append(str(exc) if isinstance(exc, EngineError) else type(exc).__name__)
                if not pdf.exists():
                    with self.conn:
                        self.conn.execute("UPDATE papers SET pdf_status='NEEDS_MANUAL_PDF' WHERE bib_key=?", (paper["bib_key"],))
                        self.audit("ingest", "manual_required", {"bib_key": paper["bib_key"], "errors": errors})
                    label, link = self.source_link(paper)
                    print(f"{paper['bib_key']}: NEEDS_MANUAL_PDF; " + (f"[{label}]({link}); " if link else "") +
                          f"place PDF at {pdf.relative_to(self.root).as_posix()}")
                    results.append(False)
                    continue
                try:
                    digest = self.reopen_changed_source(paper, pdf)
                    markdown, pages = self.parse_pdf(paper, pdf)
                    with self.conn:
                        self.conn.execute("UPDATE papers SET pdf_status='PARSED',local_pdf_path=?,local_md_path=? WHERE bib_key=?",
                                          (pdf.relative_to(self.root).as_posix(), markdown.relative_to(self.root).as_posix(), paper["bib_key"]))
                        self.audit("ingest", "parsed", {"bib_key": paper["bib_key"], "pages": pages,
                                   "pdf_sha256": digest})
                    print(f"{paper['bib_key']}: PARSED, {pages} pages and visual assets")
                    results.append(True)
                except Exception as exc:
                    with self.conn:
                        self.conn.execute("UPDATE papers SET pdf_status='PARSE_ERROR',local_pdf_path=?,local_md_path=NULL WHERE bib_key=?",
                                          (pdf.relative_to(self.root).as_posix(), paper["bib_key"]))
                        self.audit("ingest", "parse_failed", {"bib_key": paper["bib_key"], "error": type(exc).__name__})
                    print(f"{paper['bib_key']}: PARSE_ERROR ({type(exc).__name__}); inspect the original PDF.", file=sys.stderr)
                    results.append(False)
        finally:
            if client:
                client.close()
        self.matrix()
        return all(results)

    def record_extraction(self, args):
        paper = self.paper(args.bib_key)
        state = self.conn.execute("SELECT stage,decision FROM screening WHERE bib_key=?", (args.bib_key,)).fetchone()
        if tuple(state) != ("FULL_TEXT", "INCLUDE"):
            raise EngineError("Extraction requires FULL_TEXT INCLUDE.")
        if not compact(args.variable) or not compact(args.value):
            raise EngineError("Variable name and extracted value must be nonempty.")
        self.validate_quote(paper, args.quote, "FULL_TEXT", args.page, bool(args.used_vision))
        values = (args.bib_key, args.variable, args.quote, args.page, args.value, args.used_vision)
        with self.conn:
            row = self.conn.execute("""SELECT id FROM extractions WHERE bib_key=? AND variable_name=?
                AND verbatim_quote=? AND page_number=? AND extracted_value=? AND used_vision_asset=?""", values).fetchone()
            if row:
                record_id = row[0]
            else:
                record_id = self.conn.execute("""INSERT INTO extractions(bib_key,variable_name,verbatim_quote,
                    page_number,extracted_value,used_vision_asset) VALUES(?,?,?,?,?,?)""", values).lastrowid
                self.audit("extraction", "recorded", {"id": record_id, "bib_key": args.bib_key, "variable": args.variable})
        self.matrix()
        print(json.dumps({"id": record_id, "bib_key": args.bib_key}))

    def matrix(self):
        def cell(value):
            return compact(value).replace("&", "&amp;").replace("<", "&lt;").replace(
                ">", "&gt;").replace("|", "&#124;").replace("[", "&#91;").replace(
                "]", "&#93;").replace("*", "&#42;").replace("`", "&#96;")
        lines = ["# Extraction matrix", "", "Generated evidence; interpretation belongs in synthesis_report.md.", "",
                 "| Paper | Variable | Value | Verbatim evidence | PDF page | Vision used | Current eligibility |",
                 "|---|---|---|---|---:|---|---|"]
        for row in self.conn.execute("""SELECT e.*,p.doi,p.arxiv_id,p.pmid,s.stage,s.decision FROM extractions e
            JOIN papers p USING(bib_key) JOIN screening s USING(bib_key) ORDER BY e.bib_key,e.variable_name,e.id"""):
            paper = dict(row)
            key = paper["bib_key"]
            label, link = self.source_link(paper)
            citation = f"[@{key}](../3_papers/raw_pdfs/{key}.pdf)" + (f" ([{label}]({link}))" if link else "")
            fields = [citation, cell(row["variable_name"]), cell(row["extracted_value"]), cell(row["verbatim_quote"]),
                      str(row["page_number"]), "yes" if row["used_vision_asset"] else "no", f"{row['stage']} / {row['decision']}"]
            lines.append("| " + " | ".join(fields) + " |")
        atomic_write(self.workspace / "extraction_matrix.md", "\n".join(lines) + "\n")

    def flow_counts(self):
        source_records = {}
        for row in self.conn.execute("SELECT notes FROM audit_log WHERE phase='search' AND action='record' ORDER BY id"):
            record = json.loads(row[0])
            source_records[(record["db"], record["source_id"])] = record["bib_key"]
        by_db = Counter(db for db, identity in source_records)
        papers = {r["bib_key"]: dict(r) for r in self.conn.execute("SELECT * FROM papers")}
        history = self.decision_history()
        ta = {key: stages["TITLE_ABSTRACT"] for key, stages in history.items() if "TITLE_ABSTRACT" in stages}
        sought = {key for key, event in ta.items() if event["decision"] == "INCLUDE"}
        ft = {key: history[key]["FULL_TEXT"] for key in sought if "FULL_TEXT" in history[key]}
        retrieved = {key for key in sought if key in ft or papers[key].get("local_pdf_path")}
        manual = {key for key in sought - retrieved if papers[key]["pdf_status"] == "NEEDS_MANUAL_PDF"}
        excluded_ta = Counter(e["criterion_code"] for e in ta.values() if e["decision"] == "EXCLUDE")
        excluded_ft = Counter(e["criterion_code"] for e in ft.values() if e["decision"] == "EXCLUDE")
        canonical = set(source_records.values())
        return {"identified_by_db": {db: by_db[db] for db in DBS}, "identified": len(source_records),
                "duplicates_removed": len(source_records) - len(canonical), "unique_records": len(papers),
                "without_search_provenance": len(set(papers) - canonical), "screened": len(ta),
                "unscreened": len(papers)-len(ta), "ta_excluded": sum(excluded_ta.values()),
                "ta_exclusions": dict(sorted(excluded_ta.items())),
                "ta_maybe": sum(e["decision"] == "MAYBE" for e in ta.values()),
                "fulltext_sought": len(sought), "manual_pdf": len(manual),
                "retrieval_pending": len(sought-retrieved-manual), "retrieved": len(retrieved),
                "fulltext_assessed": len(ft), "assessment_pending": len(retrieved)-len(ft),
                "ft_excluded": sum(excluded_ft.values()), "ft_exclusions": dict(sorted(excluded_ft.items())),
                "ft_maybe": sum(e["decision"] == "MAYBE" for e in ft.values()),
                "final_included": sum(e["decision"] == "INCLUDE" for e in ft.values())}

    def prisma(self):
        c = self.flow_counts()
        lines = ["| PRISMA flow item | Count |", "|---|---:|"]
        for db, count in c["identified_by_db"].items():
            lines.append(f"| Identified: {db} | {count} |")
        names = [("identified", "Identified source records"), ("duplicates_removed", "Duplicates removed"),
                 ("unique_records", "Unique records"), ("without_search_provenance", "Records lacking search provenance"),
                 ("unscreened", "Awaiting title/abstract screening"), ("screened", "Title/abstract screened"),
                 ("ta_excluded", "Excluded at title/abstract"), ("ta_maybe", "Title/abstract MAYBE"),
                 ("fulltext_sought", "Full-text reports sought"), ("manual_pdf", "NEEDS_MANUAL_PDF (not retrieved)"),
                 ("retrieval_pending", "Retrieval pending"), ("retrieved", "Reports retrieved"),
                 ("assessment_pending", "Full-text assessment pending"), ("fulltext_assessed", "Full-text reports assessed"),
                 ("ft_excluded", "Excluded at full text"), ("ft_maybe", "Full-text MAYBE"),
                 ("final_included", "Final included reports")]
        lines += [f"| {name} | {c[key]} |" for key, name in names]
        for stage, key in (("Title/abstract", "ta_exclusions"), ("Full text", "ft_exclusions")):
            lines += [f"| {stage} exclusion: {code} | {count} |" for code, count in c[key].items()]
        lines += ["", "```mermaid", "flowchart TD",
                  f'  I["Identified source records: {c["identified"]}"] --> D["Duplicates removed: {c["duplicates_removed"]}"]',
                  f'  I --> U["Unique records: {c["unique_records"]}"]',
                  f'  U --> W["Awaiting screening: {c["unscreened"]}"]',
                  f'  U --> S["Screened: {c["screened"]}"]',
                  f'  S --> E["Title/abstract excluded: {c["ta_excluded"]}"]',
                  f'  S --> M["Title/abstract MAYBE: {c["ta_maybe"]}"]',
                  f'  S --> F["Reports sought: {c["fulltext_sought"]}"]',
                  f'  F --> N["Needs manual PDF: {c["manual_pdf"]}"]',
                  f'  F --> P["Retrieval pending: {c["retrieval_pending"]}"]',
                  f'  F --> R["Reports retrieved: {c["retrieved"]}"]',
                  f'  R --> Q["Assessment pending: {c["assessment_pending"]}"]',
                  f'  R --> A["Full-text assessed: {c["fulltext_assessed"]}"]',
                  f'  A --> X["Full-text excluded: {c["ft_excluded"]}"]',
                  f'  A --> Y["Full-text MAYBE: {c["ft_maybe"]}"]',
                  f'  A --> Z["Included reports: {c["final_included"]}"]', "```", "",
                  "Counts describe retrieved records and reports, not provider hit estimates or distinct studies.",
                  "Repeated source identities are counted once across searches. Unresolved work remains visible."]
        unfinished = self.conn.execute("SELECT COUNT(*) FROM audit_log WHERE phase='search' AND action IN ('capped','failed')").fetchone()[0]
        if unfinished:
            lines.append(f"Search history includes {unfinished} capped/failed attempts; review their resolution in audit_log.")
        block = "\n".join(lines)
        path = self.workspace / "synthesis_report.md"
        text = path.read_text(encoding="utf-8") if path.exists() else "# Systematic literature review synthesis\n"
        replacement = "<!-- PRISMA:START -->\n" + block + "\n<!-- PRISMA:END -->"
        if "<!-- PRISMA:START -->" in text and "<!-- PRISMA:END -->" in text:
            text = re.sub(r"<!-- PRISMA:START -->.*?<!-- PRISMA:END -->", lambda m: replacement, text, flags=re.S)
        else:
            text += "\n" + replacement + "\n"
        atomic_write(path, text)
        with self.conn:
            self.audit("synthesis", "prisma", c)
        print(block)
        return c

    def checkpoint(self, message):
        if not compact(message):
            raise EngineError("Checkpoint message cannot be empty.")
        if not (self.root / ".git").exists():
            self.git("init", "--quiet")
        self.sync_bib()
        with self.conn:
            audit_id = self.audit("backup", "checkpoint", {"message": message, "state": "pending"})
        # Close SQLite before Git reads its binary file (important on Windows).
        self.conn.close()
        commit_hash = None
        try:
            paths = ("1_workspace/", "3_papers/references.bib")
            self.git("add", "--", *paths)
            self.git("-c", "user.name=SLR Shadow Backup", "-c", "user.email=slr@localhost",
                     "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + os.devnull,
                     "commit", "--quiet", "--only", "-m", "SLR Checkpoint: " + message, "--", *paths)
            commit_hash = self.git("rev-parse", "HEAD")
        finally:
            self.conn = sqlite3.connect(self.workspace / "slr_state.sqlite", timeout=30)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys=ON")
            with self.conn:
                self.conn.execute("UPDATE audit_log SET git_commit_hash=?,notes=? WHERE id=?",
                                  (commit_hash, json.dumps({"message": message,
                                   "state": "committed" if commit_hash else "failed"}), audit_id))
        print(json.dumps({"checkpoint": commit_hash, "message": message}))
        return commit_hash

    def stage_skill_updates(self):
        if not (self.root / ".git").exists():
            return {"status": "no_repository"}
        upstream = self.git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False)
        branch = self.git("symbolic-ref", "--short", "HEAD", check=False)
        remote = self.git("config", "--get", f"branch.{branch}.remote", check=False) if branch else ""
        if not upstream or not remote:
            return {"status": "no_upstream"}
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
        self.git("fetch", "--quiet", "--no-tags", "--", remote, env=env)
        commit = self.git("rev-parse", upstream)
        folder = self.workspace / "skill_updates" / commit
        entries = self.git("ls-tree", "-r", commit, "--", "2_skills/")
        staged = []
        for line in entries.splitlines():
            metadata, name = line.split("\t", 1)
            mode, kind, blob = metadata.split()
            path = Path(name)
            if (mode not in ("100644", "100755") or kind != "blob" or path.is_absolute()
                    or ".." in path.parts or path.parts[0] != "2_skills" or path.suffix not in (".py", ".md")):
                raise EngineError("Upstream contains an unsupported skill path or symlink; review manually.")
            content = self.git("show", blob, binary=True)
            if len(content) > 5_000_000:
                raise EngineError("Upstream skill file exceeds the review staging size limit.")
            atomic_write(folder / path, content)
            staged.append(name)
        result = {"status": "staged_for_review", "commit": commit, "files": staged,
                  "path": folder.relative_to(self.root).as_posix()}
        with self.conn:
            self.audit("update", "skills_staged", result)
        return result

    def update(self):
        jobs = {}
        for row in self.conn.execute("""SELECT action,query_executed,notes FROM audit_log
            WHERE phase='search' AND action IN ('started','completed','capped','failed') ORDER BY id"""):
            data = json.loads(row["notes"])
            pair = (data["db"], row["query_executed"])
            job = jobs.setdefault(pair, {"since": data.get("since"), "maximum": data["max_results"]})
            job["maximum"] = data["max_results"]
            if row["action"] == "completed":
                job["since"] = data["started"][:10]
        if jobs:
            query = self.protocol_query()  # Fail before retrieval if the protocol is not usable.
        complete = True
        for (db, original), job in jobs.items():
            complete = self.search(original, [db], job["maximum"], job["since"]) and complete
        if jobs:
            self.rank(query)
        try:
            skills = self.stage_skill_updates()
        except EngineError as exc:
            skills = {"status": "failed", "error": str(exc)}
            complete = False
            with self.conn:
                self.audit("update", "skills_failed", skills)
        print(json.dumps({"query_database_pairs": len(jobs), "skills": skills}))
        self.checkpoint("Living review update" if jobs else "Skill update check")
        return complete

    def status(self):
        path = self.workspace / "protocol.md"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        state = re.search(r"^Status:\s*(.+)$", text, re.M)
        print("Protocol:", state[1] if state else "MISSING/UNSPECIFIED")
        print("Papers:", self.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0])
        for db in DBS:
            count = self.conn.execute("SELECT COUNT(*) FROM papers WHERE ',' || source_db || ',' LIKE ?",
                                      ("%," + db + ",%",)).fetchone()[0]
            print(f"  {db}: {count} (memberships overlap)")
        print("Screening:")
        for row in self.conn.execute("SELECT stage,COALESCE(decision,'PENDING'),COUNT(*) FROM screening GROUP BY stage,decision"):
            print(f"  {row[0]} / {row[1]}: {row[2]}")
        for row in self.conn.execute("SELECT pdf_status,COUNT(*) FROM papers GROUP BY pdf_status"):
            print(f"PDF {row[0]}: {row[1]}")
        row = self.conn.execute("SELECT COUNT(*),COUNT(DISTINCT bib_key) FROM extractions").fetchone()
        print(f"Extractions: {row[0]} evidence rows across {row[1]} papers")
        checkpoint = self.conn.execute("SELECT timestamp,git_commit_hash FROM audit_log WHERE action='checkpoint' AND git_commit_hash IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
        print("Latest checkpoint:", f"{checkpoint[0]} UTC {checkpoint[1]}" if checkpoint else "none")


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Initialize directories, four SQLite tables, and local Git")
    search = commands.add_parser("search", help="Search and deduplicate database metadata")
    search.add_argument("--query", required=True)
    search.add_argument("--dbs", default=",".join(DBS))
    search.add_argument("--max-results", type=positive, default=200)
    search.add_argument("--since", type=iso_date)
    rank = commands.add_parser("rank", help="Rank reading priority without deciding eligibility")
    rank.add_argument("--picoc-text")
    batch = commands.add_parser("fetch-batch", help="Emit bounded JSON evidence batches")
    batch.add_argument("--phase", choices=("screen", "extract"), required=True)
    batch.add_argument("--limit", type=positive)
    decision = commands.add_parser("record-decision", help="Validate evidence and record a screening decision")
    decision.add_argument("--bib-key", required=True)
    decision.add_argument("--stage", choices=("TITLE_ABSTRACT", "FULL_TEXT"), required=True)
    decision.add_argument("--devils-advocate", required=True)
    decision.add_argument("--quote", required=True)
    decision.add_argument("--decision", choices=("INCLUDE", "EXCLUDE", "MAYBE"), required=True)
    decision.add_argument("--code", required=True)
    decision.add_argument("--notes", default="")
    ingest = commands.add_parser("ingest", help="Retrieve PDFs and render text plus 200-DPI pages")
    ingest.add_argument("--bib-key")
    extraction = commands.add_parser("record-extraction", help="Store page-grounded evidence and update matrix")
    extraction.add_argument("--bib-key", required=True)
    extraction.add_argument("--variable", required=True)
    extraction.add_argument("--quote", required=True)
    extraction.add_argument("--page", type=positive, required=True)
    extraction.add_argument("--value", required=True)
    extraction.add_argument("--used-vision", type=int, choices=(0, 1), default=0)
    commands.add_parser("prisma", help="Generate reproducible PRISMA counts and flowchart")
    checkpoint = commands.add_parser("checkpoint", help="Create a local shadow backup")
    checkpoint.add_argument("--message", required=True)
    commands.add_parser("update", help="Run living searches and stage upstream skill updates")
    commands.add_parser("status", help="Print the review dashboard")
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        with workspace_lock(ROOT / "1_workspace"):
            engine = Engine()
            try:
                result = None
                if args.command == "search":
                    result = engine.search(args.query, [d.strip().lower() for d in args.dbs.split(",")], args.max_results, args.since)
                elif args.command == "rank":
                    engine.rank(args.picoc_text)
                elif args.command == "fetch-batch":
                    engine.fetch_batch(args.phase, args.limit)
                elif args.command == "record-decision":
                    engine.record_decision(args)
                elif args.command == "ingest":
                    result = engine.ingest(args.bib_key)
                elif args.command == "record-extraction":
                    engine.record_extraction(args)
                elif args.command == "checkpoint":
                    engine.checkpoint(args.message)
                else:
                    result = getattr(engine, args.command)()
                return 2 if result is False else 0
            finally:
                engine.close()
    except (EngineError, sqlite3.Error, OSError, ValueError, subprocess.SubprocessError) as exc:
        print("ERROR: " + (str(exc) if isinstance(exc, EngineError) else type(exc).__name__), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted; completed database transactions are preserved.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
