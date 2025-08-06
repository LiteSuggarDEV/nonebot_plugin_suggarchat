import inspect
from collections.abc import Awaitable, Callable
from copy import deepcopy
from types import FrameType
from typing import Any, ClassVar

from nonebot import logger
from nonebot.exception import (
    FinishedException,
    NoneBotException,
    ProcessException,
    StopPropagation,
)
from pydantic import BaseModel, Field
from typing_extensions import Self

from .event import SuggarEvent
from .exception import BlockException, CancelException, PassException

"""
suggar matcher
"""


class FunctionData(BaseModel, arbitrary_types_allowed=True):
    function: Callable[..., Awaitable[Any]] = Field(...)
    signature: inspect.Signature = Field(...)
    frame: FrameType = Field(...)
    priority: int = Field(...)
    block: bool = Field(...)
    matcher: Any = Field(...)


class EventRegistry:
    _instance = None
    __event_handlers: ClassVar[dict[str, list[FunctionData]]] = {}

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register_handler(self, event_type: str, data: FunctionData):
        self.__event_handlers.setdefault(event_type, []).append(data)

    def get_handlers(self, event_type: str) -> list[FunctionData]:
        self.__event_handlers.setdefault(event_type, [])
        self.__event_handlers[event_type].sort(key=lambda x: x.priority, reverse=False)
        return self.__event_handlers[event_type]

    def _all(self) -> dict[str, list[FunctionData]]:
        return self.__event_handlers


class Matcher:
    def __init__(self, event_type: str, priority: int = 10, block: bool = True):
        """构造函数，初始化Matcher对象。
        Args:
            event_type (str): 事件类型
            priority (int, optional): 优先级。 Defaults to 10.
            block (bool, optional): 是否阻止后续事件。 Defaults to True.
        """
        self.event_type = event_type
        self.priority = priority
        self.block = block

    def handle(self):
        """
        事件处理函数注册函数
        """
        if self.priority <= 0:
            raise ValueError("事件优先级不能为0或负！")

        def wrapper(
            func: Callable[..., Awaitable[Any]],
        ):
            frame = inspect.currentframe()
            assert frame is not None, "Frame is None!!!"
            func_data = FunctionData(
                function=func,
                signature=inspect.signature(func),
                frame=frame,
                priority=self.priority,
                block=self.block,
                matcher=self,
            )
            EventRegistry().register_handler(self.event_type, func_data)
            return func

        return wrapper

    def stop_process(self):
        """
        阻止当前Suggar事件循环继续运行并立即停止当前的处理器。
        """
        raise BlockException()

    def cancel(self):
        """
        终止Nonebot层的处理器
        """
        raise FinishedException()

    def cancel_matcher(self):
        """
        停止当前Suggar事件处理并取消。
        """
        raise CancelException()

    def cancel_nonebot_process(self):
        """
        直接停止Nonebot的处理流程，不触发任何事件处理程序。
        """
        raise StopPropagation()

    def pass_event(self):
        """
        忽略当前处理器，继续处理下一个。
        """
        raise PassException()


class MatcherManager:
    @staticmethod
    async def trigger_event(*args, **kwargs):
        """
        触发特定类型的事件，并调用该类型的所有注册事件处理程序。

        参数:
        - event: SuggarEvent 对象，包含事件相关数据。
        - **kwargs: 关键字参数，传递给依赖注入系统的参数。
        - *args: 可变参数，传递给依赖注入系统的参数。
        """
        event: SuggarEvent | None = None
        for i in args:
            if isinstance(i, SuggarEvent):
                event = i
                break
        if not event:
            logger.error("事件必须被传入，但是是没有找到！")
            return
        event_type = event.get_event_type()  # 获取事件类型
        priority_tmp = 0
        logger.info(f"正在为事件: {event_type} 运行matcher!")
        # 检查是否有处理该事件类型的处理程序
        if matcher_list := EventRegistry().get_handlers(event_type):
            for matcher in matcher_list:
                if matcher.priority != priority_tmp:
                    priority_tmp = matcher.priority
                    logger.info(f"为优先级 {priority_tmp} 运行Matcher......")

                signature = matcher.signature
                frame = matcher.frame
                line_number = frame.f_lineno
                file_name = frame.f_code.co_filename
                handler = matcher.function
                session_args = [matcher.matcher, *args]
                session_kwargs = {**deepcopy(kwargs)}

                args_types = {k: v.annotation for k, v in signature.parameters.items()}
                filtered_args_types = {
                    k: v for k, v in args_types.items() if v is not inspect._empty
                }
                if args_types != filtered_args_types:
                    failed_args = list(args_types.keys() - filtered_args_types.keys())
                    logger.warning(
                        f"匹配器 {matcher.function.__name__} (File: {file_name}: Line {frame.f_lineno!s}) 有没有类型注解的参数！"
                        + f"(Args:{''.join(i + ',' for i in failed_args)}).跳过......"
                    )
                    continue
                new_args = []
                used_indices = set()
                for param_type in filtered_args_types.values():
                    for i, arg in enumerate(session_args):
                        if i in used_indices:
                            continue
                        if isinstance(arg, param_type):
                            new_args.append(arg)
                            used_indices.add(i)
                            break
                new_args_tuple = tuple(new_args)

                # 获取关键词参数类型注解
                kwparams = signature.parameters
                f_kwargs = {
                    param_name: session_kwargs[param.annotation]
                    for param_name, param in kwparams.items()
                    if param.annotation in session_kwargs
                }
                if len(new_args_tuple) != len(list(filtered_args_types)):
                    continue

                # 调用处理程序

                try:
                    logger.info(f"开始运行Matcher: '{handler.__name__}'")

                    await handler(*new_args_tuple, **f_kwargs)

                except ProcessException as e:
                    logger.info("停止Nonebot处理")
                    raise e
                except PassException:
                    logger.info(
                        f"Matcher '{handler.__name__}'(~{file_name}:{line_number}) 已跳过"
                    )
                    continue
                except CancelException:
                    logger.info("取消了Matcher处理")
                    return
                except BlockException:
                    break
                except NoneBotException:
                    raise
                except Exception as e:
                    logger.error(
                        f"运行时发生了错误 '{handler.__name__}'({file_name}:{line_number}) "
                    )
                    logger.opt(exception=e, colors=True).exception(str(e))
                    continue
                finally:
                    logger.info(f"处理器 {handler.__name__} 已结束")
                    if matcher.block:
                        break
        else:
            logger.info(f"没有为 {event_type} 事件注册的Matcher，跳过处理。")
