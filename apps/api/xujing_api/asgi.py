"""Run the API locally: ``uvicorn xujing_api.main:app`` from apps/api."""

from xujing_api.config import get_settings
from xujing_api.main import create_app

settings = get_settings()
app = create_app(settings)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.bind_host, port=settings.bind_port)
