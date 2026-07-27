# -*- coding: utf-8 -*-

from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from config import CLOUD_STATE_ENCRYPTED_FILENAME
from src.automation.github_artifact_state import (
    ArtifactRecord,
    extract_encrypted_state,
    restore_latest_state,
    select_latest_artifact,
)


class FakeResponse(BytesIO):
    """提供 urllib response 所需的 context manager。"""

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


# 建立只含單一加密狀態檔的 artifact ZIP。
def _artifact_zip(content: bytes = b"encrypted-state") -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(CLOUD_STATE_ENCRYPTED_FILENAME, content)
    return buffer.getvalue()


# 最新 artifact 必須依 created_at 選出，而不是依 API 順序。
def test_select_latest_artifact_uses_created_at() -> None:
    older = ArtifactRecord(1, "https://example.com/1", "2026-07-27T00:00:00Z")
    newer = ArtifactRecord(2, "https://example.com/2", "2026-07-28T00:00:00Z")

    assert select_latest_artifact([newer, older]) == newer


# 沒有雲端狀態時必須 fail closed，要求先初始化。
def test_select_latest_artifact_requires_initialization() -> None:
    with pytest.raises(RuntimeError, match="initialize"):
        select_latest_artifact([])


# 解壓縮只能接受唯一且名稱正確的加密狀態檔。
def test_extract_encrypted_state_reads_expected_file(tmp_path: Path) -> None:
    archive_path = tmp_path / "artifact.zip"
    archive_path.write_bytes(_artifact_zip())
    output_path = tmp_path / CLOUD_STATE_ENCRYPTED_FILENAME

    extract_encrypted_state(archive_path, output_path)

    assert output_path.read_bytes() == b"encrypted-state"


# REST 清單應忽略過期與非 main artifact，並下載最新有效狀態。
def test_restore_latest_state_filters_and_downloads(tmp_path: Path) -> None:
    payload = {
        "artifacts": [
            {
                "id": 1,
                "expired": False,
                "created_at": "2026-07-27T00:00:00Z",
                "archive_download_url": "https://example.com/1.zip",
                "workflow_run": {"head_branch": "feature"},
            },
            {
                "id": 2,
                "expired": True,
                "created_at": "2026-07-28T00:00:00Z",
                "archive_download_url": "https://example.com/2.zip",
                "workflow_run": {"head_branch": "main"},
            },
            {
                "id": 3,
                "expired": False,
                "created_at": "2026-07-29T00:00:00Z",
                "archive_download_url": "https://example.com/3.zip",
                "workflow_run": {"head_branch": "main"},
            },
        ]
    }
    responses = iter(
        (
            FakeResponse(json.dumps(payload).encode("utf-8")),
            FakeResponse(_artifact_zip(b"latest-state")),
        )
    )

    def opener(*_: object, **__: object) -> FakeResponse:
        return next(responses)

    output_path = tmp_path / "cloud-state" / CLOUD_STATE_ENCRYPTED_FILENAME
    artifact = restore_latest_state("owner/repo", "token", output_path, opener)

    assert artifact.artifact_id == 3
    assert output_path.read_bytes() == b"latest-state"
    assert not output_path.with_suffix(output_path.suffix + ".zip").exists()
