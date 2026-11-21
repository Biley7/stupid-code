from fastapi import FastAPI

app = FastAPI(title="Stupid Code")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "stupid-code"}
