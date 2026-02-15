# TALE IDE & Learning Center

A web-based playground and course for the TALE beginner-friendly programming language. It bundles a browser IDE, interactive terminal, AI-assisted code generation, and a guided 12-lesson curriculum to teach programming concepts through natural, English-like syntax.

## Table of Contents
- Project Overview
- Key Features
- System Architecture & Tech Stack
- Technical Deep Dive
- Installation & Setup
- Usage Guide
- Environment Configuration
- Screens & Pages
- Security & Privacy
- Performance Notes
- Limitations & Known Issues
- Future Enhancements
- Real-World Value
- Contribution Guidelines
- License
- Conclusion

## Project Overview
- Platform: Browser-based IDE plus learning portal for TALE, backed by a Flask API.
- Purpose: Teach absolute beginners core programming by translating readable TALE scripts into safe Python and executing them with controlled I/O.
- Audience: New coders, educators, students, hobbyists, and teams prototyping instructional content.
- Scope: Authoring, running, and analyzing TALE code; structured lessons with runnable examples; optional AI-assisted code generation via Google Gemini.

## Key Features
- **Core IDE**: Monaco-powered TALE editor with syntax highlighting, snippets, hover markers, adjustable font, word wrap toggle, and keyboard shortcuts (F5 run, F2 prompt, F8 submit prompt, Ctrl+Enter run selection).
- **Safe Interpreter**: TALE-to-Python translator with syntax validation, controlled execution environment, sandboxed built-ins, and deterministic input provision (tale_engine.py).
- **Interactive Terminal**: In-browser terminal rendering stdout/stderr, clearing, show/hide controls, and per-run session output (editor.js).
- **Input Collection**: Auto-detected `ask` prompts trigger interactive input forms; labels derived from prompt text for clarity.
- **Code Analysis**: Background `/analyze` endpoint surfaces syntax issues as Monaco markers without executing code.
- **AI Generation (optional)**: `/ai_generate` calls Google Gemini (via `google-genai`) to produce TALE code from natural-language prompts, applying safety filters and fence stripping (ai.py).
- **Learning Center**: 12-lesson curriculum with progress tracking (localStorage), collapsible sections, copy/run code cards that deep-link to the IDE, and a course TOC (learn.html, learn.js).
- **Examples & Transfer**: Example snippets can be inserted into the editor or copied from lessons; lesson “Run” buttons transfer code to the IDE via localStorage (`TALE_TRANSFER_CODE`).

## System Architecture & Tech Stack
- **Architecture**: Flask server exposes REST endpoints; static frontend served from templates; TALE code compiled to Python in-process and executed with a sandboxed runtime.
- **Backend**: Python 3, Flask routes in app.py; interpreter and analyzer in tale_engine.py; AI gateway in ai.py.
- **Frontend**: Vanilla JS + Monaco Editor (CDN), Bootstrap Icons, custom CSS (style.css, theme.css), learning styles (learn.css).
- **AI**: Google Gemini model `gemini-2.5-flash` via `google-genai`; system prompt enforces TALE-only responses.
- **Persistence**: None server-side; browser localStorage for lesson progress and code handoff.
- **APIs**:
  - `POST /run` — execute TALE with inputs.
  - `POST /analyze` — static syntax check.
  - `POST /ai_generate` — TALE generation from prompt.
  - `GET /` — IDE; `GET /learn` — course.

## Technical Deep Dive
- **Interpreter pipeline** (tale_engine.py):
  - Parses TALE lines, handles block structure (`if/elif/else/end`, `repeat`, `while`, `function`, `class`, `try/catch/finally`).
  - Expression transformer supports helpers (`upper/lower/strip`, `map/filter`, `json read/write`, `csv read/write`, set ops, lambda arrow syntax, `call foo 1 2` shorthand).
  - Validates identifiers/expressions via `ast.parse`; normalizes boolean/None and dict literals.
  - Execution uses `exec` with restricted built-ins (math/random/datetime/json/csv/os/sys) and an allowlisted importer; prints are redirected to a buffer for UI display.
  - Input is supplied deterministically from the provided list; numeric-looking inputs auto-coerce to int/float; exhaustion raises user-facing guidance.
- **Safety checks**:
  - AI input screened for unsafe patterns (e.g., “hack”, “shell”, infinite loops) before calling Gemini.
  - AI output stripped of fences and markdown; empty/blocked responses raise structured errors.
  - Interpreter forbids arbitrary imports and disallowed AST nodes; file I/O gated via `_open_file`.
- **Frontend logic** (editor.js):
  - Monaco language registration for “tale” with keywords/types/builtins, completion, snippets, signature help, hover markers.
  - Analyzer debounce (350ms) to update diagnostics.
  - Input collection UI injected into terminal when `ask` detected.
  - Prompt mode: swaps theme, disables run, shows overlay placeholder, submits prompt to AI, rehydrates editor with returned code.
  - Resizable layout dividers (vertical editor/examples, horizontal workspace/terminal) with mouse/touch drag.
- **Learning center** (learn.js):
  - Progress persistence keyed `tale-learn-progress-v1`; updates chips, counts, and progress bar.
  - Example cards support copy-to-clipboard and “Run” deep link (stores code to localStorage then redirects `/`).

## Installation & Setup
- **Requirements**: Python 3.10+ recommended; internet access if using AI; Google API key for generation; Node not required.
- **Install dependencies**:
  - `python -m venv .venv`
  - `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (Unix)
  - `pip install -r requirements.txt`
- **Environment**:
  - Create .env with `GOOGLE_API_KEY=<your-key>` for AI features; without it, `/ai_generate` returns “AI not configured”.
- **Run locally**:
  - `python app.py`
  - Open http://localhost:5000 for the IDE; http://localhost:5000/learn for the course.
- **Production hint**:
  - `gunicorn -b 0.0.0.0:5000 app:app` (adjust workers for your environment).
- **Troubleshooting**:
  - Missing API key → AI endpoints return 503/400 with “AI not configured”.
  - Analyzer errors → check TALE block endings (`end`) and assignments (`x is 3`).
  - Input exhaustion → ensure Inputs count matches `ask` statements.

## Usage Guide
- Visit the IDE, type TALE code, and press F5 or the Run button.
- Provide inputs when prompted in the terminal; labels match `ask` prompts.
- Toggle word wrap, font size, show/hide examples and terminal as needed.
- Use prompt mode (F2) to describe a program; submit (F8) to receive AI-generated TALE; run or edit afterward.
- Copy or insert quick examples; lesson “Run” buttons in Learning Center open the IDE with that code preloaded.

## Environment Configuration
- `GOOGLE_API_KEY`: Required for AI generation; loaded via `python-dotenv`.
- Optional: `PORT` not explicitly used; defaults to 5000 in app.py.

## Screens & Pages
- **IDE** (index.html):
  - Dark Monaco editor, example panel, resizable terminal, spinner overlay for AI, status pill.
- **Learning Center** (learn.html):
  - 12 lessons with TOC, progress card, collapsible sections, copy/run code examples, responsive layout.

## Security & Privacy
- Code execution sandboxed with restricted built-ins/imports; file access via controlled helper.
- AI prompts filtered for unsafe content; blocked requests return 400.
- No user data persisted server-side; progress stored locally in the browser.
- Network calls only to Google AI when configured.

## Performance Notes
- TALE-to-Python translation is lightweight; execution confined to a single process.
- Monaco and assets served via CDN; initial load depends on CDN availability.
- Analyzer debounce limits chatter to the backend during editing.

## Limitations & Known Issues
- No authentication or multi-user state.
- No server-side persistence or database.
- AI generation requires a valid Google API key; otherwise disabled.
- Sandbox is best-effort; not a full security boundary for untrusted multi-tenant use.
- No automated tests included.

## Future Enhancements
- Add unit/integration tests for interpreter and API.
- Introduce server-side rate limiting and per-session isolation.
- Expand TALE standard library and diagnostics with richer hints.
- Offline/bundled Monaco assets for air-gapped use.
- Export/shareable gists for TALE programs.

## Real-World Value
- Low-friction onramp for teaching programming concepts.
- Useful for workshops, classrooms, and self-paced learners.
- Rapid prototyping of exercises and interactive curriculum.

## Contribution Guidelines
- Fork and branch from main; prefer small, focused PRs.
- Add tests for interpreter changes; document new syntax helpers.
- Keep frontend UI keyboard-accessible and responsive.
- Run linting/formatting consistent with existing style (no formatter specified; follow current patterns).

## License
- No license file present; clarify intended licensing before redistribution or commercial use.

## Conclusion
TALE IDE blends a gentle, English-like language, an interactive browser IDE, AI-assisted authoring, and a structured course to help beginners learn core programming ideas quickly and safely. Set up locally, explore the lessons, and iterate on new TALE programs with the built-in sandbox and AI assist.