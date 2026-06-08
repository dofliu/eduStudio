"""U-3: legacy UI 退場 banner 注入測試。

`/ui` `/studio` build 產物在測試環境通常不存在（route 不註冊），故直接單元測注入
helper。banner 是收斂到 `/app` 前的非破壞性過渡提示。
"""
from server.main import (
    _inject_legacy_banner,
    _legacy_banner_html,
)


def test_banner_links_to_app():
    html = _legacy_banner_html(studio=False)
    assert 'href="/app/"' in html
    assert "legacy" in html


def test_studio_banner_warns_about_bypass():
    """/studio banner 額外標「繞過後端計費/審查」(U-1 漏洞警示)。"""
    studio = _legacy_banner_html(studio=True)
    ui = _legacy_banner_html(studio=False)
    assert "計費" in studio and "審查" in studio
    assert "計費" not in ui


def test_inject_after_body_tag():
    html = "<html><body class=\"x\"><div id=\"root\"></div></body></html>"
    out = _inject_legacy_banner(html, studio=False)
    # banner 在 <body ...> 之後、#root 之前
    body_close = out.find(">", out.find("<body"))
    assert out.index("/app/") > body_close
    assert out.index("/app/") < out.index('id="root"')
    # 原內容保留
    assert '<div id="root"></div>' in out


def test_inject_without_body_prepends():
    html = "<div id=\"root\"></div>"
    out = _inject_legacy_banner(html, studio=True)
    assert out.startswith("<div role=\"alert\"")
    assert html in out


def test_inject_handles_uppercase_body():
    html = "<HTML><BODY><main></main></BODY></HTML>"
    out = _inject_legacy_banner(html, studio=False)
    assert "/app/" in out
    assert "<main></main>" in out
