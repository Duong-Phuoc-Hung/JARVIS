"""
jarvis/ui/terminal/modules/data.py
=====================================
Data Analysis module adapter. Never guesses a dataset -- every analysis
action requires an explicitly selected file first (stored in ctx.state).
"""
from __future__ import annotations

from pathlib import Path

from jarvis.data.analysis_service import (
    AnalysisOperation,
    DataAnalysisRequest,
    DataAnalysisService,
)
from jarvis.ui.terminal.context import TerminalContext, run_timed
from jarvis.ui.terminal.models import ActionOutcome, MenuAction, MenuScreen
from jarvis.ui.terminal.theme import StatusLevel

MODULE = "DATA"


def _service(ctx: TerminalContext) -> DataAnalysisService:
    svc = ctx.state.get("data_service")
    if svc is None:
        svc = DataAnalysisService()
        ctx.state["data_service"] = svc
    return svc


def _select_dataset(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        raw = ctx.console.read_line("Enter dataset/document file path: ")
        if not raw:
            return ActionOutcome(status=StatusLevel.SKIPPED, title="Select Dataset / Document",
                                  detail_lines=["No path entered."])
        path = Path(raw).expanduser()
        if not path.exists() or not path.is_file():
            return ActionOutcome(status=StatusLevel.BLOCKED, title="Select Dataset / Document",
                                  fields=[("Path", str(path))],
                                  error_reason="File does not exist or is not a regular file.")
        ctx.state["data_selected_file"] = str(path)
        return ActionOutcome(status=StatusLevel.PASS, title="Select Dataset / Document",
                              fields=[("Path", str(path)), ("Size", f"{path.stat().st_size} bytes")])
    return run_timed(body)


def _run_operation(ctx: TerminalContext, label: str, op: AnalysisOperation) -> ActionOutcome:
    def body() -> ActionOutcome:
        selected = ctx.state.get("data_selected_file")
        if not selected:
            return ActionOutcome(status=StatusLevel.SKIPPED, title=label,
                                  detail_lines=["No dataset selected. Use 'Select Dataset / Document' first."])
        request = DataAnalysisRequest(operation=op, file_path=selected)
        result = _service(ctx).execute(request)
        if not result.success:
            return ActionOutcome(status=StatusLevel.FAILED, title=label,
                                  fields=[("File", selected)], error_reason=result.error or "Unknown error.")
        summary_fields = [("File", selected)]
        data_repr = result.data
        if isinstance(data_repr, dict):
            for k, v in list(data_repr.items())[:8]:
                summary_fields.append((str(k), str(v)))
        return ActionOutcome(status=StatusLevel.PASS, title=label, fields=summary_fields,
                              structured_data={"result": data_repr if isinstance(data_repr, (dict, list, str, int, float)) else str(data_repr)})
    return run_timed(body)


def _visualization_status(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        try:
            import matplotlib  # noqa: F401
            return ActionOutcome(status=StatusLevel.AVAILABLE, title="Visualization",
                                  fields=[("matplotlib", "AVAILABLE")])
        except ImportError:
            return ActionOutcome(status=StatusLevel.LIMITED, title="Visualization",
                                  fields=[("matplotlib", "NOT INSTALLED")],
                                  detail_lines=["Install the optional 'charts' extra to enable chart rendering."])
    return run_timed(body)


def _backend_status(ctx: TerminalContext) -> ActionOutcome:
    def body() -> ActionOutcome:
        try:
            _service(ctx)
            svc_ok = True
        except Exception:
            svc_ok = False
        viz = _visualization_status(ctx)
        selected = ctx.state.get("data_selected_file") or "(none selected)"
        fields = [
            ("Analysis Service", "AVAILABLE" if svc_ok else "ERROR"),
            ("Visualization", viz.status.value),
            ("Selected Dataset", selected),
        ]
        status = StatusLevel.AVAILABLE if svc_ok else StatusLevel.ERROR
        return ActionOutcome(status=status, title="Analysis Backend Status", fields=fields)
    return run_timed(body)


def build_menu(ctx: TerminalContext) -> MenuScreen:
    has_file = bool(ctx.state.get("data_selected_file"))
    actions = [
        MenuAction(id="data_select", key="1", label="Select Dataset / Document",
                   description="Choose a real file to analyze",
                   handler=lambda: _select_dataset(ctx), requires_target=True, safe_for_batch=False,
                   help_text="Prompts for a file path and verifies it exists before selecting it."),
        MenuAction(id="data_overview", key="2", label="Dataset Overview",
                   description="Shape/columns overview of the selected file",
                   handler=lambda: _run_operation(ctx, "Dataset Overview", AnalysisOperation.DESCRIBE),
                   safe_for_batch=has_file, available=True,
                   help_text="Runs the DESCRIBE operation on the selected dataset."),
        MenuAction(id="data_stats", key="3", label="Descriptive Statistics",
                   description="Descriptive statistics of the selected file",
                   handler=lambda: _run_operation(ctx, "Descriptive Statistics", AnalysisOperation.DESCRIBE),
                   safe_for_batch=has_file,
                   help_text="Same DESCRIBE operation as Dataset Overview, presented as statistics."),
        MenuAction(id="data_analysis", key="4", label="Statistical Analysis",
                   description="Anomaly detection (z-score) on the selected file",
                   handler=lambda: _run_operation(ctx, "Statistical Analysis", AnalysisOperation.ANOMALY),
                   safe_for_batch=has_file,
                   help_text="Runs ANOMALY (z-score, threshold=3.0) analysis."),
        MenuAction(id="data_document", key="5", label="Document Analysis",
                   description="Document-oriented overview (PDF/DOCX/TXT/MD)",
                   handler=lambda: _run_operation(ctx, "Document Analysis", AnalysisOperation.DESCRIBE),
                   safe_for_batch=has_file,
                   help_text="Runs DESCRIBE against the selected document."),
        MenuAction(id="data_viz", key="6", label="Visualization",
                   description="Chart backend availability",
                   handler=lambda: _visualization_status(ctx), safe_for_batch=True,
                   help_text="Reports whether matplotlib is installed. Does not render a chart "
                              "from arbitrary data in this build."),
        MenuAction(id="data_backend", key="7", label="Analysis Backend Status",
                   description="Aggregate backend availability",
                   handler=lambda: _backend_status(ctx), safe_for_batch=False,
                   help_text="Summarizes analysis-service and visualization availability."),
    ]
    return MenuScreen(
        id="data", title="DATA ANALYSIS", breadcrumb=["MAIN", "DATA"],
        actions=actions, batch_label="Analyze All",
        help_intro="Analysis actions only appear eligible for [A] once a dataset has been "
                   "explicitly selected via 'Select Dataset / Document'.",
    )
