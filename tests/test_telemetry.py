# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import mock
import pytest

from mozphab import telemetry
from mozphab.bmo import BMOAPIError


@pytest.fixture
@mock.patch("mozphab.telemetry.config")
def get_telemetry(_config):
    t = telemetry.Telemetry()
    return t


@mock.patch("mozphab.telemetry.config")
def test_telemetry_enabled(m_config):
    m_config.telemetry_enabled = True
    passed = mock.Mock()

    @telemetry.if_telemetry_enabled
    def telemetry_pass():
        passed()

    telemetry_pass()
    passed.assert_called_once()

    passed.reset_mock()
    m_config.telemetry_enabled = False
    telemetry_pass()
    passed.assert_not_called()


@mock.patch("mozphab.telemetry.platform")
@mock.patch("mozphab.telemetry.distro")
@mock.patch("mozphab.telemetry.config")
def test_set_os(m_config, m_distro, m_platform, get_telemetry):
    m_config.telemetry_enabled = True
    t = get_telemetry
    m_platform.uname.side_effect = (("Linux", "node", "release", None, None, None),)
    m_distro.linux_distribution.side_effect = (("debian", "2020.1", None),)
    t.set_os()
    assert (
        "debian 2020.1"
        == t.metrics.mozphab.environment.distribution_version.test_get_value()
    )

    m_platform.uname.side_effect = (("Windows", "node", "release", None, None, None),)
    m_platform.win32_ver.side_effect = (("10", "10.0.18362", "", "multiprocessor"),)
    t.set_os()
    assert (
        "10.0.18362"
        == t.metrics.mozphab.environment.distribution_version.test_get_value()
    )

    m_platform.uname.side_effect = (("Darwin", "node", "release", None, None, None),)
    m_platform.mac_ver.side_effect = (("10.15.3", ("", "", ""), "x86_64"),)
    t.set_os()
    assert (
        "10.15.3" == t.metrics.mozphab.environment.distribution_version.test_get_value()
    )

    m_platform.uname.side_effect = (("Something", "node", "release", None, None, None),)
    t.set_os()
    assert (
        "release" == t.metrics.mozphab.environment.distribution_version.test_get_value()
    )


@mock.patch("mozphab.telemetry.platform")
@mock.patch("mozphab.telemetry.config")
def test_set_python(m_config, m_platform, get_telemetry):
    m_config.telemetry_enabled = True
    m_platform.python_version.side_effect = ("3.7.6",)
    t = get_telemetry
    t.metrics = mock.Mock()
    t.set_python()
    t.metrics.mozphab.environment.python_version.set.assert_called_once_with("3.7.6")


@mock.patch("mozphab.telemetry.config")
def test_disable(m_config, get_telemetry):
    get_telemetry.disable(write=False)
    assert not m_config.telemetry_enabled
    m_config.write.assert_not_called()

    get_telemetry.disable()
    assert not m_config.telemetry_enabled
    m_config.write.assert_called_once()


@mock.patch("mozphab.telemetry.config")
def test_enable(m_config, get_telemetry):
    get_telemetry.enable()
    assert m_config.telemetry_enabled
    m_config.write.assert_called_once()


@mock.patch("mozphab.telemetry.config")
@mock.patch("mozphab.telemetry.user_data")
@mock.patch("mozphab.telemetry.sys")
@mock.patch("mozphab.telemetry.prompt")
def test_set_metrics(m_prompt, m_sys, m_user_data, m_config, get_telemetry):
    m_user_data.set_user_data.return_value = False
    m_sys.argv = []
    m_config.telemetry_enabled = True
    t = get_telemetry
    t.set_os = mock.Mock()
    t.set_python = mock.Mock()

    class Args:
        def __init__(self, needs_repo=False, command="submit"):
            self.needs_repo = needs_repo
            self.command = command

    # development mode
    t.set_metrics(None, is_development=True)
    assert not m_config.telemetry_enabled
    m_user_data.set_user_data.assert_not_called()
    m_config.write.assert_not_called()

    # switched off, no repo
    t.set_metrics(Args(needs_repo=False))
    assert not t.metrics.mozphab.usage.command.test_has_value()

    # not instantiated, repo, BMOAPIError
    m_user_data.set_user_data.side_effect = BMOAPIError
    t.set_metrics(Args(needs_repo=True))
    assert not t.metrics.mozphab.usage.command.test_has_value()

    # switched off, not instantiated, repo, user data retrieved from BMO, employee
    m_user_data.set_user_data.side_effect = None
    m_user_data.set_user_data.return_value = True
    m_user_data.configure_mock(
        is_employee=True,
        is_data_collected=True,
        installation_id="install_id",
        user_code="user_code",
    )
    m_config.configure_mock(telemetry_enabled=True)
    t.set_metrics(Args(needs_repo=True))
    assert "submit" == t.metrics.mozphab.usage.command.test_get_value()
    t.set_os.assert_called_once()
    t.set_python.assert_called_once()
    assert m_config.telemetry_enabled
    assert t.metrics.mozphab.usage.override_switch.test_get_value() is False
    # `duration.start()` has been called, but not stop, it has no value yet
    # assert t.metrics.mozphab.usage.duration.test_has_value()
    assert "install_id" == t.metrics.mozphab.user.installation.test_get_value()
    # assert "user_code" == t.metrics.mozphab.user.id.test_get_value()

    # switched off, not instantiated, repo, user data retrieved from BMO, not employee
    m_user_data.is_employee = False
    m_config.telemetry_enabled = False
    # not opt-in
    m_prompt.return_value = "No"
    t.set_os.reset_mock()
    t.set_metrics(Args(needs_repo=True))
    assert not m_config.telemetry_enabled
    t.set_os.assert_not_called()

    # opt-in
    m_prompt.return_value = "Yes"
    t.set_os.reset_mock()
    t.set_metrics(Args(needs_repo=True))
    assert m_config.telemetry_enabled
    t.set_os.assert_called_once()
