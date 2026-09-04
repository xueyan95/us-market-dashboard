#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
should_notify.py — 决定 GitHub Actions 这一轮跑下来要不要推 Telegram、推哪种。

输入：
  - cron UTC 时间（由 workflow 用 ${{ github.event.schedule }} 传入 → env SLOT_UTC）
    '0 0'   收盘复盘
    '0 13'  盘前（夏令时 21:00 CST）
    '30 14' 盘前（冬令时 22:00 CST）
  - 也支持手动传参 --cron='HH MM'；默认从 env SLOT_UTC 读

输出到 stdout 一行 JSON：
  {"slot": "postmarket|premarket|skip", "reason": "..."}

下游步骤根据 SLOT 决定行为：
  - postmarket：正常收盘复盘
  - premarket ：正常盘前速览
  - skip      ：跳过推送（节假日 / 非交易日 / 数据未就绪）

DST 规则（美国）：3 月第 2 个周日 ~ 11 月第 1 个周日（美东时间）
判定依据是 today（脚本运行时），而非美国当前时间——简化处理，误差 < 1 天。
"""
import datetime
import json
import os
import subprocess
import sys


def is_us_dst(today):
    """美国夏令时：3 月第 2 个周日 ~ 11 月第 1 个周日。"""
    y = today.year
    # 3 月第 2 个周日
    mar1 = datetime.date(y, 3, 1)
    sun_to_add = (6 - mar1.weekday()) % 7  # 第 1 个周日距 3/1 几天
    mar2_sun = mar1 + datetime.timedelta(days=sun_to_add + 7)
    # 11 月第 1 个周日
    nov1 = datetime.date(y, 11, 1)
    nov1_sun = nov1 + datetime.timedelta(days=(6 - nov1.weekday()) % 7)
    return mar2_sun <= today < nov1_sun


def last_trading_day_from_data():
    """从 market_data.json 读最近交易日 ISO 字符串。文件不存在/失败返回 None。
    依赖：fetch_data.py 已先跑完。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, "market_data.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            m = json.load(f)
        d = m.get("d_latest")
        return d if d else None
    except Exception as e:  # noqa: BLE001
        print(f"[read market_data.json] 失败: {e}", file=sys.stderr)
        return None


def last_trading_day_via_kline():
    """（fallback）拉 SPY 最近 5 日 K 线，返回最新交易日 ISO 字符串。仅当
    market_data.json 不可用时使用——避免重复 fetch。
    """
    try:
        r = subprocess.run(
            ["npx", "-y", "westock-data-clawhub@1.0.4", "kline", "usSPY",
             "--period", "day", "--limit", "5"],
            capture_output=True, text=True, timeout=60)
        for line in r.stdout.splitlines():
            if line.startswith("| usSPY"):
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3:
                    return parts[2]
    except Exception as e:  # noqa: BLE001
        print(f"[kline] 失败: {e}", file=sys.stderr)
    return None


def classify_slot(cron_hh, cron_mm, dst):
    """根据 cron 时间和 DST 判定 slot 类型。

    '0 0'        → postmarket（收盘复盘，固定 08:00 CST，不受 DST 影响）
    '0 13' (DST)  → premarket（盘前 21:00 CST，夏令时有效）
    '30 14' (noDST)→ premarket（盘前 22:00 CST，冬令时有效）
    其他组合 → skip
    """
    if cron_hh == 0 and cron_mm == 0:
        return "postmarket"
    if dst and cron_hh == 13 and cron_mm == 0:
        return "premarket"
    if (not dst) and cron_hh == 14 and cron_mm == 30:
        return "premarket"
    return "skip"


def main():
    # 从 env 或 argv 取 cron
    slot_env = os.environ.get("SLOT_UTC", "")
    cron_hh, cron_mm = 0, 0
    if slot_env:
        try:
            cron_hh, cron_mm = [int(x) for x in slot_env.strip().split()[:2]]
        except Exception:
            pass
    else:
        for arg in sys.argv[1:]:
            if arg.startswith("--cron="):
                try:
                    cron_hh, cron_mm = [int(x) for x in arg.split("=", 1)[1].split()[:2]]
                except Exception:
                    pass

    today = datetime.datetime.now().date()
    dst = is_us_dst(today)
    slot = classify_slot(cron_hh, cron_mm, dst)
    print(f"today={today} DST={dst} cron=({cron_hh:02d}:{cron_mm:02d} UTC) → slot={slot}")

    if slot == "skip":
        # 非 DST 匹配的 cron，或 cron 字段异常 → 不推送
        result = {"slot": "skip", "reason": f"DST={dst} 时 cron {cron_hh:02d}:{cron_mm:02d} 不适用"}
        _emit(result)
        sys.exit(0)

    # 进一步判断今天是否是交易日（先读 fetch_data.py 写出的 market_data.json）
    last_d = last_trading_day_from_data() or last_trading_day_via_kline()
    if last_d is None:
        result = {"slot": "skip", "reason": "无法拉取最近 K 线日期"}
        _emit(result)
        sys.exit(0)

    delta = (today - datetime.date.fromisoformat(last_d)).days
    print(f"last_trading_day={last_d} delta={delta}天")

    if slot == "premarket":
        # 盘前：今天必须开盘
        if delta > 1:
            result = {"slot": "skip", "reason": f"盘前 slot 但最近交易日 {last_d} 距今 {delta} 天（今天不开盘）"}
            _emit(result)
            sys.exit(0)
    elif slot == "postmarket":
        # 复盘：必须有"昨天"的数据
        if delta > 2:
            result = {"slot": "skip", "reason": f"复盘 slot 但最近交易日 {last_d} 距今 {delta} 天（昨天未开盘）"}
            _emit(result)
            sys.exit(0)

    _emit({"slot": slot, "reason": "ok", "dst": dst, "last_trading_day": last_d})


def _emit(result):
    """输出到 stdout + GitHub Actions outputs（兼容本地直跑）。"""
    line = json.dumps(result, ensure_ascii=False)
    print(line)
    # 同时写 outputs 文件（GitHub Actions 自动读）
    out_file = os.environ.get("GITHUB_OUTPUT")
    if out_file:
        with open(out_file, "a", encoding="utf-8") as f:
            f.write(f"slot_json={line}\n")


if __name__ == "__main__":
    main()