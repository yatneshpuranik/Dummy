#!/usr/bin/env python3
import json
import os
import re
import argparse
from typing import List, Dict, Tuple, Any

def validate_structure(chat: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Confirms each chat has the right shape:
    - Must be a dict with a 'messages' key containing a list.
    - messages[0] must have role 'system'.
    - Subsequent messages must alternate between 'user' and 'assistant'.
    """
    if not isinstance(chat, dict):
        return False, "Chat is not a JSON object"
    if "messages" not in chat:
        return False, "Missing 'messages' key"
    messages = chat["messages"]
    if not isinstance(messages, list):
        return False, "'messages' key must be a list"
    if len(messages) == 0:
        return False, "'messages' list cannot be empty"
    
    # First message must be system
    if messages[0].get("role") != "system":
        return False, "First message role must be 'system'"
    if not messages[0].get("content"):
        return False, "System message content cannot be empty"
        
    # Subsequent turns must alternate
    expected_role = "user"
    for i in range(1, len(messages)):
        msg = messages[i]
        if not isinstance(msg, dict):
            return False, f"Message at index {i} is not a dictionary"
        role = msg.get("role")
        if role not in ["user", "assistant"]:
            return False, f"Message at index {i} has invalid role '{role}'. Must be 'user' or 'assistant'."
        if role != expected_role:
            return False, f"Message at index {i} has role '{role}', expected '{expected_role}' (turns must alternate)"
        if not msg.get("content"):
            return False, f"Message at index {i} content cannot be empty"
        
        # Toggle expected role
        expected_role = "assistant" if expected_role == "user" else "user"
        
    return True, ""

def count_words_and_tokens(chat: Dict[str, Any]) -> Tuple[int, int]:
    """
    Counts words and estimates token count for all message contents.
    Formula: 1 word ≈ 1.3 tokens (heuristic for mixed English/Hindi datasets).
    """
    word_count = 0
    messages = chat.get("messages", [])
    for msg in messages:
        content = msg.get("content", "")
        if content:
            # Simple whitespace/word split
            words = content.split()
            word_count += len(words)
            
    # Estimate tokens: 1.3 tokens per word is a standard heuristic.
    # We round up to be safe.
    estimated_tokens = int(word_count * 1.3)
    return word_count, estimated_tokens

def calculate_jaccard_similarity(chat1: Dict[str, Any], chat2: Dict[str, Any]) -> float:
    """
    Calculates Jaccard similarity of words across user and assistant turns
    to identify near-duplicate chats.
    """
    def extract_words(chat: Dict[str, Any]) -> set:
        text = []
        for msg in chat.get("messages", []):
            if msg.get("role") in ["user", "assistant"]:
                content = msg.get("content", "")
                if content:
                    text.append(content.lower())
        joined_text = " ".join(text)
        # Use regex to find alphanumeric tokens, filtering out short/common tokens
        words = re.findall(r'\b\w{2,}\b', joined_text)
        return set(words)
        
    words1 = extract_words(chat1)
    words2 = extract_words(chat2)
    
    if not words1 and not words2:
        return 0.0
        
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union)

def check_safety_rules_regex(chat: Dict[str, Any]) -> List[str]:
    """
    Finds violations of safety rules using regex pattern matching.
    Looks for:
    1. Death or illness predictions
    2. Promises of medical/money results (guaranteed outcomes)
    3. Remedy upselling pressure
    """
    violations = []
    
    # 1. Death / Illness Prediction Patterns
    death_illness_patterns = [
        # English patterns
        r"\b(die|death|dying|fatal|lifespan|killed)\b",
        r"\b(cancer|heart attack|stroke|illness|disease|diabetes|accident|injury)\b",
        r"\b(cure|cured|healing) (your|his|her) (cancer|disease|illness)\b",
        r"\b(predict|foresee) (when|date of) death\b",
        # Hindi / Hinglish patterns (transliterated)
        r"\b(maut|mrityu|marne|mrega|mregi|marega|maregi|bimar|bimari|rog|la-ilaaj)\b",
        r"\b(swasthya|bimari) (theek|cured)\b",
    ]
    
    # 2. Medical / Financial Outcomes Guaranteed Patterns
    outcomes_patterns = [
        # English patterns
        r"\b(guarantee|guaranteed|promise|100% cure|100% success|sure shot|absolute result)\b",
        r"\b(lottery|jackpot|casino|satta|stock market|wealth overnight|rich overnight)\b",
        r"\b(make you|become) (millionaire|billionaire|rich)\b",
        # Hindi / Hinglish patterns
        r"\b(guarantee|pakka|daawa|100%|dhan labh|ameer|crorepati|lakhpati|lottery)\b",
        r"\b(chamatkar|karishma|magic)\b",
    ]
    
    # 3. Remedy Upselling / Pressure Patterns
    upsell_patterns = [
        # English patterns
        r"\b(must buy|must pay|remedy cost|pay for remedy|buy this gem|purchase puja)\b",
        r"\b(transfer money|only solution is to buy|cost of remedy|remedy price)\b",
        r"\b(pay me|charge you) .* (puja|havan|gemstone|remedy)\b",
        # Hindi / Hinglish patterns
        r"\b(khareed|purchase|khareedna|kharidna|paisa do|puja karvao|paise kharch|shanti puja cost|upay ke paise)\b",
        r"\b(kimat|daam|fees) .* (stone|nag|gem|puja|upay)\b",
    ]
    
    # We inspect assistant messages in detail because that's where the astrologer communicates guidelines.
    for msg in chat.get("messages", []):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if not content:
            continue
            
        # Check rule 1
        for pattern in death_illness_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                violations.append("Predicting death or illness")
                break
                
        # Check rule 2
        for pattern in outcomes_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                violations.append("Promising medical/financial results")
                break
                
        # Check rule 3
        for pattern in upsell_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                violations.append("Pressuring user to pay for remedies")
                break
                
    return list(set(violations))

def check_safety_rules_llm(chat: Dict[str, Any], api_key: str = None, api_base: str = None, model: str = None) -> List[str]:
    """
    Calls an LLM to evaluate the safety of the chat. This acts as a context-aware
    safeguard that catches nuances regular expressions might miss or falsely flag.
    """
    # pyrefly: ignore [missing-import]
    from openai import OpenAI
    
    resolved_api_key = api_key or os.environ.get("TOGETHER_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if not resolved_api_key:
        print("Warning: No API key provided for LLM safety check. Falling back to rule-based flags only.")
        return []
        
    try:
        client = OpenAI(
            api_key=resolved_api_key,
            base_url=api_base or os.environ.get("OPENAI_API_BASE", "https://api.together.xyz/v1")
        )
        
        # Default model for Together AI (DeepSeek-V3 or similar)
        model_name = model or os.environ.get("OPENAI_MODEL", "deepseek-ai/DeepSeek-V3")
        if not model_name and "together.xyz" in (api_base or ""):
            model_name = "deepseek-ai/DeepSeek-V3"
        elif not model_name:
            model_name = "gpt-4o-mini"
            
        transcript = ""
        for msg in chat.get("messages", []):
            role = msg.get("role", "").capitalize()
            content = msg.get("content", "")
            transcript += f"{role}: {content}\n"
            
        prompt = f"""You are a safety audit AI system for Vedaz, an astrology application.
Your task is to analyze the conversation between a user and an astrology assistant and determine if the assistant violated any safety rules.

Here are the strict safety rules the assistant MUST follow:
1. NO DEATH OR ILLNESS PREDICTIONS: Do not predict when someone will die, when they will fall sick, diagnose medical conditions, or promise to cure diseases.
2. NO GUARANTEED MEDICAL/FINANCIAL RESULTS: Do not promise guaranteed outcomes, tell the user they will win a lottery/jackpot, or promise overnight wealth.
3. NO REMEDY UP-SELLING PRESSURE: Do not pressure the user to buy expensive remedies, gems, or custom rituals. Remedies should only be suggested gently and should never be commercialized or forced.

Below is the chat transcript:
---
{transcript}
---

Review the transcript. If the assistant violated any of the safety rules, output a JSON array of strings describing the violations.
If there are no violations, output an empty JSON array [].
Your output MUST be ONLY a JSON array, for example: ["Predicting death or illness"] or []. Do not include any other markdown formatting or conversational text.
"""

        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"} if "gpt-" in model_name else None
        )
        content = response.choices[0].message.content.strip()
        # Clean markdown wrappers if present
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        data = json.loads(content)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "violations" in data:
            return data["violations"]
        return []
    except Exception as e:
        print(f"Warning: LLM safety check failed: {e}. Falling back to rule-based flags only.")
        return []

def analyze_chats(
    input_file: str, 
    use_llm: bool = False, 
    api_key: str = None, 
    api_base: str = None,
    model: str = None,
    duplicate_threshold: float = 0.85
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Reads chats from a .jsonl file, runs validations, safety checks, and duplicate detection.
    Returns:
        valid_chats: Chats that are well-formed and safe.
        invalid_chats: Chats that failed structure or safety rules.
    """
    valid_chats = []
    invalid_chats = []
    
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")
        
    all_chats = []
    with open(input_file, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                chat = json.loads(line)
                chat["_line_number"] = idx
                all_chats.append(chat)
            except json.JSONDecodeError as e:
                print(f"Skipping line {idx}: Invalid JSON: {e}")
                
    total_chats = len(all_chats)
    print(f"Analyzing {total_chats} chats from {input_file}...\n")
    
    # 1. Structure check
    structured_chats = []
    for chat in all_chats:
        is_ok, reason = validate_structure(chat)
        if not is_ok:
            chat["_errors"] = [f"Structure error: {reason}"]
            invalid_chats.append(chat)
        else:
            chat["_errors"] = []
            structured_chats.append(chat)
            
    print(f"[OK] Structure Validation: {len(structured_chats)} / {total_chats} chats are well-formed.")
    if len(invalid_chats) > 0:
        print(f"[ERR] Structure Violations: {len(invalid_chats)} chats failed.")
        for c in invalid_chats:
            print(f"  Line {c['_line_number']}: {c['_errors'][0]}")
            
    # 2. Near-duplicate detection among well-formed chats
    duplicates_flagged = set()
    for i in range(len(structured_chats)):
        for j in range(i + 1, len(structured_chats)):
            sim = calculate_jaccard_similarity(structured_chats[i], structured_chats[j])
            if sim >= duplicate_threshold:
                line_i = structured_chats[i]["_line_number"]
                line_j = structured_chats[j]["_line_number"]
                print(f"[WARN] Near-duplicates found: Line {line_i} and Line {line_j} (similarity: {sim:.2%})")
                duplicates_flagged.add(j) # Flag the second one
                
    # 3. Safety checks
    print(f"\nRunning safety audits...")
    for idx, chat in enumerate(structured_chats):
        violations = check_safety_rules_regex(chat)
        
        # If regex flags it or use_llm is requested, do LLM audit
        if (violations or use_llm) and api_key:
            print(f"  Performing context-aware LLM safety verification on Chat at line {chat['_line_number']}...")
            llm_violations = check_safety_rules_llm(chat, api_key, api_base, model)
            # Combine violations, prioritizing LLM's nuanced judgement
            violations = list(set(violations + llm_violations))
            
        if violations:
            chat["_errors"].extend(violations)
            
    # Final categorization
    for idx, chat in enumerate(structured_chats):
        line_num = chat["_line_number"]
        is_duplicate = idx in duplicates_flagged
        
        if is_duplicate:
            chat["_errors"].append("Duplicate or near-duplicate chat")
            
        if chat["_errors"]:
            invalid_chats.append(chat)
        else:
            valid_chats.append(chat)
            
    print(f"\nAnalysis Summary:")
    print(f"  Total chats read: {total_chats}")
    print(f"  Valid & Safe chats: {len(valid_chats)}")
    print(f"  Flagged / Invalid chats: {len(invalid_chats)}")
    
    if len(invalid_chats) > 0:
        print("\nFlagged Chats Details:")
        for chat in invalid_chats:
            print(f"  Line {chat.get('_line_number', 'unknown')}: {', '.join(chat['_errors'])}")
            
    return valid_chats, invalid_chats

def split_dataset(chats: List[Dict[str, Any]], test_ratio: float = 0.2, seed: int = 42) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Splits chats into a train set and a test set deterministically.
    """
    import random
    # Create a copy and shuffle using the seed
    temp_chats = list(chats)
    random.seed(seed)
    random.shuffle(temp_chats)
    
    test_size = int(len(temp_chats) * test_ratio)
    test_set = temp_chats[:test_size]
    train_set = temp_chats[test_size:]
    
    return train_set, test_set

def main():
    parser = argparse.ArgumentParser(description="Vedaz Astrological Chat Verification & Safety Suite")
    parser.add_argument("input_file", help="Path to the JSONL file containing chats")
    parser.add_argument("--use-llm", action="store_true", help="Trigger LLM check on all chats (requires API key)")
    parser.add_argument("--api-key", help="API key for Together AI / OpenAI / DeepSeek (overrides env variables)")
    parser.add_argument("--api-base", help="Base URL for the API provider (overrides env variables)")
    parser.add_argument("--model", help="LLM model name (overrides env variables)")
    parser.add_argument("--split-test-ratio", type=float, default=0.2, help="Ratio for the test split (default: 0.2)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for splitting datasets (default: 42)")
    parser.add_argument("--out-dir", default=".", help="Directory to save train/test splits (default: current dir)")
    parser.add_argument("--duplicate-threshold", type=float, default=0.85, help="Jaccard similarity threshold for near-duplicates")
    
    args = parser.parse_args()
    
    # Extract API details
    api_key = args.api_key or os.environ.get("TOGETHER_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    api_base = args.api_base or os.environ.get("TOGETHER_API_BASE") or os.environ.get("OPENAI_API_BASE") or os.environ.get("DEEPSEEK_API_BASE")
    model = args.model or os.environ.get("OPENAI_MODEL")
    
    try:
        valid_chats, invalid_chats = analyze_chats(
            input_file=args.input_file,
            use_llm=args.use_llm,
            api_key=api_key,
            api_base=api_base,
            model=model,
            duplicate_threshold=args.duplicate_threshold
        )
        
        # Save valid chats splits
        if valid_chats:
            train_set, test_set = split_dataset(valid_chats, test_ratio=args.split_test_ratio, seed=args.seed)
            
            # Remove helper keys before saving
            for c in train_set + test_set:
                c.pop("_line_number", None)
                c.pop("_errors", None)
                
            train_path = os.path.join(args.out_dir, "train.jsonl")
            test_path = os.path.join(args.out_dir, "test.jsonl")
            
            with open(train_path, 'w', encoding='utf-8') as f:
                for chat in train_set:
                    f.write(json.dumps(chat, ensure_ascii=False) + "\n")
                    
            with open(test_path, 'w', encoding='utf-8') as f:
                for chat in test_set:
                    f.write(json.dumps(chat, ensure_ascii=False) + "\n")
                    
            print(f"\n[OK] Dataset Split Complete:")
            print(f"  Training set saved to: {train_path} ({len(train_set)} chats)")
            print(f"  Testing set saved to: {test_path} ({len(test_set)} chats)")
        else:
            print("\nWarning: No valid and safe chats found. Split was skipped.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
