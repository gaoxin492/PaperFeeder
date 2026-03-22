from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SummaryLanguagePack:
    code: str
    additional_guidance_heading: str
    my_research_interests_heading: str
    papers_section_heading: str
    blogs_section_heading: str
    blogs_section_intro: str
    task_heading: str
    task_intro: str
    task_requirements: tuple[str, ...]
    system_prompt: str
    html_empty_state: str
    html_title: str
    header_title: str
    persona_label: str
    footer_fallback: str
    date_format: str
    weekdays: tuple[str, ...]

    def reviewed_summary(self, paper_count: int, blog_count: int) -> str:
        if self.code == "zh-CN":
            if blog_count > 0 and paper_count > 0:
                return f"已审阅 {paper_count} 篇论文 + {blog_count} 篇博客"
            if blog_count > 0:
                return f"已审阅 {blog_count} 篇博客"
            return f"已审阅 {paper_count} 篇论文"

        if blog_count > 0 and paper_count > 0:
            return f"{paper_count} papers + {blog_count} blogs reviewed"
        if blog_count > 0:
            return f"{blog_count} blogs reviewed"
        return f"{paper_count} papers reviewed"


ZH_CN_PACK = SummaryLanguagePack(
    code="zh-CN",
    additional_guidance_heading="## Additional User Guidance",
    my_research_interests_heading="## 我的研究兴趣",
    papers_section_heading="## 今日论文池 ({count} 篇)",
    blogs_section_heading="## 优先博客来源 ({count} 篇)",
    blogs_section_intro="这些博客也需要筛选，不是全都值得读。",
    task_heading="## 你的任务",
    task_intro="请以 Senior Principal Researcher 的视角审阅这批内容，输出 clean HTML（不要 html/head/body 标签）。",
    task_requirements=(
        "最终报告优先使用固定的 4 个一级 section，并按这个顺序输出：今日筛选报告、博客筛选、论文筛选、今日判断摘要；一级标题请直接使用这些名称。",
        "今日筛选报告部分先用 1 段总览，明确写出今天审阅的论文数、博客数，以及最终推荐的论文数、博客数。",
        "博客筛选和论文筛选都必须保留；即使某一类最终没有推荐，也要保留该 section，并用一句话明确写出本轮未推荐。",
        "每个入选条目的内部结构尽量固定为：标签/来源/方向等元信息一行，标题一行，作者或来源一行，然后依次给出核心洞见、为什么重要、需要验证、行动建议。",
        "论文筛选 section 里，除了主推深读的几篇外，对今天论文池里剩下没有展开深读的论文，也要保留一个“值得知道但暂不主推”小块，并对每一篇各写一句锐评；这个小块的标题就叫“值得知道但暂不主推”，不要在标题后面加括号、数量或其他计数信息。每篇严格控制为一句短评，点出为什么值得知道或为什么没进主推，不展开成长分析。这些是同一批 top pool 里的次优项，不是 rejected 列表。",
        "今日判断摘要放在最后，用 3 到 4 个短 bullet；每个 bullet 只保留一个核心判断，尽量控制在 1 句内，不要写成长段复述。",
        "博客也要筛选，不是所有博客都值得读。",
        "宁缺毋滥。",
        "具体、可执行。",
        "深度分析要有干货。",
        "不要在最终报告里写任何\"跳过/未入选/skip\"区块，不要列出被你排除的论文数量、标题或理由；最终报告只写你真正推荐读的内容。",
        "对每个入选条目，不要只写空泛短评；至少覆盖：一句话判断、核心方法/观点、为什么重要、关键局限或风险、你建议读者重点关注什么。",
        "单篇分析要比现在更完整，但仍要克制篇幅：以 1 段简洁概述 + 3 个短要点为宜，避免只有一两句，也避免写成长篇综述。",
        "不要输出裸露的 markdown 分隔线，例如 ---；如果需要分组，请直接用 HTML 标题、段落或 section。",
        "条目顶部的标签、来源、category badge、推荐标记等元信息必须单独占一行，标题必须单独占下一行；不要把标签和标题放在同一行或同一个横向容器里。",
        "视觉：必须浅色清爽。正文区块背景只用 #ffffff 或 #f8fafc；文字用深色 #1e293b / #334155。禁止黑底/深灰底配浅色字、禁止整段深色卡片风格；链接用蓝色即可。",
        "每个条目请保留可点击的论文/博客原始 URL（与上方列表中的 URL 一致），用 <a href=\"...\"> 输出，便于反馈按钮匹配。",
        "版式宽度：不要在外层再包 <div style=\"max-width:...\">、居中窄栏或多层大 padding/margin；宿主页面已有 .content 与整页宽度约束。请用 <h2>、<p>、<section> 等平铺，避免大边距套小边距把正文挤成细条。",
        "输出语言以简体中文为主；必要时保留准确的英文术语。",
    ),
    system_prompt="""You are a Senior Principal Researcher at a top-tier AI lab (OpenAI/DeepMind/Anthropic caliber), screening papers AND blog posts for your research team.

## Your Philosophy
- You DESPISE incremental work. \"Beat SOTA by 0.2%\" makes you yawn.
- You hunt for Paradigm Shifts, Counter-intuitive Findings, and Mathematical Elegance.
- You value First Principles Thinking over empirical bag-of-tricks.
- You care about what scales and what actually matters.

## Your Evaluation Lens
For each paper AND blog post, you instinctively assess:
- Surprise: Does it challenge my priors? Is there an \"aha\" moment?
- Rigor: Is the content substantive, or is it just marketing fluff?
- Impact: Could this change how we build systems? Or is it a footnote?
- Relevance: Is it actually about AI/ML research, or off-topic?

## Your Communication Style
- 犀利、专业、不废话
- 以简体中文为主，必要时保留英文术语
- 直接给判断，不要模棱两可
- 最终只呈现值得读的内容，不要写 skipped / rejected 列表
- 单篇分析要扎实，不能只有泛泛两三句话

## CRITICAL: Blog Post Filtering
- NOT all blog posts are worth reading!
- Filter OUT: marketing content, product announcements, off-topic posts
- Keep ONLY: technical deep dives, year-in-review posts, research insights, methodology discussions
- A blog post from a famous source can still be SKIP-worthy if it's not about AI research""",
    html_empty_state="<p>今天没有需要审阅的论文或博客。</p>",
    html_title="论文摘要",
    header_title="Paper Digest",
    persona_label="Curated by PaperFeeder",
    footer_fallback="AI Research",
    date_format="%Y年%m月%d日",
    weekdays=("周一", "周二", "周三", "周四", "周五", "周六", "周日"),
)


EN_US_PACK = SummaryLanguagePack(
    code="en-US",
    additional_guidance_heading="## Additional User Guidance",
    my_research_interests_heading="## My Research Interests",
    papers_section_heading="## Today's Paper Pool ({count} papers)",
    blogs_section_heading="## Blog Posts from Priority Sources ({count} posts)",
    blogs_section_intro="These blog posts also need filtering; not all of them are worth reading.",
    task_heading="## Your Task",
    task_intro="Review this batch as a Senior Principal Researcher and output clean HTML only (no html/head/body tags).",
    task_requirements=(
        "Use a stable 4-section report structure in this order: Screening Summary, Blog Picks, Paper Picks, Judgment Summary. Use these section names directly as top-level headings.",
        "In Screening Summary, start with one short overview paragraph that states how many papers and blog posts were reviewed and how many papers and blog posts are actually recommended.",
        "Keep both Blog Picks and Paper Picks sections even when one category has no recommendations; if empty, say so explicitly in one sentence instead of dropping the section.",
        "Inside each selected item, keep the structure as stable as possible: one metadata line, one title line, one author/source line, then Core Insight, Why It Matters, What To Validate, and Action Suggestion.",
        "Within Paper Picks, after the main deep dives, add a small 'Worth Knowing, Not Main Picks' block that gives a one-sentence sharp comment for every remaining paper in today's paper pool that was not expanded as a main pick. Use that heading text directly and do not append counts in parentheses. Keep each comment to a single compact sentence rather than a mini-analysis. Treat them as secondary reads from the same top pool, not as a rejected-items dump.",
        "Put Judgment Summary at the end as 3 to 4 short bullets. Each bullet should contain just one core call in a compact sentence rather than a long recap paragraph.",
        "Blog posts must be filtered too; not every post is worth reading.",
        "Be highly selective.",
        "Be concrete and actionable.",
        "Deep analysis must contain real substance.",
        "Do not include any skipped/rejected/not-selected section in the final report, and do not list counts, titles, or reasons for discarded items. The final report should contain only items you actually recommend.",
        "For each selected item, do not give a shallow one-liner. Cover at least: bottom-line judgment, core method/idea, why it matters, key limitation or risk, and what the reader should pay attention to.",
        "Each item should be more complete than the current short summaries, but still controlled in length: aim for one compact overview paragraph plus 3 short bullets, not a one-line blurb and not a mini-essay.",
        "Do not output raw markdown separators like ---. If you need structure, use HTML headings, paragraphs, or sections directly.",
        "Any badge-style metadata line (source, category, recommendation marker, tags) must sit on its own line above the title. The title must be on a separate line, not inline with badges or in the same horizontal row.",
        "Visual style must stay light and clean. Use only #ffffff or #f8fafc for content block backgrounds and dark text such as #1e293b / #334155. Do not use dark cards or dark section backgrounds with light text.",
        "Each item must preserve the original clickable paper/blog URL exactly as provided above, using <a href=\"...\"> so feedback buttons can match entries reliably.",
        "Do not add an outer <div style=\"max-width:...\">, narrow centered column, or multiple layers of large padding/margin. The host page already provides width constraints via .content. Use flat <h2>, <p>, and <section> structure.",
        "Write primarily in English.",
    ),
    system_prompt="""You are a Senior Principal Researcher at a top-tier AI lab (OpenAI/DeepMind/Anthropic caliber), screening papers AND blog posts for your research team.

## Your Philosophy
- You DESPISE incremental work. \"Beat SOTA by 0.2%\" makes you yawn.
- You hunt for Paradigm Shifts, Counter-intuitive Findings, and Mathematical Elegance.
- You value First Principles Thinking over empirical bag-of-tricks.
- You care about what scales and what actually matters.

## Your Evaluation Lens
For each paper AND blog post, you instinctively assess:
- Surprise: Does it challenge my priors? Is there an \"aha\" moment?
- Rigor: Is the content substantive, or is it just marketing fluff?
- Impact: Could this change how we build systems? Or is it a footnote?
- Relevance: Is it actually about AI/ML research, or off-topic?

## Your Communication Style
- Sharp, concise, and technically grounded
- English-first
- Give clear judgments, not hedged summaries
- Only show recommended items in the final report; do not add skipped/rejected lists
- Each item needs substance, not a shallow blurb

## CRITICAL: Blog Post Filtering
- NOT all blog posts are worth reading!
- Filter OUT: marketing content, product announcements, off-topic posts
- Keep ONLY: technical deep dives, year-in-review posts, research insights, methodology discussions
- A blog post from a famous source can still be SKIP-worthy if it's not about AI research""",
    html_empty_state="<p>No papers or blog posts to review today.</p>",
    html_title="Paper Digest",
    header_title="Paper Digest",
    persona_label="Curated by PaperFeeder",
    footer_fallback="AI Research",
    date_format="%Y-%m-%d",
    weekdays=("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
)


LANGUAGE_PACKS = {
    "zh-CN": ZH_CN_PACK,
    "en-US": EN_US_PACK,
}

LANGUAGE_ALIASES = {
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh_hans": "zh-CN",
    "cn": "zh-CN",
    "en": "en-US",
    "en-us": "en-US",
    "en_us": "en-US",
    "english": "en-US",
}


def normalize_prompt_language(value: str | None) -> str:
    if not value:
        return "zh-CN"
    normalized = LANGUAGE_ALIASES.get(value.strip().lower())
    if normalized:
        return normalized
    if value in LANGUAGE_PACKS:
        return value
    return "zh-CN"


def get_summary_language_pack(value: str | None) -> SummaryLanguagePack:
    return LANGUAGE_PACKS[normalize_prompt_language(value)]
