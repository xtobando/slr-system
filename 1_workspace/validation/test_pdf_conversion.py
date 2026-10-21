"""Offline PDF conversion checks using synthetic documents, never review data."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote

import pymupdf as fitz


PROJECT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pdf_conversion_engine", PROJECT / "2_skills/engine.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PDFConversionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="case-pdf-", dir=TEST_ROOT)
        self.root = Path(self.temporary.name).resolve()
        self.addCleanup(self.temporary.cleanup)

    def document(self, name="Evidence notes \u03b1.pdf", rotation=0, blank=True):
        """Exercise native text, inline math, vector diagrams, and raster images."""
        path = self.root / name
        with fitz.open() as document:
            page = document.new_page(width=360, height=480)
            page.insert_text((30, 35), "Participants completed the review task.")
            page.insert_text((30, 75), "x = y + 1", fontsize=14)
            page.draw_rect(fitz.Rect(30, 120, 145, 200), color=(0, 0, 0))
            page.draw_rect(fitz.Rect(185, 120, 300, 200), color=(0, 0, 0))
            page.draw_line(fitz.Point(145, 160), fitz.Point(185, 160), color=(0, 0, 0))
            page.insert_text((45, 160), "Input")
            page.insert_text((200, 160), "Output")
            image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 32, 24), False)
            image.clear_with(96)
            page.insert_image(fitz.Rect(30, 240, 190, 360), pixmap=image)
            page.set_rotation(rotation)
            if blank:
                document.new_page(width=360, height=480)
            document.save(path)
        return path

    def read_result(self, result, folder):
        markdown = Path(result["markdown"])
        manifest = Path(result["manifest"])
        self.assertEqual(markdown.resolve(), (folder / "fulltext.md").resolve())
        self.assertEqual(manifest.resolve(), (folder / "assets.json").resolve())
        return markdown.read_text(encoding="utf-8"), json.loads(manifest.read_text(encoding="utf-8"))

    def test_text_math_diagrams_and_images_have_portable_visual_references(self):
        source = self.document()
        folder = self.root / "converted notes"
        result = module.convert_pdf(source, folder)
        markdown, manifest = self.read_result(result, folder)
        self.assertEqual(result["pages"], 2)
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["source"]["filename"], source.name)
        self.assertEqual(manifest["source"]["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(manifest["dpi"], 300)
        self.assertIn("Participants completed the review task.", markdown)
        self.assertIn("<!-- PAGE 1 -->", markdown)
        self.assertIn("<!-- PAGE 2 -->", markdown)
        first, second = manifest["pages"]
        self.assertEqual(first["text_status"], "extracted")
        self.assertEqual(second["text_status"], "no_text")
        self.assertTrue({"page", "formula", "vector", "image"}.issubset(
            {asset["kind"] for asset in first["assets"]}))
        assets = [asset for page in manifest["pages"] for asset in page["assets"]]
        self.assertEqual(result["images"], len(assets))
        links = re.findall(r"!\[[^\]]*\]\((?:<([^>]+)>|([^\s)]+))(?:\s+\"[^\"]*\")?\)", markdown)
        targets = {unquote(left or right) for left, right in links}
        self.assertTrue(targets, "A Markdown viewer must display the retained pictures")
        for asset in assets:
            relative = Path(asset["path"])
            self.assertFalse(relative.is_absolute())
            self.assertTrue((folder / relative).resolve().is_relative_to(folder.resolve()))
            self.assertTrue((folder / relative).is_file())
            self.assertIn(relative.as_posix(), targets)
            pixmap = fitz.Pixmap(str(folder / relative))
            self.assertEqual((pixmap.xres, pixmap.yres), (300, 300))
        self.assertTrue((folder / "page_2_visual.png").is_file())

    def test_rotated_page_and_manual_crop_preserve_visual_dimensions(self):
        source = self.document(rotation=90, blank=False)
        folder = self.root / "rotated"
        result = module.convert_pdf(source, folder, dpi=144, crops=[(1, 25, 50, 160, 85)])
        _, manifest = self.read_result(result, folder)
        page = manifest["pages"][0]
        self.assertEqual(page["rotation"], 90)
        full_page = next(asset for asset in page["assets"] if asset["kind"] == "page")
        pixmap = fitz.Pixmap(str(folder / full_page["path"]))
        self.assertEqual((pixmap.width, pixmap.height), (960, 720))
        manual = [asset for asset in page["assets"] if asset["kind"] == "manual"]
        self.assertEqual(len(manual), 1)
        pixmap = fitz.Pixmap(str(folder / manual[0]["path"]))
        self.assertEqual((pixmap.width, pixmap.height), (70, 270))

    def test_rotated_cropbox_selects_the_requested_content(self):
        source = self.root / "cropped-and-rotated.pdf"
        with fitz.open() as document:
            page = document.new_page(width=360, height=480)
            page.draw_rect(fitz.Rect(60, 70, 130, 130), color=(1, 0, 0), fill=(1, 0, 0))
            page.draw_rect(fitz.Rect(190, 230, 290, 330), color=(0, 0, 1), fill=(0, 0, 1))
            page.set_cropbox(fitz.Rect(30, 40, 330, 400))
            page.set_rotation(90)
            document.save(source)
        folder = self.root / "selected-region"
        result = module.convert_pdf(source, folder, dpi=144, crops=[(1, 35, 35, 95, 85)])
        _, manifest = self.read_result(result, folder)
        manual = next(asset for asset in manifest["pages"][0]["assets"] if asset["kind"] == "manual")
        pixmap = fitz.Pixmap(str(folder / manual["path"]))
        self.assertEqual((pixmap.width, pixmap.height), (100, 120))
        self.assertEqual(pixmap.pixel(pixmap.width // 2, pixmap.height // 2), (255, 0, 0))

    def test_scanned_page_preserves_image_without_fabricating_text(self):
        source = self.root / "scan.pdf"
        with fitz.open() as document:
            page = document.new_page(width=120, height=160)
            scanned = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 120, 160), False)
            scanned.clear_with(96)
            page.insert_image(page.rect, pixmap=scanned)
            document.save(source)
        folder = self.root / "scan-export"
        result = module.convert_pdf(source, folder, dpi=72)
        markdown, manifest = self.read_result(result, folder)
        self.assertEqual(manifest["pages"][0]["text_status"], "no_text")
        self.assertTrue({"page", "image"}.issubset(
            {asset["kind"] for asset in manifest["pages"][0]["assets"]}))
        self.assertIn("No extractable text", markdown)
        pixmap = fitz.Pixmap(str(folder / "page_1_visual.png"))
        self.assertEqual(pixmap.pixel(60, 80), (96, 96, 96))

    def test_pdf_markdown_html_and_math_delimiters_remain_literal_text(self):
        source = self.root / "literal-text.pdf"
        lines = ["# Source heading", "[reference](https://untrusted.example)",
                 "<script>alert(1)</script>", "$cost$", "---", "- source bullet"]
        with fitz.open() as document:
            page = document.new_page(width=360, height=300)
            for row, line in enumerate(lines):
                page.insert_text((20, 30 + 30 * row), line, fontsize=10)
            document.save(source)
        result = module.convert_pdf(source, self.root / "literal-export", dpi=72)
        markdown = Path(result["markdown"]).read_text(encoding="utf-8")
        self.assertIn(r"\# Source heading", markdown)
        self.assertIn(r"\[reference\]", markdown)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", markdown)
        self.assertIn(r"\$cost\$", markdown)
        self.assertRegex(markdown, r"(?m)^\\-(?:\\?-){2}$")
        self.assertIn(r"\- source bullet", markdown)

    def test_mid_render_failure_removes_staged_files(self):
        source = self.document()
        folder = self.root / "interrupted-output"
        original_write = module.atomic_write
        written_pngs = 0

        def fail_after_first_image(path, content):
            nonlocal written_pngs
            if Path(path).suffix == ".png":
                written_pngs += 1
                if written_pngs == 2:
                    raise OSError("Simulated write failure")
            return original_write(path, content)

        before = set(self.root.iterdir())
        with patch.object(module, "atomic_write", side_effect=fail_after_first_image):
            with self.assertRaises(OSError):
                module.convert_pdf(source, folder)
        self.assertEqual(written_pngs, 2)
        self.assertFalse(folder.exists())
        self.assertEqual(set(self.root.iterdir()), before)

    def test_existing_output_is_not_overwritten(self):
        source = self.document(blank=False)
        folder = self.root / "existing"
        folder.mkdir()
        note = folder / "reviewer-notes.md"
        note.write_text("Keep the reviewer's work.", encoding="utf-8")
        with self.assertRaises(module.EngineError):
            module.convert_pdf(source, folder)
        self.assertEqual(note.read_text(encoding="utf-8"), "Keep the reviewer's work.")
        self.assertEqual(list(folder.iterdir()), [note])

    def test_invalid_or_encrypted_pdf_leaves_no_conversion_output(self):
        invalid = self.root / "invalid.pdf"
        invalid.write_bytes(b"This is not a PDF.")
        encrypted = self.root / "encrypted.pdf"
        with fitz.open() as document:
            document.new_page(width=100, height=100)
            document.save(encrypted, encryption=fitz.PDF_ENCRYPT_AES_256,
                          owner_pw="fixture-owner", user_pw="fixture-user")
        for source in (invalid, encrypted):
            with self.subTest(source=source.name):
                folder = self.root / (source.stem + "-output")
                before = set(self.root.iterdir())
                with self.assertRaises(module.EngineError):
                    module.convert_pdf(source, folder)
                self.assertFalse(folder.exists())
                self.assertEqual(set(self.root.iterdir()), before)

    def test_invalid_dpi_and_out_of_page_crops_are_rejected(self):
        source = self.document(blank=False)
        for dpi in (71, 601):
            with self.subTest(dpi=dpi):
                folder = self.root / f"dpi-{dpi}"
                with self.assertRaises(module.EngineError):
                    module.convert_pdf(source, folder, dpi=dpi)
                self.assertFalse(folder.exists())
        for crop in ((2, 1, 1, 5, 5), (1, 30, 40, 20, 60), (1, -1, 0, 20, 20)):
            with self.subTest(crop=crop):
                folder = self.root / "bad-crop"
                with self.assertRaises(module.EngineError):
                    module.convert_pdf(source, folder, crops=[crop])
                self.assertFalse(folder.exists())

    def test_oversized_page_fails_without_partial_outputs(self):
        source = self.root / "oversized.pdf"
        with fitz.open() as document:
            document.new_page(width=3000, height=3000)
            document.save(source)
        folder = self.root / "oversized-output"
        before = set(self.root.iterdir())
        with self.assertRaises(module.EngineError):
            module.convert_pdf(source, folder)
        self.assertFalse(folder.exists())
        self.assertEqual(set(self.root.iterdir()), before)

    def test_cli_converts_without_creating_review_database_or_bibliography(self):
        source = self.document(blank=False)
        with patch.object(module, "ROOT", self.root), \
                patch.object(module, "Engine", side_effect=AssertionError("Conversion must not open review state")), \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = module.main(["convert-pdf", "--pdf", str(source)])
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        folder = Path(result["markdown"]).parent
        self.assertTrue(folder.is_relative_to(self.root / "3_papers/parsed_cache/documents"))
        self.assertTrue((folder / "fulltext.md").is_file())
        self.assertFalse((self.root / "1_workspace/slr_state.sqlite").exists())
        self.assertFalse((self.root / "3_papers/references.bib").exists())

    def test_cli_rejects_output_outside_project_application_directories(self):
        source = self.document(blank=False)
        for output in ("fourth-folder", "2_skills/export", "../outside-conversion"):
            with self.subTest(output=output), patch.object(module, "ROOT", self.root), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = module.main(["convert-pdf", "--pdf", str(source), "--output-dir", output])
                self.assertNotEqual(code, 0)
                self.assertFalse((self.root / output).exists())

    def test_cli_reports_rendering_failure_without_traceback_or_partial_export(self):
        source = self.document(blank=False)
        output = "3_papers/parsed_cache/failed-export"
        with patch.object(module, "ROOT", self.root), \
                patch.object(fitz.Page, "get_pixmap", side_effect=RuntimeError("Simulated PDF rendering failure")), \
                contextlib.redirect_stdout(io.StringIO()) as stdout, \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            code = module.main(["convert-pdf", "--pdf", str(source), "--output-dir", output])
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("ERROR: PDF rendering failed", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())
        self.assertFalse((self.root / output).exists())
        self.assertEqual(list((self.root / output).parent.glob(".pdf-export-*")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
