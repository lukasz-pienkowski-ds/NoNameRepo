import json

from db.store import get_project_context, ingest_lines, query_similar


def _line(**fields) -> str:
    return json.dumps(fields)


class TestIngestLines:
    def test_ingests_each_non_empty_line(self, con):
        lines = [_line(id="a", text="docker compose"), _line(id="b", text="duckdb sql")]
        count = ingest_lines(con, lines)
        assert count == 2
        (total,) = con.execute("SELECT count(*) FROM documents").fetchone()
        assert total == 2

    def test_skips_blank_lines(self, con):
        lines = [_line(id="a", text="hello"), "", "   "]
        count = ingest_lines(con, lines)
        assert count == 1

    def test_defaults_id_from_source_and_line_number(self, con):
        ingest_lines(con, [_line(text="no id given")], default_source="jsonl")
        (doc_id,) = con.execute("SELECT id FROM documents").fetchone()
        assert doc_id == "jsonl-1"

    def test_defaults_source_when_missing(self, con):
        ingest_lines(con, [_line(id="a", text="x")], default_source="myfeed")
        (source,) = con.execute("SELECT source_file FROM documents WHERE id = 'a'").fetchone()
        assert source == "myfeed"

    def test_explicit_source_overrides_default(self, con):
        ingest_lines(con, [_line(id="a", text="x", source="explicit")], default_source="myfeed")
        (source,) = con.execute("SELECT source_file FROM documents WHERE id = 'a'").fetchone()
        assert source == "explicit"

    def test_extra_fields_land_in_metadata(self, con):
        ingest_lines(con, [_line(id="a", text="x", extra="value", another=2)])
        (metadata,) = con.execute("SELECT metadata FROM documents WHERE id = 'a'").fetchone()
        parsed = json.loads(metadata)
        assert parsed == {"extra": "value", "another": 2}

    def test_known_fields_excluded_from_metadata(self, con):
        ingest_lines(con, [_line(id="a", text="x", source="s", domain="d", model="m")])
        (metadata,) = con.execute("SELECT metadata FROM documents WHERE id = 'a'").fetchone()
        assert json.loads(metadata) == {}

    def test_tags_are_derived_from_text(self, con):
        ingest_lines(con, [_line(id="a", text="we use docker here")])
        (tags,) = con.execute("SELECT tags FROM documents WHERE id = 'a'").fetchone()
        assert tags == ["infra"]

    def test_reingesting_same_id_updates_row(self, con):
        ingest_lines(con, [_line(id="a", text="first version")])
        ingest_lines(con, [_line(id="a", text="second version")])
        (total,) = con.execute("SELECT count(*) FROM documents").fetchone()
        assert total == 1
        (text,) = con.execute("SELECT text FROM documents WHERE id = 'a'").fetchone()
        assert text == "second version"

    def test_missing_text_field_raises_keyerror(self, con):
        try:
            ingest_lines(con, [_line(id="a")])
        except KeyError as exc:
            assert exc.args[0] == "text"
        else:
            raise AssertionError("expected KeyError for missing text field")


class TestQuerySimilar:
    def test_returns_top_k_ordered_by_score(self, con):
        ingest_lines(
            con,
            [
                _line(id="a", text="docker compose infra setup"),
                _line(id="b", text="completely unrelated topic about cooking"),
            ],
        )
        results = query_similar(con, "docker compose infra setup", top_k=1)
        assert len(results) == 1
        assert results[0]["id"] == "a"
        assert "score" in results[0]

    def test_respects_top_k_limit(self, con):
        ingest_lines(
            con,
            [_line(id=f"doc{i}", text=f"text number {i}") for i in range(5)],
        )
        results = query_similar(con, "text number", top_k=3)
        assert len(results) == 3

    def test_empty_store_returns_empty_list(self, con):
        assert query_similar(con, "anything") == []


class TestGetProjectContext:
    def test_filters_by_domain(self, con):
        ingest_lines(con, [_line(id="a", text="x", domain="proj1")])
        ingest_lines(con, [_line(id="b", text="y", domain="proj2")])
        result = get_project_context(con, "proj1")
        assert result["count"] == 1
        assert result["documents"][0]["id"] == "a"

    def test_filters_by_model_when_present(self, con):
        ingest_lines(con, [_line(id="a", text="x", domain="proj1", model="gpt")])
        ingest_lines(con, [_line(id="b", text="y", domain="proj1", model="claude")])
        result = get_project_context(con, "proj1", model_name="claude")
        assert result["count"] == 1
        assert result["documents"][0]["id"] == "b"
        assert result["used_model_fallback"] is False

    def test_falls_back_when_model_has_no_matches(self, con):
        ingest_lines(con, [_line(id="a", text="x", domain="proj1", model="gpt")])
        result = get_project_context(con, "proj1", model_name="nonexistent-model")
        assert result["count"] == 1
        assert result["used_model_fallback"] is True

    def test_filters_by_tags(self, con):
        ingest_lines(con, [_line(id="a", text="docker infra", domain="proj1")])
        ingest_lines(con, [_line(id="b", text="totally unrelated text", domain="proj1")])
        result = get_project_context(con, "proj1", tags=["infra"])
        assert result["count"] == 1
        assert result["documents"][0]["id"] == "a"

    def test_groups_documents_by_topic(self, con):
        ingest_lines(con, [_line(id="a", text="docker infra setup", domain="proj1")])
        ingest_lines(con, [_line(id="b", text="more docker infra", domain="proj1")])
        result = get_project_context(con, "proj1")
        assert sorted(result["topics"]["infra"]) == ["a", "b"]

    def test_untagged_documents_grouped_under_untagged(self, con):
        ingest_lines(con, [_line(id="a", text="nothing recognizable here", domain="proj1")])
        result = get_project_context(con, "proj1")
        assert result["topics"]["untagged"] == ["a"]

    def test_no_matching_domain_returns_empty_result(self, con):
        result = get_project_context(con, "does-not-exist")
        assert result["count"] == 0
        assert result["documents"] == []
        assert result["topics"] == {}
        assert result["used_model_fallback"] is False
