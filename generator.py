#!/usr/bin/env python3
import json
import os
import argparse
from openai import OpenAI
import checker  # Import the checker functions from Task 1

# List of topics/situations for generating diverse sample chats
DEFAULT_SITUATIONS = [
    {"topic": "career delay and job change", "language": "Hindi", "tone": "anxious"},
    {"topic": "marriage compatibility", "language": "English", "tone": "skeptical"},
    {"topic": "financial stability and debt recovery", "language": "Hindi", "tone": "stressed"},
    {"topic": "education prospects abroad", "language": "English", "tone": "ambitious"},
    {"topic": "relationship conflict with partner", "language": "Hindi", "tone": "heartbroken"},
    {"topic": "business expansion timing", "language": "English", "tone": "cautious"},
    {"topic": "Sade Sati fears and anxiety", "language": "English", "tone": "scared"},
    {"topic": "spiritual growth and meditation path", "language": "Hindi", "tone": "seeking peace"},
    {"topic": "buying a house and property timing", "language": "English", "tone": "excited"},
    {"topic": "health worries and lifestyle suggestions", "language": "Hindi", "tone": "worried"},
    {"topic": "career change to creative arts", "language": "English", "tone": "unsure"},
    {"topic": "child's education and future prospects", "language": "Hindi", "tone": "hopeful"}
]

SYSTEM_PROMPT = """You are a synthetic chat generator for Vedaz, a premium Vedic astrology application. 
Your task is to generate a realistic, high-quality, and complete chat transcript between a user and the Vedaz Astrology Assistant.

The Vedaz Assistant has a very distinct voice:
- Warm, empathetic, spiritually grounded, yet highly professional.
- Explains planetary influences (e.g., Dashas, Transits, Grahas, houses) clearly without using heavy jargon.
- Emphasizes personal agency and Karma. Astrology is a guide, not a fatalistic decree.
- STRICTLY SAFE: The assistant never predicts death, never diagnoses physical or mental illness, never promises guaranteed lottery/wealth, and never pressures users to buy expensive remedies, rituals, or gemstones. Gentle, non-commercial remedies (like chants, charity, or simple lifestyle modifications) are acceptable, but never commercialized.

You must output a complete, realistic, alternating chat transcript in JSON format. The JSON must have exactly one root key: "messages".
The "messages" list must contain:
1. A "system" message at index 0 which sets the persona of the Vedaz Astrology Assistant.
2. Alternating "user" and "assistant" messages starting from index 1.
3. The conversation should be 4 to 8 turns total.

Topic/Situation to generate:
- Topic: {topic}
- Language: {language} (If Hindi, write in transliterated Hindi/Hinglish or standard Devnagri as appropriate for chat, but conversational Hinglish/Hindi mixed with English is preferred for modern users. If English, use warm professional English).
- User Tone: {tone}

Output format:
{
  "messages": [
    {"role": "system", "content": "Assistant system instructions here..."},
    {"role": "user", "content": "First user message here..."},
    {"role": "assistant", "content": "First assistant reply here..."},
    ...
  ]
}

DO NOT include any markdown code fences (like ```json) or explanation outside the JSON object. Output ONLY the raw JSON.
"""

def generate_chat(
    client: OpenAI, 
    model: str, 
    situation: dict
) -> dict:
    """
    Generates a single chat log from the LLM based on the situation.
    """
    prompt = SYSTEM_PROMPT.format(
        topic=situation["topic"],
        language=situation["language"],
        tone=situation["tone"]
    )
    
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        response_format={"type": "json_object"} if "gpt-" in model else None
    )
    
    content = response.choices[0].message.content.strip()
    
    # Clean code block wrappers if the model includes them
    if content.startswith("```json"):
        content = content[7:-3].strip()
    elif content.startswith("```"):
        content = content[3:-3].strip()
        
    chat_data = json.loads(content)
    return chat_data

def main():
    parser = argparse.ArgumentParser(description="Vedaz Synthetic Chat Generator")
    parser.add_argument("--count", type=int, default=10, help="Number of valid chats to generate (default: 10)")
    parser.add_argument("--api-key", help="API key for Together AI / OpenAI / DeepSeek")
    parser.add_argument("--api-base", help="Base URL for the API provider")
    parser.add_argument("--model", help="LLM model name")
    parser.add_argument("--out-file", default="generated_chats.jsonl", help="Output JSONL file path")
    parser.add_argument("--use-llm-checker", action="store_true", help="Use LLM inside the checker for safety verification")
    
    args = parser.parse_args()
    
    # Extract API configuration
    api_key = args.api_key or os.environ.get("TOGETHER_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    api_base = args.api_base or os.environ.get("TOGETHER_API_BASE") or os.environ.get("OPENAI_API_BASE") or os.environ.get("DEEPSEEK_API_BASE")
    model_name = args.model or os.environ.get("OPENAI_MODEL")
    
    if not api_key:
        print("Error: API Key is required. Please set TOGETHER_API_KEY, OPENAI_API_KEY, or DEEPSEEK_API_KEY in your environment, or pass --api-key.")
        return
        
    if not api_base:
        # Default base URL
        api_base = "https://api.together.xyz/v1"
        print(f"No API base URL provided, defaulting to: {api_base}")
        
    if not model_name:
        if "together.xyz" in api_base:
            model_name = "deepseek-ai/DeepSeek-V3"
        else:
            model_name = "gpt-4o-mini"
        print(f"No model name provided, defaulting to: {model_name}")
        
    client = OpenAI(api_key=api_key, base_url=api_base)
    
    print(f"Initializing generation loop using model '{model_name}'...")
    valid_chats = []
    attempts = 0
    max_attempts = args.count * 3
    
    # Cycle through our situations
    situation_idx = 0
    
    while len(valid_chats) < args.count and attempts < max_attempts:
        attempts += 1
        situation = DEFAULT_SITUATIONS[situation_idx % len(DEFAULT_SITUATIONS)]
        situation_idx += 1
        
        print(f"\n[Attempt {attempts}] Generating chat for topic: '{situation['topic']}' ({situation['language']}, {situation['tone']} user)...")
        
        try:
            chat = generate_chat(client, model_name, situation)
            
            # Run checker rules
            is_valid_structure, struct_error = checker.validate_structure(chat)
            if not is_valid_structure:
                print(f"  [ERR] Rejected: Structure error - {struct_error}")
                continue
                
            # Run safety checker
            violations = checker.check_safety_rules_regex(chat)
            if (violations or args.use_llm_checker):
                print("  Running advanced safety checks...")
                llm_violations = checker.check_safety_rules_llm(chat, api_key, api_base, model_name)
                violations = list(set(violations + llm_violations))
                
            if violations:
                print(f"  [ERR] Rejected: Safety violation(s) - {', '.join(violations)}")
                continue
                
            # Count words/tokens
            words, tokens = checker.count_words_and_tokens(chat)
            print(f"  [OK] Valid structure & safety! Length: {words} words (~{tokens} tokens).")
            
            # Store metadata
            chat["metadata"] = {
                "topic": situation["topic"],
                "language": situation["language"],
                "tone": situation["tone"],
                "word_count": words,
                "estimated_tokens": tokens
            }
            valid_chats.append(chat)
            print(f"  Progress: {len(valid_chats)} / {args.count} chats collected.")
            
        except Exception as e:
            print(f"  [ERR] Error during generation/validation: {e}")
            
    # Save output to .jsonl
    if valid_chats:
        with open(args.out_file, 'w', encoding='utf-8') as f:
            for chat in valid_chats:
                # Remove temporary metadata if needed, but keeping it in root is fine or standard
                f.write(json.dumps(chat, ensure_ascii=False) + "\n")
        print(f"\n[OK] Completed! Successfully wrote {len(valid_chats)} valid chats to '{args.out_file}'.")
    else:
        print("\n[ERR] Failed to generate any valid chats. Please check API settings or model outputs.")

if __name__ == "__main__":
    main()
