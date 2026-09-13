"""Import legacy automation JSON into the database.

This is intentionally a one-time, all-or-nothing data migration. The schema
revision must be applied first with ``flask db upgrade``.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_FILE = ROOT / "data" / "automations.json"
ASSET_FILE = ROOT / "data" / "automation_assets.json"
sys.path.insert(0, str(ROOT))

from app import app
from models import db, User, Campaign, Workflow, WorkflowTask, WorkflowRun, WorkflowAsset


def parse_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def json_text(value, default):
    return json.dumps(value if value is not None else default, sort_keys=True)


def normalize_node_type(value):
    return {"generate_content": "generate_blog"}.get(value, value or "unknown")


def normalize_asset_type(value):
    return {
        "generate_content": "blog",
        "generate_blog": "blog",
        "generate_image": "image",
        "generate_video": "video",
        "generate_voice": "voice",
        "ai_assistant": "assistant",
        "generate_newsletter": "newsletter",
    }.get(value, value or "unknown")


def latest_log(logs):
    return max(logs, key=lambda row: row.get("started_at") or "")


def import_legacy_data():
    legacy = json.loads(WORKFLOW_FILE.read_text(encoding="utf-8"))
    legacy_assets = json.loads(ASSET_FILE.read_text(encoding="utf-8"))
    workflow_data = legacy.get("workflows", [])
    logs = legacy.get("logs", [])
    asset_data = legacy_assets if isinstance(legacy_assets, list) else []

    counts = {
        "created_workflows": 0,
        "created_placeholder_workflows": 0,
        "created_tasks": 0,
        "created_runs": 0,
        "created_synthetic_runs": 0,
        "created_assets": 0,
        "skipped": 0,
        "failed": 0,
    }

    with app.app_context():
        if Workflow.query.count() or WorkflowRun.query.count() or WorkflowAsset.query.count():
            raise RuntimeError(
                "Automation storage is not empty; refusing to run a one-time import."
            )
        db.session.rollback()

        workflows_by_legacy_id = {}
        runs_by_legacy_id = {}
        logs_by_workflow_id = {}
        for log in logs:
            logs_by_workflow_id.setdefault(log.get("workflow_id"), []).append(log)

        try:
            with db.session.begin():
                def get_or_create_placeholder(workflow_legacy_id, source_log=None):
                    if workflow_legacy_id in workflows_by_legacy_id:
                        return workflows_by_legacy_id[workflow_legacy_id]

                    related_logs = logs_by_workflow_id.get(workflow_legacy_id, [])
                    latest = latest_log(related_logs) if related_logs else source_log or {}
                    workflow = Workflow(
                        legacy_id=workflow_legacy_id,
                        user_id=None,
                        campaign_id=None,
                        name=latest.get("workflow_name") or f"Legacy workflow {workflow_legacy_id}",
                        trigger="legacy",
                        status=latest.get("status") or "legacy",
                    )
                    db.session.add(workflow)
                    db.session.flush()
                    workflows_by_legacy_id[workflow_legacy_id] = workflow
                    counts["created_workflows"] += 1
                    counts["created_placeholder_workflows"] += 1
                    return workflow

                for data in workflow_data:
                    legacy_id = data["id"]
                    if legacy_id in workflows_by_legacy_id:
                        counts["skipped"] += 1
                        continue

                    user_id = data.get("user_id")
                    if user_id is not None and db.session.get(User, user_id) is None:
                        user_id = None

                    campaign_id = data.get("campaign_id")
                    if campaign_id is not None and db.session.get(Campaign, campaign_id) is None:
                        campaign_id = None

                    workflow = Workflow(
                        legacy_id=legacy_id,
                        user_id=user_id,
                        campaign_id=campaign_id,
                        name=data.get("name") or f"Legacy workflow {legacy_id}",
                        trigger=data.get("trigger") or "manual",
                        status=data.get("status") or "pending",
                        created_at=parse_datetime(data.get("created_at")) or datetime.now(timezone.utc),
                    )
                    db.session.add(workflow)
                    db.session.flush()
                    workflows_by_legacy_id[legacy_id] = workflow
                    counts["created_workflows"] += 1

                    for index, node in enumerate(data.get("nodes", [])):
                        db.session.add(WorkflowTask(
                            workflow_id=workflow.id,
                            task_type=normalize_node_type(node.get("type")),
                            status=node.get("status") or "pending",
                            node_index=index,
                            node_config=json_text(node, {}),
                            dependencies=json_text(node.get("dependencies"), []),
                            internal_id=node.get("id") or f"node_{index}",
                            result_data=json_text(node.get("result_data"), None),
                        ))
                        counts["created_tasks"] += 1

                for log in logs:
                    workflow_legacy_id = log.get("workflow_id")
                    workflow = workflows_by_legacy_id.get(workflow_legacy_id)
                    if workflow is None:
                        workflow = get_or_create_placeholder(workflow_legacy_id, log)

                    run_legacy_id = log["id"]
                    if run_legacy_id in runs_by_legacy_id:
                        counts["skipped"] += 1
                        continue

                    run = WorkflowRun(
                        legacy_id=run_legacy_id,
                        workflow_id=workflow.id,
                        workflow_name=log.get("workflow_name"),
                        status=log.get("status") or "legacy",
                        started_at=parse_datetime(log.get("started_at")),
                        completed_at=parse_datetime(log.get("completed_at")),
                        credits_used=log.get("credits_used") or 0,
                        nodes_executed=json_text(log.get("nodes_executed"), []),
                        error=log.get("error"),
                    )
                    db.session.add(run)
                    db.session.flush()
                    runs_by_legacy_id[run_legacy_id] = run
                    counts["created_runs"] += 1

                for asset in asset_data:
                    workflow_legacy_id = asset.get("workflow_id")
                    workflow = workflows_by_legacy_id.get(workflow_legacy_id)
                    if workflow is None:
                        workflow = get_or_create_placeholder(workflow_legacy_id, asset)

                    run_legacy_id = asset.get("run_id")
                    run = runs_by_legacy_id.get(run_legacy_id)
                    if run is None:
                        run = WorkflowRun(
                            legacy_id=run_legacy_id,
                            workflow_id=workflow.id,
                            workflow_name=workflow.name,
                            status="legacy",
                            started_at=parse_datetime(asset.get("created_at")),
                            completed_at=parse_datetime(asset.get("created_at")),
                            credits_used=0,
                            nodes_executed="[]",
                        )
                        db.session.add(run)
                        db.session.flush()
                        runs_by_legacy_id[run_legacy_id] = run
                        counts["created_runs"] += 1
                        counts["created_synthetic_runs"] += 1

                    db.session.add(WorkflowAsset(
                        legacy_id=asset["id"],
                        workflow_id=workflow.id,
                        run_id=run.id,
                        node_id=asset.get("node_id"),
                        asset_type=normalize_asset_type(asset.get("asset_type")),
                        title=asset.get("title"),
                        content=asset.get("content") or "",
                        file_url=asset.get("file_url"),
                        thumbnail_url=asset.get("thumbnail_url"),
                        provider_used=asset.get("provider_used"),
                        generation_time=asset.get("generation_time"),
                        meta_data=json_text(asset.get("metadata"), {}),
                        created_at=parse_datetime(asset.get("created_at")),
                    ))
                    counts["created_assets"] += 1

        except Exception:
            counts["failed"] += 1
            db.session.rollback()
            raise

    return counts


if __name__ == "__main__":
    try:
        print(json.dumps(import_legacy_data(), indent=2, sort_keys=True))
    except Exception as exc:
        print(f"Automation import rolled back: {exc}", file=sys.stderr)
        raise SystemExit(1)
