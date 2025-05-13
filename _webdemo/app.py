from flask import Flask, render_template, request, Response, stream_with_context, jsonify
import requests
import json
import time
import os
from pydub import AudioSegment
import pydub.exceptions # pydub 예외를 명시적으로 임포트
import tempfile # 임시 파일 생성을 위해 임포트
# import assemblyai as aai # AssemblyAI는 더 이상 사용하지 않음
import openai # OpenAI 라이브러리 유지

app = Flask(__name__)
LLAMA_SERVER_URL = "http://localhost:8080/v1/chat/completions"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("경고: OPENAI_API_KEY 환경 변수가 설정되지 않았습니다. STT 및 TTS 기능이 제한될 수 있습니다.")
else:
    openai.api_key = OPENAI_API_KEY # OpenAI 라이브러리에 API 키 설정


def transcribe_audio_openai(audio_file_path):
    if not OPENAI_API_KEY: # openai.api_key로 확인해도 됨
        return None, "OpenAI API 키가 설정되지 않았습니다."
    try:
        client = openai.OpenAI() # API 키는 환경 변수 또는 openai.api_key로 설정된 것을 사용
        with open(audio_file_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio_file
            )
        if hasattr(transcription, 'text'):
            return transcription.text, None
        else:
            print(f"DEBUG: OpenAI STT 응답 형식 불일치: {transcription}")
            return None, "OpenAI STT 응답에서 텍스트를 찾을 수 없습니다."
    except openai.APIError as e:
        print(f"OpenAI STT API 오류: {e}")
        error_message = f"STT API 오류: {e.status_code}"
        if hasattr(e, 'message'): error_message += f" - {e.message}"
        return None, error_message
    except Exception as e:
        print(f"STT 변환 중 일반 오류 발생: {type(e).__name__} - {e}")
        return None, f"STT 변환 중 오류 발생: {str(e)}"



def synthesize_speech_openai(text_to_synthesize, voice="alloy"):
    """
    OpenAI TTS API를 사용하여 텍스트를 음성으로 변환합니다.
    """
    print(text_to_synthesize)
    if not openai.api_key:
        return None, "OpenAI API 키가 설정되지 않았습니다."
    try:
        client = openai.OpenAI()
        response = client.audio.speech.create(
            model="gpt-4o-mini-tts",  # 또는 "tts-1-hd"
            voice=voice,    # 사용 가능한 목소리: alloy, echo, fable, onyx, nova, shimmer
            input=text_to_synthesize,
            response_format="mp3" # 기본값 mp3, 다른 옵션: opus, aac, flac
        )
        # response.content에 오디오 데이터가 들어있음
        return response.content, None
    except openai.APIError as e:
        print(f"OpenAI TTS API 오류: {e}")
        error_message = f"TTS API 오류: {e.status_code}"
        if hasattr(e, 'message'): error_message += f" - {e.message}"
        return None, error_message
    except Exception as e:
        print(f"TTS 생성 중 일반 오류 발생: {type(e).__name__} - {e}")
        return None, f"TTS 생성 중 오류 발생: {str(e)}"

@app.route("/")
def index():
    return render_template("chat.html")

@app.route("/synthesize_speech", methods=["POST"])
def synthesize_speech_route():
    data = request.json
    text_to_synthesize = data.get("text", "")
    voice_preference = data.get("voice", "nova") # 클라이언트에서 목소리 선호도를 받을 수 있음

    if not text_to_synthesize:
        return jsonify({"error": "TTS를 위한 텍스트가 제공되지 않았습니다."}), 400

    if not openai.api_key: # 함수 호출 전에 한 번 더 키 확인
        return jsonify({"error": "OpenAI API 키가 서버에 설정되지 않았습니다."}), 500

    audio_content, error = synthesize_speech_openai(text_to_synthesize, voice=voice_preference)

    if error:
        return jsonify({"error": error}), 500

    return Response(audio_content, mimetype="audio/mpeg") # MP3 포맷으로 응답

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_input = data.get("prompt", "")

    payload = {
        "model": "model.gguf", # 실제 사용하는 모델명으로 변경 필요
        "messages": [{"role": "user", "content": user_input}],
        "stream": True
    }

    def generate():
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
                                    token_count += len(delta.strip().split())
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
    temp_file_path = None

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

        # OpenAI STT 함수 사용
        transcribed_text, transcription_error = transcribe_audio_openai(target_filename)

        if transcription_error:
            print(f"ERROR_TRANSCRIPTION: {transcription_error}")
            return jsonify({
                "message": f"'{target_filename}'에 오디오가 저장되었으나, STT 변환에 실패했습니다: {transcription_error}",
                "file_saved": True,
                "transcribed_text": None
            }), 200

        if transcribed_text is not None and transcribed_text.strip() != '':
            print(f"INFO: 오디오 STT 변환 결과: {transcribed_text}")
            return jsonify({
                "message": f"'{target_filename}'에 오디오가 저장 및 STT 변환되었습니다.",
                "file_saved": True,
                "transcribed_text": transcribed_text
            }), 200
        else:
             print(f"INFO: STT 변환 결과가 없습니다. (결과: '{transcribed_text}')")
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
            try:
                os.remove(temp_file_path)
                print(f"DEBUG: 임시 파일 삭제: {temp_file_path}")
            except Exception as e_remove:
                print(f"ERROR: 임시 파일 삭제 중 오류: {e_remove}")
        # target_filename (record.mp3)은 STT/TTS 처리 후 필요에 따라 삭제할 수 있습니다.
        # 현재는 유지됩니다.

if __name__ == "__main__":
    if not OPENAI_API_KEY:
        print("="*50)
        print("경고: OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
        print("OpenAI STT 및 TTS 기능을 사용하려면 API 키를 설정해야 합니다.")
        print("예: export OPENAI_API_KEY=\"sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\"")
        print("="*50)
    app.run(host="0.0.0.0", port=5000, debug=True)