"""Uso:  python scripts/check_env.py            confere o .env (sem revelar chaves)
       python scripts/check_env.py --openai   também testa a chave da OpenAI (sem custo)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jarvis.envcheck import check, test_openai  # noqa: E402

print(f"Conferindo {ROOT / '.env'}\n")
for line in check(ROOT / ".env"):
    print(line)
if "--openai" in sys.argv:
    from jarvis.config import Config

    cfg = Config.load()
    print("\nTestando a OpenAI (sem gerar imagem, sem custo):")
    if not cfg.openai_key:
        print("✗ O Jarvis NÃO está lendo a OPENAI_API_KEY deste .env.")
    else:
        print("\n".join(test_openai(cfg.openai_key, cfg.openai_image_model)))
print("\nLembrete: depois de editar o .env, feche o Jarvis (Ctrl+C) e abra de novo.")
