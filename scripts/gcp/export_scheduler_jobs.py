from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.workers.job_registry import list_scheduler_jobs

rows = []
for job in list_scheduler_jobs():
    rows.append(
        {
            'job_id': job.job_id,
            'schedule_hour': job.schedule_hour,
            'schedule_minute': job.schedule_minute,
            'timezone': job.timezone,
            'description': job.description,
            'default_max_items': job.default_max_items,
            'path': f'/api/v1/internal/scheduler/jobs/{job.job_id}',
            'body': {},
        }
    )

print(json.dumps(rows, ensure_ascii=False, indent=2))
