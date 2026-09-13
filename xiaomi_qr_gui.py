# -*- coding: utf-8 -*-
"""
小米账号扫码登录 - 桌面弹窗版 (GUI)
=======================================
- 弹出居中桌面窗口，高清渲染二维码
- 窗口置顶，方便直接拿手机扫码
- 实时显示扫码状态：等待扫码 -> 手机确认 -> 成功入账
- 自动完成 STS 换票并保存凭据至 xiaomi_account.json 与 real_phone_cookie.txt
"""

from __future__ import annotations

import io
import os
import sys
import time
import json
import threading
import requests
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Dict, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import qrcode
from PIL import Image, ImageTk

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

UA_MOBILE = (
    "Mozilla/5.0 (Linux; U; Android 14; zh-CN; 22041216C Build/UP1A.231005.007; "
    "AppBundle/com.mipay.wallet; AppVersionName/6.114.0.5756.2747; AppVersionCode/20577694; "
    "MiuiVersion/V816.0.12.0.ULOCNXM; DeviceId/xagapro; NetworkType/WIFI; "
    "mix_version; WebViewVersion/146.0.7680.119) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Version/4.0 Mobile Safari/537.36 XiaoMi/MiuiBrowser/4.3"
)


class XiaomiLoginGui:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("小米账号扫码登录 - 玩家视界")
        self.root.geometry("400x520")
        self.root.resizable(False, False)
        self.root.configure(bg="#F7F9FA")

        # 尝试让窗口居中并置顶
        self._center_window(400, 520)
        self.root.attributes("-topmost", True)

        self.running = True
        self.login_data: Optional[Dict[str, Any]] = None
        self.qr_photo: Optional[ImageTk.PhotoImage] = None
        self.poll_thread: Optional[threading.Thread] = None

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _center_window(self, width: int, height: int):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _build_ui(self):
        # 头部标题
        header_frame = tk.Frame(self.root, bg="#F7F9FA")
        header_frame.pack(fill=tk.X, pady=(20, 10))

        title_lbl = tk.Label(
            header_frame,
            text="小米账号安全扫码登录",
            font=("Microsoft YaHei", 14, "bold"),
            bg="#F7F9FA",
            fg="#1A1A1A"
        )
        title_lbl.pack()

        subtitle_lbl = tk.Label(
            header_frame,
            text="使用 小米手机相机 / 小米扫一扫 / 微信 扫码",
            font=("Microsoft YaHei", 9),
            bg="#F7F9FA",
            fg="#666666"
        )
        subtitle_lbl.pack(pady=(4, 0))

        # 二维码容器
        qr_container = tk.Frame(self.root, bg="#FFFFFF", bd=1, relief=tk.SOLID, padx=10, pady=10)
        qr_container.pack(pady=10)

        self.qr_label = tk.Label(qr_container, bg="#FFFFFF")
        self.qr_label.pack()

        # 状态文案
        self.status_label = tk.Label(
            self.root,
            text="正在申请二维码...",
            font=("Microsoft YaHei", 10, "bold"),
            bg="#F7F9FA",
            fg="#FF6700"
        )
        self.status_label.pack(pady=10)

        # 底部提示与按钮
        self.action_frame = tk.Frame(self.root, bg="#F7F9FA")
        self.action_frame.pack(fill=tk.X, pady=(5, 15))

        self.refresh_btn = tk.Button(
            self.action_frame,
            text="🔄 刷新二维码",
            font=("Microsoft YaHei", 9),
            bg="#FFFFFF",
            fg="#333333",
            relief=tk.GROOVE,
            command=self.fetch_and_show_qr
        )
        self.refresh_btn.pack()

    def fetch_and_show_qr(self):
        """拉取最新二维码并展示"""
        self.status_label.config(text="正在申请二维码...", fg="#FF6700")
        self.refresh_btn.config(state=tk.DISABLED)

        def worker():
            url = "https://account.xiaomi.com/longPolling/loginUrl"
            params = {
                "_group": "DEFAULT",
                "_qrsize": "260",
                "qs": "?callback=https%3A%2F%2Faccount.xiaomi.com%2Fsts%3Fsign%3DZvAtJIzsDsFe60LdaPa76nNNP58%253D%26followup%3Dhttps%253A%252F%252Faccount.xiaomi.com%252Fpass%252Fauth%252Fsecurity%252Fhome%26sid%3Dpassport&sid=passport&_group=DEFAULT",
                "bizDeviceType": "",
                "callback": "https://account.xiaomi.com/sts?sign=ZvAtJIzsDsFe60LdaPa76nNNP58=&followup=https://account.xiaomi.com/pass/auth/security/home&sid=passport",
                "_hasLogo": "false",
                "theme": "",
                "sid": "passport",
                "needTheme": "false",
                "showActiveX": "false",
                "serviceParam": json.dumps({"checkSafePhone": False, "checkSafeAddress": False, "lsrp_score": 0.0}),
                "_locale": "zh_CN",
                "_sign": "2&V1_passport&BUcblfwZ4tX84axhVUaw8t6yi2E=",
                "_dc": str(int(time.time() * 1000)),
            }
            try:
                r = requests.get(url, headers={"User-Agent": USER_AGENT}, params=params, timeout=15)
                text = r.text
                if "&&&START&&&" in text:
                    text = text.split("&&&START&&&", 1)[-1].strip()
                data = json.loads(text)
                if data.get("code") == 0:
                    self.login_data = data
                    qr_img_url = data.get("qr")
                    login_url = data.get("loginUrl")

                    # 直接加载小米官方返回的高清登录二维码图片（若失败则以真正的 loginUrl 生成）
                    try:
                        img_res = requests.get(qr_img_url, headers={"User-Agent": USER_AGENT}, timeout=10)
                        img = Image.open(io.BytesIO(img_res.content)).convert("RGB")
                    except Exception:
                        qr = qrcode.QRCode(border=2)
                        qr.add_data(login_url)
                        qr.make(fit=True)
                        img = qr.make_image(fill_color="black", back_color="white").resize((260, 260), Image.Resampling.NEAREST)

                    img.save("qrcode.png")
                    self.root.after(0, self._on_qr_ready, img)
                else:
                    self.root.after(0, self._on_qr_fail, data.get("error") or "获取失败")
            except Exception as e:
                self.root.after(0, self._on_qr_fail, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_qr_ready(self, img: Image.Image):
        self.qr_photo = ImageTk.PhotoImage(img)
        self.qr_label.config(image=self.qr_photo)
        self.status_label.config(text="📱 请手机扫码（5分钟内有效）", fg="#007ACC")
        self.refresh_btn.config(state=tk.NORMAL)

        # 启动长轮询线程
        lp_url = self.login_data.get("lp")
        timeout = int(self.login_data.get("timeout", 300))
        if self.poll_thread and self.poll_thread.is_alive():
            pass
        self.poll_thread = threading.Thread(target=self._poll_worker, args=(lp_url, timeout), daemon=True)
        self.poll_thread.start()

    def _on_qr_fail(self, msg: str):
        self.status_label.config(text=f"获取失败: {msg}", fg="red")
        self.refresh_btn.config(state=tk.NORMAL)

    def _poll_worker(self, lp_url: str, timeout: int):
        deadline = time.time() + max(30, timeout)
        last_code = None
        while self.running and time.time() < deadline:
            try:
                response = requests.get(lp_url, timeout=60)
                text = response.text
                if "&&&START&&&" in text:
                    text = text.split("&&&START&&&", 1)[-1].strip()
                result = json.loads(text)
                code = result.get("code", -1)

                if code != last_code:
                    if code == 700:
                        self.root.after(0, self.status_label.config, {"text": "⏳ 等待扫码...", "fg": "#007ACC"})
                    elif code == 701:
                        self.root.after(0, self.status_label.config, {"text": "📲 已扫码，请在手机上点击【允许】", "fg": "#FF9900"})
                    elif code == 702:
                        self.root.after(0, self.status_label.config, {"text": "❌ 二维码已过期，请点击刷新", "fg": "red"})
                        break
                    last_code = code

                if code == 0:
                    user_id = str(result.get("userId", ""))
                    pass_token = str(result.get("passToken", ""))
                    security_token = str(result.get("ssecurity", ""))
                    self.root.after(0, self._on_login_success, user_id, pass_token, security_token)
                    return
            except requests.Timeout:
                pass
            except Exception as e:
                time.sleep(2)

    def _on_login_success(self, user_id: str, pass_token: str, security_token: str):
        self.status_label.config(text="✅ 扫码成功！正在自动换取凭据...", fg="#009933")
        self.refresh_btn.config(state=tk.DISABLED)

        def exchange_and_save():
            # 1. 换取天星金融/钱包业务 Cookie
            login_url = (
                "https://account.xiaomi.com/pass/serviceLogin?callback=https%3A%2F%2Fapi.jr.airstarfinance.net%2Fsts"
                "%3Fsign%3D1dbHuyAmee0NAZ2xsRw5vhdVQQ8%253D%26followup%3Dhttps%253A%252F%252Fm.jr.airstarfinance.net"
                "%252Fmp%252Fapi%252Flogin%253Ffrom%253Dmipay_indexicon_TVcard%2526deepLinkEnable%253Dfalse"
                "%2526requestUrl%253Dhttps%25253A%25252F%25252Fm.jr.airstarfinance.net%25252Fmp%25252Factivity"
                "%25252FvideoActivity%25253Ffrom%25253Dmipay_indexicon_TVcard%252526_noDarkMode%25253Dtrue"
                "%252526_transparentNaviBar%25253Dtrue%252526cUserId%25253Dusyxgr5xjumiQLUoAKTOgvi858Q"
                "%252526_statusBarHeight%25253D137&sid=jrairstar&_group=DEFAULT&_snsNone=true&_loginType=ticket"
            )
            s = requests.Session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
                "Cookie": f"passToken={pass_token}; userId={user_id};",
            }
            try:
                res = s.get(login_url, headers=headers, allow_redirects=True, timeout=20)
                wallet_cookies = s.cookies.get_dict()
                c_user_id = wallet_cookies.get("cUserId")
                service_token = wallet_cookies.get("serviceToken") or wallet_cookies.get("jrairstar_serviceToken")
                
                final_cookies = {
                    "userId": user_id,
                    "cUserId": c_user_id,
                    "serviceToken": service_token,
                    "jrairstar_serviceToken": service_token,
                }
                if "jrairstar_ph" in wallet_cookies:
                    final_cookies["jrairstar_ph"] = wallet_cookies["jrairstar_ph"]
                if "jrairstar_slh" in wallet_cookies:
                    final_cookies["jrairstar_slh"] = wallet_cookies["jrairstar_slh"]

                # 保存 Cookie
                cookie_str = "; ".join(f"{k}={v}" for k, v in final_cookies.items())
                with open("real_phone_cookie.txt", "w", encoding="utf-8") as f:
                    f.write(cookie_str)
            except Exception as e:
                print(f"[!] 换票写入异常: {e}")

            # 2. 保存长期凭据
            account_data = {
                "userId": user_id,
                "passToken": pass_token,
                "securityToken": security_token,
                "updatedAt": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            with open("xiaomi_account.json", "w", encoding="utf-8") as f:
                json.dump(account_data, f, ensure_ascii=False, indent=2)

            self.root.after(0, self._finish_ui, user_id)

        threading.Thread(target=exchange_and_save, daemon=True).start()

    def _finish_ui(self, user_id: str):
        self.status_label.config(text=f"🎉 登录成功 (ID: {user_id})，窗口即将关闭...", fg="#009933")
        self.root.after(2000, self.root.destroy)

    def on_close(self):
        self.running = False
        self.root.destroy()

    def start(self):
        self.fetch_and_show_qr()
        self.root.mainloop()


if __name__ == "__main__":
    app = XiaomiLoginGui()
    app.start()
