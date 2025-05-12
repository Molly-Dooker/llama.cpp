import assemblyai as aai
import time
import ipdb
aai.settings.api_key = "eb7798f0e37d414a8435b42c17a20b58"

# audio_file = "./local_file.mp3"
audio_file = "test2.mp3"

config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.best)
s = time.time()
transcript = aai.Transcriber(config=config).transcribe(audio_file)
e = time.time()
if transcript.status == "error":
  raise RuntimeError(f"Transcription failed: {transcript.error}")
ipdb.set_trace()
print(transcript.text)