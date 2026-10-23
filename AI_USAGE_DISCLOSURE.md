# AI Usage Disclosure (complete honestly before submission)

This project uses an AI-assisted development workflow. The exact final disclosure should be completed by the team after reviewing the repository and should name only tools/models actually used.

## Current project notes
- The synthetic fictional profile seed in `data/test_students/ai_profiles_seed.json` was AI-authored during project preparation. Its source record names GPT-6 as the model family, but the exact deployment revision is unavailable and is not claimed.
- `data/prompts/student_data_generation_prompt.md` is the verbatim prompt used by the reproducible generator. If Ollama is configured and reachable, `scripts/generate_students.py --provider auto` attempts live LLM profile generation; the run record identifies the model returned by Ollama. Otherwise, it records use of the bundled AI-authored seed.
- Python deterministically creates course, attendance and result relationships, sets programme/batch balance, derives backlog counts, applies exact rule-registry-based boundary cases, validates the output and writes run reports. It does not claim the LLM authored exact boundary values.
- The two documents named `SYN-DEMO-REG-001` and `SYN-DEMO-CIRC-002` are fictional demo data, not DTU policy.
- AI assistants were used to help draft and revise code/documentation. The team must review the code, run the tests and complete exact tool/model/version information for the environment actually used.

## Complete before submission
- Coding assistants and versions actually used: `[fill in]`
- Locally run model and version: `[fill in or say not used]`
- AI-generated artifacts reviewed by each member: `[fill in]`
- Tests executed and results: `[fill in from actual final run]`
- External libraries/tutorial patterns reused and their licenses/credits: `[fill in]`
