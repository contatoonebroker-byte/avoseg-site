"""Uso:  python scripts/check_env.py     (dentro da pasta jarvis)
Mostra o que o Jarvis enxerga no seu .env, SEM revelar as chaves."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jarvis.envcheck import check  # noqa: E402

print(f"Conferindo {ROOT / '.env'}\n")
for line in check(ROOT / ".env"):
    print(line)
print("\nLembrete: depois de editar o .env, feche o Jarvis (Ctrl+C) e abra de novo.")
