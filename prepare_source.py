from pathlib import Path
import py_compile

ROOT = Path(__file__).resolve().parent
CHUNKS = ROOT / "source_v022"
parts = []
for p in sorted(CHUNKS.glob("chunk_*.txt")):
    parts.append(p.read_text(encoding="utf-8"))
if not parts:
    raise SystemExit("Nenhum chunk da v0.2.2 encontrado")
main = ROOT / "main.py"
main.write_text("".join(parts), encoding="utf-8")
py_compile.compile(str(main), doraise=True)
text = main.read_text(encoding="utf-8")
checks = [
    'APP_VERSION = "0.2.2"',
    'QPushButton("↶  Girar à esquerda")',
    'QPushButton("↷  Girar à direita")',
    'QPushButton("⌫  Excluir página")',
    'QKeySequence.Undo',
]
for check in checks:
    if check not in text:
        raise SystemExit(f"Validação falhou: {check}")
if 'edit_bar = QFrame()' in text:
    raise SystemExit("Validação falhou: barra de edição ainda está na pré-visualização")
print("main.py v0.2.2 reconstruído e validado com sucesso")
