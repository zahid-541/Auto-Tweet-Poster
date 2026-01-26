# bot.py
import logging
import threading
import time
from telebot import TeleBot, types, apihelper
import traceback

# Import from main.py
from main import (
    status_report,
    preview_next,
    post_one,
    set_schedule,
    get_schedule,
    set_model,
    schedule_runner,
    reset_rate_limit,
    set_admin_notifier,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_ADMIN_ID,
    USE_MODEL,
    POSTS_TODAY
)

# -------------------------
# Logging
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_debug.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# -------------------------
# Bot Configuration
# -------------------------
BOT_TOKEN = TELEGRAM_BOT_TOKEN
ADMIN = TELEGRAM_ADMIN_ID

if not ADMIN:
    logger.error("TELEGRAM_ADMIN_ID not set!")
    raise ValueError("TELEGRAM_ADMIN_ID must be set in main.py")

apihelper.CONNECT_TIMEOUT = 120
apihelper.READ_TIMEOUT = 120

bot = TeleBot(BOT_TOKEN)

# Register admin notifier
def _send_admin_alert(text: str):
    try:
        bot.send_message(ADMIN, f"🔔 Admin Alert:\n\n{text}")
    except Exception as e:
        logger.exception("Failed to send admin message: %s", e)

set_admin_notifier(_send_admin_alert)

# -------------------------
# Helpers
# -------------------------
def admin_only(func):
    def wrapper(message, *args, **kwargs):
        try:
            user_id = getattr(message.from_user, "id", None)
            logger.info("Message from %s: %s", user_id, getattr(message, "text", ""))
            
            if user_id != ADMIN:
                bot.reply_to(message, f"❌ Unauthorized. Your ID: {user_id}")
                return
            return func(message, *args, **kwargs)
        except Exception as e:
            logger.exception("Handler error: %s", e)
            try:
                bot.reply_to(message, f"❌ Error: {str(e)}")
            except:
                pass
    return wrapper

def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📊 Status", "👁️ Preview Next")
    kb.row("🚀 Post Now", "🤖 Set Model")
    kb.row("⏰ Set Schedule", "🔄 Reset Limit")
    kb.row("🏓 Ping")
    return kb

def send_result(message, text):
    try:
        bot.reply_to(message, text, parse_mode="Markdown")
    except:
        try:
            bot.reply_to(message, text)
        except Exception as e:
            logger.exception("Failed to reply: %s", e)

# -------------------------
# Start Command
# -------------------------
@bot.message_handler(commands=["start"])
@admin_only
def start_cmd(message):
    try:
        schedule_times = get_schedule()
        schedule_str = ", ".join(schedule_times) if schedule_times else "Not set"
        
        welcome = (
            "🤖 *AutoPoster Bot Ready*\n\n"
            f"✅ Admin: `{message.from_user.id}`\n"
            f"🤖 Model: `{USE_MODEL}`\n"
            f"⏰ Schedule: `{schedule_str}`\n"
            f"📊 Posts today: {POSTS_TODAY}/17\n\n"
            "Choose an action from the menu:"
        )
        
        bot.send_message(message.chat.id, welcome, parse_mode="Markdown", reply_markup=main_menu())
        logger.info(f"Bot started by admin {message.from_user.id}")
    except Exception as e:
        logger.exception(f"Error in start_cmd: {e}")
        bot.send_message(message.chat.id, f"❌ Error: {str(e)}")

# -------------------------
# Menu Handler
# -------------------------
@bot.message_handler(func=lambda m: True)
@admin_only
def menu_handler(message):
    try:
        t = message.text.strip()
        clean = t.replace("📊", "").replace("👁️", "").replace("🚀", "").replace("🤖", "").replace("⏰", "").replace("🔄", "").replace("🏓", "").strip().lower()

        if clean == "status":
            res = status_report()
            send_result(message, f"📊 *Status Report*\n\n{res}")

        elif clean == "preview next":
            res = preview_next()
            send_result(message, f"👁️ *Preview*\n\n{res}")

        elif clean == "post now":
            working_msg = bot.send_message(message.chat.id, "🚀 Posting to X...\n⏳ Please wait...")
            logger.info("=" * 60)
            logger.info("MANUAL POST TRIGGERED")
            logger.info("=" * 60)
            
            try:
                res = post_one()
                
                try:
                    bot.delete_message(message.chat.id, working_msg.message_id)
                except:
                    pass
                
                if isinstance(res, str) and res.startswith("Error:"):
                    send_result(message, f"❌ *Posting Failed*\n\n{res}")
                elif isinstance(res, str) and res.startswith("⏳"):
                    send_result(message, res)
                else:
                    send_result(message, res)
                    
            except Exception as e:
                logger.exception(f"Exception in post_now: {e}")
                try:
                    bot.delete_message(message.chat.id, working_msg.message_id)
                except:
                    pass
                send_result(message, f"❌ *Error*\n\n{str(e)}")

        elif clean == "ping":
            send_result(message, "🏓 Pong! Bot is running.")

        elif clean == "set model":
            ask_model(message)

        elif clean == "set schedule":
            ask_schedule(message)

        elif clean == "reset limit":
            ask_reset_limit(message)

        else:
            send_result(message, "❓ Unknown option. Use menu buttons.")
            
    except Exception as e:
        logger.exception(f"Error in menu_handler: {e}")
        try:
            bot.send_message(message.chat.id, f"❌ Error: {str(e)}", reply_markup=main_menu())
        except:
            pass

# -------------------------
# Reset Limit
# -------------------------
def ask_reset_limit(message):
    try:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add("✅ Yes, Reset", "❌ Cancel")
        
        bot.send_message(
            message.chat.id,
            f"⚠️ *Reset Rate Limit?*\n\n"
            f"Current: {POSTS_TODAY}/17 posts\n\n"
            f"Only reset if 24h passed or testing!",
            parse_mode="Markdown",
            reply_markup=kb
        )
        bot.register_next_step_handler(message, confirm_reset_limit)
    except Exception as e:
        logger.exception(f"Error in ask_reset_limit: {e}")
        bot.send_message(message.chat.id, f"❌ Error: {str(e)}", reply_markup=main_menu())

def confirm_reset_limit(message):
    try:
        if "yes" in message.text.lower():
            old = POSTS_TODAY
            reset_rate_limit()
            bot.send_message(
                message.chat.id,
                f"✅ *Reset Complete!*\n\n"
                f"Previous: {old}/17\n"
                f"Current: 0/17\n\n"
                f"You can post again!",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
            logger.info(f"Rate limit reset (was {old})")
        else:
            bot.send_message(message.chat.id, "❌ Cancelled.", reply_markup=main_menu())
    except Exception as e:
        logger.exception(f"Error in confirm_reset_limit: {e}")
        bot.send_message(message.chat.id, f"❌ Error: {str(e)}", reply_markup=main_menu())

# -------------------------
# Model Selection
# -------------------------
def ask_model(message):
    try:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add("OpenAI (GPT-4o-mini)", "Gemini (1.5 Flash)")
        kb.add("❌ Cancel")
        
        bot.send_message(
            message.chat.id,
            f"🤖 *Select Model*\n\nCurrent: `{USE_MODEL}`",
            parse_mode="Markdown",
            reply_markup=kb
        )
        bot.register_next_step_handler(message, set_model_choice)
    except Exception as e:
        logger.exception(f"Error in ask_model: {e}")
        bot.send_message(message.chat.id, f"❌ Error: {str(e)}", reply_markup=main_menu())

def set_model_choice(message):
    try:
        choice = message.text.strip()
        
        if "cancel" in choice.lower():
            bot.send_message(message.chat.id, "❌ Cancelled.", reply_markup=main_menu())
            return
        
        if "openai" in choice.lower() or "gpt" in choice.lower():
            set_model("openai")
            bot.send_message(
                message.chat.id,
                "✅ Model set to *OpenAI (GPT-4o-mini)*",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
        elif "gemini" in choice.lower():
            set_model("gemini")
            bot.send_message(
                message.chat.id,
                "✅ Model set to *Gemini (1.5 Flash)*",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
        else:
            bot.send_message(message.chat.id, "❌ Invalid choice.", reply_markup=main_menu())
    except Exception as e:
        logger.exception(f"Error in set_model_choice: {e}")
        bot.send_message(message.chat.id, f"❌ Error: {str(e)}", reply_markup=main_menu())

# -------------------------
# Schedule Selection (Multiple Times)
# -------------------------
def ask_schedule(message):
    try:
        current = get_schedule()
        current_str = ", ".join(current) if current else "Not set"
        
        bot.send_message(
            message.chat.id,
            f"⏰ *Set Schedule*\n\n"
            f"Current: `{current_str}`\n\n"
            f"Enter times in HH:MM format, separated by commas.\n\n"
            f"Examples:\n"
            f"`09:00` (once daily)\n"
            f"`09:00, 14:00, 18:00` (3 times daily)\n"
            f"`08:00, 12:00, 16:00, 20:00` (4 times daily)",
            parse_mode="Markdown",
            reply_markup=types.ForceReply()
        )
        bot.register_next_step_handler(message, set_schedule_choice)
    except Exception as e:
        logger.exception(f"Error in ask_schedule: {e}")
        bot.send_message(message.chat.id, f"❌ Error: {str(e)}", reply_markup=main_menu())

def set_schedule_choice(message):
    try:
        input_text = message.text.strip()
        
        # Parse times
        time_list = [t.strip() for t in input_text.split(",")]
        
        # Validate each time
        valid_times = []
        for t in time_list:
            if ":" not in t or len(t.split(":")) != 2:
                bot.send_message(
                    message.chat.id,
                    f"❌ Invalid format: `{t}`\nUse HH:MM (e.g., 09:30)",
                    parse_mode="Markdown",
                    reply_markup=main_menu()
                )
                return
            
            try:
                hours, mins = t.split(":")
                if not (0 <= int(hours) <= 23 and 0 <= int(mins) <= 59):
                    raise ValueError("Invalid time range")
                valid_times.append(t)
            except:
                bot.send_message(
                    message.chat.id,
                    f"❌ Invalid time: `{t}`",
                    parse_mode="Markdown",
                    reply_markup=main_menu()
                )
                return
        
        # Set schedule
        set_schedule(valid_times)
        
        times_str = ", ".join(valid_times)
        bot.send_message(
            message.chat.id,
            f"✅ *Schedule Updated!*\n\n"
            f"Times: `{times_str}`\n"
            f"Posts per day: {len(valid_times)}\n\n"
            f"Bot will post at these times daily.",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        logger.info(f"Schedule updated: {valid_times}")
        
    except Exception as e:
        logger.exception(f"Error in set_schedule_choice: {e}")
        bot.send_message(
            message.chat.id,
            f"❌ Error: {str(e)}",
            reply_markup=main_menu()
        )

# -------------------------
# Scheduler Thread
# -------------------------
def start_scheduler_thread():
    t = threading.Thread(target=schedule_runner, daemon=True)
    t.start()
    logger.info("Scheduler thread started")

# -------------------------
# Run Bot
# -------------------------
if __name__ == "__main__":
    try:
        logger.info("Starting bot...")
        logger.info(f"Admin ID: {ADMIN}")
        start_scheduler_thread()
        
        logger.info("Bot polling started")
        logger.info("Send /start to begin")
        
        while True:
            try:
                bot.infinity_polling(timeout=120, long_polling_timeout=120)
            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"Polling failed: {e}", exc_info=True)
                time.sleep(5)
    except Exception as e:
        logger.error(f"Failed to start: {e}", exc_info=True)
