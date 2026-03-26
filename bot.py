"""
🤖 Resume-JD Matcher Telegram Bot
Matches resumes against job descriptions, provides scores, suggestions,
and generates optimized CVs in multiple template styles and export formats.

Features:
- Interactive chat: users can give suggestions & refine the CV
- Name input: auto-extracts or asks for user's name
- Template selection: Classic, Modern, Minimal, ATS-Friendly
- Export formats: PDF, DOCX, Both
- Mock Interview: AI-generated interview questions from resume+JD
- Interview Tips: Personalized preparation advice
- Career Tips: Actionable career growth suggestions
- Resume Strength: Detailed strengths & weaknesses analysis
"""

import os
import json
import logging
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

from resume_parser import parse_resume
from matcher import analyze_match
from cv_generator import generate_pdf, generate_docx

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_files")
os.makedirs(TEMP_DIR, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Conversation States
# ─────────────────────────────────────────────────────────────
(WAITING_RESUME, WAITING_JD, SHOWING_RESULTS,
 WAITING_NAME, WAITING_FEEDBACK) = range(5)


# ─────────────────────────────────────────────────────────────
# Gemini helper for interactive chat
# ─────────────────────────────────────────────────────────────
def _chat_with_gemini(user_message: str, context_data: dict) -> dict:
    """Use Gemini to process user feedback and update the optimized resume."""
    import google.generativeai as genai

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")

    current_resume = context_data.get("optimized_resume", {})
    original_resume = context_data.get("resume_text", "")
    jd_text = context_data.get("jd_text", "")

    prompt = f"""You are a helpful resume assistant chatting with a user.

The user has already matched their resume against a job description and received an optimized resume.

CURRENT OPTIMIZED RESUME DATA:
{json.dumps(current_resume, indent=2)}

ORIGINAL RESUME TEXT:
{original_resume[:2000]}

JOB DESCRIPTION:
{jd_text[:2000]}

USER'S MESSAGE:
"{user_message}"

You can do THREE things based on what the user says:

1. **Answer questions about the CV** — If they ask things like "What skills do I have?", "How many years of experience?", "What's my summary?", answer by looking at the resume data above. Be specific and quote from their actual CV.

2. **Make changes to the CV** — If they ask you to add/remove/change something (e.g. "Add Docker to skills", "Change my title to Senior Dev"), apply the change to the optimized resume data.

3. **Give career advice** — If they ask general career questions related to the JD or resume, give helpful advice.

Return ONLY valid JSON (no markdown, no code blocks):
{{
    "reply": "Your friendly, detailed response to the user",
    "updated_resume": {{ ... the full updated optimized resume dict, or null if no changes were needed ... }},
    "changes_made": true/false
}}

The optimized resume structure must have these keys if updated:
professional_summary, skills, experience, education, certifications, projects

Keep the same structure. Apply the user's feedback precisely."""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        return json.loads(text)
    except Exception as e:
        logger.error(f"Chat Gemini error: {e}")
        return {
            "reply": "I understood your feedback! However, I had trouble processing it. Could you try rephrasing?",
            "updated_resume": None,
            "changes_made": False
        }


def _gemini_generate(prompt: str) -> str:
    """Generic Gemini call that returns text."""
    import google.generativeai as genai

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
    try:
        response = model.generate_content(
            prompt + "\n\nIMPORTANT: Keep your total response under 3500 characters.")
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return f"❌ AI error: {e}"


async def _send_long_message(message, text: str, reply_markup=None, parse_mode="Markdown"):
    """Send a message, splitting into chunks if it exceeds Telegram's 4096 char limit."""
    MAX_LEN = 4000
    if len(text) <= MAX_LEN:
        await message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        return

    # Split into chunks at newlines
    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_LEN:
            chunks.append(current)
            current = line
        else:
            current += ("\n" + line if current else line)
    if current:
        chunks.append(current)

    # Send all chunks, last one gets the reply_markup
    for i, chunk in enumerate(chunks):
        is_last = (i == len(chunks) - 1)
        try:
            await message.reply_text(
                chunk,
                parse_mode=parse_mode,
                reply_markup=reply_markup if is_last else None
            )
        except Exception:
            # Fallback: send without markdown if formatting fails
            await message.reply_text(
                chunk,
                reply_markup=reply_markup if is_last else None
            )


# ─────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────
def _score_bar(score: int) -> str:
    filled = round(score / 10)
    empty = 10 - filled
    bar = "█" * filled + "░" * empty
    if score >= 80:
        emoji = "🟢"
    elif score >= 60:
        emoji = "🟡"
    elif score >= 40:
        emoji = "🟠"
    else:
        emoji = "🔴"
    return f"{emoji} {bar} {score}/100"


def _format_results(result: dict) -> str:
    overall = result.get("overall_score", 0)
    if overall >= 80:
        header = "🎉 *EXCELLENT MATCH!*"
    elif overall >= 60:
        header = "👍 *GOOD MATCH*"
    elif overall >= 40:
        header = "⚡ *MODERATE MATCH*"
    else:
        header = "🔧 *NEEDS IMPROVEMENT*"

    msg = ""

    # Show input detection warning if inputs were swapped or incorrect
    input_det = result.get("input_detection", "ok")
    if input_det and not input_det.startswith("ok"):
        msg += "⚠️ *INPUT DETECTION WARNING*\n"
        msg += f"_{input_det}_\n\n"

    msg += f"""
{header}

━━━━━━━━━━━━━━━━━━━━━━━
📊 *MATCH SCORECARD*
━━━━━━━━━━━━━━━━━━━━━━━

*Overall Score:*   {_score_bar(overall)}
*Skills:*              {_score_bar(result.get('skills_score', 0))}
*Experience:*      {_score_bar(result.get('experience_score', 0))}
*Education:*       {_score_bar(result.get('education_score', 0))}
*Keywords:*         {_score_bar(result.get('keywords_score', 0))}

"""

    matched = result.get("matched_skills", [])
    if matched:
        msg += "━━━━━━━━━━━━━━━━━━━━━━━\n✅ *MATCHED SKILLS*\n━━━━━━━━━━━━━━━━━━━━━━━\n"
        for skill in matched[:10]:
            msg += f"  • {skill}\n"
        msg += "\n"

    missing = result.get("missing_skills", [])
    if missing:
        msg += "━━━━━━━━━━━━━━━━━━━━━━━\n❌ *MISSING SKILLS*\n━━━━━━━━━━━━━━━━━━━━━━━\n"
        for skill in missing[:10]:
            msg += f"  • {skill}\n"
        msg += "\n"

    summary = result.get("summary", "")
    if summary:
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━\n📝 *ASSESSMENT*\n━━━━━━━━━━━━━━━━━━━━━━━\n{summary}\n\n"

    suggestions = result.get("suggestions", [])
    if suggestions:
        msg += "━━━━━━━━━━━━━━━━━━━━━━━\n💡 *SUGGESTIONS TO IMPROVE*\n━━━━━━━━━━━━━━━━━━━━━━━\n"
        for i, sug in enumerate(suggestions, 1):
            msg += f"\n*{i}.* {sug}\n"

    improvements = result.get("improvements_made", [])
    if improvements:
        msg += "\n━━━━━━━━━━━━━━━━━━━━━━━\n🔧 *WHAT WE IMPROVED IN YOUR CV*\n━━━━━━━━━━━━━━━━━━━━━━━\n"
        for i, imp in enumerate(improvements, 1):
            msg += f"\n✏️ *{i}.* {imp}\n"

    return msg


def _results_keyboard(has_optimized: bool = True) -> InlineKeyboardMarkup:
    """Build the results action keyboard."""
    keyboard = []
    if has_optimized:
        keyboard.append([
            InlineKeyboardButton("📄 Generate Optimized CV", callback_data="ask_name")
        ])
    keyboard.append([
        InlineKeyboardButton("🎯 Mock Interview", callback_data="mock_interview"),
        InlineKeyboardButton("💼 Interview Tips", callback_data="interview_tips"),
    ])
    keyboard.append([
        InlineKeyboardButton("💪 Resume Strength", callback_data="resume_strength"),
        InlineKeyboardButton("🚀 Career Tips", callback_data="career_tips"),
    ])
    keyboard.append([
        InlineKeyboardButton("🔄 New Analysis", callback_data="new_analysis"),
        InlineKeyboardButton("ℹ️ Help", callback_data="show_help")
    ])
    return InlineKeyboardMarkup(keyboard)


# ─────────────────────────────────────────────────────────────
# Bot Handlers
# ─────────────────────────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Match Resume & JD", callback_data="start_match")],
        [InlineKeyboardButton("📚 How to Use", callback_data="show_help")],
    ]
    welcome_msg = """
🤖 *Resume-JD Matcher Bot*

Welcome! I'm your AI-powered career assistant.

━━━━━━━━━━━━━━━━━━━━━━━
📋 *What I can do:*
━━━━━━━━━━━━━━━━━━━━━━━

📊  Match resume against JD (score + analysis)
💬  Interactive chat to refine your CV
📄  Generate optimized CV in 4 templates
🎯  Mock interview questions from your resume
💼  Personalized interview preparation tips
💪  Resume strength & weakness analysis
🚀  Career growth suggestions

━━━━━━━━━━━━━━━━━━━━━━━
🎨 *CV Templates:*
   📜 Classic | 🎨 Modern | ✨ Minimal | 🤖 ATS-Friendly

🚀 *Get started:*  Send /match
📚 *Menu:*         Send /menu
"""
    await update.message.reply_text(
        welcome_msg, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_msg = """
📚 *Commands & Features*

/start  — Welcome message
/match  — Start resume-JD matching
/menu   — Open feature menu
/mock   — Mock interview questions
/tips   — Career & interview tips
/help   — Show this help
/cancel — Cancel current operation

━━━━━━━━━━━━━━━━━━━━━━━
📖 *How to use:*
━━━━━━━━━━━━━━━━━━━━━━━

1. Send /match
2. Upload resume (PDF, DOCX, TXT) or paste
3. Send the Job Description
4. Get score, suggestions & improvements!
5. 💬 *Chat with me* to refine:
   • _"Add Docker to my skills"_
   • _"What experience do I have?"_
   • _"Make summary more technical"_
6. Use the *menu buttons* for more features:
   • 🎯 Mock Interview Questions
   • 💼 Interview Preparation Tips
   • 💪 Resume Strength Analysis
   • 🚀 Career Growth Tips
7. Generate CV → pick template → download!
8. Type *done* when finished.
"""
    await update.message.reply_text(help_msg, parse_mode="Markdown")


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the main feature menu."""
    has_data = bool(context.user_data.get("analysis_result"))

    keyboard = [
        [InlineKeyboardButton("📊 Match Resume & JD", callback_data="start_match")],
    ]
    if has_data:
        keyboard.extend([
            [InlineKeyboardButton("📄 Generate Optimized CV", callback_data="ask_name")],
            [
                InlineKeyboardButton("🎯 Mock Interview", callback_data="mock_interview"),
                InlineKeyboardButton("💼 Interview Tips", callback_data="interview_tips"),
            ],
            [
                InlineKeyboardButton("💪 Resume Strength", callback_data="resume_strength"),
                InlineKeyboardButton("🚀 Career Tips", callback_data="career_tips"),
            ],
        ])
    keyboard.append([
        InlineKeyboardButton("ℹ️ Help", callback_data="show_help")
    ])

    status = "✅ Resume & JD loaded" if has_data else "⚡ No resume loaded yet — start with Match!"

    await update.message.reply_text(
        f"📋 *Main Menu*\n\n_{status}_\n",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def mock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct command for mock interview."""
    if not context.user_data.get("analysis_result"):
        await update.message.reply_text(
            "❌ Please run /match first to analyze your resume, then I can generate mock interview questions!")
        return
    await _generate_mock_interview(update.message, context)


async def tips_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct command for tips."""
    if not context.user_data.get("analysis_result"):
        await update.message.reply_text(
            "❌ Please run /match first to analyze your resume, then I can give personalized tips!")
        return
    await _generate_interview_tips(update.message, context)


async def match_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    msg = """
📄 *Step 1/2: Upload Your Resume*

Please send me your resume as a file.

📁 *Supported formats:* PDF, DOCX, TXT

Or just paste your resume text directly!
"""
    await update.message.reply_text(msg, parse_mode="Markdown")
    return WAITING_RESUME


async def receive_resume_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document:
        await update.message.reply_text("❌ Please send a file or paste your resume as text.")
        return WAITING_RESUME

    if document.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ File too large! Max size: 20MB.")
        return WAITING_RESUME

    file_name = document.file_name or "resume"
    file_path = os.path.join(TEMP_DIR, f"{update.effective_user.id}_{file_name}")

    await update.message.reply_text("⏳ Downloading your resume...")

    try:
        tg_file = await document.get_file()
        await tg_file.download_to_drive(file_path)
        resume_text = parse_resume(file_path)
        context.user_data["resume_text"] = resume_text
        context.user_data["resume_file_path"] = file_path

        msg = f"""
✅ *Resume received!* ({len(resume_text.split())} words extracted)

━━━━━━━━━━━━━━━━━━━━━━━
📋 *Step 2/2: Send the Job Description*
━━━━━━━━━━━━━━━━━━━━━━━

Now send me the Job Description:
• Paste the JD as text, OR
• Upload a file (PDF, DOCX, TXT)
"""
        await update.message.reply_text(msg, parse_mode="Markdown")
        return WAITING_JD

    except ValueError as e:
        await update.message.reply_text(f"❌ {e}")
        return WAITING_RESUME
    except Exception as e:
        logger.error(f"Error processing resume: {e}")
        await update.message.reply_text("❌ Error processing file. Please try again.")
        return WAITING_RESUME


async def receive_resume_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if len(text) < 50:
        await update.message.reply_text("❌ That seems too short. Please paste your full resume or upload a file.")
        return WAITING_RESUME

    context.user_data["resume_text"] = text

    msg = f"""
✅ *Resume received!* ({len(text.split())} words)

━━━━━━━━━━━━━━━━━━━━━━━
📋 *Step 2/2: Send the Job Description*
━━━━━━━━━━━━━━━━━━━━━━━

Now send me the Job Description:
• Paste the JD as text, OR
• Upload a file (PDF, DOCX, TXT)
"""
    await update.message.reply_text(msg, parse_mode="Markdown")
    return WAITING_JD


async def receive_jd_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    file_name = document.file_name or "jd"
    file_path = os.path.join(TEMP_DIR, f"{update.effective_user.id}_jd_{file_name}")

    await update.message.reply_text("⏳ Processing job description...")
    try:
        tg_file = await document.get_file()
        await tg_file.download_to_drive(file_path)
        jd_text = parse_resume(file_path)
        context.user_data["jd_text"] = jd_text
        try:
            os.remove(file_path)
        except Exception:
            pass
        return await _do_analysis(update, context)
    except Exception as e:
        logger.error(f"Error processing JD file: {e}")
        await update.message.reply_text("❌ Error processing file. Please paste the JD as text instead.")
        return WAITING_JD


async def receive_jd_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if len(text) < 20:
        await update.message.reply_text("❌ That seems too short. Please paste the full JD.")
        return WAITING_JD
    context.user_data["jd_text"] = text
    return await _do_analysis(update, context)


async def _do_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resume_text = context.user_data.get("resume_text", "")
    jd_text = context.user_data.get("jd_text", "")

    await update.message.reply_text(
        "🔍 *Analyzing your resume against the JD...*\n\n⏳ This may take 10-20 seconds...",
        parse_mode="Markdown"
    )

    try:
        result = analyze_match(resume_text, jd_text)
        context.user_data["analysis_result"] = result
        if result.get("optimized_resume"):
            context.user_data["optimized_resume"] = result["optimized_resume"]

        # Auto-extract candidate name from Gemini analysis
        extracted_name = result.get("candidate_name")
        if extracted_name and extracted_name.lower() not in ("null", "none", "candidate", "n/a", ""):
            context.user_data["candidate_name"] = extracted_name
            logger.info(f"Auto-extracted name: {extracted_name}")

        results_msg = _format_results(result)
        has_opt = result.get("optimized_resume") is not None

        # Add interactive chat hint
        chat_hint = "\n\n💬 *You can now chat with me!*\nType suggestions to refine your CV, e.g.:\n• _\"Add Python to my skills\"_\n• _\"Make the summary more technical\"_\n• _\"Change my job title to Lead Developer\"_\n\nOr tap the buttons below:"

        await update.message.reply_text(
            results_msg + chat_hint,
            parse_mode="Markdown",
            reply_markup=_results_keyboard(has_opt)
        )
        return SHOWING_RESULTS

    except RuntimeError as e:
        await update.message.reply_text(f"❌ Analysis failed: {e}")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        await update.message.reply_text("❌ Something went wrong. Please try /match again.")
        return ConversationHandler.END


# ─────────────────────────────────────────────────────────────
# Interactive Chat Handler (user types feedback in results state)
# ─────────────────────────────────────────────────────────────
async def handle_user_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle free-text chat from user after analysis — for refining the CV."""
    user_msg = update.message.text.strip()

    # Check if user says "done"
    if user_msg.lower() in ("done", "exit", "quit", "finish", "bye", "stop", "no", "nope"):
        context.user_data.clear()
        await update.message.reply_text(
            "🎉 *Great, you're all set!*\n\n"
            "Thanks for using Resume-JD Matcher Bot! 🤖\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔄 Want to match another resume?\n"
            "Send /match to start a new analysis!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    if not context.user_data.get("analysis_result"):
        await update.message.reply_text("Please run /match first to analyze your resume!")
        return SHOWING_RESULTS

    await update.message.reply_text(
        "🤔 *Processing your feedback...*",
        parse_mode="Markdown"
    )

    # Build context for Gemini
    chat_context = {
        "optimized_resume": context.user_data.get("optimized_resume", {}),
        "resume_text": context.user_data.get("resume_text", ""),
        "jd_text": context.user_data.get("jd_text", ""),
    }

    result = _chat_with_gemini(user_msg, chat_context)

    reply = result.get("reply", "Got it!")
    changes_made = result.get("changes_made", False)
    updated_resume = result.get("updated_resume")

    if changes_made and updated_resume:
        context.user_data["optimized_resume"] = updated_resume
        context.user_data["analysis_result"]["optimized_resume"] = updated_resume

        msg = f"💬 {reply}\n\n✅ *CV updated!* Your changes have been applied.\n\n"
        msg += "• Type more suggestions to keep refining\n"
        msg += "• Tap *Generate Optimized CV* to download\n"
        msg += "• Type *done* when you're finished"
    else:
        msg = f"💬 {reply}\n\n"
        msg += "_Keep typing suggestions, or say *done* to finish:_"

    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=_results_keyboard(True)
    )
    return SHOWING_RESULTS


# ─────────────────────────────────────────────────────────────
# Name Input Handler
# ─────────────────────────────────────────────────────────────
async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive the user's name for the CV."""
    name = update.message.text.strip()

    if len(name) < 2 or len(name) > 60:
        await update.message.reply_text("❌ Please enter a valid name (2-60 characters).")
        return WAITING_NAME

    context.user_data["candidate_name"] = name

    # Show template selection
    keyboard = [
        [InlineKeyboardButton("📜 Classic — Traditional", callback_data="tpl_classic")],
        [InlineKeyboardButton("🎨 Modern — Two-Column Sidebar", callback_data="tpl_modern")],
        [InlineKeyboardButton("✨ Minimal — Clean & Elegant", callback_data="tpl_minimal")],
        [InlineKeyboardButton("🤖 ATS-Friendly — Scanner Optimized", callback_data="tpl_ats")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"✅ Name set to: *{name}*\n\n"
        "🎨 *Now choose a CV template style:*",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    return SHOWING_RESULTS


# ─────────────────────────────────────────────────────────────
# Callback Handler (buttons)
# ─────────────────────────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # ── Generate CV: check if name exists, otherwise ask ──
    if data == "ask_name":
        await query.edit_message_reply_markup(reply_markup=None)

        # If name was already extracted from resume, skip to template selection
        existing_name = context.user_data.get("candidate_name")
        if existing_name:
            keyboard = [
                [InlineKeyboardButton("📜 Classic — Traditional", callback_data="tpl_classic")],
                [InlineKeyboardButton("🎨 Modern — Two-Column Sidebar", callback_data="tpl_modern")],
                [InlineKeyboardButton("✨ Minimal — Clean & Elegant", callback_data="tpl_minimal")],
                [InlineKeyboardButton("🤖 ATS-Friendly — Scanner Optimized", callback_data="tpl_ats")],
            ]
            await query.message.reply_text(
                f"👤 Name detected: *{existing_name}*\n\n"
                "🎨 *Choose a CV template style:*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return SHOWING_RESULTS
        else:
            # No name found — ask the user
            await query.message.reply_text(
                "👤 *I couldn't find your name in the resume.*\n\n"
                "Please type your full name:",
                parse_mode="Markdown"
            )
            return WAITING_NAME

    # ── Template selection ──
    elif data == "choose_template":
        keyboard = [
            [InlineKeyboardButton("📜 Classic — Traditional", callback_data="tpl_classic")],
            [InlineKeyboardButton("🎨 Modern — Two-Column Sidebar", callback_data="tpl_modern")],
            [InlineKeyboardButton("✨ Minimal — Clean & Elegant", callback_data="tpl_minimal")],
            [InlineKeyboardButton("🤖 ATS-Friendly — Scanner Optimized", callback_data="tpl_ats")],
        ]
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "🎨 *Choose a CV Template Style:*\n\n"
            "Each template has a unique layout & design.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SHOWING_RESULTS

    # ── Template selected → choose export format ──
    elif data.startswith("tpl_"):
        template_id = data.replace("tpl_", "")
        context.user_data["selected_template"] = template_id

        template_names = {
            "classic": "📜 Classic",
            "modern": "🎨 Modern Two-Column",
            "minimal": "✨ Minimal",
            "ats": "🤖 ATS-Friendly",
        }
        tpl_name = template_names.get(template_id, template_id)

        keyboard = [
            [
                InlineKeyboardButton("📕 PDF", callback_data="export_pdf"),
                InlineKeyboardButton("📘 DOCX", callback_data="export_docx"),
            ],
            [InlineKeyboardButton("📗 Both PDF + DOCX", callback_data="export_both")],
            [InlineKeyboardButton("◀️ Change Template", callback_data="choose_template")],
        ]

        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            f"✅ Template: *{tpl_name}*\n\n📁 *Choose export format:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SHOWING_RESULTS

    # ── Export format selected → generate CV ──
    elif data.startswith("export_"):
        fmt = data.replace("export_", "")
        template_id = context.user_data.get("selected_template", "classic")
        optimized = context.user_data.get("optimized_resume")
        candidate_name = context.user_data.get("candidate_name") or "Candidate"

        if not optimized:
            await query.message.reply_text("❌ No optimized resume data. Please run /match again.")
            return ConversationHandler.END

        # Sanitize: ensure no None values in optimized resume
        if isinstance(optimized, dict):
            for key, val in optimized.items():
                if val is None:
                    optimized[key] = "" if isinstance(val, str) or val is None else []

        template_names = {
            "classic": "📜 Classic",
            "modern": "🎨 Modern Two-Column",
            "minimal": "✨ Minimal",
            "ats": "🤖 ATS-Friendly",
        }
        tpl_name = template_names.get(template_id, template_id)

        await query.message.reply_text(
            f"⏳ *Generating your CV...*\n"
            f"👤 Name: *{candidate_name}*\n"
            f"🎨 Template: {tpl_name}\n"
            f"📁 Format: {fmt.upper()}",
            parse_mode="Markdown"
        )

        user_id = update.effective_user.id
        files_to_send = []

        try:
            if fmt in ("pdf", "both"):
                pdf_path = os.path.join(TEMP_DIR, f"{user_id}_cv_{template_id}.pdf")
                generate_pdf(optimized, pdf_path, candidate_name, template_id)
                files_to_send.append(("pdf", pdf_path))

            if fmt in ("docx", "both"):
                docx_path = os.path.join(TEMP_DIR, f"{user_id}_cv_{template_id}.docx")
                generate_docx(optimized, docx_path, candidate_name, template_id)
                files_to_send.append(("docx", docx_path))

            for file_fmt, file_path in files_to_send:
                safe_name = candidate_name.replace(" ", "_")
                with open(file_path, "rb") as f:
                    await query.message.reply_document(
                        document=f,
                        filename=f"Optimized_CV_{safe_name}_{template_id}.{file_fmt}",
                        caption=f"✅ *{tpl_name}* CV ({file_fmt.upper()}) for *{candidate_name}*",
                        parse_mode="Markdown"
                    )

            for _, file_path in files_to_send:
                try:
                    os.remove(file_path)
                except Exception:
                    pass

            keyboard = [
                [InlineKeyboardButton("📄 Regenerate CV", callback_data="ask_name")],
                [InlineKeyboardButton("🎨 Try Another Template", callback_data="choose_template")],
                [InlineKeyboardButton("✅ Done", callback_data="user_done")],
            ]

            await query.message.reply_text(
                "🎉 *Your optimized CV is ready!*\n\n"
                "💬 *Want to make changes?* Just type your suggestions:\n"
                "• _\"Add more details to my experience\"_\n"
                "• _\"Change my name to ...\"_\n"
                "• _\"Make it more concise\"_\n\n"
                "I'll update your CV and you can regenerate it!\n\n"
                "Type *done* or tap ✅ when you're satisfied.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return SHOWING_RESULTS

        except Exception as e:
            logger.error(f"CV generation error: {e}")
            await query.message.reply_text(f"❌ Error generating CV: {e}")
            return SHOWING_RESULTS

    # ── User Done ──
    elif data == "user_done":
        context.user_data.clear()
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "🎉 *Great, you're all set!*\n\n"
            "Thanks for using Resume-JD Matcher Bot! 🤖\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔄 Want to match another resume?\n"
            "Send /match to start a new analysis!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # ── New Analysis ──
    elif data == "new_analysis":
        context.user_data.clear()
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "🔄 *Starting new analysis!*\n\n"
            "📄 Please upload your resume (PDF, DOCX, TXT) or paste it.",
            parse_mode="Markdown"
        )
        return WAITING_RESUME

    # ── Help ──
    elif data == "show_help":
        await query.message.reply_text(
            "📚 Send /help for detailed usage instructions!")
        return SHOWING_RESULTS

    # ── Start Match from menu ──
    elif data == "start_match":
        context.user_data.clear()
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "📄 *Step 1/2: Upload Your Resume*\n\n"
            "Send your resume as a file (PDF, DOCX, TXT) or paste it!",
            parse_mode="Markdown"
        )
        return WAITING_RESUME

    # ── Mock Interview ──
    elif data == "mock_interview":
        if not context.user_data.get("analysis_result"):
            await query.message.reply_text("❌ Please run /match first!")
            return SHOWING_RESULTS
        await query.edit_message_reply_markup(reply_markup=None)
        await _generate_mock_interview(query.message, context)
        return SHOWING_RESULTS

    # ── Interview Tips ──
    elif data == "interview_tips":
        if not context.user_data.get("analysis_result"):
            await query.message.reply_text("❌ Please run /match first!")
            return SHOWING_RESULTS
        await query.edit_message_reply_markup(reply_markup=None)
        await _generate_interview_tips(query.message, context)
        return SHOWING_RESULTS

    # ── Resume Strength ──
    elif data == "resume_strength":
        if not context.user_data.get("analysis_result"):
            await query.message.reply_text("❌ Please run /match first!")
            return SHOWING_RESULTS
        await query.edit_message_reply_markup(reply_markup=None)
        await _generate_resume_strength(query.message, context)
        return SHOWING_RESULTS

    # ── Career Tips ──
    elif data == "career_tips":
        if not context.user_data.get("analysis_result"):
            await query.message.reply_text("❌ Please run /match first!")
            return SHOWING_RESULTS
        await query.edit_message_reply_markup(reply_markup=None)
        await _generate_career_tips(query.message, context)
        return SHOWING_RESULTS


# ─────────────────────────────────────────────────────────────
# AI Feature Generators
# ─────────────────────────────────────────────────────────────
async def _generate_mock_interview(message, context):
    """Generate mock interview questions based on resume + JD."""
    await message.reply_text("🎯 *Generating mock interview questions...*", parse_mode="Markdown")

    resume = context.user_data.get("resume_text", "")[:2000]
    jd = context.user_data.get("jd_text", "")[:2000]

    prompt = f"""You are an expert technical interviewer.

Based on this RESUME and JOB DESCRIPTION, generate realistic interview questions.

RESUME:
{resume}

JOB DESCRIPTION:
{jd}

Generate exactly:
- 3 Technical/Skills questions (based on the required skills)
- 2 Behavioral questions (STAR method format)
- 2 Experience questions (about their specific work history)
- 1 Situational question
- 2 Questions the candidate should ask the interviewer

For each question, also provide a brief hint on how to answer it well (1-2 lines).

Format your response nicely with emojis and clear sections. Use markdown bold for section headers."""

    result = _gemini_generate(prompt)

    await _send_long_message(
        message,
        f"🎯 *MOCK INTERVIEW QUESTIONS*\n━━━━━━━━━━━━━━━━━━━━━━━\n\n{result}",
        reply_markup=_results_keyboard(bool(context.user_data.get("optimized_resume")))
    )


async def _generate_interview_tips(message, context):
    """Generate personalized interview preparation tips."""
    await message.reply_text("💼 *Preparing your interview tips...*", parse_mode="Markdown")

    resume = context.user_data.get("resume_text", "")[:2000]
    jd = context.user_data.get("jd_text", "")[:2000]
    score = context.user_data.get("analysis_result", {}).get("overall_score", 50)

    prompt = f"""You are a career coach preparing a candidate for an interview.

RESUME:
{resume}

JOB DESCRIPTION:
{jd}

MATCH SCORE: {score}/100

Provide personalized interview preparation advice:

1. How to present yourself (opening pitch based on their actual experience)
2. Key strengths to emphasize (from their resume that match the JD)
3. Weakness areas to prepare for (gaps between resume and JD)
4. Salary negotiation tips (based on the role)
5. Body language and communication tips
6. Common mistakes to avoid for this specific role
7. Day-before checklist (what to prepare)

Be specific to THIS candidate and THIS job. Use their actual experience and skills.
Format nicely with emojis."""

    result = _gemini_generate(prompt)

    await _send_long_message(
        message,
        f"💼 *INTERVIEW PREPARATION*\n━━━━━━━━━━━━━━━━━━━━━━━\n\n{result}",
        reply_markup=_results_keyboard(bool(context.user_data.get("optimized_resume")))
    )


async def _generate_resume_strength(message, context):
    """Analyze resume strengths and weaknesses in detail."""
    await message.reply_text("💪 *Analyzing your resume...*", parse_mode="Markdown")

    resume = context.user_data.get("resume_text", "")[:2000]
    jd = context.user_data.get("jd_text", "")[:2000]

    prompt = f"""You are a senior recruiter who has reviewed 10,000+ resumes.

RESUME:
{resume}

JOB DESCRIPTION:
{jd}

Give a brutally honest but constructive analysis:

1. Top 5 Strengths of this resume (what stands out)
2. Top 5 Weaknesses (what's missing or poorly presented)
3. Red Flags a recruiter would notice
4. ATS Compatibility — would this pass ATS scanners? Why/why not?
5. Format and Structure rating (1-10) with explanation
6. Impact Score — do the bullets show impact or just duties?
7. One-line verdict — would you shortlist this candidate?

Be specific. Quote actual lines from the resume when pointing out issues.
Format with emojis for readability."""

    result = _gemini_generate(prompt)

    await _send_long_message(
        message,
        f"💪 *RESUME STRENGTH ANALYSIS*\n━━━━━━━━━━━━━━━━━━━━━━━\n\n{result}",
        reply_markup=_results_keyboard(bool(context.user_data.get("optimized_resume")))
    )


async def _generate_career_tips(message, context):
    """Generate personalized career growth tips."""
    await message.reply_text("🚀 *Generating career tips...*", parse_mode="Markdown")

    resume = context.user_data.get("resume_text", "")[:2000]
    jd = context.user_data.get("jd_text", "")[:2000]

    prompt = f"""You are a career strategist helping someone grow in their career.

RESUME:
{resume}

TARGET JOB:
{jd}

Provide actionable career advice:

1. Skills Gap Analysis — What skills should they learn next? (be specific with resources/courses)
2. Certifications — Which certifications would boost their profile for this role?
3. Portfolio/Projects — What side projects or contributions would strengthen their application?
4. Networking Strategy — How to network for this specific role/industry
5. Career Path — What's the typical progression from their current level?
6. Timeline — Realistic timeline to become a strong candidate if they're not yet
7. Quick Wins — 3 things they can do THIS WEEK to improve

Be specific to their experience level and target role.
Format with emojis."""

    result = _gemini_generate(prompt)

    await _send_long_message(
        message,
        f"🚀 *CAREER GROWTH TIPS*\n━━━━━━━━━━━━━━━━━━━━━━━\n\n{result}",
        reply_markup=_results_keyboard(bool(context.user_data.get("optimized_resume")))
    )

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled. Send /match to start again!")
    return ConversationHandler.END


async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Send /match to start analyzing your resume!\nSend /help for more info.")


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
def main():
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_telegram_bot_token_here":
        print("=" * 55)
        print("  ❌ ERROR: TELEGRAM_BOT_TOKEN not set!")
        print("=" * 55)
        print("\n  1. Create a bot at https://t.me/BotFather")
        print("  2. Copy the token → add to .env")
        print("  3. Also add: GEMINI_API_KEY=your_key_here")
        print()
        return

    print()
    print("🤖 Resume-JD Matcher Bot")
    print("=" * 55)
    print("  Templates: Classic | Modern | Minimal | ATS-Friendly")
    print("  Formats:   PDF | DOCX")
    print("  Features:  Interactive Chat, Name Input")
    print("=" * 55)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("match", match_command),
        ],
        states={
            WAITING_RESUME: [
                MessageHandler(filters.Document.ALL, receive_resume_file),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_resume_text),
            ],
            WAITING_JD: [
                MessageHandler(filters.Document.ALL, receive_jd_file),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_jd_text),
            ],
            SHOWING_RESULTS: [
                CallbackQueryHandler(handle_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_chat),
            ],
            WAITING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name),
                CallbackQueryHandler(handle_callback),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CommandHandler("match", match_command),
        ],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("mock", mock_command))
    app.add_handler(CommandHandler("tips", tips_command))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))

    print("  ✅ Bot is running! Press Ctrl+C to stop.")
    print("  📱 Open Telegram and message your bot.")
    print("=" * 55)
    print()

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
