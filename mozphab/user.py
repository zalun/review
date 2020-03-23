# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import hashlib
import json
import time
import uuid

from mozphab import environment
from pathlib import Path

from .bmo import bmo


USER_INFO_FILE = Path(environment.MOZBUILD_PATH) / "user_info.json"
EMPLOYEE_CHECK_FREQUENCY = 24 * 7  # week


class UserData:
    is_employee = None
    user_code = None
    installation_id = None
    last_check = 0
    keys = ["is_employee", "user_code", "installation_id", "last_check"]

    def __init__(self):
        self.set_from_file()

    @property
    def is_data_collected(self):
        """True if all user info data are collected."""
        for key in self.keys:
            attr = getattr(self, key)
            if attr is None or attr == 0 and attr is not False:
                return False

        return True

    def to_dict(self):
        return dict(
            is_employee=self.is_employee,
            user_code=self.user_code,
            installation_id=self.installation_id,
        )

    def update_from_dict(self, dictionary):
        """Assign attributes from a dict."""
        for key in self.keys:
            if key in dictionary:
                setattr(self, key, dictionary[key])

    def set_from_file(self):
        if USER_INFO_FILE.exists():
            with USER_INFO_FILE.open("r", encoding="utf-8") as f:
                user_info = json.load(f)
                self.update_from_dict(user_info)

    def save_user_info(self, **kwargs):
        """Save any fields provided as kwargs into the user_info file."""
        self.update_from_dict(kwargs)
        user_info = self.to_dict()
        user_info["last_check"] = self.last_check
        with USER_INFO_FILE.open("w", encoding="utf-8") as f:
            json.dump(user_info, f, sort_keys=True, indent=2)

    def set_user_data(self, from_file_only=False):
        """Sets user data if needed.

        Returns a bool value indicating if status is updated.
        """
        if USER_INFO_FILE.exists():
            update = time.time() - self.last_check > EMPLOYEE_CHECK_FREQUENCY * 60 * 60
            if not update and self.is_data_collected:
                return False

        # Do not save the file
        if from_file_only:
            return False

        whoami = bmo.whoami()
        if whoami is None:
            return False

        if self.installation_id is None:
            self.installation_id = uuid.uuid4().hex

        self.last_check = int(time.time())
        self.user_code = hashlib.md5(whoami["name"].encode("utf-8")).hexdigest()
        self.is_employee = "mozilla-employee-confidential" in whoami["groups"]
        self.save_user_info(
            is_employee=self.is_employee,
            user_code=self.user_code,
            installation_id=self.installation_id,
            last_check=self.last_check,
        )
        return True


user_data = UserData()
