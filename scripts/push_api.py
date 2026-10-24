#!/usr/bin/env python3
"""
通过 GitHub REST API 把本地文件提交到远端仓库（绕过被代理拦截的 github.com 主域）。
适用场景：本机 git push 因网络代理拦截 github.com 而失败时，用 api.github.com 直推。
token 仅从 Git Credential Manager 内存取出，不落盘。

用法（在项目根目录执行）：
  python scripts/push_api.py                # 默认只推 data.json
  python scripts/push_api.py data.json scripts/update_dashboard.py   # 推多个文件
"""
import json, base64, subprocess, urllib.request, urllib.error, os, sys

REPO = "1191642967-spec/guaker-dashboard-v2"
BASE = "https://api.github.com"


def get_token():
    out = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n",
        capture_output=True, text=True,
    ).stdout
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    return None


def api(method, path, token, data=None):
    url = f"{BASE}/{path}"
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "workbuddy-dashboard-sync")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.data = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def push_file(token, rel_path, msg):
    local = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), rel_path)
    if not os.path.exists(local):
        print(f"  [SKIP] 本地不存在: {rel_path}")
        return False
    with open(local, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode("ascii")
    st, resp = api("GET", f"repos/{REPO}/contents/{rel_path}", token)
    sha = resp.get("sha") if (st == 200 and isinstance(resp, dict)) else None
    body = {"message": msg, "content": content_b64}
    if sha:
        body["sha"] = sha
    elif st not in (404,):
        print(f"  [GET] {rel_path} 异常 HTTP {st}: {str(resp)[:200]}")
        return False
    st, resp = api("PUT", f"repos/{REPO}/contents/{rel_path}", token, body)
    if st in (200, 201) and isinstance(resp, dict):
        print(f"  [OK] {rel_path} -> {resp.get('commit', {}).get('html_url', '')}")
        return True
    print(f"  [FAIL] {rel_path} HTTP {st}: {str(resp)[:300]}")
    return False


def main():
    files = sys.argv[1:] or ["data.json"]
    token = get_token()
    if not token:
        print("未取到 GitHub token（请在 Windows 凭据管理器保存 github.com 凭据），推送中止。")
        sys.exit(2)
    st, resp = api("GET", f"repos/{REPO}", token)
    if st != 200:
        print(f"token 校验失败 HTTP {st}: {str(resp)[:200]}")
        sys.exit(3)
    msg = "Auto update dashboard via API: " + (
        files[0] if len(files) == 1 else f"{len(files)} files"
    )
    ok = all(push_file(token, p, msg) for p in files)
    print("RESULT:", "ALL_OK" if ok else "PARTIAL_FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
