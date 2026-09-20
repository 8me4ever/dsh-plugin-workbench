"""Real-browser check for the workbench, driven with Playwright.

`smoke-client.mjs` runs the client bundle headless against a stubbed Cordis
context, which is fast and catches most things — but by construction it cannot
catch the failures that only exist *between* plugins:

  - a third-party Remote that never reaches the browser because its client half
    did not `$mount` its namespace (or did, without injecting `typert`);
  - a call rejected by the gateway's parameter-arity check, which only exists in
    the descriptor, not in the stub;
  - the `{ ok, value }` envelope, which a stub can quietly agree to skip;
  - the `main` slot handshake — a sidebar entry whose id does not match the key
    the layout dispatches, and therefore selects nothing.

All of those happened. So the seam gets one test that talks to the real host.

The script drives the whole new interaction: click the sidebar entry → the
workbench *replaces* the centre column (no overlay) → click the project card →
read the job rows → walk Back and Forward → mark a job.

Usage:
    python scripts/browser-check.py [--url http://127.0.0.1:3080/] [--no-mutate]
                                    [--jobs PATH]

Exits non-zero when the workbench does not render. Screenshots land in
`scripts/shots/`. The write test edits a real jobs.json, so it snapshots the
file first and restores it afterwards. It only runs when that path is supplied
(`--jobs`, or `$JOB_RADAR_JOBS`); the read-only assertions run regardless, and
`--no-mutate` keeps the whole run read-only.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"

# The project under test. Slot 0 is Job Radar, and its data lives *outside*
# this repo, so the path is never hard-coded here: it comes from `--jobs` or
# `$JOB_RADAR_JOBS`. Without one the write test is skipped, not silently passed.
JOBS_ENV = "JOB_RADAR_JOBS"
SLOT = "slot:0"
CONSOLE = "control-room"
HOST = "host"


def chip_counts(page) -> dict:
    """label -> data-count for every filter chip on screen."""
    out = {}
    for el in page.locator("[data-chip]").all():
        out[el.get_attribute("data-chip")] = el.get_attribute("data-count")
    return out


def view_id(page) -> str | None:
    """Which view the workbench body is showing, per its `data-view` attribute."""
    el = page.locator("[data-view]")
    return el.first.get_attribute("data-view") if el.count() else None


def card_ids(page) -> list:
    return [el.get_attribute("data-card") for el in page.locator("[data-card]").all()]


def nav_disabled(page, which: str) -> bool | None:
    el = page.locator(f'[data-nav="{which}"]')
    if not el.count():
        return None
    return el.first.is_disabled()


def run(url: str, mutate: bool, jobs: Path | None) -> dict:
    r: dict = {"console": [], "pageErrors": [], "requestFailures": []}

    # The write test touches a real jobs.json. Snapshot first, restore in a
    # finally, so a crash mid-run cannot leave the data altered.
    backup = None
    if mutate and jobs is not None and jobs.exists():
        backup = jobs.with_suffix(".json.browsercheck.bak")
        shutil.copy2(jobs, backup)
        r["jobsBackup"] = str(backup)
    elif mutate:
        r["jobsWriteSkipped"] = (
            f"no jobs.json at {jobs}" if jobs is not None
            else f"neither --jobs nor ${JOBS_ENV} was given"
        )
    SHOTS.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("console", lambda m: r["console"].append(f"{m.type}: {m.text}"[:400]))
            page.on("pageerror", lambda e: r["pageErrors"].append(str(e)[:400]))
            page.on(
                "requestfailed",
                lambda q: r["requestFailures"].append(f"{q.url} :: {q.failure}"[:400]),
            )

            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(2500)

            # 1. the workbench must NOT be showing before the entry is clicked.
            r["panelBeforeClick"] = page.locator("[data-workbench]").count()

            # 2. the sidebar-foot entry selects the panel.
            entry = page.locator('button[title="工作台"]')
            r["entryCount"] = entry.count()
            if entry.count():
                entry.first.click()
                page.wait_for_timeout(1800)
            r["entrySelected"] = (
                entry.first.get_attribute("aria-current") if entry.count() else None
            )

            # 3. the centre column is the workbench now — not a floating card.
            r["panelCount"] = page.locator("[data-workbench]").count()
            r["viewAfterOpen"] = view_id(page)
            r["cards"] = card_ids(page)
            r["dashboardJobRows"] = page.locator("[data-dashboard-job]").count()
            r["dashboardFactors"] = page.locator("[data-dashboard-factor]").count()
            r["backDisabledAtStart"] = nav_disabled(page, "back")
            r["forwardDisabledAtStart"] = nav_disabled(page, "forward")
            r["crumbConsole"] = page.locator(f'[data-crumb="{CONSOLE}"]').count()
            r["screenshotConsole"] = str(SHOTS / "console.png")
            page.screenshot(path=r["screenshotConsole"], full_page=True)
            page.set_viewport_size({"width": 560, "height": 900})
            page.wait_for_timeout(500)
            r["screenshotConsoleMobile"] = str(SHOTS / "console-mobile.png")
            page.screenshot(path=r["screenshotConsoleMobile"], full_page=True)
            r["mobileHorizontalOverflow"] = page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
            )
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.wait_for_timeout(500)

            # 4. the action card in the sidebar is untouched by the panel: the
            #    app around it still works, which is what "not an overlay" means.
            r["sidebarStillThere"] = page.locator('button[title="工作台"]').count()

            # 5. click the project card.
            card = page.locator(f'[data-card="{SLOT}"]')
            r["slotCardCount"] = card.count()
            r["slotCardLabel"] = card.first.inner_text().strip()[:200] if card.count() else None
            if card.count():
                card.first.click()
                page.wait_for_timeout(2500)
            r["viewAfterCard"] = view_id(page)
            r["crumbCurrent"] = page.locator(f'[data-crumb="{SLOT}"]').count()
            r["backDisabledInProject"] = nav_disabled(page, "back")

            # 6. what the project actually drew.
            r["jobRows"] = page.locator("[data-job]").count()
            r["missingCard"] = page.locator('[data-job-source="missing"]').count()
            r["errorCard"] = page.locator('[data-job-source="error"]').count()
            if r["errorCard"]:
                r["errorText"] = page.locator('[data-job-source="error"]').first.inner_text()[:600]
            r["markButtons"] = page.locator("[data-mark]").count()
            r["chipCounts"] = chip_counts(page)
            r["screenshot"] = str(SHOTS / "project-01.png")
            page.screenshot(path=r["screenshot"], full_page=True)

            # 7. the write path — only with a backup actually in hand.
            #
            # Guarded on `backup`, not on `mutate`: without --jobs/$JOB_RADAR_JOBS there
            # is no jobs.json to snapshot, and mutating real data with no restore point
            # is precisely what this check must never do. Gating only the *backup* on the
            # path and the *write* on `mutate` is the bug that shipped a stray status
            # change; the two must be gated together.
            if backup is not None and r["jobRows"] > 0:
                first = page.locator("[data-job]").first
                jid = first.get_attribute("data-job")
                r["firstJobId"] = jid
                r["appliedChipBefore"] = chip_counts(page).get("已投递")
                btn = page.locator(f'[data-mark="{jid}:applied"]')
                r["markButtonFound"] = btn.count() > 0
                if btn.count():
                    btn.first.click()
                    page.wait_for_timeout(2500)
                    r["appliedChipAfter"] = chip_counts(page).get("已投递")
                    r["writeErrorBar"] = page.locator("[data-job-error]").count()

            # 8. Back, then Forward — and the project must come back with data.
            page.locator('[data-nav="back"]').first.click()
            page.wait_for_timeout(1200)
            r["viewAfterBack"] = view_id(page)
            r["cardsAfterBack"] = card_ids(page)
            r["forwardDisabledAfterBack"] = nav_disabled(page, "forward")
            r["screenshotAfterBack"] = str(SHOTS / "console-after-back.png")
            page.screenshot(path=r["screenshotAfterBack"], full_page=True)

            page.locator('[data-nav="forward"]').first.click()
            page.wait_for_timeout(2500)
            r["viewAfterForward"] = view_id(page)
            r["jobRowsAfterForward"] = page.locator("[data-job]").count()

            # 9. Host diagnostics are intentionally hidden from the healthy
            #    dashboard; they remain a routed page for exceptional flows.
            page.locator('[data-nav="back"]').first.click()
            page.wait_for_timeout(1000)
            host_card = page.locator(f'[data-card="{HOST}"]')
            r["hostCardCount"] = host_card.count()

            # 10. leaving: the entry toggles the centre back to the conversation.
            if entry.count():
                entry.first.click()
                page.wait_for_timeout(1500)
            r["panelAfterExit"] = page.locator("[data-workbench]").count()
            r["viewsAfterExit"] = page.locator("[data-view]").count()

            browser.close()
    finally:
        if backup is not None:
            shutil.copy2(backup, jobs)
            backup.unlink(missing_ok=True)
            r["jobsRestored"] = True

    # The assertions worth failing on.
    r["ok"] = (
        r["panelBeforeClick"] == 0
        and r["entryCount"] == 1
        and r["entrySelected"] == "page"
        and r["panelCount"] == 1
        and r["viewAfterOpen"] == CONSOLE
        and SLOT in r["cards"]
        and HOST not in r["cards"]
        and r["dashboardJobRows"] > 0
        and r["dashboardFactors"] > 0
        and r["mobileHorizontalOverflow"] is False
        and r["backDisabledAtStart"] is True
        and r["forwardDisabledAtStart"] is True
        and r["sidebarStillThere"] == 1
        and r["slotCardCount"] == 1
        and r["viewAfterCard"] == SLOT
        and r["jobRows"] > 0
        and r["missingCard"] == 0
        and r["errorCard"] == 0
        and r["viewAfterBack"] == CONSOLE
        and r["forwardDisabledAfterBack"] is False
        and r["viewAfterForward"] == SLOT
        and r["jobRowsAfterForward"] > 0
        and r["hostCardCount"] == 0
        and r["panelAfterExit"] == 0
        and r["viewsAfterExit"] == 0
        and not r["pageErrors"]
        and not any(c.startswith("error") for c in r["console"])
    )
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:3080/")
    ap.add_argument("--no-mutate", action="store_true",
                    help="skip the write test, so jobs.json is only ever read")
    ap.add_argument("--jobs", default=os.environ.get(JOBS_ENV),
                    help="path to the job-radar jobs.json the write test edits "
                         f"(default: ${JOBS_ENV}); without it that one test is skipped")
    args = ap.parse_args()

    report = run(args.url, mutate=not args.no_mutate,
                 jobs=Path(args.jobs) if args.jobs else None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
