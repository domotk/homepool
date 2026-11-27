"""The season state, the calendar's proposals and the step lists.

A mixin of ``PoolCoordinator``; see coordinator.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_CHLORINATOR_AUTO_TOGGLE,
    DOMAIN,
    EVENT_CHLORINATOR_SEASON_END,
    EVENT_CHLORINATOR_SEASON_START,
    EVENT_SEASON_PROPOSAL,
    EVENT_SEASON_STATE_CHANGED,
)
from ..pool.chlorine_calculator import is_chlorinator_in_season
from ..pool.checklists import CLOSING, OPENING, TREATMENT, StepDef, build, step_def
from ..pool.season import WINTER_STATES, SeasonState, season_proposal
from ..pool.tasks import FILTER_TASKS, TASKS_BY_KEY, task_applies
from ..texts import text
from .common import _parse_dt


# An unconfirmed season proposal is brought up again after this many days.
PROPOSAL_REMIND_DAYS = 7
# The proposals that come from the calendar; any other is not the calendar's
# to withdraw.
CALENDAR_PROPOSALS = ("winter", "opening")
# The list each of them opens.
PROPOSAL_LISTS = {"winter": CLOSING, "opening": OPENING}


class SeasonMixin:
    """The season state, the calendar's proposals and the step lists."""

    @property
    def season_state(self) -> str:
        """The owner's season state; set on the first load when missing."""
        return self.settings.get("season_state", SeasonState.SWIMMING)

    @property
    def winter_passive(self) -> bool:
        return self.season_state == SeasonState.WINTER_PASSIVE

    async def _async_season(self, today: date) -> None:
        """Fire the chlorinator's season events, as in 0.1.

        The cell no longer follows the calendar: it follows the season state,
        which the owner confirms (``async_set_season_state``).
        """
        if not self.is_salt:
            return
        in_season = is_chlorinator_in_season(today, self.active_months)
        if self.in_season_last is None:
            self.in_season_last = in_season
            return
        if in_season == self.in_season_last:
            return
        self.in_season_last = in_season
        event = EVENT_CHLORINATOR_SEASON_START if in_season else EVENT_CHLORINATOR_SEASON_END
        key = "season_start" if in_season else "season_end"
        message = text(self.hass.config.language, key, pool=self.pool_name)
        self.hass.bus.async_fire(
            event, {"entry_id": self.entry.entry_id, "pool": self.pool_name, "message": message}
        )
        if not self.conf.get(CONF_CHLORINATOR_AUTO_TOGGLE, True):
            # With proposals on, the season proposal's reminder replaces this one.
            await self._async_remind(text(self.hass.config.language, "title"), message)

    async def _async_season_proposal(self, now: datetime) -> None:
        """Propose the season change the calendar calls for, and bring it up
        again every week until it is confirmed or dismissed."""
        current = self.season_proposal
        to = None
        if self.conf.get(CONF_CHLORINATOR_AUTO_TOGGLE, True):
            to = season_proposal(now.date(), self.swimming_months, self.season_state)
        if (
            current is not None
            and current.get("to") not in CALENDAR_PROPOSALS
            and current.get("to") != to
        ):
            # The finished opening list proposes swimming, not the calendar:
            # it is brought up again every week, until confirmed or dismissed,
            # while the calendar calls for nothing else. Dismissed, or for the
            # state the pool is already in, it is moot: it goes, and the
            # calendar has its say. (When the calendar proposes the same, it
            # is the calendar's from here on, dismissal and all.)
            if (
                to is None
                and current.get("dismissed_for") != current.get("to")
                and current.get("to") != self.season_state
            ):
                if self._proposal_due(current, now):
                    await self._async_announce_proposal(current, now)
                    self._save()
                return
            self.season_proposal = current = None
            self._save()
        if to is None:
            if current is not None:
                self._withdraw_proposal(current)
                self._save()
            return
        is_new = current is None or current.get("to") != to
        if is_new:
            if current is not None:
                self._withdraw_proposal(current)
            self.season_proposal = current = {
                "to": to,
                "since": now.isoformat(),
                "reminded": None,
                "dismissed_for": None,
            }
        elif current.get("dismissed_for") == to:
            return
        else:
            if not self._proposal_due(current, now):
                return
        await self._async_announce_proposal(current, now)
        if is_new:
            self._open_season_checklist(to)
        self._save()

    def _withdraw_proposal(self, proposal: dict[str, Any]) -> None:
        """The calendar no longer calls for this change: the proposal goes, and
        so does the list it opened, which belongs to a season that did not
        come (a list kept would greet next year's with last year's ticks)."""
        self.season_proposal = None
        list_id = PROPOSAL_LISTS.get(proposal.get("to"))
        if list_id is not None and not self._in_season_of(list_id):
            self.checklists.pop(list_id, None)

    def _in_season_of(self, list_id: str) -> bool:
        """Whether the pool is in the state a closing or opening list prepares."""
        if list_id == CLOSING:
            return self.season_state in WINTER_STATES
        return self.season_state == SeasonState.OPENING

    @staticmethod
    def _proposal_due(proposal: dict[str, Any], now: datetime) -> bool:
        """Whether a proposal has gone a week without being brought up."""
        reminded = _parse_dt(proposal.get("reminded"))
        return reminded is None or now.date() >= (
            dt_util.as_local(reminded).date() + timedelta(days=PROPOSAL_REMIND_DAYS)
        )

    async def _async_announce_proposal(self, proposal: dict[str, Any], now: datetime) -> None:
        """Fire the proposal's event and remind the owner of it."""
        to = proposal["to"]
        proposal["reminded"] = now.isoformat()
        self.hass.bus.async_fire(
            EVENT_SEASON_PROPOSAL,
            {"entry_id": self.entry.entry_id, "pool": self.pool_name, "to": to},
        )
        language = self.hass.config.language
        await self._async_remind(
            text(language, "title") + f" · {self.pool_name}",
            text(language, f"season_proposal_{to}", pool=self.pool_name),
        )

    # ──────────────────────────────────────────
    # Checklists
    # ──────────────────────────────────────────

    @property
    def equipment(self) -> set[str]:
        """The equipment flags the step lists filter by."""
        flags = set()
        if self.is_salt:
            flags.add("salt")
        if task_applies("winter_product", self.conf):
            flags.add("winter_product")
        if task_applies("ph_calibration", self.conf):
            flags.add("ph_probe")
        return flags

    def _open_season_checklist(self, to: str) -> None:
        """Open the closing list (``to`` is "winter") or the opening list
        ("opening"), unless there is one already: an open list keeps its
        progress, and a finished one stays finished."""
        list_id = PROPOSAL_LISTS.get(to)
        if list_id is None or list_id in self.checklists:
            return
        self.checklists[list_id] = {
            "created": dt_util.utcnow().isoformat(),
            "steps": [
                {"id": s.id, "done": None} for s in build(list_id, self.equipment)
            ],
        }

    def _prune_passive_steps(self) -> None:
        """Active wintering: the steps for a pool that sits unpowered are moot."""
        closing = self.checklists.get(CLOSING)
        if closing is None:
            return
        closing["steps"] = [
            s
            for s in closing["steps"]
            if not (d := step_def(CLOSING, s["id"])) or not d.only_passive
        ]
        self._finish_if_done(CLOSING)

    def _finish_if_done(self, list_id: str) -> bool:
        """Whether every step of a list is done. A finished closing or opening
        list is kept, marked ``completed`` and no longer shown, until the next
        change of season: the state it prepares may be confirmed after it is
        done, and must not open a blank one. A treatment's list just goes."""
        checklist = self.checklists.get(list_id)
        if checklist is None or any(s["done"] is None for s in checklist["steps"]):
            return False
        if list_id == TREATMENT:
            del self.checklists[list_id]
        else:
            checklist.setdefault("completed", dt_util.utcnow().isoformat())
        return True

    def _open_list(self, list_id: str) -> dict[str, Any] | None:
        """A list that is open: there, and not finished."""
        checklist = self.checklists.get(list_id)
        if checklist is None or checklist.get("completed"):
            return None
        return checklist

    def _closing_needs_pump(self) -> bool:
        """Passive wintering with a closing step that needs the pump still open."""
        closing = self.checklists.get(CLOSING)
        if not self.winter_passive or closing is None:
            return False
        for step in closing["steps"]:
            d = step_def(CLOSING, step["id"])
            if step["done"] is None and d is not None and d.needs_pump:
                return True
        return False

    def checklist_view(self) -> dict[str, list[dict[str, Any]]]:
        """The open lists, with their texts in Home Assistant's language."""
        language = self.hass.config.language
        view: dict[str, list[dict[str, Any]]] = {}
        for list_id, checklist in self.checklists.items():
            if checklist.get("completed"):
                continue
            steps = []
            for step in checklist["steps"]:
                d = step_def(list_id, step["id"], checklist.get("treatment"))
                item = {
                    "id": step["id"],
                    "text": text(language, d.text_key) if d else step["id"],
                    "done": step["done"] is not None,
                    "done_at": step["done"],
                    # The card offers to start this treatment from the step.
                    "starts_treatment": d.starts_treatment if d else None,
                    "needs_pump": d.needs_pump if d else False,
                }
                if step["id"] == "treatment.dose" and checklist.get("dose"):
                    item["dose"] = checklist["dose"]
                steps.append(item)
            view[list_id] = steps
        return view

    def has_open_step(self, step: str) -> bool:
        checklist = self._open_list(step.split(".", 1)[0])
        return checklist is not None and any(
            s["id"] == step for s in checklist["steps"]
        )

    async def async_complete_step(self, step: str) -> None:
        """Tick a step of an open list, and what it stands for with it."""
        list_id = step.split(".", 1)[0]
        checklist = self._open_list(list_id)
        entry = next((s for s in (checklist or {}).get("steps", []) if s["id"] == step), None)
        if entry is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="step_not_open",
                translation_placeholders={"step": step, "pool": self.pool_name},
            )
        if entry["done"] is not None:
            return
        d = await self._async_tick_step(list_id, entry)
        self._save()
        if d is not None and d.completes_task:
            task = d.completes_task
            if task in FILTER_TASKS:
                # The filter's own job: a cartridge is cleaned, not backwashed.
                task = next((k for k in FILTER_TASKS if task_applies(k, self.conf)), task)
            await self.async_record_action(TASKS_BY_KEY[task].action)
        elif step == "opening.reconnect_cell":
            await self.async_set_setting("chlorinator_enabled", True)
        else:
            await self.async_refresh()

    async def _async_tick_step(self, list_id: str, entry: dict[str, Any]) -> StepDef | None:
        """Mark a step done, close its list if that was the last one, and
        propose swimming when that list was the opening. No refresh: it also
        runs from inside an evaluation, when a shock ends."""
        checklist = self.checklists[list_id]
        entry["done"] = dt_util.utcnow().isoformat()
        d = step_def(list_id, entry["id"], checklist.get("treatment"))
        if self._finish_if_done(list_id) and list_id == OPENING:
            await self._async_propose_swimming()
        return d

    async def async_dismiss_checklist(self, list_id: str) -> None:
        if self.checklists.pop(list_id, None) is not None:
            self._save()
            await self.async_refresh()

    async def _async_propose_swimming(self) -> None:
        """The opening list is done: propose the swimming state, which the owner confirms.

        Only from the opening state: ticked while wintering, the calendar's
        opening proposal still stands; ticked while swimming, there is nothing
        to propose.
        """
        if self.season_state != SeasonState.OPENING:
            return
        current = self.season_proposal
        if (
            current is not None
            and current.get("to") == "opening"
            and current.get("dismissed_for") != "opening"
        ):
            return
        now = dt_util.now()
        self.season_proposal = {
            "to": SeasonState.SWIMMING.value,
            "since": now.isoformat(),
            "reminded": None,
            "dismissed_for": None,
        }
        await self._async_announce_proposal(self.season_proposal, now)
        self._save()

    async def async_set_season_state(self, state: str) -> None:
        """The owner confirms a season state, from the select or the service."""
        new = SeasonState(state)
        old = self.season_state
        # Taken before the proposal is cleared and a finished list is gone:
        # a winter product topped up since the closing began counts.
        closing_began = self._closing_began()
        self.settings["season_state"] = new.value
        if new != old:
            # Only a real change sets the cell: confirming the state it is
            # already in keeps what the owner set by hand.
            if new == SeasonState.SWIMMING:
                self.settings["chlorinator_enabled"] = True
            elif new in WINTER_STATES:
                self.settings["chlorinator_enabled"] = False
            # Confirming the state it is already in answers no proposal: one
            # for another state stands, and is not brought up anew.
            self.season_proposal = None
        if new == SeasonState.WINTER_PASSIVE:
            # The pump never starts in passive wintering: nothing may be left running.
            self.cycle_until = None
            self.override = None
            if self.treatment is not None:
                now = dt_util.utcnow()
                self._account(now)
                # Cut short, not done: a shock does not tick its closing step.
                await self._async_finish_treatment(now, cut_short=True)
        if new != old:
            # A finished list has done its work once the season moves on,
            # except the one for the state just entered.
            for list_id in (CLOSING, OPENING):
                checklist = self.checklists.get(list_id)
                if checklist and checklist.get("completed") and not self._in_season_of(list_id):
                    del self.checklists[list_id]
            if new in WINTER_STATES and old not in WINTER_STATES:
                self.winter_entered = dt_util.utcnow()
                self.winter_top_up_from = closing_began
                # An opening list left open belongs to a season that is over.
                self.checklists.pop(OPENING, None)
                self._open_season_checklist("winter")
            elif new == SeasonState.OPENING:
                self.checklists.pop(CLOSING, None)
                self._open_season_checklist("opening")
                if self.checklists[OPENING].get("completed"):
                    # Every step done while still wintering: ready to swim.
                    await self._async_propose_swimming()
            elif new == SeasonState.SWIMMING and old in WINTER_STATES:
                # Straight from winter to swimming: the closing list is last
                # season's.
                self.checklists.pop(CLOSING, None)
        if new == SeasonState.WINTER_ACTIVE:
            self._prune_passive_steps()
        if new != old:
            self.hass.bus.async_fire(
                EVENT_SEASON_STATE_CHANGED,
                {
                    "entry_id": self.entry.entry_id,
                    "pool": self.pool_name,
                    "old": str(old),
                    "new": new.value,
                },
            )
        await self._async_maybe_recalculate(dt_util.utcnow(), force=True)
        self._save()
        await self.async_refresh()

    def _closing_began(self) -> datetime | None:
        """When the closing began: the closing list's creation or the winter
        proposal's start, whichever came first."""
        starts = []
        closing = self.checklists.get(CLOSING)
        if closing is not None:
            starts.append(_parse_dt(closing.get("created")))
        proposal = self.season_proposal
        if proposal is not None and proposal.get("to") == "winter":
            starts.append(_parse_dt(proposal.get("since")))
        starts = [s for s in starts if s is not None]
        return min(starts) if starts else None

    async def async_dismiss_season_proposal(self) -> None:
        """Not now: the proposal is not brought up again until the calendar
        calls for another change."""
        if self.season_proposal is not None:
            to = self.season_proposal["to"]
            self.season_proposal["dismissed_for"] = to
            # The list opened with the proposal goes with it.
            if to in PROPOSAL_LISTS:
                self.checklists.pop(PROPOSAL_LISTS[to], None)
        self._save()
        await self.async_refresh()

    @property
    def season_proposal_shown(self) -> str | None:
        """The change proposed and not dismissed, if any."""
        proposal = self.season_proposal
        if proposal is None or proposal.get("dismissed_for") == proposal.get("to"):
            return None
        return proposal.get("to")
