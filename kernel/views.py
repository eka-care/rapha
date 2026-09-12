"""Views and metrics: a queue, a summary or a dashboard, evaluated.

A view is a query over state, resources and metrics, so there is one
implementation per kind and no per screen code. The renderer receives a
ViewResult and draws it; a new queue for a dental chain is a markdown file,
not a component.

Metrics are local. There is no export here and there must never be one: the
numbers are computed on the machine that holds the records.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kernel import contracts as c
from kernel.state import actions, count, flags, line, station

# How far back each window reaches. Weeks and months are rolling and not
# calendar aligned, which is the honest thing to compute without a locale.
_BACK = {"day": timedelta(days=1), "week": timedelta(days=7), "month": timedelta(days=30)}
_EPOCH = "0001-01-01T00:00:00Z"


def window_start(window, at=None):
    at = at or datetime.now(timezone.utc)
    if window == "all":
        return _EPOCH
    if window == "day":
        at = at.replace(hour=0, minute=0, second=0, microsecond=0)
        return at.strftime("%Y-%m-%dT%H:%M:%SZ")
    return (at - _BACK[window]).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bind(query, start):
    """Replace the literal window.start in a query's conditions."""
    where = {}
    for field, cond in (query.get("where") or {}).items():
        if isinstance(cond, dict):
            cond = {op: (start if v == "window.start" else v) for op, v in cond.items()}
        where[field] = cond
    return {"resource": query["resource"], "where": where}


def metric(store, m, *, window=None, at=None):
    """One MetricValue. A zero denominator is 0, not an error: an empty week
    is a normal week at a primary health centre."""
    window = window or m.window
    start = window_start(window, at)
    num = count(store, None, _bind(m.numerator, start))
    den = None if m.denominator is None else count(store, None, _bind(m.denominator, start))
    if m.unit == "count":
        value = float(num)
    elif not den:
        value = 0.0
    else:
        value = num / den * (100.0 if m.unit == "percent" else 1.0)
    return c.MetricValue(metric=m.id, value=round(value, 2), numerator=num,
                         denominator=den, unit=m.unit, window=window, window_start=start)


def _queue(bundle, view, store, at):
    wf = bundle.workflows[view.workflow]
    rows = []
    for ref in store.threads(workflow=view.workflow, scope=view.scope):
        known = flags(store, ref.id, wf)
        rows.append(c.QueueRow(
            thread=ref.id,
            subject={k: ref.subject.get(k) for k in view.columns},
            station=station(wf, known), flags=sorted(known),
            badges={f: s for f, s in view.badges.items() if f in known},
            opened_at=ref.opened_at))

    groups = []
    if view.group_by == "station":
        # In line order, with a trailing group for a finished thread.
        for step in wf.steps:
            groups.append({"key": step.station,
                           "count": sum(1 for r in rows if r.station == step.station)})
        groups.append({"key": None, "count": sum(1 for r in rows if r.station is None)})
    elif view.group_by:
        held = sum(1 for r in rows if view.group_by in r.flags)
        groups = [{"key": view.group_by, "count": held},
                  {"key": f"not {view.group_by}", "count": len(rows) - held}]
    return rows, groups


def _summary(bundle, view, store, thread, caps):
    wf = bundle.workflows[view.workflow]
    known = flags(store, thread, wf)
    out = []
    for section in view.sections:
        if section.resource is not None:
            rows = store.select(section.resource, thread=thread,
                                where=dict(section.where or {}),
                                fields=list(section.fields), limit=50)
        elif section.show == "line":
            rows = [s.__dict__ for s in line(wf, known)]
        elif section.show == "flags":
            rows = sorted(known)
        elif section.show == "actions":
            rows = actions(wf, bundle.operations, known, caps)
        elif section.show == "proposals":
            rows = store.proposals(thread, status="pending")
        elif section.show == "audit":
            rows = store.audit(thread)
        else:
            raise ValueError(f"unknown section show '{section.show}'")
        out.append({"title": section.title, "resource": section.resource, "rows": rows})
    return out


def resolve(bundle, view_id, store, *, thread=None, caps=frozenset(), at=None):
    """Evaluate one view. `thread` is required for a summary and ignored
    otherwise. `caps` is the caller's; the capability to open the view is the
    caller's check, at the route, not here."""
    view = bundle.views[view_id]
    generated_at = (at or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")

    if view.kind == "queue":
        rows, groups = _queue(bundle, view, store, at)
    elif view.kind == "summary":
        if thread is None:
            raise ValueError(f"{view_id} is a summary and needs ?thread=")
        rows, groups = _summary(bundle, view, store, thread, caps), []
    elif view.kind == "dashboard":
        rows = [metric(store, bundle.metrics[mid], window=view.window, at=at)
                for mid in view.metrics]
        groups = []
    else:
        raise ValueError(f"unknown view kind '{view.kind}'")

    return c.ViewResult(view=view_id, kind=view.kind, rows=rows,
                        generated_at=generated_at, groups=groups)
