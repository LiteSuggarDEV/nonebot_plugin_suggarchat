from typing import TypeAlias

from nonebot.adapters.onebot.v11 import (
    GroupAdminNoticeEvent,
    GroupBanNoticeEvent,
    GroupDecreaseNoticeEvent,
    GroupIncreaseNoticeEvent,
    GroupMessageEvent,
    GroupRecallNoticeEvent,
    GroupRequestEvent,
    GroupUploadNoticeEvent,
    HonorNotifyEvent,
)

GroupEvent: TypeAlias = (
    GroupAdminNoticeEvent
    | GroupDecreaseNoticeEvent
    | GroupIncreaseNoticeEvent
    | GroupMessageEvent
    | GroupRequestEvent
    | GroupUploadNoticeEvent
    | GroupRecallNoticeEvent
    | GroupBanNoticeEvent
    | HonorNotifyEvent
)
