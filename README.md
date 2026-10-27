# CampusNet Auto Reconnect

**校园网掉线或网页认证过期时，自动恢复 Wi-Fi 连接和认证，减少电脑离线导致远程维护中断的情况。**

电脑不在身边时，校园网欠费、认证过期或短暂断线，可能让远程桌面、SSH 或其他远程连接突然失效。这个小工具在 Windows 上按计划检查连接；需要时重新连接指定 Wi-Fi，并尝试完成校园网网页认证。可以用根目录的两个开关随时启用或停用。

它的目标是**尽量让电脑重新联网**，并不承诺校园网分配的 IP 固定，也不能保证校园网允许外网主动连入。远程连接仍取决于校园网的 NAT、防火墙和你的远程访问方案。

## 能做什么

- 每 5 分钟检查一次；关闭开关时只读取状态，不启动登录程序或切换网络。
- 目标 Wi-Fi 未连接时，尝试连接；网页认证失效时，尝试自动填写账号密码并提交。
- 自动模式下保留已有的其他网络连接，不会因为校园网掉线主动切断手机热点等连接。
- 手动运行时可以立即尝试切换到目标校园网。
- 后台任务使用隐藏方式运行，日常开关会显示简短提示。
- 账号和密码从本机环境变量读取，不需要写入代码或提交到 GitHub。

## 适用范围

Windows 10/11，使用“开放 Wi-Fi + 网页认证”的校园网。认证页面的表单需要能被自动识别；不同学校的认证页面可能需要调整代码中的输入框或按钮选择器。

## 配置

安装 Python 3.10 或更新版本，并确保 `pythonw.exe` 在 Windows `PATH` 中（安装 Python 时可勾选添加到 PATH）。然后在 PowerShell 中设置本机配置。请把示例值替换成自己校园网的信息：

```powershell
setx CAMPUS_WIFI_SSID "你的校园网名称"
setx CAMPUS_WIFI_PORTAL_URL "http://校园认证网关/认证页面"
setx CAMPUS_WIFI_USER "你的校园网账号"
setx CAMPUS_WIFI_PASS "你的校园网密码"
```

认证地址应是校园网的登录页面地址，不要把账号或密码拼进 URL。`setx` 保存后，注销并重新登录 Windows，让计划任务读取到新环境变量。

安装依赖：

```powershell
cd internal
py -3 -m pip install -r requirements.txt
py -3 -m playwright install chromium
```

## 启用

1. 用管理员身份打开 PowerShell，进入 `internal` 文件夹。
2. 安装每 5 分钟唤醒一次的隐藏计划任务：

   ```powershell
   .\install_startup_task_hidden.ps1
   ```

3. 回到项目根目录，双击 `开启自动重连.bat`。完成这段时间的远程使用后，双击 `关闭自动重连.bat`。

人在电脑前想立即尝试重连时，可以运行 `internal\run_manual.bat`。移除计划任务时，使用管理员 PowerShell 运行 `internal\uninstall_startup_task_hidden.ps1`。

计划任务只在当前 Windows 用户已登录、电脑未睡眠时运行。电脑关机、睡眠或彻底断网后，工具无法自行唤醒电脑或保证远程连接恢复。

## 安全说明

- 不要把真实账号、密码、认证页面中的个人参数或 `.env` 配置提交到仓库。
- 密码由脚本从 `CAMPUS_WIFI_PASS` 环境变量读取；本项目不会把密码写进源码。
- 校园网认证协议和网络管理规则由学校决定，请只用于你有权限使用的网络和账号。

## English

CampusNet Auto Reconnect helps a Windows computer recover from campus Wi-Fi disconnects and expired captive-portal sessions. It can reconnect to a configured network and submit the portal login in the background, reducing interruptions to unattended remote maintenance.

It does **not** make a campus-assigned IP static or guarantee inbound remote access. NAT, firewalls, sleep state, and campus network policy still determine whether the computer can be reached remotely. Credentials are read from local environment variables and should never be committed.
