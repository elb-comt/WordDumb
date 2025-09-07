import json
import logging
import sqlite3
import subprocess
import sys
import unittest
from itertools import zip_longest
from pathlib import Path
from shutil import which

from calibre.library import db
from calibre_plugins.worddumb.config import prefs
from calibre_plugins.worddumb.parse_job import ParseJobData, do_job
from convert import LIMIT


class TestDumbCode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prefs["search_people"] = True
        prefs["add_locator_map"] = True
        prefs["minimal_x_ray_count"] = 1
        prefs["gloss_lang"] = "en"
        prefs["use_wiktionary_for_kindle"] = False
        prefs["test_wsd"] = False
        prefs["python_path"] = which("python3")
        prefs["custom_entity_only"] = False

        lib_db = db("~/Calibre Library").new_api
        for book_id in lib_db.all_book_ids():
            mi = lib_db.get_metadata(book_id)
            if mi.get("title") == "Twelve Years a Slave":
                test_book_id = book_id
                break

        for fmt in lib_db.formats(book_id):
            book_path = lib_db.format_abspath(book_id, fmt)
            cls.book_folder = Path(book_path).parent
            try:
                data = ParseJobData(
                    book_id=test_book_id,
                    book_path=book_path,
                    mi=mi,
                    book_fmt=fmt,
                    book_lang="en",
                )
                do_job(data)
                if fmt == "EPUB":
                    cls.epub_path = data.book_path
            except subprocess.CalledProcessError as e:
                logging.error(e.stderr.decode("utf-8", "ignore"))
                raise e

            if fmt != "EPUB":
                kll_path = cls.get_db_path(cls, ".kll")
                kll_path.rename(kll_path.with_suffix(f".kll_{fmt}"))
                asc_path = cls.get_db_path(cls, ".asc")
                asc_path.rename(asc_path.with_suffix(f".asc_{fmt}"))

    def get_db_path(self, suffix):
        for path in self.book_folder.iterdir():
            if path.suffix == suffix:
                return path

    def check_db(self, test_json_path, created_db_path, table, sql):
        with (
            open(test_json_path, encoding="utf-8") as test_json,
            sqlite3.connect(created_db_path) as created_db,
        ):
            for expected_value, value_in_db in zip_longest(
                json.load(test_json)[table], created_db.execute(sql)
            ):
                self.assertEqual(tuple(expected_value), value_in_db)

    def test_word_wise_glosses(self):
        for fmt in ["KFX", "AZW3"]:
            self.check_db(
                f"LanguageLayer.en.{fmt}.json",
                self.get_db_path(f".kll_{fmt}"),
                "glosses",
                "SELECT start, difficulty, sense_id FROM glosses "
                f"ORDER BY start LIMIT {LIMIT}",
            )

    def test_word_wise_glosses_count(self):
        for fmt in ["KFX", "AZW3"]:
            self.check_db(
                f"LanguageLayer.en.{fmt}.json",
                self.get_db_path(f".kll_{fmt}"),
                "count",
                "SELECT count(*) FROM glosses",
            )

    def test_word_wise_metadata(self):
        for fmt in ["KFX", "AZW3"]:
            self.check_db(
                f"LanguageLayer.en.{fmt}.json",
                self.get_db_path(f".kll_{fmt}"),
                "metadata",
                "SELECT * FROM metadata",
            )

    def test_x_ray_occurrence(self):
        for fmt in ["KFX", "AZW3"]:
            self.check_db(
                f"XRAY.entities.{fmt}.json",
                self.get_db_path(f".asc_{fmt}"),
                "occurrence",
                f"SELECT * FROM occurrence ORDER BY start LIMIT {LIMIT}",
            )

    def test_x_ray_book_metadata(self):
        for fmt in ["KFX", "AZW3"]:
            self.check_db(
                f"XRAY.entities.{fmt}.json",
                self.get_db_path(f".asc_{fmt}"),
                "book_metadata",
                "SELECT * FROM book_metadata",
            )

    def test_x_ray_top_mentioned(self):
        for fmt in ["KFX", "AZW3"]:
            self.check_db(
                f"XRAY.entities.{fmt}.json",
                self.get_db_path(f".asc_{fmt}"),
                "type",
                "SELECT top_mentioned_entities FROM type",
            )

    def test_x_ray_image_excerpt(self):
        for fmt in ["KFX", "AZW3"]:
            self.check_db(
                f"XRAY.entities.{fmt}.json",
                self.get_db_path(f".asc_{fmt}"),
                "excerpt",
                "SELECT * FROM excerpt",
            )

    def test_epub_file(self):
        self.assertTrue(Path(self.epub_path).exists())


if __name__ == "__main__":
    r = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestDumbCode)
    )
    sys.exit(0 if r.wasSuccessful() else 1)
