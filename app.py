from dash import Dash, dcc, html, Input, Output, State, callback
import dash_bootstrap_components as dbc

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
            'backgroundImage': 'url("/assets/landing_page.png")',
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
                src='/assets/chat-icon.svg',
                style={'width': '28px', 'height': '28px', 'filter': 'brightness(0) invert(1)'}
            )
        ], id='chat-icon-container'),
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
        html.Div([
            # Welcome message
            html.Div([
                html.Div([
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
            ], style={'display': 'flex', 'justifyContent': 'flex-start'}),
        ], id='chat-messages', style=MESSAGE_CONTAINER_STYLE),
        
        # Suggested questions
        html.Div([
            html.Div("Quick questions:", style={
                'fontSize': '12px',
                'color': '#666',
                'marginBottom': '8px'
            }),
            html.Div([
                html.Button("What's my deductible?", className='suggestion-btn', id='suggest-1', n_clicks=0),
                html.Button("Find a doctor", className='suggestion-btn', id='suggest-2', n_clicks=0),
                html.Button("Coverage for prescriptions", className='suggestion-btn', id='suggest-3', n_clicks=0),
            ], style={
                'display': 'flex',
                'flexWrap': 'wrap',
                'gap': '6px'
            })
        ], id='suggestions-container', style={
            'padding': '12px 16px',
            'borderTop': '1px solid #e9ecef',
            'backgroundColor': '#fafafa'
        }),
        
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
    ], id='chat-window', style={**CHAT_WINDOW_STYLE, 'display': 'none'}),
    
    # Store for chat state
    dcc.Store(id='chat-open', data=False),
    dcc.Store(id='chat-history', data=[])
], style={'margin': '0', 'padding': '0'})


# Callback to toggle chat window
@callback(
    [Output('chat-window', 'style'),
     Output('chat-open', 'data')],
    [Input('chat-toggle-btn', 'n_clicks'),
     Input('chat-close-btn', 'n_clicks')],
    [State('chat-open', 'data')],
    prevent_initial_call=True
)
def toggle_chat(toggle_clicks, close_clicks, is_open):
    from dash import ctx
    triggered_id = ctx.triggered_id
    
    if triggered_id == 'chat-close-btn':
        return {**CHAT_WINDOW_STYLE, 'display': 'none'}, False
    elif triggered_id == 'chat-toggle-btn':
        if is_open:
            return {**CHAT_WINDOW_STYLE, 'display': 'none'}, False
        else:
            return {**CHAT_WINDOW_STYLE, 'display': 'flex'}, True
    
    return {**CHAT_WINDOW_STYLE, 'display': 'none'}, False


if __name__ == '__main__':
    dash_app.run_server(debug=False)
