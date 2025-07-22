from flask import Flask, jsonify
import finnhub
import pandas as pd
from ta.trend import MACD
import talib
import time
import pytz
from datetime import datetime
import threading
import json
import websocket
import requests
import os

app = Flask(__name__)

# Finnhub and Telegram configuration
api_key = "d1vhbphr01qqgeelhtj0d1vhbphr01qqgeelhtjg"  # Replace with your key or use os.getenv("FINNHUB_API_KEY")
finnhub_client = finnhub.Client(api_key)
TELEGRAM_TOKEN = os.getenv("7769081812:AAG1nMhPiFMvsVdmkTWr6k-p78e-Lj9atRQ")  # e.g., "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
TELEGRAM_CHAT_ID = os.getenv("1131774812")  # e.g., "123456789"

# Markets (Forex and Crypto matching Olymp Trade)
markets = ["EUR/USD", "GBP/USD", "USD/JPY", "BTC/USD", "ETH/USD"]
indicators = {market: {"rsi": 50, "macd": 0, "macd_signal": 0, "ema50": 0, "ema200": 0,
                      "prev_rsi": 50, "prev_macd": 0, "prev_macd_signal": 0, "prev_ema50": 0, "prev_ema200": 0} for market in markets}
prices = {market: 0 for market in markets}

def on_message(ws, message):
    data = json.loads(message)
    if 'data' in data:
        for quote in data['data']:
            market = quote['s']
            if market in ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "BTCUSD", "ETHUSD"]:
                mapped_market = {"EURUSD=X": "EUR/USD", "GBPUSD=X": "GBP/USD", "USDJPY=X": "USD/JPY"}.get(market, market)
                prices[mapped_market] = quote['p']

def on_error(ws, error):
    print(f"WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("WebSocket closed")

def on_open(ws):
    ws.send(json.dumps({"type": "subscribe", "symbol": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "BTCUSD", "ETHUSD"]}))

def start_websocket():
    ws = websocket.WebSocketApp(
        f"wss://ws.finnhub.io?token={api_key}",
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )
    ws.run_forever()

def calculate_indicators():
    while True:
        ist = pytz.timezone("Asia/Kolkata")
        current_time = datetime.now(ist)
        if current_time.hour >= 0 and current_time.hour < 23:
            for market in markets:
                current_price = prices[market]
                if current_price:
                    df = pd.DataFrame([{"close": current_price}])
                    rsi = talib.RSI(df['close'], timeperiod=14).iloc[-1] if len(df) >= 14 else indicators[market]["rsi"]
                    macd = MACD(df['close']).macd()[-1] if len(df) >= 26 else indicators[market]["macd"]
                    macd_signal = MACD(df['close']).macd_signal()[-1] if len(df) >= 26 else indicators[market]["macd_signal"]
                    ema50 = talib.EMA(df['close'], timeperiod=50).iloc[-1] if len(df) >= 50 else indicators[market]["ema50"]
                    ema200 = talib.EMA(df['close'], timeperiod=200).iloc[-1] if len(df) >= 200 else indicators[market]["ema200"]
                    prev_rsi = indicators[market]["rsi"]
                    prev_macd = indicators[market]["macd"]
                    prev_macd_signal = indicators[market]["macd_signal"]
                    prev_ema50 = indicators[market]["ema50"]
                    prev_ema200 = indicators[market]["ema200"]
                    indicators[market] = {"rsi": rsi, "macd": macd, "macd_signal": macd_signal, "ema50": ema50, "ema200": ema200,
                                        "prev_rsi": prev_rsi, "prev_macd": prev_macd, "prev_macd_signal": prev_macd_signal,
                                        "prev_ema50": prev_ema50, "prev_ema200": prev_ema200}
                    rsi_change = abs(rsi - prev_rsi) if rsi and prev_rsi else 0
                    macd_change = abs(macd - prev_macd) if macd and prev_macd else 0
                    ema_change = abs(ema50 - prev_ema50) if ema50 and prev_ema50 else 0
                    if (rsi < 30 or ema50 > ema200) and macd > macd_signal and prev_macd <= prev_macd_signal:
                        signal_type = "up"
                        reason = f"Oversold RSI ({rsi:.1f}) or EMA50 > EMA200 with bullish MACD crossover"
                        if rsi_change > 5 or macd_change > 1 or ema_change > 0.5:
                            duration = "1m"
                        elif rsi_change > 3 or macd_change > 0.5 or ema_change > 0.3:
                            duration = "5m"
                        elif rsi_change > 2 or macd_change > 0.3 or ema_change > 0.2:
                            duration = "10m"
                        else:
                            duration = "15m"
                        send_telegram_signal(market, signal_type, reason, duration, current_time, current_price)
                    elif (rsi > 70 or ema50 < ema200) and macd < macd_signal and prev_macd >= prev_macd_signal:
                        signal_type = "down"
                        reason = f"Overbought RSI ({rsi:.1f}) or EMA50 < EMA200 with bearish MACD crossover"
                        if rsi_change > 5 or macd_change > 1 or ema_change > 0.5:
                            duration = "1m"
                        elif rsi_change > 3 or macd_change > 0.5 or ema_change > 0.3:
                            duration = "5m"
                        elif rsi_change > 2 or macd_change > 0.3 or ema_change > 0.2:
                            duration = "10m"
                        else:
                            duration = "15m"
                        send_telegram_signal(market, signal_type, reason, duration, current_time, current_price)
        time.sleep(1)

def send_telegram_signal(market, signal_type, reason, duration, current_time, current_price):
    message = f"Make {signal_type} on {market} at {current_time.strftime('%Y-%m-%d %H:%M:%S')}\nReason: {reason}\nTrade for: {duration}\nCurrent Price: {current_price:.2f}"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

# Start WebSocket and indicator loop in separate threads
threading.Thread(target=start_websocket, daemon=True).start()
threading.Thread(target=calculate_indicators, daemon=True).start()

@app.route('/')
def home():
    return "Forex & Crypto Signal App Online"

@app.route('/signal')
def get_signal():
    return jsonify({"status": "Running", "check_interval": "1 second"})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
