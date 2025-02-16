# Leave Request Telegram Bot

A Telegram bot for managing leave requests with a two-step approval process.

## Features

- Submit leave requests with date ranges and hours
- Two-step approval process (Supervisor → Duty Ops)
- Google Sheets integration for leave balance tracking
- Automatic notifications for all parties involved

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/leave-request-bot.git
cd leave-request-bot
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up configuration:
   - Copy `config.example.py` to `config.py`
   - Fill in your configuration values
   - Place your Google Sheets credentials JSON file in the project directory

5. Set up Google Sheets:
   - Create a spreadsheet for leave balances
   - Share it with the service account email from your credentials
   - Add the spreadsheet ID to config.py

## Usage

Run the bot:
```bash
python leave_bot.py
```

## Command Reference

- `/start` - Initialize the bot
- `/request` - Start a new leave request
- `/cancel` - Cancel the current request process

