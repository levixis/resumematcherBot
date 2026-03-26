# 🤖 Resume Matcher Bot - Interview Guide

This guide breaks down exactly how you built the bot, what each piece does, and how to answer technical questions like a pro. Think of this as your "cheat sheet."

---

## 1. The "Elevator Pitch" (What did you build?)
**If they ask:** *"Tell me about your project."*

**Your answer:**
"I built an AI-powered Telegram bot that helps job seekers tailor their resumes to specific job descriptions.
Users upload their resume and a Job Description. The bot uses the Google Gemini AI to analyze them, gives a match score out of 100, points out missing skills, and gives specific suggestions on how to improve.
Then, it automatically rewrites the resume to better match the job, and lets the user export it as a professional PDF or DOCX file using different templates (like Classic, Modern, or ATS-friendly). I even added an interactive chat feature so users can talk to the AI to tweak the generated CV before downloading it."

---

## 2. The Architecture (How does it work?)
**If they ask:** *"Walk me through the architecture / How do the pieces connect?"*

Explain that you split the project into **4 core modules** to keep the code clean and organized.

### Module 1: `bot.py` (The Traffic Cop)
This is the main entry point. It uses `python-telegram-bot` to handle everything the user types or clicks.
*   **How it works:** It uses a `ConversationHandler`. Think of this as a state machine. It remembers where the user is in the flow:
    1. `WAITING_RESUME`: Waiting for the file.
    2. `WAITING_JD`: Waiting for the job description.
    3. `SHOWING_RESULTS`: Showing the score and taking chat feedback.
    4. `WAITING_NAME`: Asking for their name if the AI couldn't find it.
*   **Key Concept to Mention:** "I used Telegram's InlineKeyboards for the buttons to make the UI user-friendly, and async functions because network requests (like downloading files or calling the AI) take time, and we don't want the bot to freeze."

### Module 2: `resume_parser.py` (The Reader)
This file grabs the text out of the files the user uploads.
*   **How it works:** Depending on the file extension, it uses different libraries:
    *   `.pdf`: Uses `PyPDF2` to extract text page by page.
    *   `.docx`: Uses `python-docx` to read paragraphs.
    *   `.txt`: Just reads it as a normal string.
*   **Key Concept to Mention:** "Handling different file types was tricky, so I built a central `parse_resume()` function. The rest of the app doesn't care *how* the text was extracted; it just gets a clean text string."

### Module 3: `matcher.py` (The Brain)
This is where the magic happens. It connects to the Google Gemini API (`gemini-2.5-flash` model).
*   **How it works:** It takes the resume text and the JD text and inserts them into a prompt.
*   **The Prompt:** The prompt tells the AI to act as an ATS (Applicant Tracking System). Crucially, the prompt demands that the AI returns *pure JSON* (a structured data format).
*   **Key Concept to Mention:** "The hardest part of using LLMs (Large Language Models) in code is making sure they return data your code can understand. I solved this by explicitly instructing Gemini to return a strict JSON structure containing the scores, missing skills, and the optimized resume text. I then parse that JSON in Python using `json.loads()`."

### Module 4: `cv_generator.py` (The Designer)
This takes the optimized data from Gemini and turns it into real files.
*   **PDFs:** Uses `ReportLab`. It literally draws the text onto an empty canvas, calculating margins and fonts.
*   **DOCX:** Uses `python-docx`. It creates a document object and adds formatted paragraphs.
*   **Key Concept to Mention:** "I built a template system. Instead of hardcoding the design, I have a `TEMPLATES` dictionary containing colors and fonts. When generating the PDF, it looks up the chosen template (Classic, Modern, Minimal, ATS) and applies those styles."

---

## 3. Anticipated Interview Questions & Answers

### Q1: "Why did you choose Telegram instead of making a web app?"
**Answer:** "A Telegram bot provides immediate distribution. Job seekers are often on their phones. Instead of making them sign up for a website, they can just open an app they already use, drop a file, and get instant feedback. It lowers the barrier to entry."

### Q2: "Why Gemini and not OpenAI/ChatGPT?"
**Answer:** "I went with Gemini 2.5 Flash because it's extremely fast and offers a very generous free tier, which is perfect for a hackathon. It's also exceptionally good at following strict JSON formatting instructions, which was critical for my `matcher.py` module to parse the results reliably."

### Q3: "How do you handle the interactive chat feature?"
**Answer:** "When the user types a message *after* their score is generated, `bot.py` catches it. It takes their current 'optimized resume' state, their suggestion, and the original JD, and sends it all *back* to Gemini. The prompt asks Gemini to apply their specific suggestion to the JSON structure. Once Gemini replies with the new JSON, I overwrite the user's state in memory so the 'Generate CV' button uses newest version."

### Q4: "What happens if the Gemini AI hallucinates or returns bad JSON?"
**Answer:** "I implemented error handling. In `matcher.py`, the `json.loads()` call is wrapped in a `try/except` block. If Gemini returns garbage text that isn't valid JSON, the code catches the `JSONDecodeError` and returns a fallback 'default' dictionary. This ensures the bot doesn't crash entirely; it just tells the user the analysis had an issue."

### Q5: "How is the bot deployed?"
**Answer:** "I containerized the entire application using Docker. I wrote a `Dockerfile` using a lightweight Python image, and a `docker-compose.yml` file. This means the app is completely isolated. I can run `docker compose up -d --build` on any server (like Render, Railway, or AWS EC2), and it will automatically install dependencies, start the bot, and automatically restart it if it ever crashes."

---

## 4. Key Developer Terms to Use Naturally
Sprinkle these words into your explanations to sound like a senior dev:
*   **"State Management":** Mention how the `ConversationHandler` in `python-telegram-bot` keeps track of the user's *state* (waiting for resume, showing results, etc.).
*   **"Structured Output":** When talking about Gemini, mention "enforcing structured output" (forcing it to give you JSON).
*   **"Modular Architecture":** Mention how splitting parsing, matching, generic generation, and bot logic into separate files makes the code easier to maintain.
*   **"Containerization":** When talking about Docker.
*   **"Error Handling":** When talking about catching bad files or bad AI responses.

## 5. Summary Check
If you get nervous, just remember the flow:
1. **User Input** (Telegram hooks it) ->
2. **Text Extraction** (PyPDF2/docx) ->
3. **AI Analysis** (Gemini -> JSON) ->
4. **Interactive State** (User refines the JSON) ->
5. **Generation** (ReportLab/docx creates the file) ->
6. **Delivery** (Telegram sends it back).
