import re, collections, random
from datasets import load_dataset
from transformers import AutoTokenizer
ds = load_dataset("open-thoughts/OpenThoughts-Agent-SFT-10K", split="train")
print("result values:", collections.Counter(str(x) for x in ds["result"]).most_common(5))
print("trace_source:", collections.Counter(ds["trace_source"]).most_common(8))
base = [re.sub(r"_copy\d+$", "", t) for t in ds["task"]]
print("unique tasks:", len(set(base)), "of", len(base))
print("task prefixes:", collections.Counter(b.split("-")[0] for b in base).most_common(8))
m = ds[0]["conversations"]
print("message keys:", list(m[0].keys()), "| roles:", [x.get("role") for x in m[:6]])
tok = AutoTokenizer.from_pretrained("Qwen/Qwen3-Coder-30B-A3B-Instruct")
idx = random.Random(0).sample(range(len(ds)), 2000)
lens = [len(tok("\n".join(str(x.get("content", "")) for x in ds[i]["conversations"])).input_ids) for i in idx]
s = sorted(lens); n = len(s)
print("RANDOM sample | median:", s[n//2], "| mean:", round(sum(s)/n), "| p90:", s[int(n*.9)], "| max:", s[-1])
for cap, sp in {12288: 2574, 16384: 2347, 24576: 1948}.items():
    keep = [l for l in lens if l <= cap]; trunc = [min(l, cap) for l in lens]; k = 10000 / n
    print(f"cap {cap}: DROP -> {round(100*len(keep)/n,1)}% = {round(len(keep)*k)} rows, {round(sum(keep)*k/1e6)}M tokens, ~{round(sum(keep)*k/(sp*3600),1)} h | TRUNCATE -> 10000 rows, {round(sum(trunc)*k/1e6)}M tokens, ~{round(sum(trunc)*k/(sp*3600),1)} h")
