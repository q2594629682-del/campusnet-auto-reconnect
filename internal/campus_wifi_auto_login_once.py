# campus_wifi_auto_login_once.py
# Campus Wi-Fi: reconnect and complete captive-portal login, then exit
#
# 省资源版逻辑：
#   0. Check whether the current network is usable.
#   1. If needed, connect to the configured campus Wi-Fi.
#   2. If Windows has no saved profile, create an open Wi-Fi profile.
#   3. After connecting, check whether captive-portal authentication succeeded.
#   4. If authentication is needed, fill credentials from environment variables.
#   5. 最多尝试 3 轮，然后退出，等待任务计划程序下次启动。
#
# 推荐运行方式：
#   Run run_manual.bat for an immediate reconnect.
#
# Keep credentials in local environment variables; never commit them:
#   setx CAMPUS_WIFI_USER your_account
#   setx CAMPUS_WIFI_PASS your_password
#
# setx 后要重新打开 Anaconda Prompt。

from __future__ import annotations

import os
import re
import sys
import html
import time
import socket
import logging
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path


# ===================== 主要配置 =====================

SSID = os.getenv("CAMPUS_WIFI_SSID", "YOUR_CAMPUS_WIFI")
PORTAL_URL = os.getenv("CAMPUS_WIFI_PORTAL_URL", "").strip()

USER_ENV = "CAMPUS_WIFI_USER"
PASS_ENV = "CAMPUS_WIFI_PASS"

# Whether to force the target Wi-Fi when another network already works.
# 推荐 False：只要当前网络可用，就直接退出，最省资源。
REQUIRE_TARGET_WIFI_WHEN_INTERNET_OK = False

# 如果账号/密码框自动识别失败，再填这两个。
# 例：USER_SELECTOR = 'input[name="DDDDD"]'
# 例：PASS_SELECTOR = 'input[name="upass"]'
USER_SELECTOR = ""
PASS_SELECTOR = ""

# 如果登录按钮自动识别失败，再填这个。
# 例：BUTTON_SELECTOR = 'input[type="submit"]'
BUTTON_SELECTOR = ""

LOGIN_TEXTS = [
    "登录",
    "登陆",
    "连接",
    "上网",
    "认证",
    "进入",
    "Connect",
    "Login",
    "Sign in",
]

# 一般留 None。若有多个无线网卡，可运行 netsh wlan show interfaces 看名称后填 "Wi-Fi"。
INTERFACE_NAME = None

# 每次被任务计划程序唤醒后，最多尝试几轮。
MAX_ATTEMPTS = 3

# 每轮失败后的等待时间。
ATTEMPT_WAIT_SECONDS = 15

# 连上 Wi-Fi 后等几秒再打开认证页。
PORTAL_AFTER_WIFI_DELAY_SECONDS = 3

# 后台运行，不弹浏览器。
# 如果之后需要调试自动填表，再临时改成 True。
SHOW_BROWSER = False

# 用于判断“当前是否已经能正常上网”。
# 校园网未认证时，普通 HTTP 请求通常会被重定向到认证页。
CHECK_URL = "http://www.msftconnecttest.com/connecttest.txt"
CHECK_KEYWORD = "Microsoft Connect Test"

# =====================================================


LOG_DIR = Path.home() / "campus_wifi_auto_login_logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "keeper_once.log"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)


def run_cmd(args: list[str], timeout: int = 25) -> tuple[int, str]:
    # pythonw hides its own console, but console programs such as netsh can
    # still create a new window unless the child process is hidden as well.
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        p = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
            shell=False,
            creationflags=creationflags,
        )
        return p.returncode, (p.stdout or "") + "\n" + (p.stderr or "")
    except UnicodeDecodeError:
        p = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="ignore",
            timeout=timeout,
            shell=False,
            creationflags=creationflags,
        )
        return p.returncode, (p.stdout or "") + "\n" + (p.stderr or "")
    except Exception as e:
        return 999, str(e)


def get_wlan_info() -> dict[str, str]:
    code, out = run_cmd(["netsh", "wlan", "show", "interfaces"])
    info: dict[str, str] = {}

    if code != 0:
        logging.warning("读取 Wi-Fi 接口失败：%s", out.strip())
        return info

    for raw in out.splitlines():
        line = raw.strip()
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()

        if key in ("name", "名称"):
            info["name"] = value
        elif key in ("state", "状态"):
            info["state"] = value
        elif key == "ssid":
            info["ssid"] = value
        elif key in ("signal", "信号"):
            info["signal"] = value

    return info



def any_network_connected() -> bool:
    """
    检测任意网络接口是否已经连接。
    注意：这里不判断是否能访问互联网。
    For example, an active phone hotspot is left alone during automatic runs.
    """
    code, out = run_cmd(["netsh", "interface", "show", "interface"], timeout=15)

    if code == 0:
        for line in out.splitlines():
            low = line.lower()
            if (re.search(r"\bconnected\b", low) and "not connected" not in low) or "已连接" in line:
                logging.info("An existing network is connected; leaving it unchanged.")
                return True

    # 兼容部分中文 Windows 输出
    info = get_wlan_info()
    state = info.get("state", "")
    if "已连接" in state or state.strip().lower() == "connected":
        logging.info("An existing Wi-Fi connection is active; leaving it unchanged.")
        return True

    return False


def wifi_profile_exists() -> bool:
    code, out = run_cmd(["netsh", "wlan", "show", "profiles"])
    if code != 0:
        logging.warning("查看 Wi-Fi 配置文件失败：%s", out.strip())
        return False

    exists = SSID in out
    logging.info("Wi-Fi 配置文件 %s：%s", SSID, "存在" if exists else "不存在")
    return exists


def add_open_wifi_profile() -> bool:
    """
    Create an open Wi-Fi profile for networks using captive-portal login.
    如果学校 Wi-Fi 本身还需要 WPA 密码或企业认证，这个方法不适用。
    """
    ssid_escaped = html.escape(SSID, quote=True)

    xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid_escaped}</name>
    <SSIDConfig>
        <SSID>
            <name>{ssid_escaped}</name>
        </SSID>
        <nonBroadcast>false</nonBroadcast>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>open</authentication>
                <encryption>none</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
        </security>
    </MSM>
</WLANProfile>
"""

    xml_path = LOG_DIR / f"{SSID}_open_wifi_profile.xml"
    xml_path.write_text(xml, encoding="utf-8")

    cmd = ["netsh", "wlan", "add", "profile", f"filename={xml_path}", "user=current"]
    if INTERFACE_NAME:
        cmd.append(f"interface={INTERFACE_NAME}")

    logging.info("正在添加开放 Wi-Fi 配置文件：%s", xml_path)
    code, out = run_cmd(cmd, timeout=30)
    logging.info("添加 Wi-Fi 配置返回：code=%s, out=%s", code, out.strip())

    return code == 0 or "已添加" in out or "is added" in out.lower()


def ensure_wifi_profile() -> bool:
    if wifi_profile_exists():
        return True

    logging.warning("Target Wi-Fi profile not found; trying to create an open profile.")
    ok = add_open_wifi_profile()

    if not ok:
        logging.error("Could not create Wi-Fi profile. Connect to the target network once manually.")
        return False

    time.sleep(1)
    return wifi_profile_exists()


def is_connected_to_target_wifi() -> bool:
    info = get_wlan_info()
    state = info.get("state", "").lower()
    current_ssid = info.get("ssid", "")

    state_ok = (
        "connected" in state
        or "已连接" in state
        or "已連線" in state
    )

    ok = state_ok and current_ssid == SSID

    if ok:
        logging.info("已连接目标 Wi-Fi：%s，信号：%s", SSID, info.get("signal", "未知"))
    else:
        logging.info(
            "未连接目标 Wi-Fi：state=%s, current_ssid=%s, target=%s",
            info.get("state", "未知"),
            current_ssid or "无",
            SSID,
        )

    return ok


def scan_target_visible() -> bool:
    code, out = run_cmd(["netsh", "wlan", "show", "networks", "mode=bssid"], timeout=30)
    if code != 0:
        logging.warning("扫描 Wi-Fi 失败：%s", out.strip())
        return False

    visible = SSID in out
    logging.info("扫描目标 Wi-Fi：%s -> %s", SSID, "可见" if visible else "不可见")
    return visible


def connect_wifi() -> bool:
    if is_connected_to_target_wifi():
        return True

    if not ensure_wifi_profile():
        return False

    if not scan_target_visible():
        logging.warning("当前扫描不到 %s，可能不在校园网覆盖范围内。", SSID)
        return False

    cmd = ["netsh", "wlan", "connect", f"name={SSID}", f"ssid={SSID}"]

    if INTERFACE_NAME:
        cmd.append(f"interface={INTERFACE_NAME}")

    logging.info("执行 Wi-Fi 连接命令：%s", " ".join(cmd))
    code, out = run_cmd(cmd, timeout=30)
    logging.info("连接命令返回：code=%s, out=%s", code, out.strip())

    for _ in range(15):
        time.sleep(2)
        if is_connected_to_target_wifi():
            return True

    return False


def get_current_ipv4_for_portal() -> str | None:
    try:
        host = urllib.parse.urlparse(PORTAL_URL).hostname
        if not host:
            logging.error("Set CAMPUS_WIFI_PORTAL_URL to your campus captive-portal URL.")
            return None
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(3)
            s.connect((host, 80))
            ip = s.getsockname()[0]
        logging.info("当前本机 IPv4：%s", ip)
        return ip
    except Exception as e:
        logging.warning("获取当前 IPv4 失败：%s", e)
        return None


def build_portal_url() -> str:
    parsed = urllib.parse.urlparse(PORTAL_URL)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    if "wlanuserip" not in query:
        return PORTAL_URL

    ip = get_current_ipv4_for_portal()
    if not ip:
        return PORTAL_URL

    query["wlanuserip"] = [ip]

    new_query = urllib.parse.urlencode(query, doseq=True)
    new_url = urllib.parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )

    logging.info("认证页地址：%s", new_url)
    return new_url


def get_local_account() -> tuple[str | None, str | None]:
    user = os.getenv(USER_ENV)
    password = os.getenv(PASS_ENV)

    if not user or not password:
        logging.warning(
            "没有读取到账号密码环境变量。请执行：setx %s 你的账号；setx %s 你的密码",
            USER_ENV,
            PASS_ENV,
        )
        return None, None

    return user, password


def internet_auth_ok() -> bool:
    """
    判断当前是否已经能正常上网。
    已经能上网时，脚本会直接退出，不再打开校园认证页。
    未认证时，校园网通常会把普通 HTTP 请求重定向到认证页。
    """
    try:
        req = urllib.request.Request(
            CHECK_URL,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read(200).decode("utf-8", errors="ignore")
            ok = CHECK_KEYWORD in body
            logging.info("网络检测：%s，url=%s，body=%s", "可正常上网" if ok else "未认证/被重定向", resp.url, body[:80])
            return ok
    except Exception as e:
        logging.info("网络检测失败，按未认证处理：%s", e)
        return False


def basic_portal_get(url: str) -> None:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read(300).decode("utf-8", errors="ignore")
            logging.info("访问认证页完成：status=%s, body_head=%s", resp.status, body)
    except Exception as e:
        logging.warning("访问认证页失败：%s", e)


def fill_first_visible(page, selectors: list[str], value: str, label: str) -> bool:
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0 and loc.is_visible(timeout=2000):
                loc.fill(value, timeout=5000)
                logging.info("已填写 %s：selector=%s", label, selector)
                return True
        except Exception as e:
            logging.info("填写 %s 失败：selector=%s, err=%s", label, selector, e)
    return False


def click_login_button(page) -> bool:
    if BUTTON_SELECTOR:
        try:
            loc = page.locator(BUTTON_SELECTOR).first
            if loc.count() > 0 and loc.is_visible(timeout=3000):
                loc.click(timeout=5000)
                logging.info("已点击指定按钮：%s", BUTTON_SELECTOR)
                return True
        except Exception as e:
            logging.warning("指定按钮点击失败：%s", e)

    for text in LOGIN_TEXTS:
        try:
            loc = page.get_by_text(text, exact=False).first
            if loc.count() > 0 and loc.is_visible(timeout=2000):
                loc.click(timeout=5000)
                logging.info("已点击文字按钮：%s", text)
                return True
        except Exception as e:
            logging.info("文字按钮点击失败：%s, err=%s", text, e)

    selectors = [
        "input[type=submit]",
        "input[type=button]",
        "button",
        "a",
        ".login",
        "#login",
        "[onclick*=login]",
        "[onclick*=Login]",
        "[onclick*=connect]",
        "[onclick*=Connect]",
    ]

    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0 and loc.is_visible(timeout=2000):
                loc.click(timeout=5000)
                logging.info("已点击选择器按钮：%s", selector)
                return True
        except Exception as e:
            logging.info("选择器按钮点击失败：%s, err=%s", selector, e)

    return False


def portal_login_with_playwright(url: str) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        logging.error("没有安装 playwright。请运行：python -m pip install playwright")
        return False

    user, password = get_local_account()

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel="msedge", headless=not SHOW_BROWSER)
            except Exception:
                browser = p.chromium.launch(headless=not SHOW_BROWSER)

            page = browser.new_page()
            logging.info("打开认证页：%s", url)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1500)

            if user and password:
                user_selectors = []
                pass_selectors = []

                if USER_SELECTOR:
                    user_selectors.append(USER_SELECTOR)
                if PASS_SELECTOR:
                    pass_selectors.append(PASS_SELECTOR)

                user_selectors += [
                    'input[name="username"]',
                    'input[name="user"]',
                    'input[name="userid"]',
                    'input[name="userId"]',
                    'input[name="account"]',
                    'input[name="DDDDD"]',
                    'input[id="username"]',
                    'input[id="user"]',
                    'input[id="account"]',
                    'input[type="text"]',
                    'input:not([type])',
                ]

                pass_selectors += [
                    'input[name="password"]',
                    'input[name="passwd"]',
                    'input[name="pass"]',
                    'input[name="upass"]',
                    'input[name="pwd"]',
                    'input[id="password"]',
                    'input[id="passwd"]',
                    'input[id="pwd"]',
                    'input[type="password"]',
                ]

                filled_user = fill_first_visible(page, user_selectors, user, "账号")
                filled_pass = fill_first_visible(page, pass_selectors, password, "密码")

                if not filled_user or not filled_pass:
                    logging.warning(
                        "账号或密码输入框没有自动识别成功。filled_user=%s, filled_pass=%s",
                        filled_user,
                        filled_pass,
                    )

            clicked = click_login_button(page)

            if clicked:
                page.wait_for_timeout(8000)
                logging.info("已尝试提交登录。当前页面：%s", page.url)
                browser.close()
                return True

            logging.warning("没有找到登录按钮。")
            if SHOW_BROWSER:
                logging.warning("浏览器保留 30 秒，请观察页面结构。")
                page.wait_for_timeout(30000)

            browser.close()
            return False

    except Exception as e:
        logging.exception("网页登录过程失败：%s", e)
        return False


def portal_login() -> bool:
    time.sleep(PORTAL_AFTER_WIFI_DELAY_SECONDS)

    # 进入认证页前再次检测一次，避免不必要打开浏览器。
    if internet_auth_ok():
        logging.info("进入认证页前检测到网络已可用，跳过网页登录。")
        return True

    url = build_portal_url()
    if not url:
        logging.error("Captive-portal URL is not configured.")
        return False
    basic_portal_get(url)

    ok = portal_login_with_playwright(url)

    if ok:
        logging.info("网页登录流程已执行，等待后重新检测认证状态。")
        time.sleep(5)
        return internet_auth_ok()

    logging.warning("网页登录流程失败。")
    return False


def run_once(manual: bool = False) -> bool:
    logging.info("=" * 80)
    logging.info("Campus Wi-Fi Auto Reconnect started")
    logging.info("Target Wi-Fi: %s", SSID)
    logging.info("日志文件：%s", LOG_FILE)

    # Automatic runs preserve other active networks. Manual runs may switch to the target Wi-Fi.
    if (not manual and not is_connected_to_target_wifi()
            and any_network_connected()
            and not REQUIRE_TARGET_WIFI_WHEN_INTERNET_OK):
        logging.info("Another network is connected; exiting without switching to the target Wi-Fi.")
        return True

    for attempt in range(1, MAX_ATTEMPTS + 1):
        logging.info("本次任务尝试 #%s / %s", attempt, MAX_ATTEMPTS)

        if not is_connected_to_target_wifi():
            if not connect_wifi():
                logging.warning("Wi-Fi 连接失败。")
                if attempt < MAX_ATTEMPTS:
                    time.sleep(ATTEMPT_WAIT_SECONDS)
                continue

        # Check connectivity before opening the captive portal.
        if internet_auth_ok():
            logging.info("网络已经可用，本次任务退出。")
            return True

        if portal_login():
            logging.info("网页登录认证成功，本次任务退出。")
            return True

        logging.warning("本轮网页登录未成功。")
        if attempt < MAX_ATTEMPTS:
            time.sleep(ATTEMPT_WAIT_SECONDS)

    logging.warning("本次任务尝试结束，仍未成功。")
    return False


if __name__ == "__main__":
    sys.exit(0 if run_once(manual="--manual" in sys.argv[1:]) else 1)
