# stock_analyzer.py (修改版)
# 處理所有股票數據分析、指標計算和篩選的核心邏輯類別。

import pandas as pd
import os
from datetime import datetime, timedelta
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import threading
import shutil # 用於刪除目錄
from pytz import timezone # 用於時區處理
import time
import numpy as np # 新增 numpy 導入，用於計算

# 配置日誌
#logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 定義進行分析所需的最小數據筆數 (例如，計算 MA20 或布林通道需要至少 20 筆)
MIN_DATA_FOR_ANALYSIS = 20

# 引入新的數據下載模組 (假設 data_downloader.py 在同一個目錄)
# 確保這些變量在 DataDownloader 模組中定義
try:
    from data_downloader import DataDownloader, MIN_HISTORY_START_DATE, DEFAULT_DOWNLOAD_START_DATE
except ImportError:
    logging.error("無法導入 data_downloader.py。請確保檔案存在且路徑正確。使用簡化版 DataDownloader。")
    # 如果無法導入，則在這裡提供一個簡化的 DataDownloader 類別和常數作為備用
    MIN_HISTORY_START_DATE = "2024-03-01"
    DEFAULT_DOWNLOAD_START_DATE = "2024-03-01"
    DOWNLOAD_STATUS_FILE = "download_status.json"

    class DataDownloader:
        def __init__(self, data_dir="stock_data"):
            self.data_dir = data_dir
            if not os.path.exists(self.data_dir):
                os.makedirs(self.data_dir)
            logging.warning("使用簡化版 DataDownloader，因為無法導入完整模組。")

        def load_df_from_raw_parquet(self, ticker: str, start_date: str, end_date: str, interval: str = '1d') -> pd.DataFrame | None:
            # 簡化版：僅嘗試從指定路徑載入，不處理多個檔案或複雜邏輯
            filepath = os.path.join(self.data_dir, interval, f"{ticker.replace('.', '_')}_{start_date}_{end_date}.parquet")
            if os.path.exists(filepath):
                try:
                    df = pd.read_parquet(filepath)
                    if df.index.tz is not None:
                        df.index = df.index.tz_localize(None)
                    return df
                except Exception as e:
                    logging.error(f"簡化版 DataDownloader 載入 {filepath} 失敗: {e}")
            return None

        def save_df_to_raw_parquet(self, df: pd.DataFrame, ticker: str, interval: str = '1d', overwrite: bool = False) -> str:
            # 簡化版：僅儲存單一檔案
            interval_data_dir = os.path.join(self.data_dir, interval)
            if not os.path.exists(interval_data_dir):
                os.makedirs(interval_data_dir)
            cleaned_ticker = ticker.replace('.', '_')
            start_date_str = df.index.min().strftime("%Y-%m-%d") if not df.empty else datetime.now().strftime("%Y-%m-%d")
            end_date_str = df.index.max().strftime("%Y-%m-%d") if not df.empty else datetime.now().strftime("%Y-%m-%d")
            parquet_path = os.path.join(interval_data_dir, f"{cleaned_ticker}_{start_date_str}_{end_date_str}.parquet")
            df.to_parquet(parquet_path, index=True)
            return parquet_path

        def download_and_cache_all_raw_data(self, tickers_to_update: list, stop_flag: threading.Event, update_callback=None, force_full_refresh: bool = False, reverse_order: bool = False) -> str:
            logging.warning("使用簡化版 DataDownloader 的 download_and_cache_all_raw_data，功能可能不完整。")
            # 這裡只是一個模擬，實際應有完整的下載邏輯
            if update_callback:
                update_callback(("status", "簡化版下載器正在模擬下載..."))
            time.sleep(1) # 模擬下載時間
            if stop_flag.is_set():
                return "中止"
            if update_callback:
                update_callback(("status", "簡化版下載器模擬完成。"))
            return "完成"

        def delete_all_cached_data(self, interval: str = '1d'): # 修正方法名稱以匹配 main_app_bearish.py
            interval_data_dir = os.path.join(self.data_dir, interval)
            if os.path.exists(interval_data_dir):
                shutil.rmtree(interval_data_dir)
                os.makedirs(interval_data_dir)
                logging.info(f"已刪除並重新創建 {interval_data_dir} 目錄下的所有本地股票原始數據檔案 (簡化版)。")
            # 簡化版不處理 download_status.json

        def _load_download_status(self):
            return {"last_full_download_date": None, "is_complete": False}

        def _is_trading_day_and_after_close(self, current_time: datetime) -> bool:
            return True # 簡化版總是返回 True


def calculate_bollinger_bands(df, window=20, num_std_dev=2):
    """
    為給定的 DataFrame 計算布林通道。
    此函數現在統一使用 'BB_Mid', 'BB_High', 'BB_Low' 作為欄位名稱。
    :param df: 包含 'Close' 價格的 Pandas DataFrame。
    :param window: 計算移動平均和標準差的窗口大小 (天數)。
    :param num_std_dev: 標準差的倍數，用於計算布林上軌和下軌。
    :return: 包含布林通道指標 (BB_Mid, BB_Std, BB_High, BB_Low, Bandwidth) 的 DataFrame。
    """
    if df.empty or len(df) < window:
        # 如果數據不足以計算布林通道，則填充 NaN
        df['BB_Mid'] = pd.NA
        df['BB_Std'] = pd.NA # 確保 BB_Std 也被初始化
        df['BB_High'] = pd.NA
        df['BB_Low'] = pd.NA
        df['Bandwidth'] = pd.NA
        return df

    # 嘗試使用 talib 庫計算布林通道
    try:
        import talib
        # talib.BBANDS 返回 UpperBand, MiddleBand, LowerBand
        df['BB_High'], df['BB_Mid'], df['BB_Low'] = talib.BBANDS(
            df['Close'].values, # talib 需要 NumPy 陣列
            timeperiod=window,
            nbdevup=num_std_dev,
            nbdevdn=num_std_dev,
            matype=0 # SMA
        )
        # talib 不直接返回 StdDev，手動計算
        df['BB_Std'] = df['Close'].rolling(window=window).std()
    except ImportError:
        logging.warning("talib 模組未安裝，使用 pandas 進行布林通道計算。")
        # 如果沒有安裝 talib，則手動計算
        df['BB_Mid'] = df['Close'].rolling(window=window).mean()
        df['BB_Std'] = df['Close'].rolling(window=window).std()
        df['BB_High'] = df['BB_Mid'] + df['BB_Std'] * num_std_dev
        df['BB_Low'] = df['BB_Mid'] - df['BB_Std'] * num_std_dev
    except Exception as e:
        logging.error(f"使用 talib 計算布林通道時發生錯誤: {e}，回退到 pandas 計算。")
        # 如果 talib 存在但計算出錯，也回退到 pandas 計算
        df['BB_Mid'] = df['Close'].rolling(window=window).mean()
        df['BB_Std'] = df['Close'].rolling(window=window).std()
        df['BB_High'] = df['BB_Mid'] + df['BB_Std'] * num_std_dev
        df['BB_Low'] = df['BB_Mid'] - df['BB_Std'] * num_std_dev


    # 計算布林通道寬度 (Bandwidth)，用於判斷通道收縮/擴張
    # 避免除以零
    # 檢查 BB_Mid 是否為零或 NaN，避免除以零錯誤
    # 確保 BB_Mid 至少有一個非 NaN 值
    if df['BB_Mid'].isnull().all() or (not df['BB_Mid'].empty and (df['BB_Mid'].iloc[-1] == 0 or pd.isna(df['BB_Mid'].iloc[-1]))):
        df['Bandwidth'] = pd.NA
    else:
        # 確保 BB_High 和 BB_Low 也不是 NaN
        if (not df['BB_High'].empty and pd.isna(df['BB_High'].iloc[-1])) or \
           (not df['BB_Low'].empty and pd.isna(df['BB_Low'].iloc[-1])):
            df['Bandwidth'] = pd.NA
        else:
            df['Bandwidth'] = ((df['BB_High'] - df['BB_Low']) / df['BB_Mid']) * 100
    return df

def analyze_bollinger_bands_status(df):
    """
    分析布林通道的當前狀態並對股票進行分類。
    假設 DataFrame 按日期排序，最後一行包含最新數據。
    :param df: 包含布林通道指標的 Pandas DataFrame (需包含 'Close', 'BB_Mid', 'BB_High', 'BB_Low', 'Bandwidth' 列)。
    :return: 描述布林通道狀態的字符串 (例如 "飆股格局", "起漲時刻", "通道收縮", "通道擴張", "盤整", "中軌之下", "資料不足", "數據異常")。
    """
    if df.empty:
        return "資料不足"

    # --- ★★★ 新增：檢查均線欄位是否存在 ★★★ ---
    required_cols = ['Close', 'BB_Mid', 'BB_High', 'BB_Low', 'Bandwidth', 'MA5', 'MA20', 'MA60']
    if not all(col in df.columns for col in required_cols):
        missing_cols = [col for col in required_cols if col not in df.columns]
        logging.warning(f"缺少布林通道分析所需的欄位: {', '.join(missing_cols)}")
        return "數據異常 (欄位缺失)"

    df_clean = df.dropna(subset=required_cols)

    if df_clean.empty:
        return "資料不足 (計算後為空)"
    
    if len(df_clean) < 2:
        last_row = df_clean.iloc[-1]
        close = last_row['Close']
        mid = last_row['BB_Mid']
        if pd.isna(close) or pd.isna(mid):
            return "數據異常 (NaN 值)"
        if close < mid:
            return "中軌之下"
        elif close > mid:
            return "中軌之上"
        else:
            return "盤整"
    
    last_row = df_clean.iloc[-1]
    second_last_row = df_clean.iloc[-2]

    close = last_row['Close']
    upper = last_row['BB_High']
    lower = last_row['BB_Low']
    mid = last_row['BB_Mid']
    bandwidth = last_row['Bandwidth']
    # --- ★★★ 新增：獲取均線值 ★★★ ---
    ma5 = last_row['MA5']
    ma20 = last_row['MA20']
    ma60 = last_row['MA60']


    if pd.isna(close) or pd.isna(upper) or pd.isna(lower) or pd.isna(mid) or pd.isna(bandwidth) or pd.isna(ma5) or pd.isna(ma20) or pd.isna(ma60):
        logging.warning(f"布林通道指標存在 NaN 值，無法進行分析。")
        return "數據異常 (NaN 值)"

    # --- ★★★ 新增「四大皆空」判斷邏輯 ★★★ ---
    # 條件：收盤價 < MA5 < MA20 < MA60，且股價在布林下軌附近或更低
    # 這是最強的空頭訊號，所以優先判斷
    is_si_da_jie_kong = (close < ma5) and (ma5 < ma20) and (ma20 < ma60) and (close <= lower * 1.01) # 股價在下軌 1% 範圍內或更低
    if is_si_da_jie_kong:
        return "四大皆空"
    # --- ★★★ 邏輯結束 ★★★ ---

    status = "盤整"

    if close > upper * 1.02 and bandwidth > 10:
        status = "飆股格局"
    elif close > upper and bandwidth > 8:
        status = "飆股格局"
    elif pd.notna(second_last_row['Bandwidth']) and \
         close > mid and close > second_last_row['Close'] and \
         bandwidth > 5 and bandwidth > second_last_row['Bandwidth'] * 1.1:
        status = "起漲時刻"
    elif close > mid and close > second_last_row['Close']:
        status = "起漲時刻"
    elif bandwidth < 3:
        status = "通道收縮"
    elif bandwidth > 5 and pd.notna(second_last_row['Bandwidth']) and bandwidth > second_last_row['Bandwidth'] * 1.1:
        status = "通道擴張"
    
    if close < mid:
        status = "中軌之下"

    return status

def calculate_daily_change(df):
    """
    計算每日價格變動百分比。
    :param df: 包含 'Close' 價格的 Pandas DataFrame。
    :return: 包含 'Change_Pct' 欄位的 DataFrame。
    """
    df['Change_Pct'] = df['Close'].pct_change() * 100
    return df

class StockAnalyzer:
    """
    處理所有股票數據分析、指標計算和篩選的核心邏輯類別。
    此類別現在依賴 DataDownloader 來獲取和管理原始數據。
    """
    def __init__(self, data_dir="stock_data"):
        """
        初始化 StockAnalyzer 類別。
        :param data_dir: 儲存股票數據的目錄名稱 (與 DataDownloader 共享)。
        """
        logging.debug("進入 StockAnalyzer.__init__")
        self.data_dir = data_dir
        self.data_downloader = DataDownloader(data_dir=self.data_dir) 
        self.ticker_names = self._load_ticker_names()
        self.all_daily_data_in_memory = {}
        self._load_all_cached_data_to_memory_and_calculate_indicators() 
        logging.debug("StockAnalyzer 初始化完成。")

    def _load_ticker_names(self):
        """
        從 ticker_names.txt 檔案中載入股票代號、名稱和類別。
        檔案格式：代號 名稱 類別 (例如：2330.TW 台積電 半導體)
        """
        logging.debug(f"進入 _load_ticker_names")
        ticker_info = {}
        try:
            with open("ticker_names.txt", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split(maxsplit=2)
                    if len(parts) == 3:
                        ticker, name, category = parts
                        if name.lower() == ticker.split('.')[0].lower():
                            logging.warning(f"ticker_names.txt 中股票 {ticker} 的名稱似乎與代碼重複 ({name})。請檢查檔案格式。")
                        ticker_info[ticker] = (name, category)
                    elif len(parts) == 2:
                        ticker, name = parts
                        if name.lower() == ticker.split('.')[0].lower():
                            logging.warning(f"ticker_names.txt 中股票 {ticker} 的名稱似乎與代碼重複 ({name})。請檢查檔案格式。")
                        ticker_info[ticker] = (name, "")
                    else:
                        logging.warning(f"ticker_names.txt 中的行不完整: {line.strip()}")

        except FileNotFoundError:
            logging.warning("找不到 ticker_names.txt，使用預設名稱。")
            ticker_info = {
                "2330.TW": ("台積電", "半導體"),
                "2454.TW": ("聯發科", "半導體"),
                "0050.TW": ("元大台灣50", "ETF"),
                "2317.TW": ("鴻海", "電子代工"),
                "1234.TW": ("範例股", "其他")
            }
        except Exception as e:
            logging.error(f"載入 ticker_names.txt 時發生錯誤: {e}", exc_info=True)
            ticker_info = {
                "2330.TW": ("台積電", "半導體"),
                "2454.TW": ("聯發科", "半導體"),
                "0050.TW": ("元大台灣50", "ETF"),
            }
        return ticker_info

    def _load_all_cached_data_to_memory_and_calculate_indicators(self, update_callback=None, stop_flag: threading.Event = None):
        """
        將所有本地快取的原始數據載入記憶體並計算指標。
        此方法現在使用 DataDownloader 的 load_df_from_raw_parquet。
        可以接收 update_callback 和 stop_flag 參數，以便在更新進度時使用。
        """
        logging.debug("進入 _load_all_cached_data_to_memory_and_calculate_indicators")
        self.all_daily_data_in_memory = {}
        interval_data_dir = os.path.join(self.data_dir, '1d')

        if not os.path.exists(interval_data_dir):
            logging.info(f"數據快取目錄 {interval_data_dir} 不存在，跳過載入記憶體。")
            if update_callback:
                update_callback(("status", "數據快取目錄不存在。"))
            return

        all_known_tickers = list(self.ticker_names.keys())
        total_tickers = len(all_known_tickers)
        processed_count = 0

        max_workers_load_calc = min(os.cpu_count() * 8 if os.cpu_count() else 40, 80)
        logging.debug(f"載入並計算指標執行緒池最大工作者數量: {max_workers_load_calc}")

        with ThreadPoolExecutor(max_workers=max_workers_load_calc) as executor:
            futures = {executor.submit(self._load_and_calculate_single_ticker, ticker): ticker for ticker in all_known_tickers}

            for future in as_completed(futures):
                if stop_flag and stop_flag.is_set():
                    logging.info("載入數據並計算指標進程被用戶中止。")
                    executor.shutdown(wait=False, cancel_futures=True)
                    if update_callback:
                        update_callback(("status", "數據載入與指標計算已中止。"))
                    return "中止"

                ticker_name = futures[future]
                try:
                    df_with_indicators = future.result()
                    if df_with_indicators is not None and not df_with_indicators.empty:
                        self.all_daily_data_in_memory[ticker_name] = df_with_indicators
                except Exception as e:
                    logging.error(f"載入並計算 {ticker_name} 指標失敗: {e}", exc_info=True)
                finally:
                    processed_count += 1
                    if update_callback:
                        update_callback(("progress_analysis", processed_count, total_tickers))
                        update_callback(("status", f"正在載入數據並計算指標 ({processed_count}/{total_tickers})..."))

        logging.info(f"所有本地快取數據已載入記憶體並計算指標，共 {len(self.all_daily_data_in_memory)} 檔股票。")
        if update_callback:
            update_callback(("status", "所有資料已載入記憶體並計算指標。"))
        return "完成"

    def _load_and_calculate_single_ticker(self, ticker: str) -> pd.DataFrame | None:
        """
        載入單一股票的原始數據，然後計算其技術指標。
        此函數設計為在 ThreadPoolExecutor 中運行。
        """
        taipei_tz = timezone('Asia/Taipei')
        today = datetime.now(taipei_tz).strftime("%Y-%m-%d")

        df_raw = self.data_downloader.load_df_from_raw_parquet(ticker, MIN_HISTORY_START_DATE, today, interval='1d')

        if df_raw is not None and not df_raw.empty:
            df_with_indicators = self.calculate_indicators(df_raw.copy())
            return df_with_indicators
        return None

    def _calculate_atr(self, df, period=14):
        """
        計算平均真實波動範圍 (Average True Range, ATR)。
        ATR 用於衡量市場波動性。
        """
        if len(df) < period + 1:
            return None
        
        df_temp = df.copy()
        
        df_temp['high_low'] = df_temp['High'] - df_temp['Low']
        df_temp['high_close_prev'] = np.abs(df_temp['High'] - df_temp['Close'].shift(1))
        df_temp['low_close_prev'] = np.abs(df_temp['Low'] - df_temp['Close'].shift(1))
        
        df_temp['tr'] = df_temp[['high_low', 'high_close_prev', 'low_close_prev']].max(axis=1)
        
        atr = df_temp['tr'].ewm(span=period, adjust=False).mean()
        
        return atr.iloc[-1] if not atr.empty else None

    def calculate_indicators(self, df: pd.DataFrame, bb_window=20) -> pd.DataFrame:
        """
        計算股票的技術指標 (MA5, MA20, MA60, 布林通道)。
        此函數現在會根據 ATR 動態調整布林通道的標準差。
        :param df: 包含股票數據的 DataFrame (必須包含 'Close' 列)
        :param bb_window: 布林通道的視窗大小
        :return: 包含技術指標的 DataFrame
        """
        logging.debug("進入 calculate_indicators")
        if df.empty or 'Close' not in df.columns:
            logging.warning("DataFrame 為空或缺少 'Close' 列，無法計算指標。")
            return df

        df = df.sort_index()

        if len(df) < 60:
            logging.warning(f"數據點不足 ({len(df)} < 60)，可能無法計算所有指標。")
            df['MA5'] = pd.NA
            df['MA20'] = pd.NA
            df['MA60'] = pd.NA
            df['BB_Mid'] = pd.NA
            df['BB_Std'] = pd.NA
            df['BB_High'] = pd.NA
            df['BB_Low'] = pd.NA
            df['Bandwidth'] = pd.NA
            df['BB_Std_Dev_Used'] = pd.NA
            df['ATR_Value'] = pd.NA
            return df

        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()

        atr_value = self._calculate_atr(df, period=14)
        
        bb_dev = 2.0

        # *** UPDATE: 修正因 pandas Series 布林值模糊不清所導致的錯誤 ***
        # 將條件判斷拆開，並使用 .values[-1] 來確保獲取的是純量值，避免錯誤
        if atr_value is not None and not df['Close'].empty:
            last_close_price = df['Close'].values[-1] # 使用 .values[-1] 來獲取最後一個純量值
            if last_close_price != 0:
                atr_percentage = (atr_value / last_close_price) * 100
                logging.info(f"股票 {df.name if hasattr(df, 'name') else '未知'} 的最新 ATR 百分比: {atr_percentage:.2f}%")

                if atr_percentage > 3.0:
                    bb_dev = 2.2
                    logging.info(f"ATR 百分比高 ({atr_percentage:.2f}%)，使用較寬的布林通道標準差 {bb_dev}")
                elif atr_percentage > 1.5:
                    bb_dev = 2.1
                    logging.info(f"ATR 百分比中等 ({atr_percentage:.2f}%)，使用中等的布林通道標準差 {bb_dev}")
                else:
                    bb_dev = 2.0
                    logging.info(f"ATR 百分比低 ({atr_percentage:.2f}%)，使用標準布林通道標準差 {bb_dev}")
            else:
                logging.warning(f"股票 {df.name if hasattr(df, 'name') else '未知'} 最新收盤價為零，無法計算 ATR 百分比。使用預設布林通道標準差 2.0")
        else:
            logging.warning(f"股票 {df.name if hasattr(df, 'name') else '未知'} 無法計算 ATR 或收盤價數據為空。使用預設布林通道標準差 2.0")

        try:
            import talib
            df['BB_High'], df['BB_Mid'], df['BB_Low'] = talib.BBANDS(
                df['Close'].values,
                timeperiod=bb_window,
                nbdevup=bb_dev,
                nbdevdn=bb_dev,
                matype=0
            )
            df['BB_Std'] = df['Close'].rolling(window=bb_window).std()
        except ImportError:
            logging.warning("talib 模組未安裝，使用 pandas 進行布林通道計算。")
            df['BB_Mid'] = df['Close'].rolling(window=bb_window).mean()
            df['BB_Std'] = df['Close'].rolling(window=bb_window).std()
            df['BB_High'] = df['BB_Mid'] + df['BB_Std'] * bb_dev
            df['BB_Low'] = df['BB_Mid'] - df['BB_Std'] * bb_dev
        except Exception as e:
            logging.error(f"使用 talib 計算布林通道時發生錯誤: {e}，回退到 pandas 計算。")
            df['BB_Mid'] = df['Close'].rolling(window=bb_window).mean()
            df['BB_Std'] = df['Close'].rolling(window=bb_window).std()
            df['BB_High'] = df['BB_Mid'] + df['BB_Std'] * bb_dev
            df['BB_Low'] = df['BB_Mid'] - df['BB_Std'] * bb_dev

        if 'BB_Mid' in df.columns and not df['BB_Mid'].isnull().all() and \
           (not df['BB_Mid'].empty and pd.notna(df['BB_Mid'].iloc[-1]) and df['BB_Mid'].iloc[-1] != 0):
            if (not df['BB_High'].empty and pd.notna(df['BB_High'].iloc[-1])) and \
               (not df['BB_Low'].empty and pd.notna(df['BB_Low'].iloc[-1])):
                df['Bandwidth'] = ((df['BB_High'] - df['BB_Low']) / df['BB_Mid']) * 100
            else:
                df['Bandwidth'] = pd.NA
        else:
            df['Bandwidth'] = pd.NA
        
        df['BB_Std_Dev_Used'] = bb_dev
        df['ATR_Value'] = atr_value if atr_value is not None else pd.NA

        logging.debug("指標計算完成。")
        return df

    def get_price_on_date(self, ticker: str, date_str: str) -> float | None:
        """
        從記憶體或本地快取中獲取指定股票在指定日期的收盤價。
        """
        logging.debug(f"進入 get_price_on_date, 股票: {ticker}, 日期: {date_str}")
        try:
            target_date = pd.to_datetime(date_str).date()
            taipei_tz = timezone('Asia/Taipei')
            today = datetime.now(taipei_tz).date()

            df = self.all_daily_data_in_memory.get(ticker)

            if df is None or df.empty:
                df_raw = self.data_downloader.load_df_from_raw_parquet(ticker, MIN_HISTORY_START_DATE, today.strftime("%Y-%m-%d"), interval='1d')
                if df_raw is not None and not df_raw.empty:
                    df = self.calculate_indicators(df_raw)
                    self.all_daily_data_in_memory[ticker] = df
                else:
                    logging.warning(f"記憶體和本地快取中都沒有 {ticker} 的數據。")
                    return None

            if df is not None and not df.empty:
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                past_data = df[df.index.date <= target_date]
                if not past_data.empty:
                    price_date = past_data.index[-1]
                    if 'Close' in past_data.columns and pd.notna(past_data.loc[price_date, 'Close']):
                        return past_data.loc[price_date, 'Close']
                    else:
                        logging.warning(f"在 {price_date.strftime('%Y-%m-%d')} 找到 {ticker} 的數據，但收盤價為 NaN。")
                        return None
                else:
                    logging.warning(f"在 {date_str} 或之前沒有找到 {ticker} 的價格數據。")
                    return None
            else:
                logging.warning(f"無法獲取 {ticker} 在 {date_str} 的價格數據。")
                return None
        except Exception as e:
            logging.error(f"獲取 {ticker} 在 {date_str} 的價格時出錯: {e}", exc_info=True)
            return None

    def calculate_price_change_percentage(self, ticker: str, observation_date_str: str) -> tuple[float | None, str]:
        """
        計算指定股票從觀察日期到最新交易日的百分比變化。
        """
        logging.debug(f"進入 calculate_price_change_percentage, 股票: {ticker}, 觀察日期: {observation_date_str}")
        try:
            observation_price = self.get_price_on_date(ticker, observation_date_str)
            if observation_price is None:
                return None, "無法獲取觀察日期的價格。"

            latest_df = self.all_daily_data_in_memory.get(ticker)
            if latest_df is None or latest_df.empty:
                taipei_tz = timezone('Asia/Taipei')
                today = datetime.now(taipei_tz).strftime("%Y-%m-%d")
                df_raw = self.data_downloader.load_df_from_raw_parquet(ticker, MIN_HISTORY_START_DATE, today, interval='1d')
                if df_raw is not None and not df_raw.empty:
                    latest_df = self.calculate_indicators(df_raw)
                    self.all_daily_data_in_memory[ticker] = latest_df
                else:
                    return None, "無法獲取最新交易日的價格。"

            if latest_df is None or latest_df.empty or 'Close' not in latest_df.columns:
                return None, "無法獲取最新交易日的價格。"
            
            if latest_df.index.tz is not None:
                latest_df.index = latest_df.index.tz_localize(None)

            latest_price = latest_df['Close'].iloc[-1]
            if pd.isna(latest_price):
                return None, "最新交易日價格為 NaN。"

            if observation_price == 0:
                return None, "觀察日期的價格為零，無法計算百分比變化。"

            percentage_change = ((latest_price - observation_price) / observation_price) * 100
            return percentage_change, "計算成功。"

        except Exception as e:
            logging.error(f"計算 {ticker} 百分比變化失敗: {e}", exc_info=True)
            return None, f"計算錯誤: {e}"

    def _process_single_ticker_for_bullish_selection(self, ticker, start_date, end_date):
        """
        處理單一股票看漲觀察點篩選邏輯。
        此函數假定數據已載入記憶體並計算好指標。
        """
        logging.debug(f"進入 _process_single_ticker_for_bullish_selection, 股票: {ticker}")
        try:
            df = self.all_daily_data_in_memory.get(ticker)

            if df is None or df.empty:
                logging.warning(f"記憶體中沒有找到 {ticker} 的數據，跳過篩選。這表示股票數據可能未成功載入或計算指標。")
                return None
            
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            required_indicator_cols = ['MA5', 'MA20', 'MA60', 'BB_Mid', 'BB_High', 'BB_Low', 'Bandwidth', 'BB_Std_Dev_Used', 'ATR_Value']
            if not all(col in df.columns for col in required_indicator_cols) or \
               any(df[col].isnull().all() for col in required_indicator_cols):
                logging.warning(f"由於缺少必要的指標列或指標為空，跳過 {ticker} 的看漲篩選。")
                return None

            if len(df) < MIN_DATA_FOR_ANALYSIS:
                logging.warning(f"{ticker} 的數據少於 {MIN_DATA_FOR_ANALYSIS} 個點 ({len(df)} 個點)，無法進行有效分析，跳過篩選。")
                return None

            rise_date = None
            rise_price = None
            
            if len(df) >= MIN_DATA_FOR_ANALYSIS:
                relevant_data = df.tail(MIN_DATA_FOR_ANALYSIS).copy()
            else:
                relevant_data = df.copy()

            if not relevant_data.empty and 'Close' in relevant_data.columns and 'BB_Mid' in relevant_data.columns:
                for i in range(len(relevant_data) - 1, 0, -1):
                    if pd.isna(relevant_data['BB_Mid'].iloc[i]) or pd.isna(relevant_data['BB_Mid'].iloc[i-1]):
                        continue

                    if relevant_data['Close'].iloc[i] > relevant_data['BB_Mid'].iloc[i] and \
                       relevant_data['Close'].iloc[i-1] <= relevant_data['BB_Mid'].iloc[i-1]:
                        rise_date = relevant_data.index[i].strftime("%Y-%m-%d")
                        rise_price = relevant_data['Close'].iloc[i]
                        logging.debug(f"找到 {ticker} 的看漲點: {rise_date} @ {rise_price}")
                        break

            if not df.empty and 'Close' in df.columns and 'MA20' in df.columns and \
               pd.notna(df['MA20'].iloc[-1]) and pd.notna(df['Close'].iloc[-1]) and \
               df['Close'].iloc[-1] > df['MA20'].iloc[-1] and \
               rise_date is not None:

                stock_name, stock_category = self.ticker_names.get(ticker, ("", ""))
                latest_price = df['Close'].iloc[-1]
                latest_volume_shares = df['Volume'].iloc[-1]
                latest_volume_lots = latest_volume_shares / 1000

                if rise_price is not None and rise_price != 0:
                    change_percent = ((latest_price - rise_price) / rise_price) * 100
                    formatted_change_percent = f"{change_percent:.2f}%" if pd.notna(change_percent) else "N/A"
                else:
                    formatted_change_percent = "N/A"

                result = {
                    "代碼": ticker.split('.')[0],
                    "名稱": stock_name,
                    "類別": stock_category,
                    "觀察點日期": rise_date,
                    "觀察點價格": f"{rise_price:.2f}" if isinstance(rise_price, (int, float)) else str(rise_price),
                    "最新價格": f"{latest_price:.2f}",
                    "漲跌幅百分比": formatted_change_percent,
                    "成交量": f"{latest_volume_lots:,.0f}",
                    "raw_volume": latest_volume_shares,
                    "布林通道狀態": analyze_bollinger_bands_status(df),
                    "標準差": f"{df['BB_Std_Dev_Used'].iloc[-1]:.1f}" if pd.notna(df['BB_Std_Dev_Used'].iloc[-1]) else "N/A",
                    "ATR": f"{df['ATR_Value'].iloc[-1]:.2f}" if pd.notna(df['ATR_Value'].iloc[-1]) else "N/A"
                }
                return result
            else:
                logging.debug(f"跳過 {ticker} 的看漲篩選邏輯: 條件不滿足。")
                return None
        except Exception as e:
            logging.error(f"處理 {ticker} 看漲篩選時出錯: {e}", exc_info=True)
            return None

    def _process_single_ticker_for_bearish_selection(self, ticker, start_date, end_date):
        """
        處理單一股票看跌觀察點篩選邏輯 (跌破布林中軌)。
        此函數假定數據已載入記憶體並計算好指標。
        """
        logging.debug(f"進入 _process_single_ticker_for_bearish_selection, 股票: {ticker}")
        try:
            df = self.all_daily_data_in_memory.get(ticker)

            if df is None or df.empty:
                logging.warning(f"記憶體中沒有找到 {ticker} 的數據，跳過看跌篩選。")
                return None

            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            required_indicator_cols = ['MA5', 'MA20', 'MA60', 'BB_Mid', 'BB_High', 'BB_Low', 'Bandwidth', 'BB_Std_Dev_Used', 'ATR_Value']
            if not all(col in df.columns for col in required_indicator_cols) or \
               any(df[col].isnull().all() for col in required_indicator_cols):
                logging.warning(f"由於缺少必要的指標列或指標為空，跳過 {ticker} 的看跌篩選。")
                return None

            if len(df) < MIN_DATA_FOR_ANALYSIS:
                logging.warning(f"{ticker} 的數據少於 {MIN_DATA_FOR_ANALYSIS} 個點 ({len(df)} 個點)，無法進行有效分析，跳過看跌篩選。")
                return None

            fall_date = None
            fall_price = None
            
            if len(df) >= MIN_DATA_FOR_ANALYSIS:
                relevant_data = df.tail(MIN_DATA_FOR_ANALYSIS).copy()
            else:
                relevant_data = df.copy()

            if not relevant_data.empty and 'Close' in relevant_data.columns and 'BB_Mid' in relevant_data.columns:
                for i in range(len(relevant_data) - 1, 0, -1):
                    if pd.isna(relevant_data['BB_Mid'].iloc[i]) or pd.isna(relevant_data['BB_Mid'].iloc[i-1]):
                        continue

                    if relevant_data['Close'].iloc[i] < relevant_data['BB_Mid'].iloc[i] and \
                       relevant_data['Close'].iloc[i-1] >= relevant_data['BB_Mid'].iloc[i-1]:
                        fall_date = relevant_data.index[i].strftime("%Y-%m-%d")
                        fall_price = relevant_data['Close'].iloc[i]
                        logging.debug(f"找到 {ticker} 的看跌點: {fall_date} @ {fall_price}")
                        break

            if not df.empty and 'Close' in df.columns and 'MA20' in df.columns and \
               pd.notna(df['MA20'].iloc[-1]) and pd.notna(df['Close'].iloc[-1]) and \
               df['Close'].iloc[-1] < df['MA20'].iloc[-1] and \
               fall_date is not None:

                stock_name, stock_category = self.ticker_names.get(ticker, ("", ""))
                latest_price = df['Close'].iloc[-1]
                latest_volume_shares = df['Volume'].iloc[-1]
                latest_volume_lots = latest_volume_shares / 1000

                if fall_price is not None and fall_price != 0:
                    change_percent = ((latest_price - fall_price) / fall_price) * 100
                    formatted_change_percent = f"{change_percent:.2f}%" if pd.notna(change_percent) else "N/A"
                else:
                    formatted_change_percent = "N/A"

                result = {
                    "代碼": ticker.split('.')[0],
                    "名稱": stock_name,
                    "類別": stock_category,
                    "觀察點日期": fall_date,
                    "觀察點價格": f"{fall_price:.2f}" if isinstance(fall_price, (int, float)) else str(fall_price),
                    "最新價格": f"{latest_price:.2f}",
                    "漲跌幅百分比": formatted_change_percent,
                    "成交量": f"{latest_volume_lots:,.0f}",
                    "raw_volume": latest_volume_shares,
                    "布林通道狀態": analyze_bollinger_bands_status(df),
                    "標準差": f"{df['BB_Std_Dev_Used'].iloc[-1]:.1f}" if pd.notna(df['BB_Std_Dev_Used'].iloc[-1]) else "N/A",
                    "ATR": f"{df['ATR_Value'].iloc[-1]:.2f}" if pd.notna(df['ATR_Value'].iloc[-1]) else "N/A"
                }
                return result
            else:
                logging.debug(f"跳過 {ticker} 的看跌篩選邏輯: 條件不滿足。")
                return None
        except Exception as e:
            logging.error(f"處理 {ticker} 看跌篩選時出錯: {e}", exc_info=True)
            return None

    def _process_single_ticker_for_custom_date_selection(self, ticker, custom_observation_date_str):
        """
        處理單一股票從指定 custom_observation_date_str 到最新價格的百分比變化計算。
        此函數假定數據已載入記憶體並計算好指標。
        """
        logging.debug(f"進入 _process_single_ticker_for_custom_date_selection, 股票: {ticker}, 觀察日期: {custom_observation_date_str}")
        try:
            observation_price = self.get_price_on_date(ticker, custom_observation_date_str)
            if observation_price is None:
                logging.warning(f"無法獲取 {ticker} 在指定觀察日期 {custom_observation_date_str} 的價格，跳過篩選。")
                return None

            latest_df = self.all_daily_data_in_memory.get(ticker)
            if latest_df is None or latest_df.empty:
                logging.warning(f"記憶體中沒有 {ticker} 的最新數據，跳過篩選。")
                return None

            if latest_df.index.tz is not None:
                latest_df.index = latest_df.index.tz_localize(None)

            if 'Close' not in latest_df.columns or pd.isna(latest_df['Close'].iloc[-1]) or \
               'Volume' not in latest_df.columns or pd.isna(latest_df['Volume'].iloc[-1]):
                logging.warning(f"{ticker} 的最新收盤價或成交量數據缺失，跳過篩選。")
                return None

            latest_price = latest_df['Close'].iloc[-1]
            latest_volume_shares = latest_df['Volume'].iloc[-1]
            latest_volume_lots = latest_volume_shares / 1000

            if observation_price == 0:
                logging.warning(f"{ticker} 在觀察日期 {custom_observation_date_str} 的價格為零，無法計算百分比變化。")
                return None

            change_percent = ((latest_price - observation_price) / observation_price) * 100
            formatted_change_percent = f"{change_percent:.2f}%" if pd.notna(change_percent) else "N/A"

            stock_name, stock_category = self.ticker_names.get(ticker, ("", ""))

            result = {
                "代碼": ticker.split('.')[0],
                "名稱": stock_name,
                "類別": stock_category,
                "觀察點日期": custom_observation_date_str,
                "觀察點價格": f"{observation_price:.2f}",
                "最新價格": f"{latest_price:.2f}",
                "漲跌幅百分比": formatted_change_percent,
                "成交量": f"{latest_volume_lots:,.0f}",
                "raw_volume": latest_volume_shares,
                "布林通道狀態": analyze_bollinger_bands_status(latest_df),
                "標準差": f"{latest_df['BB_Std_Dev_Used'].iloc[-1]:.1f}" if pd.notna(latest_df['BB_Std_Dev_Used'].iloc[-1]) else "N/A",
                "ATR": f"{latest_df['ATR_Value'].iloc[-1]:.2f}" if pd.notna(latest_df['ATR_Value'].iloc[-1]) else "N/A"
            }
            return result
        except Exception as e:
            logging.error(f"處理 {ticker} 指定日期篩選時出錯: {e}", exc_info=True)
            return None

    def run_stock_selection(self, tickers: list, start_date: str, end_date: str, selection_type="bullish", low_price=None, high_price=None, update_callback=None, stop_flag=None, reverse_order: bool = False, custom_observation_date_str: str = None):
        """
        執行股票篩選邏輯，現在支援看漲、看跌和自定義日期漲幅篩選。
        此函數假定所有必要的數據已在 self.all_daily_data_in_memory 中。

        :param tickers: 要篩選的股票代號列表。
        :param start_date: 數據開始日期 (可能不直接用於自定義日期篩選)。
        :param end_date: 數據結束日期 (可能不直接用於自定義日期篩選)。
        :param selection_type: 篩選類型 ("bullish" 為看漲點, "bearish" 為看跌點, "custom_date_gain" 為自定義日期漲幅)。
        :param low_price: 最新價格下限篩選。
        :param high_price: 最新價格上限篩選。
        :param update_callback: 進度更新的回調函數。
        :param stop_flag: 用於控制進程終止的執行緒事件旗標。
        :param reverse_order: 如果為 True，則從列表中的最後一個股票開始處理。
        :param custom_observation_date_str: 指定觀察日期的字串 (YYYY-MM-DD)，僅用於 "custom_date_gain" 篩選。
        :return: 符合篩選條件的股票列表。
        """
        logging.info(f"股票篩選開始 ({selection_type} 類型), 順序: {'反向' if reverse_order else '正向'}...")
        results = []

        tickers_to_process = tickers[::-1] if reverse_order else tickers
        total_tickers = len(tickers_to_process)
        processed_count = 0

        max_workers_selection = min(os.cpu_count() * 12 if os.cpu_count() else 60, 140)
        logging.debug(f"篩選執行緒池最大工作者數量: {max_workers_selection}")

        with ThreadPoolExecutor(max_workers=max_workers_selection) as executor:
            futures = []
            if selection_type == "bullish":
                futures = [executor.submit(self._process_single_ticker_for_bullish_selection, ticker, start_date, end_date) for ticker in tickers_to_process]
            elif selection_type == "bearish":
                futures = [executor.submit(self._process_single_ticker_for_bearish_selection, ticker, start_date, end_date) for ticker in tickers_to_process]
            elif selection_type == "custom_date_gain":
                if not custom_observation_date_str:
                    logging.error("執行 'custom_date_gain' 篩選時未提供 custom_observation_date_str。")
                    return []
                futures = [executor.submit(self._process_single_ticker_for_custom_date_selection, ticker, custom_observation_date_str) for ticker in tickers_to_process]
            else:
                logging.error(f"未知篩選類型: {selection_type}")
                return []

            for future in as_completed(futures):
                if stop_flag and stop_flag.is_set():
                    logging.info("篩選已停止。")
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                try:
                    result = future.result()
                    if result:
                        latest_price_str = result.get("最新價格")
                        if latest_price_str:
                            try:
                                latest_price = float(latest_price_str.replace(',', ''))
                                if (low_price is None or latest_price >= low_price) and \
                                   (high_price is None or latest_price <= high_price):
                                    results.append(result)
                            except ValueError:
                                logging.warning(f"無法解析股票 {result.get('代碼', '')} 的最新價格: {latest_price_str}")
                except Exception as e:
                    logging.error(f"獲取並行任務結果時出錯: {e}", exc_info=True)
                finally:
                    processed_count += 1
                    if update_callback:
                        update_callback(("update_selection_progress", processed_count, total_tickers))

        logging.info(f"股票篩選完成 ({selection_type} 類型)。")
        return results

    def ensure_local_data_and_calculate_indicators(self, tickers: list, update_callback=None, stop_flag: threading.Event = None, data_downloader_instance=None) -> str: # 新增 data_downloader_instance 參數
        """
        確保本地有最新的原始數據，然後載入這些數據並計算指標，填充到記憶體中。
        此函數將在分析前被呼叫。

        :param tickers: 要處理的股票代號列表。
        :param update_callback: 進度更新的回調函數。
        :param stop_flag: 用於控制進程終止的執行緒事件旗標。
        :param data_downloader_instance: 外部傳入的 DataDownloader 實例。
        :return: 處理狀態 ("完成" 或 "中止")。
        """
        logging.info(f"開始確保本地數據並計算指標流程，共 {len(tickers)} 檔股票。")

        downloader = data_downloader_instance if data_downloader_instance else self.data_downloader

        total_tickers = len(tickers)
        processed_count = 0
        self.all_daily_data_in_memory = {}

        max_workers_load_calc = min(os.cpu_count() * 12 if os.cpu_count() else 60, 140)
        logging.debug(f"載入並計算指標執行緒池最大工作者數量: {max_workers_load_calc}")

        start_time = time.time()
        with ThreadPoolExecutor(max_workers=max_workers_load_calc) as executor:
            futures = {executor.submit(self._load_and_calculate_single_ticker_with_downloader, ticker, downloader): ticker for ticker in tickers}

            for future in as_completed(futures):
                if stop_flag and stop_flag.is_set():
                    logging.info("載入數據並計算指標進程被用戶中止。")
                    executor.shutdown(wait=False, cancel_futures=True)
                    if update_callback:
                        update_callback(("status", "數據載入與指標計算已中止。"))
                    return "中止"

                ticker_name = futures[future]
                try:
                    df_with_indicators = future.result()
                    if df_with_indicators is not None and not df_with_indicators.empty:
                        self.all_daily_data_in_memory[ticker_name] = df_with_indicators
                except Exception as e:
                    logging.error(f"載入並計算 {ticker_name} 指標失敗: {e}", exc_info=True)
                finally:
                    processed_count += 1
                    if update_callback:
                        update_callback(("progress_analysis", processed_count, total_tickers))
                        update_callback(("status", f"正在載入數據並計算指標 ({processed_count}/{total_tickers})..."))

        end_time = time.time()
        duration = end_time - start_time
        if update_callback:
            update_callback(("analysis_time", duration))

        if len(self.all_daily_data_in_memory) == total_tickers:
            logging.info(f"所有股票數據已成功載入記憶體並計算指標，共 {total_tickers} 檔股票。")
            return "完成"
        else:
            logging.warning(f"股票數據載入與指標計算完成，但有 {total_tickers - len(self.all_daily_data_in_memory)} 檔股票的數據無法處理。")
            return "部分完成"

    def _load_and_calculate_single_ticker_with_downloader(self, ticker: str, downloader_instance) -> pd.DataFrame | None:
        """
        載入單一股票的原始數據，然後計算其技術指標。
        此函數設計為在 ThreadPoolExecutor 中運行，並使用傳入的 downloader 實例。
        """
        taipei_tz = timezone('Asia/Taipei')
        today = datetime.now(taipei_tz).strftime("%Y-%m-%d")

        df_raw = downloader_instance.load_df_from_raw_parquet(ticker, MIN_HISTORY_START_DATE, today, interval='1d')

        if df_raw is not None and not df_raw.empty:
            df_with_indicators = self.calculate_indicators(df_raw.copy())
            return df_with_indicators
        return None


    def run_integrated_analysis(self, tickers: list, start_date: str, end_date: str,
                                low_price: float | None = None, high_price: float | None = None,
                                selection_type: str = "bullish",
                                update_callback=None, stop_flag: threading.Event = None,
                                force_full_refresh: bool = False,
                                custom_observation_date_str: str = None,
                                data_downloader_instance=None) -> list:
        """
        執行整合的股票分析流程：首先確保本地有最新原始數據，然後載入並計算指標，最後執行篩選。

        :param tickers: 要分析的股票代號列表。
        :param start_date: 數據開始日期 (格式 "YYYY-MM-DD")。
        :param end_date: 數據結束日期 (格式 "YYYY-M-D)。
        :param low_price: 篩選條件：最新價格下限。
        :param high_price: 最新價格上限篩選。
        :param selection_type: 篩選類型 ("bullish" 為看漲點, "bearish" 為看跌點, "custom_date_gain" 為自定義日期漲幅)。
        :param update_callback: 進度更新的回調函數。
        :param stop_flag: 用於控制進程終止的執行緒事件旗標。
        :param force_full_refresh: 是否強制完整更新原始數據 (刪除舊數據並重新下載)。
        :param custom_observation_date_str: 指定觀察日期的字串 (YYYY-MM-DD)，僅用於 "custom_date_gain" 篩選。
        :param data_downloader_instance: 外部傳入的 DataDownloader 實例，用於數據下載。
        :return: 符合篩選條件的股票列表。
        """
        logging.info(f"開始整合股票分析流程 ({selection_type} 篩選): 首先下載原始數據，然後載入並計算指標，最後篩選。")

        downloader = data_downloader_instance if data_downloader_instance else self.data_downloader

        if update_callback:
            update_callback(("status", "正在下載並快取原始股票數據..."))

        reverse_download_order = (selection_type == "bearish")

        download_result = downloader.download_and_cache_all_raw_data(
            tickers, stop_flag, update_callback, force_full_refresh=force_full_refresh, reverse_order=reverse_download_order
        )

        if download_result == "中止":
            logging.info("原始數據下載被用戶中止，跳過後續分析。")
            if update_callback:
                update_callback(("status", "原始數據下載已中止。"))
            return []
        elif download_result == "完成":
            logging.info("所有股票原始數據已下載完成。")
        else:
            logging.warning("原始數據下載狀態未知或部分完成，仍嘗試進行後續分析。")

        if stop_flag and stop_flag.is_set():
            logging.info("在原始數據下載後，分析流程被用戶中止。")
            if update_callback:
                update_callback(("status", "分析已中止。"))
            return []

        if update_callback:
            update_callback(("status", "正在載入本地數據並計算技術指標..."))

        load_calc_result = self.ensure_local_data_and_calculate_indicators(tickers, update_callback, stop_flag, data_downloader_instance=downloader)

        if load_calc_result == "中止":
            logging.info("數據載入與指標計算被用戶中止，跳過篩選。")
            if update_callback:
                update_callback(("status", "分析已中止。"))
            return []
        elif load_calc_result == "完成":
            logging.info("所有股票數據已載入記憶體並計算指標完成。")
        else:
            logging.warning("數據載入與指標計算狀態未知或部分完成，仍嘗試進行篩選。")

        if stop_flag and stop_flag.is_set():
            logging.info("在數據載入與指標計算後，篩選流程被用戶中止。")
            if update_callback:
                update_callback(("status", "分析已中止。"))
            return []

        if update_callback:
            if selection_type == "bullish":
                update_callback(("status", "正在進行股票上升點篩選...\n(布林通道狀態判斷中)"))
            elif selection_type == "bearish":
                update_callback(("status", "正在進行股票下降點篩選...\n(布林通道狀態判斷中)"))
            elif selection_type == "custom_date_gain":
                update_callback(("status", f"正在進行從 {custom_observation_date_str} 到今日的漲幅篩選...\n(布林通道狀態判斷中)"))

        reverse_selection_order = (selection_type == "bearish" or selection_type == "custom_date_gain")

        selection_results = self.run_stock_selection(
            tickers,
            start_date,
            end_date,
            selection_type,
            low_price,
            high_price,
            update_callback,
            stop_flag,
            reverse_order=reverse_selection_order,
            custom_observation_date_str=custom_observation_date_str
        )

        if update_callback:
            update_callback(("status", "整合分析流程完成。"))
        logging.info("整合分析流程完成。")

        return selection_results
    def find_impression_stocks(self, original_results: list, t0_gain_threshold: float = 0.0, t1_gain_threshold: float = 8.0, t2_gain_threshold: float = 10.0, volume_multiplier=1.2) -> list:
        """
        [最終修正]
        從原始篩選結果中進行二次篩選，找出符合“印象派飆股”條件的股票。
        T 日: 檢查布林通道狀態 (避免被 0.00% 漲幅和不穩定的成交量卡住)。
        T-1/T-2: 檢查漲幅和成交量倍數 (尋找強勢隔日衝標的)。
        """
        logging.info(f"開始進行二次篩選：尋找印象派飆股 (T > {t0_gain_threshold}%, T-1 > {t1_gain_threshold}%, T-2 > {t2_gain_threshold}%), 成交量倍數: {volume_multiplier}X...")
        impression_stocks = []
        
        try:
            taipei_tz = timezone('Asia/Taipei')
            today = datetime.now(taipei_tz).date()
            # 使用 pandas 的 BDay (Business Day) 來處理交易日，更精確
            # 注意: 雖然 BDay 導入了，但這裡的程式碼需要整個 stock_analyzer.py 檔案頂部有 pd 的導入
            one_trading_day_ago = (today - pd.tseries.offsets.BDay(1)).date()
            two_trading_days_ago = (today - pd.tseries.offsets.BDay(2)).date()
            
            logging.info(f"二次篩選日期條件：觀察點需在 {today.strftime('%Y-%m-%d')}, {one_trading_day_ago.strftime('%Y-%m-%d')} 或 {two_trading_days_ago.strftime('%Y-%m-%d')}")

            for stock_result in original_results:
                observation_date_str = stock_result.get("觀察點日期")
                if not observation_date_str: continue

                observation_date = datetime.strptime(observation_date_str, "%Y-%m-%d").date()

                # 檢查觀察點日期是否為 T, T-1 或 T-2
                if observation_date not in [today, one_trading_day_ago, two_trading_days_ago]:
                    continue

                stock_code_raw = stock_result.get("代碼")
                full_ticker = None
                for t_key in self.ticker_names.keys():
                    if t_key.startswith(stock_code_raw + "."):
                        full_ticker = t_key
                        break
                
                if not full_ticker: continue
                
                df = self.all_daily_data_in_memory.get(full_ticker)
                if df is None or df.empty or len(df) < 20: continue
                
                observation_price_str = stock_result.get("觀察點價格", "0").replace(',', '')
                observation_price = float(observation_price_str)
                if observation_price == 0: continue
                
                latest_price = df['Close'].iloc[-1]
                latest_volume = df['Volume'].iloc[-1]
                volume_ma20 = df['Volume'].rolling(window=20).mean().iloc[-1]
                # 成交量突破條件 (用於 T-1 和 T-2)
                is_volume_breakthrough = latest_volume > (volume_ma20 * volume_multiplier) 
                
                total_gain_percent = ((latest_price - observation_price) / observation_price) * 100
                
                # ▼▼▼▼▼ 這裡是本次修改的核心 ▼▼▼▼▼
                # 為所有符合條件的股票都添加成交量資訊
                volume_in_lots = latest_volume / 1000
                
                # --- T-2 規則 (高漲幅 + 成交量突破) ---
                if observation_date == two_trading_days_ago:
                    if total_gain_percent > t2_gain_threshold and is_volume_breakthrough:
                        impression_stocks.append({
                            "代碼": stock_code_raw, "名稱": stock_result.get("名稱", ""),
                            "觀察點日期": observation_date_str, "觀察點價格": f"{observation_price:.2f}",
                            "最新價格": f"{latest_price:.2f}", "期間": "2日",
                            "漲跌幅": f"{total_gain_percent:.2f}%",
                            "當日成交量": f"{int(volume_in_lots):,}", # 新增欄位
                            "raw_volume": latest_volume, # 新增原始成交量，用於排序
                            "full_ticker": full_ticker
                        })
                
                # --- T-1 規則 (高漲幅 + 成交量突破) ---
                elif observation_date == one_trading_day_ago:
                    if total_gain_percent > t1_gain_threshold and is_volume_breakthrough:
                        impression_stocks.append({
                            "代碼": stock_code_raw, "名稱": stock_result.get("名稱", ""),
                            "觀察點日期": observation_date_str, "觀察點價格": f"{observation_price:.2f}",
                            "最新價格": f"{latest_price:.2f}", "期間": "1日",
                            "漲跌幅": f"{total_gain_percent:.2f}%",
                            "當日成交量": f"{int(volume_in_lots):,}", # 新增欄位
                            "raw_volume": latest_volume, # 新增原始成交量，用於排序
                            "full_ticker": full_ticker
                        })
                
                # --- T (今日) 規則 (漲幅通過 + 布林狀態強勢) ---
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
                            "代碼": stock_code_raw, "名稱": stock_result.get("名稱", ""),
                            "觀察點日期": observation_date_str, 
                            "觀察點價格": f"{latest_open:.2f}",      # 觀察點價格改為今日開盤價
                            "最新價格": f"{latest_price:.2f}", 
                            "期間": "當日",
                            "漲跌幅": f"{t0_max_gain_percent:.2f}% (高/開)", # 顯示 (最高價/開盤價) 漲幅
                            "當日成交量": f"{int(volume_in_lots):,}",
                            "raw_volume": latest_volume, 
                            "full_ticker": full_ticker
                        })

        except Exception as e:
            logging.error(f"執行印象派飆股二次篩選時發生錯誤: {e}", exc_info=True)

        logging.info(f"二次篩選完成，共找到 {len(impression_stocks)} 檔印象派飆股。")
        return impression_stocks
