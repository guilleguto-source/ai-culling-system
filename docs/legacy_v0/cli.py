from __future__ import annotations
import json
from dataclasses import replace
from pathlib import Path
import typer
from .presets import load_preset
from .pipeline import cull_folder, cull_report
from . import xmp_writer

app = typer.Typer(help="Selector de fotos de eventos (culling).")


@app.callback()
def main() -> None:
    """Selector de fotos de eventos (culling)."""


@app.command()
def cull(
    folder: Path = typer.Argument(..., help="Carpeta con las fotos"),
    preset: Path = typer.Option(None, "--preset", help="Archivo YAML de preset"),
    blur: str = typer.Option(None, "--blur", help="indulgente | moderado | estricto"),
    dry_run: bool = typer.Option(False, "--dry-run", help="No escribe XMP; solo reporta"),
    out: Path = typer.Option(None, "--out", help="Ruta del JSON de reporte (con --dry-run)"),
) -> None:
    cfg = load_preset(preset)
    if blur:
        cfg = replace(cfg, blur=blur)

    if dry_run:
        payload = cull_report(folder, cfg)
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        if out:
            out.write_text(text, encoding="utf-8")
        else:
            typer.echo(text)
        return

    decisions = cull_folder(folder, cfg)
    for d in decisions:
        xmp_writer.write_metadata(d.path, d.rating, d.label)
    typer.echo(f"Procesadas {len(decisions)} fotos.")


if __name__ == "__main__":
    app()
