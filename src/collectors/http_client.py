# -*- coding: utf-8 -*-

import ssl
from types import TracebackType
from urllib.parse import urlparse

import httpx

LEGACY_CERTIFICATE_DOMAINS = frozenset({
    "www.edu.tw",
    "www.scholarship.moe.gov.tw",
    "scholarship.moe.gov.tw",
})
_CERTIFICATE_ERROR_MARKERS = (
    "certificate_verify_failed",
    "missing subject key identifier",
)


# 建立仍保留 CA 與 hostname 驗證的舊憑證相容 context。
def build_legacy_compatible_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise RuntimeError("舊憑證相容模式不得停用 hostname 或 CA 驗證")
    return context


class SafeHttpClient:
    """先嚴格驗證，僅對允許網域的特定憑證錯誤安全重試。"""

    def __init__(self, timeout_seconds: float, user_agent: str) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self._strict_client = self._build_client(True)
        self._legacy_client: httpx.Client | None = None
        self.fallback_hosts: set[str] = set()

    # 建立共用連線池，避免每一頁重新建立 TCP/TLS 連線。
    def _build_client(self, verify: bool | ssl.SSLContext) -> httpx.Client:
        return httpx.Client(
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout_seconds,
            follow_redirects=True,
            verify=verify,
        )

    # 下載 UTF-8/網站宣告編碼的 HTML 文字。
    def get_text(self, url: str) -> str:
        try:
            return self._get(self._strict_client, url)
        except httpx.TransportError as error:
            if not self._can_use_legacy_context(url, error):
                raise
            host = urlparse(url).hostname or ""
            self.fallback_hosts.add(host)
            if self._legacy_client is None:
                self._legacy_client = self._build_client(
                    build_legacy_compatible_ssl_context()
                )
            return self._get(self._legacy_client, url)

    # 執行單一 GET 並確認 HTTP 狀態。
    def _get(self, client: httpx.Client, url: str) -> str:
        response = client.get(url)
        response.raise_for_status()
        return response.text

    # 僅允許已知網域及明確 X.509 格式錯誤進入相容模式。
    def _can_use_legacy_context(self, url: str, error: Exception) -> bool:
        host = urlparse(url).hostname or ""
        message = " ".join(str(error).lower().split())
        return host in LEGACY_CERTIFICATE_DOMAINS and all(
            marker in message for marker in _CERTIFICATE_ERROR_MARKERS
        )

    # 關閉連線池。
    def close(self) -> None:
        self._strict_client.close()
        if self._legacy_client is not None:
            self._legacy_client.close()

    def __enter__(self) -> "SafeHttpClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
