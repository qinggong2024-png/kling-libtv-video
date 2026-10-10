from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

CameraFamily = Literal["locked", "push_in", "pull_back", "lateral_follow"]


@dataclass(frozen=True)
class CameraMotion:
    family: CameraFamily
    instruction: str
    energy: str = "low"
    max_axes: int = 1


CAMERA_MOTIONS: dict[str, CameraMotion] = {
    "locked": CameraMotion("locked", "沿用输入机位和景别，构图稳定", max_axes=0),
    "push_in": CameraMotion("push_in", "沿用输入机位，单轴轻推，完整保留上装"),
    "pull_back": CameraMotion("pull_back", "沿用输入机位，单轴轻退，上装保持可辨"),
    "lateral_follow": CameraMotion(
        "lateral_follow",
        "沿用输入机位，单轴小幅平行跟随，保持上装清晰",
    ),
}

# Exact aliases only: unrestricted camera prose never becomes executable motion.
_CAMERA_ALIASES = {
    "slow subtle push-in": "push_in",
    "gentle push-in": "push_in",
    "minor push-in": "push_in",
    "subtle push-in on product": "push_in",
    "slow push-in": "push_in",
    "gentle pull-back": "pull_back",
    "slight tracking": "lateral_follow",
    "walking follow": "lateral_follow",
    "subtle follow": "lateral_follow",
    "static": "locked",
    "locked camera": "locked",
}


def camera_motion(value: str | None) -> CameraMotion:
    key = (value or "locked").strip().lower()
    return CAMERA_MOTIONS.get(_CAMERA_ALIASES.get(key, key), CAMERA_MOTIONS["locked"])


@dataclass(frozen=True)
class ShotMotionContract:
    start_state: str
    primary_action: str
    camera: CameraMotion
    environment_motion: str
    end_state: str
    preserved_facts: tuple[str, ...]
    product_scope: str = "upper_garment"
    version: str = "upper-garment-shot-v1"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def render(self) -> str:
        return (
            f"进入：{self.start_state}；主动作：{self.primary_action}；"
            f"镜头：{self.camera.instruction}；环境：{self.environment_motion}；"
            f"退出：{self.end_state}；每镜仅一个主动作，表演基调不添加肢体动作"
        )


def shot_motion_contract(primary_action: str, camera: CameraMotion) -> ShotMotionContract:
    return ShotMotionContract(
        start_state="沿用对应输入姿态、手位与持物关系",
        primary_action=primary_action,
        camera=camera,
        environment_motion="仅已有上装衣料随动作轻微响应，背景与光线沿用输入",
        end_state="沿用输入支持的姿态减速停稳，上装清晰停留",
        preserved_facts=("人物身份", "上装版型、领口、袖口、扣件", "配色、材质、印花、Logo、文字"),
    )
