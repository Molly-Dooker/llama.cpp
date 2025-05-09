from flask import Flask, render_template, request, Response, stream_with_context
import requests
import json
import time

app = Flask(__name__)
LLAMA_SERVER_URL = "http://localhost:8080/v1/chat/completions"

@app.route("/")
def index():
    return render_template("chat.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_input = data.get("prompt", "")

    payload = {
        "model": "model.gguf",  # llama-server 실행 시 모델 이름과 일치해야 함
        "messages": [{"role": "user", "content": user_input}],
        "stream": True
    }

    def generate():
        yield f"🧑‍💻 {user_input}\n🤖 "
        token_count = 0
        start_time = time.time()

        with requests.post(LLAMA_SERVER_URL, json=payload, stream=True, timeout=60) as r:
            for line in r.iter_lines():
                if line and line.startswith(b"data: "):
                    content = json.loads(line[6:].decode("utf-8"))
                    delta = content["choices"][0]["delta"].get("content", "")
                    if delta:
                        token_count += len(delta.strip().split())
                        yield delta
                        elapsed = time.time() - start_time
                        if elapsed > 0:
                            tps = token_count / elapsed
                            yield f"<tps>{tps:.2f}</tps>"

    return Response(stream_with_context(generate()), content_type="text/plain")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
