from flask import Flask, render_template, request, Response, stream_with_context, jsonify
import requests
import json
import time
import os
from pydub import AudioSegment
import pydub.exceptions # pydub 예외를 명시적으로 임포트
import tempfile # 임시 파일 생성을 위해 임포트

app = Flask(__name__)
LLAMA_SERVER_URL = "http://localhost:8080/v1/chat/completions"
import assemblyai as aai
aai.settings.api_key = "eb7798f0e37d414a8435b42c17a20b58"

def transcribe_audio_aai(audio_file_path):    
    config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.best)
    transcript = aai.Transcriber(config=config).transcribe(audio_file_path)
    if transcript.status == "error":
        return None, 'error!'
    else:
        return transcript.text, None
        

@app.route("/")
def index():
    return render_template("chat.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_input = data.get("prompt", "")

    payload = {
        "model": "model.gguf",
        "messages": [{"role": "user", "content": user_input}],
        "stream": True
    }

    def generate():
        # 사용자 입력을 🎤 심볼과 함께 표시 (STT 결과인 경우) 또는 일반 텍스트로 표시
        # 이 부분은 클라이언트에서 처리하므로 서버에서는 그대로 user_input을 사용하거나,
        # 클라이언트에서 STT 결과임을 명시하는 prefix를 붙여서 보내면 여기서도 반영 가능.
        # 현재 클라이언트에서 "🎤: "를 붙이므로 여기서는 특별히 수정하지 않음.
        yield f"🧑‍💻 {user_input}\n🤖 "
        token_count = 0
        start_time = time.time()

        try:
            with requests.post(LLAMA_SERVER_URL, json=payload, stream=True, timeout=60) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if line:
                        if line.startswith(b"data: "):
                            data_str = line[6:].decode("utf-8").strip()
                            if not data_str:
                                continue
                            if data_str == "[DONE]":
                                break
                            try:
                                content = json.loads(data_str)
                                choices = content.get("choices")
                                if choices and isinstance(choices, list) and len(choices) > 0:
                                    delta_obj = choices[0].get("delta", {})
                                    delta = delta_obj.get("content", "")
                                else:
                                    delta = ""
                                if delta:
                                    token_count += len(delta.strip().split()) # 단순 공백 기준 단어 수
                                    yield delta
                                    elapsed = time.time() - start_time
                                    if elapsed > 0:
                                        tps = token_count / elapsed
                                        yield f"<tps>{tps:.2f}</tps>"
                            except json.JSONDecodeError:
                                print(f"DEBUG: JSONDecodeError for line: >>>{data_str}<<< - Skipping.")
                                continue
                            except Exception as e_inner:
                                print(f"DEBUG: Error processing content: {e_inner} for line: >>>{data_str}<<< - Skipping.")
                                continue
        except requests.exceptions.RequestException as e_req:
            print(f"ERROR: Request to LLAMA_SERVER failed: {e_req}")
            yield "LLM 서버 연결에 실패했습니다. 서버 상태를 확인해주세요."
        except Exception as e_outer:
            print(f"ERROR: An unexpected error occurred in generate(): {e_outer}")
            yield "응답 생성 중 예기치 않은 오류가 발생했습니다."
    return Response(stream_with_context(generate()), content_type="text/plain")


@app.route('/upload_audio', methods=['POST'])
def upload_audio():
    if 'audio_data' not in request.files:
        return jsonify({"error": "오디오 파일 부분이 요청에 없습니다.", "file_saved": False, "transcribed_text": None}), 400
    
    file = request.files['audio_data']
    
    if not file or file.filename == '':
        return jsonify({"error": "파일이 비어있거나 선택되지 않았습니다.", "file_saved": False, "transcribed_text": None}), 400
    
    target_filename = "record.mp3"
    temp_file_path = None # 임시 파일 경로 초기화

    try:
        content_type = file.content_type or 'application/octet-stream'
        extension_hint = "." + content_type.split('/')[-1].split(';')[0]
        
        if extension_hint == ".octet-stream":
            extension_hint = ""
        if "webm" in content_type:
            extension_hint = ".webm"
        elif "ogg" in content_type:
            extension_hint = ".ogg"

        with tempfile.NamedTemporaryFile(delete=False, suffix=extension_hint) as temp_f:
            file.save(temp_f.name)
            temp_file_path = temp_f.name
        
        print(f"DEBUG: 오디오 업로드 시도. Content-Type: {content_type}, 임시 파일: {temp_file_path}")

        try:
            print(f"DEBUG: pydub 로드 시도 (자동 포맷 감지): {temp_file_path}")
            audio = AudioSegment.from_file(temp_file_path)
        except pydub.exceptions.CouldntDecodeError:
            explicit_format = content_type.split('/')[-1].split(';')[0]
            if explicit_format == "opus" and "webm" in content_type:
                explicit_format = "webm"
            elif explicit_format == "opus" and "ogg" in content_type:
                explicit_format = "ogg"

            print(f"DEBUG: pydub 자동 포맷 감지 실패. 명시적 포맷 ({explicit_format})으로 재시도: {temp_file_path}")
            if explicit_format and explicit_format not in ['octet-stream']:
                audio = AudioSegment.from_file(temp_file_path, format=explicit_format)
            else:
                raise
        
        audio.export(target_filename, format="mp3")
        print(f"INFO: 오디오 파일이 '{target_filename}'으로 저장되었습니다.")

        # STT 변환 시도
        transcribed_text, transcription_error = transcribe_audio_aai(target_filename)
        if transcription_error:
            print(f"ERROR_TRANSCRIPTION: {transcription_error}")
            return jsonify({
                "message": f"'{target_filename}'에 오디오가 저장되었으나, STT 변환에 실패했습니다: {transcription_error}",
                "file_saved": True,
                "transcribed_text": None
            }), 200 # 파일 저장은 성공했으므로 200, 클라이언트에서 transcribed_text 유무로 처리
        
        if transcribed_text is not None and transcribed_text is not '':
            print(f"INFO: 오디오 STT 변환 결과: {transcribed_text}")
            return jsonify({
                "message": f"'{target_filename}'에 오디오가 저장 및 STT 변환되었습니다.",
                "file_saved": True,
                "transcribed_text": transcribed_text
            }), 200
        else: # transcribed_text가 None이지만 명시적 오류가 없었던 경우 (예: 빈 오디오)
             return jsonify({
                "message": f"'{target_filename}'에 오디오가 저장되었으나, STT 변환 결과가 없습니다 (예: 음성이 없는 오디오).",
                "file_saved": True,
                "transcribed_text": None
            }), 200

    except pydub.exceptions.CouldntDecodeError as e_decode:
        print(f"ERROR_PYDUB: pydub.exceptions.CouldntDecodeError - 오디오 디코딩 실패: {e_decode}")
        print(f"ERROR_DETAILS: Content-Type: {file.content_type if file else 'N/A'}, 임시 파일 경로 (문제시 유지됨): {temp_file_path}")
        return jsonify({"error": f"MP3로 오디오를 저장하는데 실패했습니다 (디코딩 오류). 오류 유형: CouldntDecodeError", "file_saved": False, "transcribed_text": None}), 500
    except Exception as e:
        print(f"ERROR_GENERAL: 오디오 변환 또는 저장 중 일반 오류 발생: {type(e).__name__} - {e}")
        if temp_file_path:
            print(f"ERROR_DETAILS: Content-Type: {file.content_type if file else 'N/A'}, 임시 파일 경로: {temp_file_path}")
        else:
            print(f"ERROR_DETAILS: Content-Type: {file.content_type if file else 'N/A'}, 임시 파일 생성 전 오류.")
        return jsonify({"error": f"MP3로 오디오를 저장하는데 실패했습니다. 오류 유형: {type(e).__name__}", "file_saved": False, "transcribed_text": None}), 500
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            # CouldntDecodeError 발생 시 디버깅을 위해 임시 파일을 남기려면 아래 라인을 조건부로 실행
            # 현재 로직에서는 모든 경우에 삭제 시도
            try:
                os.remove(temp_file_path)
                print(f"DEBUG: 임시 파일 삭제: {temp_file_path}")
            except Exception as e_remove:
                print(f"ERROR: 임시 파일 삭제 중 오류: {e_remove}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)