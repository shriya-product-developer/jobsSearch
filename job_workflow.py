# ════════════════════════════════════════════════════════════════════
# IMPORTS & CONFIG
# ════════════════════════════════════════════════════════════════════
import os
import re
import json
import requests
import xml.etree.ElementTree as ET
import resend
from datetime import date
from google import genai
from google.genai import types
from serpapi import GoogleSearch

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
RESEND_API_KEY = os.environ["RESEND_API_KEY"]
SERPAPI_KEY    = os.environ["SERPAPI_KEY"]
TO_EMAIL       = os.environ["TO_EMAIL"]
FROM_EMAIL     = "onboarding@resend.dev"

resend.api_key = RESEND_API_KEY

CV_SUMMARY = """
Name: Raghav Malhotra
Current role: Business Analyst at 23ICT, Melbourne (Mar 2025 - Present)
Education: Master of Commerce (Data Analytics & Information Systems), University of Sydney (2023-2025)
           Bachelor of Business Administration, GGSI University Delhi (2019-2022)
Skills: Power BI, Tableau, Excel, Power Query, DAX, Python, SQL, Jira, Agile
Experience highlights:
  - IT consulting, client problem-solving, Agile/Scrum at 23ICT
  - Data analysis with Power BI and Tableau at Arsenal Infosolutions
  - Database management and onboarding at STMicroelectronics
  - Predictive modelling (86% precision) using Python and logistic regression
Certifications: Microsoft Power BI (Udemy), Google Data Analytics Professional,
                Business Analysis & Process Management (Coursera)
Target roles: Entry level Data Analyst, Business Analyst, Product Analyst in Sydney
Key strengths: Data analytics, business intelligence, stakeholder communication,
               Agile methodology, Python/SQL/Power BI
Awards: $15,000 merit scholarship, University of Sydney
"""

today_str = date.today().strftime("%A, %B %d, %Y")


# ════════════════════════════════════════════════════════════════════
# TOOLS
# ════════════════════════════════════════════════════════════════════
def search_seek_rss(role: str = "analyst") -> str:
    """
    Search Seek.com.au for entry level analyst jobs in Sydney.
    Returns job listings with title, company, URL and description.

    Args:
        role: Job role to search for e.g. 'data analyst', 'business analyst'
    """
    query = role.replace(" ", "+")
    headers = {"User-Agent": "Mozilla/5.0 (JobAgent/1.0)"}

    # Try 1: Seek JSON API
    try:
        url = f"https://www.seek.com.au/api/chalice-search/v4/search?where=Sydney+NSW&what={query}&worktype=242"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            jobs = data.get("data", [])
            if jobs:
                lines = []
                for i, job in enumerate(jobs[:8], 1):
                    lines.append(
                        f"{i}. {job.get('title', 'N/A')}\n"
                        f"   Company: {job.get('advertiser', {}).get('description', 'N/A')}\n"
                        f"   Location: {job.get('location', 'Sydney')}\n"
                        f"   URL: https://www.seek.com.au/job/{job.get('id', '')}\n"
                        f"   Posted: {job.get('listingDate', 'Recent')}\n"
                        f"   Summary: {job.get('teaser', 'No description')[:200]}\n"
                    )
                return f"[SEEK — {role.upper()}]\n" + "\n".join(lines)
    except Exception as e:
        print(f"  [Seek JSON API failed: {e}]")

    # Try 2: Seek RSS feed
    try:
        rss_url = f"https://www.seek.com.au/{role.replace(' ', '-')}-jobs/in-Sydney-NSW?format=rss"
        resp = requests.get(rss_url, headers=headers, timeout=10)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "xml" not in content_type and not resp.text.strip().startswith("<"):
            raise ValueError(f"Not XML — got: {resp.text[:100]}")

        root = ET.fromstring(resp.content)
        items = root.findall(".//item")
        if not items:
            raise ValueError("No items in RSS feed")

        lines = []
        for i, item in enumerate(items[:8], 1):
            def get(tag):
                el = item.find(tag)
                return el.text.strip() if el is not None and el.text else "N/A"
            title   = get("title")
            link    = get("link")
            summary = re.sub(r"<[^>]+>", "", get("description"))[:200]
            lines.append(
                f"{i}. {title}\n"
                f"   URL: {link}\n"
                f"   Summary: {summary}\n"
            )
        return f"[SEEK RSS — {role.upper()}]\n" + "\n".join(lines)

    except Exception as e:
        print(f"  [Seek RSS failed: {e}]")

    # Try 3: Scrape Seek search page
    try:
        search_url = f"https://www.seek.com.au/{role.replace(' ', '-')}-jobs/in-Sydney-NSW"
        resp = requests.get(search_url, headers=headers, timeout=10)
        resp.raise_for_status()

        titles    = re.findall(r'data-automation="jobTitle"[^>]*>([^<]+)<', resp.text)
        companies = re.findall(r'data-automation="jobCompany"[^>]*>([^<]+)<', resp.text)
        job_ids   = re.findall(r'data-job-id="(\d+)"', resp.text)

        if not titles:
            return f"No jobs found on Seek for: {role}"

        lines = []
        for i, (title, job_id) in enumerate(zip(titles[:8], job_ids[:8]), 1):
            company = companies[i-1] if i-1 < len(companies) else "N/A"
            lines.append(
                f"{i}. {title}\n"
                f"   Company: {company}\n"
                f"   URL: https://www.seek.com.au/job/{job_id}\n"
            )
        return f"[SEEK — {role.upper()}]\n" + "\n".join(lines)

    except Exception as e:
        return f"Error searching Seek: {e}"


def search_google_jobs(role: str = "entry level data analyst Sydney") -> str:
    """
    Search Google Jobs via SerpAPI for analyst roles in Sydney.
    Pulls from LinkedIn, Glassdoor, Indeed and other boards.
    Returns job listings with title, company, URL and description.

    Args:
        role: Full search query e.g. 'entry level business analyst Sydney'
    """
    try:
        search = GoogleSearch({
            "engine":   "google_jobs",
            "q":        f"{role} Sydney Australia entry level",
            "location": "Sydney, New South Wales, Australia",
            "api_key":  SERPAPI_KEY,
        })
        results = search.get_dict()
        jobs = results.get("jobs_results", [])

        if not jobs:
            return f"No Google Jobs results for: {role}"

        lines = []
        for i, job in enumerate(jobs[:8], 1):
            apply_url = job.get("related_links", [{}])[0].get("link", "")
            if not apply_url:
                apply_url = f"https://www.google.com/search?q={role.replace(' ', '+')}+Sydney+jobs"

            lines.append(
                f"{i}. {job.get('title', 'N/A')}\n"
                f"   Company: {job.get('company_name', 'N/A')}\n"
                f"   Location: {job.get('location', 'Sydney')}\n"
                f"   Via: {job.get('via', 'N/A')}\n"
                f"   URL: {apply_url}\n"
                f"   Posted: {job.get('detected_extensions', {}).get('posted_at', 'Recent')}\n"
                f"   Summary: {job.get('description', 'No description')[:300]}\n"
            )
        return f"[GOOGLE JOBS — {role.upper()}]\n" + "\n".join(lines)

    except Exception as e:
        return f"Error searching Google Jobs: {e}"


# ════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ════════════════════════════════════════════════════════════════════
SYSTEM_PROMPT = f"""You are a career research agent helping Raghav Malhotra find
entry level analyst jobs in Sydney, Australia. Today is {today_str}.

Here is Raghav's CV:
{CV_SUMMARY}

Your job:
1. Search for entry level analyst roles using both search_seek_rss and
   search_google_jobs. Search for at least 3 role types:
   - "data analyst"
   - "business analyst"
   - "product analyst"

2. From all results, select the BEST 3-5 jobs using this scoring logic:
   Score each job on two dimensions:
   A) CV Match (0-10): How well does it match Raghav's skills and experience?
   B) Competition Level (0-10): How few applicants likely? Score 10 if posted
      today or yesterday with no applicant count mentioned. Score lower if
      the listing mentions "100+ applicants", "actively hiring" with high
      volume, or has been posted more than 2 weeks ago.

   Final score = (CV Match x 0.6) + (Competition x 0.4)
   Pick the 3-5 jobs with the highest final score.
   Prefer jobs posted in the last 3 days where possible.

3. For each selected job write:
   - A 1-line reason why this specific role fits Raghav's CV
   - A competition assessment: "Low", "Medium", or "High" applicants
   - A competition note: 1 line explaining why competition is low/high
     e.g. "Posted 1 day ago with no applicant count — likely under 20 applicants"
   - A personalised 5-8 line Statement of Purpose (SOP) for that specific
     company and role — mention the company by name, reference Raghav's
     relevant experience, and explain why he wants THIS role at THIS company

4. Return ONLY a JSON object in this exact structure:
{{
  "jobs": [
    {{
      "rank": 1,
      "title": "Data Analyst",
      "company": "Company Name",
      "location": "Sydney, NSW",
      "source": "Seek / LinkedIn / Indeed",
      "url": "https://...",
      "posted": "2 days ago",
      "cv_match_score": 8,
      "competition_score": 9,
      "final_score": 8.4,
      "competition_level": "Low",
      "competition_note": "Posted yesterday, no applicant count listed",
      "fit_reason": "One line explaining why this role suits Raghav",
      "sop": "Dear Hiring Manager at [Company],\\n\\nI am writing to express my interest in the [Role] position at [Company]. [5-8 lines personalised to this company and role]\\n\\nWarm regards,\\nRaghav Malhotra"
    }}
  ],
  "total_jobs_reviewed": 20,
  "searches_performed": 3
}}

Return ONLY the JSON. No markdown, no preamble."""


# ════════════════════════════════════════════════════════════════════
# AGENT LOOP
# ════════════════════════════════════════════════════════════════════
def run_agent() -> dict:
    client = genai.Client(api_key=GEMINI_API_KEY)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[search_seek_rss, search_google_jobs],
    )

    chat = client.chats.create(model="gemini-2.5-flash", config=config)
    response = chat.send_message(
        "Search for the best entry level analyst jobs in Sydney for Raghav "
        "and return the top 3-5 matches with personalised fit reasons and SOPs."
    )

    step = 0
    while True:
        step += 1
        print(f"[Step {step}] Processing...")

        tool_calls = [
            part for candidate in response.candidates
            for part in candidate.content.parts
            if part.function_call is not None
        ]

        if not tool_calls:
            raw = response.text.strip()
            print(f"[Debug] Raw response preview: {raw[:300]}")

            raw_clean = re.sub(r"^```json\s*", "", raw)
            raw_clean = re.sub(r"```$", "", raw_clean).strip()

            try:
                return json.loads(raw_clean)
            except json.JSONDecodeError:
                print("[Warning] Gemini returned no JSON — tools likely failed")
                return {
                    "jobs": [],
                    "total_jobs_reviewed": 0,
                    "searches_performed": 0,
                    "error": raw[:500]
                }

        tool_response_parts = []
        for part in tool_calls:
            fn = part.function_call
            print(f"  -> {fn.name}({json.dumps(dict(fn.args))})")

            if fn.name == "search_seek_rss":
                result = search_seek_rss(**fn.args)
            elif fn.name == "search_google_jobs":
                result = search_google_jobs(**fn.args)
            else:
                result = f"Unknown tool: {fn.name}"

            print(f"  <- {result[:120].replace(chr(10), ' ')}...")
            tool_response_parts.append(
                types.Part.from_function_response(
                    name=fn.name,
                    response={"result": result}
                )
            )

        response = chat.send_message(tool_response_parts)


# ════════════════════════════════════════════════════════════════════
# FORMAT HTML EMAIL
# ════════════════════════════════════════════════════════════════════
def format_html_email(data: dict) -> tuple[str, str]:
    jobs     = data.get("jobs", [])
    total    = data.get("total_jobs_reviewed", "multiple")
    searches = data.get("searches_performed", 3)
    subject  = f"Your Daily Job Matches — {today_str}"

    source_colours = {
        "seek":      "#0d3880",
        "linkedin":  "#0077b5",
        "indeed":    "#003a9b",
        "glassdoor": "#0caa41",
    }

    competition_colours = {
        "Low":    ("#dcfce7", "#166534"),
        "Medium": ("#fef9c3", "#854d0e"),
        "High":   ("#fee2e2", "#991b1b"),
    }

    job_blocks = ""
    for job in jobs:
        source_key  = job.get("source", "").lower().split("/")[0].strip()
        badge_color = source_colours.get(source_key, "#534AB7")

        competition      = job.get("competition_level", "Unknown")
        competition_note = job.get("competition_note", "")
        cv_score         = job.get("cv_match_score", "-")
        comp_score       = job.get("competition_score", "-")
        final_score      = job.get("final_score", "-")
        sop_html         = job.get("sop", "").replace("\n", "<br>")

        comp_bg, comp_text = competition_colours.get(
            competition, ("#f3f4f6", "#374151")
        )

        job_blocks += f"""
        <div style="margin-bottom:36px; padding:24px; background:#fff;
                    border:1px solid #eee; border-radius:12px;">

          <div style="display:flex; justify-content:space-between;
                      align-items:flex-start; flex-wrap:wrap; gap:8px;">
            <div>
              <span style="background:{badge_color}; color:#fff; font-size:11px;
                           font-weight:600; padding:3px 10px; border-radius:12px;">
                {job.get("source", "Job Board").upper()}
              </span>
              <span style="margin-left:8px; font-size:11px; color:#999;">
                {job.get("posted", "Recently posted")}
              </span>
            </div>
            <span style="font-size:11px; font-weight:600; color:#534AB7;
                         background:#f0edff; padding:3px 10px; border-radius:12px;">
              Match score: {final_score}/10
            </span>
          </div>

          <h2 style="margin:12px 0 4px; font-size:19px; font-weight:700;
                     color:#1a1a1a; line-height:1.3;">
            {job.get("title", "Analyst Role")}
          </h2>
          <p style="margin:0 0 4px; font-size:14px; color:#555;">
            {job.get("company", "Company")} &nbsp;·&nbsp; {job.get("location", "Sydney")}
          </p>

          <div style="display:flex; gap:8px; margin:10px 0; flex-wrap:wrap;">
            <span style="font-size:12px; color:#555; background:#f5f5f5;
                         padding:4px 10px; border-radius:8px;">
              CV match: {cv_score}/10
            </span>
            <span style="font-size:12px; color:#555; background:#f5f5f5;
                         padding:4px 10px; border-radius:8px;">
              Competition score: {comp_score}/10
            </span>
            <span style="font-size:12px; font-weight:600; color:{comp_text};
                         background:{comp_bg}; padding:4px 10px; border-radius:8px;">
              {competition} competition
            </span>
          </div>

          <p style="margin:0 0 12px; font-size:12px; color:#888;
                    font-style:italic;">{competition_note}</p>

          <div style="margin:12px 0; padding:10px 14px; background:#f0f7ff;
                      border-left:3px solid #534AB7; border-radius:0 8px 8px 0;">
            <p style="margin:0; font-size:13px; color:#334; font-weight:500;">
              Why this fits you: {job.get("fit_reason", "")}
            </p>
          </div>

          <div style="margin:16px 0; padding:16px; background:#fafafa;
                      border:1px solid #eee; border-radius:8px;">
            <p style="margin:0 0 8px; font-size:12px; font-weight:600;
                      color:#888; letter-spacing:0.5px;">
              SUGGESTED STATEMENT OF PURPOSE
            </p>
            <p style="margin:0; font-size:13px; color:#333;
                      line-height:1.7;">{sop_html}</p>
          </div>

          <a href="{job.get('url', '#')}"
             style="display:inline-block; margin-top:4px; padding:10px 24px;
                    background:#1a1a1a; color:#fff; font-size:13px;
                    font-weight:600; text-decoration:none; border-radius:8px;">
            Apply Now
          </a>
        </div>
        """

    html = f"""
    <html><body style="margin:0; padding:0; background:#f5f5f5;
                       font-family:-apple-system, BlinkMacSystemFont, sans-serif;">
      <div style="max-width:640px; margin:32px auto;">

        <div style="background:#1a1a1a; padding:28px 36px;
                    border-radius:12px 12px 0 0;">
          <p style="margin:0; color:#aaa; font-size:13px;">{today_str}</p>
          <h1 style="margin:6px 0 0; color:#fff; font-size:24px;
                     font-weight:700;">Your Job Matches</h1>
          <p style="margin:6px 0 0; color:#888; font-size:13px;">
            {len(jobs)} roles selected from {total} jobs reviewed
            across {searches} searches · ranked by CV fit + low competition
          </p>
        </div>

        <div style="padding:24px; background:#f5f5f5;">
          {job_blocks}
        </div>

        <div style="background:#fff; padding:20px 36px;
                    border-top:1px solid #eee; border-radius:0 0 12px 12px;">
          <p style="margin:0; color:#aaa; font-size:12px;">
            Matched to Raghav's CV automatically · {today_str}<br>
            Sources: Seek, Google Jobs (LinkedIn, Glassdoor, Indeed)
          </p>
        </div>

      </div>
    </body></html>
    """

    return subject, html


# ════════════════════════════════════════════════════════════════════
# SEND EMAIL
# ════════════════════════════════════════════════════════════════════
def send_email(subject: str, html_body: str):
    print(f"[Email] Sending to {TO_EMAIL}...")
    params = {
        "from":    FROM_EMAIL,
        "to":      [TO_EMAIL],
        "subject": subject,
        "html":    html_body,
    }
    response = resend.Emails.send(params)
    print(f"[Email] Sent! ID: {response['id']}")


# ════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════
def main():
    print(f"\n{'='*60}")
    print(f"  JOB AGENT — {today_str}")
    print(f"{'='*60}\n")

    print("[Stage 1/3] Searching for jobs...")
    job_data = run_agent()

    if not job_data.get("jobs"):
        print(f"[Error] No jobs found. Reason: {job_data.get('error', 'Unknown')}")
        print("[Hint] Check your SERPAPI_KEY and internet connection")
        return

    print(f"[Stage 1/3] Found {len(job_data['jobs'])} matched roles\n")

    print("[Stage 2/3] Formatting email...")
    subject, html = format_html_email(job_data)

    print("[Stage 3/3] Sending email...")
    send_email(subject, html)

    print(f"\n[Done] Job matches delivered to {TO_EMAIL}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print("ERROR:", e)
        traceback.print_exc()
        raise
