# data_downloader.py (修正版)

import yfinance as yf
import pandas as pd
import os
from datetime import datetime, timedelta
from pytz import timezone
import time
import random
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import shutil
import threading

# --- [新增] 引入股票代號更新模組 ---
# 嘗試導入更新器，如果檔案不存在則優雅地處理
try:
    # ▼▼▼▼▼ 這裡是本次修正的地方 ▼▼▼▼▼
    # 函式名稱從 'update_ticker_names' 改為您檔案中實際使用的 'update_stock_list'
    from ticker_updater import update_stock_list
    UPDATER_LOADED = True
except ImportError:
    UPDATER_LOADED = False
    # 警告訊息中的舊檔名也一併修正
    logging.warning("未能找到 ticker_updater.py，將無法自動更新股票列表。")
# ▲▲▲▲▲ 修改結束 ▲▲▲▲▲


# ★★★ 核心修正：註解掉這裡的 basicConfig 呼叫 ★★★
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 定義下載狀態檔案路徑
DOWNLOAD_STATUS_FILE = "download_status.json"

# 定義預設下載起始日期 (用於非強制完整更新時的數據獲取起始點)
DEFAULT_DOWNLOAD_START_DATE = "2025-03-01"

# 定義最小歷史數據起始日期 (作為數據獲取的絕對最早日期，用於強制完整更新)
MIN_HISTORY_START_DATE = "2025-03-01" # 從 2025 年 3 月 1 日開始獲取數據
MIN_HISTORY_START_DATE_DT = datetime.strptime(MIN_HISTORY_START_DATE, "%Y-%m-%d")

# 定義在判斷本地數據是否足夠時所需的最小交易日數據量
REQUIRED_CACHE_DATA_POINTS = 90

class DataDownloader:
    """
    專門處理股票原始數據下載、本地快取管理和下載狀態追蹤的類別。
    此類別不應包含任何技術指標計算或股票篩選邏輯。
    """
    def __init__(self, data_dir="stock_data"):
        """
        初始化 DataDownloader 類別。
        :param data_dir: 儲存股票原始數據的目錄名稱。
        """
        logging.debug("進入 DataDownloader.__init__")
        self.data_dir = data_dir
        # 如果數據目錄不存在，則創建它
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        logging.debug("DataDownloader 初始化完成。")

    def _load_download_status(self):
        """載入下載狀態。"""
        logging.debug("進入 _load_download_status")
        if os.path.exists(DOWNLOAD_STATUS_FILE):
            try:
                with open(DOWNLOAD_STATUS_FILE, 'r', encoding='utf-8') as f:
                    status = json.load(f)
                    logging.info("下載狀態載入成功。")
                    return status
            except json.JSONDecodeError as e:
                logging.error(f"載入下載狀態檔案失敗 (JSON 格式錯誤): {e}")
                return {"last_full_download_date": None, "is_complete": False}
            except Exception as e:
                logging.error(f"載入下載狀態檔案失敗: {e}")
                return {"last_full_download_date": None, "is_complete": False}
        logging.info("下載狀態檔案不存在，初始化為空。")
        return {"last_full_download_date": None, "is_complete": False}

    def _save_download_status(self, date_str, is_complete):
        """儲存下載狀態。"""
        logging.debug("進入 _save_download_status")
        try:
            status = {"last_full_download_date": date_str, "is_complete": is_complete}
            with open(DOWNLOAD_STATUS_FILE, 'w', encoding='utf-8') as f:
                json.dump(status, f, ensure_ascii=False, indent=4)
            logging.info(f"下載狀態已儲存: 日期={date_str}, 完成={is_complete}")
        except Exception as e:
            logging.error(f"儲存下載狀態檔案失敗: {e}")

    def fetch_stock_data_raw(self, ticker: str, start_date: str, end_date: str, interval: str = '1d', retries=3) -> pd.DataFrame | None:
        """
        從 yfinance 獲取股票原始數據，包括重試機制和時間間隔參數。
        """
        logging.debug(f"進入 fetch_stock_data_raw, 股票: {ticker}, 開始日期: {start_date}, 結束日期: {end_date}")
        ticker_candidates_set = set()
        ticker_candidates_set.add(ticker)
        base_ticker = ticker.replace('.TW', '').replace('.TWO', '').replace('.SA', '').replace('.SS', '')

        if base_ticker.isdigit():
            ticker_candidates_set.add(f"{base_ticker}.TW")
            ticker_candidates_set.add(f"{base_ticker}.TWO")
        
        possible_tickers = []
        if ticker in ticker_candidates_set:
            possible_tickers.append(ticker)
            ticker_candidates_set.remove(ticker)
        tw_variant = f"{base_ticker}.TW"
        if tw_variant in ticker_candidates_set:
            possible_tickers.append(tw_variant)
            ticker_candidates_set.remove(tw_variant)
        two_variant = f"{base_ticker}.TWO"
        if two_variant in ticker_candidates_set:
            possible_tickers.append(two_variant)
            ticker_candidates_set.remove(two_variant)
        possible_tickers.extend(list(ticker_candidates_set))

        for t_candidate in possible_tickers:
            for attempt in range(retries):
                try:
                    time.sleep(random.uniform(0.5, 2.0))

                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    end_dt_exclusive = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

                    stock = yf.Ticker(t_candidate)
                    df = stock.history(start=start_dt, end=end_dt_exclusive, interval=interval)

                    if df.index.tz is not None:
                        df.index = df.index.tz_convert('Asia/Taipei').tz_localize(None)
                    else:
                        df.index = df.index.tz_localize('UTC', errors='coerce').tz_convert('Asia/Taipei').tz_localize(None)

                    df.columns = [col.replace(' ', '_').lower() for col in df.columns]
                    column_mapping = {
                        'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close',
                        'volume': 'Volume', 'adj_close': 'Adj Close'
                    }
                    df = df.rename(columns=column_mapping)

                    if 'Adj Close' in df.columns:
                        df['Close'] = df['Adj Close']
                    
                    if 'Close' not in df.columns or 'Volume' not in df.columns:
                        logging.error(f"獲取 {t_candidate} 後，缺少必要的 'Close' 或 'Volume' 列。可用列: {df.columns.tolist()}")
                        return pd.DataFrame()

                    df.attrs['ticker'] = t_candidate
                    return df

                except Exception as e:
                    if "404 Not Found" in str(e) or "No data found for this period" in str(e) or "invalid interval" in str(e):
                        logging.error(f"下載 {t_candidate} 失敗: 股票代號可能無效、已下市或時間間隔/範圍不匹配。{e}")
                        break
                    logging.warning(f"下載 {t_candidate} 失敗 (嘗試 {attempt+1}/{retries}): {e}")
                    if attempt < retries - 1:
                        time.sleep(3)
                    else:
                        logging.error(f"下載 {t_candidate} 最終失敗。")
        return None

    def save_df_to_raw_parquet(self, df: pd.DataFrame, ticker: str, interval: str = '1d', overwrite: bool = False) -> str:
        """
        將原始 DataFrame 儲存為 Parquet 檔案。
        """
        logging.debug(f"進入 save_df_to_raw_parquet, 股票: {ticker}, 時間間隔: {interval}, 覆蓋: {overwrite}")
        interval_data_dir = os.path.join(self.data_dir, interval)
        if not os.path.exists(interval_data_dir):
            os.makedirs(interval_data_dir)

        cleaned_ticker = ticker.replace('.', '_')

        if overwrite:
            for f_name in os.listdir(interval_data_dir):
                if f_name.startswith(f"{cleaned_ticker}_") and f_name.endswith(".parquet"):
                    try:
                        os.remove(os.path.join(interval_data_dir, f_name))
                        logging.debug(f"已刪除舊檔案: {f_name}")
                    except Exception as e:
                        logging.warning(f"刪除舊檔案 {f_name} 失敗: {e}")

        if not df.empty:
            start_date_str = df.index.min().strftime("%Y-%m-%d")
            end_date_str = df.index.max().strftime("%Y-%m-%d")
        else:
            taipei_tz = timezone('Asia/Taipei')
            today = datetime.now(taipei_tz).strftime("%Y-%m-%d")
            start_date_str = today
            end_date_str = today

        parquet_path = os.path.join(interval_data_dir, f"{cleaned_ticker}_{start_date_str}_{end_date_str}.parquet")
        df.to_parquet(parquet_path, index=True, engine='pyarrow')
        logging.debug(f"已將 {ticker} 原始數據儲存到 {parquet_path}")
        return parquet_path

    def load_df_from_raw_parquet(self, ticker: str, start_date: str, end_date: str, interval: str = '1d') -> pd.DataFrame | None:
        """
        從 Parquet 檔案載入原始 DataFrame。
        """
        logging.debug(f"進入 load_df_from_raw_parquet, 股票: {ticker}, 時間間隔: {interval}")
        interval_data_dir = os.path.join(self.data_dir, interval)
        cleaned_ticker = ticker.replace('.', '_')
        
        if not os.path.exists(interval_data_dir):
            logging.debug(f"數據目錄 {interval_data_dir} 不存在，無法載入 {ticker} 原始數據。")
            return None

        all_dfs = []
        
        for f_name in os.listdir(interval_data_dir):
            if f_name.startswith(f"{cleaned_ticker}_") and f_name.endswith(".parquet"):
                file_path = os.path.join(interval_data_dir, f_name)
                try:
                    df_temp = pd.read_parquet(file_path, engine='pyarrow')
                    if not df_temp.empty:
                        if df_temp.index.tz is not None:
                            df_temp.index = df_temp.index.tz_convert('Asia/Taipei').tz_localize(None)
                        else:
                            df_temp.index = pd.to_datetime(df_temp.index).tz_localize('Asia/Taipei', ambiguous='infer').tz_localize(None)
                        all_dfs.append(df_temp)
                        logging.debug(f"成功載入部分原始檔案: {f_name}, 數據量: {len(df_temp)}")
                except Exception as e:
                    logging.warning(f"從 {file_path} 載入原始數據失敗，檔案可能已損壞或格式錯誤: {e}")
                    continue

        if not all_dfs:
            logging.debug(f"在 {interval_data_dir} 中找不到 {ticker} 的原始 Parquet 數據。")
            return None

        combined_df = pd.concat(all_dfs)
        combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
        combined_df = combined_df.sort_index()

        try:
            start_dt_filter = pd.to_datetime(start_date)
            end_dt_filter = pd.to_datetime(end_date)
            combined_df = combined_df[(combined_df.index.date >= start_dt_filter.date()) & (combined_df.index.date <= end_dt_filter.date())]
        except ValueError as e:
            logging.error(f"日期篩選格式錯誤: {e}")
            pass

        if combined_df.empty:
            logging.warning(f"載入並合併 {ticker} 原始數據後，在指定日期範圍內找不到數據。")
            return None

        combined_df.attrs['ticker'] = ticker 
        logging.info(f"成功載入並合併 {ticker} 的所有本地原始數據，共 {len(combined_df)} 條記錄。")
        return combined_df

    def delete_all_raw_cached_data(self, interval: str = '1d'):
        """
        刪除指定時間間隔的本地股票原始數據檔案 (Parquet)。
        """
        logging.info(f"進入 delete_all_raw_cached_data, 時間間隔: {interval}")
        interval_data_dir = os.path.join(self.data_dir, interval)
        if os.path.exists(interval_data_dir):
            try:
                shutil.rmtree(interval_data_dir)
                os.makedirs(interval_data_dir)
                logging.info(f"已刪除並重新創建 {interval_data_dir} 目錄下的所有本地股票原始數據檔案。")
                self._save_download_status(None, False)
            except Exception as e:
                logging.error(f"刪除 {interval_data_dir} 目錄失敗: {e}")
                raise
        else:
            logging.info(f"目錄 {interval_data_dir} 不存在，無需刪除檔案。")

    def _is_trading_day_and_after_close(self, current_time: datetime) -> bool:
        """
        判斷當前時間是否為台灣股市交易日且在收盤後。
        """
        logging.debug(f"進入 _is_trading_day_and_after_close, 當前時間: {current_time}")
        if current_time.weekday() >= 5:
            logging.debug("當前時間是週末，非交易日。")
            return False

        close_hour, close_minute = 13, 30

        if current_time.hour > close_hour or (current_time.hour == close_hour and current_time.minute >= close_minute):
            logging.debug("當前時間是交易日且市場已收盤。")
            return True
        else:
            logging.debug("當前時間是交易日但市場尚未收盤。")
            return False

    def _download_and_cache_single_ticker(self, ticker: str, download_start_date_str: str, current_end_date_str: str, force_full_refresh: bool) -> str | None:
        """
        處理 ThreadPoolExecutor 中單一股票原始數據獲取和儲存邏輯的輔助函數。
        """
        try:
            logging.info(f"正在獲取 {ticker} 從 {download_start_date_str} 到 {current_end_date_str} 的原始數據。")
            fetched_df = self.fetch_stock_data_raw(ticker, download_start_date_str, current_end_date_str, interval='1d', retries=3)
            
            if fetched_df is not None and not fetched_df.empty:
                self.save_df_to_raw_parquet(fetched_df, ticker, interval='1d', overwrite=True)
                logging.debug(f"已獲取並儲存 {ticker} 的原始數據。")
                return ticker
            else:
                logging.warning(f"無法獲取 {ticker} 的任何有效原始數據，可能是沒有數據或獲取失敗。")
                return None
        except Exception as e:
            logging.error(f"獲取並儲存 {ticker} 原始數據失敗: {e}", exc_info=True)
            return None

    def download_and_cache_all_raw_data(self, tickers_to_update: list, stop_flag: threading.Event, update_callback=None, force_full_refresh: bool = False, reverse_order: bool = False, force_update_tickers: bool = False) -> str:
        """
        下載並快取所有指定股票的原始數據。
        """
        # --- [修改] 增加強制更新股票列表的邏輯 ---
        if force_update_tickers:
            if UPDATER_LOADED:
                try:
                    logging.info("觸發強制更新 ticker_names.txt...")
                    if update_callback:
                        update_callback(("status", "正在強制更新股票代號列表..."))
                    
                    # ▼▼▼▼▼ 這裡也需要跟著修改 ▼▼▼▼▼
                    # 呼叫的函式名稱從 update_ticker_names 改為 update_stock_list
                    update_stock_list()
                    # ▲▲▲▲▲ 修改結束 ▲▲▲▲▲
                    
                    logging.info("股票代號列表強制更新完成。")
                    if update_callback:
                        time.sleep(1)
                except Exception as e:
                    logging.error(f"強制更新股票代號列表時發生錯誤: {e}")
            else:
                logging.warning("無法執行強制更新，因為 ticker_updater.py 模組未載入。")
        
        logging.info(f"開始所有股票原始數據下載，共 {len(tickers_to_update)} 檔股票。強制更新: {force_full_refresh}")
        taipei_tz = timezone('Asia/Taipei')
        now = datetime.now(taipei_tz)
        today_date_str = now.strftime("%Y-%m-%d")
        download_status = self._load_download_status()
        
        all_tickers = tickers_to_update[::-1] if reverse_order else tickers_to_update
        total_tickers = len(all_tickers)
        
        auto_force_refresh_due_to_cross_day = False
        last_download_date_status = download_status.get("last_full_download_date")
        is_download_complete_status = download_status.get("is_complete", False)

        if last_download_date_status is None:
            logging.info("首次運行或下載狀態檔案不存在，執行完整下載。")
            auto_force_refresh_due_to_cross_day = True
        elif last_download_date_status != today_date_str:
            logging.info(f"檢測到跨日 (上次下載日期: {last_download_date_status}, 今天: {today_date_str})，執行強制完整更新。")
            auto_force_refresh_due_to_cross_day = True
        elif not is_download_complete_status:
            logging.info(f"上次下載 ({last_download_date_status}) 未完成，執行強制完整更新以完成。")
            auto_force_refresh_due_to_cross_day = True
        
        final_force_refresh = force_full_refresh or auto_force_refresh_due_to_cross_day

        if final_force_refresh:
            logging.info("執行強制完整更新: 刪除舊數據並重新下載所有數據。")
            if update_callback:
                update_callback(("status", "正在執行強制完整原始數據下載 (刪除舊數據)..."))
            self.delete_all_raw_cached_data(interval='1d')
            self._save_download_status(None, False)
        
        download_start_date_for_fetch = MIN_HISTORY_START_DATE if final_force_refresh else DEFAULT_DOWNLOAD_START_DATE

        logging.info(f"開始所有股票原始數據下載 (下載起始日期: {download_start_date_for_fetch}, 強制更新: {final_force_refresh})。")
        processed_fetch_count = 0 

        max_workers_download = 40 
        logging.debug(f"網路下載執行緒池最大工作者數量: {max_workers_download}")

        start_fetch_time = time.time()
        with ThreadPoolExecutor(max_workers=max_workers_download) as executor:
            futures = {executor.submit(self._download_and_cache_single_ticker, ticker, download_start_date_for_fetch, today_date_str, final_force_refresh): ticker for ticker in all_tickers}

            for future in as_completed(futures):
                if stop_flag.is_set():
                    logging.info("所有股票原始數據下載已中止。")
                    if update_callback:
                        update_callback(("status", "原始數據下載已中止。"))
                    self._save_download_status(today_date_str, False)
                    return "中止"
                
                ticker_name_from_future = futures[future]
                try:
                    result_ticker = future.result()
                    if result_ticker:
                        pass
                except Exception as e:
                    logging.error(f"下載 {ticker_name_from_future} 原始數據失敗: {e}", exc_info=True)
                
                processed_fetch_count += 1
                if update_callback:
                    update_callback(("progress", processed_fetch_count, total_tickers))

        end_fetch_time = time.time()
        fetch_duration = end_fetch_time - start_fetch_time
        if update_callback:
            update_callback(("download_time", fetch_duration))

        final_status = "完成"
        if processed_fetch_count == total_tickers:
            is_today_market_closed = self._is_trading_day_and_after_close(now)
            
            if is_today_market_closed:
                logging.info(f"所有股票原始數據下載完成。共 {total_tickers} 檔股票已更新。市場已收盤，標記為完整下載。")
                self._save_download_status(today_date_str, True)
            else:
                logging.info(f"所有股票原始數據下載完成。共 {total_tickers} 檔股票已更新。市場尚未收盤，標記為等待最終數據的未完成下載。")
                self._save_download_status(today_date_str, False)
        else:
            final_status = "部分完成"
            logging.warning(f"股票原始數據下載完成，但有 {total_tickers - processed_fetch_count} 檔股票的數據無法下載。")
            self._save_download_status(today_date_str, False)

        return final_status
