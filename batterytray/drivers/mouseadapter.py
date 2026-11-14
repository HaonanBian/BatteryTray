"""One interface for the mouse settings of every supported vendor.

The Razer mice use the feature report protocol, the ASUS ROG mice use a
plain HID protocol. The two differ in almost every detail, so each one
keeps its own driver. This module hides that difference behind a single
interface, so the settings window does not have to care which mouse it is
talking to.

The drivers expose the same methods, so the wrapper mostly takes care of:

* picking the right driver for a device,
* turning the vendor specific errors into one kind of error,
* and presenting the button list in the same shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import asusmouse, mouseconfig
from .mouseconfig import DpiStage, MOUSE_BUTTON_IDS


class MouseSettingsError(Exception):
    """A setting could not be read or written."""


class MouseSleeping(MouseSettingsError):
    """The mouse did not answer because it is asleep."""


@dataclass(frozen=True)
class ButtonMapping:
    """The function assigned to one mouse button.

    The button id is the vendor specific one, so the UI has to ask the
    driver for its name.
    """

    button_id: int
    function_id: int
    data: bytes
    is_default: bool
    label: str


@dataclass(frozen=True)
class MouseSettings:
    """Everything the mouse reports about its configuration."""

    dpi: int
    polling_rate: int
    stages: list[DpiStage]
    active_stage: int
    supported_rates: tuple[int, ...]
    has_stages: bool


class MouseAdapter:
    """Wraps one vendor driver in a common interface."""

    def __init__(self, controller, vendor: str):
        self._controller = controller
        self.vendor = vendor

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def get_settings(self) -> MouseSettings:
        """Reads every setting the mouse exposes."""
        try:
            if self.vendor == "asus":
                return self._asus_settings()
            return self._razer_settings()
        except mouseconfig.MouseAsleepError as exc:
            raise MouseSleeping(str(exc)) from exc
        except asusmouse.AsusMouseAsleep as exc:
            raise MouseSleeping(str(exc)) from exc
        except mouseconfig.MouseConfigError as exc:
            raise MouseSettingsError(str(exc)) from exc
        except asusmouse.AsusMouseError as exc:
            raise MouseSettingsError(str(exc)) from exc

    def _razer_settings(self) -> MouseSettings:
        """Reads the settings of a Razer mouse."""
        settings = self._controller.get_settings()
        return MouseSettings(
            dpi=settings.dpi_x,
            polling_rate=settings.polling_rate,
            stages=list(settings.stages),
            active_stage=settings.active_stage,
            supported_rates=self._controller.supported_polling_rates,
            has_stages=settings.has_stages,
        )

    def _asus_settings(self) -> MouseSettings:
        """Reads the settings of an ASUS mouse."""
        settings = self._controller.get_settings()
        stages = [DpiStage(dpi=stage.dpi_x) for stage in settings.dpi_stages]
        return MouseSettings(
            dpi=settings.dpi_stages[0].dpi_x if settings.dpi_stages else 0,
            polling_rate=settings.polling_rate,
            stages=stages,
            active_stage=settings.active_dpi_stage,
            supported_rates=tuple(sorted(asusmouse.POLLING_RATES)),
            has_stages=bool(settings.dpi_stages),
        )

    def list_buttons(self) -> list[ButtonMapping]:
        """Reads the function of every button."""
        try:
            if self.vendor == "asus":
                return self._asus_buttons()
            return self._razer_buttons()
        except mouseconfig.MouseAsleepError as exc:
            raise MouseSleeping(str(exc)) from exc
        except asusmouse.AsusMouseAsleep as exc:
            raise MouseSleeping(str(exc)) from exc
        except mouseconfig.MouseConfigError as exc:
            raise MouseSettingsError(str(exc)) from exc
        except asusmouse.AsusMouseError as exc:
            raise MouseSettingsError(str(exc)) from exc

    def _razer_buttons(self) -> list[ButtonMapping]:
        """Reads the buttons of a Razer mouse."""
        result: list[ButtonMapping] = []
        for button_id in self._controller.list_buttons():
            try:
                mapping = self._controller.get_button_mapping(button_id)
            except mouseconfig.MouseConfigError:
                continue
            result.append(ButtonMapping(
                button_id=button_id,
                function_id=mapping.function_id,
                data=mapping.data,
                is_default=mapping.is_default,
                label=mapping.label,
            ))
        return result

    def _asus_buttons(self) -> list[ButtonMapping]:
        """Reads the buttons of an ASUS mouse."""
        result: list[ButtonMapping] = []
        for button_id in self._controller.list_buttons():
            try:
                mapping = self._controller.get_button_mapping(button_id)
            except asusmouse.AsusMouseError:
                continue
            result.append(ButtonMapping(
                button_id=button_id,
                function_id=mapping.action_code,
                data=bytes([mapping.action_code & 0xFF,
                            (mapping.action_code >> 8) & 0xFF]),
                is_default=mapping.is_default,
                label=mapping.label,
            ))
        return result

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def set_button(self, button_id: int, kind: str, function_id: int,
                   code: int) -> None:
        """Writes the function of one button.

        ``kind`` is ``default``, ``code`` or ``function``.
        """
        try:
            if self.vendor == "asus":
                self._set_asus_button(button_id, kind, function_id, code)
                return
            if kind == "default":
                self._controller.reset_button(button_id)
            elif kind == "code":
                self._controller.assign_button_code(button_id, code)
            else:
                self._controller.set_button_mapping(button_id, function_id)
        except mouseconfig.MouseAsleepError as exc:
            raise MouseSleeping(str(exc)) from exc
        except asusmouse.AsusMouseAsleep as exc:
            raise MouseSleeping(str(exc)) from exc
        except mouseconfig.MouseConfigError as exc:
            raise MouseSettingsError(str(exc)) from exc
        except asusmouse.AsusMouseError as exc:
            raise MouseSettingsError(str(exc)) from exc

    def _set_asus_button(self, button_id: int, kind: str, function_id: int,
                         code: int) -> None:
        """Writes the action of an ASUS button.

        The ASUS protocol stores an action code rather than a function id,
        so the action codes are mapped back to the codes the UI uses.
        """
        if kind == "default":
            self._controller.reset_button(button_id)
            return
        if kind == "code":
            self._controller.assign_button_code(button_id, code)
            return
        # The function id of the UI is the action code of the ASUS
        # protocol.
        self._controller.set_button_action(button_id, function_id)

    def reset_all_buttons(self) -> None:
        """Restores every button to its factory default."""
        try:
            self._controller.reset_all_buttons()
        except mouseconfig.MouseAsleepError as exc:
            raise MouseSleeping(str(exc)) from exc
        except asusmouse.AsusMouseAsleep as exc:
            raise MouseSleeping(str(exc)) from exc
        except mouseconfig.MouseConfigError as exc:
            raise MouseSettingsError(str(exc)) from exc
        except asusmouse.AsusMouseError as exc:
            raise MouseSettingsError(str(exc)) from exc

    def reset_to_factory(self) -> None:
        """Restores the whole configuration of the mouse.

        Every part of the configuration goes back to its default: the
        buttons, the DPI, the polling rate and the DPI stages. Neither
        protocol has a real factory reset command, so the driver writes
        the defaults one by one.
        """
        try:
            self._controller.reset_to_factory()
        except mouseconfig.MouseAsleepError as exc:
            raise MouseSleeping(str(exc)) from exc
        except asusmouse.AsusMouseAsleep as exc:
            raise MouseSleeping(str(exc)) from exc
        except mouseconfig.MouseConfigError as exc:
            raise MouseSettingsError(str(exc)) from exc
        except asusmouse.AsusMouseError as exc:
            raise MouseSettingsError(str(exc)) from exc

    def apply_settings(self, dpi: int, polling_rate: int,
                       stages: list[DpiStage]) -> None:
        """Writes the settings and reads them back for a check."""
        try:
            if self.vendor == "asus":
                asus_stages = [asusmouse.AsusDpiStage(dpi_x=stage.dpi,
                                                       dpi_y=stage.dpi)
                                for stage in stages]
                self._controller.apply_settings(
                    polling_rate=polling_rate, stages=asus_stages)
                return
            self._controller.apply_settings(dpi=dpi,
                                           polling_rate=polling_rate,
                                           stages=stages)
        except mouseconfig.MouseAsleepError as exc:
            raise MouseSleeping(str(exc)) from exc
        except asusmouse.AsusMouseAsleep as exc:
            raise MouseSleeping(str(exc)) from exc
        except mouseconfig.MouseConfigError as exc:
            raise MouseSettingsError(str(exc)) from exc
        except asusmouse.AsusMouseError as exc:
            raise MouseSettingsError(str(exc)) from exc

    def close(self) -> None:
        """Releases the HID handle."""
        self._controller.close()

    # ------------------------------------------------------------------
    # Naming
    # ------------------------------------------------------------------

    def button_name(self, button_id: int) -> str:
        """The name of a button."""
        if self.vendor == "asus":
            return asusmouse.BUTTON_CODES.get(button_id,
                                              f"按键 0x{button_id:04X}")
        return MOUSE_BUTTON_IDS.get(button_id, f"按键 {button_id}")

    def function_options(self) -> dict[str, tuple[str, int, int]]:
        """The functions the dropdown offers, keyed by their label."""
        if self.vendor == "asus":
            return _asus_options()
        return _razer_options()


def _razer_options() -> dict[str, tuple[str, int, int]]:
    """The functions a Razer mouse offers."""
    options: dict[str, tuple[str, int, int]] = {
        "默认值": ("default", 0, 0),
        "无操作": ("function", mouseconfig.FUNCTION_NONE, 0),
    }
    for code, name in mouseconfig.ASSIGNABLE_BUTTON_CODES.items():
        options[f"鼠标按键：{name}"] = ("code", 0, code)
    for function_id, name in mouseconfig.BUTTON_FUNCTIONS.items():
        if function_id in (mouseconfig.FUNCTION_NONE,
                           mouseconfig.FUNCTION_DEFAULT):
            continue
        options[name] = ("function", function_id, 0)
    return options


def _asus_options() -> dict[str, tuple[str, int, int]]:
    """The functions an ASUS mouse offers.

    The ASUS protocol stores an action code rather than a function id, so
    the action codes are the ones the UI shows.
    """
    options: dict[str, tuple[str, int, int]] = {
        "默认值": ("default", 0, 0),
    }
    for code, name in asusmouse.ASSIGNABLE_BUTTON_CODES.items():
        options[f"鼠标按键：{name}"] = ("code", 0, code)
    for code, name in asusmouse.ACTION_CODES.items():
        if code == 0:
            options["无操作"] = ("function", code, 0)
            continue
        # The mouse button codes are already offered as a mouse button.
        if code in asusmouse.ASSIGNABLE_BUTTON_CODES:
            continue
        options[name] = ("function", code, 0)
    return options


def is_asus_device(device_name: str) -> bool:
    """Whether a device name belongs to an ASUS mouse."""
    lowered = device_name.lower()
    return "rog" in lowered or "asus" in lowered or "asustek" in lowered


def open_mouse(device_name: str,
               product_id: int | None = None) -> MouseAdapter | None:
    """Opens the mouse that belongs to a device.

    The vendor is guessed from the device name, because the two brands
    use completely different protocols and a wrong guess only shows up as
    a device that does not answer.
    """
    if is_asus_device(device_name):
        controller = asusmouse.open_mouse(product_id)
        if controller is not None:
            return MouseAdapter(controller, "asus")
        return None

    controller = mouseconfig.open_mouse(product_id)
    if controller is not None:
        return MouseAdapter(controller, "razer")
    return None
