"""共用 SSRF 防護 helper (T2-1)。

`source_type=url` 的 job 會由 **server 端**去抓使用者給的網址,內容還會被渲染進
deck、再經 `GET /jobs/{id}/draft` 讀回。原本只檢查 `http://` / `https://` 前綴 —
未設 `EDUSTUDIO_API_TOKEN` 時(預設)遠端未授權者即可讓 server 代抓內網位址,
典型如雲端 metadata endpoint `http://169.254.169.254/`。

三道防護(對應 docs/CODE_REVIEW_2026-07.md T2-1 的修法):
  1. **scheme 白名單** — 只允許 http / https(擋 file:// gopher:// 等)。
  2. **port 白名單** — 只允許 80 / 443(省略即為 scheme 預設 port)。
     擋掉「用 HTTP 打內網其他服務的 port」這類 SSRF 常見玩法。
  3. **位址過濾** — 主機名解析後,**每一個**解析結果都必須是 public IP。
     擋 loopback / RFC1918 / link-local(含 metadata) / ULA / 保留位址 /
     multicast / unspecified。

redirect 由 caller 負責:一律關掉 requests 的自動 redirect,每一跳都重新跑一次
`assert_public_url`(見 `core/adapters/url.py`)。只擋第一跳等於沒擋 —— 攻擊者
用一個 public 網址 302 到 `169.254.169.254` 就繞過了。

**自架逃生門**:設 `EDUSTUDIO_ALLOW_PRIVATE_URLS=1` 可整個關閉第 3 道,給
「我就是要讓它抓我區網內的 wiki」的自架情境用。預設關閉 = 安全預設;要放行是
使用者自己明示的決定。scheme / port 兩道不受此開關影響。

已知邊界(誠實標示,非本輪範圍):
- **DNS rebinding**:本模組是「解析後檢查」,檢查與實際連線之間 DNS 可能變臉。
  要根治得改成「解析→鎖定 IP 連線→自帶 Host header」,那要接管 requests 的
  連線層。以本專案「單人自架」的定位,先擋掉直球攻擊即可。
"""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlsplit


ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443)
_DEFAULT_PORT = {"http": 80, "https": 443}

#: 設 1/true/yes/on 即放行私有位址(自架抓區網內部資源用)。
ALLOW_PRIVATE_ENV = "EDUSTUDIO_ALLOW_PRIVATE_URLS"


class UnsafeUrlError(ValueError):
    """URL 沒通過 SSRF 防護。

    繼承 `ValueError`,讓既有把 adapter 例外當 ingest 失敗處理的 caller
    (`server/runner.py`)行為不變 —— job 標 FAILED 並帶出訊息。
    """


def allow_private() -> bool:
    """是否放行私有位址(讀環境變數,呼叫時解析以便測試 monkeypatch)。"""
    return os.environ.get(ALLOW_PRIVATE_ENV, "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """這個 IP 是否可以放行(= 真正的公網位址)。

    用 `is_global` 當主判準(它已涵蓋 loopback / private / link-local / 保留),
    再明確排掉 multicast 與 unspecified,讓意圖直接寫在程式碼裡而不是靠
    `is_global` 的實作細節。IPv4-mapped 的 IPv6(`::ffff:127.0.0.1`)先還原成
    IPv4 再判,否則會被當成一般 IPv6 位址放行。
    """
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    if ip.is_multicast or ip.is_unspecified:
        return False
    return bool(ip.is_global)


def _resolve_all(host: str) -> list[str]:
    """把主機名解析成所有 IP 字串。純 IP 字面值會原樣回來。

    解析不出來 → `UnsafeUrlError`(fail-closed:寧可擋掉也不要放行一個
    我們無法檢查的目標)。
    """
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise UnsafeUrlError(f"無法解析主機名 {host!r}: {e}") from e

    ips: list[str] = []
    for info in infos:
        addr = info[4][0]
        if addr not in ips:
            ips.append(addr)
    if not ips:
        raise UnsafeUrlError(f"主機名 {host!r} 解析不到任何位址")
    return ips


def assert_public_url(url: str) -> None:
    """驗證 `url` 可以安全地由 server 端代抓;不合格一律 `UnsafeUrlError`。

    純檢查、不發任何網路請求(除了 DNS 解析)。redirect 的每一跳都該再呼叫一次。
    """
    parts = urlsplit(url)

    scheme = (parts.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(
            f"URL 必須以 http:// 或 https:// 開頭, 得到: {url}"
        )

    host = parts.hostname
    if not host:
        raise UnsafeUrlError(f"URL 缺少主機名: {url}")

    # port: 省略 → 用 scheme 預設; 明寫 → 必須在白名單內。
    try:
        port = parts.port
    except ValueError as e:  # port 不是合法數字
        raise UnsafeUrlError(f"URL port 不合法: {url}") from e
    if port is None:
        port = _DEFAULT_PORT[scheme]
    if port not in ALLOWED_PORTS:
        raise UnsafeUrlError(
            f"只允許連 port {'/'.join(str(p) for p in ALLOWED_PORTS)}, "
            f"得到 {port}: {url}"
        )

    if allow_private():
        return

    for raw_ip in _resolve_all(host):
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError:  # 理論上不會發生; 解析不出來就 fail-closed
            raise UnsafeUrlError(f"無法解析位址 {raw_ip!r}: {url}") from None
        if not _is_public_ip(ip):
            raise UnsafeUrlError(
                f"拒絕連線到非公開位址 {ip}(主機名 {host})。"
                f"自架若確實要抓內網資源, 設 {ALLOW_PRIVATE_ENV}=1 放行。"
            )
