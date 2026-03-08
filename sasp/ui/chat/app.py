"""SASP Security Analyst Chat Interface — Gradio-based investigation dashboard."""

import os
import json
import logging
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from sasp.agents.llm_client import chat_completion

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Service endpoints (configurable via environment)
# ---------------------------------------------------------------------------
LLM_ENDPOINT = os.environ.get("LLM_ENDPOINT", "http://localhost:1234")
LLM_MODEL = os.environ.get("LLM_MODEL", "nvidia/nemotron-3-nano")
KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "localhost:9092")
TRITON_URL = os.environ.get("TRITON_URL", "http://localhost:8000")

GRADIO_USERNAME = os.environ.get("GRADIO_USERNAME")
GRADIO_PASSWORD = os.environ.get("GRADIO_PASSWORD")

# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

def _check_service_health() -> Dict[str, str]:
    """Check connectivity to Kafka, Triton, and LLM server.

    Returns a dict mapping service name to 'ok' or an error string.
    """
    status: Dict[str, str] = {}

    # LLM Server (OpenAI-compatible)
    try:
        resp = requests.get(f"{LLM_ENDPOINT}/v1/models", timeout=3)
        status["llm"] = "ok" if resp.status_code == 200 else f"HTTP {resp.status_code}"
    except Exception as exc:
        status["llm"] = str(exc)[:80]

    # Triton
    try:
        resp = requests.get(f"{TRITON_URL}/v2/health/ready", timeout=3)
        status["triton"] = "ok" if resp.status_code == 200 else f"HTTP {resp.status_code}"
    except Exception as exc:
        status["triton"] = str(exc)[:80]

    # Kafka — just a TCP connect check
    try:
        import socket
        host, port_str = KAFKA_BROKER.rsplit(":", 1)
        sock = socket.create_connection((host, int(port_str)), timeout=3)
        sock.close()
        status["kafka"] = "ok"
    except Exception as exc:
        status["kafka"] = str(exc)[:80]

    return status

# ---------------------------------------------------------------------------
# Mock / live detection feed
# ---------------------------------------------------------------------------

_MOCK_DETECTIONS: List[List[Any]] = [
    ["2026-02-28T08:12:33Z", "10.1.5.42", "10.200.0.12", "high", 0.94],
    ["2026-02-28T08:11:07Z", "172.16.3.8", "192.168.1.1", "medium", 0.72],
    ["2026-02-28T08:09:55Z", "10.1.5.42", "10.200.0.15", "high", 0.88],
    ["2026-02-28T08:05:12Z", "192.168.10.5", "8.8.8.8", "low", 0.35],
    ["2026-02-28T07:58:41Z", "10.1.5.42", "10.200.0.12", "critical", 0.97],
]

_DETECTION_HEADERS = ["timestamp", "source_ip", "dest_ip", "severity", "anomaly_score"]


def _fetch_detections() -> List[List[Any]]:
    """Return recent detections. Falls back to mock data when Kafka is unavailable."""
    try:
        # Attempt to pull from a local detection API if available
        resp = requests.get("http://localhost:8080/api/detections/recent", timeout=3)
        if resp.status_code == 200:
            rows = resp.json()
            if rows:
                return rows
    except Exception:
        pass

    return list(_MOCK_DETECTIONS)


def _detection_row_to_dict(row: List[Any]) -> Dict[str, Any]:
    """Convert a detection row list into a dict keyed by column headers."""
    return dict(zip(_DETECTION_HEADERS, row))

# ---------------------------------------------------------------------------
# Chat handler — talks to Ollama
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a senior security analyst assistant in the SASP platform. "
    "You help human analysts investigate network detections, correlate evidence, "
    "identify MITRE ATT&CK techniques, and recommend response actions. "
    "Be concise, precise, and cite evidence when possible."
)


def _call_llm_chat(prompt: str, history: List[Dict[str, str]]) -> str:
    """Send a chat completion to the LLM server and return the assistant reply."""
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for entry in history:
        messages.append({"role": entry["role"], "content": entry["content"]})
    messages.append({"role": "user", "content": prompt})

    response = chat_completion(
        endpoint=LLM_ENDPOINT,
        model=LLM_MODEL,
        messages=messages,
        temperature=0.5,
        max_tokens=4096,
        timeout=120,
        raw=True,  # Show reasoning traces to the analyst
    )

    if not response:
        return (
            "[LLM unavailable] I cannot reach the LLM backend right now. "
            "Please verify that the server is running at "
            f"`{LLM_ENDPOINT}` with model `{LLM_MODEL}`."
        )
    return response


def _chat_handler(
    message: str,
    history: List[Dict[str, str]],
    selected_detection: Optional[str],
) -> str:
    """Process analyst message, enrich with detection context, query LLM.

    Args:
        message: Analyst's new message.
        history: Gradio chat history (list of {"role": ..., "content": ...} dicts).
        selected_detection: JSON-encoded detection row or None.

    Returns:
        Assistant response text.
    """
    if not message.strip():
        return ""

    # Build context prefix when a detection is selected
    context = ""
    if selected_detection:
        try:
            det = json.loads(selected_detection)
            context = (
                "The analyst has selected this detection for investigation:\n"
                f"```json\n{json.dumps(det, indent=2)}\n```\n\n"
            )
        except (json.JSONDecodeError, TypeError):
            pass

    enriched_prompt = context + message if context else message
    return _call_llm_chat(enriched_prompt, history)

# ---------------------------------------------------------------------------
# Investigation state helpers
# ---------------------------------------------------------------------------

_MOCK_INVESTIGATION_STATE: Dict[str, Any] = {
    "investigation_id": "inv-a1b2c3d4e5f6",
    "severity": "high",
    "triage_decision": "investigate",
    "triage_confidence": 0.92,
    "mitre_techniques": ["T1071.001", "T1048.003"],
    "affected_assets": ["10.1.5.42", "10.200.0.12"],
    "evidence": [
        {
            "source": "splunk",
            "query": "index=firewall src_ip=10.1.5.42",
            "result": "47 connections in 5 min window",
            "timestamp": "2026-02-28T08:15:00Z",
        }
    ],
    "recommendations": [
        "Block outbound traffic from 10.1.5.42 pending review",
        "Isolate host via ISE quarantine policy",
        "Escalate to IR team for forensic imaging",
    ],
    "approval_request": None,
}

# ---------------------------------------------------------------------------
# Gradio application
# ---------------------------------------------------------------------------


def build_app():
    """Construct and return the Gradio Blocks application."""
    import gradio as gr

    with gr.Blocks(
        title="SASP Security Analyst Console",
        theme=gr.themes.Monochrome(),
    ) as app:
        # Shared state --------------------------------------------------------
        selected_detection_state = gr.State(value=None)

        # Header / status bar -------------------------------------------------
        gr.Markdown("# SASP Security Analyst Console")
        with gr.Row():
            status_display = gr.Textbox(
                label="Service Status",
                interactive=False,
                max_lines=1,
                value="Checking services...",
            )
            refresh_status_btn = gr.Button("Refresh Status", size="sm")

        def _refresh_status() -> str:
            health = _check_service_health()
            parts = []
            for svc, state in health.items():
                indicator = "[OK]" if state == "ok" else "[DOWN]"
                parts.append(f"{svc}: {indicator}")
            return "  |  ".join(parts)

        refresh_status_btn.click(fn=_refresh_status, outputs=[status_display])

        # Three-column layout --------------------------------------------------
        with gr.Row():
            # --- Left column: Detection feed --------------------------------
            with gr.Column(scale=3):
                gr.Markdown("## Detection Feed")
                detection_table = gr.Dataframe(
                    headers=_DETECTION_HEADERS,
                    value=_fetch_detections(),
                    interactive=False,
                    label="Recent Detections",
                )
                refresh_detections_btn = gr.Button("Refresh Detections")

                def _refresh_table():
                    return _fetch_detections()

                refresh_detections_btn.click(fn=_refresh_table, outputs=[detection_table])

                def _on_select(evt: gr.SelectData, table_data):
                    """When a row is clicked, store the detection as JSON."""
                    try:
                        row_idx = evt.index[0]
                        if hasattr(table_data, "values"):
                            row = table_data.values.tolist()[row_idx]
                        elif isinstance(table_data, list):
                            row = table_data[row_idx]
                        else:
                            return None
                        det = _detection_row_to_dict(row)
                        return json.dumps(det)
                    except Exception:
                        return None

                detection_table.select(
                    fn=_on_select,
                    inputs=[detection_table],
                    outputs=[selected_detection_state],
                )

            # --- Center column: Chat ----------------------------------------
            with gr.Column(scale=5):
                gr.Markdown("## Investigation Chat")
                chatbot = gr.Chatbot(
                    label="Analyst Chat",
                    height=480,
                    type="messages",
                )
                with gr.Row():
                    chat_input = gr.Textbox(
                        placeholder="Ask about the selected detection...",
                        show_label=False,
                        scale=8,
                    )
                    send_btn = gr.Button("Send", variant="primary", scale=1)

                def _handle_send(
                    message: str,
                    history: List[Dict[str, str]],
                    det_json: Optional[str],
                ) -> Tuple[List[Dict[str, str]], str]:
                    if not message.strip():
                        return history, ""
                    history = list(history)
                    history.append({"role": "user", "content": message})
                    reply = _chat_handler(message, history, det_json)
                    history.append({"role": "assistant", "content": reply})
                    return history, ""

                send_btn.click(
                    fn=_handle_send,
                    inputs=[chat_input, chatbot, selected_detection_state],
                    outputs=[chatbot, chat_input],
                )
                chat_input.submit(
                    fn=_handle_send,
                    inputs=[chat_input, chatbot, selected_detection_state],
                    outputs=[chatbot, chat_input],
                )

            # --- Right column: Investigation details -------------------------
            with gr.Column(scale=4):
                gr.Markdown("## Investigation Details")
                inv_state_json = gr.JSON(
                    value=_MOCK_INVESTIGATION_STATE,
                    label="Investigation State",
                )

                with gr.Accordion("Evidence", open=False):
                    evidence_display = gr.JSON(
                        value=_MOCK_INVESTIGATION_STATE.get("evidence", []),
                        label="Collected Evidence",
                    )

                with gr.Accordion("MITRE Techniques", open=False):
                    mitre_display = gr.JSON(
                        value=_MOCK_INVESTIGATION_STATE.get("mitre_techniques", []),
                        label="Mapped Techniques",
                    )

                gr.Markdown("### Human Approval")
                with gr.Row():
                    approve_btn = gr.Button("Approve", variant="primary")
                    reject_btn = gr.Button("Reject", variant="stop")
                approval_output = gr.Textbox(
                    label="Approval Result",
                    interactive=False,
                )

                def _handle_approval(action: str) -> str:
                    ts = datetime.now(timezone.utc).isoformat()
                    return f"[{ts}] Investigation {action}d by analyst."

                approve_btn.click(
                    fn=lambda: _handle_approval("approve"),
                    outputs=[approval_output],
                )
                reject_btn.click(
                    fn=lambda: _handle_approval("reject"),
                    outputs=[approval_output],
                )

        # Auto-refresh status on load
        app.load(fn=_refresh_status, outputs=[status_display])

    return app


def main() -> None:
    """Launch the SASP Gradio chat application."""
    logging.basicConfig(level=logging.INFO)

    app = build_app()

    auth = None
    if GRADIO_USERNAME and GRADIO_PASSWORD:
        auth = (GRADIO_USERNAME, GRADIO_PASSWORD)
        logger.info("Authentication enabled for Gradio UI.")

    app.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("GRADIO_PORT", "7860")),
        auth=auth,
        share=False,
    )


if __name__ == "__main__":
    main()
