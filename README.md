# Vedaz AI Astrology Quality & Safety Framework

This repository contains the production-grade quality control, generation, and testing suite developed for **Vedaz**. It ensures our empathetic Vedic astrology voice remains consistent, safe, and of high quality at scale.

---

## Repository Structure

```text
├── checker.py          # Task 1: Chat validation, near-duplicate check, safety filter, dataset splitting
├── generator.py        # Task 2: Synthetic chat generator with inline validation loop
├── tester.py           # Task 3: Quality evaluation harness (LLM-as-a-judge)
├── requirements.txt    # Project Python dependencies
├── generated_chats.jsonl # 10 high-quality, pre-generated chats from Task 2
├── test_results.md     # Markdown results table generated from Task 3
└── README.md           # Instructions, architecture notes, and choices
```

---

## Setup Instructions

### Prerequisites
- Python 3.8 or higher.
- An API key for an OpenAI-compatible service (Together AI, DeepSeek, or OpenAI).

### 1. Initialize Virtual Environment & Install Dependencies
Run the following commands in your shell:
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (CMD):
.venv\Scripts\activate.bat
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory or export variables directly. 
```bash
# Example for Together AI (DeepSeek)
export TOGETHER_API_KEY="your_together_api_key"
export TOGETHER_API_BASE="https://api.together.xyz/v1"
export OPENAI_MODEL="deepseek-ai/DeepSeek-V3"

# Example for OpenAI
# export OPENAI_API_KEY="your_openai_api_key"
# export OPENAI_MODEL="gpt-4o-mini"
```

---

## Execution Guide

### Task 1 — Chat Checker (`checker.py`)
Reads a `.jsonl` file containing chats, validates format structure, counts words/estimated tokens, flags near-duplicates, runs safety auditing, and splits them into training and test files.

```bash
# Run checker completely offline (using fast regex safety rules)
python checker.py generated_chats.jsonl

# Run checker with advanced LLM-as-a-judge safety checks (requires API keys configured)
python checker.py generated_chats.jsonl --use-llm
```

### Task 2 — Chat Generator (`generator.py`)
Generates high-quality synthetic chats. It prompts the model, parses JSON, and passes outputs through the Chat Checker pipeline. Only safe, well-formed chats are preserved.

```bash
# Generates 10 chats (cycles through predefined Vedic scenarios)
python generator.py --count 10 --out-file generated_chats.jsonl
```

### Task 3 — Quality Tester (`tester.py`)
Evaluates an assistant's safety, tone, and boundary-setting across a test suite using an LLM-as-a-judge. Prints a report summary and writes details to `test_results.md`.

```bash
# Run evaluation on default test suite
python tester.py --out-file test_results.md
```

---

## Architectural Choices & Design Notes

### Task 1: Safety Auditing Strategy
- **Method Chosen**: A **Hybrid Safety Engine**.
  1. *Regex Filter (Fast/Deterministic)*: Standard regex rules catch obvious violations (e.g. diagnosing "cancer", predicting "death", upselling expensive stones or pujas in Hinglish/English).
  2. *LLM Safety Verifier (Nuanced)*: Borderline or flagged cases are routed to a fast LLM call (e.g. `gpt-4o-mini` or `DeepSeek-V3`) to verify context.
- **Why this works**: Regex is cost-effective, immediate, and catches 90% of explicit violations. The LLM handles the remaining 10% of complex phrasing.
- **Blind spots**:
  - *Sarcasm and Double Negatives*: An expression like "I am not saying you'll die tomorrow, but Shani is bad" might pass standard filters.
  - *Transliteration Variations*: Hindi terms spelled creatively in Hinglish (e.g., `mrityuu`, `mawt`) might slip past static regex lists unless a dictionary is updated.

### Task 2: Voice Consistency & Robust Generation
- **Method Chosen**: System instructions feed-forwarding strict operational limits, combined with a **Validation Loop**.
- **Why this works**: Language models can still hallucinate violations. By piping outputs directly through the `checker.py` validator, we enforce a closed-loop system where only verified safe chats are outputted.

### Task 3: Quality Tester & LLM-as-a-Judge
- **Method Chosen**: Structured scorecard judging. The judge outputs a clean JSON grading three dimensions:
  - **Safety**: Strict binary score (Pass/Fail) on illness/death/upselling/lotteries.
  - **Tone**: Qualitative score (1 to 5) evaluating warmth and empathy.
  - **Boundaries**: Qualitative score (1 to 5) verifying if the assistant clearly states astrology's limitations.
- **Why this works**: Provides reproducible quantitative scores across all evaluations, removing subjective biases from gut feelings.

---

## Future Improvements (With More Time)
1. **Semantic Duplicate Check**: Use Sentence-Transformers (vector embeddings) instead of Jaccard similarity to catch duplicates that use different wording.
2. **Dynamic Regex Engine**: Connect the regex matcher to an online database/service (like Redis) so the list of high-risk Hinglish words can be updated live without rebuilding the container.
3. **Multi-turn Judge Evaluation**: Grade individual turns in a conversation contextually rather than grading the whole conversation block at once.
