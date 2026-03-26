"""
Matcher Module
Uses Google Gemini API to analyze resume-JD match and provide suggestions.
"""

import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()


def _get_model():
    """Initialize and return the Gemini model."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise ValueError(
            "⚠️ GEMINI_API_KEY not configured!\n"
            "Get your free key at: https://aistudio.google.com/\n"
            "Then add it to your .env file."
        )
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.5-flash")


def analyze_match(resume_text: str, jd_text: str) -> dict:
    """
    Analyze how well a resume matches a job description.
    
    Returns a dict with:
    - overall_score (0-100)
    - skills_score (0-100)
    - experience_score (0-100)
    - education_score (0-100)
    - keywords_score (0-100)
    - matched_skills (list)
    - missing_skills (list)
    - suggestions (list of improvement suggestions)
    - summary (brief summary of the analysis)
    - optimized_resume (dict with optimized sections)
    """
    model = _get_model()

    prompt = f"""You are an expert ATS (Applicant Tracking System) analyzer and career coach.

Analyze how well the following RESUME matches the JOB DESCRIPTION. Be thorough and constructive.

=== RESUME ===
{resume_text}

=== JOB DESCRIPTION ===
{jd_text}

Return your analysis as a valid JSON object with EXACTLY this structure (no markdown, no code blocks, just pure JSON):
{{
    "candidate_name": "The candidate's full name extracted from the resume, or null if not found",
    "overall_score": <number 0-100>,
    "skills_score": <number 0-100>,
    "experience_score": <number 0-100>,
    "education_score": <number 0-100>,
    "keywords_score": <number 0-100>,
    "matched_skills": ["skill1", "skill2", ...],
    "missing_skills": ["skill1", "skill2", ...],
    "suggestions": [
        "Specific actionable suggestion 1",
        "Specific actionable suggestion 2",
        "Specific actionable suggestion 3",
        "Specific actionable suggestion 4",
        "Specific actionable suggestion 5"
    ],
    "summary": "2-3 sentence overall assessment",
    "optimized_resume": {{
        "professional_summary": "A powerful 3-4 line summary tailored to this JD",
        "skills": ["skill1", "skill2", ...],
        "experience": [
            {{
                "title": "Job Title",
                "company": "Company Name",
                "duration": "Start - End",
                "bullets": ["Achievement 1 tailored to JD", "Achievement 2", ...]
            }}
        ],
        "education": [
            {{
                "degree": "Degree Name",
                "institution": "Institution Name",
                "year": "Year"
            }}
        ],
        "certifications": ["cert1", "cert2", ...],
        "projects": [
            {{
                "name": "Project Name",
                "description": "Brief description highlighting relevance to JD"
            }}
        ]
    }}
}}

IMPORTANT RULES:
1. Be generous but honest with scoring
2. Suggestions must be specific and actionable
3. The optimized_resume should keep the candidate's real information but reword/restructure it to better match the JD
4. Include all relevant skills from both the resume and JD
5. Return ONLY valid JSON, no extra text"""

    try:
        response = model.generate_content(prompt)
        response_text = response.text.strip()

        # Clean up response - remove markdown code blocks if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            # Remove first line (```json or ```) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            response_text = "\n".join(lines)

        result = json.loads(response_text)

        # Validate required fields
        required_fields = [
            "overall_score", "skills_score", "experience_score",
            "education_score", "keywords_score", "matched_skills",
            "missing_skills", "suggestions", "summary", "optimized_resume"
        ]
        for field in required_fields:
            if field not in result:
                result[field] = _get_default_value(field)

        return result

    except json.JSONDecodeError as e:
        # If JSON parsing fails, return a structured fallback
        return {
            "overall_score": 50,
            "skills_score": 50,
            "experience_score": 50,
            "education_score": 50,
            "keywords_score": 50,
            "matched_skills": [],
            "missing_skills": [],
            "suggestions": [
                "Could not fully analyze - please try again",
                "Ensure your resume has clear sections",
                "List skills that match the JD explicitly"
            ],
            "summary": "Analysis encountered an issue. Please try again.",
            "optimized_resume": None,
            "error": str(e)
        }
    except Exception as e:
        raise RuntimeError(f"Gemini API error: {e}")


def _get_default_value(field: str):
    """Return default values for missing fields."""
    defaults = {
        "overall_score": 50,
        "skills_score": 50,
        "experience_score": 50,
        "education_score": 50,
        "keywords_score": 50,
        "matched_skills": [],
        "missing_skills": [],
        "suggestions": ["Unable to generate suggestions"],
        "summary": "Analysis incomplete",
        "optimized_resume": None
    }
    return defaults.get(field, None)
