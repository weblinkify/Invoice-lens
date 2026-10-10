from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.services.container import Services


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


ServicesDep = Annotated[Services, Depends(get_services)]


def get_session(services: ServicesDep) -> Iterator[Session]:
    with services.session_factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
