"""
PROJECT: SHREEK_SCALP - SCALPING ANALYSIS SYSTEM
Version: 1.0 | Codename: شريك مشروع 2
Timeframes: M30 -> M15 -> M5
Strategies: Breakout + EMA Cross + Session Open Breakout
Risk: Max 3% per trade | Targets: 3 TPs
AI: Google Gemini 2.5 Flash
REQUIRED: pip install google-genai python-telegram-bot MetaTrader5
"""

import asyncio
import sys

from google import genai
import MetaTrader5 as mt5
from telegram import Update, BotCommand, BotCommandScopeDefault, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.request import HTTPXRequest
from datetime import datetime, timezone
import logging

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.WARNING)

# ─── 1. CONFIGURATION ─────────────────────────────────────────
TELEGRAM_TOKEN = "8684990616:AAGc_ZQThP4C-9yCtzi9bdWdScGEAHkQ5eY"
GEMINI_API_KEY = "AQ.Ab8RN6KUbO7BnKwyCkHvOksqDdrir6EM-jpUz9S6hAPV_88RRg"

# Proxy: None = direct | "socks5://127.0.0.1:1080" | "http://127.0.0.1:8080"
PROXY_URL = None

ai_client = genai.Client(api_key=GEMINI_API_KEY)

# ─── 2. SCALP DATA FUNCTION ───────────────────────────────────
def get_scalp_data(symbol):
    if not mt5.initialize():
        return None

    if any(x in symbol for x in ["XAU", "BTC", "XBR", "OIL"]):
        decimals = 2
    elif "JPY" in symbol:
        decimals = 3
    else:
        decimals = 5

    timeframes = {
        "M30": (mt5.TIMEFRAME_M30, 60),
        "M15": (mt5.TIMEFRAME_M15, 80),
        "M5":  (mt5.TIMEFRAME_M5,  100),
    }

    result = {}
    for name, (tf, count) in timeframes.items():
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is not None:
            candles = [
                f"O:{r['open']:.{decimals}f} H:{r['high']:.{decimals}f} L:{r['low']:.{decimals}f} C:{r['close']:.{decimals}f} V:{r['tick_volume']}"
                for r in rates
            ]
            result[name] = " | ".join(candles)
        else:
            result[name] = "NO DATA"

    return result

# ─── 3. SYSTEM PROMPT ─────────────────────────────────────────
SCALP_SYSTEM_PROMPT = """
You are an elite scalping analyst specializing in short-term high-probability setups.
Timeframe hierarchy: M30 (bias) -> M15 (confirmation) -> M5 (entry trigger).
You apply THREE strategies simultaneously and score each setup out of 10.
Only recommend trades scoring 6/10 or higher.

DECIMAL PRECISION (STRICT):
- EURUSD and forex pairs: 5 decimal places. Example: 1.13245
- XAUUSD: 2 decimal places. Example: 3312.75
- BTCUSD: 2 decimal places. Example: 94521.30
- NEVER round prices. Use exact values from raw data.

LANGUAGE RULES:
- Full analysis: English only
- "--- ملخص الصفقة ---" section: Arabic only
- "--- QUICK ENTRY ---" section: English only, numbers only

════════════════════════════════════════
STRATEGY 1 — BREAKOUT CONFIRMATION
════════════════════════════════════════
Definition: Price breaks a key consolidation level with momentum.

DETECTION RULES:
- Identify consolidation range on M30: at least 6 candles ranging within 20-40 pips
- Breakout candle: body must be > 65% of total candle range
- Volume confirmation: breakout candle volume > 1.5x average of last 20 candles
- Retest: wait for price to retest broken level on M15 or M5
- Entry: on retest confirmation candle (Pin Bar or Engulfing)

SCORING (max 4 points):
+1: Consolidation clear (6+ candles, tight range)
+1: Breakout candle body > 65%
+1: Volume spike confirmed
+1: Retest completed with confirmation candle

════════════════════════════════════════
STRATEGY 2 — EMA CROSSOVER + RSI FILTER
════════════════════════════════════════
Definition: EMA 9 crosses EMA 21 with RSI confirming momentum direction.

DETECTION RULES (calculate from candle data):
EMA 9 approximation: average of last 9 closing prices (weighted toward recent)
EMA 21 approximation: average of last 21 closing prices
- Bullish Cross: EMA9 crosses above EMA21 + RSI between 45-65 (not overbought)
- Bearish Cross: EMA9 crosses below EMA21 + RSI between 35-55 (not oversold)
RSI approximation: compare last 14 candles average gain vs average loss
- RSI > 70: overbought — avoid BUY
- RSI < 30: oversold — avoid SELL
- Entry on M5 after cross confirmed on M15

SCORING (max 3 points):
+1: EMA cross confirmed on M15
+1: RSI in valid zone (45-65 for BUY, 35-55 for SELL)
+1: M30 trend aligns with cross direction

════════════════════════════════════════
STRATEGY 3 — SESSION OPEN BREAKOUT
════════════════════════════════════════
Definition: Trade the first directional move of London or New York session.

SESSION TIMES (UTC):
- London Open: 07:00-09:00 UTC
- New York Open: 13:00-15:00 UTC
- Asian session (low volatility): AVOID trading 00:00-06:00 UTC

DETECTION RULES:
- Identify the range of the last 4 candles before session open (pre-session consolidation)
- Mark range high and low
- Breakout of this range in first 15-30 min of session = valid signal
- Direction confirms with M30 bias

SCORING (max 3 points):
+1: Currently within valid session window (London or NY)
+1: Pre-session range clearly defined (tight consolidation)
+1: Breakout direction aligns with M30 bias

════════════════════════════════════════
COMPOSITE SCORING SYSTEM
════════════════════════════════════════
Total score = Strategy 1 (max 4) + Strategy 2 (max 3) + Strategy 3 (max 3) = max 10

Score thresholds:
- 8-10: STRONG SIGNAL — 3% risk allowed
- 6-7:  VALID SIGNAL — 1.5% risk allowed
- 4-5:  WEAK — NO TRADE
- 0-3:  NO TRADE

════════════════════════════════════════
RISK MANAGEMENT — SCALP RULES
════════════════════════════════════════
- Max risk per trade: 3% of account balance
- Stop Loss: beyond breakout/retest candle + 5 pip buffer (forex) / 50 cents (gold) / $100 (BTC)
- TP1 (1:1.5): Partial exit — move SL to breakeven
- TP2 (1:2.5): Primary target — close 50%
- TP3 (1:4.0): Maximum extension — trail remaining
- Daily loss limit: 5% (stop all trading)
- Max 3 scalp trades per session
- No trading 30 min before/after major news

STRICT SCALP RULES:
- No trades during Asian session (00:00-06:00 UTC) — low volatility
- No trades if spread > 3 pips (forex) or > $1 (gold)
- Minimum candle body for entry: 40% of range
- Always check M30 bias before M5 entry

════════════════════════════════════════
ENTRY CHECKLIST (all 7 required for TRADE)
════════════════════════════════════════
[ ] 1. M30 bias clear (bullish or bearish)
[ ] 2. At least ONE strategy scored 3+ points
[ ] 3. Total composite score >= 6/10
[ ] 4. Valid session window (London or NY)
[ ] 5. Confirmation candle on M5
[ ] 6. RRR >= 1.5 minimum
[ ] 7. No major news in next 30 minutes

════════════════════════════════════════
OUTPUT FORMAT (follow exactly)
════════════════════════════════════════

===== SHREEK SCALP ANALYSIS =====
SYMBOL: [symbol] | DATE: [date] | SESSION: [London/NewYork/Asian/Off-Hours]

--- M30 BIAS ---
Trend: [Bullish/Bearish/Ranging]
Key High: [price] | Key Low: [price]
EMA9 (approx): [price] | EMA21 (approx): [price]
EMA Alignment: [Bullish/Bearish/Neutral]
RSI (approx): [value]
Volume Trend: [Increasing/Decreasing/Neutral]
M30 Bias: [BUY/SELL/NEUTRAL]

--- M15 CONFIRMATION ---
Trend: [Bullish/Bearish/Ranging]
EMA Cross: [Yes-Bullish/Yes-Bearish/No]
Consolidation Zone: [price range or None]
Breakout Level: [price or None]
Breakout Confirmed: [Yes/No]
Retest: [Yes/No/Pending]
M15 Signal: [CONFIRMS/CONTRADICTS/NEUTRAL]

--- M5 ENTRY TRIGGER ---
Current Price: [price]
Confirmation Candle: [Pin Bar/Engulfing/None]
Candle Body %: [value]%
Entry Trigger: [Ready/Pending/None]

--- STRATEGY SCORING ---
Strategy 1 — Breakout:      [X/4] | [brief reason]
Strategy 2 — EMA+RSI:       [X/3] | [brief reason]
Strategy 3 — Session Open:  [X/3] | [brief reason]
─────────────────────────────────
COMPOSITE SCORE:            [X/10]
Signal Strength:            [STRONG/VALID/WEAK/NO TRADE]

--- TRADE SETUP ---
Signal: [BUY/SELL/NO TRADE]
No Trade Reason: [if NO TRADE: exact reason]
Entry Zone: [price range]
Stop Loss: [exact price]
TP1 (1:1.5): [price]
TP2 (1:2.5): [price]
TP3 (1:4.0): [price]
RRR to TP2: [value]
Checklist Passed: [X of 7]
Items Failed: [list or None]

--- RISK CALCULATION ---
Account Balance: [USD]
Score-Based Risk: [1.5% or 3%]
Risk Amount: [USD]
1.5% = [USD] | 3% = [USD]
Daily Loss Limit (5%): [USD]
Reason: [one precise sentence]

--- EXIT RULES ---
TP1 Hit: Move SL to breakeven immediately. Hold for TP2.
TP2 Hit: Close 50%. Trail remaining position to TP3.
TP3 Hit: Full close. Log trade result.
SL Hit: Accept loss. Wait for next valid setup. No revenge trading.
Invalidation: Price closes back beyond breakout level = exit immediately.

--- ملخص الصفقة ---
[اكتب 3-4 جمل بالعربية فقط تشرح: (1) اتجاه السوق الحالي، (2) الاستراتيجية التي أعطت الإشارة، (3) سبب الدخول أو عدم الدخول، (4) النقاط التي يجب مراقبتها]
===========================

--- QUICK ENTRY ---
Signal: [BUY / SELL / NO TRADE]
Score: [X/10]
Session: [London/NewYork/Other]
Entry: [price]
SL: [price]
TP1: [price]
TP2: [price]
TP3: [price]
Risk: [%] = [USD]
─────────────────
"""

# ─── 4. ANALYSIS FUNCTION ─────────────────────────────────────
def get_scalp_analysis(symbol):
    try:
        data = get_scalp_data(symbol)
        if data is None:
            return "MT5 Connection Failed."

        balance = None
        if mt5.initialize():
            acc = mt5.account_info()
            balance = acc.balance if acc else None

        current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
        utc_hour = datetime.now(timezone.utc).hour

        if 7 <= utc_hour < 12:
            session = "London Open"
        elif 12 <= utc_hour < 17:
            session = "New York Open"
        elif 17 <= utc_hour < 21:
            session = "New York Afternoon"
        elif 0 <= utc_hour < 7:
            session = "Asian Session (Low Volatility)"
        else:
            session = "Off-Hours"

        balance_context = (
            f"Account Balance: {balance} USD\n" if balance else ""
        )

        user_prompt = (
            f"Perform full scalping analysis for {symbol}.\n"
            f"{balance_context}"
            f"Current UTC Time: {current_time}\n"
            f"Current Session: {session}\n\n"
            f"M30 DATA (last 60 candles):\n{data['M30']}\n\n"
            f"M15 DATA (last 80 candles):\n{data['M15']}\n\n"
            f"M5 DATA (last 100 candles):\n{data['M5']}\n\n"
            f"MANDATORY: Apply all 3 strategies. Calculate composite score. "
            f"Only issue BUY/SELL if score >= 6/10. "
            f"Calculate RRR explicitly. "
            f"Write ملخص الصفقة in Arabic only."
        )

        response = ai_client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=f"{SCALP_SYSTEM_PROMPT}\n\n{user_prompt}"
        )
        return response.text

    except Exception as e:
        return f"AI Error: {str(e)}"

# ─── 5. TRADE HISTORY ─────────────────────────────────────────
scalp_history = []

# ─── 6. TELEGRAM COMMANDS ─────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "<b>شريك مشروع 2 — Scalping Engine Online</b>\n\n"
        "<b>الأوامر المتاحة:</b>\n"
        "/gold - تحليل سكالب الذهب XAUUSD\n"
        "/euro - تحليل سكالب اليورو EURUSD\n"
        "/btc - تحليل سكالب البيتكوين BTCUSD\n"
        "/scalp - تحليل أي رمز (مثال: /scalp GBPUSD)\n"
        "/symbols - قائمة الرموز المتاحة في MT5\n"
        "/status - حالة الحساب والمخاطرة\n"
        "/session - الجلسة الحالية والتوقيت\n"
        "/history - سجل تحليلات اليوم\n"
        "/settings - إعدادات النظام\n\n"
        "Timeframes: M30 → M15 → M5\n"
        "Strategies: Breakout | EMA Cross | Session Open\n"
        "Min Score to Trade: 6/10\n"
        "Max Risk: 3% | Targets: TP1 / TP2 / TP3"
    )
    await update.message.reply_text(welcome_text, parse_mode="HTML")

async def session_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    utc_hour = datetime.now(timezone.utc).hour
    utc_min  = datetime.now(timezone.utc).minute
    now_str  = datetime.now(timezone.utc).strftime('%H:%M UTC')

    if 7 <= utc_hour < 12:
        session = "London Open — ACTIVE"
        status  = "High volatility. Best time to scalp."
    elif 12 <= utc_hour < 17:
        session = "New York Open — ACTIVE"
        status  = "High volatility. Best time to scalp."
    elif 17 <= utc_hour < 21:
        session = "NY Afternoon — MODERATE"
        status  = "Medium volatility. Be selective."
    elif 0 <= utc_hour < 7:
        session = "Asian Session — LOW"
        status  = "Low volatility. Avoid scalping."
    else:
        session = "Off-Hours"
        status  = "Low activity. Wait for London open."

    msg = (
        f"Current Time: {now_str}\n"
        f"Session: {session}\n"
        f"Status: {status}\n\n"
        f"London Open:   07:00 - 12:00 UTC\n"
        f"New York Open: 13:00 - 17:00 UTC\n"
        f"Asian (avoid): 00:00 - 07:00 UTC"
    )
    await update.message.reply_text(msg)

# ─── SYMBOL CATEGORIES ───────────────────────────────────────
SYMBOL_CATEGORIES = {
    "Forex Major": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"],
    "Forex Minor": ["EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "CHFJPY", "EURCHF"],
    "Metals":      ["XAUUSD", "XAGUSD"],
    "Crypto":      ["BTCUSD", "ETHUSD", "LTCUSD"],
    "Energy":      ["XBRUSD", "USOUSD"],
    "Indices":     ["US30", "US500", "NAS100", "UK100", "GER40"],
}

async def symbols_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not mt5.initialize():
            await update.message.reply_text("MT5 not connected.")
            return

        available = {s.name for s in (mt5.symbols_get() or []) if s.visible}

        keyboards = []
        for category, syms in SYMBOL_CATEGORIES.items():
            row = []
            for sym in syms:
                if sym in available:
                    row.append(InlineKeyboardButton(sym, callback_data=f"scalp:{sym}"))
            if row:
                keyboards.append([InlineKeyboardButton(f"── {category} ──", callback_data="noop")])
                for i in range(0, len(row), 4):
                    keyboards.append(row[i:i+4])

        # Add MT5 available symbols not in categories
        extra = [s for s in available if not any(s in v for v in SYMBOL_CATEGORIES.values())]
        extra_filtered = sorted(extra)[:20]
        if extra_filtered:
            keyboards.append([InlineKeyboardButton("── MT5 Other ──", callback_data="noop")])
            for i in range(0, len(extra_filtered), 4):
                row = [InlineKeyboardButton(s, callback_data=f"scalp:{s}") for s in extra_filtered[i:i+4]]
                keyboards.append(row)

        if not keyboards:
            await update.message.reply_text("No symbols found in MT5.")
            return

        markup = InlineKeyboardMarkup(keyboards)
        await update.message.reply_text(
            "اختر الأصل للتحليل السكالب:",
            reply_markup=markup
        )

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def symbol_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "noop":
        return

    if query.data.startswith("scalp:"):
        symbol = query.data.split(":")[1]
        await query.edit_message_text(f"تحليل {symbol}...\nM30 → M15 → M5\nانتظر 15-25 ثانية...")
        report = get_scalp_analysis(symbol)

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        scalp_history.append(f"{timestamp} | {symbol} | Scalp Analysis")

        if len(report) > 4000:
            parts = [report[i:i+4000] for i in range(0, len(report), 4000)]
            for part in parts:
                await query.message.reply_text(part)
        else:
            await query.message.reply_text(report)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if mt5.initialize():
            acc = mt5.account_info()
            msg = (
                f"Balance: {acc.balance} USD\n"
                f"Equity: {acc.equity} USD\n"
                f"Free Margin: {acc.margin_free} USD\n"
                f"Broker: {acc.company}\n\n"
                f"1.5% Risk: {round(acc.balance * 0.015, 2)} USD\n"
                f"3.0% Risk: {round(acc.balance * 0.03, 2)} USD\n"
                f"Daily Loss Limit (5%): {round(acc.balance * 0.05, 2)} USD\n\n"
                f"Max trades per session: 3\n"
                f"Min score to trade: 6/10"
            )
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text("MT5 not connected.")
    except Exception as e:
        await update.message.reply_text(f"Status Error: {str(e)}")

async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime('%Y-%m-%d')
    today_trades = [t for t in scalp_history if t.startswith(today)]
    if today_trades:
        msg = f"سجل اليوم ({today}):\n\n" + "\n".join(today_trades)
    else:
        msg = f"لا توجد تحليلات مسجلة اليوم ({today})."
    await update.message.reply_text(msg)

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "<b>شريك مشروع 2 — Scalp Settings:</b>\n\n"
        "Model: gemini-2.5-flash\n"
        "Timeframes: M30 → M15 → M5\n"
        "Strategy 1: Breakout + Volume (max 4pts)\n"
        "Strategy 2: EMA 9/21 + RSI Filter (max 3pts)\n"
        "Strategy 3: Session Open Breakout (max 3pts)\n"
        "Min Score to Trade: 6/10\n"
        "Score 6-7: Risk 1.5%\n"
        "Score 8-10: Risk 3%\n"
        "Daily Loss Limit: 5%\n"
        "Max Trades/Session: 3\n"
        "Targets: TP1 (1:1.5) | TP2 (1:2.5) | TP3 (1:4.0)\n"
        "Analysis Language: English + Arabic Summary\n"
        "Avoid: Asian Session | News Events | Spread > 3 pips"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

async def send_scalp(update: Update, symbol: str):
    await update.message.reply_text(
        f"Scalp Analysis: {symbol}\n"
        f"Timeframes: M30 → M15 → M5\n"
        f"Strategies: Breakout | EMA Cross | Session Open\n"
        f"Please wait 15-25 seconds..."
    )
    report = get_scalp_analysis(symbol)

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    scalp_history.append(f"{timestamp} | {symbol} | Scalp Analysis")

    if len(report) > 4000:
        parts = [report[i:i+4000] for i in range(0, len(report), 4000)]
        for part in parts:
            await update.message.reply_text(part)
    else:
        await update.message.reply_text(report)

async def gold_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_scalp(update, "XAUUSD")

async def euro_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_scalp(update, "EURUSD")

async def btc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_scalp(update, "BTCUSD")

async def scalp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0].upper() if context.args else "XAUUSD"
    await send_scalp(update, symbol)

# ─── 7. BOOTSTRAP ─────────────────────────────────────────────
if __name__ == "__main__":
    print("[*] شريك مشروع 2 — Scalp Engine Starting...")

    if PROXY_URL:
        request = HTTPXRequest(
            proxy=PROXY_URL,
            connection_pool_size=8,
            read_timeout=120,
            connect_timeout=120,
            write_timeout=120,
        )
        app = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .request(request)
            .build()
        )
        print(f"[*] Proxy: {PROXY_URL}")
    else:
        app = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .read_timeout(120)
            .connect_timeout(120)
            .write_timeout(120)
            .pool_timeout(30)
            .build()
        )
        print("[*] Direct connection")

    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CallbackQueryHandler(symbol_callback))
    app.add_handler(CommandHandler("gold",     gold_cmd))
    app.add_handler(CommandHandler("euro",     euro_cmd))
    app.add_handler(CommandHandler("btc",      btc_cmd))
    app.add_handler(CommandHandler("scalp",    scalp_cmd))
    app.add_handler(CommandHandler("symbols",  symbols_cmd))
    app.add_handler(CommandHandler("status",   status_cmd))
    app.add_handler(CommandHandler("session",  session_cmd))
    app.add_handler(CommandHandler("history",  history_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))

    async def post_init(app):
        commands = [
            BotCommand("start",    "تشغيل البوت"),
            BotCommand("gold",     "سكالب الذهب XAUUSD"),
            BotCommand("euro",     "سكالب اليورو EURUSD"),
            BotCommand("btc",      "سكالب البيتكوين BTCUSD"),
            BotCommand("scalp",    "سكالب رمز مخصص"),
            BotCommand("symbols",  "قائمة الرموز المتاحة"),
            BotCommand("status",   "حالة الحساب"),
            BotCommand("session",  "الجلسة الحالية"),
            BotCommand("history",  "سجل اليوم"),
            BotCommand("settings", "إعدادات النظام"),
        ]
        await app.bot.set_my_commands(commands, scope=BotCommandScopeDefault())
        print("[*] Commands registered.")

    app.post_init = post_init

    print("[*] Engine Running.")
    try:
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"],
            poll_interval=2.0,
            timeout=30,
            close_loop=False,
        )
    except RuntimeError as e:
        if "Cannot close a running event loop" in str(e) or "Event loop is closed" in str(e):
            pass
        else:
            raise
