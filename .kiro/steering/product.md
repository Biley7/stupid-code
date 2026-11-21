# Product: Stupid Code (Code Autopsy Edition)

## Mission
Stupid Code is a deterministic, anti-vibe-coding codebase comprehension and forensic learning engine. It helps developers understand a codebase through grounded, structured dissection instead of generic chatbot summaries.

Every explanation must be grounded in the actual source code or repository evidence being inspected.

## Analysis Levels

### L1 — Syntax & Primitives
Explain the exact syntax, language primitives, decorators, expressions, functions, types, and constructs found in the selected code. Stay grounded in the real source.

### L2 — Execution & Data Flow
Explain execution paths, runtime flow, callers, callees, dependency movement, and how data moves through the system.

Includes a **DSA-in-the-Wild detector** that identifies real data structures and algorithmic patterns used in production code, only when evidence supports their existence. Never force a DSA explanation onto code with no meaningful pattern.

### L3 — Production Folder Architecture & Counterfactual Tradeoffs
Explain how production codebases are organized, how modules relate, and why architectural choices may have been made. Provide counterfactual tradeoffs: explain the actual architecture and compare it against plausible alternative structures, with advantages and disadvantages of each. Ground claims in repository evidence, not invented assumptions about developer intent.

## Study Mode
Study Mode is a toggle. It must change behavior, not just appearance.

- **Study Mode OFF — Autopsy Mode:** fast, zero-friction exploration. Browse dissections immediately. No mandatory quizzes, no Socratic interruptions. Prioritize quick comprehension and navigation.
- **Study Mode ON — Active Mastery & Socratic Exorcism Mode:** code-grounded Socratic questions. Understanding must be verified before mastery progresses. Supports long-term retention and spaced repetition (later phases).

## Native Product Surfaces
One shared backend serves three native surfaces:

1. **Hosted Web App**
2. **Kiro Crew App**
3. **Kiro Power + FastMCP Server**

Surfaces must reuse shared backend functionality. Never duplicate business logic per surface.

## Non-Goals
Do not add features or change the mission without an explicit instruction from the project owner.
