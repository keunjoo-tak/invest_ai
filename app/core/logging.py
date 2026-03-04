import logging
import sys


def configure_logging() -> None:
    """동작 설명은 인수인계 문서를 참고하세요."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
