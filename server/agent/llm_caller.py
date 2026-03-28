import json
import re
import aiohttp
import os
from typing import Dict, Any, Optional

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
# Using Llama 3.1 8B instant to bypass decommissioned and rate-limited 70B endpoints
MODEL_NAME = "llama-3.1-8b-instant"

def _extract_json(text: str) -> Optional[str]:
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return match.group(0)
    return None

async def call_llm(prompt: str, max_retries: int = 3) -> Dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("[LLM ERROR] Missing GROQ_API_KEY in environment variables.")
        return {
            "next_state": "IDLE", "action": "SPEAK", 
            "tool_name": None, "tool_args": None,
            "response": "Please set your GROQ API KEY in the terminal before continuing."
        }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You must reply ONLY with a valid JSON object. No other text."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.0
    }
    
    async with aiohttp.ClientSession() as session:
        for attempt in range(max_retries):
            try:
                async with session.post(GROQ_API_URL, headers=headers, json=payload) as response:
                    if response.status != 200:
                        err_text = await response.text()
                        print(f"[LLM ERROR] HTTP {response.status}: {err_text}")
                        continue
                        
                    result = await response.json()
                    raw_text = result["choices"][0]["message"]["content"]
                    print(f"\\n[LLM RAW] {raw_text}")
                    
                    json_str = _extract_json(raw_text) or raw_text
                    parsed = json.loads(json_str)
                    
                    required_keys = {"next_state", "action"}
                    if not required_keys.issubset(parsed.keys()):
                        print(f"[LLM ERROR] Missing keys: {parsed.keys()}")
                        continue
                        
                    parsed.setdefault("tool_name", None)
                    parsed.setdefault("tool_args", None)
                    parsed.setdefault("response", None)
                    parsed.setdefault("extracted_info", {})
                    return parsed
                    
            except Exception as e:
                print(f"[LLM ERROR] {type(e).__name__}: {str(e)}")
                
    return {
        "next_state": "IDLE",
        "action": "SPEAK",
        "tool_name": None,
        "tool_args": None,
        "response": "I apologize, our cloud reasoning engine timed out. Let's try that again."
    }
