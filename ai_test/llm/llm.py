import json
import glob
import os
import requests

# 사용할 클라우드 주소와 LLM 모델명으로 변경하세요
OLLAMA_URL = "http://127.0.0.1:11434"
LLM_MODEL = "gemma2:2b"

# 1. 최신 객체 위치를 파싱하는 함수
def get_all_latest_positions(folder_path):
    # 폴더 내의 모든 json 파일 찾기
    json_files = glob.glob(os.path.join(folder_path, "*.json"))

    if not json_files:
        return "저장된 객체 위치 데이터가 없습니다."

    all_data = []

    # 1단계: 파일 모두 읽기
    for file in json_files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                all_data.append(data)
        except Exception as e:
            print(f"파일 읽기 실패 ({file}): {e}")

    # 2단계: 최신순 정렬 (timestamp 기준 내림차순)
    all_data.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    # 3단계: 최신 데이터부터 보면서 객체 위치 기록하기
    seen_objects = set()
    context_text = "[최근 관측된 물체 위치]\n"

    for data in all_data:
        timestamp = data.get("timestamp", "시간 미상")[:16].replace("T", " ")
        location = data.get("location_context", "위치 미상")

        for obj in data.get("objects", []):
            name = obj.get("name", "이름 없음")

            # 처음 보는 물체(즉 가장 최신 정보)만 기록
            if name not in seen_objects:
                position = obj.get("position", {})
                surface = position.get("surface", "위치 모름")
                nearby = ", ".join(obj.get("nearby_objects", []))
                
                context_text += f"- {name}: {surface}에 위치 (마지막 관측: {timestamp}, 공간: {location} / 주변물체: {nearby})\n"
                seen_objects.add(name)

    if not seen_objects:
        return "발견된 물체가 없습니다."

    return context_text

# 2. Ollama API를 사용하는 챗봇 함수
def ask_smart_vision_chatbot(user_question, target_folder):
    # 1. 최신 위치 정보를 토대로 프롬프트 컨텍스트 생성
    context = get_all_latest_positions(target_folder)

    # 2. 시스템 프롬프트 및 유저 프롬프트 구성
    system_prompt = "당신은 사용자의 물건 위치를 찾아주는 똑똑한 비서입니다. 항상 한국어로 친절하게 대답하세요."
    
    prompt = f"""아래는 카메라가 최근에 관측한 물체들의 위치 기록입니다.
이 기록을 바탕으로 사용자의 질문에 답해주세요.
관측 기록에 없는 물체라면 "해당 물체의 최근 위치를 찾을 수 없습니다."라고 정직하게 말하세요.
시간과 주변 물체 정보를 함께 알려주면 더 좋습니다.

[관측 기록]
{context}

[사용자 질문]
{user_question}"""

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "options": {
            "num_predict": 256,
            "temperature": 0.1
        },
        "stream": False
    }

    try:
        res = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=60)
        res.raise_for_status()
        return res.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        return f"[Ollama LLM 오류] 챗봇 응답에 실패했습니다: {e}"

# --- 테스트 코드 ---
if __name__ == "__main__":
    # pipeline.py에서 결과가 저장되는 폴더 경로
    target_dir = "../../output"
    
    question = "내 맥북 어딨어?"
    print(f"질문: {question}")
    print(f"답변: {ask_smart_vision_chatbot(question, target_dir)}")
