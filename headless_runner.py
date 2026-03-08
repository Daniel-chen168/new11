import os
import json
import logging
from datetime import datetime, timedelta
from pytz import timezone
from stock_analyzer import StockAnalyzer
from data_downloader import DataDownloader

# 設定台北時區與存檔路徑
TAIPEI_TZ = timezone('Asia/Taipei')
DOCS_DIR = "docs"

def run_headless_analysis():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    os.makedirs(DOCS_DIR, exist_ok=True)

    # 初始化不含 UI 的分析器
    analyzer = StockAnalyzer()
    downloader = DataDownloader()
    all_tickers = list(analyzer.ticker_names.keys())
    
    logging.info(f"開始執行 GitHub 自動化選股，共 {len(all_tickers)} 檔...")

    # 步驟 1: 下載與計算指標
    downloader.download_and_cache_all_raw_data(all_tickers, None) 
    analyzer.ensure_local_data_and_calculate_indicators(all_tickers)

    # 步驟 2: 執行看漲篩選
    today_str = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d")
    start_date = (datetime.now(TAIPEI_TZ) - timedelta(days=90)).strftime("%Y-%m-%d")
    
    initial_results = analyzer.run_stock_selection(
        all_tickers, start_date, today_str, selection_type="bullish"
    )

    # 步驟 3: 二次篩選 (印象派飆股邏輯)
    impression_stocks = analyzer.find_impression_stocks(initial_results)

    # 步驟 4: 產出網頁 JSON 數據
    web_output = {
        "last_update": datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "stock_count": len(impression_stocks),
        "stocks": impression_stocks
    }

    with open(os.path.join(DOCS_DIR, "data.json"), "w", encoding="utf-8") as f:
        json.dump(web_output, f, ensure_ascii=False, indent=4)
    
    logging.info("數據已更新至 docs/data.json")

if __name__ == "__main__":
    run_headless_analysis()
