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
    api_url = GROQ_API_URL
    model_name = MODEL_NAME
    headers = {"Content-Type": "application/json"}
    
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        print("[LLM WARN] Missing GROQ_API_KEY. Engaging local Ollama fallback (llama3.1)...")
        api_url = "http://localhost:11434/v1/chat/completions"
        model_name = "llama3.1"

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You must reply ONLY with a valid JSON object. No other text."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.0
    }
    
    import ssl
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)
    async with aiohttp.ClientSession(connector=connector) as session:
        for attempt in range(max_retries):
            try:
                async with session.post(api_url, headers=headers, json=payload) as response:
                    if response.status != 200:
                        err_text = await response.text()
                        print(f"[LLM ERROR] HTTP {response.status}: {err_text}")
                        if "localhost" in api_url:
                            return {
                                "next_state": "IDLE", "action": "SPEAK", 
                                "tool_name": None, "tool_args": None,
                                "response": "GROQ API KEY is missing and local Ollama is down. Please set your GROQ API KEY in the terminal or start Ollama."
                            }
                        continue
                        
                    result = await response.json()
                    raw_text = result["choices"][0]["message"]["content"]
                    print(f"\\n[LLM RAW] {raw_text}")
                    
                    json_str = _extract_json(raw_text) or raw_text
                    parsed = json.loads(json_str)
                    
                    if not isinstance(parsed, dict):
                        print(f"[LLM ERROR] Response is not a dict: {parsed}")
                        continue
                        
                    return parsed
                    
            except Exception as e:
                print(f"[LLM ERROR] {type(e).__name__}: {str(e)}")
                
    err_msg = "I apologize, our cloud reasoning engine timed out. Let's try that again."
    if "localhost" in api_url:
        err_msg = "GROQ API KEY is missing and local Ollama is down. Please set your GROQ API KEY in the terminal or start Ollama."

    return {
        "next_state": "IDLE",
        "action": "SPEAK",
        "tool_name": None,
        "tool_args": None,
        "response": err_msg
    }
