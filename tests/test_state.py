from __future__ import annotations

from pathlib import Path

import pytest

from forge_antigravity.state import ExportState, load_state, save_state


def _payload(tmp_path: Path) -> dict[str, str]:
    return {"artifactDirectoryPath": str(tmp_path / "artifact")}


def test_state_round_trip_is_scoped_to_the_conversation_artifact(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    state = ExportState(last_exported_step=12, history_start_step=4)

    save_state(payload, state)

    assert load_state(payload) == state
    path = tmp_path / "artifact" / ".forge-antigravity" / "state.json"
    assert path.is_file()
    assert not list(path.parent.glob("*.tmp"))


def test_state_path_can_be_derived_from_the_transcript(tmp_path: Path) -> None:
    transcript = tmp_path / "artifact" / ".system_generated" / "logs" / "transcript.jsonl"
    payload = {"transcriptPath": str(transcript)}

    save_state(payload, ExportState(last_exported_step=2, history_start_step=0))

    assert load_state(payload).last_exported_step == 2


def test_missing_invalid_and_unusable_state_fall_back_safely(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    assert load_state(payload) == ExportState()
    assert load_state({}) == ExportState()

    path = tmp_path / "artifact" / ".forge-antigravity" / "state.json"
    path.parent.mkdir(parents=True)
    for content in ("not json", "[]", '{"last_exported_step":-2,"history_start_step":0}'):
        path.write_text(content, encoding="utf-8")
        assert load_state(payload) == ExportState(corrupted=True)

    save_state({}, ExportState(last_exported_step=1, history_start_step=0))


def test_content_exclusion_mark_round_trips_and_defaults_for_older_state(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    state = ExportState(
        last_exported_step=8,
        history_start_step=0,
        content_excluded_through_step=4,
    )
    save_state(payload, state)

    path = tmp_path / "artifact" / ".forge-antigravity" / "state.json"
    assert load_state(payload) == state
    assert "corrupted" not in path.read_text(encoding="utf-8")

    path.write_text('{"last_exported_step":8,"history_start_step":0}', encoding="utf-8")
    assert load_state(payload) == ExportState(
        last_exported_step=8,
        history_start_step=0,
        content_excluded_through_step=8,
    )


@pytest.mark.parametrize("mark", ['"4"', "1.5", "true", "-2", "null"])
def test_invalid_content_exclusion_mark_is_corrupted_but_keeps_the_cursor(
    tmp_path: Path, mark: str
) -> None:
    payload = _payload(tmp_path)
    path = tmp_path / "artifact" / ".forge-antigravity" / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        f'{{"last_exported_step":8,"history_start_step":0,"content_excluded_through_step":{mark}}}',
        encoding="utf-8",
    )

    assert load_state(payload) == ExportState(
        last_exported_step=8,
        history_start_step=0,
        corrupted=True,
    )
