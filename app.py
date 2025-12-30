import json
import os
from functools import lru_cache
from uuid import uuid4
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import dash
import dash_bootstrap_components as dbc
from dash import Dash, dcc, html, Input, Output, State, callback
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import DatabricksError
from dotenv import load_dotenv

# Load environment variables from .env when running locally
load_dotenv()

# Databricks configuration
DEFAULT_INVOCATIONS_URL = (
    "https://e2-demo-field-eng.cloud.databricks.com/"
    "serving-endpoints/ka-a7b8e184-endpoint/invocations"
)

# Temporary debugging aid: when enabled, show the raw request/response payload in chat.
DEBUG_SHOW_AGENT_PAYLOAD = os.getenv("DEBUG_SHOW_AGENT_PAYLOAD", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "y",
    "on",
}

# Optional: set this to the *full* invocations URL (matches what you shared).
# Example:
#   https://<workspace-host>/serving-endpoints/<endpoint-name>/invocations
DATABRICKS_AGENT_INVOCATIONS_URL = os.getenv(
    "DATABRICKS_AGENT_INVOCATIONS_URL", DEFAULT_INVOCATIONS_URL
)

# Host can be set explicitly; otherwise we derive it from DATABRICKS_AGENT_INVOCATIONS_URL.
_parsed_invocations_url = urlparse(DATABRICKS_AGENT_INVOCATIONS_URL)
_derived_host = f"{_parsed_invocations_url.scheme}://{_parsed_invocations_url.netloc}"
DATABRICKS_HOST = os.getenv("DATABRICKS_HOST", _derived_host)


def _normalize_host(host: str) -> str:
    host = (host or "").strip()
    if not host:
        return host
    if host.startswith("http://") or host.startswith("https://"):
        return host
    return f"https://{host}"


DATABRICKS_HOST = _normalize_host(DATABRICKS_HOST)

# Endpoint name can be set explicitly; otherwise we try to derive it from the invocations URL.
_derived_endpoint_name = None
try:
    # Path shape: /serving-endpoints/<name>/invocations
    parts = [p for p in _parsed_invocations_url.path.split("/") if p]
    if len(parts) >= 3 and parts[0] == "serving-endpoints" and parts[2] == "invocations":
        _derived_endpoint_name = parts[1]
except Exception:
    _derived_endpoint_name = None

DATABRICKS_ENDPOINT_NAME = os.getenv(
    "DATABRICKS_ENDPOINT_NAME", _derived_endpoint_name or "ka-a7b8e184-endpoint"
)

# Databricks OpenAI-compatible endpoint (Responses API)
# This matches the sample code you shared: base_url="https://<host>/serving-endpoints"
DATABRICKS_OPENAI_BASE_URL = os.getenv(
    "DATABRICKS_OPENAI_BASE_URL",
    f"{DATABRICKS_HOST.rstrip('/')}/serving-endpoints",
)
DATABRICKS_OPENAI_RESPONSES_URL = os.getenv(
    "DATABRICKS_OPENAI_RESPONSES_URL",
    f"{DATABRICKS_OPENAI_BASE_URL.rstrip('/')}/responses",
)
# Initialize the Dash app
dash_app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# Chat widget styles
CHAT_BUTTON_STYLE = {
    'position': 'fixed',
    'bottom': '30px',
    'right': '30px',
    'width': '60px',
    'height': '60px',
    'borderRadius': '50%',
    'backgroundColor': '#6B2D7B',
    'border': 'none',
    'cursor': 'pointer',
    'boxShadow': '0 4px 12px rgba(107, 45, 123, 0.4)',
    'display': 'flex',
    'alignItems': 'center',
    'justifyContent': 'center',
    'zIndex': '1000',
    'transition': 'transform 0.2s ease'
}

CHAT_WINDOW_STYLE = {
    'position': 'fixed',
    'bottom': '100px',
    'right': '30px',
    'width': '380px',
    'height': '500px',
    'backgroundColor': 'white',
    'borderRadius': '16px',
    'boxShadow': '0 8px 32px rgba(0, 0, 0, 0.15)',
    'zIndex': '1000',
    'display': 'flex',
    'flexDirection': 'column',
    'overflow': 'hidden'
}

CHAT_HEADER_STYLE = {
    'background': 'linear-gradient(135deg, #6B2D7B 0%, #00539B 100%)',
    'color': 'white',
    'padding': '16px 20px',
    'display': 'flex',
    'alignItems': 'center',
    'gap': '12px'
}

MESSAGE_CONTAINER_STYLE = {
    'flex': '1',
    'overflowY': 'auto',
    'padding': '16px',
    'display': 'flex',
    'flexDirection': 'column',
    'gap': '12px',
    'backgroundColor': '#f8f9fa'
}

INPUT_CONTAINER_STYLE = {
    'padding': '12px 16px',
    'borderTop': '1px solid #e9ecef',
    'backgroundColor': 'white'
}


@lru_cache(maxsize=1)
def get_workspace_client() -> WorkspaceClient:
    """
    Build a WorkspaceClient using the service principal credentials provided
    via environment variables.
    """
    client_id = os.getenv("DATABRICKS_CLIENT_ID")
    client_secret = os.getenv("DATABRICKS_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError(
            "DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET must be set for "
            "service principal authentication."
        )

    return WorkspaceClient(
        host=DATABRICKS_HOST,
        client_id=client_id,
        client_secret=client_secret,
    )


def _extract_agent_reply(response: dict) -> str:
    """
    Best-effort extraction of assistant text from various Databricks response shapes.
    """
    if not response:
        return "I could not retrieve a response right now."

    # Chat-style response
    if "choices" in response and response["choices"]:
        choice = response["choices"][0]
        message = choice.get("message") or {}
        return (
            message.get("content")
            or choice.get("text")
            or json.dumps(choice)
        )

    # Agent / serving endpoint responses
    for key in ("outputs", "predictions", "result"):
        if key in response and response[key]:
            item = response[key][0] if isinstance(response[key], list) else response[key]
            return (
                item.get("content")
                or item.get("answer")
                or item.get("text")
                or json.dumps(item)
            )

    # Fall back to the raw JSON if nothing matches
    return json.dumps(response)


def _extract_openai_responses_text(response: dict) -> str:
    """
    Extract assistant text from OpenAI Responses API shaped output:
      {
        "output": [
          {
            "content": [{"type": "...", "text": "..."}]
          }
        ]
      }
    """
    if not response:
        return "I could not retrieve a response right now."

    output = response.get("output") or []
    chunks: list[str] = []
    for item in output:
        for content in item.get("content") or []:
            text = content.get("text")
            if text:
                chunks.append(text)
    if chunks:
        return "".join(chunks).strip()

    # Some variants return a top-level "output_text"
    if response.get("output_text"):
        return str(response["output_text"]).strip()

    return json.dumps(response)


def call_databricks_agent(messages: list[dict]) -> str:
    """
    Invoke the Databricks agent endpoint with the provided chat messages.

    Expected input shape:
      [{"role": "user"|"assistant"|"system", "content": "<text>"}]
    """
    client = get_workspace_client()
    # Databricks OpenAI-compatible Responses API request (matches the sample code).
    body = {
        "model": DATABRICKS_ENDPOINT_NAME,
        "input": messages,
    }

    def _redact_headers(headers: dict) -> dict:
        redacted = {}
        for k, v in (headers or {}).items():
            if k.lower() == "authorization":
                redacted[k] = "Bearer ***"
            else:
                redacted[k] = v
        return redacted

    def _best_effort_auth_headers() -> dict:
        """
        Attempt to retrieve auth headers from the databricks-sdk client without
        depending on private APIs too heavily.
        """
        candidates = []
        # Common internal shapes across sdk versions
        candidates.append(lambda: client.api_client._cfg.authenticate())  # type: ignore[attr-defined]
        candidates.append(lambda: client.api_client.cfg.authenticate())  # type: ignore[attr-defined]
        candidates.append(lambda: client.api_client.config.authenticate())  # type: ignore[attr-defined]
        candidates.append(lambda: client.config.authenticate())  # type: ignore[attr-defined]

        for fn in candidates:
            try:
                headers = fn()
                if isinstance(headers, dict) and headers:
                    return headers
            except Exception:
                continue
        return {}

    def _invoke_http(url: str, body: dict) -> dict:
        """
        Invoke the endpoint via stdlib urllib so we can capture status/headers/text.
        """
        auth_headers = _best_effort_auth_headers()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **(auth_headers or {}),
        }
        data = json.dumps(body).encode("utf-8")

        req = Request(url=url, data=data, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=30) as resp:
                raw = resp.read()
                text = raw.decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(text) if text else None
                except Exception:
                    parsed = None
                return {
                    "url": url,
                    "status": getattr(resp, "status", None),
                    "headers": dict(resp.headers.items()),
                    "text": text,
                    "json": parsed,
                    "request_headers_redacted": _redact_headers(headers),
                }
        except HTTPError as e:
            raw = e.read()
            text = raw.decode("utf-8", errors="replace")
            return {
                "url": url,
                "status": getattr(e, "code", None),
                "headers": dict(getattr(e, "headers", {}).items()),
                "text": text,
                "request_headers_redacted": _redact_headers(headers),
                "error": {"type": "HTTPError", "message": str(e)},
            }
        except URLError as e:
            return {
                "url": url,
                "request_headers_redacted": _redact_headers(headers),
                "error": {"type": "URLError", "message": str(e)},
            }

    try:
        http_debug = _invoke_http(DATABRICKS_OPENAI_RESPONSES_URL, body)
        if DEBUG_SHOW_AGENT_PAYLOAD:
            return json.dumps(
                {
                    "request": {
                        "base_url": DATABRICKS_OPENAI_BASE_URL,
                        "responses_url": DATABRICKS_OPENAI_RESPONSES_URL,
                        "model": DATABRICKS_ENDPOINT_NAME,
                        "body": body,
                    },
                    "http": http_debug,
                },
                indent=2,
                default=str,
            )

        return _extract_openai_responses_text(http_debug.get("json") or {})
    except DatabricksError as err:
        if DEBUG_SHOW_AGENT_PAYLOAD:
            return json.dumps(
                {
                    "request": {
                        "responses_url": DATABRICKS_OPENAI_RESPONSES_URL,
                        "model": DATABRICKS_ENDPOINT_NAME,
                        "body": body,
                    },
                    "error": {"type": type(err).__name__, "message": str(err)},
                },
                indent=2,
                default=str,
            )
        return "Sorry, I ran into an issue talking to the assistant."
    except Exception as err:  # noqa: BLE001 - surface unexpected errors to the user
        if DEBUG_SHOW_AGENT_PAYLOAD:
            return json.dumps(
                {
                    "request": {
                        "responses_url": DATABRICKS_OPENAI_RESPONSES_URL,
                        "model": DATABRICKS_ENDPOINT_NAME,
                        "body": body,
                    },
                    "error": {"type": type(err).__name__, "message": str(err)},
                },
                indent=2,
                default=str,
            )
        return "Sorry, something went wrong while processing your request."


def render_message_bubble(text: str, role: str) -> html.Div:
    is_user = role == "user"
    bubble_style = {
        "backgroundColor": "#6B2D7B" if is_user else "white",
        "color": "white" if is_user else "#212529",
        "padding": "12px 14px",
        "borderRadius": "12px",
        "borderTopLeftRadius": "4px" if is_user else "12px",
        "borderTopRightRadius": "12px" if is_user else "4px",
        "boxShadow": "0 1px 2px rgba(0,0,0,0.1)",
        "maxWidth": "85%",
        "fontSize": "14px",
        "lineHeight": "1.5",
        "whiteSpace": "pre-wrap",
    }

    avatar_size = 28
    avatar_style = {
        "width": f"{avatar_size}px",
        "height": f"{avatar_size}px",
        "borderRadius": "50%",
        "flex": "0 0 auto",
        "objectFit": "cover",
    }

    # Assistant uses provided bot icon.
    assistant_avatar = html.Img(src=dash_app.get_asset_url("bot_icon.png"), style=avatar_style)

    # Layout: assistant avatar on left; user has no avatar.
    row_style = {
        "display": "flex",
        "alignItems": "flex-end",
        "gap": "8px",
        "justifyContent": "flex-end" if is_user else "flex-start",
    }

    if is_user:
        return html.Div([html.Div(text, style=bubble_style)], style=row_style)

    return html.Div([assistant_avatar, html.Div(text, style=bubble_style)], style=row_style)


def render_history(history: list[dict]) -> list:
    """
    Convert stored chat history into Dash components.
    """
    if not history:
        return []

    rendered = []
    for msg in history:
        text = msg.get("text", "")
        if msg.get("pending"):
            text = "Thinking..."
        rendered.append(render_message_bubble(text, msg.get("role", "assistant")))
    return rendered


def _welcome_message_view() -> html.Div:
    avatar_size = 28
    assistant_avatar = html.Img(
        src=dash_app.get_asset_url("bot_icon.png"),
        style={
            "width": f"{avatar_size}px",
            "height": f"{avatar_size}px",
            "borderRadius": "50%",
            "flex": "0 0 auto",
            "objectFit": "cover",
        },
    )

    welcome_card = html.Div([
        html.P("👋 Hi there! I'm your Select Health virtual assistant.", style={'margin': '0 0 8px 0'}),
        html.P("I can help you with:", style={'margin': '0 0 8px 0', 'fontWeight': '500'}),
        html.Ul([
            html.Li("Understanding your benefits"),
            html.Li("Finding in-network providers"),
            html.Li("Explaining coverage details"),
            html.Li("Open enrollment questions"),
        ], style={'margin': '0', 'paddingLeft': '20px', 'fontSize': '13px'})
    ], style={
        'backgroundColor': 'white',
        'padding': '14px 16px',
        'borderRadius': '12px',
        'borderBottomLeftRadius': '4px',
        'boxShadow': '0 1px 2px rgba(0,0,0,0.1)',
        'maxWidth': '85%',
        'fontSize': '14px',
        'lineHeight': '1.5'
    })

    return html.Div(
        [assistant_avatar, welcome_card],
        style={
            "display": "flex",
            "alignItems": "flex-end",
            "gap": "8px",
            "justifyContent": "flex-start",
        },
    )


def _messages_view(history: list[dict]) -> list:
    return [_welcome_message_view()] + render_history(history or [])


# Define the app layout
dash_app.layout = html.Div([
    # Background screenshot
    html.Div(
        style={
            'position': 'fixed',
            'top': '0',
            'left': '0',
            'width': '100vw',
            'height': '100vh',
            'backgroundImage': f'url("{dash_app.get_asset_url("landing_page.png")}")',
            'backgroundSize': 'cover',
            'backgroundPosition': 'top center',
            'backgroundRepeat': 'no-repeat',
            'zIndex': '0'
        }
    ),
    
    # Chat toggle button
    html.Button(
        html.Div([
            # Chat icon SVG
            html.Img(
                src=dash_app.get_asset_url("chat-icon.svg"),
                style={'width': '28px', 'height': '28px', 'filter': 'brightness(0) invert(1)'}
            )
        ], id='chat-icon-container', className="chat-icon"),
        id='chat-toggle-btn',
        style=CHAT_BUTTON_STYLE,
        n_clicks=0
    ),
    
    # Chat window
    html.Div([
        # Header
        html.Div([
            html.Div([
                html.Div(style={
                    'width': '40px',
                    'height': '40px',
                    'borderRadius': '50%',
                    'backgroundColor': 'rgba(255,255,255,0.2)',
                    'display': 'flex',
                    'alignItems': 'center',
                    'justifyContent': 'center'
                }, children=[
                    html.Span('💬', style={'fontSize': '20px'})
                ]),
                html.Div([
                    html.Div('Select Health Assistant', style={
                        'fontWeight': '600',
                        'fontSize': '16px'
                    }),
                    html.Div('Ask me anything about your coverage', style={
                        'fontSize': '12px',
                        'opacity': '0.9'
                    })
                ])
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '12px', 'flex': '1'}),
            html.Button('✕', id='chat-close-btn', n_clicks=0, style={
                'background': 'none',
                'border': 'none',
                'color': 'white',
                'fontSize': '20px',
                'cursor': 'pointer',
                'padding': '0',
                'lineHeight': '1'
            })
        ], style=CHAT_HEADER_STYLE),
        
        # Messages container
        html.Div(_messages_view([]), id='chat-messages', style=MESSAGE_CONTAINER_STYLE),
        
        # Input area
        html.Div([
            dbc.InputGroup([
                dbc.Input(
                    id='chat-input',
                    placeholder='Type your question...',
                    type='text',
                    style={
                        'borderRadius': '24px',
                        'border': '1px solid #e0e0e0',
                        'padding': '10px 16px',
                        'fontSize': '14px'
                    }
                ),
                dbc.Button(
                    '➤',
                    id='send-btn',
                    n_clicks=0,
                    style={
                        'borderRadius': '50%',
                        'width': '40px',
                        'height': '40px',
                        'marginLeft': '8px',
                        'backgroundColor': '#6B2D7B',
                        'border': 'none',
                        'display': 'flex',
                        'alignItems': 'center',
                        'justifyContent': 'center'
                    }
                )
            ], style={'display': 'flex', 'alignItems': 'center'})
        ], style=INPUT_CONTAINER_STYLE)
    ], id='chat-window', style=CHAT_WINDOW_STYLE, className="chat-window"),
    
    # Store for chat state
    dcc.Store(id='chat-open', data=False),
    dcc.Store(id='chat-history', data=[]),
    dcc.Store(id='pending-request', data=None),
], style={'margin': '0', 'padding': '0'})


# Callback to toggle chat window
@callback(
    [
        Output('chat-window', 'className'),
        Output('chat-open', 'data'),
        Output('chat-icon-container', 'className'),
    ],
    [Input('chat-toggle-btn', 'n_clicks'),
     Input('chat-close-btn', 'n_clicks')],
    [State('chat-open', 'data')],
    prevent_initial_call=True
)
def toggle_chat(toggle_clicks, close_clicks, is_open):
    from dash import ctx
    triggered_id = ctx.triggered_id
    is_open = bool(is_open)
    closed_class = "chat-window"
    open_class = "chat-window open"
    icon_base = "chat-icon"
    icon_open = "chat-icon is-open spin-open"
    icon_closed = "chat-icon spin-close"
    
    if triggered_id == 'chat-close-btn':
        return closed_class, False, icon_closed
    elif triggered_id == 'chat-toggle-btn':
        if is_open:
            return closed_class, False, icon_closed
        else:
            return open_class, True, icon_open
    
    return closed_class, False, icon_closed


@callback(
    [
        Output('chat-messages', 'children'),
        Output('chat-history', 'data'),
        Output('chat-input', 'value'),
        Output('pending-request', 'data'),
    ],
    [
        Input('send-btn', 'n_clicks'),
    ],
    [
        State('chat-input', 'value'),
        State('chat-history', 'data'),
        State('pending-request', 'data'),
    ],
    prevent_initial_call=True,
)
def handle_chat(send_clicks, user_input, history, pending_request):
    from dash import ctx
    history = history or []

    # If a request is in-flight, don't queue another one (keeps ordering simple).
    if pending_request:
        raise dash.exceptions.PreventUpdate

    message = (user_input or "").strip()
    if not message:
        raise dash.exceptions.PreventUpdate

    request_id = str(uuid4())
    updated_history = history + [
        {"id": request_id, "role": "user", "text": message, "pending": False},
        {"id": request_id, "role": "assistant", "text": "", "pending": True},
    ]

    request_messages = [
        {"role": msg["role"], "content": msg["text"]}
        for msg in updated_history
        if msg.get("role") in {"user", "assistant"} and msg.get("text") and not msg.get("pending")
    ]

    pending = {"id": request_id, "messages": request_messages}
    return _messages_view(updated_history), updated_history, "", pending


@callback(
    [
        Output('chat-messages', 'children', allow_duplicate=True),
        Output('chat-history', 'data', allow_duplicate=True),
        Output('pending-request', 'data', allow_duplicate=True),
    ],
    [Input('pending-request', 'data')],
    [State('chat-history', 'data')],
    prevent_initial_call=True,
)
def fetch_agent_reply(pending_request, history):
    if not pending_request:
        raise dash.exceptions.PreventUpdate

    history = history or []
    request_id = pending_request.get("id")
    request_messages = pending_request.get("messages") or []

    reply = call_databricks_agent(request_messages)

    updated = []
    for msg in history:
        if msg.get("id") == request_id and msg.get("role") == "assistant" and msg.get("pending"):
            updated.append({**msg, "text": reply, "pending": False})
        else:
            updated.append(msg)

    return _messages_view(updated), updated, None


if __name__ == '__main__':
    dash_app.run_server(debug=False)
