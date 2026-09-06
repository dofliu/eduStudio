"""edustudio_cli — eduStudio 的 Python client 與命令列工具 (只走 REST API, 不碰 /app 前端)。

    from edustudio_cli import EduStudioClient
    c = EduStudioClient("http://localhost:8000", token="...")
    job = c.upload("lecture.pdf", "slides_pdf", project_id="wind101")
    c.wait(job["job_id"], until=("done", "failed"))
    c.download_all(job["job_id"], "out/")

命令列: `python -m edustudio_cli --help` (或安裝後 `edustudio --help`)。
"""
from .client import ComicsClient, EduStudioClient, EduStudioError

__all__ = ["EduStudioClient", "ComicsClient", "EduStudioError"]
__version__ = "0.1.0"
