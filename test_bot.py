import MetaTrader5 as mt5
import traceback
from datetime import datetime

def ema(prices, period):
    k = 2.0 / (period + 1)
    result = [prices[0]]
    for p in prices[1:]:
        result.append(p * k + result[-1] * (1 - k))
    return result

def calc_rsi(closes, period=14):
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_adx(highs, lows, closes, period=14):
    try:
        tr_list, pdm_list, ndm_list = [], [], []
        for i in range(1, len(closes)):
            tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
            pdm = max(highs[i]-highs[i-1], 0) if highs[i]-highs[i-1] > lows[i-1]-lows[i] else 0
            ndm = max(lows[i-1]-lows[i], 0) if lows[i-1]-lows[i] > highs[i]-highs[i-1] else 0
            tr_list.append(tr); pdm_list.append(pdm); ndm_list.append(ndm)
        atr = sum(tr_list[-period:]) / period
        if atr == 0: return 0
        pdi = (sum(pdm_list[-period:]) / period) / atr * 100
        ndi = (sum(ndm_list[-period:]) / period) / atr * 100
        dx = abs(pdi-ndi) / (pdi+ndi) * 100 if (pdi+ndi) > 0 else 0
        return dx
    except: return 0

def calc_macd(closes):
    e12 = ema(closes, 12)
    e26 = ema(closes, 26)
    macd_line = [a-b for a,b in zip(e12, e26)]
    signal_line = ema(macd_line, 9)
    hist = [m-s for m,s in zip(macd_line, signal_line)]
    return macd_line[-1], signal_line[-1], hist[-1], hist[-2]

def get_4h_trend(symbol):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 250)
    if rates is None or len(rates) < 50:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 250)
    if rates is None or len(rates) < 50:
        return "BUY", 25
    closes = [r['close'] for r in rates]
    highs  = [r['high']  for r in rates]
    lows   = [r['low']   for r in rates]
    e200 = ema(closes, 200)
    adx  = calc_adx(highs, lows, closes, 14)
    trend = "BUY" if closes[-1] > e200[-1] else "SELL"
    return trend, adx

try:
    print("Starting debug bot...")
    mt5.initialize()
    
    info = mt5.account_info()
    print(f"Balance: {info.balance}")
    
    for symbol in ['BTCUSDm', 'ETHUSDm', 'XAUUSDm']:
        print(f"\n--- {symbol} ---")
        
        trend, adx = get_4h_trend(symbol)
        print(f"4H Trend: {trend} | ADX: {adx:.1f}")
        
        rates5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 100)
        if rates5 is None or len(rates5) < 50:
            print("M5 data not enough!")
            continue
            
        closes = [r['close'] for r in rates5]
        highs  = [r['high']  for r in rates5]
        lows   = [r['low']   for r in rates5]
        
        e9  = ema(closes, 9)
        e50 = ema(closes, 50)
        rsi = calc_rsi(closes)
        macd_l, macd_s, macd_h, macd_h_prev = calc_macd(closes)
        
        print(f"EMA9: {e9[-1]:.2f} | EMA50: {e50[-1]:.2f}")
        print(f"RSI: {rsi:.1f} | MACD: {macd_h:.4f}")
        
        # Score
        score = 0
        score += 25  # trend
        if adx >= 30: score += 20
        elif adx >= 20: score += 12
        if trend == "BUY" and 35 <= rsi <= 55: score += 20
        elif trend == "SELL" and 45 <= rsi <= 65: score += 20
        if trend == "BUY" and macd_h > 0: score += 15
        elif trend == "SELL" and macd_h < 0: score += 15
        score += 10  # atr
        if trend == "BUY" and closes[-1] > e50[-1]: score += 10
        elif trend == "SELL" and closes[-1] < e50[-1]: score += 10
        
        print(f"Score: {score}/100")
        print(f"Signal: {'TRADE!' if score >= 60 else 'WAIT'}")

except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
finally:
    mt5.shutdown()