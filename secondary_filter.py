import logging
from datetime import datetime, timedelta
# [新增] 引入 pytz 用於時區
from pytz import timezone 
from stock_analyzer import (
    StockAnalyzer, 
    # [新增] 從 stock_analyzer 導入必要的函數和常量
    analyze_bollinger_bands_status,
    MIN_DATA_FOR_ANALYSIS
)
import pandas as pd

def run_impression_stock_filter(results, t0_gain_threshold, t1_gain_threshold, t2_gain_threshold):
    """原 run_impression_stock_filter 计算逻辑（从 stock_analyzer 提取）"""
    analyzer = StockAnalyzer()  # 或传入
    impression_stocks = analyzer.find_impression_stocks(
        results, 
        t0_gain_threshold=float(t0_gain_threshold),
        t1_gain_threshold=float(t1_gain_threshold), 
        t2_gain_threshold=float(t2_gain_threshold)
    )
    logging.info(f"二次篩選完成，共找到 {len(impression_stocks)} 檔印象派飆股。")
    return impression_stocks

def _display_impression_results(impression_stocks, root):
    """显示结果 UI（从 UI 移动到这里，或保持在 UI 中调用）"""
    # [原 _display_impression_results 代码：Toplevel 窗口、Treeview、导出按钮]
    # 导出按钮：command=lambda: export_impression_stocks_to_pdf(impression_stocks, root)
    pass  # 完整复制原代码

# [find_impression_stocks 从 stock_analyzer 复制完整逻辑]
def find_impression_stocks(self, results, t0_gain_threshold=0.0, t1_gain_threshold=8.0, t2_gain_threshold=10.0):
    """从 stock_analyzer 提取的印象派飆股计算"""
    impression_stocks = []
    taipei_tz = timezone('Asia/Taipei')
    today = datetime.now(taipei_tz).date()
    # 警告: 以下日期計算使用日曆日，未跳過週末/假日。
    one_trading_day_ago = today - timedelta(days=1)
    two_trading_days_ago = today - timedelta(days=2)
    
    for result in results:
        stock_code_raw = result.get("代碼", "")
        full_ticker = self._resolve_ticker(stock_code_raw)
        if not full_ticker: continue
        
        df = self.all_daily_data_in_memory.get(full_ticker)
        # 使用 MIN_DATA_FOR_ANALYSIS (已新增匯入)
        if df is None or len(df) < MIN_DATA_FOR_ANALYSIS: continue 
        
        observation_date_str = result.get("觀察點日期", "")
        try:
            observation_date = pd.to_datetime(observation_date_str).date()
        except:
            continue
        
        observation_price_str = result.get("觀察點價格", "")
        try:
            observation_price = float(observation_price_str)
            if observation_price == 0: continue
        except:
            continue
            
        latest_price = df['Close'].iloc[-1]
        latest_volume = df['Volume'].iloc[-1]
        volume_ma20 = df['Volume'].rolling(window=20).mean().iloc[-1]
        is_volume_breakthrough = latest_volume > (volume_ma20 * 1.5)
        total_gain_percent = ((latest_price - observation_price) / observation_price) * 100
        
        # T-2 规则
        if observation_date == two_trading_days_ago:
            if total_gain_percent > t2_gain_threshold and is_volume_breakthrough:
                # 準備輸出欄位
                volume_in_lots = latest_volume / 1000 # 假設 1000 股為 1 張
                impression_stocks.append({
                    "代碼": stock_code_raw, "名稱": result.get("名稱", ""),
                    "觀察點日期": observation_date_str, "觀察點價格": f"{observation_price:.2f}",
                    "最新價格": f"{latest_price:.2f}", "期間": "2日",
                    "漲跌幅": f"{total_gain_percent:.2f}%",
                    "當日成交量": f"{int(volume_in_lots):,}",
                    "raw_volume": latest_volume,
                    "full_ticker": full_ticker
                })
        
        # T-1 規則 (從 stock_analyzer.py 補齊 T-1 邏輯)
        elif observation_date == one_trading_day_ago:
            # T-1 規則：漲幅大於 t1_gain_threshold 且成交量突破
            if total_gain_percent > t1_gain_threshold and is_volume_breakthrough:
                # 準備輸出欄位
                volume_in_lots = latest_volume / 1000 # 假設 1000 股為 1 張
                impression_stocks.append({
                    "代碼": stock_code_raw, "名稱": result.get("名稱", ""),
                    "觀察點日期": observation_date_str, "觀察點價格": f"{observation_price:.2f}",
                    "最新價格": f"{latest_price:.2f}", "期間": "1日",
                    "漲跌幅": f"{total_gain_percent:.2f}%",
                    "當日成交量": f"{int(volume_in_lots):,}", 
                    "raw_volume": latest_volume, 
                    "full_ticker": full_ticker
                })

        # --- T (今日) 規則 (漲幅、布林狀態、成交量倍數優化) ---
        elif observation_date == today:
            
            # 1. 獲取當日開盤價與最高價
            latest_open = df['Open'].iloc[-1]
            latest_high = df['High'].iloc[-1]
            
            # 2. 計算 T日 漲幅 (使用盤中最高價對比開盤價)
            if latest_open == 0:
                t0_max_gain_percent = 0.0
            else:
                t0_max_gain_percent = ((latest_high - latest_open) / latest_open) * 100
            
            # 3. T日 成交量倍數檢查 (新需求: 預設 1.2x)
            T0_VOLUME_MULTIPLIER = 1.2
            # 依賴於前面計算好的 latest_volume 和 volume_ma20 變數
            is_t0_volume_pass = latest_volume > (volume_ma20 * T0_VOLUME_MULTIPLIER)

            # 4. 檢查布林狀態
            # analyze_bollinger_bands_status(df) 已新增匯入
            bb_status = analyze_bollinger_bands_status(df) 
            
            # 5. 更新篩選條件:
            # (1) T日最高漲幅 > 閾值 AND 
            # (2) 布林狀態強勢 AND 
            # (3) 成交量倍數通過
            if t0_max_gain_percent > t0_gain_threshold and \
               (bb_status == "起漲時刻" or bb_status == "飆股格局") and \
               is_t0_volume_pass:
                
                # 準備輸出欄位
                volume_in_lots = latest_volume / 1000 # 假設 1000 股為 1 張

                impression_stocks.append({
                    "代碼": stock_code_raw, "名稱": result.get("名稱", ""),
                    "觀察點日期": observation_date_str, 
                    "觀察點價格": f"{latest_open:.2f}",      # 觀察點價格改為今日開盤價
                    "最新價格": f"{latest_price:.2f}", 
                    "期間": "當日",
                    "漲跌幅": f"{t0_max_gain_percent:.2f}% (高/開)", # 顯示 (最高價/開盤價) 漲幅
                    "當日成交量": f"{int(volume_in_lots):,}",
                    "raw_volume": latest_volume, 
                    "full_ticker": full_ticker
                })
    
    return impression_stocks