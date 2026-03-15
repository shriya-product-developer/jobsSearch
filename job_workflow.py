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
Target roles: Entry level Data Analyst, Business Analyst, Product Analyst
Target cities: Sydney, Melbourne, Brisbane, Perth (Australia)
Key strengths: Data analytics, business intelligence, stakeholder communication,
               Agile methodology, Python/SQL/Power BI
Awards: $15,000 merit scholarship, University of Sydney
"""

today_str = date.today().strftime("%A, %B %d, %Y")

CITIES = [
    {"name": "Sydney",    "seek_location": "Sydney+NSW",        "serp_location": "Sydney, New South Wales, Australia"},
    {"name": "Melbourne", "seek_location": "Melbourne+VIC",     "serp_location": "Melbourne, Victoria, Australia"},
    {"name": "Brisbane",  "seek_location": "Brisbane+QLD",      "serp_location": "Brisbane, Queensland, Australia"},
    {"name": "Perth",     "seek_location": "Perth+WA",          "serp_location": "Perth, Western Australia, Australia"},
]


# ════════════════════════════════════════════════════════════════════
# TOOLS
# ════════════════════════════════════════════════════════════════════
def search_seek(role: str = "data analyst", city: str = "Sydney NSW") -> str:
    """
    Search Seek.com.au for entry level analyst jobs in a given Australian city.
    Returns up to 8 job listings with title, company, URL and description.

    Args:
        role: Job role to search for e.g. 'data analyst', 'business analyst'
        city: Australian city and state e.g. 'Sydney NSW', 'Melbourne VIC',
              'Brisbane QLD', 'Perth WA'
    """
    query    = role.replace(" ", "+")
    location = city.replace(" ", "+")
    headers  = {"User-Agent": "Mozilla/5.0 (JobAgent/1.0)"}

    # Try 1: Seek JSON API
    try:
        url  = f"https://www.seek.com.au/api/chalice-search/v4/search?where={location}&what={query}&worktype=242"
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
                        f"   Location: {job.get('location', city)}\n"
                        f"   URL: https://www.seek.com.au/job/{job.get('id', '')}\n"
                        f"   Posted: {job.get('listingDate', 'Recent')}\n"
                        f"   Summary: {job.get('teaser', 'No description')[:200]}\n"
                    )
                return f"[SEEK — {role.upper()} — {city.upper()}]\n" + "\n".join(lines)
    except Exception as e:
        print(f"  [Seek JSON API failed for {city}: {e}]")

    # Try 2: Seek RSS feed
    try:
        city_slug = city.lower().replace(" ", "-")
        rss_url   = f"https://www.seek.com.au/{role.replace(' ', '-')}-jobs/in-{city_slug}?format=rss"
        resp      = requests.get(rss_url, headers=headers, timeout=10)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "xml" not in content_type and not resp.text.strip().startswith("<"):
            raise ValueError(f"Not XML — got: {resp.text[:100]}")

        root  = ET.fromstring(resp.content)
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
        return f"[SEEK RSS — {role.upper()} — {city.upper()}]\n" + "\n".join(lines)

    except Exception as e:
        print(f"  [Seek RSS failed for {city}: {e}]")

    # Try 3: Scrape Seek search page
    try:
        search_url = f"https://www.seek.com.au/{role.replace(' ', '-')}-jobs/in-{city.lower().replace(' ', '-')}"
        resp       = requests.get(search_url, headers=headers, timeout=10)
        resp.raise_for_status()

        titles    = re.findall(r'data-automation="jobTitle"[^>]*>([^<]+)<', resp.text)
        companies = re.findall(r'data-automation="jobCompany"[^>]*>([^<]+)<', resp.text)
        job_ids   = re.findall(r'data-job-id="(\d+)"', resp.text)

        if not titles:
            return f"No jobs found on Seek for {role} in {city}"

        lines = []
        for i, (title, job_id) in enumerate(zip(titles[:8], job_ids[:8]), 1):
            company = companies[i-1] if i-1 < len(companies) else "N/A"
            lines.append(
                f"{i}. {title}\n"
                f"   Company: {company}\n"
                f"   URL: https://www.seek.com.au/job/{job_id}\n"
            )
        return f"[SEEK — {role.upper()} — {city.upper()}]\n" + "\n".join(lines)

    except Exception as e:
        return f"Error searching Seek for {role} in {city}: {e}"


def search_linkedin(role: str = "data analyst", city: str = "Sydney, New South Wales, Australia") -> str:
    """
    Search LinkedIn Jobs via SerpAPI for analyst roles in a given Australian city.
    Returns up to 8 job listings with title, company, URL and description.

    Args:
        role: Job role to search for e.g. 'data analyst', 'business analyst'
        city: Full city name e.g. 'Sydney, New South Wales, Australia'
    """
    try:
        search = GoogleSearch({
            "engine":   "google_jobs",
            "q":        f"{role} entry level site:linkedin.com/jobs",
            "location": city,
            "api_key":  SERPAPI_KEY,
        })
        results = search.get_dict()
        jobs    = results.get("jobs_results", [])

        if not jobs:
            return f"No LinkedIn results for {role} in {city}"

        lines = []
        for i, job in enumerate(jobs[:8], 1):
            apply_url = job.get("related_links", [{}])[0].get("link", "")
            if not apply_url:
                apply_url = f"https://www.linkedin.com/jobs/search/?keywords={role.replace(' ', '%20')}"

            lines.append(
                f"{i}. {job.get('title', 'N/A')}\n"
                f"   Company: {job.get('company_name', 'N/A')}\n"
                f"   Location: {job.get('location', city)}\n"
                f"   URL: {apply_url}\n"
                f"   Posted: {job.get('detected_extensions', {}).get('posted_at', 'Recent')}\n"
                f"   Summary: {job.get('description', 'No description')[:300]}\n"
            )
        return f"[LINKEDIN — {role.upper()} — {city.upper()}]\n" + "\n".join(lines)

    except Exception as e:
        return f"Error searching LinkedIn for {role} in {city}: {e}"


def search_google_jobs(role: str = "data analyst", city: str = "Sydney, New South Wales, Australia") -> str:
    """
    Search Google Jobs via SerpAPI for analyst roles in a given Australian city.
    Pulls from Indeed, Glassdoor and other boards.
    Returns up to 8 job listings with title, company, URL and description.

    Args:
        role: Job role to search for e.g. 'data analyst', 'business analyst'
        city: Full city name e.g. 'Sydney, New South Wales, Australia'
    """
    try:
        search = GoogleSearch({
            "engine":   "google_jobs",
            "q":        f"{role} entry level",
            "location": city,
            "api_key":  SERPAPI_KEY,
        })
        results = search.get_dict()
        jobs    = results.get("jobs_results", [])

        if not jobs:
            return f"No Google Jobs results for {role} in {city}"

        lines = []
        for i, job in enumerate(jobs[:8], 1):
            apply_url = job.get("related_links", [{}])[0].get("link", "")
            if not apply_url:
                apply_url = f"https://www.google.com/search?q={role.replace(' ', '+')}+jobs+{city.split(',')[0]}"

            lines.append(
                f"{i}. {job.get('title', 'N/A')}\n"
                f"   Company: {job.get('company_name', 'N/A')}\n"
                f"   Location: {job.get('location', city)}\n"
                f"   Via: {job.get('via', 'N/A')}\n"
                f"   URL: {apply_url}\n"
                f"   Posted: {job.get('detected_extensions', {}).get('posted_at', 'Recent')}\n"
                f"   Summary: {job.get('description', 'No description')[:300]}\n"
            )
        return f"[GOOGLE JOBS — {role.upper()} — {city.upper()}]\n" + "\n".join(lines)

    except Exception as e:
        return f"Error searching Google Jobs for {role} in {city}: {e}"


# ════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ════════════════════════════════════════════════════════════════════
SYSTEM_PROMPT = f"""You are a career research agent helping Raghav Malhotra find
entry level analyst jobs across Australia. Today is {today_str}.

Here is Raghav's CV:
{CV_SUMMARY}

Your job:
1. For EACH of these 4 cities — Sydney, Melbourne, Brisbane, Perth — search for
   jobs using all 3 tools: search_seek, search_linkedin, search_google_jobs.
   Search for at least 2 role types per city:
   - "data analyst"
   - "business analyst"

2. For EACH city independently, select the BEST 2-3 jobs using this scoring:
   A) CV Match (0-10): How well does it match Raghav's skills and experience?
   B) Competition (0-10): Score 10 if posted today/yesterday with no applicant
      count. Score lower for "100+ applicants" or postings older than 2 weeks.

   Final score = (CV Match x 0.6) + (Competition x 0.4)
   Pick top 2-3 per city. Prefer jobs posted in the last 3 days.

3. For each selected job write:
   - A 1-line reason why this role fits Raghav's CV
   - Competition assessment: "Low", "Medium", or "High"
   - Competition note: 1 line on why
   - A personalised 5-8 line SOP mentioning the company and city by name,
     referencing Raghav's specific experience

4. Return ONLY a JSON object in this exact structure — one array per city:
{{
  "cities": {{
    "Sydney": {{
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
          "sop": "Dear Hiring Manager at [Company],\\n\\n[5-8 lines]\\n\\nWarm regards,\\nRaghav Malhotra"
        }}
      ],
      "total_reviewed": 10
    }},
    "Melbourne": {{ "jobs": [], "total_reviewed": 0 }},
    "Brisbane":  {{ "jobs": [], "total_reviewed": 0 }},
    "Perth":     {{ "jobs": [], "total_reviewed": 0 }}
  }},
  "total_searches": 12
}}

Return ONLY the JSON. No markdown, no preamble."""


# ════════════════════════════════════════════════════════════════════
# AGENT LOOP
# ════════════════════════════════════════════════════════════════════
def run_agent() -> dict:
    client = genai.Client(api_key=GEMINI_API_KEY)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[search_seek, search_linkedin, search_google_jobs],
    )

    chat     = client.chats.create(model="gemini-2.5-flash", config=config)
    response = chat.send_message(
        "Search for the best entry level analyst jobs for Raghav across "
        "Sydney, Melbourne, Brisbane and Perth. Return top 2-3 per city "
        "with personalised fit reasons and SOPs."
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
                print("[Warning] Gemini returned no JSON")
                return {
                    "cities": {c: {"jobs": [], "total_reviewed": 0} for c in ["Sydney", "Melbourne", "Brisbane", "Perth"]},
                    "total_searches": 0,
                    "error": raw[:500]
                }

        tool_response_parts = []
        for part in tool_calls:
            fn = part.function_call
            print(f"  -> {fn.name}({json.dumps(dict(fn.args))})")

            if fn.name == "search_seek":
                result = search_seek(**fn.args)
            elif fn.name == "search_linkedin":
                result = search_linkedin(**fn.args)
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
    cities_data    = data.get("cities", {})
    total_searches = data.get("total_searches", 0)
    subject        = f"Your Daily Job Matches — {today_str}"

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

    city_colours = {
        "Sydney":    "#534AB7",
        "Melbourne": "#0F6E56",
        "Brisbane":  "#854F0B",
        "Perth":     "#185FA5",
    }

    city_sections = ""
    total_jobs    = 0

    for city_name in ["Sydney", "Melbourne", "Brisbane", "Perth"]:
        city_info     = cities_data.get(city_name, {})
        jobs          = city_info.get("jobs", [])
        total_reviewed = city_info.get("total_reviewed", 0)
        city_color    = city_colours.get(city_name, "#534AB7")
        total_jobs   += len(jobs)

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
            <div style="margin-bottom:24px; padding:20px; background:#fff;
                        border:1px solid #eee; border-radius:10px;">

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

              <h3 style="margin:10px 0 4px; font-size:17px; font-weight:700;
                         color:#1a1a1a; line-height:1.3;">
                {job.get("title", "Analyst Role")}
              </h3>
              <p style="margin:0 0 4px; font-size:13px; color:#555;">
                {job.get("company", "Company")} &nbsp;·&nbsp; {job.get("location", city_name)}
              </p>

              <div style="display:flex; gap:6px; margin:8px 0; flex-wrap:wrap;">
                <span style="font-size:11px; color:#555; background:#f5f5f5;
                             padding:3px 8px; border-radius:6px;">
                  CV match: {cv_score}/10
                </span>
                <span style="font-size:11px; color:#555; background:#f5f5f5;
                             padding:3px 8px; border-radius:6px;">
                  Competition: {comp_score}/10
                </span>
                <span style="font-size:11px; font-weight:600; color:{comp_text};
                             background:{comp_bg}; padding:3px 8px; border-radius:6px;">
                  {competition} competition
                </span>
              </div>

              <p style="margin:0 0 10px; font-size:12px; color:#888;
                        font-style:italic;">{competition_note}</p>

              <div style="margin:10px 0; padding:8px 12px; background:#f0f7ff;
                          border-left:3px solid {city_color}; border-radius:0 6px 6px 0;">
                <p style="margin:0; font-size:12px; color:#334; font-weight:500;">
                  Why this fits you: {job.get("fit_reason", "")}
                </p>
              </div>

              <div style="margin:12px 0; padding:14px; background:#fafafa;
                          border:1px solid #eee; border-radius:8px;">
                <p style="margin:0 0 6px; font-size:11px; font-weight:600;
                          color:#888; letter-spacing:0.5px;">
                  SUGGESTED STATEMENT OF PURPOSE
                </p>
                <p style="margin:0; font-size:12px; color:#333;
                          line-height:1.7;">{sop_html}</p>
              </div>

              <a href="{job.get('url', '#')}"
                 style="display:inline-block; margin-top:4px; padding:8px 20px;
                        background:#1a1a1a; color:#fff; font-size:12px;
                        font-weight:600; text-decoration:none; border-radius:8px;">
                Apply Now
              </a>
            </div>
            """

        no_jobs_msg = ""
        if not jobs:
            no_jobs_msg = """
            <p style="color:#888; font-size:13px; font-style:italic; padding:16px 0;">
              No matching roles found today in this city.
            </p>
            """

        city_sections += f"""
        <div style="margin-bottom:32px;">

          <!-- City header -->
          <div style="background:{city_color}; padding:14px 20px;
                      border-radius:10px 10px 0 0; display:flex;
                      justify-content:space-between; align-items:center;">
            <h2 style="margin:0; color:#fff; font-size:18px;
                       font-weight:700;">{city_name}</h2>
            <span style="color:rgba(255,255,255,0.7); font-size:12px;">
              {len(jobs)} matched · {total_reviewed} reviewed
            </span>
          </div>

          <div style="background:#f9f9f9; padding:16px;
                      border:1px solid #eee; border-top:none;
                      border-radius:0 0 10px 10px;">
            {job_blocks or no_jobs_msg}
          </div>

        </div>
        """

    html = f"""
    <html><body style="margin:0; padding:0; background:#f0f0f0;
                       font-family:-apple-system, BlinkMacSystemFont, sans-serif;">
      <div style="max-width:660px; margin:32px auto;">

        <!-- Main header -->
        <div style="background:#1a1a1a; padding:28px 32px;
                    border-radius:12px 12px 0 0;">
          <p style="margin:0; color:#aaa; font-size:13px;">{today_str}</p>
          <h1 style="margin:6px 0 0; color:#fff; font-size:24px;
                     font-weight:700;">Your Daily Job Matches</h1>
          <p style="margin:6px 0 0; color:#888; font-size:13px;">
            {total_jobs} roles across 4 cities · {total_searches} searches performed
          </p>
          <div style="display:flex; gap:8px; margin-top:12px; flex-wrap:wrap;">
            <span style="background:#534AB7; color:#fff; font-size:11px;
                         padding:3px 10px; border-radius:10px;">Sydney</span>
            <span style="background:#0F6E56; color:#fff; font-size:11px;
                         padding:3px 10px; border-radius:10px;">Melbourne</span>
            <span style="background:#854F0B; color:#fff; font-size:11px;
                         padding:3px 10px; border-radius:10px;">Brisbane</span>
            <span style="background:#185FA5; color:#fff; font-size:11px;
                         padding:3px 10px; border-radius:10px;">Perth</span>
          </div>
        </div>

        <!-- City sections -->
        <div style="padding:24px; background:#f0f0f0;">
          {city_sections}
        </div>

        <!-- Footer -->
        <div style="background:#fff; padding:20px 32px;
                    border-top:1px solid #eee; border-radius:0 0 12px 12px;">
          <p style="margin:0; color:#aaa; font-size:12px;">
            Matched to Raghav's CV automatically · {today_str}<br>
            Sources: Seek, LinkedIn (via SerpAPI), Google Jobs
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

    print("[Stage 1/3] Searching for jobs across 4 cities...")
    job_data = run_agent()

    cities      = job_data.get("cities", {})
    total_found = sum(len(c.get("jobs", [])) for c in cities.values())

    if total_found == 0:
        print(f"[Error] No jobs found. Reason: {job_data.get('error', 'Unknown')}")
        print("[Hint] Check your SERPAPI_KEY and internet connection")
        return

    for city, info in cities.items():
        print(f"  {city}: {len(info.get('jobs', []))} matched roles")

    print(f"\n[Stage 1/3] Found {total_found} total matched roles\n")

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
