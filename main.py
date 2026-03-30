import os
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pytz import timezone

# 匯入您的核心模組
try:
    from stock_analyzer import StockAnalyzer
    from data_downloader import DataDownloader
    from secondary_filter import find_impression_stocks 
except ImportError as e:
    print(f"核心模組匯入失敗，請檢查檔案是否存在: {e}")
    exit(1)

# 設定
TAIPEI_TZ = timezone('Asia/Taipei')
DOCS_DIR = "docs"

# ★★★ 新增：JSON 數值轉換器 ★★★
class StockJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'item'):
            return obj.item()
        if isinstance(obj, (datetime, datetime.date)):
            return obj.isoformat()
        return super(StockJSONEncoder, self).default(obj)

def run_headless_analysis():
    # --- [日誌配置] ---
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler("headless_debug.log", encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    start_total_time = time.time()
    
    # 🌟 修正 1：在程式「一啟動」時就先記下觸發時間 (例如 13:30)
    trigger_time = datetime.now(TAIPEI_TZ)
    
    logging.info("==========================================")
    logging.info("🚀 啟動 IKE_TOOL 自動分析流程 (50筆滾動歷史版)")
    logging.info(f"📅 觸發時間: {trigger_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("==========================================")

    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR)

    analyzer = StockAnalyzer()
    downloader = DataDownloader()
    all_tickers = list(analyzer.ticker_names.keys())
    fake_stop_flag = threading.Event()

    # --- 步驟 1: 下載數據 ---
    logging.info("📥 步驟 1/5: 正在下載數據 (預計需要 30~45 分鐘)...")
    downloader.download_and_cache_all_raw_data(all_tickers, fake_stop_flag)

    # --- 步驟 2: 計算指標 ---
    logging.info("📊 步驟 2/5: 正在計算技術指標...")
    analyzer.ensure_local_data_and_calculate_indicators(all_tickers, stop_flag=fake_stop_flag)

    # --- 步驟 3: 一次篩選 ---
    logging.info("🔍 步驟 3/5: 正在執行一次篩選...")
    today_str = trigger_time.strftime("%Y-%m-%d")
    start_date_str = (trigger_time - timedelta(days=90)).strftime("%Y-%m-%d")
    
    primary_list = analyzer.run_stock_selection(
        tickers=all_tickers, 
        start_date=start_date_str, 
        end_date=today_str, 
        selection_type="bullish",
        stop_flag=fake_stop_flag
    )
    
    primary_list.sort(key=lambda x: float(str(x.get("當日成交量", "0")).replace(',', '')), reverse=True)
    logging.info(f"📈 一次篩選完成: {len(primary_list)} 檔")

    # --- 步驟 4: 二次篩選 ---
    logging.info("💎 步驟 4/5: 執行二次篩選...")
    secondary_list = find_impression_stocks(
        analyzer, 
        primary_list, 
        t0_gain_threshold=0.0, 
        t1_gain_threshold=8.0, 
        t2_gain_threshold=10.0
    )
    
    secondary_list.sort(key=lambda x: x.get("raw_volume", 0), reverse=True)
    logging.info(f"🔥 二次篩選完成: {len(secondary_list)} 檔")

    # --- 步驟 5: 產出 JSON (滾動式 50 筆歷史) ---
    logging.info("💾 步驟 5/5: 正在更新 docs/data.json...")
    json_path = os.path.join(DOCS_DIR, "data.json")
    finish_time = datetime.now(TAIPEI_TZ)
    
    current_record = {
        "time": trigger_time.strftime("%H:%M"), 
        "date": trigger_time.strftime("%Y-%m-%d"),
        "primary_count": len(primary_list),
        "secondary_count": len(secondary_list),
        "primary_list": primary_list,
        "secondary_list": secondary_list
    }

    # 初始化結構，確保讀取失敗時有預設值
    full_data = {"last_update": "", "history": [], "recommendations": []}

    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                content = json.load(f)
                if isinstance(content, dict):
                    # 繼承舊資料，但排除掉 recommendations (由本次掃描決定)
                    if "history" in content:
                        full_data["history"] = content["history"]
                    if "last_update" in content:
                        full_data["last_update"] = content["last_update"]
                    
            # 🌟 關鍵改動：刪除了「隔日重置歷史」的程式碼塊
            # 這樣資料就會一直累積下去，直到超過 50 筆
            
        except Exception as e:
            logging.error(f"讀取舊 JSON 失敗: {e}，將初始化新檔案。")

    # 🌟 將最新一筆資料塞在最前面 (history[0])
    full_data["history"].insert(0, current_record)
    
    # 🌟 設定上限為 50 筆 (約可存兩週的盤中紀錄)
    if len(full_data["history"]) > 50:
        logging.info("歷史紀錄超過 50 筆，移除最舊的一筆。")
        full_data["history"] = full_data["history"][:50]

    # 更新全域資訊
    full_data["last_update"] = finish_time.strftime("%Y-%m-%d %H:%M:%S")
    full_data["recommendations"] = secondary_list 

    # 寫入檔案
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(full_data, f, ensure_ascii=False, indent=4, cls=StockJSONEncoder)
        logging.info(f"✨ 任務結束！耗時 {finish_time - trigger_time}，歷史紀錄總數: {len(full_data['history'])}")
    except Exception as e:
        logging.error(f"寫入 JSON 失敗: {e}")

if __name__ == "__main__":
    run_headless_analysis()
