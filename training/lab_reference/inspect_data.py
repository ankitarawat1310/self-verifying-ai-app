import json
from datasets import load_dataset
from transformers import AutoTokenizer

ds = load_dataset("open-thoughts/OpenThoughts-Agent-SFT-10K", split="train")
print(ds); print(ds.column_names)
for k, v in ds[0].items():
    print("COL", k, type(v).__name__, str(v)[:200].replace("\n", " "))

col = next(c for c in ds.column_names
           if isinstance(ds[0][c], list) and ds[0][c] and isinstance(ds[0][c][0], dict))
print("conversation column:", col)
tok = AutoTokenizer.from_pretrained("Qwen/Qwen3-Coder-30B-A3B-Instruct")
lens, turns = [], []
for i in range(min(len(ds), 2000)):
    msgs = ds[i][col]
    text = "\n".join(str(m.get("content", m.get("value", ""))) for m in msgs)
    lens.append(len(tok(text).input_ids)); turns.append(len(msgs))
lens.sort()
pct = lambda p: lens[int(len(lens) * p)]
print("rows sampled:", len(lens), "| median:", pct(.5), "| p90:", pct(.9), "| max:", lens[-1])
for cap in (4096, 8192, 16384, 24576, 32768):
    print("fits under", cap, ":", round(100 * sum(l <= cap for l in lens) / len(lens), 1), "%")
print("avg turns:", round(sum(turns) / len(turns), 1))
json.dump({"lens": lens}, open("/app/dataset_stats.json", "w"))
