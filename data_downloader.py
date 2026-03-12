# data_downloader.py (解決 3/12 日期缺失與二次篩選失效版)

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

# --- 引入股票代號更新模組 ---
try:
    from ticker_updater import update_stock_list
    UPDATER_LOADED = True
except ImportError:
    UPDATER_LOADED = False
    logging.warning("未能找到 ticker_updater.py，將無法自動更新股票列表。")

DOWNLOAD_STATUS_FILE = "download_status.json"
DEFAULT_DOWNLOAD_START_DATE = "2025-03-01"
MIN_HISTORY_START_DATE = "2025-03-01" 
MIN_HISTORY_START_DATE_DT = datetime.strptime(MIN_HISTORY_START_DATE, "%Y-%m-%d")
REQUIRED_CACHE_DATA_POINTS = 90

class DataDownloader:
    def __init__(self, data_dir="stock_data"):
        logging.debug("進入 DataDownloader.__init__")
        self.data_dir = data_dir
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        logging.debug("DataDownloader 初始化完成。")

    def _load_download_status(self):
        logging.debug("進入 _load_download_status")
        if os.path.exists(DOWNLOAD_STATUS_FILE):
            try:
                with open(DOWNLOAD_STATUS_FILE, 'r', encoding='utf-8') as f:
                    status = json.load(f)
                    return status
            except Exception as e:
                logging.error(f"載入下載狀態檔案失敗: {e}")
                return {"last_full_download_date": None, "is_complete": False}
        return {"last_full_download_date": None, "is_complete": False}

    def _save_download_status(self, date_str, is_complete):
        logging.debug("進入 _save_download_status")
        try:
            status = {"last_full_download_date": date_str, "is_complete": is_complete}
            with open(DOWNLOAD_STATUS_FILE, 'w', encoding='utf-8') as f:
                json.dump(status, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logging.error(f"儲存下載狀態檔案失敗: {e}")

    def fetch_stock_data_raw(self, ticker: str, start_date: str, end_date: str, interval: str = '1d', retries=3) -> pd.DataFrame | None:
        ticker_candidates_set = set()
        ticker_candidates_set.add(ticker)
        base_ticker = ticker.replace('.TW', '').replace('.TWO', '').replace('.SA', '').replace('.SS', '')

        if base_ticker.isdigit():
            ticker_candidates_set.add(f"{base_ticker}.TW")
            ticker_candidates_set.add(f"{base_ticker}.TWO")
        
        possible_tickers = list(ticker_candidates_set)
        if ticker in possible_tickers:
            possible_tickers.remove(ticker)
            possible_tickers.insert(0, ticker)

        for t_candidate in possible_tickers:
            for attempt in range(retries):
                try:
                    time.sleep(random.uniform(0.5, 2.0))

                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    stock = yf.Ticker(t_candidate)

                    # 🌟 核心修復：拔除 end 參數，強制 yfinance 抓取到現在這一秒！
                    df = stock.history(start=start_dt, interval=interval)

                    # 🌟 雙重保險：如果 yfinance 異常回傳空值，改用 period 強制抓取最近一年
                    if df.empty:
                        df = stock.history(period="1y", interval=interval)

                    if df.empty:
                        continue 

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
                        return pd.DataFrame()

                    df.attrs['ticker'] = t_candidate
                    return df

                except Exception as e:
                    if "404 Not Found" in str(e) or "No data found" in str(e) or "invalid interval" in str(e):
                        break
                    if attempt < retries - 1:
                        time.sleep(3)
        return None

    def save_df_to_raw_parquet(self, df: pd.DataFrame, ticker: str, interval: str = '1d', overwrite: bool = False) -> str:
        interval_data_dir = os.path.join(self.data_dir, interval)
        if not os.path.exists(interval_data_dir):
            os.makedirs(interval_data_dir)

        cleaned_ticker = ticker.replace('.', '_')

        if overwrite:
            for f_name in os.listdir(interval_data_dir):
                if f_name.startswith(f"{cleaned_ticker}_") and f_name.endswith(".parquet"):
                    try: os.remove(os.path.join(interval_data_dir, f_name))
                    except: pass

        if not df.empty:
            start_date_str = df.index.min().strftime("%Y-%m-%d")
            end_date_str = df.index.max().strftime("%Y-%m-%d")
        else:
            taipei_tz = timezone('Asia/Taipei')
            today = datetime.now(taipei_tz).strftime("%Y-%m-%d")
            start_date_str, end_date_str = today, today

        parquet_path = os.path.join(interval_data_dir, f"{cleaned_ticker}_{start_date_str}_{end_date_str}.parquet")
        df.to_parquet(parquet_path, index=True, engine='pyarrow')
        return parquet_path

    def load_df_from_raw_parquet(self, ticker: str, start_date: str, end_date: str, interval: str = '1d') -> pd.DataFrame | None:
        interval_data_dir = os.path.join(self.data_dir, interval)
        cleaned_ticker = ticker.replace('.', '_')
        
        if not os.path.exists(interval_data_dir): return None

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
                except: continue

        if not all_dfs: return None

        combined_df = pd.concat(all_dfs)
        combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
        combined_df = combined_df.sort_index()

        try:
            start_dt_filter = pd.to_datetime(start_date)
            # 🌟 讀取時放寬結束日期，確保最新盤中資料不被濾掉
            end_dt_filter = pd.to_datetime(end_date) + timedelta(days=2) 
            combined_df = combined_df[(combined_df.index.date >= start_dt_filter.date()) & (combined_df.index.date <= end_dt_filter.date())]
        except: pass

        if combined_df.empty: return None

        combined_df.attrs['ticker'] = ticker 
        return combined_df

    def delete_all_raw_cached_data(self, interval: str = '1d'):
        interval_data_dir = os.path.join(self.data_dir, interval)
        if os.path.exists(interval_data_dir):
            try:
                shutil.rmtree(interval_data_dir)
                os.makedirs(interval_data_dir)
                self._save_download_status(None, False)
            except: pass

    def _is_trading_day_and_after_close(self, current_time: datetime) -> bool:
        if current_time.weekday() >= 5: return False
        close_hour, close_minute = 13, 30
        return current_time.hour > close_hour or (current_time.hour == close_hour and current_time.minute >= close_minute)

    def _download_and_cache_single_ticker(self, ticker: str, download_start_date_str: str, current_end_date_str: str, force_full_refresh: bool) -> str | None:
        try:
            fetched_df = self.fetch_stock_data_raw(ticker, download_start_date_str, current_end_date_str, interval='1d', retries=3)
            if fetched_df is not None and not fetched_df.empty:
                self.save_df_to_raw_parquet(fetched_df, ticker, interval='1d', overwrite=True)
                return ticker
            return None
        except: return None

    def download_and_cache_all_raw_data(self, tickers_to_update: list, stop_flag: threading.Event, update_callback=None, force_full_refresh: bool = False, reverse_order: bool = False, force_update_tickers: bool = False) -> str:
        if force_update_tickers and UPDATER_LOADED:
            try: update_stock_list()
            except: pass
        
        taipei_tz = timezone('Asia/Taipei')
        now = datetime.now(taipei_tz)
        today_date_str = now.strftime("%Y-%m-%d")
        download_status = self._load_download_status()
        
        all_tickers = tickers_to_update[::-1] if reverse_order else tickers_to_update
        total_tickers = len(all_tickers)
        
        auto_force_refresh_due_to_cross_day = False
        last_download_date_status = download_status.get("last_full_download_date")
        is_download_complete_status = download_status.get("is_complete", False)

        if last_download_date_status is None or last_download_date_status != today_date_str or not is_download_complete_status:
            auto_force_refresh_due_to_cross_day = True
        
        final_force_refresh = force_full_refresh or auto_force_refresh_due_to_cross_day

        if final_force_refresh:
            self.delete_all_raw_cached_data(interval='1d')
            self._save_download_status(None, False)
        
        download_start_date_for_fetch = MIN_HISTORY_START_DATE if final_force_refresh else DEFAULT_DOWNLOAD_START_DATE
        processed_fetch_count = 0 

        max_workers_download = 40 

        start_fetch_time = time.time()
        with ThreadPoolExecutor(max_workers=max_workers_download) as executor:
            futures = {executor.submit(self._download_and_cache_single_ticker, ticker, download_start_date_for_fetch, today_date_str, final_force_refresh): ticker for ticker in all_tickers}

            for future in as_completed(futures):
                if stop_flag.is_set():
                    self._save_download_status(today_date_str, False)
                    return "中止"
                try: future.result()
                except: pass
                
                processed_fetch_count += 1
                if update_callback: update_callback(("progress", processed_fetch_count, total_tickers))

        final_status = "完成"
        if processed_fetch_count == total_tickers:
            if self._is_trading_day_and_after_close(now): self._save_download_status(today_date_str, True)
            else: self._save_download_status(today_date_str, False)
        else:
            final_status = "部分完成"
            self._save_download_status(today_date_str, False)

        return final_status
