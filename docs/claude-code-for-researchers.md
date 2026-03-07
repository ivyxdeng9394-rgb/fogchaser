# Claude Code for Research Work
### Why Claude Projects isn't the whole story, and what you're still missing

---

## Starting honestly: Claude Projects is genuinely good

If you're using Claude Projects on the web, you've already solved the biggest problem with plain Claude Web. Projects gives you:

- Persistent context across conversations, so you don't have to re-explain your research focus every session
- Uploaded documents Claude can reference throughout the project
- Custom instructions that carry over automatically

That's real. This document isn't arguing that you're doing it wrong. It's arguing that there are four specific things Claude Projects still can't do, and for a research-heavy workflow, they matter.

---

## What Claude Projects still doesn't solve

### 1. Your documents are snapshots, not live files

When you upload a document to Claude Projects, Claude reads a frozen copy from the time of upload. If you update your literature review, revise your codebook, or add new studies to your meta-analysis, Claude doesn't know. You have to manually re-upload.

Claude Code reads files directly from your computer, in real time. There's nothing to upload or sync. If you edit a document, Claude sees the current version the next time it reads it. Your working folder *is* the project.

### 2. Output still goes to a chat bubble

With Claude Projects, Claude's responses are still chat messages. You read them, decide what's useful, and copy-paste the relevant parts into a document somewhere else. The work lives in two places (the chat and your Google Doc) and you're the bridge between them.

Claude Code writes directly to files. You ask for a revised section of a research memo, it edits the file. You ask for a synthesis of your included studies, it creates a document in your project folder. No copy-paste, no reconciling two versions. The output is already where it belongs.

### 3. No parallel agents

Claude Projects is one thread. You ask a question, you get an answer, you ask another question. If you want to explore two angles simultaneously, say "assess internal validity" and "assess external validity," you do them sequentially.

Claude Code can dispatch multiple specialized agents at the same time. One agent reviews your identification strategy. Another stress-tests the assumptions. Another scans your literature for contradicting evidence. They run in parallel and report back. For work that involves systematic critique, this is meaningfully faster and produces sharper output.

### 4. Memory that updates itself

In Claude Projects, context is what you've uploaded plus the conversation history. It doesn't grow or self-organize based on what you learn.

Claude Code maintains a live memory file, a structured document that updates as the project evolves. Every significant finding, every methodological decision, every assumption that got revised gets written down automatically. When you start a new session, Claude loads that file and knows exactly where things stand. Not just what documents you have, but the reasoning history of the whole project.

---

## Side-by-side comparison

| Research task | Claude Web Projects | Claude Code |
|---|---|---|
| **Reading your documents** | Uploaded snapshots; must re-upload when docs change | Reads live from your file system, always current |
| **Output goes to...** | Chat bubble; you copy-paste to Google Doc | Directly into a file in your project folder |
| **Critiquing your work** | One thread, sequential | Parallel agents: multiple critique angles running simultaneously |
| **Project memory** | Conversation history + uploaded files | Self-updating memory file that builds over time |
| **Searching across your files** | Only what you've uploaded | Searches your entire project folder by content or filename |
| **Structured research workflows** | Freestyle; you direct everything | Skills: built-in workflows for brainstorming, systematic critique, planning |
| **Tracking decisions and reasoning** | Buried in chat history | Dated plan and finding documents, saved and organized |

---

## A real example: the fogchaser project

To make this concrete — fogchaser is a fog prediction research project that Ivy (my co-author on this document) has been working on with Claude Code. No production software has been built yet. The work so far has been entirely research, analysis, and planning. Here is what Claude Code has actually been used for:

**Writing and refining a Product Requirements Document across multiple sessions**
Claude read early working notes, asked clarifying questions, and helped produce a structured PRD covering product vision, data sources, modeling philosophy, competitive landscape, and a full bibliography. Each session picked up with full context because of the memory file — not just what documents existed, but what had been decided and why.

**Critiquing modeling approaches before committing to one**
Before choosing a prediction approach, parallel agents evaluated multiple options simultaneously: one exploring the strengths of each, another actively looking for failure modes and edge cases. The output was saved as a structured analysis document in the project folder, not a chat log.

**Investigating unexpected findings systematically**
When real data showed fog occurs only 0.7% of the time (the original estimate was 2 to 5%), Claude used a structured debugging workflow to investigate why before drawing any conclusions. The finding and its implications were written directly into the running memory file and carried forward into every subsequent session automatically.

**Building a phased research plan with explicit decision gates**
The phase 1 plan includes task breakdowns, stopping criteria, and instructions for what to do if key assumptions break. It lives as a versioned file in the project, not a conversation thread.

**Maintaining a running record of what was learned and why**
The memory file now captures eight months of findings: which approaches were tested, what the data showed, what assumptions got revised, and what the current best understanding is. This document is loaded at the start of every session. There is no "can you remind me where we landed on X."

None of this involved writing software. All of it required the things Claude Projects doesn't have: live file access, output that writes directly to files, parallel critique, and memory that compounds over time.

---

## Why this matters for empirical research specifically

The copy-paste workflow is annoying for any research. But for quantitative empirical work like meta-analysis, quasi-experiments, and impact evaluation, it creates specific problems that compound over time.

**Meta-analysis**

A meta-analysis involves tracking dozens or hundreds of studies: effect sizes, sample characteristics, quality ratings, inclusion/exclusion decisions. With Claude Projects, you're uploading static spreadsheets and asking Claude to reason over them in chat. When you add five more studies or revise your inclusion criteria, you re-upload and re-explain.

With Claude Code, your study database is a live file. You update it, Claude reads the current version. Your codebook, your inclusion rationale, your running notes on heterogeneity all live in the same folder, all readable by Claude without uploading. You can ask "given the studies we've coded so far, what's driving the variance in effect sizes?" and Claude has the full, current picture.

**Quasi-experiments and identification strategy**

Designing a credible identification strategy (difference-in-differences, regression discontinuity, instrumental variables) requires pressure-testing assumptions, not just drafting them. In Claude Projects, you describe your design in chat and Claude responds. That's one perspective, sequentially.

In Claude Code, you can run parallel critique agents: one looking for violations of parallel trends, another evaluating whether your instrument is actually exogenous, another scanning your literature folder for papers that used similar designs and what critiques they faced. All at once. The output is a structured critique document saved to your project, not a chat log you have to summarize later.

**Impact evaluation**

Impact evaluation reports evolve over months. Your theory of change gets revised. Your comparison group changes. Your outcome definitions get refined. With Claude Projects, Claude's understanding of your project is only as current as your last upload.

With Claude Code, your evolving documents are always current. The memory file tracks not just what the project looks like now, but why it looks that way: what you tried, what you rejected, what the evidence said. That institutional memory is the difference between a tool that helps you think and a tool that helps you produce output.

---

## What running analysis actually looks like

One more thing Claude Projects can't do: run anything.

If your research involves data (and impact evaluation and meta-analysis both do), Claude Code can actually execute statistical analysis. You describe what you want in plain English. Claude writes the R or Python, runs it against your data files, reads the output, and interprets the results. You don't write the code. You describe the question.

"Run a forest plot on the studies in this folder and flag any with high heterogeneity."
"Check whether the pre-trend assumption holds for these two groups."
"Summarize the effect size distribution and flag outliers."

These are the kinds of questions you'd ask an RA to answer. Claude Code can answer them directly, against your actual data, and write the findings into a document.

---

## The honest trade-off

Claude Projects is easier to start with. There's no setup and you're already on the web. If your research workflow is mostly "ask questions, read the answer, move on," Projects is probably fine.

Claude Code is worth it when:
- Your research involves evolving documents and data you keep updating
- You're building a body of work that needs to compound across months
- You want outputs that live in structured files, not chat logs
- You're doing systematic work like meta-analysis or impact evaluation, where tracking decisions and assumptions over time matters
- You want parallel critique of methodology, not just sequential Q&A
- You're tired of being the copy-paste bridge between Claude and your documents

The setup is a terminal application you point at a folder. You talk to it in plain English. The difference is not in how you interact with it. It's in what happens to the output and how much the system learns over time.

---

*This document was written by Claude Code. It exists as a file in a project folder, not as a chat message.*
