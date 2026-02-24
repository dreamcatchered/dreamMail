# dreamMail

Email management Telegram bot with Flask web interface.

Monitors your IMAP mailbox and forwards new emails to Telegram. Manage email aliases and read messages without opening a mail client.

## Features

- IMAP email monitoring
- New email notifications in Telegram
- Email alias management
- HTML email rendering
- Flask web interface

## Stack

![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?style=flat&logo=flask&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=flat&logo=javascript&logoColor=black)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat&logo=sqlite&logoColor=white)

## Setup

```bash
pip install -r requirements.txt
```

Set environment variables:
```env
TELEGRAM_TOKEN=your_bot_token
EMAIL_USER=your_email@yandex.ru
EMAIL_PASS=your_imap_app_password
ADMIN_ID=your_telegram_id
```

```bash
python bot1.py
# Web interface:
python app.py
```

## Contact

Telegram: [@dreamcatch_r](https://t.me/dreamcatch_r)
