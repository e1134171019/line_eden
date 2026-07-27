# -*- coding: utf-8 -*-

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import ZipFile

from config import (
    CLOUD_STATE_ARTIFACT_NAME,
    CLOUD_STATE_ENCRYPTED_FILENAME,
    GITHUB_API_URL,
    GITHUB_API_VERSION,
)

UrlOpener = Callable[..., Any]


@dataclass(frozen=True)
class ArtifactRecord:
    """GitHub Actions 狀態 artifact 的必要欄位。"""

    artifact_id: int
    archive_download_url: str
    created_at: str


# 建立具版本與驗證標頭的 GitHub REST API 請求。
def _build_request(url: str, token: str) -> Request:
    return Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "ScholarshipAgent-GitHubActions",
        },
    )


# 取得同名且尚未過期的雲端狀態 artifacts。
def list_state_artifacts(
    repository: str,
    token: str,
    opener: UrlOpener = urlopen,
) -> list[ArtifactRecord]:
    query = urlencode({"name": CLOUD_STATE_ARTIFACT_NAME, "per_page": 100})
    url = f"{GITHUB_API_URL}/repos/{repository}/actions/artifacts?{query}"
    with opener(_build_request(url, token), timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return _parse_artifacts(payload.get("artifacts", []))


# 將 API 回傳資料縮成可排序與下載的安全型別。
def _parse_artifacts(items: list[dict[str, Any]]) -> list[ArtifactRecord]:
    records: list[ArtifactRecord] = []
    for item in items:
        branch = item.get("workflow_run", {}).get("head_branch")
        if item.get("expired") or branch != "main":
            continue
        records.append(
            ArtifactRecord(
                int(item["id"]),
                str(item["archive_download_url"]),
                str(item["created_at"]),
            )
        )
    return records


# 依建立時間選出最新一份有效雲端狀態。
def select_latest_artifact(records: list[ArtifactRecord]) -> ArtifactRecord:
    if not records:
        raise RuntimeError("找不到雲端狀態；請先手動執行 initialize。")
    return max(records, key=lambda item: item.created_at)


# 下載最新 artifact ZIP 到指定暫存路徑。
def download_artifact_zip(
    artifact: ArtifactRecord,
    token: str,
    destination: Path,
    opener: UrlOpener = urlopen,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with opener(_build_request(artifact.archive_download_url, token), timeout=60) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


# 只從 artifact ZIP 取出預期的加密狀態檔，拒絕其他路徑。
def extract_encrypted_state(archive_path: Path, output_path: Path) -> None:
    with ZipFile(archive_path) as archive:
        candidates = [
            name
            for name in archive.namelist()
            if Path(name).name == CLOUD_STATE_ENCRYPTED_FILENAME
        ]
        if len(candidates) != 1:
            raise RuntimeError("雲端狀態 artifact 缺少唯一的加密狀態檔。")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(candidates[0]) as source, output_path.open("wb") as target:
            shutil.copyfileobj(source, target)


# 完成列舉、選擇、下載與安全解壓縮。
def restore_latest_state(
    repository: str,
    token: str,
    output_path: Path,
    opener: UrlOpener = urlopen,
) -> ArtifactRecord:
    artifact = select_latest_artifact(list_state_artifacts(repository, token, opener))
    archive_path = output_path.with_suffix(output_path.suffix + ".zip")
    download_artifact_zip(artifact, token, archive_path, opener)
    try:
        extract_encrypted_state(archive_path, output_path)
    finally:
        archive_path.unlink(missing_ok=True)
    return artifact


# 解析 GitHub Actions 內部使用的輸出路徑。
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="還原最新 GitHub Actions 加密狀態")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


# 從 GitHub Actions 環境變數取得 repository 與 token 後還原狀態。
def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise RuntimeError("缺少 GITHUB_REPOSITORY 或 GITHUB_TOKEN。")
    artifact = restore_latest_state(repository, token, args.output)
    print(f"已還原雲端狀態 artifact：{artifact.artifact_id} ({artifact.created_at})")


if __name__ == "__main__":
    main()
