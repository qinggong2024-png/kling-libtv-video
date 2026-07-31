import uuid
from typing import Final

from libtv_agent.domain.models import PromptPreset
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_PROMPT_PRESET_NAME: Final = "默认 1"

DEFAULT_PROMPT_PRESET_SPECS: Final[tuple[tuple[str, str, str], ...]] = (
    (
        "image_fusion",
        DEFAULT_PROMPT_PRESET_NAME,
        "以图一为底图，仅将图一人物身上的上衣替换为图二的球衣，完整保留图一原始背景、"
        "人物身份、脸部、发型、姿态、下装、构图、机位、光线和色调。不要抠出人物，不要"
        "移除、替换、虚化或重构背景。球衣上网眼小孔清晰可见，衣服自然贴合身体，有自然的"
        "褶皱和垂落，球衣的一角自然塞进裤子，oversize风格，融合后衣服的色调光影和环境"
        "统一协调",
    ),
    (
        "image_storyboard",
        DEFAULT_PROMPT_PRESET_NAME,
        "根据图一的人物和环境，生成一张人物别的姿势和拍摄角度的图片，保留人物脸部的毛孔和"
        "绒毛细节，自然的皮肤纹理，人物比例正常，保持图一的色调和光影不变，保持衣服的印花"
        "和结构不变正面与图二一致，背面与图三一致，人物动作自然，表情放松，人物和环境比例"
        "大小正常，人物高度和透视与环境的关系参考图一的身高",
    ),
    (
        "video",
        DEFAULT_PROMPT_PRESET_NAME,
        "生成一段动态视频，智能分镜。iPhone17后置拍摄效果模仿手持镜头拍摄，画面带有轻微"
        "自然的晃动。模特做了几个自然的动作展示今天的穿搭，100%还原球衣的网眼小孔，还原"
        "球衣的印花图案和文字细节，画面整体呈现真实自然，保留模特面部瑕疵，皮肤不要过度"
        "光滑，保留毛孔细节和绒毛，真实皮肤质感\n"
        "动作包含：\n"
        "1. 模特在原地做了几个自然的动作展示穿搭\n"
        "2. 画面切上半身，模特表情自然自信，动作流畅，展示衣服图案\n"
        "3. 模特走近镜头展示衣服 细节轻扶衣服\n"
        "要求画面流畅自然，人物皮肤保留瑕疵细节，动态有松弛感，自然流畅，保持原图光感和"
        "色调风格，画面整体真实自然光线和谐统一，9:16竖屏，高清8K。包含以上动作",
    ),
)


def add_default_prompt_presets(session: AsyncSession, user_id: uuid.UUID) -> None:
    for scope, name, content in DEFAULT_PROMPT_PRESET_SPECS:
        session.add(
            PromptPreset(
                user_id=user_id,
                scope=scope,
                name=name,
                content=content,
                sort_order=0,
            )
        )
