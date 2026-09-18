"""CAS 人工辅助登录。

规则（硬约束）：
1. 使用有界面 Playwright 打开 CAS，由本人在浏览器中输入账号和密码。
2. 程序不读取键盘输入，不把账号写入配置。
3. 登录完成后只把当前 Cookie 复制到内存中的 requests.Session；默认不落盘。
"""
from __future__ import annotations


def assisted_login(cas_base_url: str, portal_base_url: str,
                   success_url_hint: str = "notice") -> "object":
    """打开有界面浏览器等待人工登录，返回携带门户 Cookie 的内存 requests.Session。

    - 需要 `pip install requests playwright` 并执行 `playwright install chromium`。
    - 返回的 Session 只存在于内存；调用方负责不落盘。
    """
    try:
        import requests  # noqa: PLC0415
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "辅助登录需要 requests 与 playwright：pip install requests playwright "
            "&& playwright install chromium"
        ) from exc

    session = requests.Session()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        print(f"[cas_login] 已打开浏览器，请在页面中人工完成 CAS 登录：{portal_base_url}")
        page.goto(portal_base_url, wait_until="domcontentloaded")
        # 等待人工登录完成：URL 回到门户且不再指向 CAS
        page.wait_for_url(
            lambda url: cas_base_url.rstrip("/") not in url,
            timeout=0,  # 不设超时，等待人工操作
        )
        page.wait_for_load_state("domcontentloaded")
        for cookie in context.cookies():
            session.cookies.set(cookie["name"], cookie["value"],
                                domain=cookie.get("domain", ""),
                                path=cookie.get("path", "/"))
        browser.close()
    print("[cas_login] 登录会话已复制到内存 requests.Session（未落盘）")
    return session
