"""Copy only public browser assets into Vercel's static output directory."""

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "dist"
PUBLIC_SUFFIXES = {".html", ".css", ".js"}


if OUTPUT.exists():
    shutil.rmtree(OUTPUT)
OUTPUT.mkdir(mode=0o755)

for source in ROOT.iterdir():
    if source.is_file() and source.suffix in PUBLIC_SUFFIXES:
        shutil.copy2(source, OUTPUT / source.name)

print(f"Prepared {len(list(OUTPUT.iterdir()))} public RIPPLE assets in {OUTPUT}")
