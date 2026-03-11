import logging
from datetime import datetime, timedelta
from pytz import timezone 
import pandas as pd
from stock_analyzer import analyze_bollinger_bands_status, MIN_DATA_FOR_ANALYSIS

def find_impression_stocks(analyzer, results, t0_gain_threshold=0.0, t1_gain_threshold=8.0, t2_gain_threshold=10.0):
    """
    從一次篩選結果中，進階過濾出符合『印象派』邏輯的飆股名單。
    """
    impression_stocks = []
    taipei_tz = timezone('Asia/Taipei')
    today = datetime.now(taipei_tz).date()
    
    # 使用交易日計算 (BDay) 確保日期判斷精準
    one_trading_day_ago = (today - pd.tseries.offsets.BDay(1)).date()
    two_trading_days_ago = (today - pd.tseries.offsets.BDay(2)).date()
    
    logging.info(f"二次篩選執行中: T={today}, T-1={one_trading_day_ago}, T-2={two_trading_days_ago}")

    for result in results:
        stock_code_raw = result.get("代碼", "")
        stock_category = result.get("類別", "") # 確保網頁能顯示產業類別
        
        # 🌟 解決報錯的核心：用迴圈比對字典，不再呼叫不存在的 _resolve_ticker
        full_ticker = None
        for t_key in analyzer.ticker_names.keys():
            if t_key.startswith(str(stock_code_raw) + "."):
                full_ticker = t_key
                break
        
        if not full_ticker:
            continue
        
        # 取得個股數據並檢查長度
        df = analyzer.all_daily_data_in_memory.get(full_ticker)
        if df is None or len(df) < MIN_DATA_FOR_ANALYSIS:
            continue 
        
        observation_date_str = result.get("觀察點日期", "")
        try:
            observation_date = pd.to_datetime(observation_date_str).date()
        except Exception:
            continue
        
        # 觀察點價格處理
        observation_price_str = str(result.get("觀察點價格", "0")).replace(',', '')
        try:
            observation_price = float(observation_price_str)
            if observation_price == 0: continue
        except Exception:
            continue
            
        latest_price = float(df['Close'].iloc[-1])
        latest_volume = float(df['Volume'].iloc[-1])
        volume_ma20 = float(df['Volume'].rolling(window=20).mean().iloc[-1])
        
        # 基本門檻：成交量需大於 20 日均量的 1.2 倍
        is_volume_breakthrough = latest_volume > (volume_ma20 * 1.2)
        total_gain_percent = ((latest_price - observation_price) / observation_price) * 100
        
        # 格式化張數
        volume_in_lots = int(latest_volume / 1000)
        
        # 取得布林通道狀態
        bb_status = analyze_bollinger_bands_status(df)
        
        # --- T-2 規則 (兩日前偵測到，且兩日累計漲幅達標) ---
        if observation_date == two_trading_days_ago:
            if total_gain_percent > t2_gain_threshold and is_volume_breakthrough:
                impression_stocks.append({
                    "代碼": stock_code_raw, "名稱": result.get("名稱", ""), "類別": stock_category,
                    "觀察點日期": observation_date_str, "觀察點價格": f"{observation_price:.2f}",
                    "最新價格": f"{latest_price:.2f}", "期間": "2日",
                    "漲跌幅百分比": f"{total_gain_percent:.2f}%",
                    "成交量": f"{volume_in_lots:,}",
                    "raw_volume": int(latest_volume),
                    "布林通道狀態": bb_status
                })
        
        # --- T-1 規則 (昨日偵測到，且今日續強) ---
        elif observation_date == one_trading_day_ago:
            if total_gain_percent > t1_gain_threshold and is_volume_breakthrough:
                impression_stocks.append({
                    "代碼": stock_code_raw, "名稱": result.get("名稱", ""), "類別": stock_category,
                    "觀察點日期": observation_date_str, "觀察點價格": f"{observation_price:.2f}",
                    "最新價格": f"{latest_price:.2f}", "期間": "1日",
                    "漲跌幅百分比": f"{total_gain_percent:.2f}%",
                    "成交量": f"{volume_in_lots:,}", 
                    "raw_volume": int(latest_volume),
                    "布林通道狀態": bb_status
                })

        # --- T (今日) 規則 (布林起漲判斷) ---
        elif observation_date == today:
            latest_open = float(df['Open'].iloc[-1])
            latest_high = float(df['High'].iloc[-1])
            t0_max_gain_percent = ((latest_high - latest_open) / latest_open) * 100 if latest_open != 0 else 0
            
            # 條件：最高漲幅 > 閾值 且 處於起漲/飆股格局 且 成交量通過
            if t0_max_gain_percent > t0_gain_threshold and \
               (bb_status == "起漲時刻" or bb_status == "飆股格局") and \
               is_volume_breakthrough:
                
                impression_stocks.append({
                    "代碼": stock_code_raw, "名稱": result.get("名稱", ""), "類別": stock_category,
                    "觀察點日期": observation_date_str, 
                    "觀察點價格": f"{latest_open:.2f}", 
                    "最新價格": f"{latest_price:.2f}", 
                    "期間": "當日",
                    "漲跌幅百分比": f"{t0_max_gain_percent:.2f}%",
                    "成交量": f"{volume_in_lots:,}",
                    "raw_volume": int(latest_volume),
                    "布林通道狀態": bb_status
                })
    
    return impression_stocks
