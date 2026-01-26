# 🤖 AutoPoster Bot for X (Twitter)

A robust, fully automated Python bot designed to manage and post content to X (formerly Twitter) using a Google Sheet as a database. It features AI-powered text rewriting (OpenAI & Gemini), media handling, and a Telegram-based admin interface for control and monitoring.

Designed to run 24/7 on a cloud server (e.g., Oracle Cloud).

## 🌟 Features

*   **Google Sheets Integration**: specific content (Body, Tags, Media URL) is pulled directly from a Google Sheet.
*   **AI-Powered Rewriting**: Automatically rewrites post content using **OpenAI (GPT-4o)** or **Google Gemini (Flash 1.5)** to keep tweets fresh and unique.
*   **Smart Scheduling**: Set custom daily posting schedules via Telegram (e.g., `09:00, 14:00, 20:00`).
*   **Rate Limit Management**: Automatically tracks daily posts (Free Tier limit: 17 posts/day) and prevents 429 errors.
*   **Robust Posting Methods**: Uses a hybrid approach (v1.1 for media, v2 for text) with fallback logic to ensure high success rates.
*   **Telegram Admin Panel**:
    *   📊 **Status Reporting**: See posts made, remaining, and model status.
    *   🚀 **Post Now**: Trigger an immediate manual post.
    *   👁️ **Preview**: See exactly what the next post will look like (including AI rewrite).
    *   ⚙️ **Configuration**: Switch AI models, set schedules, or reset limits on the fly.

## 📂 Project Structure

*   `bot.py`: The main entry point. Handles the Telegram bot interface and runs the scheduler thread.
*   `main.py`: Contains the core logic for Google Sheets, AI processing, and X API interaction.
*   `requirements.txt`: List of Python dependencies.
*   `service_account.json`: **(Required)** Google Cloud service account credentials for Sheets access.

## 🛠️ Prerequisites

*   Python 3.8+
*   Oracle Cloud (or any VPS) heavily recommended for 24/7 uptime.
*   **X (Twitter) Developer Account** (API Key, Secret, Access Token, Access Secret).
*   **Google Cloud Service Account** (JSON key file) with access to the Google Sheet.
*   **Telegram Bot Token** (from @BotFather).
*   **OpenAI API Key** and/or **Google Gemini API Key**.

## 🚀 Installation & Setup

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/xposter.git
    cd xposter
    ```

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Setup Credentials**:
    *   Place your Google Cloud JSON key as `service_account.json` in the project root.
    *   **IMPORTANT**: Open `main.py` and update the `API KEYS & CONFIGURATION` section with your actual API keys.
        *   *Note: For better security, consider moving these to environment variables if sharing code.*

4.  **Google Sheet Setup**:
    *   Create a Google Sheet with headers: `Body Text`, `Tags`, `Media`, `Posted`, `Final text`.
    *   Share the sheet with the email address found inside your `service_account.json`.

## 🏃‍♂️ Running the Bot

Run the bot using Python:

```bash
python bot.py
```

### Running in Background (Oracle Cloud / Linux)
To keep the bot running 24/7 even after you disconnect:

1.  **Create a Systemd Service** (Recommended):
    Create a file `/etc/systemd/system/xposter.service`:
    ```ini
    [Unit]
    Description=X AutoPoster Bot
    After=network.target

    [Service]
    User=ubuntu
    WorkingDirectory=/home/ubuntu/xposter
    ExecStart=/usr/bin/python3 /home/ubuntu/xposter/bot.py
    Restart=always

    [Install]
    WantedBy=multi-user.target
    ```

2.  **Start the Service**:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable xposter
    sudo systemctl start xposter
    ```

## 📱 Telegram Commands

Send `/start` to your bot to open the main menu.

*   **📊 Status**: View current stats (posted count, rate limits).
*   **👁️ Preview Next**: See the next post from the sheet.
*   **🚀 Post Now**: Force a post immediately.
*   **🤖 Set Model**: Switch between OpenAI and Gemini.
*   **⏰ Set Schedule**: Configure daily posting times.

## ⚠️ Disclaimer
This bot is designed for educational and personal automation purposes. Please ensure you comply with X's automation rules and terms of service.
