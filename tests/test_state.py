from __future__ import annotations

from pathlib import Path

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
        assert load_state(payload) == ExportState()

    save_state({}, ExportState(last_exported_step=1, history_start_step=0))
