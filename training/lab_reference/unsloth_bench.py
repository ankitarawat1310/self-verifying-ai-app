import unsloth
from unsloth import FastModel
import sys, time, json, torch

name = sys.argv[1]
lengths = [int(x) for x in sys.argv[2].split(",")]
tag = name.replace("/", "_")
out = {"model": name, "runs": []}
def save(): json.dump(out, open(f"/app/bench_{tag}.json", "w"), indent=1)

t0 = time.time()
model, tok = FastModel.from_pretrained(model_name=name, max_seq_length=max(lengths),
                                       load_in_4bit=True, full_finetuning=False)
out["load_seconds"] = round(time.time() - t0, 1)
out["gpu_after_load_gb"] = round(torch.cuda.memory_allocated() / 1e9, 1)
print("load:", out["load_seconds"], "s | GPU GB:", out["gpu_after_load_gb"], flush=True)
model = FastModel.get_peft_model(model, r=16, lora_alpha=16, lora_dropout=0, bias="none",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    use_gradient_checkpointing="unsloth", random_state=3407)
tk = getattr(tok, "tokenizer", tok)
text = "def add(a, b):\n    return a + b\n\n" * 8000
opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-4)
model.train()
for L in lengths:
    rec = {"seq_len": L}
    try:
        ids = tk(text, return_tensors="pt", truncation=True, max_length=L).input_ids.cuda()
        torch.cuda.reset_peak_memory_stats(); times = []
        for s in range(6):
            t = time.time()
            loss = model(input_ids=ids, labels=ids).loss
            loss.backward(); opt.step(); opt.zero_grad()
            torch.cuda.synchronize(); times.append(time.time() - t)
            print(L, s, round(times[-1], 2), "s", flush=True)
        avg = sum(times[2:]) / len(times[2:])
        rec.update(avg_step_s=round(avg, 2), tokens_per_s=round(ids.numel() / avg),
                   peak_gpu_gb=round(torch.cuda.max_memory_allocated() / 1e9, 1))
        out["runs"].append(rec); print(rec, flush=True); save()
    except Exception as e:
        rec["error"] = "OOM" if "out of memory" in str(e).lower() else repr(e)[:300]
        out["runs"].append(rec); print(rec, flush=True); save(); break
try:
    model.eval(); FastModel.for_inference(model)
    p = tk("Write a Python function that reads a CSV file and returns a list of dicts.",
           return_tensors="pt").to("cuda")
    model.generate(**p, max_new_tokens=32, do_sample=False)  # warm-up
    t = time.time(); g = model.generate(**p, max_new_tokens=200, do_sample=False)
    n = g.shape[1] - p["input_ids"].shape[1]
    out["gen_tokens_per_s"] = round(n / (time.time() - t), 1)
except Exception as e:
    out["gen_error"] = repr(e)[:300]
print("gen:", out.get("gen_tokens_per_s"), out.get("gen_error"), flush=True)
save(); print("DONE", flush=True)
