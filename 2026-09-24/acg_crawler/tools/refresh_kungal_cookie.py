"""刷新鲲Galgame(kungal.com) 会话 cookie

kungal 的账号体系是 NextMoe·未萌 OAuth，站点自己没有账密登录接口，
所以只能用真实浏览器登一次，再把 kungal_session 写回 .env。

需要 .env 里有：
    NEXTMOE_NAME=账号
    NEXTMOE_PASSWORD=密码

用法：
    python tools/refresh_kungal_cookie.py

会话 cookie 约 90 天滑动有效：只要期间爬过（哪怕一次）就会自动续期，
连续 90 天没动才会失效。失效时爬取日志会抛 CookieExpiredError，跑一次本脚本即可。
"""
import os
import re
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

# agent-browser 原生二进制（npm shim 在部分 bash 环境里会因缺 coreutils 而失效）
AB_CANDIDATES = [
    Path(r"C:/Users/Administrator/AppData/Roaming/npm/node_modules/agent-browser/bin/agent-browser-win32-x64.exe"),
    Path(os.environ.get("APPDATA", "")) / "npm/node_modules/agent-browser/bin/agent-browser-win32-x64.exe",
]

KUNGAL_GALGAME_URL = "https://www.kungal.com/galgame/2754"


def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def find_ab():
    for p in AB_CANDIDATES:
        if p and Path(p).exists():
            return str(p)
    raise SystemExit("找不到 agent-browser 原生二进制；请先 npm i -g agent-browser")


def run_ab(ab, *args, timeout=120, capture=False):
    """执行一条 agent-browser 命令（daemon 会话在本进程内保持）

    注意：不能把 stdout 接成管道 —— 浏览器 daemon 会继承这个句柄并一直持有，
    subprocess 就永远等不到 EOF。所以默认丢弃输出，需要输出时写到临时文件再读。
    """
    if not capture:
        subprocess.run([ab, *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=timeout)
        return ""
    out_file = BASE_DIR / "_ab_out.tmp"
    with open(out_file, "w", encoding="utf-8", errors="ignore") as fh:
        subprocess.run([ab, *args], stdout=fh, stderr=subprocess.DEVNULL, timeout=timeout)
    text = out_file.read_text(encoding="utf-8", errors="ignore")
    out_file.unlink(missing_ok=True)
    return text


def main():
    env = load_env()
    name = env.get("NEXTMOE_NAME") or os.environ.get("NEXTMOE_NAME", "")
    password = env.get("NEXTMOE_PASSWORD") or os.environ.get("NEXTMOE_PASSWORD", "")
    if not name or not password:
        raise SystemExit("请在 .env 里配置 NEXTMOE_NAME / NEXTMOE_PASSWORD 后重试")

    ab = find_ab()
    print("[1/5] 启动浏览器并打开 kungal …")
    run_ab(ab, "close", "--all", timeout=60)
    run_ab(ab, "wait", "2500")
    run_ab(ab, "open", KUNGAL_GALGAME_URL, timeout=120)
    run_ab(ab, "wait", "5000")

    print("[2/5] 打开发登录弹窗 → 跳转 NextMoe 授权页 …")
    run_ab(ab, "find", "text", "登录", "click")
    run_ab(ab, "wait", "2500")
    run_ab(ab, "click", "[role=dialog] button[aria-label='登录']", timeout=120)
    run_ab(ab, "wait", "7000")
    run_ab(ab, "find", "text", "登录后继续", "click", timeout=120)
    run_ab(ab, "wait", "7000")

    print("[3/5] 填账号密码并登录 …")
    run_ab(ab, "fill", "input[type=text]", name)
    run_ab(ab, "fill", "input[type=password]", password)
    run_ab(ab, "click", "button[type=submit][aria-label='登录']")
    run_ab(ab, "wait", "12000")

    print("[4/5] 读取会话 cookie …")
    cookies = run_ab(ab, "cookies", "get", timeout=60, capture=True)
    run_ab(ab, "close", "--all", timeout=60)

    m = re.search(r"(kungal_session=[0-9a-f]+)", cookies)
    if not m:
        raise SystemExit(f"没拿到 kungal_session，登录可能失败。原始输出：\n{cookies[:500]}")
    cookie = m.group(1)

    print("[5/5] 写回 .env …")
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    out, replaced = [], False
    for line in lines:
        if line.strip().startswith("KUNGAL_COOKIE="):
            out.append("KUNGAL_COOKIE=" + cookie)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append("# 鲲Galgame(kungal.com) 登录会话cookie（约90天滑动有效）")
        out.append("KUNGAL_COOKIE=" + cookie)
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("完成：KUNGAL_COOKIE 已更新（值不打印到日志）")


if __name__ == "__main__":
    sys.exit(main())
