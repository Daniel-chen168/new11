# telegram_integration.py
import json
import os
from telegram import Bot
import asyncio
import logging
import httpx # Ensure httpx is imported
import telegram.request # Ensure telegram.request is imported

TELEGRAM_SETTINGS_FILE = "telegram_settings.json"

def save_telegram_settings(token, chat_id):
    """
    儲存 Telegram Bot Token 和 Chat ID 到設定檔。
    :param token: Telegram Bot 的 Token。
    :param chat_id: 用於發送訊息的 Chat ID。
    """
    logging.debug("進入 save_telegram_settings")
    config_dir = os.path.join(os.getcwd(), 'config')
    os.makedirs(config_dir, exist_ok=True)
    filepath = os.path.join(config_dir, TELEGRAM_SETTINGS_FILE)
    try:
        # 使用 bot_token 和 chat_id 作為鍵名，保持一致性
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({'bot_token': token, 'chat_id': chat_id}, f, indent=4, ensure_ascii=False)
        logging.info("Telegram 設定已儲存。")
    except Exception as e:
        logging.error(f"儲存 Telegram 設定失敗: {e}")
        raise

def load_telegram_settings():
    """
    從設定檔載入 Telegram Bot Token 和 Chat ID。
    :return: 包含 'bot_token' 和 'chat_id' 的字典，如果檔案不存在或載入失敗則為 None。
    """
    logging.debug("進入 load_telegram_settings")
    filepath = os.path.join(os.getcwd(), 'config', TELEGRAM_SETTINGS_FILE)
    if not os.path.exists(filepath):
        logging.info("Telegram 設定檔不存在，返回空設定。")
        return {"bot_token": None, "chat_id": None} # 返回字典

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            # 兼容舊的 'token' 鍵名，如果存在則使用它
            bot_token = settings.get('bot_token') or settings.get('token')
            chat_id = settings.get('chat_id')
            logging.info("Telegram 設定載入成功。")
            return {"bot_token": bot_token, "chat_id": chat_id} # 返回字典
    except json.JSONDecodeError as e:
        logging.error(f"載入 Telegram 設定檔失敗 (JSON 格式錯誤): {e}")
        return {"bot_token": None, "chat_id": None} # 返回字典
    except Exception as e:
        logging.error(f"載入 Telegram 設定檔失敗: {e}")
        return {"bot_token": None, "chat_id": None} # 返回字典

class TelegramBotSender:
    """
    用於發送訊息和檔案到 Telegram 的類別。
    """
    def __init__(self, bot_token, chat_id):
        """
        初始化 TelegramBotSender。
        :param bot_token: Telegram Bot 的 Token。
        :param chat_id: 用於發送訊息的 Chat ID。
        """
        logging.debug(f"進入 TelegramBotSender.__init__, chat_id: {chat_id}")
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(50.0),
            limits=httpx.Limits(max_connections=20),
        )
        self.bot = Bot(
            token=bot_token,
            request=telegram.request.HTTPXRequest(
                connect_timeout=50.0,
                read_timeout=50.0
            )
        )
        self.chat_id = chat_id
        logging.debug("TelegramBotSender 初始化完成。")

    async def send_message_async(self, message):
        """
        非同步發送文本訊息到 Telegram。
        :param message: 要發送的文本訊息。
        """
        logging.debug(f"進入 send_message_async, 訊息: {message}")
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=message)
            logging.debug("訊息發送成功。")
        except telegram.error.TelegramError as e:
            logging.error(f"發送訊息失敗 (Telegram 錯誤): {e}")
            raise
        except Exception as e:
            logging.error(f"發送訊息失敗: {e}")
            raise

    async def send_file_async(self, filepath, caption=""):
        """
        非同步發送檔案到 Telegram。
        :param filepath: 要發送的檔案路徑。
        :param caption: 檔案的文字說明。
        """
        logging.debug(f"進入 send_file_async, 檔案路徑: {filepath}")
        try:
            with open(filepath, 'rb') as f:
                if filepath.lower().endswith(('.png', '.jpg', '.jpeg')):
                    await self.bot.send_photo(chat_id=self.chat_id, photo=f, caption=caption)
                else:
                    await self.bot.send_document(chat_id=self.chat_id, document=f, caption=caption)
            logging.debug("檔案發送成功。")
        except FileNotFoundError:
            logging.error(f"發送檔案失敗: 檔案未找到 {filepath}")
            raise
        except telegram.error.TelegramError as e:
            logging.error(f"發送檔案失敗 (Telegram 錯誤): {e}")
            raise
        except Exception as e:
            logging.error(f"發送檔案失敗: {e}")
            raise
