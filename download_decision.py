"""Explicit setup: download pinned decision weights and runtime to local disk."""
from pathlib import Path
from huggingface_hub import snapshot_download

REVISION = 'c454ee39b862248d70abd7f84195d2f54ffe6d43'

if __name__ == '__main__':
    revision = REVISION
    folder = Path(__file__).resolve().parent / 'models' / 'decision'
    snapshot_download('vllm-sr/d3-edge', revision=revision, local_dir=folder,
                      allow_patterns=['*.json', '*.py', '*.safetensors', '*.model', '*.txt', '*.jinja'])
    (folder / 'REVISION').write_text(revision, encoding='utf-8')
    print(f'Decision model ready: {folder} at {revision}')
