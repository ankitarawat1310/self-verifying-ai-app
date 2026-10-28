import unsloth  # must be imported first
from unsloth import FastModel
import sys, time, json, torch, psutil

name = sys.argv[1] if len(sys.argv) > 1 else "Qwen/Qwen3-Coder-30B-A3B-Instruct"
lengths = [1024, 2048]
out = {"model": name, "runs": []}

def ram():
    m = psutil.virtual_memory()
    return round(m.used/1e9, 1), round(m.available/1e9, 1)

print("start RAM used/avail GB:", ram(), flush=True)
t0 = time.time()
model, tok = FastModel.from_pretrained(
    model_name=name, max_seq_length=2048, load_in_4bit=True, full_finetuning=False)
out["load_seconds"] = round(time.time() - t0, 1)
out["gpu_after_load_gb"] = round(torch.cuda.memory_allocated() / 1e9, 1)
print("load seconds:", out["load_seconds"], "| GPU GB:", out["gpu_after_load_gb"],
      "| RAM used/avail:", ram(), flush=True)

model = FastModel.get_peft_model(
    model, r=16, lora_alpha=16, lora_dropout=0, bias="none",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    use_gradient_checkpointing="unsloth", random_state=3407)
tk = getattr(tok, "tokenizer", tok)
text = "def add(a, b):\n    return a + b\n\n" * 2000
params = [p for p in model.parameters() if p.requires_grad]
opt = torch.optim.AdamW(params, lr=1e-4)
model.train()

for L in lengths:
    rec = {"seq_len": L}
    try:
        ids = tk(text, return_tensors="pt", truncation=True, max_length=L).input_ids.cuda()
        torch.cuda.reset_peak_memory_stats()
        times = []
        for s in range(6):
            t = time.time()
            loss = model(input_ids=ids, labels=ids).loss
            loss.backward(); opt.step(); opt.zero_grad()
            torch.cuda.synchronize(); times.append(time.time() - t)
            print(L, s, round(loss.item(), 3), round(times[-1], 2), "s", flush=True)
        avg = sum(times[2:]) / len(times[2:])
        rec.update(avg_step_s=round(avg, 2), tokens_per_s=round(ids.numel() / avg),
                   peak_gpu_gb=round(torch.cuda.max_memory_allocated() / 1e9, 1))
    except torch.cuda.OutOfMemoryError:
        rec["error"] = "OOM"; torch.cuda.empty_cache()
    except Exception as e:
        rec["error"] = repr(e)[:300]
    out["runs"].append(rec); print(rec, flush=True)
    json.dump(out, open("/app/results_" + name.replace("/", "_") + ".json", "w"), indent=1)
print("DONE", flush=True)
