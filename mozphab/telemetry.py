# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import distro
import logging
import platform
import sys

from contextlib import contextmanager
from glean import Glean, Configuration, load_metrics, load_pings
from pathlib import Path

from mozphab import environment

from .bmo import BMOAPIError
from .config import config
from .helpers import prompt
from .logger import logger
from .updater import get_installed_distribution
from .user import user_data

logging.getLogger("glean").setLevel(logging.DEBUG)


def if_telemetry_enabled(func):
    def wrapper(*args, **kwargs):
        if not config.telemetry_enabled:
            return
        func(*args, **kwargs)

    return wrapper


class Telemetry:
    def __init__(self):
        dist = get_installed_distribution()

        Glean.initialize(
            application_id="MozPhab",
            application_version=dist.version,
            upload_enabled=True,
            configuration=Configuration(ping_tag="mozphab-test-tag"),
            data_dir=Path(environment.MOZBUILD_PATH) / "telemetry-data",
        )
        Glean.set_upload_enabled(True)

        self.pings = load_pings(environment.MOZPHAB_MAIN_DIR / "pings.yaml")
        self.metrics = load_metrics(environment.MOZPHAB_MAIN_DIR / "metrics.yaml")

    @if_telemetry_enabled
    def set_os(self):
        system, node, release, version, machine, processor = platform.uname()
        if system == "Linux":
            distribution_name, distribution_number, _ = distro.linux_distribution(
                full_distribution_name=False
            )
            distribution_version = " ".join([distribution_name, distribution_number])
        elif system == "Windows":
            _release, distribution_version, _csd, _ptype = platform.win32_ver()
        elif system == "Darwin":
            distribution_version, _versioninfo, _machine = platform.mac_ver()
        else:
            distribution_version = release

        self.metrics.mozphab.environment.distribution_version.set(distribution_version)

    @if_telemetry_enabled
    def set_python(self):
        self.metrics.mozphab.environment.python_version.set(platform.python_version())

    @if_telemetry_enabled
    def set_vcs(self, repo):
        self.metrics.mozphab.environment.vcs.name.set(repo.vcs)
        self.metrics.mozphab.environment.vcs.version.set(repo.vcs_version)

    @if_telemetry_enabled
    def submit(self):
        self.pings.usage.submit()
        logger.debug("Telemetry submit called.")

    def enable(self):
        config.telemetry_enabled = True
        config.write()

    def disable(self, write=True):
        config.telemetry_enabled = False
        if write:
            config.write()

    def set_metrics(self, args, is_development=False):
        if is_development:
            self.disable(write=False)
            return

        # collect data
        # User needs to call MozPhab with a "Repository command" to initiate user_data
        # for Telemetry.
        if args.needs_repo:
            if (
                args.command == "install-certificate"
                and not user_data.is_data_collected
            ):
                # Don't collect data without Phabricator's certificate.
                return

            try:
                is_data_updated = user_data.set_user_data()
            except BMOAPIError as err:
                # Error in retrieving user status.
                # We quietly allow to work without Telemetry.
                self.disable(write=False)
                logger.debug("BMOAPIErrori: %s", str(err))
                return

            # Switch on Telemetry for employee or ask to opt-in for non-employee
            if is_data_updated:
                if user_data.is_employee:
                    logger.info("Enabled collecting anonymous MozPhab usage data.")
                    self.enable()
                else:
                    # user is new or no longer employee
                    opt_in = prompt(
                        "Would you like to allow MozPhab to collect anonymous usage "
                        "data?",
                        ["Yes", "No"],
                    )
                    if opt_in == "Yes":
                        self.enable()
                    else:
                        self.disable()

        # We can't call Telemetry if User never collected any user data
        if not config.telemetry_enabled or not user_data.is_data_collected:
            return

        self.metrics.mozphab.usage.command.set(args.command)
        self.set_os()
        self.set_python()
        self.metrics.mozphab.usage.override_switch.set(
            ("--force_vcs" in sys.argv or "--force" in sys.argv),
        )
        self.metrics.mozphab.usage.duration.start()
        self.metrics.mozphab.user.installation.set(user_data.installation_id)
        self.metrics.mozphab.user.id.set(user_data.user_code)

    @contextmanager
    def timing_distribution(self, metric):
        if not config.telemetry_enabled:
            yield
            return

        timer_id = metric.start()
        yield
        metric.store_and_accumulate(timer_id)


telemetry = Telemetry()
