from flask import Flask
import finnhub
import pandas as pd
import pandas_ta
import websocket
import json
import requests
from datetime import datetime, time
import telegram
import os
import asyncio
import threading
import pytz

app = Flask(__name__)

# Environment variables
FINNHUB_API_KEY = os.getenv('d1vhbphr01qqgeelhtj0d1vhbphr01qqgeelhtjg')
TELEGRAM_TOKEN = os.getenv('7769081812:AAG1nMhPiFMvsVdmkTWr6k-p78e-Lj9atRQ')
TELEGRAM_CHAT_ID = os.getenv('1131774812')


# Trading parameters
SYMBOLS = ['EUR/USD', 'GBP/USD', 'USD/JPY', 'BINANCE:BTCUSDT', 'BINANCE:ETHUSDT']
DURATIONS = ['1m', '5m', '10m', '15m']
IST = pytz.timezone('Asia/Kolkata')

# Store latest price data
price_data = {symbol: [] for symbol in SYMBOLS}

# Check if current time is within trading window (12:00 PM - 4:00 PM IST)
def is_trading_time():
    now = datetime.now(IST).time()
    start_time = time(12, 0)
    end_time = time(16, 0)
    return start_time <= now <= end_time

# Calculate indicators and generate signals
def calculate_indicators(df):
    df['rsi'] = pandas_ta.rsi(df['close'], length=14)
    df['ema50'] = pandas_ta.ema(df['close'], length=50)
    df['ema200'] = pandas_ta.ema(df['close'], length=200)
    df['macd'] = pandas_ta.macd(df['close'], fast=12, slow=26, signal=9)['MACD_12_26_9']
    df['macd_signal'] = pandas_ta.macd(df['close'], fast=12, slow=26, signal=9)['MACDs_12_26_9']
    return df

def generate_signal(symbol, df):
    if len(df) < 200:  # Ensure enough data for EMA200
        return None
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    # Signal logic: RSI overbought/oversold + MACD crossover + EMA alignment
    if (latest['rsi'] > 70 and latest['macd'] < latest['macd_signal'] and prev['macd'] >= prev['macd_signal'] and
        latest['ema50'] < latest['ema200']):
        reason = "RSI overbought + MACD bearish crossover + EMA50 below EMA200"
        return {'direction': 'down', 'reason': reason, 'duration': '5m', 'price': latest['close']}
    elif (latest['rsi'] < 30 and latest['macd'] > latest['macd_signal'] and prev['macd'] <= prev['macd_signal'] and
          latest['ema50'] > latest['ema200']):
        reason = "RSI oversold + MACD bullish crossover + EMA50 above EMA200"
        return {'direction': 'up', 'reason': reason, 'duration': '5m', 'price': latest['close']}
    return None

# Send signal to Telegram
async def send_telegram_message(message):
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

# WebSocket handler
def on_message(ws, message):
    if not is_trading_time():
        return
    data = json.loads(message)
    if 'data' in data:
        for tick in data['data']:
            symbol = tick['s']
            price = tick['p']
            timestamp = datetime.fromtimestamp(tick['t'] / 1000, tz=IST)
            price_data[symbol].append({'time': timestamp, 'close': price})
            # Keep only last 300 data points to avoid memory issues
            if len(price_data[symbol]) > 300:
                price_data[symbol] = price_data[symbol][-300:]
            # Convert to DataFrame and calculate indicators
            df = pd.DataFrame(price_data[symbol])
            df = calculate_indicators(df)
            signal = generate_signal(symbol, df)
            if signal:
                message = (f"Make {signal['direction']} on {symbol} at {timestamp.strftime('%H:%M:%S %Z')}, "
                          f"Reason: {signal['reason']}, Trade for: {signal['duration']}, "
                          f"Current Price: {signal['price']}")
                asyncio.run(send_telegram_message(message))

def on_error(ws, error):
    print(f"WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("WebSocket closed")

def on_open(ws):
    for symbol in SYMBOLS:
        ws.send(json.dumps({'type': 'subscribe', 'symbol': symbol}))

# Start WebSocket in a separate thread
def start_websocket():
    ws = websocket.WebSocketApp(
        f"wss://ws.finnhub.io?token={FINNHUB_API_KEY}",
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )
    ws.run_forever()

@app.route('/')
def index():
    return "Forex/Crypto Signal App is running!"

if __name__ == '__main__':
    # Start WebSocket in a background thread
    threading.Thread(target=start_websocket, daemon=True).start()
    # Run Flask app
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
