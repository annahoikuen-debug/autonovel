"""Step 12 (H11): Outbox パイプラインを有効化。

H11: _process_outbox_events_async が mark_outbox_event_processed だけを呼び、
process_vector_event を呼ばなかったため、RAG/Chroma 同期が no-op だった。
修正：process_vector_event を先に呼び、成功後に done マーク。
"""
from __future__ import annotations

import inspect

from src.backend.tasks.__init__ import _process_outbox_events_async


def test_outbox_dispatches_before_mark_done():
    """process_vector_event が mark_outbox_event_processed の前に呼ばれる（H11）。"""
    src = inspect.getsource(_process_outbox_events_async)
    process_pos = src.find("process_vector_event(event)")
    mark_pos = src.find("await event_uow.mark_outbox_event_processed(event.id)")
    assert process_pos != -1, "process_vector_event が呼ばれていない (H11)"
    assert mark_pos != -1, "mark_outbox_event_processed が呼ばれていない (H11)"
    assert process_pos < mark_pos, (
        "process_vector_event が mark_outbox_event_processed より後 (H11)"
    )
