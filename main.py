import time
import requests
import schedule
import gspread
import tweepy
import google.generativeai as genai
from openai import OpenAI
from datetime import datetime, timedelta
from functools import wraps
import traceback
import logging
from typing import Tuple, Optional, List, Dict

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

# ============================================================
# API KEYS & CONFIGURATION - UPDATE THESE!
# ============================================================

# X (Twitter) API Credentials
X_API_KEY = "..."
X_API_SECRET = "..."
X_ACCESS_TOKEN = "..."
X_ACCESS_SECRET = "..."

# OpenAI API Key
OPENAI_API_KEY = "..."

# Gemini API Key
GEMINI_API_KEY = "..."

# Google Sheets Configuration
SHEET_ID = "..."
SHEET_TAB = "..."

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = "..."
TELEGRAM_ADMIN_ID = ...

# Bot Settings
USE_MODEL = "openai"  # "openai" or "gemini"
SCHEDULE_TIMES = []  # Will be populated via bot, e.g., ["09:00", "14:00", "18:00"]
POSTS_TODAY = 0
LAST_POST_TIME = None

# Admin notification function (will be set by bot)
_admin_notifier = None

def set_admin_notifier(func):
    global _admin_notifier
    _admin_notifier = func

# ============================================================
# Google sheet header names
COL_BODY = "Body Text"
COL_TAGS = "Tags"
COL_MEDIA = "Media"
COL_POSTED = "Posted"
COL_FINAL = "Final text"

# ============================================================
# NOTIFICATION HELPERS
# ============================================================
def admin_notify(subject: str, details: str = ""):
    ts = datetime.utcnow().isoformat()
    msg = f"[{ts} UTC] {subject}\n{details}"
    if _admin_notifier:
        try:
            _admin_notifier(msg)
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")

def safe_exec(also_notify: bool = True):
    """Decorator to catch exceptions, log, optionally notify admin, and return a friendly error."""
    def deco(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                tb = traceback.format_exc()
                short = f"{func.__name__} error: {str(e)}"
                logger.exception(short)
                if also_notify:
                    admin_notify(short, tb)
                return f"Error: {str(e)}"
        return wrapper
    return deco

# ============================================================
# RATE LIMIT MANAGEMENT
# ============================================================
def check_rate_limit_reset():
    global POSTS_TODAY, LAST_POST_TIME
    
    if not LAST_POST_TIME:
        return True, "No previous posts recorded"
    
    last_post = datetime.fromisoformat(LAST_POST_TIME)
    now = datetime.utcnow()
    time_diff = now - last_post
    
    # Reset counter if more than 24 hours have passed
    if time_diff.total_seconds() > 86400:
        POSTS_TODAY = 0
        LAST_POST_TIME = now.isoformat()
        return True, "Rate limit reset (24h passed)"
    
    # Check if we've hit the daily limit
    FREE_TIER_DAILY_LIMIT = 17
    if POSTS_TODAY >= FREE_TIER_DAILY_LIMIT:
        reset_time = last_post + timedelta(hours=24)
        wait_seconds = (reset_time - now).total_seconds()
        wait_hours = wait_seconds / 3600
        return False, f"Rate limit reached ({POSTS_TODAY}/{FREE_TIER_DAILY_LIMIT} posts). Resets in {wait_hours:.1f} hours at {reset_time.strftime('%Y-%m-%d %H:%M UTC')}"
    
    return True, f"OK ({POSTS_TODAY}/{FREE_TIER_DAILY_LIMIT} posts used today)"

def increment_post_counter():
    global POSTS_TODAY, LAST_POST_TIME
    POSTS_TODAY += 1
    LAST_POST_TIME = datetime.utcnow().isoformat()
    logger.info(f"Post counter updated: {POSTS_TODAY} posts today")

def reset_rate_limit():
    global POSTS_TODAY, LAST_POST_TIME
    POSTS_TODAY = 0
    LAST_POST_TIME = None
    logger.info("Rate limit counter reset")

# ============================================================
# GOOGLE SHEET CONNECTION
# ============================================================
@safe_exec()
def sheet():
    client = gspread.service_account(filename="service_account.json")
    sh = client.open_by_key(SHEET_ID)
    return sh.worksheet(SHEET_TAB)

@safe_exec()
def load_rows() -> Tuple[object, List[Dict]]:
    ws = sheet()
    records = ws.get_all_records()
    
    if records:
        logger.info(f"First record keys: {list(records[0].keys())}")
        logger.info(f"First record sample: Body={records[0].get(COL_BODY, 'N/A')[:50] if records[0].get(COL_BODY) else 'EMPTY'}")
    
    return ws, records

# ============================================================
# REWRITE TEXT USING SELECTED MODEL
# ============================================================
@safe_exec()
def rewrite_text(original: str) -> Optional[str]:
    if USE_MODEL == "openai":
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Rewrite text. Keep meaning & hashtags."},
                {"role": "user", "content": original}
            ],
            temperature=0.2,
            max_tokens=700
        )
        return response.choices[0].message.content.strip()

    if USE_MODEL == "gemini":
        genai.configure(api_key=GEMINI_API_KEY)
        m = genai.GenerativeModel("gemini-1.5-flash")
        r = m.generate_content(f"Rewrite this text. Keep hashtags:\n\n{original}")
        return getattr(r, "text", "").strip()

    return None

# ============================================================
# DOWNLOAD MEDIA
# ============================================================
@safe_exec()
def download_media(url: str, index: int) -> str:
    import os
    os.makedirs("media", exist_ok=True)
    path = f"media/tmp_{index}.jpg"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)
    return path

# ============================================================
# POST TO X (Twitter) - WORKING METHODS
# ============================================================
@safe_exec(also_notify=False)
def post_to_x(text: str, media_path: Optional[str] = None) -> None:
    """Post to X using verified working methods"""
    
    logger.info("=" * 60)
    logger.info("POST_TO_X CALLED")
    logger.info(f"Text length: {len(text) if text else 0}")
    logger.info(f"Media path: {media_path}")
    logger.info("=" * 60)
    
    # Try Method 1 first (HYBRID - Verified Working)
    try:
        logger.info("🔄 Attempting Method 1: Hybrid (v1.1 media + v2 post)")
        _post_method1_hybrid(text, media_path)
        logger.info("✅ Method 1 SUCCESS")
        return
    except Exception as e1:
        logger.warning(f"⚠️ Method 1 failed: {str(e1)}")
        logger.info("🔄 Falling back to Method 2...")
        
        # Try Method 2 as fallback
        try:
            _post_method2_v2_only(text, media_path)
            logger.info("✅ Method 2 SUCCESS")
            return
        except Exception as e2:
            logger.error(f"❌ Method 2 also failed: {str(e2)}")
            raise Exception(
                f"All posting methods failed!\n\n"
                f"Method 1: {str(e1)}\n"
                f"Method 2: {str(e2)}"
            )

def _post_method1_hybrid(text: str, media_path: Optional[str] = None) -> None:
    """Method 1: Upload media via v1.1, post tweet via v2 (VERIFIED WORKING)"""
    
    logger.info("▶️  Method 1 starting...")
    
    # Create v1.1 API client for media upload
    auth_v1 = tweepy.OAuth1UserHandler(
        X_API_KEY,
        X_API_SECRET,
        X_ACCESS_TOKEN,
        X_ACCESS_SECRET
    )
    api_v1 = tweepy.API(auth_v1)
    logger.info("✅ v1.1 API created")
    
    # Create v2 Client for posting tweets
    client_v2 = tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_SECRET
    )
    logger.info("✅ v2 Client created")
    
    media_ids = None
    
    # Upload media via v1.1 if provided
    if media_path:
        logger.info(f"📤 Uploading media via v1.1 API: {media_path}")
        media = api_v1.media_upload(filename=media_path)
        media_ids = [media.media_id]
        logger.info(f"✅ Media uploaded: {media.media_id}")
    
    # Post tweet via v2 API
    logger.info(f"📤 Posting tweet via v2 API")
    
    if text and media_ids:
        response = client_v2.create_tweet(text=text, media_ids=media_ids)
    elif media_ids and not text:
        response = client_v2.create_tweet(text="", media_ids=media_ids)
    elif text and not media_ids:
        response = client_v2.create_tweet(text=text)
    else:
        raise Exception("No content to post")
    
    tweet_id = response.data['id']
    logger.info(f"✅✅✅ SUCCESS! Tweet ID: {tweet_id}")
    logger.info(f"🔗 URL: https://twitter.com/user/status/{tweet_id}")

def _post_method2_v2_only(text: str, media_path: Optional[str] = None) -> None:
    """Method 2: V2 only approach (VERIFIED WORKING)"""
    
    logger.info("▶️  Method 2 starting...")
    
    client = tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_SECRET
    )
    logger.info("✅ v2 Client created")
    
    media_ids = None
    
    if media_path:
        logger.info(f"📤 Uploading media via v1.1 API: {media_path}")
        auth_v1 = tweepy.OAuth1UserHandler(
            X_API_KEY,
            X_API_SECRET,
            X_ACCESS_TOKEN,
            X_ACCESS_SECRET
        )
        api_v1 = tweepy.API(auth_v1)
        media = api_v1.media_upload(filename=media_path)
        media_ids = [media.media_id]
        logger.info(f"✅ Media uploaded: {media.media_id}")
    
    logger.info("📤 Posting via v2...")
    if text and media_ids:
        response = client.create_tweet(text=text, media_ids=media_ids)
    elif media_ids and not text:
        response = client.create_tweet(text="", media_ids=media_ids)
    elif text:
        response = client.create_tweet(text=text)
    else:
        raise Exception("No content to post")
    
    tweet_id = response.data['id']
    logger.info(f"✅✅✅ SUCCESS! Tweet ID: {tweet_id}")

# ============================================================
# FIND NEXT ROW
# ============================================================
def get_next() -> Tuple[Optional[int], Optional[dict]]:
    try:
        ws, rows = load_rows()
        if isinstance(ws, str) and ws.startswith("Error:"):
            logger.error(f"load_rows failed: {ws}")
            return None, None
        
        logger.info(f"Total rows loaded: {len(rows)}")
        
        for i, r in enumerate(rows):
            posted_value = str(r.get(COL_POSTED, "")).strip().upper()
            if posted_value != "YES":
                logger.info(f"Found unposted row at index {i}")
                return i, r
        
        logger.info("No unposted rows found")
        return None, None
    except Exception as e:
        logger.exception(f"get_next error: {e}")
        admin_notify("get_next error", str(e))
        return None, None

# ============================================================
# POST ONE
# ============================================================
@safe_exec(also_notify=False)
def post_one() -> str:
    # Check rate limit first
    can_post, rate_msg = check_rate_limit_reset()
    if not can_post:
        logger.warning(f"Rate limit check failed: {rate_msg}")
        return f"⏳ {rate_msg}"
    
    logger.info(f"Rate limit check: {rate_msg}")
    
    # Get next row
    idx, row = get_next()
    if idx is None and row is None:
        return "No posts remaining."

    logger.info(f"Processing row {idx}")
    
    body = str(row.get(COL_BODY, '')).strip()
    tags = str(row.get(COL_TAGS, '')).strip()
    media_url = str(row.get(COL_MEDIA, '')).strip()
    
    has_text = bool(body or tags)
    has_media = bool(media_url)
    
    if not has_text and not has_media:
        return "Error: Post has no content"
    
    # Prepare text
    combined = f"{body}\n\n{tags}".strip()
    final_text = combined
    
    if combined:
        logger.info("Rewriting text...")
        rewritten = rewrite_text(combined)
        if rewritten and not (isinstance(rewritten, str) and rewritten.startswith("Error:")):
            final_text = rewritten
            logger.info("Text rewritten")
        else:
            logger.warning("Using original text")
    else:
        final_text = ""

    # Download media
    media_path = None
    if media_url:
        logger.info(f"Downloading media")
        media_path = download_media(media_url, idx if idx is not None else 0)
        if isinstance(media_path, str) and media_path.startswith("Error:"):
            media_path = None
            if not final_text:
                return f"Error: Media download failed"

    if not final_text and not media_path:
        return "Error: Nothing to post"

    # Post to X
    logger.info("Posting to X...")
    post_result = post_to_x(final_text, media_path)
    
    if isinstance(post_result, str) and post_result.startswith("Error:"):
        if "429" in post_result or "Too Many Requests" in post_result:
            increment_post_counter()
            return f"⏳ Rate limit reached! Wait and try again.\n\n{post_result}"
        return f"❌ {post_result}"
    
    logger.info("✅ Posted successfully!")
    increment_post_counter()

    # Mark sheet as posted
    try:
        ws, rows = load_rows()
        if not (isinstance(ws, str) and ws.startswith("Error:")):
            ws.update_cell(idx + 2, 5, "YES")
            ws.update_cell(idx + 2, 6, final_text if final_text else "[Media Only]")
            logger.info(f"✅ Marked row {idx + 2} as posted")
    except Exception as e:
        logger.exception("Failed to update sheet: %s", e)

    preview = final_text[:200] if final_text else "[Media Only Post]"
    media_info = f"\n📷 Media: {'✅ Included' if media_path else '❌ Not included'}"
    
    return f"✅ Posted successfully!\n\n📊 Posts today: {POSTS_TODAY}/17\n\nPreview:\n{preview}...{media_info}"

# ============================================================
# STATUS
# ============================================================
@safe_exec()
def status_report() -> str:
    result = load_rows()
    if isinstance(result, str) and result.startswith("Error:"):
        return result
    
    _, rows = result
    posted = len([r for r in rows if str(r.get(COL_POSTED, "")).upper() == "YES"])
    remaining = len([r for r in rows if str(r.get(COL_POSTED, "")).upper() != "YES"])
    
    can_post, rate_msg = check_rate_limit_reset()
    
    if LAST_POST_TIME:
        last_post_dt = datetime.fromisoformat(LAST_POST_TIME)
        last_post_str = last_post_dt.strftime("%Y-%m-%d %H:%M UTC")
    else:
        last_post_str = "Never"
    
    rate_status = "✅ Ready" if can_post else "⏳ Rate Limited"
    schedule_str = ", ".join(SCHEDULE_TIMES) if SCHEDULE_TIMES else "Not set"
    
    return (f"Posted: {posted}\n"
            f"Remaining: {remaining}\n"
            f"Model: {USE_MODEL}\n"
            f"Schedule: {schedule_str}\n\n"
            f"📊 *Rate Limit Status:*\n"
            f"Status: {rate_status}\n"
            f"Posts today: {POSTS_TODAY}/17\n"
            f"Last post: {last_post_str}\n"
            f"{rate_msg}")

# ============================================================
# PREVIEW NEXT
# ============================================================
@safe_exec()
def preview_next() -> str:
    idx, r = get_next()
    if idx is None and r is None:
        return "No posts remaining."
    
    body = str(r.get(COL_BODY, '')).strip()
    tags = str(r.get(COL_TAGS, '')).strip()
    media = str(r.get(COL_MEDIA, '')).strip()
    
    combined = f"{body}\n\n{tags}".strip()
    
    rewrite_preview = ""
    if combined:
        rewritten = rewrite_text(combined)
        if rewritten and not (isinstance(rewritten, str) and rewritten.startswith("Error:")):
            rewrite_preview = f"\n\n*AI Rewrite ({USE_MODEL}):*\n{rewritten}"
    
    body_display = body[:200] + "..." if len(body) > 200 else body
    tags_display = tags[:100] + "..." if len(tags) > 100 else tags
    
    return (
        f"*Next Post Preview*\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"*Body:*\n{body_display}\n\n"
        f"*Tags:*\n{tags_display}\n\n"
        f"*Media:*\n{media}\n"
        f"{rewrite_preview}"
    )

# ============================================================
# SCHEDULER
# ============================================================
def schedule_runner():
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logger.exception("schedule.run_pending error: %s", e)
            admin_notify("Scheduler error", str(e))
        time.sleep(20)

def set_schedule(time_list: List[str]):
    global SCHEDULE_TIMES
    schedule.clear()
    SCHEDULE_TIMES = time_list
    for time_str in time_list:
        schedule.every().day.at(time_str).do(post_one)
        logger.info(f"Scheduled post at {time_str}")

def get_schedule() -> List[str]:
    return SCHEDULE_TIMES

def set_model(model_name: str):
    global USE_MODEL
    USE_MODEL = model_name
    logger.info(f"Model set to: {model_name}")