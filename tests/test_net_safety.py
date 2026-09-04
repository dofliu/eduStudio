"""T2-1 SSRF 防護測試 — `core/net_safety.py` + `core/adapters/url.py` 的每跳重驗。

全程不打真網路:DNS 解析 (`socket.getaddrinfo`) 與 `requests.get` 都 monkeypatch
掉,對齊硬規則 #2 offline-first。
"""
from __future__ import annotations

import socket

import pytest

from core import net_safety
from core.net_safety import UnsafeUrlError, assert_public_url


# ---------- helpers ----------

def fake_resolver(mapping: dict[str, list[str]]):
    """做一個假的 getaddrinfo:主機名 → IP 清單。未列出的主機名 → gaierror。

    IP 字面值原樣回傳(真的 `getaddrinfo` 就是這行為),否則測轉址到
    `169.254.169.254` 時會誤判成「解析失敗」而不是「位址被擋」。
    """
    import ipaddress

    def _getaddrinfo(host, port, *args, **kwargs):
        try:
            ipaddress.ip_address(host)
            ips = [host]
        except ValueError:
            if host not in mapping:
                raise socket.gaierror(f"unknown host {host}")
            ips = mapping[host]
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 0))
            for ip in ips
        ]
    return _getaddrinfo


@pytest.fixture
def public_dns(monkeypatch):
    """example.com → 一個公網 IP;evil.internal → metadata IP。"""
    monkeypatch.setattr(socket, "getaddrinfo", fake_resolver({
        "example.com": ["93.184.216.34"],
        "evil.internal": ["169.254.169.254"],
        "mixed.example": ["93.184.216.34", "10.0.0.5"],
    }))
    monkeypatch.delenv(net_safety.ALLOW_PRIVATE_ENV, raising=False)


# ---------- scheme / port ----------

class TestSchemeAndPort:
    @pytest.mark.parametrize("url", [
        "file:///etc/passwd",
        "gopher://example.com/",
        "ftp://example.com/x",
        "//example.com/x",
    ])
    def test_non_http_scheme_rejected(self, url, public_dns):
        with pytest.raises(UnsafeUrlError):
            assert_public_url(url)

    def test_missing_host_rejected(self, public_dns):
        with pytest.raises(UnsafeUrlError, match="缺少主機名"):
            assert_public_url("http:///just/a/path")

    @pytest.mark.parametrize("port", [22, 3306, 6379, 8000, 11434])
    def test_non_web_port_rejected(self, port, public_dns):
        with pytest.raises(UnsafeUrlError, match="只允許連 port"):
            assert_public_url(f"http://example.com:{port}/x")

    @pytest.mark.parametrize("url", [
        "http://example.com/x",
        "https://example.com/x",
        "http://example.com:80/x",
        "https://example.com:443/x",
    ])
    def test_default_and_web_ports_allowed(self, url, public_dns):
        assert_public_url(url)  # 不應 raise

    def test_scheme_is_case_insensitive(self, public_dns):
        assert_public_url("HTTPS://example.com/x")


# ---------- 位址過濾 ----------

class TestAddressFiltering:
    @pytest.mark.parametrize("ip", [
        "127.0.0.1",        # loopback
        "10.0.0.1",         # RFC1918
        "172.16.5.4",       # RFC1918
        "192.168.1.1",      # RFC1918
        "169.254.169.254",  # link-local / 雲端 metadata
        "0.0.0.0",          # unspecified
        "224.0.0.1",        # multicast
        "::1",              # IPv6 loopback
        "fd00::1",          # IPv6 ULA
        "fe80::1",          # IPv6 link-local
    ])
    def test_private_ip_literals_rejected(self, ip, monkeypatch):
        monkeypatch.delenv(net_safety.ALLOW_PRIVATE_ENV, raising=False)
        host = f"[{ip}]" if ":" in ip else ip
        with pytest.raises(UnsafeUrlError, match="非公開位址"):
            assert_public_url(f"http://{host}/x")

    def test_ipv4_mapped_ipv6_loopback_rejected(self, monkeypatch):
        """`::ffff:127.0.0.1` 還原成 IPv4 才判, 否則會被當一般 IPv6 放行。"""
        monkeypatch.delenv(net_safety.ALLOW_PRIVATE_ENV, raising=False)
        with pytest.raises(UnsafeUrlError, match="非公開位址"):
            assert_public_url("http://[::ffff:127.0.0.1]/x")

    def test_public_ip_literal_allowed(self, monkeypatch):
        monkeypatch.delenv(net_safety.ALLOW_PRIVATE_ENV, raising=False)
        assert_public_url("http://93.184.216.34/x")

    def test_hostname_resolving_to_metadata_rejected(self, public_dns):
        """DNS 指到 metadata IP 的主機名也要擋 — 不能只看字面。"""
        with pytest.raises(UnsafeUrlError, match="非公開位址"):
            assert_public_url("http://evil.internal/latest/meta-data/")

    def test_any_private_result_rejects_whole_host(self, public_dns):
        """一個主機名解析出多個 IP 時, 只要有一個是私有就整個擋(不能挑好的用)。"""
        with pytest.raises(UnsafeUrlError, match="非公開位址"):
            assert_public_url("http://mixed.example/x")

    def test_unresolvable_host_is_fail_closed(self, public_dns):
        with pytest.raises(UnsafeUrlError, match="無法解析主機名"):
            assert_public_url("http://nope.invalid/x")


class TestAllowPrivateEscapeHatch:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_opt_in_allows_private(self, value, monkeypatch, public_dns):
        monkeypatch.setenv(net_safety.ALLOW_PRIVATE_ENV, value)
        assert_public_url("http://192.168.1.10/wiki")

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
    def test_other_values_keep_blocking(self, value, monkeypatch, public_dns):
        monkeypatch.setenv(net_safety.ALLOW_PRIVATE_ENV, value)
        with pytest.raises(UnsafeUrlError):
            assert_public_url("http://192.168.1.10/wiki")

    def test_opt_in_does_not_bypass_scheme_or_port(self, monkeypatch, public_dns):
        """逃生門只放行位址, 不放行 scheme / port —— 免得變成全開。"""
        monkeypatch.setenv(net_safety.ALLOW_PRIVATE_ENV, "1")
        with pytest.raises(UnsafeUrlError):
            assert_public_url("file:///etc/passwd")
        with pytest.raises(UnsafeUrlError, match="只允許連 port"):
            assert_public_url("http://192.168.1.10:6379/")


# ---------- adapter 端:每一跳都要重驗 ----------

class _FakeResp:
    def __init__(self, *, status_code=200, text="", location=None):
        self.status_code = status_code
        self.text = text
        self.headers = {"Location": location} if location else {}

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308)

    is_permanent_redirect = is_redirect

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def fake_requests(monkeypatch):
    """攔 requests.get,記錄實際被請求的 URL,回傳預先排好的 response。"""
    import requests

    state = {"queue": [], "requested": []}

    def _get(url, **kwargs):
        state["requested"].append(url)
        assert kwargs.get("allow_redirects") is False, "必須關掉自動 redirect"
        if not state["queue"]:
            raise AssertionError(f"沒有預備 response 給 {url}")
        return state["queue"].pop(0)

    monkeypatch.setattr(requests, "get", _get)
    return state


HTML = "<html><head><title>T</title></head><body><article>內容</article></body></html>"


class TestScanUrlRedirectGuard:
    def test_redirect_to_metadata_is_blocked(self, fake_requests, public_dns):
        """public 網址 302 → metadata:第二跳必須被擋, 且**不會**真的送出請求。"""
        from core.adapters.url import scan_url

        fake_requests["queue"] = [
            _FakeResp(status_code=302, location="http://169.254.169.254/latest/"),
            _FakeResp(text=HTML),   # 若防護失效就會用到這個 → 測試會抓到
        ]
        with pytest.raises(UnsafeUrlError, match="非公開位址"):
            scan_url("http://example.com/article")

        assert fake_requests["requested"] == ["http://example.com/article"], (
            "第二跳不該真的發出去"
        )

    def test_relative_redirect_resolved_against_current_url(self, fake_requests, public_dns):
        from core.adapters.url import scan_url

        fake_requests["queue"] = [
            _FakeResp(status_code=301, location="/moved"),
            _FakeResp(text=HTML),
        ]
        raw = scan_url("http://example.com/article")
        assert fake_requests["requested"] == [
            "http://example.com/article",
            "http://example.com/moved",
        ]
        assert raw["stats"]["final_url"] == "http://example.com/moved"
        # 原始 url 欄位維持使用者輸入的那個(向後相容)
        assert raw["url"] == "http://example.com/article"

    def test_happy_path_no_redirect(self, fake_requests, public_dns):
        from core.adapters.url import scan_url

        fake_requests["queue"] = [_FakeResp(text=HTML)]
        raw = scan_url("http://example.com/article")
        assert raw["source_kind"] == "url"
        assert raw["title"] == "T"
        assert "內容" in raw["content"]
        assert raw["stats"]["final_url"] == "http://example.com/article"

    def test_redirect_loop_gives_up(self, fake_requests, public_dns):
        from core.adapters.url import scan_url

        fake_requests["queue"] = [
            _FakeResp(status_code=302, location="http://example.com/loop")
            for _ in range(10)
        ]
        with pytest.raises(UnsafeUrlError, match="轉址超過"):
            scan_url("http://example.com/loop", max_redirects=3)
        assert len(fake_requests["requested"]) == 4  # 首次 + 3 跳

    def test_redirect_without_location_errors(self, fake_requests, public_dns):
        from core.adapters.url import scan_url

        fake_requests["queue"] = [_FakeResp(status_code=302)]
        with pytest.raises(ValueError, match="沒有 Location"):
            scan_url("http://example.com/article")

    def test_blocked_before_any_request(self, fake_requests, public_dns):
        """一開始就給內網位址 → 連第一個請求都不該送出。"""
        from core.adapters.url import scan_url

        with pytest.raises(UnsafeUrlError):
            scan_url("http://169.254.169.254/latest/meta-data/")
        assert fake_requests["requested"] == []


def test_unsafe_url_error_is_value_error():
    """caller (server/runner.py) 把 adapter 例外當 ingest 失敗處理, 型別不能變窄。"""
    assert issubclass(UnsafeUrlError, ValueError)
