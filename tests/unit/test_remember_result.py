import json

from slowave.core.engine import RememberResult


def test_remember_result_is_backward_compatible_int(eng):
    result = eng.remember(content="In project atlas, use PostgreSQL.", type="decision")

    assert isinstance(result, int)
    assert isinstance(result, RememberResult)
    assert int(result) == result.event_id
    assert result == result.event_id

    assert result.event_id > 0
    assert result.schema_id > 0
    assert result.created_schema is not None
    assert result.created_schema.id == result.schema_id
    assert isinstance(result.superseded_schema_ids, list)


def test_remember_result_serializes_as_int_for_existing_payloads(eng):
    result = eng.remember(content="The user prefers concise technical answers.", type="preference")

    payload = {"event_id": result, "type": "preference"}

    assert json.loads(json.dumps(payload)) == {
        "event_id": result.event_id,
        "type": "preference",
    }


def test_remember_result_as_dict_is_json_friendly(eng):
    result = eng.remember(content="Always run tests before release.", type="habit")

    assert result.as_dict() == {
        "event_id": result.event_id,
        "schema_id": result.schema_id,
        "superseded_schema_ids": result.superseded_schema_ids,
    }
