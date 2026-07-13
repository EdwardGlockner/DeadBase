from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deadlock_coach.config import Settings
from deadlock_coach.knowledge_base import (
    extract_knowledge_entities,
    imported_knowledge_root,
    query_local_knowledge_tables,
    retrieve_grounded_knowledge_context,
    search_local_knowledge,
    sync_reference_corpus,
    sync_wiki_reference_files,
    wiki_page_parse,
    wiki_all_pages,
    wiki_category_members,
)


class KnowledgeBaseSyncTests(unittest.TestCase):
    class _FakeHttpResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self) -> "KnowledgeBaseSyncTests._FakeHttpResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def test_sync_wiki_reference_files_writes_imported_markdown_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            payload = {
                "query": {
                    "pages": {
                        "60": {
                            "pageid": 60,
                            "title": "Lash",
                            "extract": "Lash is a bruiser initiator.",
                        }
                    }
                }
            }

            with patch("deadlock_coach.knowledge_base.urlopen", return_value=self._FakeHttpResponse(payload)):
                result = sync_wiki_reference_files(settings, kind="heroes", titles=["Lash"], limit=5)

            self.assertEqual(result["imported_count"], 1)
            import_path = imported_knowledge_root(settings) / "heroes" / "lash.md"
            self.assertTrue(import_path.exists())
            self.assertIn("Imported reference", import_path.read_text(encoding="utf-8"))
            self.assertIn("Lash is a bruiser initiator.", import_path.read_text(encoding="utf-8"))
            manifest_path = settings.project_root / result["manifest_path"]
            self.assertTrue(manifest_path.exists())

    def test_sync_wiki_reference_files_uses_category_when_titles_not_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            category_payload = {
                "query": {
                    "categorymembers": [
                        {"title": "Lash"},
                        {"title": "Shiv"},
                    ]
                }
            }
            lash_payload = {
                "query": {
                    "pages": {
                        "60": {"pageid": 60, "title": "Lash", "extract": "Lash extract."}
                    }
                }
            }
            shiv_payload = {
                "query": {
                    "pages": {
                        "88": {"pageid": 88, "title": "Shiv", "extract": "Shiv extract."}
                    }
                }
            }

            responses = [
                self._FakeHttpResponse(category_payload),
                self._FakeHttpResponse(lash_payload),
                self._FakeHttpResponse(shiv_payload),
            ]

            def next_response(*_args, **_kwargs):
                return responses.pop(0)

            with patch("deadlock_coach.knowledge_base.urlopen", side_effect=next_response):
                result = sync_wiki_reference_files(settings, kind="heroes", titles=[], limit=2)

            self.assertEqual(result["imported_count"], 2)
            self.assertTrue((imported_knowledge_root(settings) / "heroes" / "lash.md").exists())
            self.assertTrue((imported_knowledge_root(settings) / "heroes" / "shiv.md").exists())

    def test_wiki_category_members_paginates_and_filters_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            first_payload = {
                "query": {
                    "categorymembers": [
                        {"ns": 0, "title": "Lash"},
                        {"ns": 0, "title": "Lash/zh-hans"},
                        {"ns": 2, "title": "User:Sandbox/Haze"},
                    ]
                },
                "continue": {"cmcontinue": "page|abc", "continue": "-||"},
            }
            second_payload = {
                "query": {
                    "categorymembers": [
                        {"ns": 0, "title": "Shiv"},
                        {"ns": 0, "title": "Lash"},
                    ]
                }
            }

            responses = [
                self._FakeHttpResponse(first_payload),
                self._FakeHttpResponse(second_payload),
            ]

            def next_response(*_args, **_kwargs):
                return responses.pop(0)

            with patch("deadlock_coach.knowledge_base.urlopen", side_effect=next_response):
                titles = wiki_category_members(settings, "Category:Heroes", limit=None)

            self.assertEqual(titles, ["Lash", "Shiv"])

    def test_sync_reference_corpus_imports_both_heroes_and_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            responses = [
                self._FakeHttpResponse({"query": {"categorymembers": [{"ns": 0, "title": "Lash"}]}}),
                self._FakeHttpResponse({"query": {"pages": {"60": {"pageid": 60, "title": "Lash", "extract": "Lash extract."}}}}),
                self._FakeHttpResponse({"query": {"categorymembers": [{"ns": 0, "title": "Active Reload"}]}}),
                self._FakeHttpResponse({"query": {"pages": {"267": {"pageid": 267, "title": "Active Reload", "extract": "Item extract."}}}}),
            ]

            def next_response(*_args, **_kwargs):
                return responses.pop(0)

            with patch("deadlock_coach.knowledge_base.urlopen", side_effect=next_response):
                result = sync_reference_corpus(settings)

            self.assertEqual(result["imported_count"], 2)
            self.assertTrue((imported_knowledge_root(settings) / "heroes" / "lash.md").exists())
            self.assertTrue((imported_knowledge_root(settings) / "items" / "active-reload.md").exists())

    def test_wiki_all_pages_paginates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            first_payload = {
                "query": {
                    "allpages": [
                        {"ns": 0, "title": "Boon"},
                        {"ns": 0, "title": "Billy"},
                    ]
                },
                "continue": {"apcontinue": "Billy", "continue": "-||"},
            }
            second_payload = {
                "query": {
                    "allpages": [
                        {"ns": 0, "title": "Warp Stone"},
                    ]
                }
            }

            responses = [
                self._FakeHttpResponse(first_payload),
                self._FakeHttpResponse(second_payload),
            ]

            def next_response(*_args, **_kwargs):
                return responses.pop(0)

            with patch("deadlock_coach.knowledge_base.urlopen", side_effect=next_response):
                titles = wiki_all_pages(settings, limit=None)

            self.assertEqual(titles, ["Boon", "Billy", "Warp Stone"])

    def test_sync_wiki_reference_files_supports_full_page_imports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            allpages_payload = {
                "query": {
                    "allpages": [
                        {"ns": 0, "title": "Boon"},
                        {"ns": 0, "title": "Billy"},
                    ]
                }
            }
            boon_payload = {
                "parse": {
                    "pageid": 799,
                    "title": "Boon",
                    "text": {
                        "*": (
                            "<h2>Boon Basics</h2>"
                            "<p>Boons increase hero power over the match.</p>"
                            "<table>"
                            "<caption>Base Bullet Damage based on Boons</caption>"
                            "<tr><th>Hero</th><th>Increase per Boon</th></tr>"
                            "<tr><td>The Doorman</td><td>+1.19</td></tr>"
                            "</table>"
                        )
                    },
                }
            }
            billy_payload = {
                "parse": {
                    "pageid": 801,
                    "title": "Billy",
                    "text": {
                        "*": "<p>Billy extract.</p>"
                    },
                }
            }

            responses = [
                self._FakeHttpResponse(allpages_payload),
                self._FakeHttpResponse(boon_payload),
                self._FakeHttpResponse(billy_payload),
            ]

            def next_response(*_args, **_kwargs):
                return responses.pop(0)

            with patch("deadlock_coach.knowledge_base.urlopen", side_effect=next_response):
                result = sync_wiki_reference_files(settings, kind="pages", titles=[], limit=2)

            self.assertEqual(result["imported_count"], 2)
            self.assertTrue((imported_knowledge_root(settings) / "pages" / "799-boon.md").exists())
            self.assertTrue((imported_knowledge_root(settings) / "pages" / "801-billy.md").exists())
            boon_text = (imported_knowledge_root(settings) / "pages" / "799-boon.md").read_text(encoding="utf-8")
            self.assertIn("Base Bullet Damage based on Boons", boon_text)
            self.assertIn("| Hero | Increase per Boon |", boon_text)
            self.assertIn("| The Doorman | +1.19 |", boon_text)

    def test_sync_reference_corpus_can_include_full_wiki_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            responses = [
                self._FakeHttpResponse({"query": {"categorymembers": [{"ns": 0, "title": "Lash"}]}}),
                self._FakeHttpResponse({"query": {"pages": {"60": {"pageid": 60, "title": "Lash", "extract": "Lash extract."}}}}),
                self._FakeHttpResponse({"query": {"categorymembers": [{"ns": 0, "title": "Active Reload"}]}}),
                self._FakeHttpResponse({"query": {"pages": {"267": {"pageid": 267, "title": "Active Reload", "extract": "Item extract."}}}}),
                self._FakeHttpResponse({"query": {"allpages": [{"ns": 0, "title": "Boon"}]}}),
                self._FakeHttpResponse({"parse": {"pageid": 799, "title": "Boon", "text": {"*": "<p>Boon extract.</p>"}}}),
            ]

            def next_response(*_args, **_kwargs):
                return responses.pop(0)

            with patch("deadlock_coach.knowledge_base.urlopen", side_effect=next_response):
                result = sync_reference_corpus(settings, include_pages=True, page_limit=1)

            self.assertEqual(result["imported_count"], 3)
            self.assertIn("pages", result["kinds"])
            self.assertTrue((imported_knowledge_root(settings) / "pages" / "799-boon.md").exists())

    def test_wiki_page_parse_preserves_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            payload = {
                "parse": {
                    "pageid": 379,
                    "title": "Items",
                    "text": {
                        "*": (
                            "<p>There are three types of items.</p>"
                            "<table>"
                            "<caption>Item Type Bonuses by Souls</caption>"
                            "<tr><th>Souls</th><th>Weapon</th><th>Spirit</th></tr>"
                            "<tr><td>4,800</td><td>+46%</td><td>+38</td></tr>"
                            "<tr><td>6,400</td><td>+54%</td><td>+45</td></tr>"
                            "</table>"
                        )
                    },
                }
            }

            with patch("deadlock_coach.knowledge_base.urlopen", return_value=self._FakeHttpResponse(payload)):
                page = wiki_page_parse(settings, "Items")

            assert page is not None
            self.assertIn("There are three types of items.", page["extract"])
            self.assertIn("Item Type Bonuses by Souls", page["extract"])
            self.assertIn("| 6,400 | +54% | +45 |", page["extract"])

    def test_search_local_knowledge_prefers_curated_note_over_imported_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(project_root=root)
            (root / "docs" / "knowledge" / "fundamentals").mkdir(parents=True, exist_ok=True)
            (root / "docs" / "knowledge" / "_imports" / "wiki" / "pages").mkdir(parents=True, exist_ok=True)
            (root / "docs" / "knowledge" / "fundamentals" / "boons-and-level-scaling.md").write_text(
                "# Boons And Level Scaling\n\n- boons are soul-based level rewards\n- boon level tracks soul progression through the match\n",
                encoding="utf-8",
            )
            (root / "docs" / "knowledge" / "_imports" / "wiki" / "pages" / "799-boon.md").write_text(
                (
                    "# Boon\n\n"
                    "Imported reference\n\n"
                    "- kind: pages\n"
                    "- source: Deadlock Wiki\n"
                    "- url: https://deadlock.wiki/Boon\n"
                    "- imported_at: 2026-07-08T10:00:00Z\n\n"
                    "Reference extract:\n\n"
                    "Boons indicate the player's power level over the course of the match.\n"
                ),
                encoding="utf-8",
            )

            matches = search_local_knowledge(settings, "do you know what boons are?", limit=2)

        self.assertGreaterEqual(len(matches), 1)
        self.assertEqual(matches[0]["source"], "knowledge_base")
        self.assertIn("boons-and-level-scaling.md", matches[0]["relative_path"])
        self.assertIn("soul-based level rewards", matches[0]["excerpt"])

    def test_search_local_knowledge_strips_import_metadata_from_excerpt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(project_root=root)
            (root / "docs" / "knowledge" / "_imports" / "wiki" / "pages").mkdir(parents=True, exist_ok=True)
            (root / "docs" / "knowledge" / "_imports" / "wiki" / "pages" / "799-boon.md").write_text(
                (
                    "# Boon\n\n"
                    "Imported reference\n\n"
                    "- kind: pages\n"
                    "- source: Deadlock Wiki\n"
                    "- url: https://deadlock.wiki/Boon\n"
                    "- imported_at: 2026-07-08T10:00:00Z\n\n"
                    "Reference extract:\n\n"
                    "Boons indicate the player's power level over the course of the match.\n"
                    "Players gain boons by gathering souls.\n"
                ),
                encoding="utf-8",
            )

            matches = search_local_knowledge(settings, "what are boons?", limit=1, source_filter="knowledge_imports")

        self.assertEqual(len(matches), 1)
        self.assertNotIn("Imported reference", matches[0]["excerpt"])
        self.assertNotIn("kind:", matches[0]["excerpt"])
        self.assertIn("power level", matches[0]["excerpt"])

    def test_search_local_knowledge_rebuilds_index_after_new_note_is_added(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(project_root=root)
            fundamentals = root / "docs" / "knowledge" / "fundamentals"
            fundamentals.mkdir(parents=True, exist_ok=True)
            (fundamentals / "boons-and-level-scaling.md").write_text(
                "# Boons\n\n- boons are soul-based level rewards\n",
                encoding="utf-8",
            )

            first_matches = search_local_knowledge(settings, "what are boons?", limit=2)
            self.assertEqual(len(first_matches), 1)

            (fundamentals / "local-vs-global-meta.md").write_text(
                "# Local Vs Global Meta\n\n- global meta answers need wider cohort or patch-aware analytics\n",
                encoding="utf-8",
            )

            second_matches = search_local_knowledge(settings, "what is the meta right now?", limit=2)

        self.assertEqual(len(second_matches), 1)
        self.assertIn("local-vs-global-meta.md", second_matches[0]["relative_path"])

    def test_query_local_knowledge_tables_returns_exact_numeric_threshold_fact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(project_root=root)
            pages = root / "docs" / "knowledge" / "_imports" / "wiki" / "pages"
            pages.mkdir(parents=True, exist_ok=True)
            (pages / "379-items.md").write_text(
                (
                    "# Items\n\n"
                    "Imported reference\n\n"
                    "### Item Type Bonuses by Souls\n\n"
                    "| Souls | Weapon | Vitality | Spirit |\n"
                    "| --- | --- | --- | --- |\n"
                    "| 4,800 | +46% | +38% | +38 |\n"
                    "| 6,400 | +54% | +42% | +45 |\n"
                    "| 8,000 | +62% | +46% | +52 |\n"
                ),
                encoding="utf-8",
            )

            result = query_local_knowledge_tables(settings, "how much bonus spirit do you get after 6.4k investment")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("6,400", result["fact"])
        self.assertIn("+45", result["fact"])
        self.assertIn("379-items.md", result["relative_path"])

    def test_query_local_knowledge_tables_can_answer_best_boon_scaling_from_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(project_root=root)
            pages = root / "docs" / "knowledge" / "_imports" / "wiki" / "pages"
            pages.mkdir(parents=True, exist_ok=True)
            (pages / "835-bullet-damage.md").write_text(
                (
                    "# Bullet Damage\n\n"
                    "Imported reference\n\n"
                    "### Base Bullet Damage Stats\n\n"
                    "| Hero | Starting | Added per Boon | At Max Boon |\n"
                    "| --- | --- | --- | --- |\n"
                    "| Billy | 6.3 | +0.127 | 10.7 |\n"
                    "| Holliday | 19.7 | +1.14 | 59.6 |\n"
                    "| The Doorman | 26 | +1.19 | 67.7 |\n"
                ),
                encoding="utf-8",
            )

            result = query_local_knowledge_tables(settings, "which hero weapon scales the best with boons")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("The Doorman", result["fact"])
        self.assertIn("+1.19", result["fact"])
        self.assertIn("Added per Boon", result["fact"])

    def test_extract_knowledge_entities_finds_named_hero_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(project_root=root)
            heroes = root / "docs" / "knowledge" / "_imports" / "wiki" / "heroes"
            heroes.mkdir(parents=True, exist_ok=True)
            (heroes / "shiv.md").write_text("# Shiv\n\nShiv is an assassin.\n", encoding="utf-8")

            entities = extract_knowledge_entities(settings, "what do high-mmr players build on shiv?")

        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0]["title"], "Shiv")
        self.assertIn("shiv.md", entities[0]["relative_path"])

    def test_retrieve_grounded_knowledge_context_combines_table_fact_and_chunk_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(project_root=root)
            pages = root / "docs" / "knowledge" / "_imports" / "wiki" / "pages"
            fundamentals = root / "docs" / "knowledge" / "fundamentals"
            pages.mkdir(parents=True, exist_ok=True)
            fundamentals.mkdir(parents=True, exist_ok=True)
            (pages / "379-items.md").write_text(
                (
                    "# Items\n\n"
                    "### Item Type Bonuses by Souls\n\n"
                    "| Souls | Weapon | Vitality | Spirit |\n"
                    "| --- | --- | --- | --- |\n"
                    "| 4,800 | +46% | +38% | +38 |\n"
                    "| 6,400 | +54% | +42% | +45 |\n"
                ),
                encoding="utf-8",
            )
            (fundamentals / "investment-spikes.md").write_text(
                (
                    "# Investment Spikes\n\n"
                    "- 4.8k is the famous category-bar spike.\n"
                    "- 6.4k still increases the bonus, but the standout spike is 4.8k.\n"
                ),
                encoding="utf-8",
            )

            result = retrieve_grounded_knowledge_context(
                settings,
                "how much bonus spirit do you get after 6.4k investment",
                limit=3,
            )

        self.assertEqual(result["fact"], "In Item Type Bonuses by Souls, the 6,400 row shows Spirit +45.")
        self.assertTrue(any(match["title"] == "Investment Spikes" for match in result["matches"]))
        self.assertTrue(any(table["section_title"] == "Item Type Bonuses by Souls" for table in result["tables"]))


if __name__ == "__main__":
    unittest.main()
