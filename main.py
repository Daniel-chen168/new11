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
# 解決 TypeError: Object of type int64 is not JSON serializable
class StockJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        # 檢查對象是否具有 .item() 方法 (NumPy/Pandas 數值類型通常有)
        if hasattr(obj, 'item'):
            return obj.item()
        # 處理日期對象
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
    logging.info("==========================================")
    logging.info("🚀 啟動 IKE_TOOL 自動分析流程 (修正 JSON 版)")
    logging.info(f"📅 當前台北時間: {datetime.now(TAIPEI_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("==========================================")

    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR)

    # 初始化分析器與下載器
    analyzer = StockAnalyzer()
    downloader = DataDownloader()
    all_tickers = list(analyzer.ticker_names.keys())
    fake_stop_flag = threading.Event()

    # --- 步驟 1: 下載數據 ---
    logging.info("📥 步驟 1/5: 正在下載數據...")
    downloader.download_and_cache_all_raw_data(all_tickers, fake_stop_flag)

    # --- 步驟 2: 計算指標 ---
    logging.info("📊 步驟 2/5: 正在計算技術指標...")
    analyzer.ensure_local_data_and_calculate_indicators(all_tickers, stop_flag=fake_stop_flag)

    # --- 步驟 3: 一次篩選 (過中軌) ---
    logging.info("🔍 步驟 3/5: 正在執行一次篩選...")
    today_str = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d")
    start_date_str = (datetime.now(TAIPEI_TZ) - timedelta(days=90)).strftime("%Y-%m-%d")
    
    primary_list = analyzer.run_stock_selection(
        tickers=all_tickers, 
        start_date=start_date_str, 
        end_date=today_str, 
        selection_type="bullish",
        stop_flag=fake_stop_flag
    )
    
    # 排序邏輯：成交量大排到小
    primary_list.sort(key=lambda x: float(str(x.get("當日成交量", "0")).replace(',', '')), reverse=True)
    logging.info(f"📈 一次篩選完成: {len(primary_list)} 檔")

    # --- 步驟 4: 二次篩選 (印象派精選) ---
    logging.info("💎 步驟 4/5: 執行二次篩選...")
    secondary_list = find_impression_stocks(
        analyzer, 
        primary_list, 
        t0_gain_threshold=0.0, 
        t1_gain_threshold=8.0, 
        t2_gain_threshold=10.0
    )
    
    # 排序邏輯：成交量大排到小 (使用 raw_volume 排序更精準)
    secondary_list.sort(key=lambda x: x.get("raw_volume", 0), reverse=True)
    logging.info(f"🔥 二次篩選完成: {len(secondary_list)} 檔")

    # --- 步驟 5: 產出 JSON (分層結構) ---
    logging.info("💾 步驟 5/5: 正在更新 docs/data.json...")
    json_path = os.path.join(DOCS_DIR, "data.json")
    
    now = datetime.now(TAIPEI_TZ)
    current_record = {
        "time": now.strftime("%H:%M"),
        "date": now.strftime("%Y-%m-%d"),
        "primary_count": len(primary_list),
        "secondary_count": len(secondary_list),
        "primary_list": primary_list,
        "secondary_list": secondary_list
    }

    full_data = {"last_update": "", "history": [], "recommendations": []}

    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                content = json.load(f)
                if isinstance(content, dict):
                    full_data.update(content)
                    if "history" not in full_data: full_data["history"] = []
                # 隔日重置歷史
                if full_data["history"] and full_data["history"][0].get("date") != current_record["date"]:
                    full_data["history"] = []
        except: pass

    full_data["history"].append(current_record)
    full_data["last_update"] = now.strftime("%Y-%m-%d %H:%M:%S")
    full_data["recommendations"] = secondary_list 

    # ★★★ 修改點：使用 StockJSONEncoder 處理 int64 錯誤 ★★★
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(full_data, f, ensure_ascii=False, indent=4, cls=StockJSONEncoder)
    
    logging.info(f"✨ 任務結束！數據已儲存至 {json_path}")

if __name__ == "__main__":
    run_headless_analysis()
