# -*- coding: utf-8 -*-

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
import ssl
import time
from types import TracebackType
from urllib.parse import urlparse

import httpx

LEGACY_CERTIFICATE_DOMAINS = frozenset({
    "www.edu.tw",
    "www.scholarship.moe.gov.tw",
    "scholarship.moe.gov.tw",
    "xinzhuangawards.ntpc.gov.tw",
})
_CERTIFICATE_ERROR_MARKERS = (
    "certificate_verify_failed",
    "missing subject key identifier",
)
_TRANSIENT_TIMEOUT_ATTEMPTS = 3
_TRANSIENT_TIMEOUT_BACKOFF_SECONDS = (0.5, 1.0)


# 建立仍保留 CA 與 hostname 驗證的舊憑證相容 context。
def build_legacy_compatible_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise RuntimeError("舊憑證相容模式不得停用 hostname 或 CA 驗證")
    return context


# 確認錯誤是否為可由非 strict X.509 context 相容的舊憑證格式。
def _is_legacy_certificate_error(error: Exception) -> bool:
    message = " ".join(str(error).lower().split())
    return all(marker in message for marker in _CERTIFICATE_ERROR_MARKERS)


class SafeHttpClient:
    """先嚴格驗證；timeout 有限重試，舊憑證僅允許安全相容模式。"""

    def __init__(self, timeout_seconds: float, user_agent: str) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self._strict_client = self._build_client(True)
        self._legacy_client: httpx.Client | None = None
        self.fallback_hosts: set[str] = set()
        self.timeout_retry_hosts: set[str] = set()

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
            return self._get_with_timeout_retry(self._strict_client, url)
        except httpx.TransportError as error:
            if not self._can_use_legacy_context(url, error):
                raise
            return self._get_with_timeout_retry(self._legacy_client_for(url), url)

    # timeout 通常是來源暫時性抖動；只重試固定次數，不重試憑證、DNS 或 HTTP 狀態。
    def _get_with_timeout_retry(self, client: httpx.Client, url: str) -> str:
        for attempt in range(_TRANSIENT_TIMEOUT_ATTEMPTS):
            try:
                return self._get(client, url)
            except httpx.TimeoutException:
                if attempt + 1 >= _TRANSIENT_TIMEOUT_ATTEMPTS:
                    raise
                host = urlparse(url).hostname or ""
                self.timeout_retry_hosts.add(host)
                time.sleep(_TRANSIENT_TIMEOUT_BACKOFF_SECONDS[attempt])
        raise RuntimeError("timeout retry flow ended unexpectedly")

    # 以串流方式下載二進位正文或附件，並回報是否使用相容模式。
    @contextmanager
    def stream(self, url: str) -> Iterator[tuple[httpx.Response, bool]]:
        manager: AbstractContextManager[httpx.Response]
        fallback = False
        manager = self._strict_client.stream("GET", url)
        try:
            response = manager.__enter__()
        except httpx.TransportError as error:
            if not self._can_use_legacy_context(url, error):
                raise
            manager = self._legacy_client_for(url).stream("GET", url)
            response = manager.__enter__()
            fallback = True
        try:
            yield response, fallback
        finally:
            manager.__exit__(None, None, None)

    # 執行單一 GET 並確認 HTTP 狀態。
    def _get(self, client: httpx.Client, url: str) -> str:
        response = client.get(url)
        response.raise_for_status()
        return response.text

    # 僅允許白名單網域進入清單來源的相容模式。
    def _can_use_legacy_context(self, url: str, error: Exception) -> bool:
        host = urlparse(url).hostname or ""
        return host in LEGACY_CERTIFICATE_DOMAINS and _is_legacy_certificate_error(error)

    # 延遲建立相容 client 並記錄實際使用網域。
    def _legacy_client_for(self, url: str) -> httpx.Client:
        host = urlparse(url).hostname or ""
        self.fallback_hosts.add(host)
        if self._legacy_client is None:
            self._legacy_client = self._build_client(
                build_legacy_compatible_ssl_context()
            )
        return self._legacy_client

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


class DetailSafeHttpClient(SafeHttpClient):
    """公告內頁版：任意 HTTPS 網域僅遇到指定舊憑證格式時安全重試。"""

    # 內頁來源不可預先枚舉，因此只限制 HTTPS 與精確的 X.509 錯誤類型。
    def _can_use_legacy_context(self, url: str, error: Exception) -> bool:
        return urlparse(url).scheme == "https" and _is_legacy_certificate_error(error)
