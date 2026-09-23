"""Future RP2040/TDOA integration boundary with an honest unavailable default."""

from control_center.models.state import TdoaState


class UnavailableTdoaSource:
    def read(self) -> TdoaState:
        return TdoaState()

    @property
    def available(self) -> bool:
        return False
