# -*- coding: utf-8 -*-
"""
小米钱包“玩家视界”自动做任务领会员时长脚本 (2026 增强自适应版)
===========================================================
- 适配真机 (Redmi Note 11T Pro+ / HyperOS) 与 2026 最新版小米钱包 (v6.114+)
- 协议修正：clickTask / completeTask / luckDraw 全面采用 GET 请求规范，彻底规避网关 401 拦截
- 状态机自适应驱动：摒弃死板的固定 2 轮计数限制，基于 completeStatus (0~4) 与 todayUserTaskStatus 智能动态循环 (支持单日 2~5 轮)
- 防漏领机制：自动检测 remainChance > 0 遗留奖励并智能补开奖
- 扩展任务与账目流水：集成 queryUserJoinList 历史明细与 getEmiAdUrlV2 / inviteTask 扩展任务状态展示
- 凭证支持：自动读取 real_phone_cookie.txt 或 passToken 自动换票
"""

import os
import sys
import time
import json
import random
import re
import requests
from typing import Optional, Dict, Any, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

API_HOST = "m.jr.airstarfinance.net"
ACTIVITY_CODE = "2211-videoWelfare"
TASK_CODE = "BROWSE_GROUP_TASK1"

# Redmi Note 11T Pro+ (xagapro) 真机环境指纹
APP_VERSION_NAME = "6.114.0.5756.2747"
APP_VERSION_CODE = "20577694"

UA_MOBILE = (
    f"Mozilla/5.0 (Linux; U; Android 14; zh-CN; 22041216C Build/UP1A.231005.007; "
    f"AppBundle/com.mipay.wallet; AppVersionName/{APP_VERSION_NAME}; AppVersionCode/{APP_VERSION_CODE}; "
    f"MiuiVersion/V816.0.12.0.ULOCNXM; DeviceId/xagapro; NetworkType/WIFI; "
    f"mix_version; WebViewVersion/146.0.7680.119) AppleWebKit/537.36 (KHTML, like Gecko) "
    f"Version/4.0 Mobile Safari/537.36 XiaoMi/MiuiBrowser/4.3"
)

USER_EXTRA = json.dumps({
    "platformType": 1,
    "com.miui.player": "4.27.0.4",
    "com.miui.video": "v2024090290(MiVideo-UN)",
    "com.mipay.wallet": APP_VERSION_NAME
}, separators=(',', ':'))


def load_real_phone_cookie(filename: str = "real_phone_cookie.txt") -> str:
    """尝试从本地文件加载真机实时 Cookie"""
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                c = f.read().strip()
                if c:
                    return c
        except Exception:
            pass
def load_account_json(filename: str = "xiaomi_account.json") -> Dict[str, str]:
    """尝试从本地加载扫码生成的长期凭据"""
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


class XiaomiWalletBot:
    def __init__(self, user_id: str = "", pass_token: str = "", raw_cookie: str = "", device_file: str = "device_params.json"):
        # 自动读取扫码保存的长期凭据
        acc_info = load_account_json()
        self.user_id = str(user_id or acc_info.get("userId", "2713517541")).strip()
        self.pass_token = str(pass_token or acc_info.get("passToken", "")).strip()
        self.device_file = device_file
        self.device_params = self._load_or_gen_device()

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA_MOBILE,
            "Host": API_HOST,
            "Referer": "https://m.jr.airstarfinance.net/mp/activity/videoActivity",
            "Origin": "https://m.jr.airstarfinance.net",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

        # 优先使用传入的 raw_cookie，若为空则自动尝试读取 real_phone_cookie.txt
        cookie_to_use = raw_cookie or load_real_phone_cookie()
        if cookie_to_use:
            self._parse_and_set_cookie(cookie_to_use)

    def _load_or_gen_device(self) -> Dict[str, str]:
        """每账号生成并持久化固定设备指纹，防止由于指纹频繁变更被风控"""
        key = f"device_{self.user_id}"
        all_devices = {}
        if os.path.exists(self.device_file):
            try:
                with open(self.device_file, "r", encoding="utf-8") as f:
                    all_devices = json.load(f)
            except Exception:
                all_devices = {}

        if key in all_devices:
            return all_devices[key]

        dev = {
            "imei": "862190063736876",
            "deviceId": "22041216UC",
            "longitude": f"{116.3 + random.random() * 0.1:.6f}",
            "latitude": f"{39.9 + random.random() * 0.1:.6f}"
        }
        all_devices[key] = dev
        try:
            with open(self.device_file, "w", encoding="utf-8") as f:
                json.dump(all_devices, f, indent=2)
        except Exception:
            pass
        return dev

    def _parse_and_set_cookie(self, raw_cookie: str):
        """解析并设置 Cookie"""
        for item in raw_cookie.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                self.session.cookies.set(k.strip(), v.strip(), domain="m.jr.airstarfinance.net")
                self.session.cookies.set(k.strip(), v.strip(), domain="api.jr.airstarfinance.net")

    def login_by_pass_token(self) -> bool:
        """使用 passToken 自动通过 STS 换取业务 session cookies"""
        if not self.pass_token or not self.user_id:
            return False
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
            "Cookie": f"passToken={self.pass_token}; userId={self.user_id};",
        }
        try:
            res = s.get(login_url, headers=headers, allow_redirects=True, timeout=20)
            cookies = s.cookies.get_dict()
            c_user_id = cookies.get("cUserId")
            service_token = cookies.get("serviceToken") or cookies.get("jrairstar_serviceToken")
            ph = cookies.get("jrairstar_ph")
            slh = cookies.get("jrairstar_slh")

            if c_user_id and service_token and c_user_id != "EXPIRED":
                for k, v in cookies.items():
                    self.session.cookies.set(k, v, domain="m.jr.airstarfinance.net")
                    self.session.cookies.set(k, v, domain="api.jr.airstarfinance.net")
                
                # 同步更新本地 real_phone_cookie.txt
                cookie_parts = [f"userId={self.user_id}", f"cUserId={c_user_id}", f"serviceToken={service_token}", f"jrairstar_serviceToken={service_token}"]
                if ph:
                    cookie_parts.append(f"jrairstar_ph={ph}")
                if slh:
                    cookie_parts.append(f"jrairstar_slh={slh}")
                try:
                    with open("real_phone_cookie.txt", "w", encoding="utf-8") as f:
                        f.write("; ".join(cookie_parts))
                except Exception:
                    pass

                print(f"[+] 登录凭据成功换取! cUserId: {c_user_id[:6]}...{c_user_id[-4:]}")
                return True
            else:
                return False
        except Exception as e:
            print(f"[-] 登录换票异常: {e}")
            return False

    def query_balance(self) -> Dict[str, Any]:
        """查询当前会员时长余额"""
        url = f"https://{API_HOST}/mp/api/generalActivity/queryUserBalanceWithFrozen"
        params = {
            "activityCode": ACTIVITY_CODE,
            "app": "com.mipay.wallet",
            "deviceType": "2",
            "system": "1",
            "visitEnvironment": "2",
            "userExtra": USER_EXTRA
        }
        try:
            res = self.session.get(url, params=params, timeout=10)
            data = res.json()
            if data.get("code") == 0:
                val = data.get("value") or {}
                cur_balance = val.get("currentBalance", 0)
                frozen_balance = val.get("frozenBalance", 0)
                avail_balance = val.get("availableBalance", 0)
                return {
                    "ok": True,
                    "days": cur_balance / 100.0,
                    "frozen_days": frozen_balance / 100.0,
                    "avail_days": avail_balance / 100.0,
                    "raw": val
                }
            else:
                return {"ok": False, "error": data.get("error", "未知错误")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def query_join_history(self) -> List[Dict[str, Any]]:
        """查询会员时长获取明细"""
        url = f"https://{API_HOST}/mp/api/generalActivity/queryUserJoinList"
        params = {
            "activityCode": ACTIVITY_CODE,
            "app": "com.mipay.wallet",
            "deviceType": "2",
            "system": "1",
            "visitEnvironment": "2"
        }
        try:
            res = self.session.get(url, params=params, timeout=10)
            data = res.json()
            if data.get("code") == 0:
                return data.get("value") or []
        except Exception:
            pass
        return []

    def get_task_info(self) -> Optional[Dict[str, Any]]:
        """获取 BROWSE_GROUP_TASK1 任务详情"""
        url = f"https://{API_HOST}/mp/api/generalActivity/getTask"
        params = {
            "activityCode": ACTIVITY_CODE,
            "taskCode": TASK_CODE,
            "app": "com.mipay.wallet",
            "isNfcPhone": "true",
            "deviceType": "2",
            "system": "1",
            "visitEnvironment": "2",
            "userExtra": USER_EXTRA,
            "longitude": self.device_params["longitude"],
            "latitude": self.device_params["latitude"]
        }
        try:
            res = self.session.get(url, params=params, timeout=10)
            data = res.json()
            if data.get("code") == 0:
                return data.get("value", {}).get("taskInfo")
            else:
                print(f"[-] getTask 响应异常: {data.get('error')}")
                return None
        except Exception as e:
            print(f"[-] getTask 请求异常: {e}")
            return None

    def click_task(self, task_id: int, brows_task_id: int, brows_click_url_id: str) -> bool:
        """核心前置步骤：上报开始浏览广告 (现版本必须走 GET 请求)"""
        url = f"https://{API_HOST}/mp/api/generalActivity/clickTask"
        params = {
            "activityCode": ACTIVITY_CODE,
            "taskId": task_id,
            "taskCode": TASK_CODE,
            "newBrowsTask": "true",
            "browsTaskId": brows_task_id,
            "browsClickUrlId": brows_click_url_id,
            "app": "com.mipay.wallet",
            "deviceType": "2",
            "system": "1",
            "visitEnvironment": "2",
            "userExtra": USER_EXTRA
        }
        try:
            res = self.session.get(url, params=params, timeout=10)
            data = res.json()
            if data.get("code") == 0:
                return True
            else:
                print(f"[-] clickTask 失败: {data.get('error')}")
                return False
        except Exception as e:
            print(f"[-] clickTask 请求异常: {e}")
            return False

    @staticmethod
    def parse_browse_duration(task: Dict[str, Any], url_info: Optional[Dict[str, Any]] = None) -> int:
        """
        动态匹配任务所需浏览时长 (完美支持 0~60 秒及以上，兼容毫秒/秒两种单位与正则提取)
        """
        url_info = url_info or {}
        raw_val = task.get("browseTime")
        if raw_val is None or raw_val == "":
            raw_val = url_info.get("browseTime")

        # 尝试从任务名称或描述中正则匹配 (如 "浏览10秒", "浏览15秒", "浏览30秒", "浏览60秒")
        for text_source in (task.get("taskName", ""), task.get("taskDesc", "")):
            if text_source:
                m = re.search(r"浏览\s*(\d+)\s*秒", text_source)
                if m:
                    return int(m.group(1))

        if raw_val is None or raw_val == "":
            return 10  # 默认兜底 10 秒

        try:
            val = int(raw_val)
            if val >= 1000:
                # 毫秒单位换算 (10000ms -> 10s, 15000ms -> 15s, 60000ms -> 60s)
                sec = int(round(val / 1000.0))
            else:
                # 秒单位 (0s, 5s, 10s, 15s, 30s, 60s)
                sec = val
            return max(0, min(sec, 120))
        except (ValueError, TypeError):
            return 10

    def complete_task(self, task_id: int, brows_task_id: int, brows_click_url_id: str, browse_seconds: int = 10, task_code: str = TASK_CODE) -> Optional[Dict[str, Any]]:
        """上报完成广告浏览任务 (现版本必须走 GET 请求)"""
        url = f"https://{API_HOST}/mp/api/generalActivity/completeTask"
        browse_time_param = str(browse_seconds * 1000 if browse_seconds > 0 else 0)
        params = {
            "activityCode": ACTIVITY_CODE,
            "taskId": task_id,
            "taskCode": task_code,
            "browsTaskId": brows_task_id,
            "browsClickUrlId": brows_click_url_id,
            "clickEntryType": "undefined",
            "festivalStatus": "0",
            "completeTime": str(int(time.time() * 1000)),
            "browseTime": browse_time_param,
            "app": "com.mipay.wallet",
            "deviceType": "2",
            "system": "1",
            "visitEnvironment": "2",
            "userExtra": USER_EXTRA
        }
        try:
            res = self.session.get(url, params=params, timeout=10)
            data = res.json()
            if data.get("code") == 0:
                return data.get("value")
            else:
                print(f"[-] completeTask 提示: {data.get('error')} (code={data.get('code')})")
                return None
        except Exception as e:
            print(f"[-] completeTask 请求异常: {e}")
            return None

    def luck_draw(self, user_task_id: str = "") -> Optional[Dict[str, Any]]:
        """开奖领取会员时长奖励 (现版本必须走 GET 请求)"""
        url = f"https://{API_HOST}/mp/api/generalActivity/luckDraw"
        params = {
            "activityCode": ACTIVITY_CODE,
            "userTaskId": str(user_task_id),
            "imei": self.device_params["imei"],
            "longitude": self.device_params["longitude"],
            "latitude": self.device_params["latitude"],
            "app": "com.mipay.wallet",
            "deviceType": "2",
            "system": "1",
            "visitEnvironment": "2",
            "userExtra": USER_EXTRA
        }
        try:
            res = self.session.get(url, params=params, timeout=10)
            data_json = res.json()
            if data_json.get("code") == 0:
                return data_json.get("value")
            else:
                print(f"[-] luckDraw 提示: {data_json.get('error')}")
                return None
        except Exception as e:
            print(f"[-] luckDraw 请求异常: {e}")
            return None

    def query_extra_tasks(self):
        """查询第三方试用与拉新任务状态"""
        print("\n-------------------- 其他扩展任务状态 --------------------")
        
        # 1. 邀请新用户任务
        try:
            r_inv = self.session.get(
                f"https://{API_HOST}/mp/api/video/inviteTask",
                params={
                    "activityCode": ACTIVITY_CODE,
                    "channel": "local",
                    "deviceType": 1,
                    "app": "com.mipay.wallet",
                    "system": "1",
                    "visitEnvironment": "2"
                },
                timeout=10
            ).json()
            if r_inv.get("code") == 0:
                inv = r_inv.get("value", {})
                print(f"[*] 邀请好友任务: [{inv.get('taskName') or '邀请好友领会员'}] "
                      f"进度: {inv.get('periodCompleteCount', 0)}/{inv.get('periodCount', 5)} 人 "
                      f"(每人送1天会员, 最高可得5天)")
        except Exception:
            pass

        # 2. App 试用下载任务
        try:
            jrairstar_ph = self.session.cookies.get("jrairstar_ph") or ""
            r_emi = self.session.post(
                f"https://{API_HOST}/mp/api/video/getEmiAdUrlV2",
                data={
                    "activityCode": ACTIVITY_CODE,
                    "pagination": "0",
                    "dataType": "0",
                    "taskCode": "NEW_USER_CAMPAIGN",
                    "app": "com.mipay.wallet",
                    "deviceType": "2",
                    "system": "1",
                    "visitEnvironment": "2",
                    "jrairstar_ph": jrairstar_ph,
                    "_deviceInfos": json.dumps({"platformType": 1, "imei": self.device_params["imei"], "deviceId": self.device_params["deviceId"]})
                },
                timeout=10
            ).json()
            if r_emi.get("code") == 0:
                tasks = r_emi.get("value", {}).get("tasks", {})
                for k, v in tasks.items():
                    if v:
                        t_name = v.get("taskName")
                        days = v.get("maxDrawGoldNum", 0) / 100.0
                        b_sec = int(v.get("browseTime", 30000) / 1000)
                        status_str = "可参与" if v.get("completeStatus") == 1 else "已完成"
                        print(f"[*] 试用下载任务: [{t_name}] 试用{b_sec}秒可领 {days:.1f} 天会员 ({status_str})")
        except Exception:
            pass

    def run(self):
        """执行全套自适应自动化流程"""
        print(f"\n================================================================")
        print(f"   小米钱包“玩家视界”自动做任务领会员 (账号: {self.user_id})")
        print(f"================================================================")

        # 1. 验证凭据
        balance_info = self.query_balance()
        if not balance_info.get("ok"):
            print("[!] 会话凭据可能已过期，尝试通过 passToken 换取...")
            if self.login_by_pass_token():
                balance_info = self.query_balance()
            else:
                print("[-] 无法通过 passToken 换取凭据。请更新 real_phone_cookie.txt 或 passToken")
                return

        if balance_info.get("ok"):
            print(f"[+] 当前会员总时长: {balance_info['days']:.2f} 天 (可用余额: {balance_info['avail_days']:.2f} 天)")
        else:
            print(f"[-] 查询会员时长异常: {balance_info.get('error')}")

        # 2. 自适应状态机循环执行 10 秒浏览任务
        round_idx = 0
        max_safety_rounds = 10  # 防御性最大循环轮次

        while round_idx < max_safety_rounds:
            task = self.get_task_info()
            if not task:
                print("[-] 无法获取任务详情，退出循环")
                break

            complete_status = task.get("completeStatus", 0)
            period_complete = task.get("periodCompleteCount", 0)
            period_count = task.get("periodCount", 2)
            remain_chance = task.get("remainChance", 0)
            user_task_id = str(task.get("userTaskId", ""))
            btn_text = task.get("buttonText", "")
            url_info = task.get("generalActivityUrlInfo") or {}
            today_user_task_status = url_info.get("todayUserTaskStatus", 1)

            print(f"\n[*] 任务状态监测: 状态码={complete_status} (0~4), 周期完成={period_complete}/{period_count}, "
                  f"抽奖机会={remain_chance}, 按钮文案='{btn_text}'")

            # 状态检查 A: 优先检查是否有未领取的开奖机会 (remainChance > 0)
            if remain_chance > 0:
                print(f"[!] 检测到有 {remain_chance} 次未领取的开奖机会，立即执行补开奖...")
                draw_res = self.luck_draw(user_task_id)
                if draw_res:
                    prize_name = draw_res.get("prizeInfo", {}).get("prizeName") or draw_res.get("prizeName", "会员时长")
                    amount = draw_res.get("prizeInfo", {}).get("amount") or draw_res.get("prizeAmount", 0)
                    print(f"[+] 恭喜！成功开奖获得: {prize_name} (+{amount/100.0:.2f}天)")
                time.sleep(random.uniform(2.0, 3.0))
                continue

            # 状态检查 B: 是否已经达到完成终态 (completeStatus == 3: 今日上限 / 4: 永久终态，或 todayUserTaskStatus == 2: 今日已无广告)
            if complete_status in (3, 4) or today_user_task_status == 2:
                print(f"[+] 浏览 10 秒任务今日已圆满完成 (completeStatus={complete_status}, 已完成{period_complete}轮)！")
                break

            # 状态检查 C: 获取广告下发参数与动态任务时长
            brows_click_url_id = url_info.get("browsClickUrlId", "")
            brows_task_id = url_info.get("id", 30)
            task_id = task.get("taskId", 813)

            # 🎯 动态自适应解析 0~60 秒任务时长 (兼容毫秒/秒/名称正则提取)
            base_seconds = self.parse_browse_duration(task, url_info)

            if not brows_click_url_id:
                print("[!] 服务端未返回广告 URL 标识 (browsClickUrlId 为空)，判定当前无可用广告")
                break

            round_idx += 1
            current_round_num = period_complete + 1
            print(f"\n---> 开始执行第 {current_round_num} 轮浏览任务...")

            # 步骤 2.1: 上报 clickTask (GET)
            print("  [1] 上报点击任务并开始计时...")
            if not self.click_task(task_id, brows_task_id, brows_click_url_id):
                print("  [-] clickTask 失败，尝试继续...")

            # 步骤 2.2: 动态拟真倒计时与缓冲等待 (0~60s 自适应 + 拟真随机延迟)
            if base_seconds == 0:
                # 0 秒即时任务：附加 2.0~3.5 秒自然手速与页面加载延迟，防风控瞬时拦截
                action_delay = round(random.uniform(2.0, 3.5), 1)
                print(f"  [2] 该任务为即时/0秒任务，添加拟真操作缓冲延迟 {action_delay} 秒...")
                time.sleep(action_delay)
            else:
                # 1~60 秒及以上任务：基准秒数 + 2~5 秒防时钟偏差与网络抖动随机缓冲
                extra_buffer = random.randint(2, 5)
                total_wait = base_seconds + extra_buffer
                print(f"  [2] 🎯 动态匹配任务时长: 基准 {base_seconds} 秒 + 拟真安全缓冲 {extra_buffer} 秒 (共计拟真浏览 {total_wait} 秒)...")
                for sec in range(total_wait, 0, -1):
                    print(f"      倒计时: {sec:2d} 秒...", end="\r", flush=True)
                    time.sleep(1)
                print(f"      倒计时:  0 秒 -> 拟真浏览完毕！")

            # 步骤 2.3: 上报 completeTask (GET)
            print("  [3] 上报完成任务...")
            comp_res = self.complete_task(task_id, brows_task_id, brows_click_url_id, base_seconds)
            time.sleep(random.uniform(1.5, 2.5))

            # 步骤 2.4: 开奖领取奖励 (GET)
            print("  [4] 开奖领取会员时长奖励 (luckDraw)...")
            draw_res = self.luck_draw(user_task_id)
            if draw_res:
                prize_name = draw_res.get("prizeInfo", {}).get("prizeName") or draw_res.get("prizeName", "会员时长")
                amount = draw_res.get("prizeInfo", {}).get("amount") or draw_res.get("prizeAmount", 0)
                print(f"  [+] 领取成功: {prize_name} (+{amount/100.0:.2f}天)")
            else:
                print("  [*] 当前轮次上报完毕，准备刷新下一轮状态...")

            # 拟真随机间隔后进入下一轮判定
            time.sleep(random.uniform(2.5, 4.5))

        # 3. 打印今日奖励历史明细
        print("\n-------------------- 今日奖励明细流水 --------------------")
        history = self.query_join_history()
        today_str = time.strftime("%Y-%m-%d")
        today_items = [item for item in history if item.get("createTime", "").startswith(today_str)]
        if today_items:
            for idx, item in enumerate(today_items, 1):
                val = int(item.get("value", 0))
                print(f"  {idx}. 时间: {item.get('createTime')} | 时长: +{val/100.0:.2f}天 ({val}点) | 描述: {item.get('desc')}")
        else:
            print("  暂无今日流水记录")

        # 4. 查询扩展任务
        self.query_extra_tasks()

        # 5. 最终结算
        print("\n======================== 最终结算 ========================")
        final_bal = self.query_balance()
        if final_bal.get("ok"):
            print(f"[+] 当前有效会员时长: {final_bal['days']:.2f} 天 (可用: {final_bal['avail_days']:.2f} 天)")
        print("==========================================================\n")


if __name__ == "__main__":
    # 默认自动加载本地 real_phone_cookie.txt
    # 若需指定 pass_token，可在此填入
    USER_ID = "2713517541"
    PASS_TOKEN = ""

    bot = XiaomiWalletBot(user_id=USER_ID, pass_token=PASS_TOKEN)
    bot.run()
