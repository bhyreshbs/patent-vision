# PatentVision AI backend

See the project [README](../README.md) for setup, API and pipeline documentation.

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
pytest
```
