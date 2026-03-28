import json
import re
import aiohttp
from typing import Dict, Any, Optional

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral:instruct"

def _extract_json(text: str) -> Optional[str]:
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return match.group(0)
    return None

async def call_llm(prompt: str, max_retries: int = 3) -> Dict[str, Any]:
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1
        }
    }
    
    async with aiohttp.ClientSession() as session:
        for _ in range(max_retries):
            try:
                async with session.post(OLLAMA_URL, json=payload) as response:
                    if response.status != 200:
                        continue
                        
                    result = await response.json()
                    raw_text = result.get("response", "")
                    print(f"\\n[LLM RAW HTTP 200] {raw_text}")
                    
                    json_str = _extract_json(raw_text)
                    if not json_str:
                        print("[LLM ERROR] No JSON block found in response")
                        continue
                        
                    parsed = json.loads(json_str)
                    
                    required_keys = {"next_state", "action"}
                    if not required_keys.issubset(parsed.keys()):
                        print(f"[LLM ERROR] Missing required keys. Found: {parsed.keys()}")
                        continue
                        
                    # Safely default dropped hallucinated tokens back to None
                    parsed.setdefault("tool_name", None)
                    parsed.setdefault("tool_args", None)
                    parsed.setdefault("response", None)
                    return parsed
                    
            except Exception as e:
                print(f"[LLM HTTP OR PARSE ERROR] {type(e).__name__}: {str(e)}")
                pass
                
    return {
        "next_state": "IDLE",
        "action": "SPEAK",
        "tool_name": None,
        "tool_args": None,
        "response": "I apologize, but I am having trouble processing your request right now."
    }
