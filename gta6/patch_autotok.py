"""Apply a bounded compatibility fix to the installed upstream Autotok 2.1.0 CLI."""
from importlib.metadata import version
from pathlib import Path


def main():
    import autotok
    if version('autotok')!='2.1.0':raise RuntimeError('Review the Autotok patch for this version')
    path=Path(autotok.__file__).parent/'uploader.py'
    text=path.read_text()
    old='base = "https://www.tiktok.com/api/v1/web/project/post/"'
    new='base = "https://www.tiktok.com/tiktok/web/project/post/v1/"'
    if old not in text and new in text and '# Preserve the authorized browser' in text:
        print('Pinned Autotok compatibility patch already applied.');return
    if text.count(old)!=1:raise RuntimeError('Unexpected Autotok publish implementation')
    text=text.replace(old,new)
    anchor='        s.headers.update({"User-Agent": self.user_agent, "Accept": "application/json, text/plain, */*"})'
    if text.count(anchor)!=1:raise RuntimeError('Unexpected Autotok session implementation')
    cookies='''        # Preserve the authorized browser's stable TikTok session/device cookies.
        # Short-lived msToken is obtained afresh by the existing upload flow.
        stable = {"sid_guard", "uid_tt", "uid_tt_ss", "sid_tt", "sessionid_ss",
                  "ttwid", "passport_csrf_token", "passport_csrf_token_default",
                  "s_v_web_id", "store-idc", "store-country-code", "store-country-code-src"}
        seen = set()
        for cookie in self.account.cookies:
            name = cookie.get("name")
            domain = str(cookie.get("domain", "")).lstrip(".")
            if name not in stable or name in seen or domain not in {"tiktok.com", "www.tiktok.com"}:
                continue
            if not cookie.get("value"):
                continue
            s.cookies.set(name, str(cookie["value"]), domain=cookie["domain"], path=cookie.get("path") or "/")
            seen.add(name)
'''
    path.write_text(text.replace(anchor,cookies+anchor))
    print('Applied pinned Autotok session and publish-endpoint compatibility patch.')


if __name__=='__main__':main()
