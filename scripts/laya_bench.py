import time, laya_mlx as laya
t0=time.time(); agent = laya.load("aac6fef/laya-mlx"); print(f"load {time.time()-t0:.1f}s")
q = {
  "question": {"type":"noul","instructions":"Is this utterance a question the speaker is asking?"},
  "json_term": {"type":"noul","instructions":"Does the word 'jason' here refer to the JSON data format rather than a person?"},
  "language": {"type":"choice","instructions":"What language is this mostly in?","criteria":{"english":"english","tamil":"tamil or tanglish","hindi":"hindi or hinglish","garbage":"not real words, asr failure"}},
  "stumble": {"type":"noul","instructions":"Does the speaker restart or correct themselves mid-sentence?"},
}
samples = [
 "can you parse the jason and tell me what the endpoint returns",
 "i think jason is out today so we should we should push the meeting to friday",
 "naan innaiku office ku varala enaku udambu sari illa",
 "the deploy failed twice and customers are seeing five hundreds can someone look now",
]
for s in samples: agent.predict(s, q)  # warm
for s in samples:
    t=time.perf_counter(); r=agent.predict(s, q); dt=(time.perf_counter()-t)*1000
    a=r["answers"] if "answers" in r else r
    print(f"{dt:6.1f}ms | {s[:50]!r}")
    for k,v in a.items(): print("      ", k, {kk:(round(vv,2) if isinstance(vv,float) else vv) for kk,vv in v.items() if kk in ('noul','choice','confidence','score')})
ts=[]
for _ in range(20):
    t=time.perf_counter(); agent.predict(samples[0], {"q":q["question"]}); ts.append((time.perf_counter()-t)*1000)
ts.sort(); print(f"1 noul x20: p50 {ts[10]:.1f}ms p95 {ts[18]:.1f}ms")
