import os
import time
from dataclasses import dataclass

from qbittorrentapi import Conflict409Error

from modules import util
from modules.qbit_error_handler import handle_qbit_api_errors

logger = util.logger

RELOCATION_ACTION_RELOCATE = "relocate"
RELOCATION_ACTION_SKIP = "skip"
RELOCATION_ACTION_REFUSE = "refuse"

RELOCATION_SKIP_AUTO_TMM = "Automatic Torrent Management"
RELOCATION_SKIP_NO_CONFIGURED_PATH = "no unambiguous configured path"
RELOCATION_SKIP_INCOMPLETE = "incomplete"
RELOCATION_SKIP_ALREADY_IN_PLACE = "already in place"
RELOCATION_REFUSE_CROSS_SEED = "cross-seed"


@dataclass(frozen=True)
class RelocationPlan:
    """Outcome of evaluating the relocation guards for one torrent."""

    action: str
    reason: str | None = None
    target: str | None = None

    @property
    def relocates(self) -> bool:
        return self.action == RELOCATION_ACTION_RELOCATE


def _skip(reason: str) -> RelocationPlan:
    return RelocationPlan(action=RELOCATION_ACTION_SKIP, reason=reason)


def _refuse(reason: str) -> RelocationPlan:
    return RelocationPlan(action=RELOCATION_ACTION_REFUSE, reason=reason)


class Category:
    def __init__(self, qbit_manager, hashes: list[str] = None):
        self.qbt = qbit_manager
        self.config = qbit_manager.config
        self.hashes = hashes
        self.client = qbit_manager.client
        self.stats = 0
        self.torrents_updated = []  # List of torrents updated
        self.notify_attr = []  # List of single torrent attributes to send to notifiarr
        self.uncategorized_mapping = "Uncategorized"
        self.status_filter = "completed" if self.config.settings["cat_filter_completed"] else "all"
        self.cat_update_all = self.config.settings["cat_update_all"]
        self.category()
        self.change_categories()
        self.config.webhooks_factory.notify(self.torrents_updated, self.notify_attr, group_by="category")

    def category(self):
        """Update category for torrents that don't have any category defined and returns total number categories updated"""
        start_time = time.time()
        logger.separator("Updating Categories", space=False, border=False)
        torrent_list_filter = {"status_filter": self.status_filter}
        if self.hashes:
            torrent_list_filter["torrent_hashes"] = self.hashes
        if not self.cat_update_all and not self.hashes:
            torrent_list_filter["category"] = ""
        torrent_list = self.qbt.get_torrents(torrent_list_filter)
        for torrent in torrent_list:
            torrent_category = torrent.category
            if not torrent.auto_tmm and torrent_category:
                logger.print_line(
                    f"{torrent.name} has Automatic Torrent Management disabled and already has the category"
                    f" {torrent_category}. Skipping..",
                    "DEBUG",
                )
                continue
            new_cat = []
            new_cat.extend(self.get_tracker_cat(torrent) or self.qbt.get_category(torrent.save_path))
            if new_cat[0] == self.uncategorized_mapping:
                logger.print_line(f"{torrent.name} remains uncategorized.", "DEBUG")
                continue
            if torrent_category not in new_cat:
                self.update_cat(torrent, new_cat[0], False)

        if self.stats >= 1:
            logger.print_line(
                f"{'Did not update' if self.config.dry_run else 'Updated'} {self.stats} new categories.", self.config.loglevel
            )
        else:
            logger.print_line("No new torrents to categorize.", self.config.loglevel)

        end_time = time.time()
        duration = end_time - start_time
        logger.debug(f"Category command completed in {duration:.2f} seconds")

    def change_categories(self):
        """Handle category changes separately after main categorization"""
        if not self.config.cat_change:
            return

        logger.separator("Changing Categories", space=False, border=False)
        start_time = time.time()
        now = int(time.time())

        for torrent_category, change_config in self.config.cat_change.items():
            updated_cat = change_config["new_cat"]
            delay_minutes = change_config["delay_minutes"]

            # Get torrents with the specific category to be changed
            torrent_list_filter = {"status_filter": self.status_filter, "category": torrent_category}
            if self.hashes:
                torrent_list_filter["torrent_hashes"] = self.hashes

            torrent_list = self.qbt.get_torrents(torrent_list_filter)

            for torrent in torrent_list:
                if delay_minutes > 0:
                    completion_on = torrent.get("completion_on", 0)
                    # completion_on is -1 or 0 if not yet completed
                    if completion_on <= 0:
                        logger.debug(f"Skipping category change for {torrent.name}: torrent has not completed yet")
                        continue
                    # Compare in integer seconds (now and completion_on are both int
                    # epoch seconds) to avoid float rounding at the boundary — fire
                    # only once a full delay_minutes has elapsed (Copilot review).
                    elapsed_seconds = now - completion_on
                    if elapsed_seconds < delay_minutes * 60:
                        logger.debug(
                            f"Skipping category change for {torrent.name}: "
                            f"completed {elapsed_seconds // 60} min ago, delay is {delay_minutes} min"
                        )
                        continue
                self.update_cat(torrent, updated_cat, True)

        end_time = time.time()
        duration = end_time - start_time
        logger.debug(f"Category change command completed in {duration:.2f} seconds")

    def get_tracker_cat(self, torrent):
        tracker = self.qbt.get_tags(self.qbt.get_tracker_urls(torrent.trackers))
        return [tracker["cat"]] if tracker["cat"] else None

    def relocation_enabled(self, cat_change):
        """Report whether relocation is enabled for the selected command path."""
        return self.config.settings["cat_change_relocate" if cat_change else "cat_update_relocate"]

    def _effective_auto_tmm(self, torrent, cat_change):
        """Report whether qBittorrent governs the torrent's location for this path."""
        if torrent.auto_tmm:
            return True
        if not cat_change or not self.config.settings["force_auto_tmm"]:
            return False
        ignore_tags = self.config.settings.get("force_auto_tmm_ignore_tags", [])
        return not any(tag in (torrent.tags or "") for tag in ignore_tags)

    def relocation_plan(self, torrent, category, cat_change):
        """Evaluate the relocation guards for one torrent without changing anything."""
        if self._effective_auto_tmm(torrent, cat_change):
            return _skip(RELOCATION_SKIP_AUTO_TMM)
        target = self.qbt.category_config_path(category)
        if target is None:
            return _skip(RELOCATION_SKIP_NO_CONFIGURED_PATH)
        if not torrent.state_enum.is_complete:
            return _skip(RELOCATION_SKIP_INCOMPLETE)
        if os.path.join(torrent.save_path, "") == os.path.join(target, ""):
            return _skip(RELOCATION_SKIP_ALREADY_IN_PLACE)
        if self.qbt.has_shared_files(torrent.hash, torrent.save_path):
            return _refuse(RELOCATION_REFUSE_CROSS_SEED)
        return RelocationPlan(action=RELOCATION_ACTION_RELOCATE, target=target)

    def update_cat(self, torrent, new_cat, cat_change):
        """Update category based on the torrent information"""
        tracker = self.qbt.get_tags(self.qbt.get_tracker_urls(torrent.trackers))
        t_name = torrent.name
        old_cat = torrent.category
        plan = None
        if self.relocation_enabled(cat_change):
            plan = self.relocation_plan(torrent, new_cat, cat_change)
            if plan.action == RELOCATION_ACTION_REFUSE:
                self.report_refusal(torrent, plan.reason)
                return
            if plan.action == RELOCATION_ACTION_SKIP:
                self.report_skip(torrent, plan)
            elif self.config.dry_run:
                logger.print_line(f"Would relocate {t_name} to {plan.target}.", self.config.loglevel)
        if not self.config.dry_run:

            @handle_qbit_api_errors(context="set_category", retry_attempts=2)
            def set_category_with_creation():
                try:
                    torrent.set_category(category=new_cat)
                    if (
                        torrent.auto_tmm is False
                        and self.config.settings["force_auto_tmm"]
                        and not any(tag in torrent.tags for tag in self.config.settings.get("force_auto_tmm_ignore_tags", []))
                    ):
                        torrent.set_auto_management(True)
                except Conflict409Error:
                    # Conflict409Error with "Incorrect category name" means category doesn't exist
                    ex = logger.print_line(
                        f'Existing category "{new_cat}" not found for save path {torrent.save_path}, category will be created.',
                        self.config.loglevel,
                    )
                    self.config.notify(ex, "Update Category", False)
                    self.client.torrent_categories.create_category(name=new_cat, save_path=torrent.save_path)
                    torrent.set_category(category=new_cat)
                except Exception as e:
                    # Check if it's a category creation issue (fallback for other error types)
                    if "not found" in str(e).lower():
                        ex = logger.print_line(
                            f'Existing category "{new_cat}" not found for save path '
                            f"{torrent.save_path}, category will be created.",
                            self.config.loglevel,
                        )
                        self.config.notify(ex, "Update Category", False)
                        self.client.torrent_categories.create_category(name=new_cat, save_path=torrent.save_path)
                        torrent.set_category(category=new_cat)
                    else:
                        raise
                return True

            category_updated = set_category_with_creation()
            if category_updated and plan is not None and plan.action == RELOCATION_ACTION_RELOCATE:
                self.relocate(torrent, plan.target)
        body = []
        body += logger.print_line(logger.insert_space(f"Torrent Name: {t_name}", 3), self.config.loglevel)
        if cat_change:
            body += logger.print_line(logger.insert_space(f"Old Category: {old_cat}", 3), self.config.loglevel)
            title = "Moving Categories"
        else:
            title = "Updating Categories"
        body += logger.print_line(logger.insert_space(f"New Category: {new_cat}", 3), self.config.loglevel)
        body += logger.print_line(logger.insert_space(f"Tracker: {tracker['url']}", 8), self.config.loglevel)
        attr = {
            "function": "cat_update",
            "title": title,
            "body": "\n".join(body),
            "torrents": [t_name],
            "torrent_category": new_cat,
            "torrent_tag": ", ".join(tracker["tag"]),
            "torrent_tracker": tracker["url"],
            "notifiarr_indexer": tracker["notifiarr"],
        }
        self.notify_attr.append(attr)
        self.torrents_updated.append(t_name)
        self.stats += 1

    def _relocation_counters(self):
        """Return the per-run relocation counters, creating them on first use.

        ``__init__`` belongs to another task, so the counters are created lazily; keeping them on
        the instance means a run never shares them with another.
        """
        counters = vars(self).get("_relocation_counters_state")
        if counters is None:
            counters = {"relocated": 0, "failed": 0, "refused": 0, "skipped": {}, "skipped_names": []}
            self._relocation_counters_state = counters
        return counters

    def _relocation_attribute(self, torrent, title, body):
        """Build the notification attribute for one relocation outcome.

        Mirrors the shape of the category-update attribute built in ``update_cat`` so the existing
        grouping path in ``Webhooks.notify`` can read it.
        """
        tracker = self.qbt.get_tags(self.qbt.get_tracker_urls(torrent.trackers))
        return {
            "function": "cat_update",
            "title": title,
            "body": "\n".join(body + [logger.insert_space(f"Tracker: {tracker['url']}", 8)]),
            "torrents": [torrent.name],
            "torrent_category": torrent.category,
            "torrent_tag": ", ".join(tracker["tag"]),
            "torrent_tracker": tracker["url"],
            "notifiarr_indexer": tracker["notifiarr"],
        }

    def relocate(self, torrent, target):
        """Move a torrent to the target path and report whether the move happened."""
        relocated = self.qbt.relocate_torrent(torrent, target)
        counters = self._relocation_counters()
        if relocated:
            logger.print_line(f"Relocated {torrent.name} to {target}.", self.config.loglevel)
            self.notify_attr.append(
                self._relocation_attribute(
                    torrent,
                    "Relocating Torrents",
                    [
                        logger.insert_space(f"Torrent Name: {torrent.name}", 3),
                        logger.insert_space(f"Relocated To: {target}", 3),
                    ],
                )
            )
            self.torrents_updated.append(torrent.name)
            counters["relocated"] += 1
        else:
            logger.print_line(f"Failed to relocate {torrent.name} to {target}.", self.config.loglevel)
            self.notify_attr.append(
                self._relocation_attribute(
                    torrent,
                    "Relocation Failed",
                    [
                        logger.insert_space(f"Torrent Name: {torrent.name}", 3),
                        logger.insert_space(f"Target: {target}", 3),
                        "The relocation was not performed; the torrent remains where it was.",
                    ],
                )
            )
            counters["failed"] += 1
        return relocated

    def report_refusal(self, torrent, reason):
        """Log and notify a relocation the guards refused, with its reason."""
        logger.print_line(f"Refused to relocate {torrent.name}: {reason}.", self.config.loglevel)
        self.notify_attr.append(
            self._relocation_attribute(
                torrent,
                "Relocation Refused",
                [
                    logger.insert_space(f"Torrent Name: {torrent.name}", 3),
                    logger.insert_space(f"Reason: {reason}", 3),
                ],
            )
        )
        self.torrents_updated.append(torrent.name)
        self._relocation_counters()["refused"] += 1

    def report_skip(self, torrent, plan):
        """Log and count a skipped relocation; skips are never notified per torrent."""
        logger.print_line(f"Skipping relocation for {torrent.name}: {plan.reason}.", self.config.loglevel)
        counters = self._relocation_counters()
        skipped = counters["skipped"]
        skipped[plan.reason] = skipped.get(plan.reason, 0) + 1
        counters["skipped_names"].append(torrent.name)

    def relocation_skip_summary(self):
        """Send the run's skip summary directly, bypassing the grouping path.

        ``Webhooks.notify`` groups by ``torrent_category`` and rewrites bodies when a bucket holds
        more than one torrent, so the category-independent summary is sent here instead.
        """
        counters = self._relocation_counters()
        if not counters["skipped"]:
            return
        body = [f"Relocation skipped for {sum(counters['skipped'].values())} torrent(s):"]
        body += [logger.insert_space(f"{reason}: {count}", 3) for reason, count in counters["skipped"].items()]
        self.config.send_notifications(
            {
                "function": "cat_update",
                "title": "Relocation Skipped",
                "body": "\n".join(body),
                "torrents": list(counters["skipped_names"]),
                "torrent_category": None,
                "torrent_tag": None,
                "torrent_tracker": None,
                "notifiarr_indexer": None,
            }
        )
