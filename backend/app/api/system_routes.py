"""Endpoints for Chrome/Flow status, UI defaults and opening the export folder."""

import subprocess

from fastapi import APIRouter, HTTPException, Request

from ..flow.chrome_launcher import chrome_status, launch_chrome
from ..telegram.telegram_setup import telegram_status

router = APIRouter(prefix="/api")


@router.get("/settings")
def settings(request: Request):
    cfg = request.app.state.services.config
    return {
        "auto_gates": cfg.review.auto_gates(),
        "export_dir": str(cfg.paths.export_dir),
        "rules_file": str(cfg.paths.rules_file),
        "flow": {"model": cfg.flow.model, "aspect_ratio": cfg.flow.aspect_ratio, "max_ingredients": cfg.flow.max_ingredients},
    }


@router.get("/flow/status")
def flow_status(request: Request):
    return chrome_status(request.app.state.services.config.flow.cdp_port)


@router.post("/flow/launch-chrome")
def flow_launch(request: Request):
    cfg = request.app.state.services.config
    try:
        return launch_chrome(cfg.flow.chrome_app, cfg.paths.chrome_profile, cfg.flow.cdp_port)
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/telegram/status")
def get_telegram_status(request: Request):
    services = request.app.state.services
    return telegram_status(services.config, services.telegram)


@router.post("/open-export-dir")
def open_export_dir(request: Request):
    folder = request.app.state.services.config.paths.export_dir
    folder.mkdir(parents=True, exist_ok=True)
    subprocess.run(["open", str(folder)], check=False)
    return {"ok": True}
