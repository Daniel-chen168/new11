import os
import logging
import json
import configparser  # 用于 INI 文件加载

# 共享配置常量（打破循环导入）
CONFIG_DIR = os.path.join(os.getcwd(), 'config')
MAILING_LIST_FILE = os.path.join(CONFIG_DIR, 'mailing_list.json')
TELEGRAM_SETTINGS_FILE = os.path.join(CONFIG_DIR, 'telegram_settings.json')
WATCHLIST_FILE = os.path.join(CONFIG_DIR, 'watchlist.json')
SCHEDULER_SETTINGS_FILE = os.path.join(CONFIG_DIR, 'scheduler_settings.json')
EMAIL_CONFIG_FILE = os.path.join(CONFIG_DIR, 'email_config.ini')  # 邮箱 INI 文件

def ensure_config_dir():
    """确保 config 目录存在"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    logging.info("Config 目录已确保存在。")

def load_json_config(filepath):
    """通用 JSON 加载函数"""
    ensure_config_dir()
    if not os.path.exists(filepath):
        logging.info(f"配置文件 {filepath} 不存在，返回空字典。")
        return {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logging.info(f"配置文件 {filepath} 加载成功。")
        return data
    except json.JSONDecodeError as e:
        logging.error(f"加载 {filepath} 失败 (JSON 格式错误): {e}")
        return {}
    except Exception as e:
        logging.error(f"加载 {filepath} 失败: {e}")
        return {}

def save_json_config(data, filepath):
    """通用 JSON 保存函数"""
    ensure_config_dir()
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logging.info(f"配置文件 {filepath} 保存成功。")
    except Exception as e:
        logging.error(f"保存 {filepath} 失败: {e}")
        raise

def load_email_config():
    """加载邮箱配置（从 email_config.ini）"""
    ensure_config_dir()
    config = configparser.ConfigParser()
    filepath = EMAIL_CONFIG_FILE
    if not os.path.exists(filepath):
        logging.warning(f"邮箱配置文件 {filepath} 不存在，返回空配置。")
        return {}
    try:
        config.read(filepath, encoding='utf-8')
        # 假设 INI 格式：[DEFAULT] smtp_server=... 等
        data = dict(config['DEFAULT']) if config.has_section('DEFAULT') else {}
        logging.info(f"邮箱配置文件 {filepath} 加载成功。")
        return data
    except Exception as e:
        logging.error(f"加载邮箱配置失败: {e}")
        return {}
