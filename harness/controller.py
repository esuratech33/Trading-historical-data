"""
Central portfolio controller — shared risk registry (master plan §3).

In a single-process backtest, the three strategy engines coordinate
through this module-level registry:

* Portfolio-wide daily entry cap (plan §4: max 5–6 entries/day).
* Portfolio daily loss limit — no new entries once hit (plan §6).
* Per-strategy cooldown after consecutive losses (plan §3).
* One-position-at-a-time is enforced separately: all strategies share
  one NETTING account on one instrument and check
  `portfolio.is_flat(...)` before entering, so positions never overlap
  or conflict on MNQ.

DEFAULTS BELOW ARE LABELED DECISIONS, not plan text: the plan requires
daily loss limits and cooldowns but does not fix their values.
"""

from datetime import timedelta


class PortfolioRegistry:
    def __init__(self) -> None:
        self.reset()

    def reset(
        self,
        max_entries_per_day: int = 5,
        daily_loss_limit_usd: float = 350.0,
        cooldown_after_losses: int = 2,
        cooldown_minutes: int = 60,
        daily_loss_pct: float | None = None,
        profit_target_usd: float | None = None,
        use_cooldown: bool = True,
    ) -> None:
        self.max_entries_per_day = max_entries_per_day
        self.daily_loss_limit_usd = daily_loss_limit_usd
        self.cooldown_after_losses = cooldown_after_losses
        self.cooldown_minutes = cooldown_minutes
        # Challenge-mode controls (research challenge section 7/8):
        # daily_loss_pct switches the loss limit to a percentage of
        # starting daily equity, evaluated on equity (realized +
        # unrealized) reported via update_equity; profit_target_usd
        # blocks new entries once the day's profit reaches it.
        self.daily_loss_pct = daily_loss_pct
        self.profit_target_usd = profit_target_usd
        self.use_cooldown = use_cooldown
        self.day_start_equity: float | None = None
        self.kill_switch = False
        self.target_hit = False
        self._day = None
        self.entries_today = 0
        self.realized_today = 0.0
        self.blocked_entries = 0
        self._streaks: dict[str, int] = {}
        self._cooldown_until: dict = {}
        self._last_entry_time = None

    def update_equity(self, equity: float, now) -> None:
        """Feed current account equity (realized + unrealized) each bar.

        The first report of a new ET day anchors that day's starting
        equity; the kill switch and profit target are evaluated
        against it for the rest of the day.
        """
        if self._day != now.date():
            self._roll(now)
            self.day_start_equity = equity
            self.kill_switch = False
            self.target_hit = False
        if self.day_start_equity:
            if self.daily_loss_pct is not None:
                if equity <= self.day_start_equity * (1.0 - self.daily_loss_pct):
                    self.kill_switch = True
            if self.profit_target_usd is not None:
                if equity - self.day_start_equity >= self.profit_target_usd:
                    self.target_hit = True

    def _roll(self, now) -> None:
        if self._day != now.date():
            self._day = now.date()
            self.entries_today = 0
            self.realized_today = 0.0

    def allow_entry(self, bot: str, now) -> bool:
        self._roll(now)
        if self.kill_switch or self.target_hit:
            self.blocked_entries += 1
            return False
        # Pending-entry lockout: an entry submitted on this bar has not
        # filled yet (fills land on the next bar), so block any second
        # signal within 60 seconds to prevent two bots entering at once.
        if self._last_entry_time is not None and (now - self._last_entry_time).total_seconds() < 60:
            self.blocked_entries += 1
            return False
        if self.entries_today >= self.max_entries_per_day:
            self.blocked_entries += 1
            return False
        if self.daily_loss_pct is None and self.realized_today <= -self.daily_loss_limit_usd:
            self.blocked_entries += 1
            return False
        if self.use_cooldown:
            until = self._cooldown_until.get(bot)
            if until is not None and now < until:
                self.blocked_entries += 1
                return False
        return True

    def record_entry(self, bot: str, now) -> None:
        self._roll(now)
        self.entries_today += 1
        self._last_entry_time = now

    def record_close(self, bot: str, pnl: float, now) -> None:
        self._roll(now)
        self.realized_today += pnl
        if pnl < 0:
            streak = self._streaks.get(bot, 0) + 1
            self._streaks[bot] = streak
            if streak >= self.cooldown_after_losses:
                self._cooldown_until[bot] = now + timedelta(minutes=self.cooldown_minutes)
        else:
            self._streaks[bot] = 0


REGISTRY = PortfolioRegistry()
