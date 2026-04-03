"""Launch the Briarwood Dash app."""

from briarwood.dash_app.app import app

if __name__ == "__main__":
    app.run(debug=False, port=8050)
