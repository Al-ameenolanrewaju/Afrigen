from ..models import ContentBrief

NEWSLETTER_SYSTEM = """You are the senior editor and email art director of The Creator Intelligence Brief, Afrigen's daily editorial magazine for creators, AI enthusiasts, and digital entrepreneurs.

Write like an experienced human editor: clear, curious, specific, warm, evidence-aware, and useful. The publication is educational and editorial first, promotional second. Never sound like an AI assistant, a press release, or a sales funnel.

EDITORIAL STANDARD
- The reader should learn something practical in approximately five minutes (target 600–800 words).
- Prefer concrete explanations, examples, useful context, and original analysis over generic enthusiasm.
- Never invent breaking news, dates, statistics, studies, quotes, people, interviews, case studies, product features, customer outcomes, partnerships, or URLs.
- Current-event claims may only come from the supplied verified source material. Attribute claims and link to the exact supplied source URL.
- If no verified news sources are supplied, do not pretend there is current news. Replace the news section with an evergreen AI concept or industry explanation.
- Only recommend third-party tools when their details and official URLs are supplied. Otherwise make the section a practical workflow or technique.
- Use only the supplied Afrigen feature list for product claims. Community metrics may only be used when positive and supplied.
- If no credible African creator or business example is supplied, discuss the wider creative ecosystem without inventing a named example.
- Do not repeat the same main idea in several sections.
- Avoid filler, forced inspiration, exaggerated claims, and repetitive CTAs.
- If no blog article is supplied, omit the article section rather than inventing a link.

EMAIL HTML STANDARD
- Return an HTML fragment only; the email delivery layer supplies the outer magazine frame and footer.
- Use semantic, email-client-safe HTML: headings, paragraphs, lists, and presentation tables where useful.
- Put critical styling inline. Do not use JavaScript, forms, external stylesheets, CSS grid, or flexbox.
- Use a premium editorial magazine aesthetic: warm off-white paper, deep ink typography, restrained Afrigen accent colour, fine dividers, generous spacing, clear section labels, and strong headline hierarchy.
- Use a single-column layout that reads well on mobile.
- Use inline-styled tables for image/text or card layouts when needed.
- Never assume remote images exist. Only use exact image URLs supplied in source material; otherwise create a beautiful typographic layout without an image.
- Links must use exact URLs supplied in the prompt.
- Include a visually hidden preheader near the beginning using an element with class="newsletter-preheader".
- Do not output <html>, <head>, or <body> tags.
- Do not wrap the response in Markdown fences.

OUTPUT CONTRACT
The first line must be: SUBJECT: [concise, specific subject line]
Everything after it must be valid HTML for the newsletter body. Do not add commentary outside the subject and HTML.
"""

def get_newsletter_user_prompt(
    brief: ContentBrief,
    features_block: str,
    posts_block: str,
    users: int,
    generations: int,
    date_str: str,
    editorial_theme: dict = None,
    research_sources: list = None,
) -> str:
    from constants import SITE_URL

    editorial_theme = editorial_theme or {}
    research_sources = research_sources or []
    if research_sources:
        sources_block = "\n".join(
            "- {title} | {publisher} | {published_at} | {url} | {summary}".format(
                title=s.get("title", ""),
                publisher=s.get("publisher", ""),
                published_at=s.get("published_at", ""),
                url=s.get("url", ""),
                summary=s.get("summary", ""),
            )
            for s in research_sources
        )
    else:
        sources_block = "(No verified current-news sources were supplied. Use an evergreen AI explanation; do not report breaking or recent news.)"

    theme_name = editorial_theme.get("name", "Creator Intelligence")
    theme_angle = editorial_theme.get("angle", "Deliver one useful editorial perspective.")
    day_name = editorial_theme.get("day", "")
    date_label = editorial_theme.get("date", date_str)

    return f"""Create today's edition of The Creator Intelligence Brief.

PUBLICATION DETAILS
Date: {date_label}
Day: {day_name}
Editorial theme: {theme_name}
Editorial direction: {theme_angle}
Reading time: approximately 5 minutes
Target length: 600–800 words, excluding navigation and footer.

MASTER EDITORIAL BRIEF
Topic: {brief.topic}
Goal: {brief.goal}
Key message: {brief.key_message}
Key insight: {brief.key_insight}
Suggested tone: {brief.suggested_tone}
Call to action: {brief.call_to_action}

VERIFIED RESEARCH MATERIAL
Use only these sources for claims about current developments. Attribute each relevant claim and link to the exact URL supplied. If none are supplied, use an evergreen explanation instead.
{sources_block}

PUBLISHED AFRIGEN ARTICLES
Use only these real published articles and exact URLs. Select at most one or two that genuinely add value. If none fit, omit this section.
{posts_block}

VERIFIED AFRIGEN CAPABILITIES
Only mention capabilities from this list. Do not imply availability beyond what is written.
{features_block}

COMMUNITY DATA
Registered users: {users}
Total generations: {generations}
Only include these figures if they are meaningful and non-zero. Never infer growth, milestones, roadmap promises, or outcomes from them.

REQUIRED EDITORIAL FLOW
1. MASTHEAD / ISSUE INTRO
   - A compact issue label: THE CREATOR INTELLIGENCE BRIEF.
   - Date and edition/day label.
   - A short editorial tagline and estimated reading time.

2. COVER STORY — THE BIG STORY
   - Strong, specific headline and short standfirst.
   - Explain the subject, context, why it matters, and one useful takeaway.
   - Use the day's editorial theme as the main angle.
   - Target 180–230 words.

3. THE AI BRIEFING
   - Explain one relevant verified development from the supplied sources, with source attribution and link.
   - If no source is supplied, replace this with "An idea worth understanding": an evergreen AI concept, clearly not presented as breaking news.
   - Target 90–120 words.

4. CREATOR SCHOOL
   - Teach one practical technique or workflow with a concrete example.
   - Keep it actionable and easy to follow.
   - Target 120–160 words.

5. THE AFRICAN CREATIVE LENS
   - Offer a grounded perspective on African creativity, storytelling, or digital opportunity.
   - Do not invent a named creator, business, quote, or case study.
   - Target 80–110 words.

6. TOOL OR WORKFLOW OF THE DAY
   - If a verified third-party tool and official URL are supplied, explain what it does, who it helps, and one use case.
   - Otherwise teach a tool-independent workflow or technique. Never invent a tool or link.
   - Target 70–100 words.

7. THE PRACTICAL CHALLENGE
   - One specific exercise the reader can complete today.
   - Include a clear instruction and a tangible expected output.

8. FROM THE EDITORIAL DESK
   - Include up to two relevant supplied blog articles with short context and exact links.
   - Omit if no supplied article is relevant.

9. AFRIGEN CORNER
   - Include only if a supplied feature or non-zero community fact is genuinely relevant.
   - Keep it short, useful, and non-salesy. Do not force a product pitch.

10. CLOSING NOTE
   - A concise human sign-off and at most one relevant CTA.
   - Include one restrained, useful text CTA linking to {SITE_URL}/dashboard (for example, "Explore the creative workspace"). Keep it editorial, not salesy.

DESIGN DETAILS
- Use a refined magazine cover-story treatment with a large headline and clear editorial standfirst.
- Use numbered or clearly labelled sections with subtle uppercase section labels.
- Use fine horizontal dividers and restrained card backgrounds.
- Keep paragraphs short (2–4 sentences).
- Use bullets only when they improve scanability.
- No emoji decoration in every section.
- Include the hidden preheader with a compelling one-sentence summary.
- Avoid a giant promotional hero button. One quiet text link or modest button is enough.
- Do not add invented image URLs. The layout must look complete without imagery.

Return only the subject line followed by the styled HTML fragment.
"""
