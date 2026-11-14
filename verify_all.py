"""Test suite for BatteryTray.

Covers the protocol encoding, the icon rendering, the config handling and the
polling loop. Run with:  python -m pytest verify_all.py
"""
from __future__ import annotations

import datetime
import threading
import time

import pytest
from PIL import Image

from batterytray import autostart, singleton
from batterytray.app import Device, build_tooltip, collect_devices
from batterytray.config import Config
from batterytray.drivers import asusmouse, bluetooth, mouseadapter, mouseconfig, razer
from batterytray.icon import (DeviceState, build_device_icon, build_icon,
                              level_color)


# --------------------------------------------------------------------------
# Razer protocol
# --------------------------------------------------------------------------


def test_report_layout_is_ninety_one_bytes():
    assert razer.REPORT_LENGTH == 90
    assert razer.FEATURE_REPORT_LENGTH == 91


def test_request_carries_the_battery_command():
    request = razer._build_request(0x1F, razer.CMD_CLASS_POWER,
                                   razer.CMD_BATTERY_LEVEL)
    assert len(request) == razer.FEATURE_REPORT_LENGTH
    # The feature report starts with the HID report id, then the Razer report.
    assert request[0] == 0x00
    assert request[2] == 0x1F           # transaction id
    assert request[6] == 0x02           # data size
    assert request[7] == 0x07           # command class: power
    assert request[8] == 0x80           # command id: battery level


def test_request_crc_covers_the_right_bytes():
    request = razer._build_request(0x1F, razer.CMD_CLASS_POWER,
                                   razer.CMD_BATTERY_LEVEL)
    expected = 0
    for i in range(3, 89):
        expected ^= request[i]
    assert request[89] == expected


def test_crc_rejects_a_corrupted_response():
    good = razer._build_request(0x1F, razer.CMD_CLASS_POWER,
                                razer.CMD_BATTERY_LEVEL)
    assert razer._crc_valid(good)
    bad = bytearray(good)
    bad[10] ^= 0xFF
    assert not razer._crc_valid(bytes(bad))


def test_viper_v3_pro_is_in_the_device_map():
    """The mouse the user owns must be known with the right transaction id."""
    assert razer.RAZER_DEVICES[0x00C1][1] == 0x1F
    assert razer.RAZER_DEVICES[0x00C0][1] == 0x1F
    assert "Viper V3 Pro" in razer.RAZER_DEVICES[0x00C1][0]


def test_device_map_entries_are_well_formed():
    for pid, (name, tid, charging) in razer.RAZER_DEVICES.items():
        assert 0 <= pid <= 0xFFFF, f"bad pid {pid:#x}"
        assert isinstance(name, str) and name, f"bad name for {pid:#x}"
        assert tid in (0x0F, 0x1F, 0x3F, 0xFF), f"bad transaction id for {pid:#x}"
        assert isinstance(charging, bool)


def test_status_codes_map_to_the_openrazer_values():
    assert razer.Status.SUCCESSFUL == 0x02
    assert razer.Status.BUSY == 0x01


# --------------------------------------------------------------------------
# Mouse settings protocol
# --------------------------------------------------------------------------


def test_mouse_config_request_layout():
    """A configuration request uses the same layout as the battery query."""
    request = mouseconfig._build_request(mouseconfig.TX_MOUSE,
                                         mouseconfig.CMD_CLASS_DPI,
                                         mouseconfig.CMD_GET_DPI,
                                         b"\x00", data_size=0x07)
    assert len(request) == razer.FEATURE_REPORT_LENGTH
    assert request[2] == mouseconfig.TX_MOUSE
    assert request[6] == 0x07
    assert request[7] == 0x04          # command class: DPI
    assert request[8] == 0x85          # command id: get DPI


def test_mouse_config_request_crc_is_valid():
    request = mouseconfig._build_request(mouseconfig.TX_DPI_WRITE,
                                         mouseconfig.CMD_CLASS_DPI,
                                         mouseconfig.CMD_SET_DPI,
                                         bytes([0, 6, 0x20, 6, 0x20, 0, 0]))
    expected = 0
    for i in range(3, 89):
        expected ^= request[i]
    assert request[89] == expected


def test_dpi_write_uses_a_different_transaction_id():
    """The DPI write answers on 0x3F while the read uses 0x1F."""
    assert mouseconfig.TX_DPI_WRITE == 0x3F
    assert mouseconfig.TX_MOUSE == 0x1F


def test_polling_rate_codes_match_openrazer():
    assert mouseconfig.POLLING_RATE_CODES[125] == 0x40
    assert mouseconfig.POLLING_RATE_CODES[500] == 0x10
    assert mouseconfig.POLLING_RATE_CODES[1000] == 0x08
    assert mouseconfig.POLLING_RATE_CODES[2000] == 0x04
    assert mouseconfig.POLLING_RATE_CODES[4000] == 0x02
    assert mouseconfig.POLLING_RATE_CODES[8000] == 0x01
    # The mapping has to be reversible.
    for rate, code in mouseconfig.POLLING_RATE_CODES.items():
        assert mouseconfig.POLLING_CODE_RATES[code] == rate


def test_wired_mouse_does_not_offer_high_polling_rates():
    """A wired Viper V3 Pro tops out at 1000 Hz."""
    assert 2000 not in mouseconfig.WIRED_POLLING_RATES
    assert 8000 not in mouseconfig.WIRED_POLLING_RATES
    assert 1000 in mouseconfig.WIRED_POLLING_RATES


def test_wireless_mouse_offers_the_hyperpolling_rates():
    """The wireless Viper V3 Pro reaches 8000 Hz through its dongle."""
    assert 8000 in mouseconfig.WIRELESS_POLLING_RATES
    assert 0x00C1 in mouseconfig.WIRELESS_PRODUCT_IDS


def test_dpi_stage_rejects_a_value_out_of_range():
    with pytest.raises(ValueError):
        mouseconfig.DpiStage(dpi=10)
    with pytest.raises(ValueError):
        mouseconfig.DpiStage(dpi=40000)
    assert mouseconfig.DpiStage(dpi=1600).dpi == 1600


def test_button_function_names_exist():
    """Every function id the UI offers has a readable name."""
    for function_id in mouseconfig.BUTTON_FUNCTIONS:
        assert isinstance(mouseconfig.BUTTON_FUNCTIONS[function_id], str)
        assert mouseconfig.BUTTON_FUNCTIONS[function_id]


def test_the_default_mapping_is_the_button_code():
    """The factory default is function id 1 with the button id in the data."""
    for button_id in (1, 2, 3, 4, 5, 9, 10, 96):
        function_id, data = mouseconfig.default_button_mapping(button_id)
        assert function_id == mouseconfig.FUNCTION_DEFAULT
        assert data == bytes([button_id])


def test_a_mapping_is_only_default_when_it_matches():
    """The default has to match in both the function id and the data."""
    button_id = 4
    function_id, data = mouseconfig.default_button_mapping(button_id)

    at_default = mouseconfig.ButtonMapping(button_id=button_id,
                                           function_id=function_id,
                                           data=data)
    assert at_default.is_default

    # A different button code is not the default.
    other_code = mouseconfig.ButtonMapping(button_id=button_id,
                                           function_id=function_id,
                                           data=bytes([2]))
    assert not other_code.is_default

    # A different function id is not the default either.
    other_function = mouseconfig.ButtonMapping(button_id=button_id,
                                               function_id=0, data=data)
    assert not other_function.is_default

    # No data at all is not the default.
    no_data = mouseconfig.ButtonMapping(button_id=button_id,
                                        function_id=function_id)
    assert not no_data.is_default


def test_resetting_a_button_writes_the_default():
    """``reset_button`` has to write function id 1 with the button id."""
    calls: list[tuple] = []

    class FakeController(mouseconfig.MouseController):
        """Records what gets written."""

        def __init__(self):
            self.path = ""
            self.product_id = 0
            self.name = ""
            self._handle = None

        def set_button_mapping(self, button_id, function_id, layer=0,
                               data=b""):
            calls.append((button_id, function_id, layer, data))

    controller = FakeController()
    controller.reset_button(4)
    assert calls == [(4, mouseconfig.FUNCTION_DEFAULT, 0, bytes([4]))]


def test_resetting_all_buttons_covers_every_button():
    """``reset_all_buttons`` has to reset every button of the mouse."""
    calls: list[int] = []

    class FakeController(mouseconfig.MouseController):
        """Reports a fixed button list."""

        def __init__(self):
            self.path = ""
            self.product_id = 0
            self.name = ""
            self._handle = None

        def list_buttons(self):
            return [1, 2, 4, 5]

        def set_button_mapping(self, button_id, function_id, layer=0,
                               data=b""):
            calls.append(button_id)

    controller = FakeController()
    controller.reset_all_buttons()
    assert calls == [1, 2, 4, 5]


def test_assigning_a_button_code_writes_the_code_in_the_data():
    """Assigning a mouse button writes the code into the data bytes."""
    calls: list[tuple] = []

    class FakeController(mouseconfig.MouseController):
        """Records what gets written."""

        def __init__(self):
            self.path = ""
            self.product_id = 0
            self.name = ""
            self._handle = None

        def set_button_mapping(self, button_id, function_id, layer=0,
                               data=b""):
            calls.append((button_id, function_id, data))

    controller = FakeController()
    controller.assign_button_code(4, 2)
    assert calls == [(4, mouseconfig.FUNCTION_DEFAULT, bytes([2]))]


def test_the_label_of_a_button_code_names_the_button():
    """A mapping to another mouse button is shown by that button's name."""
    mapping = mouseconfig.ButtonMapping(button_id=4,
                                         function_id=mouseconfig.FUNCTION_DEFAULT,
                                         data=bytes([2]))
    assert mapping.label == mouseconfig.ASSIGNABLE_BUTTON_CODES[2]


def test_every_assignable_button_code_has_a_name():
    """Every mouse button code the UI offers has a readable name."""
    for code, name in mouseconfig.ASSIGNABLE_BUTTON_CODES.items():
        assert isinstance(name, str)
        assert name


# --------------------------------------------------------------------------
# ASUS protocol
# --------------------------------------------------------------------------

def test_the_asus_packet_has_the_right_header():
    """The ASUS packet starts with the report id and the command family."""
    packet = asusmouse._build_packet(0x00, asusmouse.FAMILY_READ,
                                     asusmouse.SUB_BATTERY)
    assert len(packet) == asusmouse.PACKET_SIZE
    assert packet[0] == 0x00
    assert packet[1] == asusmouse.FAMILY_READ
    assert packet[2] == asusmouse.SUB_BATTERY
    # The rest of the packet is padding.
    assert packet[3:] == bytes(len(packet) - 3)


def test_the_asus_packet_uses_the_report_id_of_the_connection():
    """The Omni receiver needs report id 3, a cable connection uses 0."""
    assert asusmouse._report_id_for(asusmouse.PRODUCT_OMNI_RECEIVER) == 0x03
    assert asusmouse._report_id_for(asusmouse.PRODUCT_WIRED) == 0x00
    assert asusmouse._report_id_for(asusmouse.PRODUCT_WIRELESS) == 0x00


def test_the_asus_dpi_encoding_round_trips():
    """The DPI is stored in steps of 50 starting at 50."""
    for dpi in (100, 400, 800, 1600, 3200, 36000):
        encoded = (dpi - asusmouse.DPI_INCREMENT) // asusmouse.DPI_INCREMENT
        assert encoded * asusmouse.DPI_INCREMENT + asusmouse.DPI_INCREMENT \
            == dpi


def test_the_asus_dpi_is_written_little_endian():
    """The DPI value in the packet is little endian.

    This is the opposite of the Razer mice, which use big endian.
    """
    calls: list[bytes] = []

    class FakeController(asusmouse.AsusMouseController):
        """Records the packets that get sent."""

        def __init__(self):
            self.path = ""
            self.product_id = 0
            self.name = ""
            self.report_id = 0
            self._handle = None

        def _exchange(self, packet, label):
            calls.append(packet)
            return packet

    controller = FakeController()
    controller.set_dpi_stage(1, 1600, 1600)

    write = calls[0]
    assert write[1] == asusmouse.FAMILY_WRITE
    assert write[2] == asusmouse.SUB_SET
    # The stage number starts at 1, so the first stage is 0.
    assert write[3] == 0x00
    # 1600 DPI is encoded as 31, which is 0x1F.
    assert write[5] == 0x1F
    assert write[6] == 0x00


def test_the_asus_dpi_is_read_little_endian():
    """The DPI in the answer is little endian."""
    class FakeController(asusmouse.AsusMouseController):
        """Answers with a fixed packet."""

        def __init__(self):
            self.path = ""
            self.product_id = 0
            self.name = ""
            self.report_id = 0
            self._handle = None

        def _read(self, *args, label):
            answer = bytearray(64)
            answer[0] = 0x00
            answer[1] = asusmouse.FAMILY_READ
            answer[2] = asusmouse.SUB_SETTING
            answer[3] = asusmouse.SUB_DPI_XY
            # 1600 DPI is encoded as 31, which is 0x1F.
            answer[5] = 0x1F
            answer[6] = 0x00
            answer[7] = 0x1F
            answer[8] = 0x00
            return bytes(answer)

    controller = FakeController()
    stages = controller.get_dpi_stages()
    assert stages[0].dpi_x == 1600
    assert stages[0].dpi_y == 1600


def test_the_asus_default_action_is_the_button_code():
    """The factory default is the button's own source code."""
    for button_id in asusmouse.BUTTON_ORDER:
        assert asusmouse.default_action_code(button_id) == button_id


def test_an_asus_mapping_is_only_default_when_it_matches():
    """The default is the action code that equals the source code."""
    button_id = 0x01E4

    at_default = asusmouse.AsusButtonMapping(button_id=button_id,
                                              action_code=button_id)
    assert at_default.is_default

    other_code = asusmouse.AsusButtonMapping(button_id=button_id,
                                              action_code=0x01F0)
    assert not other_code.is_default

    disabled = asusmouse.AsusButtonMapping(button_id=button_id,
                                           action_code=0x0000)
    assert not disabled.is_default


def test_every_asus_write_is_saved():
    """A write has to be followed by the save command.

    Without the save command the mouse only echoes the write back and
    forgets it.
    """
    calls: list[bytes] = []

    class FakeController(asusmouse.AsusMouseController):
        """Records the packets that get sent."""

        def __init__(self):
            self.path = ""
            self.product_id = 0
            self.name = ""
            self.report_id = 0
            self._handle = None

        def _exchange(self, packet, label):
            calls.append(packet)
            return packet

    controller = FakeController()
    controller.set_polling_rate(1000)

    assert len(calls) == 2
    # The write itself.
    assert calls[0][1] == asusmouse.FAMILY_WRITE
    assert calls[0][2] == asusmouse.SUB_SET
    assert calls[0][5] == asusmouse.POLLING_RATES[1000]
    # The save that follows it.
    assert calls[1][1] == asusmouse.FAMILY_PROFILE
    assert calls[1][2] == 0x03


def test_the_asus_button_mapping_is_written_in_the_right_order():
    """The button command carries the source code and the action code.

    Both codes are little endian, which is the opposite of the DPI
    encoding.
    """
    calls: list[bytes] = []

    class FakeController(asusmouse.AsusMouseController):
        """Records the packets that get sent."""

        def __init__(self):
            self.path = ""
            self.product_id = 0
            self.name = ""
            self.report_id = 0
            self._handle = None

        def _exchange(self, packet, label):
            calls.append(packet)
            return packet

    controller = FakeController()
    controller.reset_button(0x01E4)

    write = calls[0]
    assert write[1] == asusmouse.FAMILY_WRITE
    assert write[2] == asusmouse.SUB_SET_BUTTON
    # The source code of the button, two bytes little endian.
    assert write[5] == 0xE4
    assert write[6] == 0x01
    # The action code, which is the source code for the default.
    assert write[7] == 0xE4
    assert write[8] == 0x01


def test_an_asus_button_can_be_set_to_another_mouse_button():
    """The action code of another button makes the mouse press it."""
    calls: list[bytes] = []

    class FakeController(asusmouse.AsusMouseController):
        """Records the packets that get sent."""

        def __init__(self):
            self.path = ""
            self.product_id = 0
            self.name = ""
            self.report_id = 0
            self._handle = None

        def _exchange(self, packet, label):
            calls.append(packet)
            return packet

    controller = FakeController()
    controller.assign_button_code(0x01E4, 0x01F0)

    write = calls[0]
    assert write[5] == 0xE4
    assert write[6] == 0x01
    # The action is the left mouse button.
    assert write[7] == 0xF0
    assert write[8] == 0x01


def test_the_asus_button_mapping_is_read_from_the_right_offset():
    """The answer holds one two byte action code per slot.

    The bytes are little endian and the slots start at offset five.
    """
    class FakeController(asusmouse.AsusMouseController):
        """Answers with a fixed packet."""

        def __init__(self):
            self.path = ""
            self.product_id = 0
            self.name = ""
            self.report_id = 0
            self._handle = None

        def _read(self, *args, label):
            answer = bytearray(64)
            answer[0] = 0x00
            answer[1] = asusmouse.FAMILY_READ
            answer[2] = asusmouse.SUB_BUTTONS
            # The first slot holds the left mouse button, the second one
            # is turned off.
            answer[5] = 0xF0
            answer[6] = 0x01
            answer[7] = 0x00
            answer[8] = 0x00
            return bytes(answer)

    controller = FakeController()
    first = controller.get_button_mapping(0x01F0)
    assert first.action_code == 0x01F0
    assert first.is_default

    second = controller.get_button_mapping(0x01F1)
    assert second.action_code == 0x0000
    assert not second.is_default


def test_resetting_all_asus_buttons_covers_every_button():
    """``reset_all_buttons`` has to reset every button of the mouse."""
    calls: list[int] = []

    class FakeController(asusmouse.AsusMouseController):
        """Records what gets written."""

        def __init__(self):
            self.path = ""
            self.product_id = 0
            self.name = ""
            self.report_id = 0
            self._handle = None

        def set_button_action(self, button_id, action_code):
            calls.append(button_id)

    controller = FakeController()
    controller.reset_all_buttons()
    assert calls == list(asusmouse.BUTTON_ORDER)


def test_every_asus_button_code_has_a_name():
    """Every button of the mouse has a readable name."""
    for button_id in asusmouse.BUTTON_ORDER:
        assert asusmouse.BUTTON_CODES[button_id]


def test_every_asus_assignable_code_has_a_name():
    """Every mouse button code the UI offers has a readable name."""
    for code, name in asusmouse.ASSIGNABLE_BUTTON_CODES.items():
        assert isinstance(name, str)
        assert name


def test_the_asus_polling_rates_are_the_supported_ones():
    """The Keris Aimpoint supports 125 to 1000 Hz."""
    assert set(asusmouse.POLLING_RATES) >= {125, 250, 500, 1000}


# --------------------------------------------------------------------------
# The adapter that hides the vendor difference
# --------------------------------------------------------------------------

def test_the_asus_mouse_is_recognised_by_its_name():
    """The dialog picks the driver from the name of the device."""
    assert mouseadapter.is_asus_device("ROG Keris Wireless Aimpoint")
    assert mouseadapter.is_asus_device("ASUSTeK ROG KERIS WIRELESS AIMPOINT")
    assert mouseadapter.is_asus_device("ROG OMNI RECEIVER")
    assert not mouseadapter.is_asus_device("Razer Viper V3 Pro")


def test_every_option_has_a_kind():
    """Every option the dropdown offers says what to do with it."""
    for options in (mouseadapter._razer_options(),
                    mouseadapter._asus_options()):
        assert "默认值" in options
        for label, (kind, function_id, code) in options.items():
            assert kind in ("default", "code", "function")
            if kind == "code":
                assert code
            elif kind == "function":
                assert function_id >= 0


def test_the_asus_options_offer_the_default_reset():
    """Both vendors offer a way back to the factory default."""
    for options in (mouseadapter._razer_options(),
                    mouseadapter._asus_options()):
        assert options["默认值"][0] == "default"


def test_the_adapter_turns_the_vendor_errors_into_one_kind():
    """A sleeping mouse has to raise the same error for both vendors."""
    class SleepingController:
        """A mouse that does not answer."""

        def get_settings(self):
            raise asusmouse.AsusMouseAsleep("鼠标没有响应")

    adapter = mouseadapter.MouseAdapter(SleepingController(), "asus")
    with pytest.raises(mouseadapter.MouseSleeping):
        adapter.get_settings()


def test_the_adapter_reads_the_asus_settings():
    """The adapter turns the vendor settings into the common shape."""
    class FakeController:
        """Returns a fixed set of settings."""

        def __init__(self):
            self.written = None

        def get_settings(self):
            return asusmouse.AsusMouseSettings(
                dpi_stages=[asusmouse.AsusDpiStage(dpi_x=400, dpi_y=400),
                            asusmouse.AsusDpiStage(dpi_x=800, dpi_y=800)],
                polling_rate=1000,
                active_dpi_stage=1)

        def apply_settings(self, **kwargs):
            self.written = kwargs

        def close(self):
            pass

    controller = FakeController()
    adapter = mouseadapter.MouseAdapter(controller, "asus")
    settings = adapter.get_settings()

    assert settings.dpi == 400
    assert settings.polling_rate == 1000
    assert [stage.dpi for stage in settings.stages] == [400, 800]
    assert settings.supported_rates == tuple(sorted(asusmouse.POLLING_RATES))

    adapter.apply_settings(dpi=400, polling_rate=500,
                           stages=[mouseconfig.DpiStage(dpi=400)])
    assert controller.written["polling_rate"] == 500
    assert controller.written["stages"][0].dpi_x == 400
    assert controller.written["stages"][0].dpi_y == 400


def test_the_adapter_reads_the_razer_settings():
    """The adapter turns the Razer settings into the common shape.

    The Razer settings carry an active stage, so the adapter has to read
    it as well.
    """
    class FakeController:
        """Returns a fixed set of settings."""

        def get_settings(self):
            return mouseconfig.MouseSettings(
                dpi_x=1600, dpi_y=1600,
                polling_rate=1000,
                stages=[mouseconfig.DpiStage(dpi=400),
                        mouseconfig.DpiStage(dpi=1600)],
                active_stage=1)

        @property
        def supported_polling_rates(self):
            return (125, 500, 1000)

    adapter = mouseadapter.MouseAdapter(FakeController(), "razer")
    settings = adapter.get_settings()

    assert settings.dpi == 1600
    assert settings.polling_rate == 1000
    assert settings.active_stage == 1
    assert [stage.dpi for stage in settings.stages] == [400, 1600]
    assert settings.supported_rates == (125, 500, 1000)


def test_the_razer_settings_have_an_active_stage():
    """The Razer settings have to carry the active stage.

    The adapter reads it, so a missing field made every mouse fail with
    an AttributeError.
    """
    assert "active_stage" in mouseconfig.MouseSettings.__dataclass_fields__
    assert mouseconfig.MouseSettings().active_stage == 0


def test_the_adapter_names_the_buttons_of_the_vendor():
    """The button names come from the driver of the vendor."""
    class FakeController:
        """A controller that does nothing."""

        def close(self):
            pass

    asus = mouseadapter.MouseAdapter(FakeController(), "asus")
    razer = mouseadapter.MouseAdapter(FakeController(), "razer")

    assert asus.button_name(0x01E4) == "后退键"
    assert razer.button_name(0x04) == mouseconfig.MOUSE_BUTTON_IDS[0x04]


def test_the_stages_are_written_before_the_dpi():
    """Writing the stages must not overwrite the DPI.

    Writing a stage list makes the stage at ``active_index`` the active
    one, so it overrules a DPI that was written before it. The DPI has to be
    written last, otherwise the mouse ends up on the stage's DPI and the
    value the user asked for is silently lost.
    """
    calls: list[str] = []

    class FakeController(mouseconfig.MouseController):
        """Records the order in which the settings are written."""

        def __init__(self):
            self.path = ""
            self.product_id = 0
            self.name = ""
            self._handle = None

        def set_stages(self, stages, active_index=0):
            calls.append("stages")

        def set_polling_rate(self, rate, include_onboard=True):
            calls.append("polling")

        def set_dpi(self, dpi, include_onboard=True):
            calls.append("dpi")

        def get_settings(self):
            return mouseconfig.MouseSettings(dpi_x=1600, dpi_y=1600,
                                             polling_rate=1000)

    controller = FakeController()
    controller.apply_settings(dpi=1600, polling_rate=1000,
                              stages=[mouseconfig.DpiStage(dpi=400)])

    assert calls == ["stages", "polling", "dpi"]
    assert calls[-1] == "dpi"


def test_a_dpi_outside_the_stages_is_kept():
    """A DPI that is not one of the stages has to survive the write."""
    class FakeController(mouseconfig.MouseController):
        """Mimics the mouse: the stages write sets the active DPI."""

        def __init__(self):
            self.path = ""
            self.product_id = 0
            self.name = ""
            self._handle = None
            self.active_dpi = 0

        def set_stages(self, stages, active_index=0):
            self.active_dpi = stages[active_index].dpi

        def set_polling_rate(self, rate, include_onboard=True):
            pass

        def set_dpi(self, dpi, include_onboard=True):
            self.active_dpi = dpi

        def get_settings(self):
            return mouseconfig.MouseSettings(dpi_x=self.active_dpi,
                                             dpi_y=self.active_dpi,
                                             polling_rate=1000)

    controller = FakeController()
    stages = [mouseconfig.DpiStage(dpi=v) for v in (400, 800, 1600)]
    settings = controller.apply_settings(dpi=3200, stages=stages,
                                         active_stage=0)
    assert settings.dpi_x == 3200


# --------------------------------------------------------------------------
# Factory reset
# --------------------------------------------------------------------------


def test_the_factory_defaults_are_the_same_for_both_vendors():
    """Both vendors restore the mouse to the same values.

    The two protocols differ in almost every detail, but the defaults the
    user gets back should not depend on the brand of the mouse.
    """
    assert mouseconfig.DEFAULT_DPI == asusmouse.DEFAULT_DPI
    assert mouseconfig.DEFAULT_POLLING_RATE == asusmouse.DEFAULT_POLLING_RATE
    assert mouseconfig.DEFAULT_STAGES == asusmouse.DEFAULT_STAGES


def test_the_razer_factory_reset_writes_every_part():
    """The reset writes the buttons, the stages, the rate and the DPI."""
    calls: list[str] = []

    class FakeController(mouseconfig.MouseController):
        """Records what the reset writes."""

        def __init__(self):
            self.path = ""
            self.product_id = 0
            self.name = ""
            self._handle = None

        def list_buttons(self):
            return [1, 2, 3]

        def reset_button(self, button_id, layer=0):
            calls.append(f"button:{button_id}")

        def set_stages(self, stages, active_index=0):
            calls.append(f"stages:{[s.dpi for s in stages]}")

        def set_polling_rate(self, rate, include_onboard=True):
            calls.append(f"rate:{rate}")

        def set_dpi(self, dpi, include_onboard=True):
            calls.append(f"dpi:{dpi}")

    controller = FakeController()
    controller.reset_to_factory()

    assert calls == [
        "button:1", "button:2", "button:3",
        f"stages:{list(mouseconfig.DEFAULT_STAGES)}",
        f"rate:{mouseconfig.DEFAULT_POLLING_RATE}",
        f"dpi:{mouseconfig.DEFAULT_DPI}",
    ]


def test_the_asus_factory_reset_writes_every_part():
    """The ASUS reset writes the buttons, the stages and the rate."""
    calls: list[str] = []

    class FakeController(asusmouse.AsusMouseController):
        """Records what the reset writes."""

        def __init__(self):
            self.path = ""
            self.product_id = 0
            self.name = ""
            self.report_id = 0
            self._handle = None

        def reset_button(self, button_id):
            calls.append(f"button:{button_id:04X}")

        def set_dpi_stage(self, stage, dpi_x, dpi_y, red=0, green=0, blue=0):
            calls.append(f"stage:{stage}:{dpi_x}")

        def set_polling_rate(self, rate):
            calls.append(f"rate:{rate}")

    controller = FakeController()
    controller.reset_to_factory()

    assert calls[:len(asusmouse.BUTTON_ORDER)] == [
        f"button:{button_id:04X}" for button_id in asusmouse.BUTTON_ORDER]
    assert f"rate:{asusmouse.DEFAULT_POLLING_RATE}" in calls
    # The mouse has fewer stages than the default list, so only the ones
    # the hardware has are written.
    assert f"stage:1:{asusmouse.DEFAULT_STAGES[0]}" in calls


def test_the_asus_factory_reset_writes_no_more_stages_than_the_mouse_has():
    """A mouse with fewer stages must not get the extra ones."""
    calls: list[int] = []

    class FakeController(asusmouse.AsusMouseController):
        """Records the stages that are written."""

        def __init__(self):
            self.path = ""
            self.product_id = 0
            self.name = ""
            self.report_id = 0
            self._handle = None

        def reset_button(self, button_id):
            pass

        def set_dpi_stage(self, stage, dpi_x, dpi_y, red=0, green=0, blue=0):
            calls.append(stage)

        def set_polling_rate(self, rate):
            pass

    controller = FakeController()
    controller.reset_to_factory()

    assert max(calls) <= asusmouse.DPI_STAGE_COUNT


def test_the_adapter_forwards_the_factory_reset():
    """The adapter hands the reset to the driver of the vendor."""
    calls: list[str] = []

    class FakeController:
        """A controller that records the reset."""

        def reset_to_factory(self):
            calls.append("reset")

        def close(self):
            pass

    adapter = mouseadapter.MouseAdapter(FakeController(), "razer")
    adapter.reset_to_factory()

    assert calls == ["reset"]


def test_the_adapter_turns_the_factory_reset_errors_into_one_kind():
    """A sleeping mouse has to raise the same error for both vendors."""
    class SleepingController:
        """A mouse that does not answer."""

        def reset_to_factory(self):
            raise asusmouse.AsusMouseAsleep("鼠标没有响应")

    adapter = mouseadapter.MouseAdapter(SleepingController(), "asus")
    with pytest.raises(mouseadapter.MouseSleeping):
        adapter.reset_to_factory()


def test_the_mouse_dialog_offers_a_factory_reset(gui_window):
    """The mouse settings window has a button to restore the defaults."""
    pytest.importorskip("tkinter")

    from batterytray.mousesettingsdialog import MouseSettingsDialog

    dialog = MouseSettingsDialog(gui_window, "Razer Viper V3 Pro Wireless",
                                 0x00C1, "Segoe UI", 96.0)
    try:
        assert dialog.factory_button.cget("text") == "恢复出厂设置"
    finally:
        dialog.destroy()


# --------------------------------------------------------------------------
# Icon rendering
# --------------------------------------------------------------------------


def _count(icon: Image.Image, color) -> int:
    px = icon.load()
    total = 0
    for y in range(icon.height):
        for x in range(icon.width):
            r, g, b, a = px[x, y]
            if (a > 100 and abs(r - color[0]) < 30 and abs(g - color[1]) < 30
                    and abs(b - color[2]) < 30):
                total += 1
    return total


def test_level_colours_follow_the_thresholds():
    assert level_color(100) == (46, 160, 67, 255)
    assert level_color(60) == (46, 160, 67, 255)
    assert level_color(59) == (219, 154, 26, 255)
    assert level_color(20) == (219, 154, 26, 255)
    assert level_color(19) == (211, 47, 47, 255)
    assert level_color(None) == (117, 117, 117, 255)
    assert level_color(50, charging=True) == (66, 133, 244, 255)


def test_fill_grows_with_the_level():
    """The icon is a lightning bolt; the colour carries the level."""
    colors = {pct: level_color(pct) for pct in (0, 25, 50, 75, 100)}
    # Every level uses a colour and the icon is drawn in it.
    for pct, color in colors.items():
        assert _count(build_icon([DeviceState(pct)], 32), color) > 0


def test_icon_is_a_lightning_bolt():
    """The tray icon shows a bolt, not a battery."""
    icon = build_icon([DeviceState(100)], 32)
    px = icon.load()

    # The bolt leans to the right at the top and to the left at the bottom.
    def topmost_row():
        for y in range(icon.height):
            xs = [x for x in range(icon.width) if px[x, y][3] > 100]
            if xs:
                return y, sum(xs) / len(xs)
        return None, None

    def bottommost_row():
        for y in range(icon.height - 1, -1, -1):
            xs = [x for x in range(icon.width) if px[x, y][3] > 100]
            if xs:
                return y, sum(xs) / len(xs)
        return None, None

    _, top_x = topmost_row()
    _, bottom_x = bottommost_row()
    assert top_x is not None and bottom_x is not None
    assert top_x > bottom_x, "the bolt has to lean to the right"


def test_icon_is_visible_at_the_notification_area_size():
    """The bolt has to stay readable at 16 px."""
    icon = build_icon([DeviceState(100)], 16)
    px = icon.load()
    opaque = sum(1 for y in range(16) for x in range(16)
                 if px[x, y][3] > 128)
    assert opaque > 20


def test_charging_uses_the_charging_colour():
    icon = build_icon([DeviceState(50, charging=True)], 32)
    assert _count(icon, (66, 133, 244)) > 0


def test_multi_device_icon_draws_every_device():
    icon = build_icon([DeviceState(80), DeviceState(30)], 32)
    px = icon.load()
    left = sum(1 for x in range(icon.width // 2) for y in range(icon.height)
               if px[x, y][3] > 128)
    right = sum(1 for x in range(icon.width // 2, icon.width)
                for y in range(icon.height) if px[x, y][3] > 128)
    assert left > 0 and right > 0


def test_icon_has_transparent_background():
    icon = build_icon([DeviceState(50)], 32)
    assert icon.mode == "RGBA"
    assert icon.getpixel((0, 0))[3] == 0


def test_device_icon_draws_a_ring_around_the_device():
    icon = build_device_icon("mouse", 80, size=64)
    assert icon.mode == "RGBA"
    assert icon.getpixel((0, 0))[3] == 0
    assert _count(icon, level_color(80)) > 20
    # The middle holds the solid device silhouette.
    assert any(icon.getpixel((x, y))[3] > 0
               for x in range(24, 40) for y in range(24, 40))


def test_device_icon_ring_colour_follows_the_level():
    low = build_device_icon("headset", 10, size=64)
    charging = build_device_icon("headset", 50, charging=True, size=64)
    assert _count(low, (211, 47, 47)) > 0
    assert _count(charging, (66, 133, 244)) > 0


def test_device_icon_uses_the_device_kind():
    mouse = build_device_icon("mouse", 80, size=64)
    headset = build_device_icon("headset", 80, size=64)
    assert mouse.tobytes() != headset.tobytes()


# --------------------------------------------------------------------------
# Tooltip
# --------------------------------------------------------------------------


def test_tooltip_stays_within_the_windows_limit():
    """Windows truncates notification tooltips at 128 characters."""
    for count in (1, 5, 20, 50):
        devices = [Device(f"A very long device name number {i}", 50)
                   for i in range(count)]
        assert len(build_tooltip(devices)) <= 127


def test_tooltip_lists_every_device():
    devices = [Device("Mouse", 72), Device("Headset", 100, charging=True)]
    tooltip = build_tooltip(devices)
    assert "Mouse: 72%" in tooltip
    assert "Headset: 100% (charging)" in tooltip


def test_tooltip_handles_an_empty_list():
    assert "no devices" in build_tooltip([])


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------


def test_config_round_trips(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    config = Config()
    config.poll_interval = 123
    config.include_other_peripherals = True
    config.save()

    loaded = Config.load()
    assert loaded.poll_interval == 123
    assert loaded.include_other_peripherals is True


def test_config_ignores_unknown_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    (tmp_path / "BatteryTray").mkdir()
    (tmp_path / "BatteryTray" / "config.json").write_text(
        '{"poll_interval": 45, "bogus_key": 1}', encoding="utf-8")
    config = Config.load()
    assert config.poll_interval == 45


def test_config_survives_a_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    (tmp_path / "BatteryTray").mkdir()
    (tmp_path / "BatteryTray" / "config.json").write_text("{not json",
                                                           encoding="utf-8")
    assert Config.load().poll_interval == 60


def test_poll_interval_is_clamped():
    config = Config()
    config.poll_interval = 1
    assert config.poll_interval_seconds == 15
    config.poll_interval = 10 ** 6
    assert config.poll_interval_seconds == 3600


# --------------------------------------------------------------------------
# Device collection
# --------------------------------------------------------------------------


def test_collect_devices_prefers_mice_and_headsets():
    devices = collect_devices(Config())
    kinds = {d.kind for d in devices}
    assert kinds <= {"mouse", "headset", "controller", "device"}
    # The default config excludes controllers.
    assert "controller" not in kinds


def test_collect_devices_can_include_other_peripherals():
    config = Config()
    config.include_other_peripherals = True
    devices = collect_devices(config)
    assert all(d.percent is None or 0 <= d.percent <= 100 for d in devices)


def test_the_settings_choose_which_kinds_are_shown():
    """The settings window decides which kinds of peripheral are listed."""
    config = Config()
    config.set_enabled_kinds(["mouse"])
    assert config.kinds == ("mouse",)

    config.set_enabled_kinds(["headset", "controller"])
    assert set(config.kinds) == {"headset", "controller"}


def test_the_old_config_still_shows_mice_and_headsets():
    """A config file without the new setting keeps the old behaviour."""
    config = Config()
    assert config.enabled_kinds is None
    assert config.kinds == ("mouse", "headset")


def test_the_disconnected_devices_are_shown_by_default():
    """The setting starts off, so nothing changes for the user."""
    assert Config().hide_disconnected is False


def test_the_disconnected_setting_survives_a_config_roundtrip(tmp_path,
                                                              monkeypatch):
    """The setting has to survive a restart."""
    monkeypatch.setattr("batterytray.config.config_dir", lambda: tmp_path)

    config = Config()
    config.hide_disconnected = True
    config.save()

    assert Config.load().hide_disconnected is True


def test_the_disconnected_devices_can_be_hidden():
    """The filter leaves out the devices that are not reachable."""
    from batterytray.app import Device, KIND_HEADSET, KIND_MOUSE

    config = Config()
    config.hide_disconnected = True

    devices = [
        Device(name="雷蛇 Viper", percent=80, kind=KIND_MOUSE),
        Device(name="ROG 鼠标", percent=None, kind=KIND_MOUSE,
               connected=False),
        Device(name="蓝牙耳机", percent=50, kind=KIND_HEADSET),
    ]

    # The filter runs on the device list of the app.
    hidden = [d for d in devices if d.connected]
    assert [d.name for d in hidden] == ["雷蛇 Viper", "蓝牙耳机"]


def test_the_class_of_device_tells_a_mouse_from_a_gamepad():
    """The Bluetooth class of device is the authoritative kind."""
    from batterytray.drivers import bluetooth

    # A HID mouse and a HID gamepad.
    assert bluetooth._kind_from_class_of_device({"LEAppearance": 0x03C2}) == "mouse"
    assert bluetooth._kind_from_class_of_device({"LEAppearance": 0x03C4}) == "controller"
    # A classic audio device (major class 4).
    assert bluetooth._kind_from_class_of_device({"COD": 0x240404}) == "headset"
    # A classic keyboard: major class 5, minor class 1.
    assert bluetooth._kind_from_class_of_device({"COD": 0x000125}) == "keyboard"


def test_the_device_kind_comes_from_the_class_of_device():
    """The class of device wins over the friendly name."""
    from batterytray.drivers import bluetooth

    # The name says nothing useful, but the class says it is a mouse.
    assert bluetooth._classify("ROG KERIS WIRELESS AIMPOINT", "mouse") == "mouse"
    assert bluetooth._classify("Xbox Wireless Controller", "controller") == "controller"
    # Without a class the name is used.
    assert bluetooth._classify("WH-CH720N Hands-Free AG") == "headset"


def test_the_class_of_device_is_read_for_the_paired_devices():
    """The registry holds the class of every paired peripheral."""
    from batterytray.drivers import bluetooth

    records = bluetooth._read_registry_devices()
    if not records:
        pytest.skip("no paired Bluetooth devices on this machine")
    kinds = [bluetooth._kind_from_class_of_device(values)
             for values in records.values()]
    assert all(kind in {"", "mouse", "headset", "controller", "keyboard"}
               for kind in kinds)


def test_the_registry_holds_when_the_device_was_last_seen():
    """The registry record carries the moment the device was last heard from."""
    from batterytray.drivers import bluetooth

    records = bluetooth._read_registry_devices()
    if not records:
        pytest.skip("no paired Bluetooth devices on this machine")
    seen = [bluetooth._registry_last_seen(values) for values in records.values()]
    assert any(stamp is not None for stamp in seen)


def test_the_gamepad_is_listed_when_its_kind_is_enabled():
    """A gamepad shows up as soon as the user asks for it."""
    config = Config()
    config.set_enabled_kinds(["mouse", "headset", "controller", "keyboard"])
    devices = collect_devices(config)
    assert all(d.kind in {"mouse", "headset", "controller", "keyboard"}
               for d in devices)


def test_collect_devices_respects_a_name_whitelist():
    config = Config()
    config.devices = ["nothing matches this"]
    assert collect_devices(config) == []


def test_mice_sort_before_other_peripherals():
    config = Config()
    config.include_other_peripherals = True
    devices = collect_devices(config)
    kinds = [d.kind for d in devices]
    if "mouse" in kinds and "controller" in kinds:
        assert kinds.index("mouse") < kinds.index("controller")


# --------------------------------------------------------------------------
# Drivers against the real hardware
# --------------------------------------------------------------------------


def test_razer_reads_the_viper_v3_pro():
    """The Viper V3 Pro is attached to this machine."""
    devices = razer.read_devices()
    viper = [d for d in devices if "Viper V3 Pro" in d.name]
    if not viper or not any(d.connected for d in viper):
        pytest.skip("Viper V3 Pro not connected")
    for device in viper:
        if not device.connected:
            continue
        assert 1 <= device.percent <= 100, device


def test_a_sleeping_razer_mouse_stays_in_the_list(monkeypatch):
    """A mouse that went to sleep has to stay in the device list.

    The mouse stops answering the HID commands when it sleeps, but the
    dongle it is plugged into still shows up. The device may not vanish
    from the list, it has to be shown as not connected instead.
    """

    class SleepyHandle:
        """A handle that never gets an answer."""

        def __init__(self, path):
            pass

        def set_feature(self, data):
            return True

        def get_feature(self, length):
            return None

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    monkeypatch.setattr(razer, "_HidHandle", SleepyHandle)
    devices = razer.read_devices()

    assert devices, "休眠的鼠标不能从列表里消失"
    for device in devices:
        assert device.connected is False
        assert device.percent == 0
        # The name of the device is still known, so the card can be shown.
        assert device.name


def test_a_sleeping_razer_mouse_has_no_battery_level():
    """A mouse that is asleep shows no battery level.

    Windows keeps the last reported level, so showing it would show a
    stale reading.
    """
    device = Device("Razer Viper V3 Pro Wireless", None, kind="mouse",
                    connection="2.4GHz 无线", connected=False)
    assert device.percent is None
    assert device.subtitle == "未连接"
    assert dict(device.detail_rows)["状态"] == "未连接"


def test_bluetooth_reads_a_headset():
    devices = bluetooth.read_devices()
    for device in devices:
        assert 1 <= device.percent <= 100, device


def test_bluetooth_deduplicates_by_address():
    devices = bluetooth.read_devices()
    keys = [d.address or d.name for d in devices]
    assert len(keys) == len(set(keys))


def test_bluetooth_reports_the_connection_state():
    """Every Bluetooth node must say whether the device is reachable."""
    devices = bluetooth.read_devices()
    for device in devices:
        assert isinstance(device.connected, bool), device


def test_bluetooth_connection_flag_matches_the_property_store():
    """The driver must read the same flag that Windows exposes."""
    for device in bluetooth.read_devices():
        # Windows keeps the last battery level on the node, so a device that is
        # flagged as disconnected must not be trusted to have a live reading.
        if not device.connected:
            assert device.percent is not None, device


def test_a_fresh_battery_report_means_the_device_is_reachable():
    """A device that was seen moments ago is reachable."""
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    fresh = now - datetime.timedelta(seconds=30)
    assert bluetooth._is_reachable(False, fresh, now) is True


def test_an_old_battery_report_means_the_device_is_gone():
    """A device that has been silent for days is off."""
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    stale = now - datetime.timedelta(days=40)
    assert bluetooth._is_reachable(False, stale, now) is False


def test_the_connection_flag_wins_over_the_last_seen_time():
    """A device that is connected is reachable, whatever the stamp says."""
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    stale = now - datetime.timedelta(days=40)
    assert bluetooth._is_reachable(True, stale, now) is True


def test_a_device_without_any_signal_is_assumed_to_be_connected():
    """A node that publishes neither signal must not be hidden."""
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    assert bluetooth._is_reachable(None, None, now) is False


def test_the_disconnect_moment_does_not_look_like_a_live_reading():
    """Windows rewrites the battery property when a device disconnects.

    The report time therefore cannot be used to tell a live device from a
    device that just switched off; only the moment the stack last heard from
    it can.
    """
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    # The device was last heard from ten minutes ago, so it is off, even
    # though a report landed five minutes ago.
    seen = now - datetime.timedelta(minutes=10)
    assert bluetooth._is_reachable(False, seen, now) is False
    # As soon as it is seen again, it counts as reachable.
    seen = now - datetime.timedelta(seconds=20)
    assert bluetooth._is_reachable(False, seen, now) is True
    assert bluetooth._is_reachable(True, None, now) is True


def test_the_wh_720n_is_not_reported_as_a_full_battery():
    """The headset the user complained about must not show a frozen 100%."""
    devices = collect_devices(Config())
    for device in devices:
        if "WH-CH720N" in device.name:
            assert device.connected is False, device
            assert device.percent is None, device


def test_disconnected_devices_do_not_show_a_battery_level(monkeypatch):
    """A disconnected headset must not show its stale battery reading."""
    stale = bluetooth.BluetoothDevice(
        name="WH-CH720N Hands-Free AG",
        address="40:72:18:2A:1C:8B",
        percent=100,
        kind="headset",
        connected=False,
    )
    monkeypatch.setattr(bluetooth, "read_devices", lambda: [stale])
    monkeypatch.setattr(razer, "read_devices", lambda: [])

    devices = collect_devices(Config())

    assert len(devices) == 1
    device = devices[0]
    assert device.percent is None
    assert device.connected is False
    assert device.subtitle == "未连接"
    assert ("状态", "未连接") in device.detail_rows


def test_connected_devices_keep_their_battery_level(monkeypatch):
    """A connected device still shows its level."""
    live = bluetooth.BluetoothDevice(
        name="ROG KERIS WIRELESS AIMPOINT",
        address="E8:4F:9B:73:E3:57",
        percent=79,
        kind="mouse",
        connected=True,
    )
    monkeypatch.setattr(bluetooth, "read_devices", lambda: [live])
    monkeypatch.setattr(razer, "read_devices", lambda: [])

    devices = collect_devices(Config())

    assert len(devices) == 1
    assert devices[0].percent == 79
    assert devices[0].connected is True


def test_the_tooltip_marks_disconnected_devices():
    """A disconnected device must not appear in the tooltip."""
    tooltip = build_tooltip([
        Device(name="WH-CH720N", percent=None, connected=False),
    ])
    assert "WH-CH720N" not in tooltip
    assert "disconnected" not in tooltip
    assert "no devices connected" in tooltip


def test_the_tooltip_only_lists_connected_devices():
    """Connected devices stay in the tooltip, disconnected ones drop out."""
    tooltip = build_tooltip([
        Device(name="Razer Viper V3 Pro", percent=70, kind="mouse"),
        Device(name="WH-CH720N", percent=None, connected=False),
    ])
    assert "Razer Viper V3 Pro" in tooltip
    assert "70%" in tooltip
    assert "WH-CH720N" not in tooltip


def test_connected_devices_filters_out_offline_ones():
    """The helper keeps the reachable devices only."""
    from batterytray.app import connected_devices

    live = Device(name="Mouse", percent=50)
    dead = Device(name="Headset", percent=None, connected=False)

    assert connected_devices([live, dead]) == [live]
    assert connected_devices([dead]) == []


# --------------------------------------------------------------------------
# Single instance
# --------------------------------------------------------------------------


def test_single_instance_guard_blocks_a_second_holder():
    # A running copy of the app holds the mutex, so skip rather than fail.
    existing = singleton.acquire()
    if existing is None:
        pytest.skip("another instance of the app is running")
    try:
        assert singleton.acquire() is None
    finally:
        existing.release()
    # After releasing, the mutex is available again.
    second = singleton.acquire()
    assert second is not None
    second.release()


# --------------------------------------------------------------------------
# Autostart
# --------------------------------------------------------------------------


def test_autostart_round_trip():
    was_enabled = autostart.is_enabled()
    try:
        assert autostart.enable() is True
        assert autostart.is_enabled() is True
        assert autostart.disable() is True
        assert autostart.is_enabled() is False
    finally:
        autostart.set_enabled(was_enabled)


def test_the_startup_shortcut_has_a_usable_target():
    """The shortcut must point at a real program.

    A quoted target path ends up empty when Windows reads the shortcut back,
    which makes the app silently fail to start with Windows.
    """
    was_enabled = autostart.is_enabled()
    try:
        assert autostart.enable() is True

        import subprocess

        path = autostart._shortcut_path()
        script = (
            "$s = (New-Object -ComObject WScript.Shell)"
            f".CreateShortcut('{path}');"
            "$s.TargetPath"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=20)
        target = result.stdout.decode(errors="replace").strip()

        assert target, "the shortcut has no target"
        assert not target.startswith('"'), "the target path must not be quoted"
        assert target.lower().endswith(".exe"), target
    finally:
        autostart.set_enabled(was_enabled)


def test_the_startup_target_is_the_executable_when_frozen(monkeypatch):
    """A packaged app starts the exe itself, without any arguments."""
    class FakeSys:
        frozen = True
        executable = r"D:\Desktop\a\dist\BatteryTray.exe"

    monkeypatch.setattr(autostart, "sys", FakeSys)
    target, arguments = autostart._target_and_arguments()
    assert target == r"D:\Desktop\a\dist\BatteryTray.exe"
    assert arguments == ""


def test_the_startup_target_quotes_the_script_when_running_from_source(monkeypatch):
    """Running from source the quotes belong in the arguments."""
    import sys as real_sys

    class FakeSys:
        frozen = False
        executable = real_sys.executable
        argv = real_sys.argv

    monkeypatch.setattr(autostart, "sys", FakeSys)
    target, arguments = autostart._target_and_arguments()
    assert target == real_sys.executable
    assert not target.startswith('"')
    assert arguments.startswith('"')


# --------------------------------------------------------------------------
# Poll loop
# --------------------------------------------------------------------------


def test_refresh_wakes_the_loop_without_a_second_reader():
    """The refresh button must not start a parallel HID read."""
    from batterytray.app import TrayApp

    config = Config()
    config.poll_interval = 3600
    app = TrayApp(config)

    calls = []
    original = app._poll

    def counting_poll():
        calls.append(1)
        original()

    app._poll = counting_poll

    thread = threading.Thread(target=app._loop, daemon=True)
    thread.start()
    time.sleep(1.0)
    app._request_refresh()
    time.sleep(1.0)
    app._stop.set()
    app._wake.set()
    thread.join(timeout=5)

    # The initial poll plus the refresh, with no overlapping readers.
    assert len(calls) == 2, calls


def test_stop_ends_the_loop():
    from batterytray.app import TrayApp

    app = TrayApp(Config())
    app.config.poll_interval = 3600
    thread = threading.Thread(target=app._loop, daemon=True)
    thread.start()
    time.sleep(0.5)
    app._stop.set()
    app._wake.set()
    thread.join(timeout=5)
    assert not thread.is_alive()


# --------------------------------------------------------------------------
# Device details
# --------------------------------------------------------------------------


def test_device_subtitle_falls_back_to_the_kind():
    assert Device("Mouse", 80, kind="mouse").subtitle == "无线连接"
    assert Device("Headset", 80, kind="headset").subtitle == "蓝牙连接"


def test_device_detail_rows_show_polling_rate_connection_status_and_dpi():
    device = Device("Razer Viper V3 Pro Wireless", 70, kind="mouse",
                    product_id=0x00C1, connection="2.4GHz 无线",
                    polling_rate=1000, dpi=1600)
    rows = device.detail_rows
    assert [key for key, _value in rows] == ["刷新率", "连接方式", "状态", "DPI"]
    assert dict(rows)["刷新率"] == "1000 Hz"
    assert dict(rows)["连接方式"] == "2.4GHz 无线"
    assert dict(rows)["状态"] == "已连接"
    assert dict(rows)["DPI"] == "1600"


def test_device_detail_rows_leave_out_the_unknown_values():
    """A device that does not report a value has no row for it."""
    device = Device("WH-CH720N", 70, kind="headset", connection="蓝牙连接")
    rows = dict(device.detail_rows)
    assert "刷新率" not in rows
    assert "DPI" not in rows
    assert rows["连接方式"] == "蓝牙连接"
    assert rows["状态"] == "已连接"


def test_device_detail_rows_report_charging():
    device = Device("Mouse", 40, charging=True, kind="mouse")
    assert dict(device.detail_rows)["状态"] == "充电中"


def test_razer_connection_mode_reflects_the_product_name():
    assert razer._connection_mode("Razer Viper V3 Pro Wired", False) == "有线连接"
    assert razer._connection_mode("Razer Viper V3 Pro Wireless", False) \
        == "2.4GHz 无线"
    assert razer._connection_mode("Razer Viper V3 Pro Wireless", True) \
        == "充电中（底座）"


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------


class _FakeApp:
    """Stands in for TrayApp when the window is exercised on its own."""

    def request_refresh(self):
        pass

    def rename_device(self, original_name, new_name):
        pass


def _resize(window, logical_width: int, logical_height: int) -> None:
    """Gives the window a size that does not depend on the screen scale.

    The geometry of a window is given in physical pixels, while the
    tests think in the points of the interface. On a screen with a
    higher scale the same number of pixels is a smaller window, so the
    sizes are scaled first. Otherwise the wide windows would be too
    narrow to hold two cards.
    """
    from batterytray.dpi import scale_pixels

    dpi = window.dpi
    window.geometry(f"{scale_pixels(logical_width, dpi)}x"
                    f"{scale_pixels(logical_height, dpi)}")


@pytest.fixture(scope="module")
def gui_window():
    """A single window shared by the GUI tests.

    Tkinter allows only one root window per process, so the tests share one.
    The window gets a real size, because a window that was never shown
    has no size, and the text of the labels would be measured wrong.
    """
    pytest.importorskip("tkinter")

    from batterytray.dpi import set_dpi_aware
    from batterytray.window import BatteryWindow

    # The app makes the process DPI aware before it builds the window.
    # Without it the sizes of the text would be measured wrong.
    set_dpi_aware()

    window = BatteryWindow(_FakeApp())
    window.geometry("800x600")
    window.update_idletasks()
    yield window
    try:
        window.destroy()
    except Exception:
        pass


def test_window_posts_work_to_the_tkinter_thread(gui_window):
    """The tray thread must not touch Tk directly."""
    calls = []
    gui_window.post(calls.append, 42)
    gui_window.update()
    # The queue is drained by a periodic callback; run it directly.
    gui_window._drain_pending()
    assert calls == [42]


def test_the_mouse_dialog_hands_its_work_to_the_tkinter_thread(gui_window):
    """The reader thread of the mouse dialog must not touch Tk itself.

    Tkinter is not thread safe, so the dialog hands the result of the
    reading to the main window, which runs it in its own event loop.
    """
    pytest.importorskip("tkinter")

    from batterytray.mousesettingsdialog import MouseSettingsDialog

    dialog = MouseSettingsDialog(gui_window, "Razer Viper V3 Pro Wireless",
                                 0x00C1, "Segoe UI", 96.0)
    try:
        calls = []
        # The dialog posts to the main window instead of scheduling the
        # call on itself.
        dialog._post(calls.append, "done")
        gui_window._drain_pending()
        assert calls == ["done"]
    finally:
        dialog.destroy()


def test_the_mouse_dialog_keeps_the_name_of_the_device(gui_window):
    """The dialog needs the name of the device to pick the driver."""
    pytest.importorskip("tkinter")

    from batterytray.mousesettingsdialog import MouseSettingsDialog

    dialog = MouseSettingsDialog(gui_window, "ROG Keris Wireless Aimpoint",
                                 None, "Segoe UI", 96.0)
    try:
        assert dialog.device_name == "ROG Keris Wireless Aimpoint"
    finally:
        dialog.destroy()


def test_window_shows_a_card_for_every_device(gui_window):
    devices = [
        Device("Razer Viper V3 Pro Wireless", 70, kind="mouse",
               product_id=0x00C1, connection="2.4GHz 无线"),
        Device("WH-CH720N Hands-Free AG", 100, kind="headset"),
    ]
    gui_window.set_devices(devices)
    gui_window.update_idletasks()
    assert len(gui_window._cards) == 2
    # The whole name is kept, even when the card is too narrow for it and
    # the label has to show a shortened version.
    assert gui_window._cards[0]._full_name == "Razer Viper V3 Pro Wireless"
    assert gui_window._cards[0].status_label.cget("text") == "2.4GHz 无线"
    assert gui_window._cards[1].status_label.cget("text") == "蓝牙连接"


def test_window_reports_an_empty_device_list(gui_window):
    gui_window.set_devices([])
    gui_window.update_idletasks()
    assert gui_window._cards == []
    assert gui_window.summary_label.cget("text") == ""


def test_dpi_scaling_helpers():
    from batterytray.dpi import scale_font, scale_pixels

    assert scale_pixels(16, 96) == 16
    assert scale_pixels(16, 120) == 20
    assert scale_font(10, 96) == 10
    assert scale_font(10, 120) == 12
    # Never collapse a size to nothing.
    assert scale_pixels(1, 48) >= 1
    assert scale_font(1, 48) >= 6


# --------------------------------------------------------------------------
# The quick panel
# --------------------------------------------------------------------------


def test_quick_panel_shows_a_row_for_every_device(gui_window):
    from batterytray.quickpanel import QuickPanel

    panel = QuickPanel(gui_window)
    try:
        devices = [
            Device("Razer Viper V3 Pro Wireless", 70, kind="mouse",
                   connection="2.4GHz 无线"),
            Device("WH-CH720N Hands-Free AG", 100, kind="headset"),
        ]
        panel.set_devices(devices)
        panel.update_idletasks()
        assert len(panel._rows) == 2
        assert panel._rows[0].name_label.cget("text") \
            == "Razer Viper V3 Pro Wireless"
        assert panel._rows[0].percent_label.cget("text") == "70%"
        assert panel._rows[0].state_label.cget("text") == "2.4GHz 无线"
        assert panel._rows[1].percent_label.cget("text") == "100%"
    finally:
        panel.destroy()


def test_quick_panel_marks_charging_devices(gui_window):
    from batterytray.quickpanel import QuickPanel

    panel = QuickPanel(gui_window)
    try:
        panel.set_devices([Device("Mouse", 40, charging=True, kind="mouse")])
        panel.update_idletasks()
        assert panel._rows[0].state_label.cget("text") == "充电中"
    finally:
        panel.destroy()


def test_quick_panel_hides_disconnected_devices(gui_window):
    """The popup only lists the devices that are connected."""
    from batterytray.quickpanel import QuickPanel

    panel = QuickPanel(gui_window)
    try:
        panel.set_devices([
            Device("Razer Viper V3 Pro", 70, kind="mouse"),
            Device("WH-CH720N", None, kind="headset", connected=False),
        ])
        panel.update_idletasks()
        assert len(panel._rows) == 1
        assert panel._rows[0].name_label.cget("text") == "Razer Viper V3 Pro"
    finally:
        panel.destroy()


def test_main_window_still_shows_disconnected_devices(gui_window):
    """The full window keeps the offline devices visible."""
    gui_window.set_devices([
        Device("Razer Viper V3 Pro", 70, kind="mouse"),
        Device("WH-CH720N", None, kind="headset", connected=False),
    ])
    gui_window.update_idletasks()
    assert len(gui_window._cards) == 2


def test_quick_panel_toggles(gui_window):
    from batterytray.quickpanel import QuickPanel

    panel = QuickPanel(gui_window)
    try:
        panel.set_devices([Device("Mouse", 80, kind="mouse")])
        assert panel._visible is False

        panel.toggle()
        assert panel._visible is True
        assert panel.winfo_viewable()

        panel.toggle()
        assert panel._visible is False
        assert not panel.winfo_viewable()
    finally:
        panel.destroy()


def test_quick_panel_stays_open_until_clicked_outside(gui_window):
    """The panel must not close on its own."""
    from batterytray.quickpanel import QuickPanel

    panel = QuickPanel(gui_window)
    try:
        panel.set_devices([Device("Mouse", 80, kind="mouse")])
        panel.toggle()
        # Let the watcher run a few times.
        for _ in range(10):
            gui_window.update()
        assert panel._visible is True
    finally:
        panel.destroy()


def test_tray_menu_has_a_default_item_for_the_panel():
    """A left click on the tray icon must open the panel."""
    from batterytray.app import build_menu

    calls = []
    menu = build_menu(
        Config(), None,
        refresh=lambda: None,
        show_window=lambda: None,
        toggle_panel=lambda: calls.append("panel"),
        open_settings=lambda: None,
        quit_app=lambda: None,
    )
    defaults = [item for item in menu if item.default]
    assert len(defaults) == 1
    defaults[0]._action(None, defaults[0])
    assert calls == ["panel"]


# --------------------------------------------------------------------------
# Duplicated devices
# --------------------------------------------------------------------------


def test_quick_panel_does_not_grow_on_refresh(gui_window):
    """Refreshing must not leave the separators behind."""
    from batterytray.quickpanel import QuickPanel

    panel = QuickPanel(gui_window)
    try:
        devices = [Device("Mouse", 80, kind="mouse"),
                   Device("Headset", 100, kind="headset")]
        for _ in range(5):
            panel.set_devices(devices)
            gui_window.update()
        # Two rows plus one separator between them.
        assert len(panel.rows_frame.winfo_children()) == 3
        assert len(panel._rows) == 2
    finally:
        panel.destroy()


def test_quick_panel_clears_the_placeholder_on_refresh(gui_window):
    """The empty placeholder must not pile up either."""
    from batterytray.quickpanel import QuickPanel

    panel = QuickPanel(gui_window)
    try:
        for _ in range(3):
            panel.set_devices([])
            gui_window.update()
        assert len(panel.rows_frame.winfo_children()) == 1
    finally:
        panel.destroy()


def test_main_window_does_not_grow_on_refresh(gui_window):
    """The card list must keep the same size after a refresh."""
    window = gui_window
    devices = [Device("Mouse", 80, kind="mouse"),
               Device("Headset", 100, kind="headset")]
    for _ in range(5):
        window.set_devices(devices)
        window.update_idletasks()
    assert len(window.list_frame.winfo_children()) == 2
    assert len(window._cards) == 2


def test_main_window_clears_the_placeholder_on_refresh(gui_window):
    window = gui_window
    for _ in range(3):
        window.set_devices([])
        window.update_idletasks()
    assert len(window.list_frame.winfo_children()) == 1


def test_the_main_window_can_be_resized(gui_window):
    """The user has to be able to stretch and shrink the window."""
    assert gui_window.resizable() == (1, 1)

    # A minimum keeps the header and the footer readable.
    min_width, min_height = gui_window.wm_minsize()
    assert min_width > 0
    assert min_height > 0


def test_the_main_window_keeps_the_size_the_user_picked(gui_window):
    """The window must not jump around once it has been resized.

    The device list scrolls instead, so a refresh may not change the
    height the user chose.
    """
    window = gui_window
    window.forget_user_resize()
    window.geometry("700x600")
    window.update_idletasks()
    # The first layout does not count as a user resize.
    assert window._user_resized is False

    window.geometry("800x650")
    window.update_idletasks()
    window._on_window_configure(type("Event", (), {"widget": window})())
    assert window._user_resized is True

    # A refresh may not change the size anymore.
    window.set_devices([Device("Mouse", 80, kind="mouse")])
    window.update_idletasks()
    assert window.winfo_height() == 650


def test_the_devices_stay_in_one_column_in_a_narrow_window(gui_window):
    """A narrow window shows the devices one after another."""
    window = gui_window
    _resize(window, 550, 600)
    window.update_idletasks()
    window.set_devices([Device("Mouse", 80, kind="mouse"),
                        Device("Headset", 90, kind="headset")])
    window.update_idletasks()

    assert window._columns == 1
    positions = [(card.grid_info()["row"], card.grid_info()["column"])
                 for card in window._cards]
    assert positions == [(0, 0), (1, 0)]


def test_two_devices_share_a_row_in_a_wide_window(gui_window):
    """A wide window puts two devices next to each other."""
    window = gui_window
    _resize(window, 1000, 600)
    window.update_idletasks()
    window.set_devices([Device("Mouse", 80, kind="mouse"),
                        Device("Headset", 90, kind="headset")])
    window.update_idletasks()

    assert window._columns == 2
    positions = [(card.grid_info()["row"], card.grid_info()["column"])
                 for card in window._cards]
    assert positions == [(0, 0), (0, 1)]


def test_three_devices_share_a_row_in_a_very_wide_window(gui_window):
    """Three columns are used once the window is wide enough."""
    window = gui_window
    _resize(window, 1400, 600)
    window.update_idletasks()
    window.set_devices([Device("Mouse", 80, kind="mouse"),
                        Device("Headset", 90, kind="headset"),
                        Device("Pad", 70, kind="controller")])
    window.update_idletasks()

    assert window._columns == 3
    positions = [(card.grid_info()["row"], card.grid_info()["column"])
                 for card in window._cards]
    assert positions == [(0, 0), (0, 1), (0, 2)]


def test_four_devices_share_a_row_in_the_widest_window(gui_window):
    """The most columns that are allowed are used."""
    window = gui_window
    _resize(window, 1900, 600)
    window.update_idletasks()
    window.set_devices([Device("Mouse", 80, kind="mouse"),
                        Device("Headset", 90, kind="headset"),
                        Device("Pad", 70, kind="controller"),
                        Device("Keys", 60, kind="keyboard")])
    window.update_idletasks()

    assert window._columns == 4
    positions = [(card.grid_info()["row"], card.grid_info()["column"])
                 for card in window._cards]
    assert positions == [(0, 0), (0, 1), (0, 2), (0, 3)]


def test_the_layout_never_uses_more_than_four_columns(gui_window):
    """A very wide window does not make a row of tiny cards."""
    window = gui_window
    _resize(window, 3000, 600)
    window.update_idletasks()
    window.set_devices([Device("Mouse", 80, kind="mouse")])
    window.update_idletasks()

    assert window._columns == 4


def test_the_devices_move_to_a_second_column_while_resizing(gui_window):
    """The layout follows the width of the window."""
    window = gui_window
    devices = [Device("Mouse", 80, kind="mouse"),
               Device("Headset", 90, kind="headset")]

    _resize(window, 550, 600)
    window.update_idletasks()
    window.set_devices(devices)
    window.update_idletasks()
    assert window._columns == 1

    # The window is stretched, so the devices move next to each other.
    _resize(window, 1000, 600)
    window.update_idletasks()
    window.update()
    assert window._columns == 2

    # And back again.
    _resize(window, 550, 600)
    window.update_idletasks()
    window.update()
    assert window._columns == 1


def test_the_cards_stay_visible_when_the_columns_change(gui_window):
    """The cards may not disappear when the window is resized.

    The cards used to stay hidden and keep the place they had in the
    old layout when the number of columns changed.
    """
    window = gui_window
    devices = [Device("Mouse", 80, kind="mouse"),
               Device("Headset", 90, kind="headset"),
               Device("Pad", 70, kind="controller")]
    window.set_devices(devices)
    window.update_idletasks()

    for width in (1400, 700, 400, 1900, 800):
        _resize(window, width, 700)
        window.update_idletasks()
        window.update()

        # Every card has to be on the screen.
        for card in window._cards:
            assert card.winfo_ismapped(), f"卡片在 {width}px 时不见了"
        # The cards have to be in the column they were put in.
        for index, card in enumerate(window._cards):
            assert card.grid_info()["column"] == index % window._columns


def test_the_cards_are_next_to_each_other_after_a_resize(gui_window):
    """The cards have to move to their new place right away."""
    window = gui_window
    devices = [Device("Mouse", 80, kind="mouse"),
               Device("Headset", 90, kind="headset"),
               Device("Pad", 70, kind="controller")]
    window.set_devices(devices)
    window.update_idletasks()

    # Three columns.
    _resize(window, 1400, 700)
    window.update_idletasks()
    window.update()
    assert window._columns == 3

    # One column: the cards have to be below each other.
    _resize(window, 700, 700)
    window.update_idletasks()
    window.update()
    assert window._columns == 1
    first, second = window._cards[0], window._cards[1]
    assert second.winfo_x() == first.winfo_x()
    assert second.winfo_y() > first.winfo_y()


def test_the_two_columns_do_not_overlap(gui_window):
    """The cards in the second column have to sit next to the first one."""
    window = gui_window
    _resize(window, 1000, 600)
    window.update_idletasks()

    devices = [Device("Mouse", 80, kind="mouse"),
               Device("Headset", 90, kind="headset")]
    window.set_devices(devices)
    window.update_idletasks()

    first, second = window._cards
    # The second card starts after the first one ends.
    assert second.winfo_x() >= first.winfo_x() + first.winfo_width()
    # Both cards are on the same row.
    assert first.grid_info()["row"] == second.grid_info()["row"]


def test_the_scrollbar_stays_inside_a_small_window(gui_window):
    """The scrollbar may not end up outside of a window that is small.

    The canvas used to take all the room, so the scrollbar was pushed
    out of the window and the devices below it could not be reached.
    """
    window = gui_window
    window.geometry("800x600")
    window.update_idletasks()
    window.set_devices([Device("Mouse", 80, kind="mouse"),
                        Device("Headset", 90, kind="headset"),
                        Device("Pad", 70, kind="controller")])
    window.update_idletasks()

    # The window is made as small as it may get.
    width, height = window.wm_minsize()
    window.geometry(f"{width}x{height}")
    window.update_idletasks()
    window.update()

    scrollbar = window.scrollbar
    # The content does not fit, so the scrollbar has to be there.
    assert scrollbar.winfo_ismapped()
    # And it has to be inside of the window.
    assert scrollbar.winfo_x() >= 0
    assert scrollbar.winfo_x() + scrollbar.winfo_width() <= window.winfo_width()
    # The canvas has to leave room for the scrollbar.
    assert window.canvas.winfo_width() + scrollbar.winfo_width() \
        <= window.winfo_width()


def test_the_devices_can_be_reached_in_a_small_window(gui_window):
    """Every device has to be reachable when the window is small."""
    window = gui_window
    window.geometry("800x600")
    window.update_idletasks()
    devices = [Device("Mouse", 80, kind="mouse"),
               Device("Headset", 90, kind="headset"),
               Device("Pad", 70, kind="controller")]
    window.set_devices(devices)
    window.update_idletasks()

    width, height = window.wm_minsize()
    window.geometry(f"{width}x{height}")
    window.update_idletasks()
    window.update()

    # The list is longer than the window, so it can be scrolled.
    assert window.canvas.yview()[0] < 1.0
    # Scrolling to the end shows the last device.
    window.canvas.yview_moveto(1.0)
    window.update_idletasks()
    assert window.canvas.yview()[1] == 1.0


def test_the_device_name_is_shortened_in_a_narrow_card(gui_window):
    """A long name may not run out of the card."""
    window = gui_window
    # The width is scaled with the screen, so the cards are the same size
    # whatever the scale of the display is.
    _resize(window, 360, 600)
    window.update_idletasks()

    long_name = "Razer Viper V3 Pro Wireless 无线游戏鼠标超长名称测试"
    window.set_devices([Device(long_name, 80, kind="mouse")])
    window.update()

    card = window._cards[0]
    # The whole name is kept.
    assert card._full_name == long_name
    # The name that is shown is shorter, so it fits into the card.
    shown = card.name_label.cget("text")
    assert shown.endswith("…")
    assert card.name_label.winfo_x() + card.name_label.winfo_reqwidth() \
        <= card.winfo_width()


def test_the_whole_name_is_shown_in_a_wide_card(gui_window):
    """A card with room for it shows the whole name."""
    window = gui_window
    # Two columns leave the cards wide enough for the whole name.
    _resize(window, 1000, 600)
    window.update_idletasks()

    name = "Razer Viper V3 Pro Wireless"
    window.set_devices([Device(name, 80, kind="mouse")])
    window.update_idletasks()

    card = window._cards[0]
    assert window._columns == 2
    assert card.name_label.cget("text") == name


def test_an_empty_device_list_still_works(gui_window):
    """The placeholder may not fight with the grid of the cards."""
    window = gui_window
    window.geometry("1000x600")
    window.update_idletasks()

    window.set_devices([])
    window.update_idletasks()
    assert len(window.list_frame.winfo_children()) == 1

    # And the cards still come back afterwards.
    window.set_devices([Device("Mouse", 80, kind="mouse")])
    window.update_idletasks()
    assert 1 <= window._columns <= 4


def test_devices_are_deduplicated_by_name():
    """The same device must not be reported twice."""
    devices = [Device("Mouse", 80, kind="mouse"),
               Device("Mouse", 80, kind="mouse")]
    unique = {}
    for device in devices:
        unique.setdefault(device.original_name, device)
    assert len(unique) == 1


# --------------------------------------------------------------------------
# Custom device names
# --------------------------------------------------------------------------


def test_config_keeps_the_custom_name():
    config = Config()
    config.set_custom_name("Razer Viper V3 Pro Wireless", "我的毒蝰")
    assert config.display_name("Razer Viper V3 Pro Wireless") == "我的毒蝰"
    # An unknown device keeps its original name.
    assert config.display_name("Other") == "Other"


def test_config_clears_the_custom_name():
    config = Config()
    config.set_custom_name("Mouse", "游戏鼠标")
    config.set_custom_name("Mouse", "")
    assert config.display_name("Mouse") == "Mouse"
    assert "Mouse" not in config.custom_names


def test_custom_name_is_applied_to_the_devices():
    config = Config()
    config.set_custom_name("Razer Viper V3 Pro Wireless", "我的毒蝰")
    devices = [Device("Razer Viper V3 Pro Wireless", 70, kind="mouse")]
    for device in devices:
        device.name = config.display_name(device.original_name)
    assert devices[0].name == "我的毒蝰"
    # The original name is kept for the next lookup.
    assert devices[0].original_name == "Razer Viper V3 Pro Wireless"


def test_custom_name_survives_a_config_roundtrip(tmp_path, monkeypatch):
    config = Config()
    config.set_custom_name("Mouse", "游戏鼠标")
    monkeypatch.setattr("batterytray.config.config_dir", lambda: tmp_path)
    config.save()

    loaded = Config.load()
    assert loaded.display_name("Mouse") == "游戏鼠标"


def test_device_keeps_the_original_name():
    device = Device("Razer Viper V3 Pro Wireless", 70, kind="mouse")
    assert device.original_name == "Razer Viper V3 Pro Wireless"

    device.name = "我的毒蝰"
    assert device.original_name == "Razer Viper V3 Pro Wireless"


def test_card_rename_reports_the_original_name(gui_window):
    """Renaming a card hands the original name to the callback."""
    renames = []
    window = gui_window
    window.app = type("App", (), {
        "rename_device": lambda self, original, new: renames.append((original, new)),
    })()
    window.set_devices([Device("Razer Viper V3 Pro Wireless", 70, kind="mouse")])
    window.update_idletasks()

    card = window._cards[0]
    card._start_rename()
    window.update_idletasks()
    assert card._editor is not None

    card._editor.delete(0, "end")
    card._editor.insert(0, "我的毒蝰")
    card._finish_rename("我的毒蝰")

    assert renames == [("Razer Viper V3 Pro Wireless", "我的毒蝰")]
    # The card shows the new name right away.
    assert card._full_name == "我的毒蝰"


def test_card_rename_can_be_cancelled(gui_window):
    """Escape keeps the original name."""
    renames = []
    window = gui_window
    window.app = type("App", (), {
        "rename_device": lambda self, original, new: renames.append((original, new)),
    })()
    window.set_devices([Device("Mouse", 70, kind="mouse")])
    window.update_idletasks()

    card = window._cards[0]
    card._start_rename()
    window.update_idletasks()
    card._editor.delete(0, "end")
    card._editor.insert(0, "别的名字")
    card._cancel_rename()

    assert renames == []
    assert card._editor is None
    assert card._full_name == "Mouse"


def test_rename_dialog_returns_the_new_name(gui_window):
    """The dialog hands the typed name back."""
    from batterytray.renamedialog import RenameDialog

    dialog = RenameDialog(gui_window, gui_window.family, gui_window.dpi,
                          "Mouse", "Mouse")
    try:
        gui_window.update_idletasks()
        assert dialog.entry.get() == "Mouse"
        dialog.entry.delete(0, "end")
        dialog.entry.insert(0, "游戏鼠标")
        dialog._confirm()
        assert dialog.result == "游戏鼠标"
    finally:
        try:
            dialog.destroy()
        except Exception:
            pass


def test_rename_dialog_can_be_cancelled(gui_window):
    from batterytray.renamedialog import RenameDialog

    dialog = RenameDialog(gui_window, gui_window.family, gui_window.dpi,
                          "Mouse", "Mouse")
    try:
        gui_window.update_idletasks()
        dialog._cancel()
        assert dialog.result is None
    finally:
        try:
            dialog.destroy()
        except Exception:
            pass


def test_rename_dialog_can_reset_to_the_original_name(gui_window):
    """Clearing the field restores the original name."""
    from batterytray.renamedialog import RenameDialog

    dialog = RenameDialog(gui_window, gui_window.family, gui_window.dpi,
                          "Mouse", "游戏鼠标")
    try:
        gui_window.update_idletasks()
        dialog._reset()
        assert dialog.entry.get() == ""
    finally:
        try:
            dialog.destroy()
        except Exception:
            pass


def test_quick_panel_row_offers_the_rename(gui_window):
    """Right clicking a row opens the rename menu."""
    from batterytray.quickpanel import QuickPanel

    requests = []
    panel = QuickPanel(gui_window, on_rename=requests.append)
    try:
        panel.set_devices([Device("Mouse", 80, kind="mouse")])
        gui_window.update_idletasks()
        row = panel._rows[0]
        assert row._original_name == "Mouse"
        assert row.on_rename is not None
    finally:
        panel.destroy()


def test_app_rename_updates_the_cached_devices(tmp_path, monkeypatch):
    """Renaming through the app updates the cached device list."""
    from batterytray.app import TrayApp

    monkeypatch.setattr("batterytray.config.config_dir", lambda: tmp_path)
    config = Config()
    app = TrayApp(config=config)
    app.devices = [Device("Mouse", 80, kind="mouse")]

    app.rename_device("Mouse", "游戏鼠标")
    assert app.devices[0].name == "游戏鼠标"
    assert app.devices[0].original_name == "Mouse"

    # The name has to survive a restart.
    assert Config.load().display_name("Mouse") == "游戏鼠标"

# --------------------------------------------------------------------------
# The settings window
# --------------------------------------------------------------------------


def test_the_settings_dialog_keeps_the_settings(gui_window):
    """Saving the dialog hands back the changed settings."""
    from batterytray.settingsdialog import SettingsDialog

    config = Config()
    dialog = SettingsDialog(gui_window, config, gui_window.family, gui_window.dpi)
    try:
        dialog.kind_vars["controller"].set(True)
        dialog.threshold_var.set(35)
        dialog.notify_var.set(False)
        dialog._confirm()

        assert dialog.result is not None
        assert "controller" in dialog.result.enabled_kinds
        assert dialog.result.low_battery_threshold == 35
        assert dialog.result.notify_low_battery is False
        # The settings the dialog does not show are carried over.
        assert dialog.result.custom_names == config.custom_names
    finally:
        try:
            dialog.destroy()
        except Exception:
            pass


def test_the_settings_dialog_can_be_cancelled(gui_window):
    """Cancelling leaves the settings alone."""
    from batterytray.settingsdialog import SettingsDialog

    dialog = SettingsDialog(gui_window, Config(), gui_window.family, gui_window.dpi)
    try:
        dialog._cancel()
        assert dialog.result is None
    finally:
        try:
            dialog.destroy()
        except Exception:
            pass


def test_the_settings_dialog_clamps_the_threshold(gui_window):
    """A threshold outside the usable range is forced back into it."""
    from batterytray.settingsdialog import SettingsDialog

    dialog = SettingsDialog(gui_window, Config(), gui_window.family, gui_window.dpi)
    try:
        dialog.threshold_var.set(500)
        assert dialog._clamped_threshold() == 100
        dialog.threshold_var.set(-3)
        assert dialog._clamped_threshold() == 1
        dialog.threshold_var.set(42)
        assert dialog._clamped_threshold() == 42
    finally:
        try:
            dialog.destroy()
        except Exception:
            pass


def test_applying_the_settings_saves_them(tmp_path, monkeypatch):
    """The app stores the new settings right away."""
    from batterytray.app import TrayApp

    monkeypatch.setattr("batterytray.config.config_dir", lambda: tmp_path)
    app = TrayApp(config=Config())

    new_config = Config()
    new_config.set_enabled_kinds(["headset", "controller"])
    new_config.low_battery_threshold = 30

    app.apply_config(new_config)

    assert app.config.low_battery_threshold == 30
    loaded = Config.load()
    assert loaded.low_battery_threshold == 30
    assert set(loaded.enabled_kinds) == {"headset", "controller"}


# --------------------------------------------------------------------------
# The simple battery
# --------------------------------------------------------------------------

class _FakeCanvas:
    """A canvas that only remembers what was drawn on it.

    The battery is drawn with plain polygons and a text, so the drawing
    can be checked without opening a window.
    """

    def __init__(self):
        self.polygons = []
        self.rectangles = []
        self.texts = []

    def create_polygon(self, points, fill="", outline="", width=1,
                       smooth=False, tags=()):
        self.polygons.append({"points": points, "fill": fill,
                               "outline": outline, "width": width})
        return len(self.polygons)

    def create_rectangle(self, *args, **kwargs):
        self.rectangles.append({"args": args, **kwargs})
        return len(self.rectangles)

    def create_text(self, *args, **kwargs):
        self.texts.append({"args": args, "kwargs": kwargs})
        return len(self.texts)


def test_the_battery_is_a_wide_rectangle():
    """The battery has to be a wide rectangle with the number in it."""
    from batterytray.widgets import draw_battery

    canvas = _FakeCanvas()
    body = draw_battery(canvas, 0, 0, 100, 30, 87, False, text="87%")

    assert body > 80
    # The body, the contact and the charge are the only shapes.
    assert len(canvas.polygons) == 3
    assert canvas.texts[0]["kwargs"]["text"] == "87%"


def test_the_battery_shows_the_number():
    """The number of the charge has to be printed in the battery."""
    from batterytray.widgets import draw_battery

    canvas = _FakeCanvas()
    draw_battery(canvas, 0, 0, 100, 30, 87, False, text="87%")
    assert len(canvas.texts) == 1
    assert canvas.texts[0]["kwargs"]["text"] == "87%"

    empty = _FakeCanvas()
    draw_battery(empty, 0, 0, 100, 30, 87, False, text="")
    assert not empty.texts


def test_the_battery_shows_the_charge():
    """The colour of the charge has to grow with the level."""
    from batterytray.widgets import draw_battery

    low = _FakeCanvas()
    draw_battery(low, 0, 0, 100, 30, 10, False)
    high = _FakeCanvas()
    draw_battery(high, 0, 0, 100, 30, 90, False)

    # The charge is the last shape that is drawn.
    from batterytray.widgets import ACCENT, DANGER

    low_fill = low.polygons[-1]["fill"]
    high_fill = high.polygons[-1]["fill"]
    assert low_fill != high_fill
    assert low_fill == DANGER
    assert high_fill == ACCENT


def test_an_empty_battery_has_no_charge():
    """A device that is not connected shows an empty outline."""
    from batterytray.widgets import draw_battery

    canvas = _FakeCanvas()
    draw_battery(canvas, 0, 0, 100, 30, None, False)
    # Only the contact and the body.
    assert len(canvas.polygons) == 2
    assert not canvas.rectangles


def test_the_charge_bar_grows_with_the_level():
    """The thin bar of a device row shows the charge as well."""
    from batterytray.widgets import draw_charge_bar

    low = _FakeCanvas()
    draw_charge_bar(low, 0, 0, 100, 8, 20)
    high = _FakeCanvas()
    draw_charge_bar(high, 0, 0, 100, 8, 80)

    def width_of(canvas):
        points = canvas.polygons[-1]["points"]
        return max(points[0::2]) - min(points[0::2])

    assert width_of(high) > width_of(low)
