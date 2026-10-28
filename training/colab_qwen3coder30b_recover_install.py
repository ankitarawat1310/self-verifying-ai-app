# Colab recovery: install the versions from the successful A100 preflight.
# Restart the session afterward; restore Drive/model/data before training.
import subprocess
import sys
from pathlib import Path
from importlib.metadata import version

assert version("torch") == "2.11.0+cu130", "Unexpected PyTorch build; inspect before changing it."
constraints=Path("/content/svaga-recovery-constraints.txt")
constraints.write_text("torch==2.11.0+cu130\n")
subprocess.run([
    sys.executable,"-m","pip","install","--constraint",str(constraints),
    "unsloth==2026.10.9","unsloth_zoo==2026.10.9",
    "bitsandbytes==0.50.2","transformers==5.17.0",
    "peft==0.21.2","accelerate==1.15.0","triton==3.6.0"
],check=True)
print("Recovery installation completed. Restart the session, then restore Drive, model and data before training.")
