# Design Decisions

## One controlled workflow, not a multi-agent system

The tasks have known stages and deterministic parts. LangGraph controls request context, intent routing, retrieval/tools, policy checks, response validation and audit. Separate autonomous agents would add coordination and failure modes without solving a mandatory requirement better.

## Retrieval vs structured data

Sentence Transformers + persistent ChromaDB search free-text policy chunks. SQLite stores exact student records, source metadata, rule values and audit summaries. Vector similarity cannot decide student eligibility or be treated as proof that a passage supports a claim.

## Embeddings and chunking

The default embedding model is `all-MiniLM-L6-v2` because it is small enough for local setup and supports semantic retrieval without a cloud dependency. The implementation keeps chunking and top-k configurable. Evaluation should be used to choose settings rather than assuming that a configuration is best without measurements.

## Rules-based intent router

A deterministic rules/keyword router handles common policy, attendance, result, CGPA, exam-eligibility, placement and supplementary requests. This avoids relying on a small local model for every tool call. An LLM fallback can be considered for truly ambiguous intent only when its output is validated; unclear requests should ask for clarification.

## Rule lifecycle

A policy document is indexed as searchable text before any numeric threshold can control a tool. New rules start as candidates. Validation checks source ID, clause, scope, dates, operator and supersession metadata. Only an explicitly validated/activated source-linked rule is used by the calculation tools. Synthetic rules remain visibly synthetic.

## Why Qwen through Ollama

A pre-trained instruction model can run locally and explain checked evidence without sending every query to a cloud LLM. It is not fine-tuned or trained from scratch. `MOCK_LLM=true` supports pipeline tests and must not be described as actual model inference. `MOCK_LLM=false` requires Ollama and the configured model to be available.

## Source precedence

Implement Annex A in order: applicability, explicit supersession, authority, recency, then unresolved conflict. Do not use a generic “latest document wins” rule. The synthetic circular only supersedes the synthetic baseline; it must not override a real DTU ordinance.

## Known trade-offs

The base attendance tool checks the 75% clause but does not automatically infer authorised attendance relaxation. Placement policy is cohort-scoped and company-specific; no universal official CGPA cutoff is inferred. Synthetic placement/supplementary rules are for UI/tool demonstrations only. OCR text needs page-level human verification before real policy decisions.
