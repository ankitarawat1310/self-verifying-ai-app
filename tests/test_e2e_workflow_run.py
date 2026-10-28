import io
import zipfile

from fastapi.testclient import TestClient


def test_workflows_run_m1_url_shortener_accept():
    from svaga_platform.app.main import app

    with TestClient(app) as c:
        res = c.post(
            "/api/v1/workflows/run",
            json={
                "pipeline": "m1",
                "natural_language": "URL shortener with POST /shorten and GET /r/{code}",
                "workflow_id": "url_shortener",
            },
            timeout=180.0,
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["decision"] == "ACCEPT"
        assert data["run_id"]
        assert "workflow_spec.json" in data["artifacts"]
        assert "policy.json" in data["artifacts"]

        run_id = data["run_id"]
        get_res = c.get(f"/api/v1/runs/{run_id}")
        assert get_res.status_code == 200

        dl = c.get(f"/api/v1/runs/{run_id}/download")
        assert dl.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(dl.content))
        names = set(zf.namelist())
        assert "app.py" in names
        assert "workflow_spec.json" in names
        assert "policy.json" in names


def test_generate_model1_delegates_to_full_run():
    from svaga_platform.app.main import app

    with TestClient(app) as c:
        res = c.post(
            "/api/v1/generate-model1",
            json={"prompt": "URL shortener"},
            timeout=180.0,
        )
        assert res.status_code == 200
        data = res.json()
        assert data.get("run_id")
        assert "decision" in data
        assert data.get("workflow_spec")
