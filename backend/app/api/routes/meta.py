from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, status

from app.api.deps import ServicesDep, SessionDep
from app.api.schemas import SampleOut, SettingsOut, SettingsUpdate, UploadAccepted
from app.core.errors import NotFoundError
from app.db.models import DocumentStatus
from app.llm.truth import load_truth, truth_path_for
from app.services.accuracy import AccuracyReport, evaluate
from app.services.app_settings import get_threshold, set_threshold
from app.services.documents import create_document
from app.services.extractions import rescore_all

router = APIRouter()


@router.get("/settings", response_model=SettingsOut, tags=["settings"])
def get_settings_route(services: ServicesDep, session: SessionDep) -> SettingsOut:
    s = services.settings
    return SettingsOut(
        confidence_threshold=get_threshold(session, s.confidence_threshold),
        llm_provider=s.llm_provider,
        demo_mode=s.demo_mode,
        max_upload_bytes=s.max_upload_bytes,
    )


@router.put("/settings", response_model=SettingsOut, tags=["settings"])
def update_settings(
    services: ServicesDep, session: SessionDep, body: SettingsUpdate
) -> SettingsOut:
    set_threshold(session, body.confidence_threshold)
    rescore_all(session, body.confidence_threshold)
    session.commit()
    return get_settings_route(services, session)


@router.get("/metrics/accuracy", response_model=AccuracyReport, tags=["metrics"])
def accuracy(services: ServicesDep, session: SessionDep) -> AccuracyReport:
    seen: dict[str, Path] = {}
    for directory in services.settings.fixtures_dirs:
        for pdf in sorted(Path(directory).glob("*.pdf")):
            seen.setdefault(pdf.name, pdf)
    threshold = get_threshold(session, services.settings.confidence_threshold)
    return evaluate(sorted(seen.values()), services.ocr, services.provider, threshold)


def _samples(services: ServicesDep) -> dict[str, Path]:
    directory = Path(services.settings.sample_data_dir)
    return {p.name: p for p in sorted(directory.glob("*.pdf"))} if directory.is_dir() else {}


@router.get("/samples", response_model=list[SampleOut], tags=["samples"])
def list_samples(services: ServicesDep) -> list[SampleOut]:
    out = []
    for name, path in _samples(services).items():
        truth_file = truth_path_for(path)
        truth = load_truth(truth_file) if truth_file.exists() else {}
        out.append(
            SampleOut(
                name=name,
                template=truth.get("template"),
                edge_cases=truth.get("edge_cases", []),
                size_bytes=path.stat().st_size,
            )
        )
    return out


@router.post(
    "/samples/{name}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadAccepted,
    tags=["samples"],
)
def load_sample(
    services: ServicesDep, session: SessionDep, background: BackgroundTasks, name: str
) -> UploadAccepted:
    path = _samples(services).get(name)
    if path is None:
        raise NotFoundError("Sample", name)
    doc = create_document(
        session,
        services.storage,
        filename=path.name,
        declared_type="application/pdf",
        data=path.read_bytes(),
        max_bytes=services.settings.max_upload_bytes,
    )
    background.add_task(services.pipeline.process, doc.id)
    return UploadAccepted(
        id=doc.id, status=DocumentStatus.QUEUED, status_url=f"/api/v1/documents/{doc.id}"
    )
