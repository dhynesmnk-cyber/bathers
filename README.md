# Spa Directory — Build Package

Feed order for Claude Code:
1. Drop this whole folder into the empty repo root (including .claude/ and .env.example).
2. Copy .env.example -> .env and add your ANTHROPIC_API_KEY.
3. Open Claude Code and say: "Read TRD.md, CLAUDE.md, SCHEMA.md, DESIGN.md and UX.md, then begin Gate 1."
4. Verify each gate's done-condition (run /validate) before approving the next.

File map:
- TRD.md ......... authoritative technical spec (what to build)
- CLAUDE.md ...... process: gates, constraints, commands (how to build)
- DESIGN.md ...... visual spec (how it looks)
- UX.md .......... behavioural spec (how it behaves), incl. image approval pipeline
- SCHEMA.md ...... single data contract: frontmatter / SQLite / harvester JSON / sample MDX
- PROMPTS/ ....... three agent prompts, loaded at runtime (edit freely, no code changes needed)
- SEED.md ........ verified test venue URLs + expected pipeline behaviour
- .env.example ... environment template
- .claude/commands/validate.md ....... /validate gate-exit test
- .claude/skills/spa-design/ ......... design enforcement on every UI session
- .claude/skills/mdx-review/ ......... optional advisory pre-screen of staged drafts
