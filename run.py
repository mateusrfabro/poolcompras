import os
from app import create_app

env = os.getenv("FLASK_ENV", "development")
config_name = "production" if env == "production" else "development"
app = create_app(config_name)

if __name__ == "__main__":
    app.run(debug=True, port=5050)