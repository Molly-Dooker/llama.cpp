from flask import Flask, render_template, Response, stream_with_context
import requests
import json
import time

app = Flask(__name__)
LLAMA_SERVER_URL = "http://localhost:8080/v1/chat/completions"
SCRIPT_PATH = "script.txt"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/run", methods=["POST"])
def run_all():
    def generate():
        with open(SCRIPT_PATH, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        for line in lines:
            prompt = line
            payload = {
                "model": "model.gguf",
                "messages": [{"role": "user", "content": prompt}],
                "stream": True
            }

            yield f"\n\n🧑‍💻 Prompt: {prompt}\n🤖 Response: "

            start_time = time.time()
            token_count = 0

            with requests.post(LLAMA_SERVER_URL, json=payload, stream=True) as r:
                for chunk in r.iter_lines():
                    if chunk and chunk.startswith(b"data: "):
                        try:
                            content = json.loads(chunk[6:].decode("utf-8"))
                            delta = content["choices"][0]["delta"].get("content", "")
                            token_count += len(delta.strip().split())
                            yield delta
                            elapsed = time.time() - start_time
                            if elapsed > 0:
                                tps = token_count / elapsed
                                yield f"<tps>{tps:.2f}</tps>"
                        except Exception:
                            continue

    return Response(stream_with_context(generate()), content_type="text/plain")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)