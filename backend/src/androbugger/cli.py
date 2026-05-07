"""Androbugger CLI — fine-tuning, validation, evaluation, and MCP server."""
from __future__ import annotations

import asyncio
from pathlib import Path

import typer

app = typer.Typer(name="androbugger", help="Androbugger CLI tools", no_args_is_help=True)


@app.command("export-training-data")
def export_training_data(
    output: Path = typer.Option(..., "--output", "-o", help="Output JSONL file path"),
    min_quality: float = typer.Option(0.0, "--min-quality", help="Minimum quality threshold (0.0–1.0)"),
) -> None:
    """Export resolved diagnostic sessions as JSONL fine-tuning data."""
    from androbugger.llm.finetune import export_training_data as _export

    typer.echo(f"Exporting training data to {output}…")
    result = _export(output, min_quality=min_quality)
    typer.secho(
        f"✓ Exported {result.record_count} records, skipped {result.skipped_count}",
        fg=typer.colors.GREEN,
    )
    typer.echo(f"  Output: {result.path}")


@app.command("validate-training-data")
def validate_training_data(
    file: Path = typer.Argument(..., help="JSONL file to validate"),
) -> None:
    """Validate a JSONL training data file for schema and content correctness."""
    from androbugger.llm.finetune import validate_training_data as _validate

    result = _validate(file)
    if result.valid:
        typer.secho(
            f"✓ Valid — {result.record_count} records",
            fg=typer.colors.GREEN,
        )
    else:
        typer.secho(f"✗ Invalid — {len(result.errors)} error(s):", fg=typer.colors.RED)
        for err in result.errors[:20]:
            typer.echo(f"  {err}")
        raise typer.Exit(code=1)


@app.command("eval-model")
def eval_model(
    model: str = typer.Option(..., "--model", "-m", help="LiteLLM model identifier"),
    eval_set: Path = typer.Option(..., "--eval-set", help="JSONL eval set file"),
) -> None:
    """Evaluate a model against a JSONL eval set using ROUGE-L scoring."""
    from androbugger.llm.finetune import evaluate_model as _eval

    typer.echo(f"Evaluating {model} against {eval_set}…")
    result = _eval(model, eval_set)
    typer.secho(
        f"✓ ROUGE-L  P={result.rouge_l_precision:.4f}  R={result.rouge_l_recall:.4f}  F={result.rouge_l_fmeasure:.4f}",
        fg=typer.colors.GREEN,
    )
    typer.echo(f"  Records evaluated: {result.record_count}")


@app.command("mcp-server")
def mcp_server(
    transport: str = typer.Option("stdio", "--transport", help="Transport: stdio or sse"),
    port: int = typer.Option(8765, "--port", help="Port for SSE transport"),
) -> None:
    """Start the Androbugger MCP server for Claude Desktop / Claude Code integration."""
    from androbugger.mcp.server import run_server

    typer.echo(f"Starting MCP server (transport={transport}, port={port})…")
    asyncio.run(run_server(transport=transport, port=port))


def main() -> None:
    app()
