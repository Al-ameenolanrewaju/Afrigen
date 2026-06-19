"""
Blog content + storage for Afrigen.

Posts now live in the database (models.BlogPost) so they are reachable from BOTH
the Render web service AND the Render cron job that generates drafts — a file in
the repo would not be (the two Render services don't share a filesystem).

SEED_POSTS below are the original 6 hand-written articles. seed_blog_posts()
inserts them once, as status='published', so the database is the single source of
truth. Public pages only ever render status='published'; drafts are invisible to
the public, search engines, and the sitemap until an admin approves them.

Each post's `body` is trusted HTML matching the site's design system (gold
#F5A623 headings, #C9D1D9 body text, .card containers), rendered with `| safe`.
"""
import os
import json
import re
from datetime import datetime
from xml.etree import ElementTree

import requests


# Original hand-written posts. Seeded once into the DB as published; the DB is
# the source of truth afterward. Each: slug, title, description (<=160 chars),
# date (display, parsed into published_at on seed), read_time, tag, body (HTML).
SEED_POSTS = [
    {
        "slug": "write-better-prompts-afrigen-ai-refiner",
        "title": "How to Write Better Prompts for Afrigen's AI Refiner",
        "description": "Practical prompt-writing techniques for Afrigen's AI refiner — structure, specificity, and the small details that turn a flat clip into a striking one.",
        "date": "June 2, 2026",
        "read_time": "6 min read",
        "tag": "Prompting",
        "body": """
<p style="color: #C9D1D9; margin-bottom: 16px;">The AI refiner is the single biggest lever you have over your final video, and most creators barely touch it. They type three words, hit generate, and then wonder why the result looks nothing like what was in their head. The refiner can only expand on what you give it. Feed it a vague idea and it fills the gaps with generic choices. Feed it a clear one and it amplifies your intent. This guide walks through how to write prompts that actually get you the video you imagined.</p>

<h4 style="color: #F5A623;">Start with the four anchors</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Every strong prompt answers four questions before anything else: <strong>who</strong> is in the shot, <strong>where</strong> they are, <strong>what</strong> they are doing, and <strong>how</strong> it should feel. "A trader" is weak. "A young woman selling fresh tomatoes at a busy Balogun Market stall, calling out to customers, warm and energetic" gives the refiner four solid anchors to build on. You do not need to write a paragraph yourself — that is the refiner's job — but you must supply the raw direction.</p>

<h4 style="color: #F5A623;">Be specific about place</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Generic locations produce generic footage. "A city street" could be anywhere on earth, so the model defaults to a bland, placeless look. Name the actual place: Lagos Island at rush hour, a quiet street in old Kano, a beach bar in Tarkwa Bay, the red earth of a village road in the southeast. Specific places carry specific light, architecture, and texture, and the refiner knows how to describe them.</p>

<h4 style="color: #F5A623;">Direct the camera, not just the scene</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">A scene description tells the model what exists. A camera direction tells it how to show that to a viewer, and that is where footage starts to feel professional. Add one camera instruction per prompt: a slow push-in on a face, a tracking shot following someone as they walk, a low angle looking up to make a subject feel powerful, a handheld feel for energy. One clear camera move beats five adjectives.</p>

<div class="p-3 mb-3" style="background: #21262D; border-radius: 8px; border-left: 3px solid #F5A623;">
    <p style="color: #888; margin: 0 0 6px;">Weak prompt:</p>
    <p style="color: #C9D1D9; margin: 0 0 14px;">"Man cooking jollof rice"</p>
    <p style="color: #888; margin: 0 0 6px;">Stronger prompt (before the refiner even touches it):</p>
    <p style="color: #C9D1D9; margin: 0;">"Close-up, slow push-in on a smiling Nigerian chef stirring a big pot of smoky party jollof over an open flame at dusk, steam rising, golden firelight on his face, warm and celebratory"</p>
</div>

<h4 style="color: #F5A623;">Control the mood with light and time</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Lighting is the cheapest way to change how a clip feels. Golden hour reads warm and aspirational. Overcast feels honest and documentary. Neon night feels modern and urban. Harsh midday sun feels raw and real. Pick the time of day on purpose — "golden hour" and "blue hour just after sunset" will pull completely different emotions out of the same scene.</p>

<h4 style="color: #F5A623;">Pick one subject and commit</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">A common mistake is cramming a whole story into one clip: "a man wakes up, drives to work, meets his team, closes a deal." AI video models work in short single moments, not montages. If you ask for four things you will usually get a confused blur of all four. Choose the single strongest moment and describe it richly. If you need the full story, generate each beat as its own clip and stitch them later.</p>

<h4 style="color: #F5A623;">Use the refiner's output as a draft, not gospel</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">When the refiner expands your idea, read it before you generate. It is a draft you can edit. If it added "snow" to your Lagos scene or made your market quiet when you wanted it loud, fix that line and regenerate. The refiner is fast and free to run — treat it as a back-and-forth, not a vending machine.</p>

<h4 style="color: #F5A623;">A quick checklist before you hit generate</h4>
<ul style="color: #C9D1D9; margin-bottom: 16px;">
    <li>Did I name a real, specific location?</li>
    <li>Is there exactly one main subject and one main action?</li>
    <li>Did I give one camera direction?</li>
    <li>Did I set a time of day or lighting mood?</li>
    <li>Did I describe the feeling I want in one or two words?</li>
</ul>

<p style="color: #C9D1D9; margin-bottom: 16px;">Run through those five points and your hit rate climbs immediately. Better prompts mean fewer wasted credits, fewer regenerations, and footage that actually looks like the idea you started with. The model is powerful — your job is simply to point it in the right direction.</p>
""",
    },
    {
        "slug": "ai-video-small-nigerian-businesses-guide",
        "title": "A Practical Guide to AI Video for Small Nigerian Businesses",
        "description": "How small Nigerian businesses can use AI video to advertise without a camera crew or big budget — from product clips to promos that actually sell.",
        "date": "May 28, 2026",
        "read_time": "7 min read",
        "tag": "Business",
        "body": """
<p style="color: #C9D1D9; margin-bottom: 16px;">If you run a small business in Nigeria — a thrift store on Instagram, a small restaurant, a skincare line, a logistics startup — you already know video sells better than photos. The problem has always been cost. Hiring a videographer, renting gear, paying for editing, and waiting a week for delivery is out of reach for most small operators. AI video changes that maths. You can now produce a usable promo clip from your phone in minutes. Here is how to actually use it well.</p>

<h4 style="color: #F5A623;">Start with what you are selling, not what looks cool</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">It is tempting to generate flashy footage just because you can. Resist it. Before you type a single prompt, decide the one thing you want the viewer to do: visit your shop, send a DM, click a link, save the post. Every clip should serve that action. A boutique owner does not need a sci-fi city — she needs a clip that makes her clothes look desirable and tells people where to buy.</p>

<h4 style="color: #F5A623;">Three video types that work for small businesses</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;"><strong>The mood clip.</strong> A short, beautiful scene that sets the feeling of your brand — a steaming plate of food, soft morning light through a salon window, a model walking confidently in your outfit. You overlay your logo and a line of text. This is the easiest win and works as a Story, a Reel intro, or a WhatsApp status.</p>
<p style="color: #C9D1D9; margin-bottom: 16px;"><strong>The product hero.</strong> One product, beautifully lit, presented like a premium advert. AI is excellent at making everyday products look high-end. Generate a clean, cinematic shot, then add your price and a "DM to order" caption.</p>
<p style="color: #C9D1D9; margin-bottom: 16px;"><strong>The concept ad.</strong> A short narrative moment that sells a feeling — a tired worker relaxing after using your product, a family enjoying a meal, a customer's reaction. These build emotional connection and stop the scroll.</p>

<h4 style="color: #F5A623;">Keep your brand consistent</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">The fastest way to look amateur is to post clips that all feel different. Pick a lane and stay in it. Decide on a consistent mood (warm and homely, sleek and modern, bold and colourful), a consistent time of day, and a consistent on-screen text style. When every clip shares a visual language, even AI-generated content starts to feel like a real brand.</p>

<div class="p-3 mb-3" style="background: #21262D; border-radius: 8px; border-left: 3px solid #F5A623;">
    <p style="color: #C9D1D9; margin: 0;">💡 <strong style="color: #F5A623;">Tip:</strong> Make a "brand prompt" — a saved sentence you reuse describing your look (e.g. "warm golden lighting, soft focus, premium lifestyle feel"). Append it to every prompt so all your clips feel related.</p>
</div>

<h4 style="color: #F5A623;">Format for where it will be seen</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Most Nigerian small-business traffic comes from Instagram, TikTok, and WhatsApp — all vertical-first. Generate in 9:16 so your clip fills the phone screen instead of sitting in a small box. A vertical clip looks native and gets more reach than a landscape one squeezed into a Story.</p>

<h4 style="color: #F5A623;">Add the words on screen</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Most people watch with the sound off, especially while scrolling at work or in traffic. Your offer needs to be readable without audio. Put your key message — the product name, the price, the discount, the call to action — directly on the video as text. A gorgeous clip with no message is just decoration; a clip with one clear line of text is an advert.</p>

<h4 style="color: #F5A623;">Post consistently, not perfectly</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Because AI video is cheap and fast, you can afford to post often. That is the real advantage. A small business that posts three decent clips a week will almost always beat one that posts a single "perfect" video a month. Use the speed. Test different hooks, different products, different moods, and double down on whatever your audience responds to.</p>

<h4 style="color: #F5A623;">A simple weekly routine</h4>
<ul style="color: #C9D1D9; margin-bottom: 16px;">
    <li><strong>Monday:</strong> a product hero clip with price and order info.</li>
    <li><strong>Wednesday:</strong> a mood or lifestyle clip that builds the brand feeling.</li>
    <li><strong>Friday:</strong> an offer or testimonial-style concept clip to drive weekend sales.</li>
</ul>

<p style="color: #C9D1D9; margin-bottom: 16px;">You do not need a studio, a crew, or a big budget anymore — you need a clear message and the discipline to show up. AI video removes the production barrier; the rest is good old-fashioned marketing sense, and that part you already have.</p>
""",
    },
    {
        "slug": "tiktok-instagram-youtube-formatting-differences",
        "title": "TikTok vs Instagram vs YouTube: Formatting Your AI Videos Right",
        "description": "Aspect ratios, lengths, hooks and captions that work on TikTok, Instagram Reels and YouTube Shorts — so your AI clips perform on each platform.",
        "date": "May 21, 2026",
        "read_time": "6 min read",
        "tag": "Platforms",
        "body": """
<p style="color: #C9D1D9; margin-bottom: 16px;">The same clip can flop on one platform and fly on another, and the difference often has nothing to do with quality. It is formatting. TikTok, Instagram Reels, and YouTube each reward slightly different shapes, lengths, and pacing. If you understand those differences before you generate, you can tailor your AI video to each one and stop leaving reach on the table.</p>

<h4 style="color: #F5A623;">Aspect ratio: go vertical, but mind the safe zone</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">All three platforms are vertical-first, so 9:16 is your default for TikTok, Reels, and YouTube Shorts. The catch is the "safe zone." Each app stacks its own buttons, captions, and username over your video. On TikTok and Reels, the right side and bottom are crowded with icons. When you plan on-screen text, keep it in the middle of the frame so the platform's UI does not cover your message. For long-form YouTube, switch to 16:9 — Shorts and full uploads are two different games.</p>

<h4 style="color: #F5A623;">Length: match the platform's patience</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;"><strong>TikTok</strong> rewards short and punchy. The strongest-performing clips often run well under 15 seconds and loop seamlessly, so the viewer watches twice without realising. <strong>Instagram Reels</strong> tolerates slightly longer, but the first three seconds still decide everything. <strong>YouTube Shorts</strong> behaves like TikTok, while regular YouTube viewers will sit through longer, more developed pieces. For AI clips, that means: cut tight for TikTok and Reels, and consider stitching several clips into a longer edit for YouTube proper.</p>

<h4 style="color: #F5A623;">The hook is platform-specific</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">On TikTok, motion and surprise in the first second win — something needs to move, change, or grab attention instantly. On Reels, a polished, aspirational opening frame tends to do well because the audience leans more lifestyle and aesthetic. On YouTube, viewers often arrive from a title and thumbnail, so they have already decided to give you a few seconds — you can open a little slower and set up a story. Generate your opening frame with the platform in mind: arresting for TikTok, beautiful for Reels, intriguing for YouTube.</p>

<div class="p-3 mb-3" style="background: #21262D; border-radius: 8px; border-left: 3px solid #F5A623;">
    <p style="color: #C9D1D9; margin: 0;">📌 <strong style="color: #F5A623;">Quick reference:</strong> TikTok &amp; Shorts → 9:16, under ~15s, instant motion hook. Reels → 9:16, polished opener, text kept centre. YouTube long-form → 16:9, longer edits, slower setup allowed.</p>
</div>

<h4 style="color: #F5A623;">Captions and text overlays</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">TikTok culture loves bold, punchy on-screen captions that drive the narration. Reels favours cleaner, more minimal text that does not clutter a pretty frame. YouTube viewers expect clear titles and often watch with sound on, so you can rely more on audio. Whatever the platform, never bury your message at the very bottom of the frame where the app's caption bar lives.</p>

<h4 style="color: #F5A623;">Sound matters differently on each</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">TikTok is built around trending audio — using a sound that is currently popular can give an ordinary clip a real boost. Reels shares much of that culture but also rewards original audio for brand content. YouTube viewers are far more likely to have sound on and to value clear voiceover or music that fits. If you add a voiceover to your AI clip, a YouTube audience will actually hear it; a muted TikTok scroller may not, so keep the visual message self-sufficient.</p>

<h4 style="color: #F5A623;">One idea, three exports</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">The efficient move is to generate one strong core clip and adapt it three ways. Cut a tight, motion-led version for TikTok. Make a cleaner, prettier version with subtle centred text for Reels. Build a longer, more developed edit — perhaps stitching several clips with a voiceover — for YouTube. You are not making three separate videos from scratch; you are re-formatting one good idea to fit three different rooms.</p>

<h4 style="color: #F5A623;">Test, then trust the data</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Formatting rules are a starting point, not a law. Every audience is a little different. Post the same idea across all three, watch which version holds attention longest, and let real numbers guide your next batch. Over a few weeks you will learn exactly what your specific followers reward — and that knowledge is worth more than any general guide.</p>
""",
    },
    {
        "slug": "ai-vs-traditional-video-ads-cost-naira",
        "title": "AI vs Traditional Video Ads in Nigeria: The Real Naira Cost",
        "description": "A clear-eyed Naira cost comparison of AI-generated video ads versus traditional shoots in Nigeria — gear, crew, time, and where each one actually wins.",
        "date": "May 14, 2026",
        "read_time": "7 min read",
        "tag": "Cost",
        "body": """
<p style="color: #C9D1D9; margin-bottom: 16px;">"How much will a video ad cost me?" is the first question every Nigerian business owner asks, and the answer used to be discouraging. Traditional production carries real, stacking costs. AI video collapses most of them. But the honest comparison is not "AI is cheap, traditional is expensive" — it is about understanding where each rand of your budget actually goes, and where each approach genuinely earns its keep.</p>

<h4 style="color: #F5A623;">What a traditional shoot actually costs</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">A modest professional video shoot in Lagos or Abuja is rarely a single fee. You are paying for several things at once:</p>
<ul style="color: #C9D1D9; margin-bottom: 16px;">
    <li><strong>Videographer / crew</strong> — often the largest line item, charged per day.</li>
    <li><strong>Equipment</strong> — camera, lighting, audio gear, either owned or rented.</li>
    <li><strong>Location</strong> — studio hire or permission to shoot somewhere good.</li>
    <li><strong>Talent</strong> — models or actors, plus styling and wardrobe.</li>
    <li><strong>Editing</strong> — colour, sound, graphics, usually billed separately.</li>
    <li><strong>Time</strong> — days of planning, a shoot day, then days of post-production.</li>
</ul>
<p style="color: #C9D1D9; margin-bottom: 16px;">Stack those together and even a "simple" promo for a small brand quickly runs into six figures of Naira, with a turnaround measured in weeks. For a large brand launching a flagship campaign, that investment is justified. For a boutique that needs fresh content every week, it is simply not sustainable.</p>

<h4 style="color: #F5A623;">What AI video actually costs</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">With AI generation, almost all of those line items disappear. There is no crew, no gear rental, no location fee, no shoot day. Your cost is effectively a small per-clip or subscription charge plus your own time writing prompts and adding text. A business owner can produce a polished vertical ad for a few hundred Naira's worth of credits and a few minutes of effort, then make ten variations before lunch. The cost per usable clip drops by an order of magnitude, and the turnaround goes from weeks to minutes.</p>

<div class="p-3 mb-3" style="background: #21262D; border-radius: 8px; border-left: 3px solid #F5A623;">
    <p style="color: #C9D1D9; margin: 0;">💡 The real saving is not just money — it is <strong style="color: #F5A623;">iteration speed</strong>. Traditional video gives you one expensive clip. AI gives you twenty cheap attempts, so you can find what works instead of betting everything on one shoot.</p>
</div>

<h4 style="color: #F5A623;">Where traditional video still wins</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">AI is not a total replacement, and pretending otherwise will burn you. Traditional shoots still win when you need a <strong>specific real person</strong> — a founder's face, a named brand ambassador, a real customer testimonial. They win when you need to show your <strong>actual product in someone's hands</strong> with perfect accuracy, or when a campaign demands a level of bespoke art direction that only a human crew can guarantee. For trust-heavy, identity-heavy content, real footage carries weight that generated footage does not.</p>

<h4 style="color: #F5A623;">Where AI clearly wins</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">AI dominates on volume, speed, and concept work. Mood clips, atmospheric backgrounds, lifestyle scenes, abstract product heroes, social-media filler that needs to be fresh weekly — this is exactly where AI shines and where paying a crew makes no economic sense. If your goal is to stay visible and post consistently without going broke, AI is the obvious tool.</p>

<h4 style="color: #F5A623;">The smart play: blend the two</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">The businesses getting the best return are not choosing one or the other. They shoot real footage once or twice a year for the high-stakes pieces — the brand film, the founder story, the hero campaign — and then use AI video for the constant weekly drumbeat of social content that keeps them top of mind in between. The expensive shoot builds trust; the cheap AI clips maintain presence. Together they cost a fraction of trying to do everything traditionally.</p>

<h4 style="color: #F5A623;">Do the maths for your own situation</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Before you spend, ask one question: how many pieces of video do I need this month, and how unique must each one be? If the answer is "one important film," pay for a real shoot. If it is "twelve fresh clips to feed my socials," AI will save you a fortune and a great deal of stress. Match the tool to the job, and your marketing budget suddenly stretches a lot further.</p>
""",
    },
    {
        "slug": "make-ai-video-authentically-african",
        "title": "How to Make AI Video Look Authentically African, Not Generic",
        "description": "Concrete prompt techniques to make AI video feel genuinely African — real places, textures, light and detail instead of a vague global aesthetic.",
        "date": "May 7, 2026",
        "read_time": "7 min read",
        "tag": "Craft",
        "body": """
<p style="color: #C9D1D9; margin-bottom: 16px;">Most AI video models were trained on the wider internet, which means their default idea of "a person," "a street," or "a market" tends to look vaguely Western and placeless. Left to its own devices, the model gives you something generic. If you want footage that genuinely feels like home — like Lagos, like Accra, like a village in the east — you have to direct it there deliberately. Here is how to make AI video read as authentically African instead of generic stock.</p>

<h4 style="color: #F5A623;">Name the place, not just the continent</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">"Africa" is too broad to be useful, and "an African city" still produces a vague mash-up. Specificity is everything. Lagos Island looks nothing like northern Kano; a Calabar street looks nothing like Jos. Name the actual location and the model pulls in the right architecture, density, and atmosphere. "A busy danfo bus stop in Oshodi at rush hour" carries a hundred details that "an African street" never will.</p>

<h4 style="color: #F5A623;">Get the light right</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">The quality of light is one of the most recognisable things about a place. The harsh, bright West African sun, the warm orange haze of the harmattan, the heavy gold of late afternoon before a rainstorm — these read instantly as home to anyone who lives here. Specify them. "Hazy harmattan morning light" or "intense midday tropical sun with deep shadows" instantly grounds a scene in the region in a way that generic "good lighting" cannot.</p>

<h4 style="color: #F5A623;">Use texture and the real details of daily life</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Authenticity lives in the small stuff. Red laterite earth on a village road. Rusted zinc roofs catching the sun. Hand-painted shop signs. Stacked jerry cans and woven baskets at a market. Ankara and adire fabric. A cooler of cold drinks, a wheelbarrow, a generator humming outside a shop. When you name these textures in your prompt, the model stops giving you a clean, anonymous set and starts giving you a place that feels lived-in and real.</p>

<div class="p-3 mb-3" style="background: #21262D; border-radius: 8px; border-left: 3px solid #F5A623;">
    <p style="color: #C9D1D9; margin: 0;">💡 <strong style="color: #F5A623;">Detail beats adjectives.</strong> "Authentic African market" is weak. "A bustling open-air market with wooden stalls, baskets of tomatoes and peppers, women in colourful Ankara, hand-painted signs, dust in the afternoon light" is what actually makes it feel real.</p>
</div>

<h4 style="color: #F5A623;">Describe people with care and dignity</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">How you describe people shapes how they appear, so be intentional and respectful. Specify clothing that fits the scene — agbada, kaftan, a sharp office shirt, a market trader's wrapper — rather than leaving it to the model's default. Aim for natural dignity and confidence; you are representing your audience, and they should look like the real, varied, stylish people you see every day, not a flat stereotype. Specifying age, role, and dress gets you a believable person instead of a generic placeholder.</p>

<h4 style="color: #F5A623;">Avoid the "safari" trap</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">There is a tired, narrow version of "Africa" that AI tends to default to: sunsets, wildlife, dusty plains, and little else. Real African life is overwhelmingly urban, modern, fast, and varied — tech hubs, busy markets, sleek offices, nightlife, street food, traffic. Unless you specifically want a rural or wildlife scene, steer the model toward the contemporary reality your audience actually lives in. Mention modern buildings, smartphones, cars, city energy. Show the Africa your viewers recognise from their own window, not a postcard.</p>

<h4 style="color: #F5A623;">Build a reusable "authenticity" prompt</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Once you find a combination of place, light, and texture words that consistently produces the look you want, save it. Keep a short phrase you can append to any prompt — something like "warm West African afternoon light, real urban detail, colourful local fabrics, lived-in textures." Reusing it keeps your whole feed visually consistent and reliably grounded in place, so every clip feels like part of the same authentic world.</p>

<h4 style="color: #F5A623;">Why it matters</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Audiences can feel the difference between content made for them and content that merely tolerates them. When your videos genuinely look and feel like the places your viewers know, they trust you more, share more, and remember you. Generic footage gets scrolled past. Footage that feels like home gets watched twice — and that is the whole point.</p>
""",
    },
    {
        "slug": "one-ai-video-into-a-week-of-content",
        "title": "Turn One AI Video Into a Week of Content for Your Brand",
        "description": "A repurposing system for Nigerian creators: how to stretch a single AI-generated clip into a full week of posts across every platform.",
        "date": "April 30, 2026",
        "read_time": "6 min read",
        "tag": "Strategy",
        "body": """
<p style="color: #C9D1D9; margin-bottom: 16px;">The hardest part of growing online is not making content — it is making <em>enough</em> of it, consistently, without burning out. Most creators run dry because they treat every post as a fresh project. The professionals do the opposite: they create one strong asset and squeeze a week of content out of it. Here is a simple system for turning a single AI-generated video into seven days of posts.</p>

<h4 style="color: #F5A623;">Start with one strong "hero" clip</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Everything begins with one well-made video — your hero. Put your effort here. Write a careful prompt, refine it, pick a clip that genuinely looks good and clearly communicates your brand or message. This is the asset you will reshape all week, so it is worth getting right. One excellent clip beats seven rushed ones every time.</p>

<h4 style="color: #F5A623;">Day 1 — Post the hero, full strength</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Lead with your best foot forward. Post the hero clip as a vertical Reel or TikTok with a strong on-screen hook and a clear caption. This is your anchor post — the one you will reference and build on for the rest of the week.</p>

<h4 style="color: #F5A623;">Day 2 — The behind-the-idea post</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Reuse the same clip but change the framing. Talk about the idea behind it — why you made it, what it is for, what problem your product solves. Same visuals, completely different message. People who scrolled past the first post will stop for the story.</p>

<h4 style="color: #F5A623;">Day 3 — Cut a shorter version</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Trim the hero down to its punchiest few seconds and post it as a fast, loopable clip optimised for TikTok or Shorts. Add a different hook line. Short cuts often outperform the full version because they are easier to watch all the way through, which the algorithm rewards.</p>

<div class="p-3 mb-3" style="background: #21262D; border-radius: 8px; border-left: 3px solid #F5A623;">
    <p style="color: #C9D1D9; margin: 0;">💡 <strong style="color: #F5A623;">One asset, many angles.</strong> The clip does not change much — the <em>caption, hook, and crop</em> do. Each variation reaches people the previous one missed.</p>
</div>

<h4 style="color: #F5A623;">Day 4 — Generate a sibling clip</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Now make a close cousin of your hero. Keep the same style, lighting, and mood — reuse your brand prompt — but change the scene or subject slightly. Because it shares a visual language with day one, it reinforces your brand identity while still feeling new. This is where AI's speed pays off: a matching clip takes minutes.</p>

<h4 style="color: #F5A623;">Day 5 — Turn it into a still or carousel</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Pull a striking frame from your video and use it as a static post or the cover of a carousel. Pair it with a longer written caption — a tip, a list, a short story. Not every follower watches video; a strong still with good words reaches the readers in your audience.</p>

<h4 style="color: #F5A623;">Day 6 — Add a question or poll</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Repost the clip as a Story with an interactive sticker — a poll, a question box, a "which do you prefer" prompt. Engagement signals tell the platform your content is worth showing, and the replies give you free ideas for next week's hero clip.</p>

<h4 style="color: #F5A623;">Day 7 — Stitch the week into a recap</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Combine your hero and sibling clips into one slightly longer edit, add a simple voiceover or music, and post it as a "this week" recap or a longer YouTube Short. You have now closed the loop: a single idea has produced seven distinct touchpoints across the week.</p>

<h4 style="color: #F5A623;">Why this works</h4>
<p style="color: #C9D1D9; margin-bottom: 16px;">Consistency, not volume of original ideas, is what grows an audience. By building a repeatable system around one strong asset, you stay visible every day without the daily pressure of inventing something from scratch. AI video makes the raw material cheap; this system makes it go far. Set it up once, run it every week, and showing up consistently stops feeling impossible.</p>
""",
    },
]


# ---------- Slugs ----------

def slugify(title):
    """Turn a title into a URL-safe slug: lowercase, hyphenated, alnum only."""
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return slug or "post"


def unique_slug(title):
    """A slug for `title` that does not collide with any existing post (draft or
    published). Appends -2, -3, ... if needed."""
    from models import BlogPost
    base = slugify(title)
    slug = base
    n = 2
    while BlogPost.query.filter_by(slug=slug).first() is not None:
        slug = f"{base}-{n}"
        n += 1
    return slug


# ---------- Public reads (PUBLISHED ONLY) ----------

def get_all_posts():
    """Published posts only, newest first. Used by the public /blog index."""
    from models import BlogPost
    return (
        BlogPost.query
        .filter_by(status="published")
        .order_by(BlogPost.published_at.desc().nullslast(), BlogPost.created_at.desc())
        .all()
    )


def get_post(slug):
    """A single PUBLISHED post by slug, or None. Drafts are never returned here,
    so they 404 for the public exactly like a non-existent post."""
    from models import BlogPost
    return BlogPost.query.filter_by(slug=slug, status="published").first()


# ---------- Admin / script helpers ----------

def get_drafts():
    """All pending drafts, newest first (for the /admin/blog review page)."""
    from models import BlogPost
    return (
        BlogPost.query
        .filter_by(status="draft")
        .order_by(BlogPost.created_at.desc())
        .all()
    )


def get_post_by_id(post_id):
    """A post by primary key, any status (admin actions)."""
    from models import db, BlogPost
    return db.session.get(BlogPost, post_id)


def existing_titles_and_slugs():
    """Every title and slug already in the DB (draft AND published) so the
    generator never repeats a topic. Returns (titles, slugs)."""
    from models import db, BlogPost
    rows = db.session.query(BlogPost.title, BlogPost.slug).all()
    titles = [t for (t, _s) in rows]
    slugs = [s for (_t, s) in rows]
    return titles, slugs


def create_draft(title, description, body, tag="", read_time="", auto_generated=True):
    """Insert a new post as status='draft'. Never publishes."""
    from models import db, BlogPost
    post = BlogPost(
        slug=unique_slug(title),
        title=title or "Untitled",
        description=(description or "")[:320],
        body=body or "",
        tag=tag or "",
        read_time=read_time or "",
        status="draft",
        auto_generated=auto_generated,
    )
    db.session.add(post)
    db.session.commit()
    return post


def publish_post(post):
    """Approve a draft: mark published and stamp published_at."""
    from models import db
    post.status = "published"
    post.published_at = datetime.utcnow()
    db.session.commit()
    return post


def discard_post(post):
    """Discard a draft by deleting the row."""
    from models import db
    db.session.delete(post)
    db.session.commit()


# ---------- One-time seed of the original 6 posts ----------

def seed_blog_posts():
    """Insert SEED_POSTS as published if they aren't already present. Idempotent:
    safe to call on every startup. Matches on slug."""
    from models import db, BlogPost
    inserted = 0
    for sp in SEED_POSTS:
        if BlogPost.query.filter_by(slug=sp["slug"]).first() is not None:
            continue
        try:
            published_at = datetime.strptime(sp["date"], "%B %d, %Y")
        except (ValueError, KeyError):
            published_at = datetime.utcnow()
        db.session.add(BlogPost(
            slug=sp["slug"],
            title=sp["title"],
            description=sp.get("description", "")[:320],
            body=sp["body"],
            tag=sp.get("tag", ""),
            read_time=sp.get("read_time", ""),
            status="published",
            auto_generated=False,
            created_at=published_at,
            published_at=published_at,
        ))
        inserted += 1
    if inserted:
        db.session.commit()
    return inserted


# ---------- Daily auto-draft generation ----------
# Generates ONE draft a day for an admin to review/approve at /admin/blog. It
# NEVER publishes. Triggered by the daily scheduler in app.py (mirroring the
# weekly newsletter), and reused by scripts/generate_blog_draft.py for manual
# runs. The model defaults to the same Groq model the rest of the app uses.

BLOG_MODEL = os.environ.get("BLOG_MODEL", "llama-3.3-70b-versatile")

# Fresh headlines give the model concrete, current hooks to write around.
_NEWS_QUERIES = [
    "AI video generation tools",
    "African content creators social media",
    "TikTok Instagram creators Nigeria",
]


def _fetch_blog_headlines(max_per_query=4, timeout=8):
    """Pull this week's real headlines from Google News RSS (free, no key).
    Returns a list of '- Headline (Source)' strings; [] on any failure."""
    headlines = []
    for query in _NEWS_QUERIES:
        q = requests.utils.quote(f"{query} when:14d")
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            root = ElementTree.fromstring(resp.content)
            for item in root.findall("./channel/item")[:max_per_query]:
                title = (item.findtext("title") or "").strip()
                src_el = item.find("source")
                source = (src_el.text or "").strip() if src_el is not None else ""
                if title:
                    headlines.append(f"- {title}" + (f" ({source})" if source else ""))
        except Exception as e:
            print(f"[blog-draft] news fetch failed for '{query}': {e}")

    seen, deduped = set(), []
    for h in headlines:
        if h not in seen:
            seen.add(h)
            deduped.append(h)
    return deduped


def _build_blog_prompt(existing_titles, headlines):
    titles_block = "\n".join(f"- {t}" for t in existing_titles) or "(none yet)"
    headlines_block = "\n".join(headlines) if headlines else "(no fresh headlines available)"

    system = (
        "You are a senior content writer for Afrigen (tagline 'Africa Creates, AI "
        "Generates'), an African AI platform that turns text prompts into videos and "
        "images. You write for REAL Nigerian and African content creators, small "
        "business owners, and marketers who use AI video tools. You write like a "
        "knowledgeable local practitioner, not a generic blog mill."
    )

    user = f"""Write ONE original blog post for the Afrigen blog.

POSTS THAT ALREADY EXIST — do NOT repeat or closely overlap any of these topics; pick a clearly different, fresh angle:
{titles_block}

FRESH REAL-WORLD HEADLINES (for grounding and specificity — reference ideas/trends naturally, do not fabricate quotes):
{headlines_block}

HARD REQUIREMENTS:
- Length: 600 to 900 words in the body. Not shorter, not longer.
- Audience: Nigerian / African creators and small businesses using AI video tools. Write to them directly.
- Be CONCRETE. Use specific, real platforms by name (TikTok, Instagram Reels, YouTube Shorts, WhatsApp Status, Facebook). Use specific Nigerian/African places, scenarios, and content niches.
- Where money is relevant, use REAL figures in Naira (₦) — e.g. realistic costs of a videographer, data, a Pro subscription, ad spend. Use believable, current ranges, not round hand-wavy numbers.
- Give at least 2 concrete, worked examples (a real-sounding prompt, a real posting scenario, a before/after, a small calculation).
- Genuinely useful and actionable: a reader should be able to DO something after reading.

STRICTLY FORBIDDEN (this is content that previously got the site flagged by Google as low value):
- Generic filler, padding, or restating the obvious.
- Vague "AI-sounding" prose ("in today's fast-paced digital world", "unlock the power of", "the possibilities are endless", "game-changer", "in conclusion").
- Empty intros/outros that say nothing specific.
- Made-up statistics or fake quotes.

FORMAT — return ONLY a valid JSON object (no markdown fences, no commentary) with exactly these keys:
{{
  "title": "specific, non-clickbait title, max ~70 chars",
  "description": "one-sentence meta description for SEO, max 155 chars, specific",
  "tag": "one or two words categorizing the post (e.g. Prompting, Business, Platforms, Cost, Craft, Strategy)",
  "body_html": "the article body as inline-styled HTML"
}}

The body_html MUST use this exact styling to match the existing site design:
- Section subheadings: <h4 style="color: #F5A623;">Subheading</h4>
- Paragraphs: <p style="color: #C9D1D9; margin-bottom: 16px;">...</p>
- Lists: <ul style="color: #C9D1D9; margin-bottom: 16px;"><li>...</li></ul>
- Optional callout box: <div class="p-3 mb-3" style="background: #21262D; border-radius: 8px; border-left: 3px solid #F5A623;"><p style="color: #C9D1D9; margin: 0;">...</p></div>
- Use <strong> for emphasis. Do NOT include <html>, <head>, <body>, <h1>, <style>, or <script> tags. Start directly with an opening <p> intro paragraph (no title inside the body — the title is separate)."""

    return system, user


def _strip_to_json(text):
    """The model is asked for raw JSON, but defensively strip ``` fences / stray prose."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text).strip()
    # Grab the outermost {...} if there's leading/trailing chatter.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    return text


def _word_count(html):
    return len(re.sub(r"<[^>]+>", " ", html).split())


def _generate_post(existing_titles, headlines):
    if not os.environ.get("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set")

    # Reuse the shared Groq client the rest of the app initialises.
    from services.claude import client

    system, user = _build_blog_prompt(existing_titles, headlines)

    print(f"[blog-draft] calling Groq ({BLOG_MODEL})...")
    resp = client.chat.completions.create(
        model=BLOG_MODEL,
        max_tokens=4000,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = resp.choices[0].message.content or ""
    data = json.loads(_strip_to_json(raw))

    title = (data.get("title") or "").strip()
    body = (data.get("body_html") or "").strip()
    if not title or not body:
        raise ValueError("Model response missing title or body_html")

    return {
        "title": title,
        "description": (data.get("description") or "").strip(),
        "tag": (data.get("tag") or "").strip(),
        "body": body,
    }


def run_daily_draft_generation():
    """Generate ONE blog draft and save it as status='draft' for the admin to
    review/approve at /admin/blog. Called by the daily scheduler in app.py (and
    by scripts/generate_blog_draft.py for manual runs). Assumes an app context is
    active. NEVER publishes."""
    titles, _slugs = existing_titles_and_slugs()
    print(f"[blog-draft] {len(titles)} existing posts found (drafts + published).")

    headlines = _fetch_blog_headlines()
    print(f"[blog-draft] pulled {len(headlines)} fresh headlines for grounding.")

    post = _generate_post(titles, headlines)

    wc = _word_count(post["body"])
    read_time = f"{max(1, round(wc / 200))} min read"
    print(f'[blog-draft] generated: "{post["title"]}" — {wc} words, tag={post["tag"]!r}')
    if not (550 <= wc <= 1000):
        print(f"[blog-draft] word count {wc} outside the 600-900 target — saving anyway for review.")

    draft = create_draft(
        title=post["title"],
        description=post["description"],
        body=post["body"],
        tag=post["tag"],
        read_time=read_time,
        auto_generated=True,
    )
    print(f'[blog-draft] saved draft id={draft.id} slug="{draft.slug}" status={draft.status}. Review at /admin/blog.')
    return draft
