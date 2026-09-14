import httpx

# 不走系统代理，避免 localhost 被代理成 502
with httpx.Client(trust_env=False, timeout=90) as client:
    r = client.post("http://127.0.0.1:8765/tts", json={"text": "hello", "lang": "en"})
    print("tts", r.status_code, r.text[:400])
    r2 = client.post("http://127.0.0.1:8765/translate/file/tts", json={"text": "hello", "lang": "en"})
    print("file", r2.status_code, r2.text[:400])
    r3 = client.post("http://127.0.0.1:8765/translate/text", json={"text": "hi", "source_lang": "en", "target_lang": "zh"})
    print("text", r3.status_code, r3.text[:200])
