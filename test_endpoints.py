import os
import json
import urllib.request
import urllib.error
from dotenv import load_dotenv
import sys

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

API_KEY = os.getenv("API_LLM_OLLAMA_API_KEY")
BASE_URL = os.getenv("API_LLM_OLLAMA_BASE_URL", "https://ollama.com/api")
VLM_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:31b-cloud")
LLM_MODEL = os.getenv("API_LLM_OLLAMA_MODEL", "gemma3:4b-cloud")

print(f"API Key Starts with: {API_KEY[:8]}***")
print(f"Base URL: {BASE_URL}")
print(f"VLM Model: {VLM_MODEL}")
print(f"LLM Model: {LLM_MODEL}")
print("-" * 50)

def test_endpoint(model, role, prompt, test_name):
    print(f"Testing {test_name} ({model})...")
    url = f"{BASE_URL}/chat"
    data = {
        "model": model,
        "messages": [
            {"role": role, "content": prompt}
        ],
        "stream": False
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            reply = result.get("message", {}).get("content", "")
            print(f"[Success] Response preview: {reply[:100]}...\n")
    except urllib.error.HTTPError as e:
        print(f"[HTTP Error] {e.code} {e.reason}")
        print(f"Body: {e.read().decode('utf-8')}\n")
    except Exception as e:
        print(f"[Error] {e}\n")

# 1. Test LLM
llm_prompt = "안녕하세요! 연결이 잘 되었는지 확인하기 위한 테스트 메시지입니다. 짧게 인사해주세요."
test_endpoint(LLM_MODEL, "user", llm_prompt, "LLM Pipeline")

# 2. Test VLM
vlm_prompt = "이것은 VLM 파이프라인 테스트입니다. 'VLM 연결 성공!' 이라고만 답해주세요."
test_endpoint(VLM_MODEL, "user", vlm_prompt, "VLM Pipeline")
