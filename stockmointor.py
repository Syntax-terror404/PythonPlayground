# jp_monitor.py
import time
import datetime as dt
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os
import sys
from math import floor

# ---------------- USER SETTINGS ----------------
TICKER = "JPPOWER.NS"
POLL_INTERVAL_SECONDS = 60         # check every 60 seconds
SMA_SHORT = 10
SMA_LONG = 30
RSI_LEN = 14

# Your current position details (fill these)
ENTRY_PRICE = 20.75                # price you placed buy order at
QTY = 9                            # number of shares you expect to hold

# Exit levels (you can compute from entry or set absolute)
TARGET_PRICE = ENTRY_PRICE * 1.03  # 3% target (change if you like)
STOPLOSS_PRICE = ENTRY_PRICE * 0.98 # 2% stoploss

# Telegram alert (optional). If you don't want telegram, leave BOT_TOKEN="" and CHAT_ID=""
BOT_TOKEN = ""      # "123456:ABC-DEF..." your bot token
CHAT_ID = ""        # your chat id (integer or string)

# Logging
LOGFILE = "jpmonitor.log"

# Market hours (IST) — adjust if needed
MARKET_OPEN = dt.time(9, 15)
MARKET_CLOSE = dt.time(15, 30)

# yfinance limitations: for 1m data use period within last 7 days.
YF_PERIOD = "7d"
YF_INTERVAL = "1m"

# ---------------- HELPERS ----------------
def log(msg):
    t = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{t}] {msg}"
    print(line)
    with open(LOGFILE, "a") as f:
        f.write(line + "\n")

def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": msg}
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        log(f"Telegram error: {e}")

def desktop_notify(title, message):
    # cross-platform best-effort
    try:
        if sys.platform.startswith("darwin"):
            # macOS
            os.system(f'''osascript -e 'display notification "{message}" with title "{title}"' ''')
        elif sys.platform.startswith("linux"):
            os.system(f'notify-send "{title}" "{message}"')
        elif sys.platform.startswith("win"):
            # windows: try toast via powershell
            ps = f'''
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
            $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $template.GetElementsByTagName("text")[0].AppendChild($template.CreateTextNode("{title}")) > $null
            $template.GetElementsByTagName("text")[1].AppendChild($template.CreateTextNode("{message}")) > $null
            $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
            $xml.LoadXml($template.GetXml())
            $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("JPMonitor").Show($toast)
            '''
            os.system(f"powershell -command \"{ps}\"")
    except Exception:
        pass

# RSI helper (Wilder's smoothing)
def compute_rsi(series_close, length=14):
    delta = series_close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi

# ---------------- MONITOR LOOP ----------------
def in_market_hours(now=None):
    if now is None:
        now = dt.datetime.now(dt.timezone.utc).astimezone()  # local timezone
    t = now.time()
    return (t >= MARKET_OPEN) and (t <= MARKET_CLOSE)

def fetch_minute_data(ticker=TICKER, period=YF_PERIOD, interval=YF_INTERVAL):
    # Returns dataframe with index as datetime and columns OHLCV
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, threads=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        # flatten columns if needed
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = ['_'.join([str(c) for c in col]).strip() for col in df.columns]
        # find close column
        close_col = next((c for c in df.columns if "close" in c.lower()), None)
        if close_col and close_col != "Close":
            df = df.rename(columns={close_col: "Close"})
        return df
    except Exception as e:
        log(f"Data fetch error: {e}")
        return None

def analyze_and_alert(df):
    # use last N rows (we need at least SMA_LONG + RSI_LEN rows)
    nreq = max(SMA_LONG, RSI_LEN) + 5
    if len(df) < nreq:
        log("Not enough minute bars to compute indicators yet.")
        return {}
    df = df.copy().dropna(subset=["Close"])
    # compute indicators
    df[f"SMA_SHORT"] = df["Close"].rolling(SMA_SHORT).mean()
    df[f"SMA_LONG"] = df["Close"].rolling(SMA_LONG).mean()
    df["RSI"] = compute_rsi(df["Close"], RSI_LEN)
    last = df.iloc[-1]
    prev = df.iloc[-2]

    current_price = float(last["Close"])
    prev_price = float(prev["Close"])
    sma_short_now = float(last["SMA_SHORT"])
    sma_long_now = float(last["SMA_LONG"])
    sma_short_prev = float(prev["SMA_SHORT"])
    sma_long_prev = float(prev["SMA_LONG"])
    rsi_now = float(last["RSI"])

    alerts = []

    # 1) target hit
    if current_price >= TARGET_PRICE:
        alerts.append(("TAKE_PROFIT", f"Price reached target: {current_price:.2f} >= {TARGET_PRICE:.2f}"))

    # 2) stoploss hit
    if current_price <= STOPLOSS_PRICE:
        alerts.append(("STOP_LOSS", f"Price reached stoploss: {current_price:.2f} <= {STOPLOSS_PRICE:.2f}"))

    # 3) trend change (SMA crossover)
    crossed_bull = (sma_short_prev <= sma_long_prev) and (sma_short_now > sma_long_now)
    crossed_bear = (sma_short_prev >= sma_long_prev) and (sma_short_now < sma_long_now)
    if crossed_bull:
        alerts.append(("TREND_BULLISH", f"SMA{SMA_SHORT} crossed ABOVE SMA{SMA_LONG} -> short={sma_short_now:.2f} long={sma_long_now:.2f}"))
    if crossed_bear:
        alerts.append(("TREND_BEARISH", f"SMA{SMA_SHORT} crossed BELOW SMA{SMA_LONG} -> short={sma_short_now:.2f} long={sma_long_now:.2f}"))

    # 4) SMA + RSI sell trigger (common rule): short SMA below long AND RSI > 70
    if (sma_short_now < sma_long_now) and (rsi_now > 70):
        alerts.append(("SMA_RSI_SELL", f"SMA short < long and RSI {rsi_now:.1f} > 70 -> consider SELL"))

    # 5) price momentum (large down candle)
    pct_move = (current_price - prev_price) / prev_price if prev_price != 0 else 0
    if pct_move <= -0.01:  # more than 1% down in one minute -> potential momentum sell
        alerts.append(("MOMENTUM_DOWN", f"Price dropped {pct_move*100:.2f}% in last minute ({prev_price:.2f} -> {current_price:.2f})"))

    return {
        "price": current_price,
        "sma_short": sma_short_now,
        "sma_long": sma_long_now,
        "rsi": rsi_now,
        "alerts": alerts,
        "time": df.index[-1]
    }

def human_msg_from_alerts(info):
    lines = []
    price = info["price"]
    lines.append(f"{TICKER} {price:.2f} at {info['time']}")
    for tag, txt in info["alerts"]:
        lines.append(f"{tag}: {txt}")
    return "\n".join(lines)

# ---------------- MAIN ----------------
def main_loop():
    log("JP Monitor started. Press Ctrl+C to stop.")
    seen_alerts = set()  # avoid duplicate telegram spam for same minute event
    try:
        while True:
            now = dt.datetime.now()
            if not in_market_hours(now):
                log("Outside market hours. Sleeping for 60s.")
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            df = fetch_minute_data(TICKER)
            if df is None:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            info = analyze_and_alert(df)
            if not info:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            alerts = info["alerts"]
            if alerts:
                key = (info["time"], tuple(a[0] for a in alerts))
                if key not in seen_alerts:
                    msg = human_msg_from_alerts(info)
                    log("ALERT:\n" + msg)
                    # Desktop notify
                    desktop_notify("JP Monitor", msg.replace("\n", " | "))
                    # Telegram
                    send_telegram(msg)
                    # Mark seen
                    seen_alerts.add(key)
                else:
                    # already sent this exact alert group for the same minute
                    pass
            else:
                # print heartbeat
                log(f"No alert. Price {info['price']:.2f} | SMA_short {info['sma_short']:.2f} SMA_long {info['sma_long']:.2f} RSI {info['rsi']:.1f}")

            # wait
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        log("Stopped by user.")
    except Exception as e:
        log(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main_loop()
