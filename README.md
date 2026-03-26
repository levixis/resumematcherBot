# 🤖 Resume-JD Matcher — Telegram Bot

A Telegram bot that **matches resumes against job descriptions** using AI, gives a **detailed score breakdown**, **actionable suggestions**, and generates **optimized CVs in 4 template styles**.

---

## ✨ Features

| Feature | Description |
|---|---|
| 📄 **Resume Upload** | Accepts PDF, DOCX, TXT files or pasted text |
| 📋 **JD Input** | File upload or paste as plain text |
| 📊 **AI Scoring** | 0–100 scores for skills, experience, education, keywords |
| ✅ **Matched Skills** | Shows which skills already match the JD |
| ❌ **Missing Skills** | Highlights what's missing from your resume |
| 💡 **Suggestions** | 5 actionable improvements to boost your score |
| 🎨 **4 CV Templates** | Classic, Modern Two-Column, Minimal, ATS-Friendly |
| 📁 **2 Export Formats** | PDF and DOCX |
| 🔄 **Interactive Flow** | Buttons to switch templates, re-analyze, try again |

---

## 🎨 CV Template Styles

| Template | Description |
|---|---|
| 📜 **Classic** | Traditional single-column formal layout |
| 🎨 **Modern** | Two-column layout with dark sidebar for skills/education |
| ✨ **Minimal** | Clean, whitespace-heavy, elegant design |
| 🤖 **ATS-Friendly** | Plain text optimized to pass Applicant Tracking Systems |

---

## 🛠️ Setup Procedure

### Prerequisites
- Python 3.10+
- A Telegram account

### Step 1: Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Follow the prompts to name your bot
4. **Copy the bot token** (looks like `123456:ABCdef...`)

### Step 2: Get a Gemini API Key (Free)

1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Sign in with your Google account
3. Click **"Get API Key"** → **"Create API Key"**
4. **Copy the API key**

### Step 3: Configure the Bot

Edit the `.env` file and paste your keys:

```bash
TELEGRAM_BOT_TOKEN=paste_your_telegram_token_here
GEMINI_API_KEY=paste_your_gemini_key_here
```

### Step 4: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 5: Run the Bot

```bash
python3 bot.py
```

You should see:
```
🤖 Resume-JD Matcher Bot
=======================================================
  Templates: Classic | Modern | Minimal | ATS-Friendly
  Formats:   PDF | DOCX
=======================================================
  ✅ Bot is running! Press Ctrl+C to stop.
```

### Step 6: Use the Bot on Telegram

1. Open Telegram
2. Find your bot by the name you gave it
3. Send `/start` → see welcome message
4. Send `/match` → start the flow

---

## 🔄 Bot Conversation Flow

```
/match
  │
  ▼
Upload Resume (PDF/DOCX/TXT/text)
  │
  ▼
Send Job Description (file or text)
  │
  ▼
🔍 AI Analysis
  │
  ├── 📊 Score Breakdown (0-100)
  ├── ✅ Matched Skills
  ├── ❌ Missing Skills
  ├── 💡 5 Suggestions
  │
  ▼
[Generate Optimized CV] button
  │
  ▼
Choose Template:
  ├── 📜 Classic
  ├── 🎨 Modern Two-Column
  ├── ✨ Minimal
  └── 🤖 ATS-Friendly
  │
  ▼
Choose Format:
  ├── 📕 PDF
  ├── 📘 DOCX
  └── 📗 Both
  │
  ▼
📥 Download your optimized CV!
  │
  ├── [Try Another Template]
  └── [New Analysis]
```

---

## 📁 Project Structure

```
hackathon/
├── bot.py              # Main Telegram bot (conversation handlers)
├── resume_parser.py    # Extracts text from PDF/DOCX/TXT
├── matcher.py          # Gemini AI matching & scoring
├── cv_generator.py     # CV generation (4 templates × 2 formats)
├── requirements.txt    # Python dependencies
├── .env                # API keys (not committed)
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

---

## 🧠 Tech Stack

| Component | Technology |
|---|---|
| Bot Framework | python-telegram-bot v21 |
| AI Engine | Google Gemini 1.5 Flash (free tier) |
| PDF Generation | ReportLab |
| DOCX Generation | python-docx |
| Resume Parsing | PyPDF2 + python-docx |

---

## 📝 Commands

| Command | Action |
|---|---|
| `/start` | Welcome message with features |
| `/match` | Start resume-JD matching flow |
| `/help` | Show help and template info |
| `/cancel` | Cancel current operation |
