import tkinter as tk
from tkinter import ttk

def create_t_day_filter_widgets(parent_frame, t0_gain_variable):
    """
    在指定的父框架中創建 T日 (今日) 篩選條件的 UI 元件。
    這個函數被設計為一個獨立的模組，以便擴充主應用程式的功能，
    而無需大幅修改主程式碼。

    :param parent_frame: 由主應用程式傳入，用於放置新 UI 元件的 ttk.Frame。
    :param t0_gain_variable: 由主應用程式傳入的 tk.StringVar，用於綁定 T日 漲幅輸入框。
    """
    # 創建一個標籤，提示使用者這是 T 日的漲幅篩選
    ttk.Label(parent_frame, text=" T(今日)漲幅(%):").pack(side="left", padx=(10, 2))
    
    # 創建一個輸入框，讓使用者可以設定 T 日的漲幅閾值
    t0_gain_entry = ttk.Entry(parent_frame, textvariable=t0_gain_variable, width=6)
    t0_gain_entry.pack(side="left")
