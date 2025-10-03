from dash import Dash, html, dcc, Input, Output, ctx
import plotly.graph_objects as go
from xml_parser import PreferenceVoteParser

URL = "https://www.volby.cz/pls/ps2021/vysledky_kandid"

# Initialize PreferenceVoteParser and cached preference data
auto_pvp = PreferenceVoteParser(url=URL)
_preference_data_cache = None


def fetch_preference_data(force_reload: bool = False):
    global auto_pvp, _preference_data_cache
    if force_reload or _preference_data_cache is None:
        if force_reload:
            auto_pvp = PreferenceVoteParser(url=URL)
        _preference_data_cache = auto_pvp.get_preference_votes()
    return _preference_data_cache


region_options = list(fetch_preference_data().keys())


def default_region() -> str:
    return "Plzeňský" if "Plzeňský" in region_options else region_options[0]


def build_graphs_for_selection(selected_region: str, party_num: int, preference_data):
    if not preference_data:
        return [html.Div("Preference data unavailable.")], "Selected Region: N/A"

    if not selected_region or selected_region not in preference_data:
        label_region = selected_region or "N/A"
        return [html.Div("Data not available for the selected region.")], f"Selected Region: {label_region} (Party {party_num})"

    region_parties = preference_data[selected_region]
    region_data = region_parties.get(party_num)

    if region_data is None:
        return [html.Div("Data not available for the selected party number.")], f"Selected Region: {selected_region} (Party {party_num})"

    candidates = region_data['candidates']
    candidate_numbers = [candidate['candidate_number'] for candidate in candidates]
    preference_votes = [candidate['preference_votes'] for candidate in candidates]
    preference_shares = [candidate.get('preference_share') for candidate in candidates]

    fig_votes = go.Figure(
        data=[go.Bar(
            x=candidate_numbers,
            y=preference_votes
        )]
    )
    fig_votes.update_layout(
        title=f"Preference Votes for {selected_region}",
        xaxis_title="Candidate Number",
        yaxis_title="Preference Votes"
    )

    bar_colors = [
        "#DAA520" if (share is not None and share >= 5) else "#1f77b4"
        for share in preference_shares
    ]

    fig_share = go.Figure(
        data=[go.Bar(
            x=candidate_numbers,
            y=preference_shares,
            marker=dict(color=bar_colors)
        )]
    )
    fig_share.update_layout(
        title=f"Preference Share for {selected_region}",
        xaxis_title="Candidate Number",
        yaxis_title="Preference Share"
    )
    fig_share.add_hline(
        y=5,
        line=dict(color="red", dash="dash"),
        annotation=dict(text="5% threshold", showarrow=False, yshift=10)
    )

    graphs = [
        dcc.Graph(figure=fig_share),
        dcc.Graph(figure=fig_votes),
    ]

    region_label = f"Selected Region: {selected_region} (Party {party_num})"

    return graphs, region_label


def default_party_num() -> int:
    return 20


app = Dash(__name__)

initial_region = default_region()
initial_party = default_party_num()
initial_data = fetch_preference_data()
initial_graphs, initial_region_label = build_graphs_for_selection(initial_region, initial_party, initial_data)

app.layout = html.Div([
    html.H1("Preference Votes Visualization"),
    html.Div(id="region-name", children=initial_region_label),
    html.Div([
        html.Label("Select Region:"),
        dcc.Dropdown(
            id="region-dropdown",
            options=[{"label": r, "value": r} for r in region_options],
            value=initial_region
        )
    ]),
    html.Div([
        html.Label("Select Party Number:"),
        dcc.Input(id="party-num-input", type="number", value=initial_party, min=0, step=1)
    ]),
    html.Button("Refresh Data", id="refresh-button", n_clicks=0),
    html.Div(id="graphs", children=initial_graphs)
])

@app.callback(
    [Output("graphs", "children"), Output("region-name", "children")],
    [
        Input("region-dropdown", "value"),
        Input("party-num-input", "value"),
        Input("refresh-button", "n_clicks"),
    ],
)
def update_graphs(selected_region, party_num, refresh_clicks):
    try:
        party_key = int(party_num)
    except (TypeError, ValueError):
        party_key = default_party_num()

    force_reload = ctx.triggered_id == "refresh-button"
    preference_data = fetch_preference_data(force_reload=force_reload)

    graphs, label = build_graphs_for_selection(selected_region, party_key, preference_data)

    return graphs, label

if __name__ == '__main__':
    app.run(debug=True)
