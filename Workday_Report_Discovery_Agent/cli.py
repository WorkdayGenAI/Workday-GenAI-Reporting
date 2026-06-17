"""
cli.py — Rich CLI interface for the Report Discovery Agent.

Run with:  python cli.py
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich import box

from agent import ReportDiscoveryAgent
import config

console = Console()


def display_results(results, query):
    """Display results in a formatted Rich table."""
    console.print()
    console.print(
        Panel(f"[bold]Query:[/bold] {query}", title="🔍 Search", border_style="blue")
    )

    table = Table(
        title="Top Matching Reports",
        box=box.ROUNDED,
        show_lines=True,
        title_style="bold cyan",
    )
    table.add_column("#", style="bold", width=3)
    table.add_column("Band", width=8)
    table.add_column("Score", width=6)
    table.add_column("Report Name", style="bold")
    table.add_column("Why It Matches", max_width=60)

    for i, r in enumerate(results, 1):
        band = r.get("band", "N/A")
        color = {"High": "green", "Medium": "yellow", "Low": "red"}.get(band, "white")
        table.add_row(
            str(i),
            f"[{color}]{band}[/{color}]",
            str(r.get("score", "N/A")),
            r.get("report_name", "Unknown"),
            r.get("explanation", "N/A")[:80],
        )

    console.print(table)
    console.print()


def main():
    console.print(
        Panel.fit(
            "[bold cyan]Report Discovery Agent[/bold cyan]\n"
            "BM25 → LLM Scorer for Workday Report Search\n"
            "Type [bold]quit[/bold] or [bold]exit[/bold] to stop.",
            border_style="cyan",
        )
    )

    # Load agent
    with console.status("[bold green]Loading report catalog..."):
        try:
            agent = ReportDiscoveryAgent()
            console.print(
                f"[green]✅ Loaded {len(agent.catalog)} reports.[/green]"
            )
        except Exception as e:
            console.print(f"[red]❌ Failed to load: {e}[/red]")
            return

    # Interactive loop
    while True:
        query = Prompt.ask("\n[bold cyan]Your query[/bold cyan]")
        if query.lower() in ("quit", "exit", "q"):
            console.print("[yellow]Goodbye![/yellow]")
            break
        if not query.strip():
            continue

        with console.status("[bold green]Searching..."):
            results = agent.search(query)

        display_results(results, query)

        # Optional: show metadata for a result
        choice = Prompt.ask(
            "Enter result # for full metadata (or Enter to skip)",
            default="",
        )
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(results):
                rpt = results[idx].get("report", {})
                console.print(
                    Panel(
                        f"[bold]Report Name:[/bold] {rpt.get('Report_Name', 'N/A')}\n"
                        f"[bold]Type:[/bold] {rpt.get('Report_Type', 'N/A')}\n"
                        f"[bold]Description:[/bold] {rpt.get('Brief_Description', 'N/A')}\n"
                        f"[bold]Data Source:[/bold] {rpt.get('DS_Description', 'N/A')}\n"
                        f"[bold]Fields Displayed:[/bold] {rpt.get('Fields_Displayed_on_Report', 'N/A')}\n"
                        f"[bold]Fields Referenced:[/bold] {rpt.get('Fields_Referenced_in_Report', 'N/A')}",
                        title="📋 Full Metadata",
                        border_style="green",
                    )
                )


if __name__ == "__main__":
    main()
